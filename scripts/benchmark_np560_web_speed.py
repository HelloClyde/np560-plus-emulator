"""Compare observer overhead with unchanged guest timing and boot inputs."""
import argparse
import json
from pathlib import Path
import re
import time
import subprocess
from web.np560_web import Emulator, artifact_identity


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=30)
    p.add_argument('--profile', action='store_true', help='read-only debugger samples, NOT timing evidence')
    p.add_argument('--minimal-only', action='store_true')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    identity = artifact_identity(Path('/mnt/e/qemu-dmcu-build/qemu-system-dmcu'))[1]
    for minimal in ((True,) if args.minimal_only else (False, True)):
        emu = Emulator(qemu=Path('/mnt/e/qemu-dmcu-build/qemu-system-dmcu'),
            firmware=Path('NP560+V3.80版系统升级程序/NP560.PRG'),
            soc_rom=Path('tmp/np560-mp3-arena-release-20260911-v2/resident.bin'),
            nand_checkpoint=Path('/mnt/e/qemu-dmcu-build/np560-mp3-tone-20260906-v1.nand'),
            boot_mode='firmware-vma03', soc_rom_skeleton=True,
            rom_mp3_hle_base=138790, rom_mp3_arena_image=93952,
            icount_shift=0, start_paused=True)
        try:
            for prop, value in [('instruction-clock', True), ('control-observers-minimal', minimal)]:
                emu.qmp.execute('qom-set', {'path':'/machine', 'property':prop, 'value':value})
            started = time.monotonic()
            emu.qmp.execute('cont')
            if args.profile:
                for sample in range(20):
                    time.sleep(.25)
                    trace = subprocess.run(['gdb', '-q', '-nx', '-batch', '-p', str(emu.process.pid),
                        '-ex', 'set pagination off', '-ex', 'thread apply all bt 6', '-ex', 'detach'],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)
                    (args.output / f'profile-{minimal}-{sample:02}.txt').write_text(trace.stdout)
                    if trace.returncode:
                        raise RuntimeError(trace.stdout)
            time.sleep(args.seconds)
            emu.qmp.execute('stop')
            elapsed = time.monotonic() - started
            clock = emu.qmp.execute('qom-get', {'path':'/machine', 'property':'instruction-clock-state'})
            state = emu.qmp.execute('qom-get', {'path':'/machine', 'property':'cpu-state'})
            ns = int(re.search(r'\bNS:(\d+)', clock)[1])
            result = dict(minimal=minimal, host_seconds=elapsed, guest_seconds=ns/1e9,
                          realtime_ratio=None if args.profile else ns/1e9/elapsed,
                          profiled=args.profile, qemu_sha256=identity, clock=clock, cpu=state)
            assert artifact_identity(Path('/mnt/e/qemu-dmcu-build/qemu-system-dmcu'))[1] == identity
            results.append(result)
            result['healthy'] = ('FAULT:0' in clock and all(
                f'{field}=none' in state for field in ('ROM_MISSING', 'UNSUPPORTED', 'INVALID_CONTROL')))
            assert result['healthy'], 'guest fault: speed result is not a successful run'
            print({k:v for k,v in result.items() if k != 'cpu'}, flush=True)
        finally:
            emu.close()
            (args.output/'report.json').write_text(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
