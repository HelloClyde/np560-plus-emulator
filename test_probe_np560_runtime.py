#!/usr/bin/env python3

import base64
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_np560_runtime as probe


class RuntimeProbeTests(unittest.TestCase):
    def test_compacts_current_boot_signals(self) -> None:
        registers = """\
PC=31:8afa  PSW=Z---
APPLICATION_STATE=STATE:0001 RESOURCE_FLAG:0001 PENDING:0000 STAGE:0001
APPLICATION_TRACE=MODALPOLL:12@31:f2d8/x,RESOURCE:1@32:512c/x
APPLICATION_INIT=CALLS:1
PROVISION=CALLS:1 STAGE:8
FILE_OPEN=CALLS:6813 ERROR:fff6
FILE_WRITE=CALLS:256 ACTIVE:0
FILE_COMMIT=CALLS:1 ACTIVE:0
STORAGE_DRIVER=CALLS:2 FROM:1f:2358 ARG:0020
FILE_ROOT_POOL=CALLS:1 RETURNS:1
FILE_ROOT_RELEASE=CALLS:2 TRACE=
FILE_SIZE_RECORD=BASE:5126ac ATTR:10 LENGTH:0001:0000
FILE_RECORD_RESOLVE=CALLS:1 RESULT:0001
RESOURCE_OPEN=CALLS:1
INDIRECT_CALLBACK=CALLS:112 TRACE=
MENU_OVERLAY_COPY=READS:0 ENTRY:0
NATIVE_LCD_FLUSH=CALLS:218 NONZERO_CALLS:217
NATIVE_FB=NONZERO:92 PEAK:699
TEXT_TRACE=27:81b6@80,0/x,29:148e@60,20/x,29:167a@3,100/x
USERINFO_FLOW=EVENTS:9 DEPTH:1 STATE:2/2/24:ec7a>5d:6d9e/CODE:2e00.58f0.58f1.58f3
IRQ_SAVE_FP_OVERWRITE=none
INVALID_CONTROL=none
UNSUPPORTED=none COUNT=0
NAND=READS=10 PROGRAMS:320 ERASES:15024
"""
        state = {
            "running": True,
            "registers": registers,
            "frame": base64.b64encode(bytes(240 * 120)).decode("ascii"),
        }
        result = probe.compact_observation(state)
        self.assertEqual(result["pc"], "31:8afa  PSW=Z---")
        self.assertEqual(result["provision_stage"], 8)
        self.assertEqual(result["callbacks"], 112)
        self.assertEqual(result["file_opens"], 6813)
        self.assertEqual(result["file_writes"], 256)
        self.assertEqual(result["file_commits"], 1)
        self.assertEqual(result["storage_driver_calls"], 2)
        self.assertEqual(result["file_root_allocs"], 1)
        self.assertEqual(result["file_root_releases"], 2)
        self.assertEqual(result["nand_programs"], 320)
        self.assertEqual(result["modal_polls"], 12)
        self.assertEqual(result["resource_calls"], 1)
        self.assertEqual(result["lcd_nonzero"], 92)
        self.assertEqual(result["text_y"], (0, 20, 100))
        self.assertEqual(result["userinfo_events"], 9)
        self.assertEqual(result["userinfo_state_calls"], 2)
        self.assertEqual(result["userinfo_state_returns"], 2)
        self.assertEqual(result["userinfo_state_code"], "2e00.58f0.58f1.58f3")
        self.assertEqual(result["incidents"], [])

    def test_flags_blank_userinfo_state_copy_overlay(self) -> None:
        lines = {name: "none" for name in probe.IMPORTANT_LINES}
        lines["USERINFO_FLOW"] = (
            "EVENTS:3 STATE:2/0/24:ec7a>5d:6d9e/"
            "CODE:ffff.ffff.ffff.ffff"
        )
        self.assertEqual(probe.is_incident(lines), [
            "USERINFO state-copy overlay is blank at runtime "
            "(2/0 calls/returns)"
        ])

    def test_flags_zero_length_main_resource_before_menu(self) -> None:
        lines = {name: "none" for name in probe.IMPORTANT_LINES}
        lines["APPLICATION_STATE"] = (
            "STATE:0001 RESOURCE_FLAG:0001 PENDING:0000 STAGE:0001"
        )
        lines["FILE_SIZE_RECORD"] = (
            "BASE:5126ac ATTR:10 LENGTH:0000:0000"
        )
        lines["MENU_OVERLAY_COPY"] = "READS:0 ENTRY:0"
        incidents = probe.is_incident(lines)
        self.assertEqual(incidents, [
            "main resource resolved to zero length before the menu entry"
        ])

    def test_does_not_reuse_stale_zero_length_after_foreground_started(self) -> None:
        lines = {name: "none" for name in probe.IMPORTANT_LINES}
        lines["APPLICATION_STATE"] = (
            "STATE:0001 RESOURCE_FLAG:0001 PENDING:0000 STAGE:0001"
        )
        lines["APPLICATION_TRACE"] = "FGLOOP:12@5f:17ca/x"
        lines["FILE_SIZE_RECORD"] = "BASE:5126ac LENGTH:0000:0000"
        lines["MENU_OVERLAY_COPY"] = "READS:0 ENTRY:0"
        self.assertEqual(probe.is_incident(lines), [])

    def test_flags_known_sector_copy_state_overwrite(self) -> None:
        lines = {name: "none" for name in probe.IMPORTANT_LINES}
        lines["APPLICATION_STATE_WRITE"] = (
            "COUNT:4 PC:2e:46c0 ADDR:512aaa VALUE:0001>0cac/16"
        )
        self.assertEqual(probe.is_incident(lines), [
            "application state overwritten by the sector-copy worker"
        ])

    def test_compacts_last_state_transition_and_foreground_event(self) -> None:
        registers = """\
APPLICATION_STATE_WRITE=COUNT:4 PC:20:2fb0 ADDR:512aaa VALUE:0001>00fe/16
APPLICATION_TRACE=FGLOOP:99@20:2ed6/sp0f96/r0000:0000:0000/a0000,FGDECODE:2@20:2f12/sp0f96/r008f:0001:0000/a0001,FGCHANGE:1@20:2fbe/sp0f96/r0001:0000:0000/a008f
"""
        result = probe.compact_observation({
            "running": True,
            "registers": registers,
            "frame": "",
        })
        self.assertEqual(result["state_write_pc"], "20:2fb0")
        self.assertEqual(result["state_old"], 0x0001)
        self.assertEqual(result["state_new"], 0x00FE)
        self.assertEqual(result["foreground_event"], 0x008F)

    def test_flags_irq_and_refresh_integrity_failures(self) -> None:
        lines = {name: "none" for name in probe.IMPORTANT_LINES}
        lines["IRQ64"] = "ENTRIES:9 RETURNS:8 BAD:1"
        lines["NATIVE_REFRESH"] = "CALLS:3 MISMATCHES:2"
        self.assertEqual(probe.is_incident(lines), [
            "64-Hz interrupt returned through a bad frame (1)",
            "LCD refresh front/back mismatch (2)",
        ])

    def test_flags_both_04d6_write_paths(self) -> None:
        lines = {name: "none" for name in probe.IMPORTANT_LINES}
        lines["IRQ_SAVE_FP_OVERWRITE"] = (
            "COUNT:2 BUS:1 TRACE=data-bus;internal-sram"
        )
        incidents = probe.is_incident(lines)
        self.assertEqual(len(incidents), 1)
        self.assertIn("0x04D6", incidents[0])

    def test_flags_pre_resource_modal_wait(self) -> None:
        lines = {name: "none" for name in probe.IMPORTANT_LINES}
        lines["APPLICATION_TRACE"] = (
            "MODALPOLL:1200@31:f2d8/sp0d9c/x,"
            "MODALEVT:2@31:f282/x,CLEANUP:1@31:f304/x,"
            "MODALHEAD:1199@31:f2ae/x"
        )
        incidents = probe.is_incident(lines)
        self.assertEqual(incidents, [
            "pre-resource modal loop is blocking the main resource entry "
            "(1200 polls)"
        ])

    def test_completed_modal_is_not_reported_as_current_blocker(self) -> None:
        lines = {name: "none" for name in probe.IMPORTANT_LINES}
        lines["APPLICATION_TRACE"] = (
            "MODALPOLL:1200@31:f2d8/x,MODALEVT:1@31:f282/x,"
            "CLEANUP:1@31:f304/x"
        )
        self.assertEqual(probe.is_incident(lines), [])

    def test_incident_changes_deduplicates_and_reports_resolution(self) -> None:
        added, resolved = probe.incident_changes(
            {"old incident", "persistent"},
            ["persistent", "new incident"],
        )
        self.assertEqual(added, ["new incident"])
        self.assertEqual(resolved, ["old incident"])

    def test_incident_counter_growth_is_not_a_new_fault(self) -> None:
        added, resolved = probe.incident_changes(
            {"unsupported instruction: 2e:2e96 WORD=a6a7 COUNT=10"},
            ["unsupported instruction: 2e:2e96 WORD=a6a7 COUNT=999"],
        )
        self.assertEqual(added, [])
        self.assertEqual(resolved, [])

    def test_observation_signature_ignores_timestamp(self) -> None:
        first = {"time": "one", "pc": "31:1234", "incidents": []}
        second = {"time": "two", "pc": "31:1234", "incidents": []}
        self.assertEqual(
            probe.observation_signature(first),
            probe.observation_signature(second),
        )


if __name__ == "__main__":
    unittest.main()
