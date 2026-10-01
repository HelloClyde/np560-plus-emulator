"""ROM bundle integrity and argument binding; no guest or NAND writes."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web.np560_web import parse_args
from web.rom_bundle import NPE_ENTRY_OFFSETS, NPE_PLAYER_SOURCES, player_bundle_settings


class BundleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.firmware = self.root / 'test.prg'
        self.firmware.write_bytes(b'fixture firmware')
        self.image = bytearray(0x14a00)
        names = ('reset', 'decode_frame', 'next_granule', 'release', 'free_words', 'copy_pcm')
        targets = {name: 0x10000 + i*16 for i, name in enumerate(names)}
        for i, address in enumerate(targets.values()):
            self.image[address:address+16] = struct.pack('<8H', 0xf00, 0xc620, 0x504d, 0x484c, 6, i, 0, 0)
        self.image[0x149be:0x149c2] = struct.pack('<2H', 0xad01, targets['free_words'] & 65535)
        self.manifest = dict(rom_bytes=len(self.image), original_prg_sha256=hashlib.sha256(b'fixture firmware').hexdigest(),
                             rom_mp3_hle=dict(version=6, original_prg_modified=False, base=0x10000,
                                              targets=targets, arena_release=False))
        self.publish()

    def publish(self):
        (self.root / 'resident.bin').write_bytes(self.image)
        self.manifest['rom_sha256'] = hashlib.sha256(self.image).hexdigest()
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def test_load_and_bind(self):
        args = parse_args(['--soc-rom-bundle', str(self.root), '--firmware', str(self.firmware)])
        self.assertEqual(args.rom_mp3_hle_base, 0x10000)
        self.assertEqual(args.rom_mp3_arena_image, 0)
        self.assertTrue(args.soc_rom_skeleton)
        self.assertFalse(args.rom_hle)
        self.assertFalse(args.rom_npe_codec_owned)

    def test_npe_bundle_gates_are_verified_before_owning_decoder(self):
        self.image.extend(bytes(0x30000 - len(self.image)))
        for entry in NPE_ENTRY_OFFSETS:
            self.image[entry:entry + 4] = b'\x00\x0f' * 2
        source_hash = hashlib.sha256(self.image).hexdigest()
        for entry in NPE_ENTRY_OFFSETS:
            self.image[entry + 2:entry + 4] = b'\x20\xc6'
        self.manifest['rom_bytes'] = len(self.image)
        self.manifest['rom_npe_hle'] = dict(
            version=1, backend='owned-mode5', format=13,
            entry_offsets=list(NPE_ENTRY_OFFSETS), source_rom_sha256=source_hash,
            scope='candidate-compatible format 13 only; not original mask ROM')
        self.publish()
        with patch.dict(NPE_PLAYER_SOURCES, {6: source_hash}):
            args = parse_args(['--soc-rom-bundle', str(self.root), '--firmware', str(self.firmware)])
            self.assertTrue(args.rom_npe_codec_owned)
            self.image[NPE_ENTRY_OFFSETS[0] + 2] ^= 1
            self.publish()
            with self.assertRaisesRegex(ValueError, 'NPE HLE gate'):
                player_bundle_settings(self.root, self.firmware)
            self.image[NPE_ENTRY_OFFSETS[0] + 2] ^= 1
            self.image[0x18010] ^= 1
            self.publish()
            with self.assertRaisesRegex(ValueError, 'reviewed player ROM'):
                player_bundle_settings(self.root, self.firmware)

    def test_v8_requires_opt_in_and_validates_all_services(self):
        self.image.extend(bytes(max(0, 0x14700-len(self.image))))
        hle = self.manifest['rom_mp3_hle']
        hle.update(version=8, audio_mode_parameters=True, audio_mode_dsp=True)
        names = tuple(hle['targets']) + ('mode_load', 'mode_enable', 'mode_disable')
        for index, name in enumerate(names):
            target = 0x10000 + index*16
            hle['targets'][name] = target
            self.image[target:target+16] = struct.pack('<8H',0xf00,0xc620,0x504d,0x484c,8,index,0,0)
        for public, name in ((0x14674,'mode_load'),(0x146cc,'mode_enable'),(0x146d0,'mode_disable')):
            target=hle['targets'][name]
            self.image[public:public+4]=struct.pack('<2H',0xad01,target&65535)
        self.manifest['rom_bytes']=len(self.image)
        self.publish()
        with self.assertRaisesRegex(ValueError, 'experimental-eq'):
            player_bundle_settings(self.root,self.firmware)
        args=parse_args(['--soc-rom-bundle',str(self.root),'--firmware',str(self.firmware),'--experimental-eq'])
        self.assertEqual(args.rom_mp3_hle_base,0x10000)
        self.image[0x14674]^=1
        self.publish()
        with self.assertRaisesRegex(ValueError,'veneer'):
            player_bundle_settings(self.root,self.firmware,allow_experimental_eq=True)

    def test_corrupt_rom_rejected(self):
        (self.root / 'resident.bin').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'size/hash'):
            player_bundle_settings(self.root, self.firmware)

    def test_wrong_firmware_rejected(self):
        self.firmware.write_bytes(b'other')
        with self.assertRaisesRegex(ValueError, 'firmware'):
            player_bundle_settings(self.root, self.firmware)

    def test_changed_marker_rejected_even_with_updated_hash(self):
        self.image[0x10000] ^= 1
        self.publish()
        with self.assertRaisesRegex(ValueError, 'marker'):
            player_bundle_settings(self.root, self.firmware)

    def test_wrong_target_rejected(self):
        self.manifest['rom_mp3_hle']['targets']['release'] += 2
        self.publish()
        with self.assertRaisesRegex(ValueError, 'target'):
            player_bundle_settings(self.root, self.firmware)

    def test_input_space_public_entry_is_bound_to_service(self):
        # A consistent image hash does not prove its public ABI calls the
        # registered HLE gate. A rebuilt/mixed package can carry a wrong jump.
        for target in (0x10000, 0x10042):
            self.image[0x149be:0x149c2] = struct.pack('<2H', 0xad01, target & 65535)
            self.publish()
            with self.assertRaisesRegex(ValueError, 'input-space veneer'):
                player_bundle_settings(self.root, self.firmware)

    def test_arena_address_is_bound_to_actual_trampoline(self):
        self.image.extend(bytes(max(0, 0x10200 - len(self.image))))
        self.image[0x10080:0x10084] = struct.pack('<2H', 0xad01, 0x00f0)
        self.manifest['rom_bytes'] = len(self.image)
        self.manifest['rom_mp3_hle']['arena_release'] = True
        self.manifest['arena_release'] = dict(allocator_image=0x10080, wrapper=0x100f0)
        self.publish()
        self.assertEqual(player_bundle_settings(self.root, self.firmware)['rom_mp3_arena_image'], 0x10080)
        self.manifest['arena_release']['wrapper'] += 2
        self.publish()
        with self.assertRaisesRegex(ValueError, 'trampoline'):
            player_bundle_settings(self.root, self.firmware)

    def test_unaligned_base_is_rejected(self):
        self.manifest['rom_mp3_hle']['base'] += 1
        self.publish()
        with self.assertRaisesRegex(ValueError, 'region'):
            player_bundle_settings(self.root, self.firmware)

    def test_explicit_settings_cannot_override_bundle(self):
        for extra in (['--rom-mp3-hle-base=0'], ['--soc-rom', 'other'],
                      ['--device', 'other.json'], ['--hle-ui'], ['--soc-rom-skeleton'],
                      ['--rom-npe-codec-owned']):
            with self.subTest(extra=extra), patch('sys.stderr'), self.assertRaises(SystemExit):
                parse_args(['--soc-rom-bundle', str(self.root), '--firmware', str(self.firmware)] + extra)


if __name__ == '__main__':
    unittest.main()
