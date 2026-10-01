from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import base64
import json
import itertools
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import probe_np560_matrix_route as route_module

from scripts.probe_np560_matrix_route import (
    ACTIVE_MATRIX_EVENTS,
    CANDIDATE_ONLY_EVENTS,
    WebBridge,
    capture_frame,
    capture_state,
    diagnostic_failure,
    held_counter_summary,
    key_counter_signature,
    key_counter_timeline_point,
    key_delivery_state,
    key_status_rearm_state,
    matrix_rearm_state,
    matrix_masks,
    parse_step,
    safe_label,
    selector_candidate_state,
    stable_frame_signature,
    wait_for_delivery_and_matrix_rearm,
    wait_for_stable_frame,
)


class MatrixRouteProbeTests(unittest.TestCase):
    def test_contact_bounds_are_optional_and_do_not_invent_missing_clock(self):
        for times, expected in (([100, 120, 210, 230], (90, 130)),
                                ([100, 120, 110, 230], None),
                                ([None] * 4, None)):
            class FakeWeb:
                def __init__(self): self.inputs = []; self.calls = 0
                def set_matrix(self, index): self.inputs.append(index)
                def get_json(self, path):
                    stamp = times[min(self.calls, 3)]
                    self.calls += 1
                    state = dict(matrix_reads=self.calls, candidates=0, maps=0)
                    if stamp is not None: state['virtual_time_ns'] = stamp
                    return state
            web = FakeWeb()
            ticks = itertools.count(0, .001)
            with patch.object(route_module.time, 'monotonic', side_effect=lambda: next(ticks)), \
                    patch.object(route_module.time, 'sleep'), \
                    self.assertRaises(route_module.KeyObservationTimeout) as caught:
                route_module.replay_step(web, parse_step('up:61:0x82'),
                    press_timeout=.03, release_timeout=.01, poll_interval=.001,
                    settle=0, pulse_duration=.01, observe_contact_bounds=True)
            bounds = caught.exception.input_evidence['contact_bounds']
            self.assertEqual(web.inputs, [61, None])
            if expected is None:
                self.assertNotIn('guest_contact_lower_ns', bounds)
            else:
                self.assertEqual((bounds['guest_contact_lower_ns'],
                                  bounds['guest_contact_upper_ns']), expected)

    def test_candidate_timeline_keeps_virtual_time_separate_from_host(self):
        point = key_counter_timeline_point(
            dict(virtual_time_ns=1000), dict(virtual_time_ns=9000), .2)
        self.assertEqual(point['elapsed_seconds'], .2)
        self.assertEqual(point['virtual_time_ns'], 9000)
        self.assertEqual(point['virtual_elapsed_ns'], 8000)

    def test_success_records_contact_not_just_post_candidate_hold(self):
        baseline = dict(matrix_reads=10, candidates=0, maps=0,
                        acknowledgements=0, modal_acknowledgements=0,
                        virtual_time_ns=1000)
        observed = dict(baseline, candidates=2, candidate=0x83, maps=2,
                        event=0x83, modal_acknowledgements=2,
                        modal_acknowledgement=0x83, virtual_time_ns=9000)
        class FakeWeb:
            def __init__(self): self.inputs = []; self.reads = 0
            def set_matrix(self, index): self.inputs.append(index)
            def get_json(self, path):
                self.reads += 1
                return baseline if self.reads == 1 else observed
        web = FakeWeb()
        delivered = dict(observed, acknowledgement=0, acknowledgement_path='modal')
        ticks = itertools.count(0, .01)
        with patch.object(route_module.time, 'monotonic', side_effect=lambda: next(ticks)), \
                patch.object(route_module, 'wait_for_delivery_and_matrix_rearm',
                             return_value=(20, delivered)):
            result = route_module.replay_step(web, parse_step('down:37:0x83'),
                press_timeout=1, release_timeout=1, poll_interval=.1, settle=0)
        self.assertEqual(web.inputs, [37, None])
        self.assertGreater(result['host_contact_request_interval_seconds'],
                           result['hold_duration_observed_seconds'])
        self.assertEqual(result['candidate_observation']['maps_delta'], 2)
        self.assertEqual(result['candidate_observation']['virtual_elapsed_ns'], 8000)
        self.assertEqual(result['matrix_make_requests'], 1)
        self.assertEqual(result['modal_acknowledgements_total'], 2)

    def test_rejected_make_is_not_misreported_as_guest_timeout(self):
        web = WebBridge("http://unused", 1)
        with patch.object(web, "post_json", return_value={"ok": True, "applied": False}):
            with self.assertRaisesRegex(RuntimeError, "rejected physical"):
                web.set_matrix(53)

    def test_timeout_keeps_observed_counters_and_releases(self):
        class FakeWeb:
            def __init__(self):
                self.calls = 0
                self.inputs = []
            def set_matrix(self, index):
                self.inputs.append(index)
            def get_json(self, path):
                self.assert_path = path
                self.calls += 1
                return {"matrix_reads": 100 + self.calls,
                        "candidates": 5, "candidate": 0x83,
                        "maps": 4, "matrix_rearmed": True}
        web = FakeWeb()
        ticks = itertools.count(0, .001)
        with patch.object(route_module.time, "monotonic", side_effect=lambda: next(ticks)), \
                patch.object(route_module.time, "sleep"), \
                self.assertRaises(route_module.KeyObservationTimeout) as caught:
            route_module.replay_step(web, parse_step("confirm:53:0x86"),
                press_timeout=.01, release_timeout=.01, poll_interval=.001,
                settle=0, pulse_duration=.001)
        evidence = caught.exception.input_evidence
        self.assertEqual(web.inputs, [53, None])
        self.assertTrue(evidence["released_before_timeout"])
        self.assertGreater(evidence["last_observation"]["matrix_reads"],
                           evidence["before"]["matrix_reads"])
        self.assertEqual(evidence["last_observation"]["candidates"], 5)
        self.assertGreaterEqual(evidence["contact_after_make_ack_upper_bound_seconds"], .001)

    def test_post_ack_rom_failure_still_records_failed_step(self) -> None:
        # Matches the native Hero failure: replay_step returns after ACK, but
        # the final full-state capture sees a newly reached ROM hole.
        registers = "ROM_MISSING=02:acd8 FETCHES=1\n"
        snapshot = {
            "registers": registers, "format": "gray5",
            "width": 240, "height": 120,
            "frame": base64.b64encode(bytes(240 * 120)).decode("ascii"),
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            argv = ["probe", "--output-dir", str(output),
                    "--skip-initial-capture", "--step", "Hero:53:0x86"]
            with patch("sys.argv", argv), \
                    patch.object(route_module, "WebBridge") as bridge, \
                    patch.object(route_module, "replay_step", return_value={}):
                bridge.return_value.get_json.return_value = snapshot
                with self.assertRaisesRegex(RuntimeError, "ROM_MISSING"):
                    route_module.main()
            report = json.loads((output / "route.json").read_text(encoding="utf-8"))
            self.assertEqual(report["steps"], [])
            self.assertEqual(report["failed_step"]["label"], "Hero")
            self.assertIn("ROM_MISSING=02:acd8", report["failed_step"]["error"])
            self.assertTrue((output / "01-Hero-failed.json").is_file())
            self.assertEqual((output / "01-Hero-failed.gray5").stat().st_size,
                             240 * 120)

    def test_key_counter_timeline_records_repeat_edges_and_event_values(self) -> None:
        before = {
            "candidates": 10, "maps": 8,
            "acknowledgements": 3, "modal_acknowledgements": 5,
            "matrix_reads": 100,
        }
        status = {
            "candidates": 12, "candidate": 0x83,
            "maps": 10, "event": 0x83,
            "acknowledgements": 3, "acknowledgement": 0x86,
            "modal_acknowledgements": 7, "modal_acknowledgement": 0x83,
            "matrix_reads": 132,
        }
        self.assertEqual(key_counter_signature(status), (12, 10, 3, 7))
        self.assertEqual(
            key_counter_timeline_point(before, status, 1.2345678),
            {
                "elapsed_seconds": 1.234568,
                "candidates": 12, "candidates_delta": 2,
                "maps": 10, "maps_delta": 2,
                "acknowledgements": 3, "acknowledgements_delta": 0,
                "modal_acknowledgements": 7,
                "modal_acknowledgements_delta": 2,
                "candidate": 0x83, "event": 0x83,
                "acknowledgement": 0x86,
                "modal_acknowledgement": 0x83,
                "matrix_reads": 132, "matrix_reads_delta": 32,
            },
        )

    def test_held_counter_summary_reports_guest_repeat_deltas(self) -> None:
        self.assertEqual(
            held_counter_summary(
                {
                    "candidates": 10, "maps": 8,
                    "acknowledgements": 3, "modal_acknowledgements": 5,
                },
                {
                    "candidates": 14, "maps": 12,
                    "acknowledgements": 3, "modal_acknowledgements": 9,
                },
            ),
            {
                "candidates_during_hold": 4,
                "maps_during_hold": 4,
                "acknowledgements_during_hold": 0,
                "modal_acknowledgements_during_hold": 4,
            },
        )

    def test_active_matrix_table_covers_all_physical_positions(self) -> None:
        self.assertEqual(len(ACTIVE_MATRIX_EVENTS), 64)
        self.assertEqual(ACTIVE_MATRIX_EVENTS[5], 0xFFFF)
        self.assertEqual(ACTIVE_MATRIX_EVENTS[26], 0x8C)
        self.assertEqual(ACTIVE_MATRIX_EVENTS[53], 0x86)
        self.assertEqual(ACTIVE_MATRIX_EVENTS[55], 0xB0)
        self.assertEqual(CANDIDATE_ONLY_EVENTS, frozenset((0x8C,)))

    def test_parse_step(self) -> None:
        step = parse_step("network-right:20:0x85")
        self.assertEqual(step.label, "network-right")
        self.assertEqual(step.matrix_index, 20)
        self.assertEqual(step.expected_event, 0x85)
        self.assertEqual(step.observation, "map")
        self.assertTrue(step.require_foreground_ack)

    def test_parse_candidate_step(self) -> None:
        step = parse_step("annunciator:26:0x8c:candidate")
        self.assertEqual(step.matrix_index, 26)
        self.assertEqual(step.expected_event, 0x8C)
        self.assertEqual(step.observation, "candidate")
        self.assertFalse(step.require_foreground_ack)

    def test_parse_step_rejects_out_of_range_index(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_step("bad:64:0x85")

    def test_matrix_masks_cover_both_halves(self) -> None:
        self.assertEqual(matrix_masks(20), (1 << 20, 0))
        self.assertEqual(matrix_masks(53), (0, 1 << 21))

    def test_one_scan_bridge_uses_dedicated_atomic_endpoint(self) -> None:
        class RecordingBridge(WebBridge):
            def __init__(self) -> None:
                self.posts = []

            def post_json(self, path, value):
                self.posts.append((path, value))
                return {"ok": True}

        web = RecordingBridge()
        web.pulse_matrix(63)
        self.assertEqual(
            web.posts, [("/api/key-pulse", {"matrix_index": 63})]
        )
        for invalid in (-1, 64):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    web.pulse_matrix(invalid)

        source = (Path(__file__).resolve().parents[1] / "probe_np560_matrix_route.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("if single_scan_pulse:\n        web.pulse_matrix", source)
        self.assertIn('"single-scan-pulse" if single_scan_pulse', source)

    def test_diagnostic_failure(self) -> None:
        self.assertIsNone(diagnostic_failure(
            "ROM_MISSING=none\nINVALID_CONTROL=none\nUNSUPPORTED=none COUNT=0"
        ))
        self.assertEqual(
            diagnostic_failure("ROM_MISSING=0c:1234\n"),
            "ROM_MISSING=0c:1234",
        )

    def test_failure_capture_preserves_full_register_snapshot(self) -> None:
        class FakeWeb:
            @staticmethod
            def get_json(path: str):
                if path != "/api/state":
                    raise AssertionError(path)
                return {
                    "running": True,
                    "registers": (
                        "PC=10:d019\n"
                        "CONTROL_TRACE=33:341e/bd32>32:f3c6\n"
                        "INVALID_CONTROL=32:f400/c620>10:d019\n"
                    ),
                }

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "INVALID_CONTROL"):
                capture_state(FakeWeb(), output, "strict")
            state = capture_state(
                FakeWeb(), output, "failed", allow_failure=True,
            )
            saved = json.loads(
                (output / "failed.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved, state)
            self.assertIn("CONTROL_TRACE=", saved["registers"])
            self.assertIn("INVALID_CONTROL=", saved["registers"])

    def test_lightweight_frame_capture_uses_frame_endpoint(self) -> None:
        raw = bytes((1, 2, 3, 4))

        class FakeWeb:
            @staticmethod
            def get_json(path: str):
                if path != "/api/frame":
                    raise AssertionError(path)
                return {
                    "format": "gray5", "width": 2, "height": 2,
                    "frame": base64.b64encode(raw).decode("ascii"),
                }

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            state = capture_frame(FakeWeb(), output, "step")
            self.assertEqual((output / "step.gray5").read_bytes(), raw)
            self.assertEqual(
                json.loads((output / "step-frame.json").read_text("utf-8")),
                state,
            )

    def test_stable_frame_signature_masks_only_live_clock_region(self) -> None:
        width, height = 240, 120
        raw = bytearray(width * height)

        def state(frame: bytes) -> dict[str, object]:
            return {
                "format": "gray5", "width": width, "height": height,
                "frame": base64.b64encode(frame).decode("ascii"),
            }

        baseline = stable_frame_signature(state(raw))
        raw[110 * width + 220] = 31
        self.assertEqual(stable_frame_signature(state(raw)), baseline)
        raw[50 * width + 100] = 31
        self.assertNotEqual(stable_frame_signature(state(raw)), baseline)

    def test_wait_for_stable_frame_requires_new_sequence_and_repeat(self) -> None:
        width, height = 4, 3

        def frame(sequence: int, value: int) -> dict[str, object]:
            raw = bytes([value]) * (width * height)
            return {
                "format": "gray5", "width": width, "height": height,
                "sequence": sequence,
                "frame": base64.b64encode(raw).decode("ascii"),
            }

        class FakeWeb:
            def __init__(self) -> None:
                self.frames = iter((
                    frame(10, 1), frame(11, 2), frame(12, 3), frame(12, 3),
                ))

            def get_json(self, path: str):
                if path != "/api/frame":
                    raise AssertionError(path)
                return next(self.frames)

        result = wait_for_stable_frame(
            FakeWeb(), sequence_before=10, timeout=0.1,
            poll_interval=0.001, stable_samples=2,
        )
        self.assertEqual(result["sequence_before"], 10)
        self.assertEqual(result["sequence_after"], 12)
        self.assertEqual(result["stable_samples"], 2)

    def test_safe_label(self) -> None:
        self.assertEqual(safe_label("network / right"), "network-right")

    def test_matrix_rearm_requires_release_gate_and_new_scan(self) -> None:
        registers = (
            "KEY_STATE=00000000 KEY_CODE=00000000 "
            "KEY_MATRIX=00000000:00000000\n"
            "IRQ64=ENABLED:1 F160:00FF MATRIX_READS:12346 MATRIX_WRITES:20\n"
            "KEY_GUEST=2A4C:0001 2A5C:0000 2A6E:0000\n"
        )
        self.assertEqual(matrix_rearm_state(registers, 12345), (True, 12346))
        self.assertEqual(matrix_rearm_state(registers, 12346), (False, 12346))

    def test_matrix_rearm_rejects_pressed_or_gated_state(self) -> None:
        pressed = (
            "KEY_STATE=00000000 KEY_MATRIX=00000001:00000000\n"
            "IRQ64=F160:00FE MATRIX_READS:11\n"
            "KEY_GUEST=2A5C:0000\n"
        )
        gated = pressed.replace(
            "KEY_MATRIX=00000001:00000000", "KEY_MATRIX=00000000:00000000"
        ).replace("2A5C:0000", "2A5C:0001").replace("F160:00FE", "F160:00FF")
        self.assertEqual(matrix_rearm_state(pressed, 10), (False, 11))
        self.assertEqual(matrix_rearm_state(gated, 10), (False, 11))

    def test_bounded_key_status_rearm_avoids_full_diagnostics(self) -> None:
        self.assertEqual(key_status_rearm_state({
            "matrix_reads": 101, "matrix_rearmed": True,
        }, 100), (True, 101))
        self.assertEqual(key_status_rearm_state({
            "matrix_reads": 100, "matrix_rearmed": True,
        }, 100), (False, 100))
        self.assertEqual(key_status_rearm_state({
            "matrix_reads": 101, "matrix_rearmed": False,
        }, 100), (False, 101))
        self.assertIsNone(key_status_rearm_state({}, 100))

    def test_key_delivery_requires_new_matching_map_and_ack(self) -> None:
        status = {
            "maps": 13,
            "event": 0x97,
            "acknowledgements": 9,
            "acknowledgement": 0x97,
        }
        self.assertEqual(
            key_delivery_state(
                status,
                maps_before=12,
                acknowledgements_before=8,
                expected_event=0x97,
            ),
            (True, True, "foreground"),
        )
        self.assertEqual(
            key_delivery_state(
                status,
                maps_before=13,
                acknowledgements_before=8,
                expected_event=0x97,
            ),
            (False, True, "foreground"),
        )
        self.assertEqual(
            key_delivery_state(
                status,
                maps_before=12,
                acknowledgements_before=8,
                expected_event=0xE9,
            ),
            (False, False, None),
        )

    def test_key_delivery_accepts_exact_modal_consumer(self) -> None:
        status = {
            "maps": 14,
            "event": 0xEA,
            "acknowledgements": 9,
            "acknowledgement": 0xBF,
            "modal_acknowledgements": 4,
            "modal_acknowledgement": 0xEA,
        }
        self.assertEqual(
            key_delivery_state(
                status,
                maps_before=13,
                acknowledgements_before=9,
                modal_acknowledgements_before=3,
                expected_event=0xEA,
            ),
            (True, True, "modal"),
        )

    def test_modal_consumer_reads_the_event_before_local_copy(self) -> None:
        helper = (
            Path(__file__).resolve().parents[2]
            / "qemu-dmcu" / "target" / "dmcu" / "helper.c"
        ).read_text(encoding="utf-8")
        hook = helper.split(
            "start == dmcu_code_address(0x1e, 0xf8e4)", 1
        )[1].split("}", 1)[0]
        self.assertIn("old_fp - 0x02u", hook)
        self.assertNotIn("old_fp - 0x0au", hook)

    def test_delivery_wait_requires_ack_and_released_guest_matrix(self) -> None:
        class FakeWeb:
            def get_json(self, path: str):
                if path == "/api/key-status":
                    return {
                        "maps": 13,
                        "event": 0x97,
                        "acknowledgements": 9,
                        "acknowledgement": 0x97,
                        "modal_acknowledgements": 2,
                        "modal_acknowledgement": 0xEA,
                    }
                self.assert_state_path(path)
                return {
                    "registers": (
                        "ROM_MISSING=none\nINVALID_CONTROL=none\n"
                        "UNSUPPORTED=none COUNT=0\n"
                        "KEY_STATE=00000000 KEY_MATRIX=00000000:00000000\n"
                        "IRQ64=F160:00FF MATRIX_READS:101\n"
                        "KEY_GUEST=2A5C:0000\n"
                    ),
                }

            @staticmethod
            def assert_state_path(path: str) -> None:
                if path != "/api/state":
                    raise AssertionError(path)

        reads, delivery = wait_for_delivery_and_matrix_rearm(
            FakeWeb(),
            reads_before=100,
            maps_before=12,
            acknowledgements_before=8,
            modal_acknowledgements_before=2,
            expected_event=0x97,
            require_foreground_ack=True,
            release_timeout=0.1,
            poll_interval=0.001,
        )
        self.assertEqual(reads, 101)
        self.assertEqual(delivery["maps"], 13)
        self.assertEqual(delivery["acknowledgements"], 9)

    def test_delivery_wait_uses_atomic_rearm_snapshot_when_available(self) -> None:
        class FakeWeb:
            @staticmethod
            def get_json(path: str):
                if path != "/api/key-status":
                    raise AssertionError(path)
                return {
                    "maps": 13,
                    "event": 0x97,
                    "acknowledgements": 9,
                    "acknowledgement": 0x97,
                    "modal_acknowledgements": 2,
                    "modal_acknowledgement": 0xEA,
                    "matrix_reads": 101,
                    "matrix_rearmed": True,
                    "faulted": False,
                }

        reads, delivery = wait_for_delivery_and_matrix_rearm(
            FakeWeb(),
            reads_before=100,
            maps_before=12,
            acknowledgements_before=8,
            modal_acknowledgements_before=2,
            expected_event=0x97,
            require_foreground_ack=True,
            release_timeout=0.1,
            poll_interval=0.001,
        )
        self.assertEqual(reads, 101)
        self.assertEqual(delivery["acknowledgement_path"], "foreground")

    def test_selector_candidate_requires_a_new_matching_slot_write(self) -> None:
        registers = (
            "SELECTOR_STATE_WRITES=COUNT:19 TRACE="
            "28:f604/5128d8/ffff>008c/16;"
            "28:f67e/5128da/ffff>008c/16\n"
        )
        matched, count, write = selector_candidate_state(
            registers, count_before=17, expected_event=0x8C,
        )
        self.assertTrue(matched)
        self.assertEqual(count, 19)
        self.assertEqual(write["address"], 0x5128D8)
        self.assertEqual(write["new"], 0x8C)
        self.assertEqual(
            selector_candidate_state(
                registers, count_before=19, expected_event=0x8C,
            ),
            (False, 19, None),
        )

    def test_selector_candidate_ignores_old_ring_entries(self) -> None:
        registers = (
            "SELECTOR_STATE_WRITES=COUNT:20 TRACE="
            "28:f604/5128d8/ffff>008c/16;"
            "28:f6da/5128da/008c>008d/16\n"
        )
        self.assertEqual(
            selector_candidate_state(
                registers, count_before=19, expected_event=0x8C,
            ),
            (False, 20, None),
        )


if __name__ == "__main__":
    unittest.main()
