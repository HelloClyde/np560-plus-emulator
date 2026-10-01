#!/usr/bin/env python3
"""Build a checked player/NPE ROM bundle from V3.80 PRG, without tmp inputs.

Reuses reconstructed guest services, the v6 MP3 HLE profile, and six reviewed
NPE HLE returns for the independent mode-5 candidate decoder. This is not an
original mask-ROM dump, a proven ESAC implementation, or a NAND builder.
Output must be new; failures retain intermediate evidence, never overwrite it.
"""
import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import sys

import build_np560_vma03_soc_rom as vma03
import build_np560_mp3_resident as resident
import build_np560_mp3_factory as factory
import build_np560_mp3_hle as hle
import build_np560_npe_hle_rom as npe_hle
from web.rom_bundle import player_bundle_settings


EXPECTED = {
    'base': '36847961b6195c6ba9dc92656c7931ce0bbcf3e0e57fee316054e9246eccd9fc',
    'skeleton': resident.ROM_SHA,
    'native': 'db2e80fce8a320c6c0a17d0b00cac92f4aa86ac1c30601402bfaf8b5b2013616',
    'factory': 'e1d8857b2c8d5686ad0a8c48ea089421d595b9fe06b76f4ce89ad2b1129828ea',
    'player': '815284dae5f7853d120e7f73f1e0444c292c4c8f313455c47a08df16a58f5031',
}
EXPECTED_NPE = {
    False: '18cca3e8bc6f9512ae017935c37d5241b268a83a45920255f8054228bfcb260a',
    True: 'a0a2dbd72b33d2ec846f80fd1e566b79a2ca6060948aeed041f9f3298978b121',
}
BASE_OPTIONS = dict(initializer_overlay_probe=True, probe_rom_08_return=True,
                    probe_rom_01_return=True, probe_system_main=True,
                    probe_storage_global_templates=True, factory_linked_startup=True)
PLAYER_OPTIONS = dict(hle_free_words=True, deferred_input_retirement=True,
                      hle_pcm_copy=True, final_frame=True, priming=True,
                      arena_release=True, compact_workspace=True)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check_stage(name, image):
    actual = sha(image)
    if actual != EXPECTED[name]:
        raise ValueError(f'{name} ROM hash changed: {actual}; review source/layout before updating pin')
    return actual


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def write_bundle(directory, image, manifest):
    directory.mkdir()
    with (directory / 'resident.bin').open('xb') as stream:
        stream.write(image)
    write_json(directory / 'manifest.json', manifest)
    resident.load_bundle(directory)


def build(firmware, output, *, experimental_eq=False):
    # Downstream legacy builders rely on assertions for source/overlap guards.
    if sys.flags.optimize:
        raise ValueError('optimized Python (-O) disables required builder checks')
    firmware, output = Path(firmware).resolve(), Path(output).resolve()
    original = firmware.read_bytes()
    if len(original) != 0x400000 or sha(original) != resident.PRG_SHA:
        raise ValueError('only the reviewed unmodified V3.80 NP560.PRG is supported')
    output.mkdir(parents=True, exist_ok=False)
    stages = output / 'stages'
    stages.mkdir()
    report = dict(format='np560-player-build-v2', firmware_sha256=sha(original),
                  base_options=BASE_OPTIONS, player_options=PLAYER_OPTIONS, stages={},
                  original_mask_rom=False, esac_supported=False,
                  npe_mode5_candidate_supported=True,
                  runtime_verified=False, nand_created=False)
    # vma03 and the base builder must share the explicit input, not silently
    # fall back to a firmware file in the developer's checkout.
    reconstructed = vma03.reconstructed
    previous = reconstructed.PROGRAM_SOURCE, reconstructed.PROVISION_TRIGGER_TARGET
    try:
        reconstructed.PROGRAM_SOURCE = firmware
        reconstructed.PROVISION_TRIGGER_TARGET = 0
        image = reconstructed.build_image(**BASE_OPTIONS)
        report['stages']['base'] = check_stage('base', image)
        base = stages / 'base.bin'
        base.write_bytes(image)
        write_json(stages / 'base.json', reconstructed.manifest(image, **BASE_OPTIONS))
        skeleton = stages / 'skeleton.bin'
        with (stages / 'vma03-build.log').open('x', encoding='utf-8') as log:
            with contextlib.redirect_stdout(log):
                vma03.build(base, skeleton, stages / 'skeleton.json')
        report['stages']['skeleton'] = check_stage('skeleton', skeleton.read_bytes())
    finally:
        reconstructed.PROGRAM_SOURCE, reconstructed.PROVISION_TRIGGER_TARGET = previous
    _, image, manifest = resident.build(skeleton, firmware, fast_dct=True)
    report['stages']['native'] = check_stage('native', image)
    write_bundle(stages / 'native', image, manifest)
    _, image, manifest = factory.install(stages / 'native', firmware)
    report['stages']['factory'] = check_stage('factory', image)
    write_bundle(stages / 'factory', image, manifest)
    options = dict(PLAYER_OPTIONS)
    if experimental_eq:
        options.update(audio_mode_parameters=True, audio_mode_dsp=True)
    report['player_options'] = options
    report['experimental_eq'] = experimental_eq
    image, manifest = hle.build(stages / 'factory', **options)
    if experimental_eq:
        actual = sha(image)
        if actual != '5e4be1ecda33813c1c5da627523d510f98b1a7e9785a16d43f87513269aaa85f':
            raise ValueError('experimental EQ ROM hash changed: ' + actual)
        report['stages']['player'] = actual
    else:
        report['stages']['player'] = check_stage('player', image)
    player_hash = sha(image)
    image = npe_hle.patch_image(image)
    if sha(image) != EXPECTED_NPE[experimental_eq]:
        raise ValueError('NPE-gated player ROM hash changed: ' + sha(image))
    report['stages']['npe_audio'] = sha(image)
    manifest['rom_sha256'] = sha(image)
    manifest['rom_npe_hle'] = {
        'version': 1, 'backend': 'owned-mode5', 'format': 13,
        'entry_offsets': list(npe_hle.ENTRY_OFFSETS),
        'source_rom_sha256': player_hash,
        'scope': 'candidate-compatible format 13 only; not original mask ROM',
    }
    # Keep the final bundle at the user-selected root, directly consumable by
    # --soc-rom-bundle / -SocRomBundle. Intermediates are not runtime inputs.
    (output / 'resident.bin').write_bytes(image)
    write_json(output / 'manifest.json', manifest)
    resident.load_bundle(output)
    settings = player_bundle_settings(output, firmware, allow_experimental_eq=experimental_eq)
    report['machine'] = {key: value for key, value in settings.items() if key != 'soc_rom'}
    if firmware.read_bytes() != original:
        raise ValueError('firmware changed during build; do not use output')
    write_json(output / 'build-report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--experimental-eq', action='store_true', help='opt-in v8 assumed EQ DSP')
    args = parser.parse_args()
    report = build(args.firmware, args.output, experimental_eq=args.experimental_eq)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
