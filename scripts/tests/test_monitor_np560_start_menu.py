#!/usr/bin/env python3
"""Tests for the NP560+ Start-key lifecycle monitor parsers."""

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
from monitor_np560_start_menu import (  # noqa: E402
    application_calls,
    diagnostic_failure,
    is_start_popup_frame,
    menu_panel_right_edge,
    named_count,
    parse_foreground_mode,
    parse_foreground_return,
    parse_indirect_callbacks,
    parse_matrix_event,
    parse_state_import,
    parse_state_import_history,
    root_frame_complete,
    static_frame_digest,
    static_pixel_difference,
    state_line,
    start_event_imported_after,
)


REGISTERS = """PC=32:13b8
APPLICATION_TRACE=ROOTCTRL:1@28:8480/sp0f78/x,ROOTRENDER:2@1d:f766/sp0f58/x
FOREGROUND_MODE=COUNT:1 FROM:1a:e036 TARGET:1a:e6b6 WORD:c600 MODE:0003 EVENT:00b0 SP:0c2a>0c2c FP:0cb0
FOREGROUND_RETURN=COUNT:1 FROM:1a:e7bc TARGET:32:13b8 WORD:c620 RESULT:0005 SP:0cb2>0cb6 FP:0cb0
FOREGROUND_CONTEXT_RETURN=COUNT:1 FROM:18:da2c TARGET:1b:2602 WORD:c620 RESULT:0000 SELECTOR:0000 STATE:00ff RESOURCE:0000 PENDING:0001 STAGE:0001 SP:0e3e>0e42 FP:0e42
FOREGROUND_OWNER_RETURN=COUNT:1 FROM:1b:2c90 TARGET:33:3e9c WORD:c620 RESULT:0000 SELECTOR:0000 STATE:00ff RESOURCE:0000 PENDING:0001 STAGE:0001 SP:0fa2>0fa6 FP:0fa6
RESOURCE_COUNT_WRITES=COUNT:2 TRACE=26:3aaa/0000>0001/16/sp0c00/fp0c10/r0001,0000,0001,0000/chainfp0c10>2e:dbae/a0051,1000,0000,0000,0000,0000;26:3aaa/0001>0002/16/sp0bf0/fp0c00/r0002,0000,0001,0000/chainfp0c00>2e:dbae/a0051,1200,0000,0000,0000,0000
INDIRECT_CALLBACK=CALLS:2 TRACE=2e:dc9c>2c:a03a/sp0f9e;2e:dc9c>24:162c/sp0f8c
ROOT_EXIT_STATE=VALUE:0002 COUNT:2 TRACE:26:3aaa/0000>0001/16,26:3aaa/0001>0002/16
STATE_IMPORT=CALLS:5 NONEMPTY:5 ACTIVE:0 POINTER:0051:28b6 INPUT:0107,1449,dc02,0000,0000,0000,0000,0000 COMPARES:3 MATCHES:1 MISMATCHES:2 LAST:0107,0107@0002 RESULT:0027:571a RETURN:28:83e6 GLOBALS:0002,0000,0000,0000,0000,0000,0000,0000,0000,0000
ROM_MISSING=none FETCHES=0
INVALID_CONTROL=none
UNSUPPORTED=none COUNT=0
SELECTOR_STATE_WRITES=COUNT:4 TRACE:none MATRIX_EVENT_MAPS=7 LAST=00b0@28:f6de
"""

STATE_HISTORY = """STATE_IMPORT_HISTORY=COUNT:4 TRACE=#1/in:0003,0000,0000,0000,00bf,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,ffff/cmp:0,0,0/result:0000:0000/return:28:84d0/mode:ffff;#2/in:0106,1449,dc02,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,ffff/cmp:2,1,1/result:001d:f2ec/return:28:83e6/mode:0001;#3/in:0107,1449,dc02,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,ffff/cmp:3,1,2/result:0027:571a/return:28:83e6/mode:0001;#4/in:0003,1449,dc02,0000,00b0,0000,0000,0000,0000,0000,0000,0000,0000,0000,0700,ffff/cmp:5,1,4/result:0032:f15c/return:28:84d0/mode:ffff
"""


