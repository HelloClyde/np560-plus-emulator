"""Bind checked MP3/NPE ROM services to their actual image and firmware."""
import hashlib
import json
from pathlib import Path
import struct


NPE_ENTRY_OFFSETS = (0x02ACD8, 0x01B6DE, 0x01B7AA, 0x01B816,
                     0x01B84E, 0x02AD92)
NPE_PLAYER_SOURCES = {
    6: '815284dae5f7853d120e7f73f1e0444c292c4c8f313455c47a08df16a58f5031',
    8: '5e4be1ecda33813c1c5da627523d510f98b1a7e9785a16d43f87513269aaa85f',
}


def player_bundle_settings(directory: Path, firmware: Path, *, allow_experimental_eq=False) -> dict:
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    image_path = (directory / 'resident.bin').resolve()
    image = image_path.read_bytes()
    if (manifest.get('rom_bytes') != len(image) or
            manifest.get('rom_sha256') != hashlib.sha256(image).hexdigest()):
        raise ValueError('ROM bundle size/hash mismatch')
    if manifest.get('original_prg_sha256') != hashlib.sha256(firmware.read_bytes()).hexdigest():
        raise ValueError('ROM bundle does not match the selected firmware')
    hle = manifest.get('rom_mp3_hle', {})
    version = hle.get('version')
    if version not in (6, 8) or hle.get('original_prg_modified') is not False:
        raise ValueError('ROM bundle requires v6 or explicitly enabled experimental v8')
    if version == 8:
        if not allow_experimental_eq:
            raise ValueError('v8 requires --experimental-eq (assumed DSP, not factory ROM)')
        if hle.get('audio_mode_parameters') is not True or hle.get('audio_mode_dsp') is not True:
            raise ValueError('v8 audio mode manifest is incomplete')

    def address(value, size):
        if type(value) is not int or value & 1 or not 0x10000 <= value < value + size <= min(len(image), 0x30000):
            raise ValueError('ROM bundle entry outside the reconstructed ROM region')
        return value

    names = ('reset', 'decode_frame', 'next_granule', 'release', 'free_words', 'copy_pcm')
    if version == 8:
        names += ('mode_load', 'mode_enable', 'mode_disable')
    base = address(hle.get('base'), len(names) * 16)
    for index, name in enumerate(names):
        entry = base + index * 16
        marker = struct.pack('<8H', 0x0f00, 0xc620, 0x504d, 0x484c, version, index, 0, 0)
        if hle.get('targets', {}).get(name) != entry or image[entry:entry+16] != marker:
            raise ValueError('ROM bundle HLE marker/target mismatch')
    # Both supported versions replace this public ROM query. Valid gate
    # markers alone cannot detect a bundle wired to an old/wrong entry.
    target = hle['targets']['free_words']
    veneer = struct.pack('<2H', 0xad00 | target >> 16, target & 65535)
    if image[0x149be:0x149c2] != veneer:
        raise ValueError('ROM bundle input-space veneer mismatch')
    if version == 8:
        for public, name in ((0x14674, 'mode_load'), (0x146cc, 'mode_enable'), (0x146d0, 'mode_disable')):
            target = hle['targets'][name]
            veneer = struct.pack('<2H', 0xad00 | target >> 16, target & 65535)
            if image[public:public+4] != veneer:
                raise ValueError('ROM bundle audio-mode veneer mismatch')
    arena_image = 0
    if hle.get('arena_release') is True:
        arena = manifest.get('arena_release', {})
        arena_image = address(arena.get('allocator_image'), 0xf6)
        wrapper = address(arena.get('wrapper'), 4)
        expected = struct.pack('<2H', 0xad00 | (wrapper >> 16), wrapper & 65535)
        if image[arena_image:arena_image+4] != expected:
            raise ValueError('ROM bundle arena trampoline mismatch')
    elif hle.get('arena_release') is not False:
        raise ValueError('Invalid ROM bundle arena-release setting')
    npe_owned = False
    npe = manifest.get('rom_npe_hle')
    if npe is not None:
        if (not isinstance(npe, dict) or
                set(npe) != {'version', 'backend', 'format', 'entry_offsets',
                             'source_rom_sha256', 'scope'} or
                npe['version'] != 1 or npe['backend'] != 'owned-mode5' or
                npe['format'] != 13 or
                npe['entry_offsets'] != list(NPE_ENTRY_OFFSETS) or
                npe['source_rom_sha256'] != NPE_PLAYER_SOURCES[version]):
            raise ValueError('ROM bundle NPE HLE manifest is not reviewed')
        unpatched = bytearray(image)
        for entry in NPE_ENTRY_OFFSETS:
            if image[entry:entry + 4] != b'\x00\x0f\x20\xc6':
                raise ValueError(f'ROM bundle NPE HLE gate mismatch at {entry:06x}')
            unpatched[entry + 2:entry + 4] = b'\x00\x0f'
        if hashlib.sha256(unpatched).hexdigest() != npe['source_rom_sha256']:
            raise ValueError('ROM bundle NPE HLE differs from the reviewed player ROM')
        npe_owned = True
    # Never execute/parse machine_option as command text. Derive arguments
    # from checked numeric fields. Hash checks are integrity, not authenticity.
    return dict(soc_rom=image_path, soc_rom_skeleton=True,
                rom_mp3_hle_base=base, rom_mp3_arena_image=arena_image,
                rom_npe_codec_owned=npe_owned)
