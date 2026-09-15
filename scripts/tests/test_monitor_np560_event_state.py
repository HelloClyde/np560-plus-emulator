#!/usr/bin/env python3
"""Tests for the NP560 initialization/event-state delta monitor."""

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent))
from monitor_np560_event_state import (  # noqa: E402
    application_counts,
    new_writes,
    parse_usb_values,
    parse_usb_writes,
    parse_values,
    parse_writes,
    usb_milestone_counts,
)


REGISTERS = """PC=31:f2d8
EVENT_STATE=0494:0000 2A4E:0004 2AAC:1234 TICK:1245
EVENT_STATE_WRITES=COUNT:2 TRACE=29:3e10/512a4e/0000>0004/16;31:f000/512aac/0000>1234/16
USB_BOOT_STATE=SFRB0:2000 BIT13:1 4B28:0001 2A48:0000 2A4A:0001 2A56:0015 2ABC:0000 MILESTONES:DETECT:4,INIT:1,SVCCLEAR:0,SVCSET:0,TRIGGER:1
USB_BOOT_WRITES=COUNT:2 TRACE=22:9b1c/512a48/0000>0001/16;2b:954e/512a48/0001>0000/16
APPLICATION_TRACE=MODALPOLL:19@31:f2d8/sp0d9c/x,MODALDONE:1@31:f2fe/sp0d9c/x
"""


class EventStateMonitorTests(unittest.TestCase):
    def test_parses_values_writers_and_milestones(self) -> None:
        self.assertEqual(parse_values(REGISTERS)["2A4E"], 4)
        count, writes = parse_writes(REGISTERS)
        self.assertEqual(count, 2)
        self.assertEqual(writes[0].pc, "29:3e10")
        self.assertEqual(writes[1].address, 0x512AAC)
        self.assertEqual(application_counts(REGISTERS)["MODALDONE"], 1)

    def test_parses_usb_boot_values_writers_and_milestones(self) -> None:
        values = parse_usb_values(REGISTERS)
        self.assertEqual(values["SFRB0"], 0x2000)
        self.assertEqual(values["BIT13"], 1)
        count, writes = parse_usb_writes(REGISTERS)
        self.assertEqual(count, 2)
        self.assertEqual(writes[-1].pc, "2b:954e")
        self.assertEqual(usb_milestone_counts(REGISTERS)["TRIGGER"], 1)

    def test_returns_only_unseen_ring_tail(self) -> None:
        _, writes = parse_writes(REGISTERS)
        lost, unseen = new_writes(1, 2, writes)
        self.assertEqual(lost, 0)
        self.assertEqual(unseen, writes[-1:])

    def test_reports_records_lost_before_ring(self) -> None:
        _, writes = parse_writes(REGISTERS)
        lost, unseen = new_writes(0, 10, writes)
        self.assertEqual(lost, 8)
        self.assertEqual(unseen, writes)


if __name__ == "__main__":
    unittest.main()
