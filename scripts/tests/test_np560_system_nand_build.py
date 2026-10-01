"""Fresh NAND orchestration must refuse unsafe inputs and retain failure evidence."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_np560_system_nand as pipeline


class SystemNANDBuildTests(unittest.TestCase):
    def test_free_space_boundary_before_creating_any_artifact(self):
        # Controlled identities isolate the space gate; no real NAND/QEMU.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b'\x01\x02\x03\x04'
            package = root / 'fixture.upd'
            package.write_bytes(raw)
            prg_sha = hashlib.sha256(pipeline.word_swap(raw)).hexdigest()
            bundle = root / 'bundle'
            bundle.mkdir()
            (bundle / 'resident.bin').write_bytes(raw)
            (bundle / 'manifest.json').write_text(json.dumps(dict(
                original_prg_sha256=prg_sha, rom_bytes=len(raw),
                rom_sha256=hashlib.sha256(raw).hexdigest())), encoding='utf-8')
            update = SimpleNamespace(blocks=[SimpleNamespace(slot=slot, kind=kind,
                offset=0, size=len(raw)) for slot, kind in
                [(0, 'burner-code'), (2, 'program-word-image'), (3, 'nand-image')]])
            output = root / 'new' / 'output'
            with patch.object(pipeline, 'PACKAGE_SHA', hashlib.sha256(raw).hexdigest()), \
                    patch.object(pipeline, 'PRG_SHA', prg_sha), \
                    patch.object(pipeline, 'parse_update', return_value=update), \
                    patch.object(pipeline.shutil, 'which', return_value='cc'), \
                    patch.object(pipeline.shutil, 'disk_usage') as usage:
                usage.return_value = SimpleNamespace(free=pipeline.MIN_FREE_BYTES - 1)
                with self.assertRaisesRegex(ValueError, '2 GiB'):
                    pipeline.preflight(package, Path(sys.executable), bundle, output)
                self.assertFalse(output.parent.exists())
                usage.return_value = SimpleNamespace(free=pipeline.MIN_FREE_BYTES)
                self.assertEqual(pipeline.preflight(package, Path(sys.executable), bundle, output), 'cc')
                self.assertFalse(output.parent.exists())

    def test_existing_output_is_rejected_before_reading_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'system.nand'
            marker.write_bytes(b'user data')
            with self.assertRaises(FileExistsError):
                pipeline.build(root / 'absent.upd', Path(sys.executable), root / 'bundle', root)
            self.assertEqual(marker.read_bytes(), b'user data')

    def test_invalid_package_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'wrong.upd'
            package.write_bytes(b'not supported')
            with patch.object(pipeline.shutil, 'which', return_value='cc'):
                with self.assertRaisesRegex(ValueError, 'reviewed V3.80'):
                    pipeline.build(package, Path(sys.executable), root / 'bundle', root / 'output')
            self.assertFalse((root / 'output').exists())

    def test_missing_compiler_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(pipeline.shutil, 'which', return_value=None):
                with self.assertRaisesRegex(ValueError, 'C compiler'):
                    pipeline.build(root / 'absent.upd', Path(sys.executable), root / 'bundle', root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_stage_failure_records_error_and_does_not_continue_to_burn(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rom = root / 'source.bin'
            rom.write_bytes(b'untouched')
            with patch.object(pipeline, 'preflight', return_value='cc'), \
                    patch.object(pipeline, 'extract_update', return_value={2: root / 'input.prg'}), \
                    patch.object(pipeline, 'player_bundle_settings', return_value={'soc_rom': rom}), \
                    patch.object(pipeline.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['cc'])) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    pipeline.build(root / 'package', Path(sys.executable), root / 'bundle', root / 'out')
                self.assertEqual(run.call_count, 1)
            report = json.loads((root / 'out' / 'build-report.json').read_text())
            self.assertFalse(report['passed'])
            self.assertIn('CalledProcessError', report['error'])
            self.assertEqual(rom.read_bytes(), b'untouched')
            self.assertFalse((root / 'out' / 'system.nand').exists())


if __name__ == '__main__':
    unittest.main()
