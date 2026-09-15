#!/usr/bin/env python3

from __future__ import annotations

import unittest

try:
    from probe_np560_npe_input_combinations import (
        combined_masks,
        consumer_delta,
        counter_deltas,
        require_single_event,
        simultaneous_winner,
    )
except ModuleNotFoundError:
    from .probe_np560_npe_input_combinations import (
        combined_masks,
        consumer_delta,
        counter_deltas,
        require_single_event,
        simultaneous_winner,
    )


class NpeInputCombinationTests(unittest.TestCase):
    def test_combined_masks_span_both_matrix_words(self) -> None:
        self.assertEqual(combined_masks(3, 37, 53), (1 << 3, (1 << 5) | (1 << 21)))

    def test_counter_deltas_and_consumer_paths(self) -> None:
        before = {
            "candidates": 4,
            "maps": 5,
            "acknowledgements": 7,
            "modal_acknowledgements": 11,
        }
        after = {
            "candidates": 5,
            "maps": 6,
            "acknowledgements": 7,
            "modal_acknowledgements": 12,
        }
        deltas = counter_deltas(before, after)
        self.assertEqual(consumer_delta(deltas), 1)
        require_single_event(deltas, label="test")

    def test_rejects_unbalanced_event(self) -> None:
        deltas = counter_deltas({}, {
            "candidates": 1,
            "maps": 2,
            "acknowledgements": 1,
        })
        with self.assertRaisesRegex(RuntimeError, "not one balanced"):
            require_single_event(deltas, label="test")

    def test_simultaneous_priority_follows_descending_matrix_index(self) -> None:
        self.assertEqual(simultaneous_winner("up"), (61, 0x82, "direction_up_paths"))
        for name in ("down", "right", "left"):
            self.assertEqual(simultaneous_winner(name), (53, 0x86, "primary-action"))


if __name__ == "__main__":
    unittest.main()
