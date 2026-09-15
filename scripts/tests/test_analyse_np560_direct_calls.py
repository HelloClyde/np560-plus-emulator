from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest

import analyse_np560_direct_calls as calls


def words(*values: int) -> bytes:
    return b"".join(value.to_bytes(2, "little") for value in values)


class DirectCallAnalysisTests(unittest.TestCase):
    def test_extracts_target_source_and_stack_cleanup(self) -> None:
        data = words(0x4800, 0xBD1C, 0xD462, 0x50F4)
        found = calls.scan_direct_calls(data)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].source_address, 0x200002)
        self.assertEqual(found[0].target_address, 0x1CD462)
        self.assertEqual(found[0].cleanup_bytes, 4)

    def test_filters_target_segment_and_counts_abis(self) -> None:
        data = words(
            0xBD1C, 0xCCD4, 0x50FC,
            0xBD1C, 0xD462, 0x50F4,
            0xBD24, 0xEAEC, 0x50F4,
        )
        report = calls.build_report(data, target_segment=0x1C)
        self.assertEqual(report["selected_call_candidates"], 2)
        targets = {item["target"]: item for item in report["targets"]}
        self.assertEqual(targets["1C:CCD4"]["cleanup_bytes"], {"12": 1})
        self.assertEqual(targets["1C:D462"]["cleanup_bytes"], {"4": 1})

    def test_function_start_candidates_are_explicitly_limited(self) -> None:
        data = words(0x0000, 0x2E03, 0xC620, 0x2E07)
        found = calls.likely_function_starts(
            data, 0x200002, 0x200006
        )
        self.assertEqual([item["address"] for item in found], ["20:0002"])

    def test_context_lists_preceding_calls_without_inventing_semantics(self) -> None:
        data = words(
            0xBD1C, 0xCCD4, 0x50FC,
            0x4800,
            0xBD24, 0xEAEC, 0x50F4,
        )
        report = calls.build_report(
            data, target=0x24EAEC, context_bytes=0x20
        )
        nearby = report["calls"][0]["preceding_calls"]
        self.assertEqual([item["target"] for item in nearby], ["1C:CCD4"])
        self.assertEqual(nearby[0]["cleanup_bytes"], 12)


if __name__ == "__main__":
    unittest.main()
