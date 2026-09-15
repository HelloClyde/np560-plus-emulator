from __future__ import annotations

import unittest

from scripts.probe_np560_npe_object_action import (
    COUNTERS,
    action_deltas,
    changed_offsets,
    contiguous_runs,
    require_delta,
)


class NPEObjectActionProbeTests(unittest.TestCase):
    def test_action_deltas_cover_every_observer_counter(self) -> None:
        before = {name: index for index, name in enumerate(COUNTERS)}
        after = {name: before[name] + 1 for name in COUNTERS}
        self.assertEqual(
            action_deltas(before, after),
            {name: 1 for name in COUNTERS},
        )

    def test_require_delta_rejects_mismatch(self) -> None:
        require_delta({"counter": 1}, "counter", 1)
        with self.assertRaisesRegex(RuntimeError, "expected 1"):
            require_delta({"counter": 0}, "counter", 1)

    def test_memory_diff_helpers(self) -> None:
        self.assertEqual(changed_offsets(b"abcd", b"axcy"), [1, 3])
        self.assertEqual(
            contiguous_runs([1, 2, 3, 7, 9, 10]),
            [(1, 4), (7, 8), (9, 11)],
        )


if __name__ == "__main__":
    unittest.main()