def desktop_frame(panel_edge: int) -> bytes:
    width, height = 240, 120
    frame = bytearray([31] * (width * height))
    for x in range(width):
        frame[x] = 1
        frame[22 * width + x] = 9
        frame[118 * width + x] = 1
        frame[119 * width + x] = 31
    for x in range(80):
        frame[10 * width + x] = 1 if x % 2 else 23
    for x in range(24, panel_edge):
        for y in range(23, 101):
            frame[y * width + x] = 9 if (x + y) % 3 else 23
    for y in range(23, 101):
        frame[y * width + panel_edge] = 11
    return bytes(frame)


class StartMenuMonitorTests(unittest.TestCase):
    def test_parses_mode_return_and_render_count(self) -> None:
        mode = parse_foreground_mode(REGISTERS)
        returned = parse_foreground_return(REGISTERS)
        self.assertEqual(application_calls(REGISTERS, "ROOTRENDER"), 2)
        self.assertEqual(named_count(REGISTERS, "FOREGROUND_MODE"), 1)
        self.assertEqual(mode["target"], "1a:e6b6")
        self.assertEqual(mode["event"], 0xB0)
        self.assertEqual(returned["target"], "32:13b8")
        self.assertEqual(returned["result"], 5)
        callbacks = parse_indirect_callbacks(REGISTERS)
        self.assertEqual(callbacks["count"], 2)
        self.assertEqual(callbacks["targets"], ("2c:a03a", "24:162c"))
        imported = parse_state_import(REGISTERS)
        self.assertEqual(imported["nonempty"], 5)
        self.assertEqual(imported["input"].split(",")[:3], [
            "0107", "1449", "dc02",
        ])
        self.assertEqual(imported["matches"], 1)
        self.assertEqual(imported["result"], "0027:571a")
        self.assertEqual(imported["return"], "28:83e6")

    def test_extracts_state_line_and_accepts_clean_diagnostics(self) -> None:
        self.assertIn("VALUE:0002", state_line(REGISTERS, "ROOT_EXIT_STATE"))
        self.assertIn(
            "26:3aaa/0001>0002",
            state_line(REGISTERS, "RESOURCE_COUNT_WRITES"),
        )
        self.assertIn(
            "RESULT:0000",
            state_line(REGISTERS, "FOREGROUND_CONTEXT_RETURN"),
        )
        self.assertIsNone(diagnostic_failure(REGISTERS))
        self.assertEqual(parse_matrix_event(REGISTERS), (7, 0x00B0))
        self.assertEqual(parse_matrix_event("MATRIX_EVENT_MAPS=0 LAST=0000"),
                         (0, 0))

    def test_reports_first_incident(self) -> None:
        broken = REGISTERS.replace(
            "ROM_MISSING=none FETCHES=0", "ROM_MISSING=16:0030"
        )
        self.assertEqual(diagnostic_failure(broken), "ROM_MISSING=16:0030")

    def test_completed_desktop_and_start_popup_geometry(self) -> None:
        start = desktop_frame(36)
        root = desktop_frame(61)
        self.assertTrue(root_frame_complete(start, 240, 120))
        self.assertTrue(root_frame_complete(root, 240, 120))
        self.assertEqual(menu_panel_right_edge(start, 240, 120), 36)
        self.assertEqual(menu_panel_right_edge(root, 240, 120), 61)
        self.assertTrue(is_start_popup_frame(start, 240, 120))
        self.assertFalse(is_start_popup_frame(root, 240, 120))

    def test_clock_region_is_excluded_from_static_frame_comparison(self) -> None:
        before = bytearray(desktop_frame(61))
        clock_only = bytearray(before)
        clock_only[110 * 240 + 220] ^= 1
        self.assertEqual(
            static_frame_digest(before, 240, 120),
            static_frame_digest(clock_only, 240, 120),
        )
        self.assertEqual(
            static_pixel_difference(before, clock_only, 240, 120), 0,
        )
        outside = bytearray(before)
        outside[80 * 240 + 100] ^= 1
        self.assertEqual(
            static_pixel_difference(before, outside, 240, 120), 1,
        )

    def test_start_record_is_distinguished_from_concurrent_0107(self) -> None:
        history = parse_state_import_history(STATE_HISTORY)
        self.assertEqual(history["count"], 4)
        self.assertEqual(len(history["entries"]), 4)
        self.assertEqual(history["entries"][2]["result"], "0027:571a")
        self.assertTrue(start_event_imported_after(STATE_HISTORY, 2))
        self.assertFalse(start_event_imported_after(STATE_HISTORY, 4))


if __name__ == "__main__":
    unittest.main()
