from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest
from pathlib import Path

import triage_np560_invalid_return as triage


ROOT = Path(__file__).resolve().parents[2]


class InvalidReturnTriageTests(unittest.TestCase):
    def test_v269_finds_file_create_validation_entry(self) -> None:
        snapshot = ROOT / "tmp" / "monitor-v269-provision-root-record" / "state.json"
        if not snapshot.exists():
            self.skipTest("v269 diagnostic snapshot is not present")
        trace, invalid = triage.load_snapshot(snapshot)
        entry = triage.infer_entry(trace, invalid)
        self.assertEqual((entry.target_segment, entry.target_pc), (0x32, 0xE560))

    def test_same_pc_scan_finds_balanced_official_body(self) -> None:
        program = triage.DEFAULT_PROGRAM.read_bytes()
        candidates = triage.find_candidates(program, 0xE560, 0x20, 0x2000)
        exact = [candidate for candidate in candidates if candidate.segment == 0x4F]
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0].size, 0x42)
        self.assertEqual(exact[0].link_words, 0)

    def test_preflight_finds_nested_unframed_storage_resolver(self) -> None:
        program = triage.DEFAULT_PROGRAM.read_bytes()
        candidate = next(
            item for item in triage.find_candidates(
                program, 0x5460, 0x20, 0x2000
            ) if item.segment == 0x42
        )
        callees = triage.direct_suspicious_callees(
            program, 0x25, candidate, 0x20, 0x2000
        )
        self.assertTrue(any(
            call == 0x25554A and target == 0x2916B0 and
            any(item.segment == 0x46 and item.size == 0x2D4
                for item in linked)
            for call, target, linked in callees
        ))

    def test_callback_rets_does_not_hide_balanced_epilogue(self) -> None:
        program = triage.DEFAULT_PROGRAM.read_bytes()
        candidates = triage.find_candidates(program, 0xBF4E, 0x20, 0x2000)
        exact = [candidate for candidate in candidates if candidate.segment == 0x3E]
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0].size, 0x538)
        self.assertEqual(exact[0].link_words, 5)

    def test_preflight_prefers_plus_1d_source_for_shared_pc(self) -> None:
        program = triage.DEFAULT_PROGRAM.read_bytes()
        parent = next(
            item for item in triage.find_candidates(
                program, 0x787E, 0x20, 0x2000
            ) if item.segment == 0x4B
        )
        callees = triage.direct_suspicious_callees(
            program, 0x2E, parent, 0x20, 0x2000
        )
        target = next(linked for _call, address, linked in callees
                      if address == 0x33507C)
        self.assertEqual([item.segment for item in target], [0x50])


if __name__ == "__main__":
    unittest.main()
