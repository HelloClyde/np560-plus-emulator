from __future__ import annotations

import unittest

from scripts.explore_np560_npe_map import (
    DIRECTIONS,
    OPPOSITE,
    direction_order,
    explorer_state,
    faces_world_target,
    position_record,
    position_tuple,
    route_to_unexplored,
)


class NPEMapExplorerTests(unittest.TestCase):
    def test_direction_order_has_exact_inverses(self) -> None:
        self.assertEqual(DIRECTIONS, ("up", "right", "down", "left"))
        for direction in DIRECTIONS:
            self.assertEqual(OPPOSITE[OPPOSITE[direction]], direction)

    def test_position_record_names_feedback_components(self) -> None:
        position = (4, 5, 0x1234, 6, 7, 3)
        record = position_record(position)
        self.assertEqual(record, {
            "x": 4,
            "y": 5,
            "map_index": 0x1234,
            "offset_x": 6,
            "offset_y": 7,
            "direction": 3,
        })
        self.assertEqual(position_tuple(record), position)

    def test_explorer_state_includes_action_facing(self) -> None:
        self.assertEqual(explorer_state({
            "current_x": 4,
            "current_y": 5,
            "current_map_index": 0x1234,
            "current_scroll": 0x20,
            "current_offset_x": 6,
            "current_offset_y": 7,
            "current_direction": 2,
        }), (4, 5, 0x1234, 6, 7, 2))

    def test_route_to_unexplored_follows_directed_edges(self) -> None:
        a = (0, 0, 1, 0, 0, 1)
        b = (1, 0, 1, 0, 0, 1)
        c = (2, 0, 1, 0, 0, 1)
        graph = {
            a: {"right": b},
            b: {"right": c},
            c: {},
        }
        attempts = {
            a: set(DIRECTIONS),
            b: set(DIRECTIONS),
            c: {"up", "right"},
        }
        self.assertEqual(
            route_to_unexplored(a, graph, attempts),
            ["right", "right"],
        )
        attempts[c] = set(DIRECTIONS)
        self.assertIsNone(route_to_unexplored(a, graph, attempts))

    def test_route_to_unexplored_prefers_target_world_frontier(self) -> None:
        start = (8, 1, 1, 1, 11, 0)
        near = (4, 1, 1, 0, 5, 0)
        far = (10, 1, 1, 1, 11, 0)
        graph = {
            start: {"left": near, "right": far},
            near: {},
            far: {},
        }
        attempts = {
            start: set(DIRECTIONS),
            near: {"up", "right"},
            far: {"up", "right"},
        }
        self.assertEqual(
            route_to_unexplored(start, graph, attempts, (1, 6)),
            ["left"],
        )

    def test_direction_order_remains_exhaustive_and_target_guided(self) -> None:
        state = (4, 1, 1, 0, 5, 0)
        order = direction_order(state, (1, 6))
        self.assertEqual(order[0], "left")
        self.assertEqual(set(order), set(DIRECTIONS))
        self.assertEqual(direction_order(state, None), DIRECTIONS)

    def test_faces_world_target_uses_offset_and_direction(self) -> None:
        self.assertTrue(faces_world_target((2, 1, 1, 0, 5, 3), (1, 6)))
        self.assertFalse(faces_world_target((2, 1, 1, 0, 5, 1), (1, 6)))


if __name__ == "__main__":
    unittest.main()
