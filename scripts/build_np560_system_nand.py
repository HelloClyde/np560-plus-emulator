#!/usr/bin/env python3
"""Create a fresh system NAND via the vendor burner, then verify payload/ECC/boot.

Run inside Linux/WSL with QEMU and a C compiler. The initial factory record
is a reconstructed fixture, NOT a real device dump. Never reuse a user NAND.
All files/processes belong to a new output directory; partial evidence stays.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from np560_upd import parse_update, extract_update, word_swap
from build_np560_mp3_resident import PRG_SHA
from build_np560_factory_nand import write_erased_checkpoint
from build_np560_stream_burn_harness import build_program
from web.rom_bundle import player_bundle_settings

PACKAGE_SHA = '6f484f700be9429d7adbed3fa0655e1f23631f9b6e59efe785b302ff2974f6cf'
SCRIPTS = Path(__file__).resolve().parent
MIN_FREE_BYTES = 2 * 1024**3


def preflight(package, qemu, bundle, output):
    if sys.flags.optimize:
        raise ValueError('Python -O disables required safety checks')
    if output.exists():
        raise FileExistsError(f'refusing existing output directory: {output}')
    if not qemu.is_file() or not os.access(qemu, os.X_OK):
        raise ValueError('QEMU must be an executable on this host (run inside WSL)')
    compiler = shutil.which('cc')
    if not compiler:
        raise ValueError('a C compiler named cc is required for the checkpoint hasher')
    raw = package.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PACKAGE_SHA:
        raise ValueError('only the reviewed V3.80 NP560+.upd is supported')
    update = parse_update(package)
    blocks = {block.slot: block for block in update.blocks}
    if (blocks[0].kind != 'burner-code' or blocks[2].kind != 'program-word-image'
            or blocks[3].kind != 'nand-image'):
        raise ValueError('unexpected package slots')
    block = blocks[2]
    if hashlib.sha256(word_swap(raw[block.offset:block.offset+block.size])).hexdigest() != PRG_SHA:
        raise ValueError('package PRG identity mismatch')
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
    image = (bundle / 'resident.bin').read_bytes()
    if (manifest.get('original_prg_sha256') != PRG_SHA or manifest.get('rom_bytes') != len(image)
            or manifest.get('rom_sha256') != hashlib.sha256(image).hexdigest()):
        raise ValueError('ROM bundle identity mismatch')
    ancestor = output.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < MIN_FREE_BYTES:
        raise ValueError('need at least 2 GiB free for seed, result and failure evidence')
    return compiler


def build(package, qemu, bundle, output):
    package, qemu, bundle, output = (Path(p).resolve() for p in (package, qemu, bundle, output))
    compiler = preflight(package, qemu, bundle, output)
    output.mkdir(parents=True, exist_ok=False)
    commands = []
    report = dict(format='np560-system-nand-build-v1', passed=False,
                  reconstructed_factory_fixture=True, real_device_dump=False,
                  package_sha256=PACKAGE_SHA, commands=commands)

    def run(arguments):
        command = [str(arg) for arg in arguments]
        commands.append(command)
        print('STAGE: ' + ' '.join(command), flush=True)
        subprocess.run(command, check=True)

    try:
        extracted = extract_update(package, output / 'package', slots={0, 2, 3})
        settings = player_bundle_settings(bundle, extracted[2])
        report['rom_sha256'] = hashlib.sha256(settings['soc_rom'].read_bytes()).hexdigest()
        hasher = output / 'checkpoint-rehash'
        run([compiler, '-O2', SCRIPTS / 'np560_checkpoint_rehash.c', '-o', hasher])
        seed = output / 'factory-seed.nand'
        write_erased_checkpoint(seed, hasher)
        program, _ = build_program(extracted[3].stat().st_size, 'updateall')
        harness = output / 'burn-harness.prg'
        harness.write_bytes(program)
        nand = output / 'system.nand'
        run([sys.executable, SCRIPTS / 'burn_np560_stream.py', '--qemu', qemu,
             '--firmware', harness, '--soc-rom', settings['soc_rom'],
             '--burn-code', extracted[0], '--payload', extracted[3], '--output', nand,
             '--nand-checkpoint', seed, '--setup-mode', 'updateall', '--require-ecc',
             '--report-dir', output / 'burn'])
        verification = output / 'payload-verification.json'
        run([sys.executable, SCRIPTS / 'verify_np560_burn_payload.py', nand,
             '--package', package, '--report', verification])
        checks = json.loads(verification.read_text(encoding='utf-8'))
        if not checks['passed'] or not checks['full_package_payload']:
            raise ValueError('complete payload/ECC verification did not pass')
        run([sys.executable, SCRIPTS / 'probe_np560_checkpoint_boot.py', '--qemu', qemu,
             '--firmware', extracted[2], '--soc-rom', settings['soc_rom'],
             '--soc-rom-skeleton', '--nand-checkpoint', nand, '--package', package,
             '--output', output / 'boot', '--timeout', '180'])
        boot = json.loads((output / 'boot' / 'report.json').read_text(encoding='utf-8'))
        if not boot['passed']:
            raise ValueError('cold boot did not pass')
        digest = hashlib.sha256()
        with nand.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        report.update(passed=True, nand_sha256=digest.hexdigest(), nand_bytes=nand.stat().st_size,
                      scope='full package payload/ECC and cold boot; not all applications or USB hardware')
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        with (output / 'build-report.json').open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('package', 'qemu', 'soc-rom-bundle', 'output'):
        parser.add_argument('--' + option, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.package, args.qemu, args.soc_rom_bundle, args.output), indent=2))


if __name__ == '__main__':
    main()
