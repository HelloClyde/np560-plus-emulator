"""Keep the seek control explicit and non-destructive."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_np560_seek_fixture import build


class SeekFixtureTests(unittest.TestCase):
    def test_wrong_identity_creates_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.mp3'
            source.write_bytes(b'not-the-reviewed-fixture')
            with self.assertRaisesRegex(ValueError, 'verified LONG22'):
                build(source, root / 'output')
            self.assertFalse((root / 'output').exists())

    def test_exact_audio_preservation_and_no_overwrite(self):
        source = Path(__file__).resolve().parents[2] / 'tmp/np560-format-fixtures-20260922-v1/LONG22.MP3'
        if not source.is_file():
            self.skipTest('optional reviewed LONG22 fixture not present')
        before = source.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'control'
            report = build(source, output)
            result = (output / 'LONG22.MP3').read_bytes()
            self.assertEqual(result[:45], before[:45])
            self.assertEqual(result[45:], before[227:])
            self.assertEqual(len(before) - len(result), 182)
            self.assertEqual(hashlib.sha256(result).hexdigest(), report['output_sha256'])
            self.assertFalse(report['production_fix'])
            with self.assertRaises(FileExistsError):
                build(source, output)
            self.assertEqual((output / 'LONG22.MP3').read_bytes(), result)
        self.assertEqual(source.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
