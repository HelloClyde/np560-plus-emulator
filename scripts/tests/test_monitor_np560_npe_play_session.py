from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import base64
import hashlib
import unittest

from scripts.monitor_np560_npe_play_session import (
    BOOT_START_STEP,
    EXIT_STEP,
    PLAY_ACTIONS,
    ROUTE_TO_GAME,
    ROUTE_FROM_EXPANDED_START_MENU,
    application_state,
    compact_state,
    desktop_menu_ready,
    desktop_blit_count,
    game_loop,
    game_ready,
    hero_journey_menu_ready,
    key_counter_snapshot,
    lcd_frame_sha256,
    play_limit_reached,
    root_render_count,
    start_menu_expanded,
    single_edge_violation,
)


REGISTERS = (
    "PC=1a:1234  PSW=----\n"
    "APPLICATION_STATE=STATE:0078 RESOURCE_FLAG:0001\n"
    "MATRIX_READS:2600 MATRIX_WRITES:9\n"
    "NPE_GAME_LOOP=GRID:10/10 INIT:10/10 RANGE:2 RAND:3 CMP:4 "
    "DRAW:11/11 ITEM:12 STATEDISP:13\n"
    "DESKTOP_BLIT_TRACE=COUNT:19 TRACE:none\n"
    "ROOT_RENDER_FLAGS=COUNT:38 TRACE:none\n"
    "ROM_MISSING=none FETCHES=0\n"
    "UNSUPPORTED=none COUNT=0\n"
    "INVALID_CONTROL=none\n"
)


class NpePlaySessionTests(unittest.TestCase):
    def test_recovered_route_and_play_matrix_positions(self) -> None:
        self.assertEqual(
            [(step.matrix_index, step.expected_event)
            for step in ROUTE_TO_GAME],
            [(55, 0xB0), (53, 0x86), (37, 0x83),
             (53, 0x86), (53, 0x86), (53, 0x86), (53, 0x86)],
        )
        self.assertEqual(
            [(step.matrix_index, step.expected_event)
             for step in PLAY_ACTIONS],
            [(37, 0x83), (29, 0x81), (61, 0x82), (45, 0x80)],
        )
        self.assertEqual(
            (EXIT_STEP.matrix_index, EXIT_STEP.expected_event), (55, 0xB0)
        )
        self.assertEqual(
            (BOOT_START_STEP.matrix_index, BOOT_START_STEP.expected_event),
            (55, 0xB0),
        )
        self.assertEqual(
            ROUTE_FROM_EXPANDED_START_MENU, ROUTE_TO_GAME[1:]
        )

    def test_expanded_start_menu_lcd_gate(self) -> None:
        width, height = 240, 120
        expanded = bytearray([31] * (width * height))
        closed = bytearray(expanded)
        for y in range(25, 35):
            for x in range(12):
                closed[y * width + x] = 0

        def state(frame: bytes) -> dict[str, object]:
            return {
                "format": "gray5", "width": width, "height": height,
                "frame": base64.b64encode(frame).decode("ascii"),
            }

        self.assertTrue(start_menu_expanded(state(expanded)))
        self.assertFalse(start_menu_expanded(state(closed)))
        self.assertFalse(start_menu_expanded({}))

    def test_lcd_frame_hash_rejects_malformed_state(self) -> None:
        frame = bytes(range(24))
        state = {
            "format": "gray5", "width": 6, "height": 4,
            "frame": base64.b64encode(frame).decode("ascii"),
        }
        self.assertEqual(lcd_frame_sha256(state), hashlib.sha256(frame).hexdigest())
        self.assertFalse(hero_journey_menu_ready(state))
        self.assertIsNone(lcd_frame_sha256({}))

    def test_state_parsers_and_ready_gate(self) -> None:
        self.assertEqual(application_state(REGISTERS), 0x78)
        self.assertEqual(desktop_blit_count(REGISTERS), 19)
        self.assertEqual(root_render_count(REGISTERS), 38)
        self.assertTrue(desktop_menu_ready(
            REGISTERS.replace("STATE:0078", "STATE:00ff"), 37
        ))
        self.assertFalse(desktop_menu_ready(
            REGISTERS.replace("STATE:0078", "STATE:00ff"), 38
        ))
        self.assertFalse(desktop_menu_ready(REGISTERS, 37))
        self.assertEqual(game_loop(REGISTERS)["draw_returns"], 11)
        self.assertTrue(game_ready(REGISTERS))
        self.assertFalse(game_ready(REGISTERS.replace("GRID:10/10", "GRID:11/10")))
        self.assertTrue(game_ready(REGISTERS.replace("GRID:10/10", "GRID:0/0")))
        self.assertFalse(game_ready(REGISTERS.replace("DRAW:11/11", "DRAW:0/0")))
        self.assertFalse(game_ready(REGISTERS.replace("STATE:0078", "STATE:00ff")))
        self.assertFalse(game_ready(REGISTERS.replace(
            "ROM_MISSING=none FETCHES=0", "ROM_MISSING=1a:1234 FETCHES=1"
        )))

    def test_compact_state_omits_full_register_payload(self) -> None:
        frame = bytes(range(24))
        summary, decoded = compact_state({
            "running": True,
            "format": "gray5",
            "width": 6,
            "height": 4,
            "frame": base64.b64encode(frame).decode("ascii"),
            "registers": REGISTERS + "LARGE_TRACE=" + "x" * 10000,
        })
        self.assertEqual(decoded, frame)
        self.assertNotIn("registers", summary)
        self.assertEqual(summary["matrix_reads"], 2600)
        self.assertEqual(summary["root_render_count"], 38)
        self.assertEqual(summary["frame"]["sha256"], hashlib.sha256(frame).hexdigest())

    def test_single_edge_gate_uses_settled_pipeline_totals(self) -> None:
        self.assertEqual(
            key_counter_snapshot({
                "candidates": 11, "maps": 10,
                "acknowledgements": 4, "modal_acknowledgements": 6,
            }),
            (11, 10, 4, 6),
        )
        self.assertIsNone(single_edge_violation({
            "candidate_writes_total": 1,
            "maps_total": 1,
            "consumer_acknowledgements_total": 1,
        }))
        self.assertEqual(single_edge_violation({
            "candidate_writes_total": 2,
            "maps_total": 2,
            "consumer_acknowledgements_total": 2,
        }), "candidate=2, map=2, consumer_ack=2")
        self.assertEqual(single_edge_violation({}),
                         "candidate=-1, map=-1, consumer_ack=-1")

    def test_play_limit_can_be_exact_edge_count_or_duration(self) -> None:
        self.assertFalse(play_limit_reached(
            999, 9999.0, duration=None, action_count=1000
        ))
        self.assertTrue(play_limit_reached(
            1000, 1.0, duration=None, action_count=1000
        ))
        self.assertFalse(play_limit_reached(
            5000, 59.9, duration=60.0, action_count=None
        ))
        self.assertTrue(play_limit_reached(
            0, 60.0, duration=60.0, action_count=None
        ))
        with self.assertRaises(ValueError):
            play_limit_reached(0, 0.0, duration=None, action_count=None)


if __name__ == "__main__":
    unittest.main()
