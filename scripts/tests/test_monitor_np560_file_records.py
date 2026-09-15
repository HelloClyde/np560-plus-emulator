from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest

import monitor_np560_file_records as monitor


def encoded_record(
    sequence: int,
    *,
    name: bytes = b"TRASH   CAN",
    attribute: int = 0x16,
    compare: str = "0001",
) -> str:
    data = bytearray(0x40)
    data[:11] = name
    data[11] = attribute
    selector = b"TRASH   CAN" + bytes(5)
    return (
        f"#{sequence}/call2/out50fe74/sel000f56/p511a40/"
        f"cur0001/lim0001/span0003/act0001/cmp{compare}/"
        f"selector{selector.hex()}/data{data.hex()}"
    )


class ParseCandidatesTests(unittest.TestCase):
    def test_decodes_name_and_selector_rejection(self) -> None:
        registers = (
            "PC=20:7848\nFILE_RECORD_CANDIDATES=COUNT:1 TRACE:" +
            encoded_record(1)
        )
        count, candidates = monitor.parse_candidates(registers)
        self.assertEqual(count, 1)
        self.assertEqual(candidates[0].short_name, "TRASH.CAN")
        self.assertEqual(candidates[0].selector_data[:11], b"TRASH   CAN")
        self.assertEqual(candidates[0].kind, "directory")
        self.assertEqual(candidates[0].decision, "selector-mismatch")

    def test_marks_missing_compare_and_volume(self) -> None:
        registers = (
            "FILE_RECORD_CANDIDATES=COUNT:1 TRACE:" +
            encoded_record(
                1, name=b"NO NAME    ", attribute=0x08, compare="-0000"
            )
        )
        _, candidates = monitor.parse_candidates(registers)
        self.assertFalse(candidates[0].compare_valid)
        self.assertEqual(candidates[0].kind, "volume")
        self.assertEqual(candidates[0].decision, "volume-rejected")

    def test_empty_or_unavailable_trace(self) -> None:
        self.assertEqual(monitor.parse_candidates("PC=00:0000"), (0, []))
        self.assertEqual(
            monitor.parse_candidates(
                "FILE_RECORD_CANDIDATES=COUNT:0 TRACE:"
            ),
            (0, []),
        )


if __name__ == "__main__":
    unittest.main()
