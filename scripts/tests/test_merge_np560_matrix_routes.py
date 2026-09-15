from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import json
import tempfile
import unittest
from pathlib import Path

from scripts.merge_np560_matrix_routes import build_report, classify_step
from scripts.probe_np560_matrix_route import ACTIVE_MATRIX_EVENTS


class MergeMatrixRoutesTests(unittest.TestCase):
    def test_classifies_candidate_map_and_foreground_boundaries(self) -> None:
        base = {
            "expected_event": 0x85,
            "maps_before": 4,
            "maps_after": 4,
            "acknowledgements_before": 3,
            "acknowledgements_after": 3,
            "acknowledgement": 0,
        }
        self.assertEqual(classify_step(base), "candidate-only")
        self.assertEqual(
            classify_step({**base, "maps_after": 5}),
            "map-only",
        )
        self.assertEqual(
            classify_step({
                **base,
                "maps_after": 5,
                "acknowledgements_after": 4,
                "acknowledgement": 0x85,
            }),
            "map+foreground-ack",
        )

    def test_complete_report_requires_all_64_exact_positions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route.json"
            steps = []
            for index, event in enumerate(ACTIVE_MATRIX_EVENTS):
                candidate_only = event == 0x8C
                steps.append({
                    "matrix_index": index,
                    "expected_event": event,
                    "event": event,
                    "foreground_ack_required": not candidate_only,
                    "candidate_writes_before": index,
                    "candidate_writes_after": index + 1,
                    "maps_before": index,
                    "maps_after": index if candidate_only else index + 1,
                    "acknowledgements_before": index,
                    "acknowledgements_after": (
                        index if candidate_only else index + 1
                    ),
                    "acknowledgement": event,
                    "release_observed": True,
                })
            path.write_text(json.dumps({
                "schema": "np560-matrix-route-v2",
                "steps": steps,
            }), encoding="utf-8")
            report = build_report([path])
        self.assertTrue(report["complete"])
        self.assertEqual(report["covered"], 64)
        self.assertEqual(report["classification_counts"], {
            "candidate-only": 1,
            "map-only": 0,
            "map+foreground-ack": 63,
        })

    def test_missing_position_makes_report_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route.json"
            path.write_text(json.dumps({
                "schema": "np560-matrix-route-v2",
                "steps": [],
            }), encoding="utf-8")
            report = build_report([path])
        self.assertFalse(report["complete"])
        self.assertEqual(report["missing"], list(range(64)))


if __name__ == "__main__":
    unittest.main()
