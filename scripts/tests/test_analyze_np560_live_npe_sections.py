from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest

from scripts.analyze_np560_live_npe_sections import (
    scan_code_references,
    scan_data_segments,
    split_word_le,
)


class LiveNpeSectionConsumerTests(unittest.TestCase):
    def test_finds_split_word_section_pointer(self) -> None:
        sections = [(0x100, 4)] * 13 + [(0x13291A, 0x274), (0x132B8E, 0x384A0)]
        payload = bytearray(0x100)
        payload[0x20:0x24] = split_word_le(0x132B8E)
        hits = scan_data_segments({0x52: bytes(payload)}, sections)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["section"], 14)
        self.assertEqual(hits[0]["data_address"], 0x520020)

    def test_finds_two_word_code_reference_to_pointer_slot(self) -> None:
        # 88F0 0020 = MOV REG[F0], [0x0020].
        code = (0x88F0).to_bytes(2, "little") + (0x0020).to_bytes(2, "little")
        refs = scan_code_references({0x24: code}, [{
            "section": 14,
            "section_offset": 0x132B8E,
            "data_address": 0x520020,
            "data_pc": 0x0020,
        }])
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["code_address"], 0x240000)
        self.assertEqual(refs[0]["instruction"], "MOV REG[0xF0], [0x0020]")


if __name__ == "__main__":
    unittest.main()
