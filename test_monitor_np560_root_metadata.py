#!/usr/bin/env python3

import unittest

import monitor_np560_root_metadata as monitor


class RootMetadataMonitorTests(unittest.TestCase):
    def test_parses_trace_and_selects_new_tail(self) -> None:
        registers = (
            "PC=20:0000\n"
            "ROOT_METADATA=PTR:0051:2878 WRITES:3 TRACE:"
            "2d:1234/512888/0000>0004/16/sp0f00/fp0f20;"
            "2d:1240/51288a/0000>0008/16/sp0efe/fp0f20;"
            "30:5678/512888/0004>0000/16/sp0ee0/fp0ef0"
        )

        pointer, count, ring = monitor.parse_root_writes(registers)
        lost, new = monitor.new_writes(2, count, ring)

        self.assertEqual(pointer, "0051:2878")
        self.assertEqual(count, 3)
        self.assertEqual(lost, 0)
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0].pc, "30:5678")
        self.assertEqual(new[0].address, 0x512888)
        self.assertEqual((new[0].old, new[0].new), (4, 0))


if __name__ == "__main__":
    unittest.main()
