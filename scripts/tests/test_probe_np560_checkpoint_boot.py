
# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import base64
import struct
import unittest
import zlib

from probe_np560_checkpoint_boot import OFF, ON, assess, render_png


class BootAssessmentTests(unittest.TestCase):
    def snapshot(self):
        return {"frame": base64.b64encode(bytes(240 * 120)).decode(),
                "registers": "ROM_HLE=off\nROM_MISSING=none\nINVALID_CONTROL=none\nUNSUPPORTED=none",
                "nand_state": "ERROR=0"}

    def test_exact_toolbar_and_clean_diagnostics(self):
        self.assertTrue(assess(self.snapshot(), bytes(5280))["passed"])

    def test_missing_diagnostics_or_nand_error_does_not_pass(self):
        for key, value in (("registers", ""), ("nand_state", "ERROR=01")):
            snapshot = self.snapshot()
            snapshot[key] = value
            self.assertFalse(assess(snapshot, bytes(5280))["passed"])

    def test_wrong_expected_category_is_not_fitted(self):
        self.assertFalse(assess(self.snapshot(), bytes([1]) * 5280)["passed"])

    def test_png_has_exact_nearest_neighbour_rows_and_valid_crcs(self):
        png = render_png(bytes([31]) + bytes(240 * 120 - 1))
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        offset = 8
        chunks = {}
        while offset < len(png):
            length, = struct.unpack_from(">I", png, offset)
            kind = png[offset + 4:offset + 8]
            data = png[offset + 8:offset + 8 + length]
            crc, = struct.unpack_from(">I", png, offset + 8 + length)
            self.assertEqual(crc, zlib.crc32(kind + data))
            chunks[kind] = data
            offset += 12 + length
        raw = zlib.decompress(chunks[b"IDAT"])
        row = b"\0" + bytes(ON) * 3 + bytes(OFF) * (719 - 2)
        self.assertEqual(len(raw), (720 * 3 + 1) * 360)
        self.assertEqual(raw[:len(row) * 3], row * 3)


if __name__ == "__main__":
    unittest.main()
