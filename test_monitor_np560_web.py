#!/usr/bin/env python3
"""Tests for the compact NP560 Web diagnostic monitor."""

from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from monitor_np560_web import (
    BlankAfterVisibleWatch, StackDescentWatch, change_signature, observe,
    should_stop,
)


def state(registers: str, *, running: bool = True,
          frame: bytes | None = None) -> dict:
    if frame is None:
        frame = bytes(240 * 120)
    return {
        "running": running,
        "status": "running" if running else "paused",
        "format": "gray5",
        "width": 240,
        "height": 120,
        "frame": base64.b64encode(frame).decode("ascii"),
        "registers": registers,
    }


class MonitorTests(unittest.TestCase):
    def test_clean_factory_chain_keeps_monitor_running(self) -> None:
        observation = observe(state(
            "PC=32:7466\n"
            "IRQ64=ENABLED:1 ENTRIES:12 RETURNS:11\n"
            "IRQ_SAVE_FP=SAVES:12 RESTORES:11 EXPECT:ffff SLOT:ffff\n"
            "IRQ_SAVE_FP_OVERWRITE=none\n"
            "UNSUPPORTED=none COUNT=0\n"
            "ROM_MISSING=none FETCHES=0\n"
            "INVALID_CONTROL=none\n"
            "APPLICATION_TRACE=BOOT33:1@20:0004/sp1000/x,"
            "SYSMAIN:1@03:0030/sp0ff0/x"
        ))
        self.assertEqual(observation.stage, "SYSMAIN")
        self.assertFalse(observation.incidents)
        self.assertIsNone(should_stop("either", observation))
        self.assertEqual(observation.sysmain_calls, 1)

    def test_fp_overwrite_is_an_incident(self) -> None:
        observation = observe(state(
            "PC=08:41f0\n"
            "IRQ64=ENABLED:1 ENTRIES:13 RETURNS:12\n"
            "IRQ_SAVE_FP=SAVES:13 RESTORES:12 EXPECT:ffff SLOT:0001\n"
            "IRQ_SAVE_FP_OVERWRITE=COUNT:1 ENTRY:13 "
            "WRITE:33:6c40 NEXT:33:6c44 ffff>0001 "
            "L:04d6 P:0004d6/16 BUS:1 DS:000,000 SP:0f6c FP:06da\n"
            "UNSUPPORTED=none COUNT=0\n"
            "ROM_MISSING=none FETCHES=0\n"
            "INVALID_CONTROL=none\n"
        ))
        self.assertEqual(observation.irq_fp_overwrites, 1)
        self.assertTrue(any("overwritten" in item for item in observation.incidents))
        self.assertTrue(any("translated data bus" in item
                            for item in observation.incidents))
        self.assertIn("WRITE:33:6c40", observation.irq_fp_overwrite_detail)
        self.assertEqual(should_stop("either", observation), "incident")

    def test_internal_sram_overwrite_path_is_named(self) -> None:
        observation = observe(state(
            "PC=33:6c44\n"
            "IRQ_SAVE_FP=SAVES:13 RESTORES:12 EXPECT:ffff SLOT:0001\n"
            "IRQ_SAVE_FP_OVERWRITE=COUNT:1 ENTRY:13 "
            "WRITE:33:6c40 NEXT:33:6c44 ffff>0001 "
            "L:04d6 P:0004d6/16 BUS:2 DS:000,000 SP:0f6c FP:06da\n"
            "UNSUPPORTED=none\nROM_MISSING=none\nINVALID_CONTROL=none\n"
        ))
        self.assertTrue(any("internal SRAM path" in item
                            for item in observation.incidents))

    def test_odd_unsupported_pc_is_not_treated_as_an_opcode_gap(self) -> None:
        observation = observe(state(
            "PC=10:50bd\n"
            "IRQ64=ENABLED:1 ENTRIES:13 RETURNS:13\n"
            "IRQ_SAVE_FP=SAVES:13 RESTORES:13 EXPECT:ffff SLOT:0001\n"
            "IRQ_SAVE_FP_OVERWRITE=none\n"
            "UNSUPPORTED=10:50bd WORD=c470 COUNT=1\n"
            "ROM_MISSING=none FETCHES=0\n"
            "INVALID_CONTROL=none\n"
        ))
        self.assertTrue(any("odd instruction address" in item
                            for item in observation.incidents))
        self.assertTrue(any("unsupported stop" in item
                            for item in observation.incidents))
        self.assertEqual(should_stop("return", observation), "incident")
        self.assertEqual(should_stop("menu", observation), "incident")
        self.assertIsNone(should_stop("never", observation))

    def test_zero_filled_writable_data_execution_is_an_incident(self) -> None:
        trace = ",".join(
            f"51:{0x0f20 + index * 2:04x}/0000"
            for index in range(16)
        )
        observation = observe(state(
            "PC=51:0f40\n"
            "IRQ_SAVE_FP_OVERWRITE=none\nUNSUPPORTED=none\n"
            "ROM_MISSING=none\nINVALID_CONTROL=none\n"
            f"EXEC_TRACE={trace}\n"
        ))
        self.assertTrue(any("writable data RAM" in item
                            for item in observation.incidents))
        self.assertEqual(should_stop("incident", observation), "incident")

    def test_menu_milestone_can_stop_without_incident(self) -> None:
        observation = observe(state(
            "PC=30:1000\n"
            "IRQ64=ENABLED:1 ENTRIES:20 RETURNS:20\n"
            "IRQ_SAVE_FP=SAVES:20 RESTORES:20 EXPECT:ffff SLOT:ffff\n"
            "IRQ_SAVE_FP_OVERWRITE=none\n"
            "UNSUPPORTED=none COUNT=0\n"
            "ROM_MISSING=none FETCHES=0\n"
            "INVALID_CONTROL=none\n"
            "APPLICATION_TRACE=MENU:1@33:1234/x,MENUOK:1@30:2000/x"
        ))
        self.assertTrue(observation.menu_reached)
        self.assertEqual(should_stop("either", observation), "menu")

    def test_cafe_metadata_can_be_captured_explicitly(self) -> None:
        observation = observe(state(
            "PC=02:bd24\n"
            "IRQ_SAVE_FP_OVERWRITE=none\nUNSUPPORTED=none\n"
            "ROM_MISSING=none\nINVALID_CONTROL=none\n"
            "NAND_CAFE_RECORD=READS:1 "
            "FIRST:02:bd24<1c:2f4a<00:0000/p0000003f+c0+o0/n520>"
            "b511000/f0000/feca930e5801424b\n"
        ))
        self.assertEqual(observation.cafe_record_reads, 1)
        self.assertIn("p0000003f", observation.cafe_record_detail)
        self.assertEqual(should_stop("cafe", observation), "cafe")
        self.assertIsNone(should_stop("either", observation))

    def test_foreground_return_can_be_captured_explicitly(self) -> None:
        observation = observe(state(
            "PC=03:0084\n"
            "IRQ_SAVE_FP_OVERWRITE=none\nUNSUPPORTED=none\n"
            "ROM_MISSING=none\nINVALID_CONTROL=none\n"
            "APPLICATION_TRACE=MAINRET:1@06:4608/sp0fea/x,"
            "SCHEDRET:1@25:5c4c/sp0ffc/x\n"
        ))
        self.assertEqual(observation.main_returns, 1)
        self.assertEqual(should_stop("return", observation),
                         "foreground-return")
        self.assertIsNone(should_stop("either", observation))

    def test_zero_resource_window_before_first_io_is_an_incident(self) -> None:
        observation = observe(state(
            "PC=31:a944\n"
            "IRQ_SAVE_FP_OVERWRITE=none\nUNSUPPORTED=none\n"
            "ROM_MISSING=none\nINVALID_CONTROL=none\n"
            "RESOURCE_WINDOW=VALUE:0200 WRITES:1 "
            "FIRST:25:ccb8/0000>0200/16 "
            "LAST:25:ccb8/0000>0200/16 ZERO_IO:1 "
            "FIRST_ZERO:31:a940>25:206e/"
            "a0000,0fd4,0010,d012,0001,49f0/base0e93/sh0008\n"
        ))
        self.assertEqual(observation.resource_window_value, 0x0200)
        self.assertEqual(observation.resource_window_writes, 1)
        self.assertEqual(observation.resource_window_zero_io_calls, 1)
        self.assertTrue(any("A2:28E0" in item
                            for item in observation.incidents))
        self.assertEqual(should_stop("incident", observation), "incident")

    def test_resource_window_initialized_before_io_is_clean(self) -> None:
        observation = observe(state(
            "PC=2d:276a\n"
            "IRQ_SAVE_FP_OVERWRITE=none\nUNSUPPORTED=none\n"
            "ROM_MISSING=none\nINVALID_CONTROL=none\n"
            "RESOURCE_WINDOW=VALUE:0200 WRITES:1 "
            "FIRST:03:0100/0000>0200/16 "
            "LAST:03:0100/0000>0200/16 ZERO_IO:0\n"
        ))
        self.assertEqual(observation.resource_window_value, 0x0200)
        self.assertEqual(observation.resource_window_zero_io_calls, 0)
        self.assertFalse(observation.incidents)

    def test_application_and_resource_path_state_are_separate_from_incidents(self) -> None:
        observation = observe(state(
            "PC=22:5650\n"
            "IRQ_SAVE_FP_OVERWRITE=none\nUNSUPPORTED=none\n"
            "ROM_MISSING=none\nINVALID_CONTROL=none\n"
            "APPLICATION_STATE=STATE:00fe RESOURCE_FLAG:0001 "
            "PENDING:0000 STAGE:0001\n"
        ))
        self.assertEqual(observation.application_state, 0x00FE)
        self.assertEqual(observation.application_pending, 0)
        self.assertEqual(observation.application_stage, 1)
        self.assertEqual(observation.resource_path_flag, 1)
        self.assertEqual(observation.resource_path_detail,
                         "resource path unavailable")
        self.assertFalse(observation.incidents)
        self.assertEqual(
            should_stop("resource-failure", observation), "resource-failure"
        )
        self.assertIsNone(should_stop("either", observation))

    def test_fast_counters_and_frames_do_not_spam_change_events(self) -> None:
        observation = observe(state(
            "PC=22:5650\n"
            "IRQ_SAVE_FP_OVERWRITE=none\nUNSUPPORTED=none\n"
            "ROM_MISSING=none\nINVALID_CONTROL=none\n"
            "APPLICATION_STATE=STATE:0001 RESOURCE_FLAG:0001 "
            "PENDING:0000 STAGE:0001\n"
            "APPLICATION_TRACE=FGPARENT:7@22:5602/sp0fd4/x,"
            "HANDLE:35@18:cfc2/sp0cd4/x\n"
        ))
        advanced = replace(
            observation,
            irq_entries=observation.irq_entries + 100,
            foreground_cycles=observation.foreground_cycles + 20,
            result_handle_calls=observation.result_handle_calls + 100,
            frame_sha256="f" * 64,
            frame_nonuniform_pixels=123,
        )
        self.assertEqual(change_signature(observation), change_signature(advanced))

    def test_lifecycle_counters_are_extracted_for_fast_comparison(self) -> None:
        observation = observe(state(
            "PC=31:f2be\n"
            "IRQ_SAVE_FP_OVERWRITE=none\nUNSUPPORTED=none\n"
            "ROM_MISSING=none\nINVALID_CONTROL=none\n"
            "APPLICATION_TRACE=FGPARENT:7@22:5602/sp0fd4/x,"
            "OP0BRET:7@31:4a30/sp0e3c/x,"
            "HANDLE:35@18:cfc2/sp0cd4/x,"
            "HANDLEPTR:28@31:49fa/sp0e2e/x,"
            "MODALPOLL:700@29:4094/sp0ca2/x,"
            "MENU:1@2c:c9e8/sp0f00/x,MENUOK:0@2c:cb5a/sp0f00/x\n"
            "ROOT_OBJECT_FAIL=COUNT:0 FROM:00:0000\n"
        ))
        self.assertEqual(observation.foreground_cycles, 7)
        self.assertEqual(observation.operation_setup_returns, 7)
        self.assertEqual(observation.result_handle_calls, 35)
        self.assertEqual(observation.result_handle_ptr_calls, 28)
        self.assertEqual(observation.modal_polls, 700)
        self.assertEqual(observation.menu_calls, 1)
        self.assertEqual(observation.menu_ok_calls, 0)
        self.assertEqual(observation.root_object_failures, 0)

    def test_stack_descent_watch_stops_before_frame_corruption(self) -> None:
        watch = StackDescentWatch(required_cycles=2, min_bytes_per_cycle=16)
        observations = [
            observe(state(
                "PC=03:026a\n"
                "IRQ_SAVE_FP_OVERWRITE=none\nUNSUPPORTED=none\n"
                "ROM_MISSING=none\nINVALID_CONTROL=none\n"
                f"APPLICATION_TRACE=SYSMAIN:{calls}@05:75a6/sp{sp:04x}/r0000:0000:0000/a0000,0000,0000,0000"
            ))
            for calls, sp in ((1, 0x1000), (2, 0x0fb6), (3, 0x0f6c))
        ]
        self.assertIsNone(watch.update(observations[0]))
        self.assertIsNone(watch.update(observations[0]))
        self.assertIsNone(watch.update(observations[1]))
        self.assertIsNone(watch.update(observations[1]))
        incident = watch.update(observations[2])
        self.assertIsNotNone(incident)
        self.assertIn("about 0x4a/cycle", incident)

    def test_stack_descent_watch_accepts_stable_scheduler_stack(self) -> None:
        watch = StackDescentWatch(required_cycles=2, min_bytes_per_cycle=16)
        for calls, sp in ((1, 0x1000), (2, 0x1000), (3, 0x0ffe), (4, 0x1000)):
            observation = observe(state(
                "PC=03:026a\n"
                "IRQ_SAVE_FP_OVERWRITE=none\nUNSUPPORTED=none\n"
                "ROM_MISSING=none\nINVALID_CONTROL=none\n"
                f"APPLICATION_TRACE=SYSMAIN:{calls}@03:0084/sp{sp:04x}/r0000:0000:0000/a0000,0000,0000,0000"
            ))
            self.assertIsNone(watch.update(observation))

    def test_blank_after_visible_watch_ignores_boot_and_short_transition(self) -> None:
        watch = BlankAfterVisibleWatch(
            required_seconds=2.0, min_visible_pixels=16,
        )
        clean_registers = (
            "PC=33:3008\nIRQ_SAVE_FP_OVERWRITE=none\n"
            "UNSUPPORTED=none\nROM_MISSING=none\nINVALID_CONTROL=none\n"
        )
        blank = observe(state(clean_registers))
        visible_frame = bytearray(240 * 120)
        visible_frame[:32] = bytes([31]) * 32
        visible = observe(state(clean_registers, frame=bytes(visible_frame)))

        self.assertEqual(blank.frame_nonuniform_pixels, 0)
        self.assertEqual(visible.frame_nonuniform_pixels, 32)
        self.assertIsNone(watch.update(blank, 0.0))
        self.assertIsNone(watch.update(visible, 1.0))
        self.assertIsNone(watch.update(blank, 2.0))
        self.assertIsNone(watch.update(blank, 3.9))
        incident = watch.update(blank, 4.1)
        self.assertIsNotNone(incident)
        self.assertIn("LCD became uniform", incident)

    def test_blank_watch_arms_from_native_flush_history(self) -> None:
        watch = BlankAfterVisibleWatch(
            required_seconds=2.0, min_visible_pixels=16,
        )
        registers = (
            "PC=33:3008\nIRQ_SAVE_FP_OVERWRITE=none\n"
            "UNSUPPORTED=none\nROM_MISSING=none\nINVALID_CONTROL=none\n"
            "NATIVE_LCD_FLUSH=CALLS:43 NONZERO:0 NONZERO_CALLS:32\n"
        )
        blank = observe(state(registers))

        self.assertEqual(blank.frame_nonuniform_pixels, 0)
        self.assertEqual(blank.lcd_nonzero_flushes, 32)
        self.assertIsNone(watch.update(blank, 10.0))
        incident = watch.update(blank, 12.1)
        self.assertIsNotNone(incident)
        self.assertIn("LCD became uniform", incident)


if __name__ == "__main__":
    unittest.main()
