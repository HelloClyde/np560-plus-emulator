#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).with_name("monitor_np560_storage_geometry.py")
SPEC = importlib.util.spec_from_file_location("monitor_np560_storage_geometry", MODULE_PATH)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = monitor
SPEC.loader.exec_module(monitor)


class StorageGeometryMonitorTests(unittest.TestCase):
    def test_parses_geometry_and_write_ring(self) -> None:
        registers = """\
STORAGE_GEOMETRY=SHIFT:0008 MODE:0010 BUFFER:0051:1000 BUFFER_STEP:0000 PAGE_DATA:0800 FTL_BLOCK:0e93 RANGE:0e93..0fea MAP_SLOT_9B:0c02 MAP_SLOT_C9:0c9a
STORAGE_GEOMETRY_WRITES=COUNT:2 TRACE=20:0100/004b66/0000>0800/16;1e:7f52/004b66/0800>cc51/16
"""
        values = monitor.parse_geometry(registers)
        self.assertEqual(values["BUFFER_HI"], 0x51)
        self.assertEqual(values["PAGE_DATA"], 0x800)
        self.assertEqual(values["MAP_SLOT_9B"], 0xC02)
        count, writes = monitor.parse_writes(registers)
        self.assertEqual(count, 2)
        self.assertEqual(writes[-1].pc, "1e:7f52")
        self.assertEqual(writes[-1].new, 0xCC51)

    def test_returns_only_new_tail(self) -> None:
        ring = [
            monitor.GeometryWrite("00:0000", index, index, index + 1, 16)
            for index in range(4)
        ]
        lost, writes = monitor.new_writes(2, 4, ring)
        self.assertEqual(lost, 0)
        self.assertEqual([write.address for write in writes], [2, 3])


if __name__ == "__main__":
    unittest.main()
