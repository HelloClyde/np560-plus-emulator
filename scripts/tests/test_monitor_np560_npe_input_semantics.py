from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest

from scripts.monitor_np560_npe_input_semantics import (
    INPUT_PROBES,
    game_input_evidence,
    repeat_timing,
)


class NPEInputSemanticsTests(unittest.TestCase):
    def test_game_input_evidence_extracts_original_action_boundaries(self) -> None:
        self.assertEqual(game_input_evidence(
            "NPE_GAME_SERVICE=ARMED:1 CODE86:7 FLAGS:01\n"
            "NPE_GAME_LINKED_LOADER=4 PC:29:ce22\n"
            "NPE_GAME_ACTION=SELECT:3/3/R0002 LATE:5\n"
        ), {
            "code86": 7,
            "linked_loader": 4,
            "selector_calls": 3,
            "selector_returns": 3,
            "selector_result": 2,
            "late_paths": 5,
        })

    def test_controller_and_modal_probe_matrix_positions_are_explicit(self) -> None:
        self.assertEqual(
            (INPUT_PROBES["primary-action"].matrix_index,
             INPUT_PROBES["primary-action"].expected_event),
            (53, 0x86),
        )
        self.assertEqual(
            (INPUT_PROBES["back-84"].matrix_index,
             INPUT_PROBES["back-84"].expected_event),
            (28, 0x84),
        )

    def test_repeat_timing_ignores_map_only_updates(self) -> None:
        summary = repeat_timing({
            "hold_timeline": [
                {"elapsed_seconds": 0.0, "candidates_delta": 1,
                 "candidate": 0x83, "matrix_reads": 100,
                 "matrix_reads_delta": 1},
                {"elapsed_seconds": 0.02, "candidates_delta": 1,
                 "maps_delta": 1, "candidate": 0x83},
                {"elapsed_seconds": 0.51, "candidates_delta": 2,
                 "candidate": 0x83, "matrix_reads": 150,
                 "matrix_reads_delta": 51},
                {"elapsed_seconds": 0.71, "candidates_delta": 3,
                 "candidate": 0x83, "matrix_reads": 170,
                 "matrix_reads_delta": 71},
                {"elapsed_seconds": 0.91, "candidates_delta": 4,
                 "candidate": 0x83, "matrix_reads": 190,
                 "matrix_reads_delta": 91},
            ],
        })
        self.assertEqual(summary["observed_edge_transitions"], 4)
        self.assertEqual(summary["skipped_edges_between_polls"], 0)
        self.assertEqual(summary["first_repeat_seconds"], 0.51)
        self.assertEqual(summary["repeat_interval_median_seconds"], 0.2)
        self.assertEqual(summary["first_repeat_matrix_reads"], 50)
        self.assertEqual(summary["repeat_interval_median_matrix_reads"], 20)

    def test_repeat_timing_excludes_post_release_completion_from_period(self) -> None:
        summary = repeat_timing({
            "hold_timeline": [
                {"elapsed_seconds": 0.0, "candidates_delta": 1,
                 "phase": "held"},
                {"elapsed_seconds": 0.5, "candidates_delta": 2,
                 "phase": "held"},
                {"elapsed_seconds": 0.75, "candidates_delta": 3,
                 "phase": "held"},
                {"elapsed_seconds": 1.2, "candidates_delta": 4,
                 "phase": "post_release"},
            ],
        })
        self.assertEqual(summary["held_edge_transitions"], 3)
        self.assertEqual(summary["post_release_edge_transitions"], 1)
        self.assertEqual(summary["repeat_interval_median_seconds"], 0.25)

    def test_repeat_timing_reports_poll_skips(self) -> None:
        summary = repeat_timing({
            "hold_timeline": [
                {"elapsed_seconds": 0.0, "candidates_delta": 1},
                {"elapsed_seconds": 0.8, "candidates_delta": 4},
            ],
        })
        self.assertEqual(summary["skipped_edges_between_polls"], 2)


if __name__ == "__main__":
    unittest.main()
