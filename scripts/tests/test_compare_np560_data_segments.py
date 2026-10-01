"""Tests for read-only guest data-bank state comparison."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_np560_data_segments import classify, compare, read_capture


class DataSegmentCompareTests(unittest.TestCase):
    def test_classify_requires_stable_distinct_on_off(self) -> None:
        rows = classify(
            bytes([0, 7, 3, 1]), bytes([0, 7, 4, 1]),
            bytes([1, 8, 6, 2]), bytes([1, 9, 6, 2]),
            bytes([0, 7, 3, 3]), bytes([0, 7, 3, 3]),
        )
        self.assertEqual([row["offset"] for row in rows], [0, 2, 3])
        self.assertTrue(rows[0]["cold_matches_off"])
        self.assertFalse(rows[1]["cold_stable"])
        self.assertFalse(rows[2]["cold_matches_on"])

    def test_corrupt_capture_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            raw = bytes(65536)
            (path / "52.bin").write_bytes(raw)
            (path / "manifest.json").write_text(json.dumps({
                "schema": "np560-data-segment-snapshot-v1",
                "run_id": "test-run",
                "segments": {"52": hashlib.sha256(raw).hexdigest()},
            }), encoding="utf-8")
            self.assertEqual(read_capture(path)[1]["52"], raw)
            (path / "52.bin").write_bytes(raw[:-1] + b"x")
            with self.assertRaisesRegex(ValueError, "corrupt segment"):
                read_capture(path)

    def test_mixed_runs_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            raw = bytes(65536)
            for index in range(6):
                path = Path(folder) / str(index)
                path.mkdir()
                (path / "52.bin").write_bytes(raw)
                (path / "manifest.json").write_text(json.dumps({
                    "schema": "np560-data-segment-snapshot-v1",
                    "run_id": "other-run" if index == 5 else "test-run",
                    "segments": {"52": hashlib.sha256(raw).hexdigest()},
                }), encoding="utf-8")
                paths.append(path)
            with self.assertRaisesRegex(ValueError, "share one QEMU run"):
                compare(paths)


if __name__ == "__main__":
    unittest.main()
