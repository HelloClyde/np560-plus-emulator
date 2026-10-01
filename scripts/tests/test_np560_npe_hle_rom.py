"""Only the verified NPE service returns may change in the experimental ROM."""

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_np560_npe_hle_rom import ENTRY_OFFSETS, RETS, STRICT, build


class NPEHLEGatesTest(unittest.TestCase):
    def test_only_return_words_are_patched(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "source.bin"
            output = Path(root) / "gates.bin"
            original = STRICT * (0x02AD94 // 2 + 1)
            source.write_bytes(original)
            report = build(source, output)
            result = output.read_bytes()
            self.assertEqual(len(result), len(original))
            self.assertTrue(report["ad92_implemented"])
            for offset in range(0, len(original), 2):
                self.assertEqual(result[offset:offset + 2],
                                 RETS if offset in {entry + 2 for entry in ENTRY_OFFSETS}
                                 else original[offset:offset + 2])
            with self.assertRaisesRegex(ValueError, "already exists"):
                build(source, output)

    def test_rejects_non_strict_entry(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "source.bin"
            output = Path(root) / "gates.bin"
            image = bytearray(STRICT * (0x02AD94 // 2 + 1))
            image[ENTRY_OFFSETS[0]] = 0x20
            source.write_bytes(image)
            with self.assertRaisesRegex(ValueError, "strict two-word"):
                build(source, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
