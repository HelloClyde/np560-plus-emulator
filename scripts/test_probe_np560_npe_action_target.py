from __future__ import annotations

import unittest

from scripts.probe_np560_npe_action_target import (
    DIRECTION_COUNTER_FIELDS,
    movement_state,
    position_state,
    spiral_directions,
)


class NPEActionTargetProbeTests(unittest.TestCase):
    def test_spiral_directions_expand_two_legs_per_length(self) -> None:
        self.assertEqual(list(spiral_directions(12)), [
            "right", "down",
            "left", "left", "up", "up",
            "right", "right", "right",
            "down", "down", "down",
        ])

    def test_direction_counters_are_separate_original_controller_paths(self) -> None:
        self.assertEqual(DIRECTION_COUNTER_FIELDS, {
            "up": "direction_up_paths",
            "down": "direction_down_paths",
            "left": "direction_left_paths",
            "right": "direction_right_paths",
        })

    def test_position_and_movement_state_use_feedback_fields(self) -> None:
        status = {
            "current_x": 4,
            "current_y": 5,
            "current_map_index": 0x1234,
            "current_scroll": 0x20,
            "current_offset_x": 6,
            "current_offset_y": 7,
            "direction_helper_result": 3,
            "direction_code": 2,
            "direction_before_x": 4,
            "direction_before_y": 5,
            "direction_before_offset_x": 6,
            "direction_before_offset_y": 7,
            "direction_after_x": 4,
            "direction_after_y": 4,
            "direction_after_offset_x": 6,
            "direction_after_offset_y": 8,
            "direction_before_map_index": 0x1234,
            "direction_before_scroll": 0x20,
            "direction_after_map_index": 0x1235,
            "direction_after_scroll": 0x1F,
        }
        self.assertEqual(position_state(status), (4, 5, 0x1234, 6, 7))
        self.assertEqual(movement_state(status), {
            "direction_helper_result": 3,
            "direction_code": 2,
            "direction_before_x": 4,
            "direction_before_y": 5,
            "direction_before_offset_x": 6,
            "direction_before_offset_y": 7,
            "direction_after_x": 4,
            "direction_after_y": 4,
            "direction_after_offset_x": 6,
            "direction_after_offset_y": 8,
            "direction_before_map_index": 0x1234,
            "direction_before_scroll": 0x20,
            "direction_after_map_index": 0x1235,
            "direction_after_scroll": 0x1F,
        })


if __name__ == "__main__":
    unittest.main()
