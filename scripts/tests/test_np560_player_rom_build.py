"""Fresh PRG-to-player pipeline: input identity, refusal, source isolation and output."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_np560_player_rom as pipeline
from web.rom_bundle import player_bundle_settings

FIRMWARE = Path(__file__).resolve().parents[2] / 'NP560+V3.80版系统升级程序' / 'NP560.PRG'


class PlayerROMBuildTests(unittest.TestCase):
    @unittest.skipUnless(FIRMWARE.is_file(), 'requires user-supplied V3.80 PRG')
    def test_explicit_eq_build_is_pinned_and_requires_launch_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'eq'
            report = pipeline.build(FIRMWARE, output, experimental_eq=True)
            self.assertEqual(report['stages']['player'],
                '5e4be1ecda33813c1c5da627523d510f98b1a7e9785a16d43f87513269aaa85f')
            self.assertEqual(report['stages']['npe_audio'], pipeline.EXPECTED_NPE[True])
            self.assertTrue(report['experimental_eq'])
            self.assertNotIn('audio_mode_dsp', pipeline.PLAYER_OPTIONS)
            with self.assertRaisesRegex(ValueError, 'experimental-eq'):
                player_bundle_settings(output, FIRMWARE)
            settings = player_bundle_settings(output, FIRMWARE, allow_experimental_eq=True)
            self.assertEqual(settings['rom_mp3_hle_base'],97514)
            self.assertTrue(settings['rom_npe_codec_owned'])

    def test_wrong_input_creates_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            firmware = root / 'wrong.prg'
            firmware.write_bytes(b'not reviewed firmware')
            with self.assertRaisesRegex(ValueError, 'unmodified V3.80'):
                pipeline.build(firmware, root / 'output')
            self.assertFalse((root / 'output').exists())

    def test_optimized_python_is_rejected_before_reading_input(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            result = subprocess.run([sys.executable, '-O', pipeline.__file__,
                                     '--firmware', str(Path(directory) / 'absent.prg'),
                                     '--output', str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('disables required builder checks', result.stderr)
            self.assertFalse(output.exists())

    def test_stage_hash_cannot_silently_drift(self):
        with self.assertRaisesRegex(ValueError, 'base ROM hash changed'):
            pipeline.check_stage('base', b'changed')

    @unittest.skipUnless(FIRMWARE.is_file(), 'requires user-supplied V3.80 PRG')
    def test_existing_output_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            marker = output / 'resident.bin'
            marker.write_bytes(b'user artifact')
            with self.assertRaises(FileExistsError):
                pipeline.build(FIRMWARE, output)
            self.assertEqual(marker.read_bytes(), b'user artifact')

    @unittest.skipUnless(FIRMWARE.is_file(), 'requires user-supplied V3.80 PRG')
    def test_new_bundle_uses_explicit_external_firmware_and_restores_globals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            firmware = root / 'external source with spaces.prg'
            shutil.copyfile(FIRMWARE, firmware)
            unavailable = root / 'must-not-read.prg'
            base = pipeline.vma03.reconstructed
            with patch.object(base, 'PROGRAM_SOURCE', unavailable), \
                    patch.object(base, 'PROVISION_TRIGGER_TARGET', 1234):
                report = pipeline.build(firmware, root / 'player')
                self.assertEqual(base.PROGRAM_SOURCE, unavailable)
                self.assertEqual(base.PROVISION_TRIGGER_TARGET, 1234)
                with patch.object(base, 'build_image', side_effect=RuntimeError('build failed')):
                    with self.assertRaisesRegex(RuntimeError, 'build failed'):
                        pipeline.build(firmware, root / 'failed')
                self.assertEqual(base.PROGRAM_SOURCE, unavailable)
                self.assertEqual(base.PROVISION_TRIGGER_TARGET, 1234)
            self.assertEqual(report['stages'],
                             {**pipeline.EXPECTED, 'npe_audio': pipeline.EXPECTED_NPE[False]})
            self.assertFalse(report['runtime_verified'])
            self.assertFalse(report['esac_supported'])
            self.assertEqual(hashlib.sha256(firmware.read_bytes()).hexdigest(), pipeline.resident.PRG_SHA)
            settings = player_bundle_settings(root / 'player', firmware)
            self.assertEqual(settings['rom_mp3_hle_base'], 138790)
            self.assertEqual(settings['rom_mp3_arena_image'], 93952)
            self.assertTrue(settings['rom_npe_codec_owned'])


if __name__ == '__main__':
    unittest.main()
