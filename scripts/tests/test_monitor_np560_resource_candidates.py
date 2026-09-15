#!/usr/bin/env python3

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = (Path(__file__).resolve().parent.parent / 'monitor_np560_resource_candidates.py')
SPEC = importlib.util.spec_from_file_location(
    "monitor_np560_resource_candidates", MODULE_PATH
)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = monitor
SPEC.loader.exec_module(monitor)


class ResourceCandidateMonitorTests(unittest.TestCase):
    def test_parses_record_and_caller(self) -> None:
        registers = """\
RESOURCE_CANDIDATES=COUNT:2 TRACE=20:00c8<00:0000/src0000(p000000)/0000>0000,0000/r80000/r100000/sp1000/fp1000/ds000,001/pfp0000/args0000,0000,0000,0000,0000,0000/outer00:0000/oargs0000,0000,0000,0000,0000,0000/rec-;2e:46bc<1e:8120/src1002(p511002)/0000>0e93,0158/r8007f/r100000/sp0ede/fp0efc/ds000,0a2/pfp0f16/args0000,4a34,0051,1000,0000,001e/outer2d:1234/oargs0001,0002,0003,0004,0005,0006/reccafe,0e93,0158,4b42
"""
        count, candidates = monitor.parse_candidates(registers)
        self.assertEqual(count, 2)
        self.assertEqual(candidates[-1].caller, "1e:8120")
        self.assertEqual(candidates[-1].source_physical, 0x511002)
        self.assertEqual(candidates[-1].outer_caller, "2d:1234")
        self.assertEqual(
            candidates[-1].copy_args,
            (0, 0x4A34, 0x51, 0x1000, 0, 0x1E),
        )
        self.assertTrue(candidates[-1].cafe_consistent)

    def test_detects_first_divergence_after_expected(self) -> None:
        good = monitor.ResourceCandidate(
            "2e:46bc", "1e:8120", 0x1002, 0x511002, 0, 0x0E93,
            0x0158, 0x7F, 0, 0xEDE, 0xEFC, 0, 0xA2, 0xF16,
            (0, 0x4A34, 0x51, 0x1000, 0, 0x1E), "2d:1234",
            (0, 0, 0, 0, 0, 0),
            (0xCAFE, 0x0E93, 0x0158),
        )
        bad = monitor.ResourceCandidate(
            "2e:46bc", "1e:8120", 0x13E0, 0x5113E0, 0x0E93,
            0x9FE5, 0x9F85, 0x7F, 0, 0xEDE, 0xEFC, 0, 0xA2, 0xF16,
            (0, 0x4A34, 0x51, 0x1600, 0, 0x200), "2d:1234",
            (0, 0, 0, 0, 0, 0),
            (0x0000, 0x9FE5, 0x9F85),
        )
        armed, incident = monitor.first_divergent_after_expected([good, bad])
        self.assertTrue(armed)
        self.assertEqual(incident, bad)

    def test_returns_only_new_tail(self) -> None:
        empty = monitor.ResourceCandidate(
            "00:0000", "00:0000", 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, (), "00:0000", (), (),
        )
        lost, candidates = monitor.new_candidates(2, 4, [empty] * 4)
        self.assertEqual(lost, 0)
        self.assertEqual(len(candidates), 2)


if __name__ == "__main__":
    unittest.main()
