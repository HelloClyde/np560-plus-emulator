from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest

from scripts.build_np560_stream_burn_harness import (
    PROGRAM_SIZE,
    STREAM_ACK,
    STREAM_FLAG,
    STREAM_FINALIZE_COMMAND,
    STREAM_FINALIZE_VALUE,
    STREAM_READY,
    STREAM_START,
    build_program,
)


class StreamBurnHarnessTests(unittest.TestCase):
    def test_setup_stream_loop_and_stop_are_encoded(self) -> None:
        image, addresses = build_program()
        self.assertEqual(len(image), PROGRAM_SIZE)
        words = [
            int.from_bytes(image[offset:offset + 2], "little")
            for offset in range(0, addresses["stop"] + 2, 2)
        ]
        calls = list(zip(words, words[1:]))
        self.assertEqual(calls.count((0xBD50, 0x6000)), 1)
        self.assertEqual(calls.count((0xBD50, 0x6004)), 7)
        self.assertEqual(calls.count((0xBD50, 0x7566)), 0)
        self.assertIn((0x88F0, STREAM_FLAG), calls)
        self.assertIn((0x88F0, STREAM_ACK), calls)
        self.assertIn(STREAM_READY, words)
        self.assertEqual(words[-1], 0xD0FF)

    def test_official_command_ids_and_total_length_are_encoded(self) -> None:
        image, addresses = build_program(0x12345678)
        words = [
            int.from_bytes(image[offset:offset + 2], "little")
            for offset in range(0, addresses["stop"] + 2, 2)
        ]
        for command in (23, 1, 27, 11, 2, 25, 13,
                        STREAM_FINALIZE_COMMAND):
            self.assertIn(command, words)
        self.assertIn(STREAM_FINALIZE_VALUE, words)
        self.assertEqual(STREAM_START, 0x880)
        self.assertIn(0x1234, words)
        self.assertIn(0x5678, words)

    def test_jump_targets_are_byte_addresses(self) -> None:
        image, addresses = build_program()
        words = [
            int.from_bytes(image[offset:offset + 2], "little")
            for offset in range(0, addresses["stop"] + 2, 2)
        ]
        loop = addresses["loop"]
        done = addresses["done"]
        self.assertGreaterEqual(words.count(loop), 2)
        self.assertIn(done, words)

    def test_setup_commands_follow_updateall_order(self) -> None:
        image, addresses = build_program()
        words = [
            int.from_bytes(image[offset:offset + 2], "little")
            for offset in range(0, addresses["stop"] + 2, 2)
        ]
        command_positions = [
            index + 1
            for index in range(len(words) - 3)
            if words[index] == 0x68F0
            and words[index + 2] == 0xA8F0
            and words[index + 3] == 0x0008
        ]
        self.assertGreaterEqual(len(command_positions), 8)
        self.assertEqual(
            [words[index] for index in command_positions[:8]],
            [23, 1, 27, 11, 2, 25, 13, STREAM_FINALIZE_COMMAND],
        )

    def test_unknown_nonofficial_setup_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_program(setup_mode="formatted")


if __name__ == "__main__":
    unittest.main()
