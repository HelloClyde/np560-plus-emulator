
# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import unittest
from unittest.mock import patch

import burn_np560_stream as burn
from build_np560_stream_burn_harness import build_program, STREAM_UPDATEALL_PROTOCOL


class UpdateAllSetupTests(unittest.TestCase):
    def test_partition_request_uses_original_updater_rounding(self):
        self.assertEqual(burn.updater_partition_kib(43963316), 0xABF5)
        self.assertEqual(burn.updater_partition_kib(1024), 0x441)
        self.assertEqual(burn.updater_partition_kib(1025), 0x442)
        for size in (0, -1, 0xFFFFFFFF):
            with self.assertRaises(ValueError):
                burn.updater_partition_kib(size)

    def run_flow(self, responses):
        self.calls = []

        def command(code, assignments):
            self.calls.append((code, dict(assignments)))
            result, detail = responses.get(code, (0, 0))
            return {"command": code, "result": result, "detail": detail}

        return burn.prepare_updateall(command, 0x029ED3B4, 0xABF5)

    def test_formatted_input_is_not_reformatted(self):
        records = self.run_flow({1: (0, -7), 27: (0, -7)})
        self.assertEqual([r["command"] for r in records], [23, 1, 27, 25])
        self.assertEqual(self.calls[1][1], {0x34: 0, 0x36: 0xABF5, 0x94: 2})
        self.assertEqual(self.calls[-1][1], {0x38: 0x029E, 0x3A: 0xD3B4, 0x3C: 0, 0x3E: 0xC000})

    def test_unformatted_input_follows_vendor_repartition_branch(self):
        for detail in (-2, -3):
            records = self.run_flow({1: (-11, detail), 27: (-12, detail)})
            self.assertEqual([r["command"] for r in records], [23, 1, 27, 11, 2, 25])
            self.assertEqual(self.calls[3][1], {0x10: 0, 0x12: 0xABF5})

    def test_format_error_branch_initializes_before_partition_check(self):
        records = self.run_flow({1: (-10, -2)})
        self.assertEqual([r["command"] for r in records], [23, 1, 2, 27, 25])

    def test_unknown_prepare_error_never_triggers_format(self):
        for pair in ((-11, -1), (-10, -1), (-1, -2)):
            with self.subTest(pair=pair):
                with self.assertRaisesRegex(RuntimeError, "prepare-error branch"):
                    self.run_flow({1: pair})
                self.assertEqual([c for c, _ in self.calls], [23, 1])

    def test_unexpected_partition_or_format_error_stops(self):
        with self.assertRaisesRegex(RuntimeError, "partition result"):
            self.run_flow({27: (-4, -2)})
        self.assertNotIn(11, [c for c, _ in self.calls])
        with self.assertRaisesRegex(RuntimeError, "command failed"):
            self.run_flow({27: (-12, -2), 11: (-11, -1)})
        self.assertEqual([c for c, _ in self.calls], [23, 1, 27, 11])

    def test_bootstrap_and_stream_prepare_failures_are_not_ignored(self):
        for command in (23, 25):
            with self.assertRaisesRegex(RuntimeError, "command failed"):
                self.run_flow({command: (-1, -2)})
            self.assertEqual(self.calls[-1][0], command)

    def test_real_return_and_detailed_error_are_separate(self):
        with patch.object(burn, "words", return_value=(0xFFFF, 0xFFF5, 5, 6, 0xFFF5, 0xFFFE, 0, 0)):
            result = burn.read_updateall_return(None, 1)
        self.assertEqual(result["result"], -11)
        self.assertEqual(result["detail"], -2)
        self.assertEqual(result["registers"], [0xFFFF, 0xFFF5, 5, 6])
        with patch.object(burn, "words", return_value=(0, 0, 5, 6, 0xFFF5, 0xFFFE, 0, 0)):
            with self.assertRaisesRegex(RuntimeError, "R0:R1"):
                burn.read_updateall_return(None, 1)

    def test_harness_does_not_autonomously_format(self):
        image, labels = build_program(setup_mode="updateall")
        words = [int.from_bytes(image[i:i + 2], "little") for i in range(0, labels["stop"] + 2, 2)]
        self.assertIn(STREAM_UPDATEALL_PROTOCOL, words)
        commands = [words[i + 1] for i in range(len(words) - 3)
                    if words[i] == 0x68F0 and words[i + 2:i + 4] == [0xA8F0, 8]]
        self.assertEqual(commands, [23, 13, 18])
        self.assertEqual(list(zip(words, words[1:])).count((0xBD50, 0x6000)), 1)
        self.assertEqual(list(zip(words, words[1:])).count((0xBD50, 0x6004)), 2)
        self.assertEqual(words[-1], 0xD0FF)


if __name__ == "__main__":
    unittest.main()
