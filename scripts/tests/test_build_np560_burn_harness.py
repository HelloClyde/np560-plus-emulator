
# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import argparse
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_np560_burn_harness as harness


class BurnHarnessTests(unittest.TestCase):
    def test_emits_guest_command_store_and_far_jump(self):
        image = harness.build_program(4, [(0x000A, 0x1234)])
        words = [
            int.from_bytes(image[offset : offset + 2], "little")
            for offset in range(0, 26, 2)
        ]
        self.assertEqual(
            words,
            [
                0x6810, 0x00A0,
                0x68F0, 0x0004, 0xA8F0, 0x0008,
                0x68F0, 0x1234, 0xA8F0, 0x000A,
                0xBD50, 0x6000,
                0xD0FF,
            ],
        )
        self.assertEqual(len(image), harness.PROGRAM_SIZE)

    def test_validates_command_and_assignment(self):
        with self.assertRaisesRegex(ValueError, "1..27"):
            harness.build_program(0, [])
        with self.assertRaises(argparse.ArgumentTypeError):
            harness.parse_word("3=1")
        with self.assertRaises(argparse.ArgumentTypeError):
            harness.parse_step_word("1:3=1")
        with self.assertRaises(argparse.ArgumentTypeError):
            harness.parse_far_entry("0x100:0")
        with self.assertRaises(argparse.ArgumentTypeError):
            harness.parse_embed("payload.bin")
        self.assertEqual(
            harness.parse_embed("payload.bin@0x1000:0x400"),
            (Path("payload.bin"), 0x1000, 0x400),
        )
        with self.assertRaisesRegex(ValueError, "selects step 2"):
            harness.build_program(1, [], [27], [(2, 0x0010, 0x1234)])

    def test_emits_stateful_follow_up_dispatch(self):
        image = harness.build_program(1, [], [13])
        words = [
            int.from_bytes(image[offset : offset + 2], "little")
            for offset in range(0, 30, 2)
        ]
        self.assertEqual(
            words,
            [
                0x6810, 0x00A0,
                0x68F0, 0x0001, 0xA8F0, 0x0008,
                0xBD50, 0x6000,
                0x68F0, 0x000D, 0xA8F0, 0x0008,
                0xBD50, 0x7566,
                0xD0FF,
            ],
        )

    def test_emits_command_local_assignments(self):
        image = harness.build_program(
            1,
            [(0x0034, 0x0000)],
            [27, 11],
            [(2, 0x0010, 0x0000), (2, 0x0012, 0xABF5)],
        )
        words = [
            int.from_bytes(image[offset : offset + 2], "little")
            for offset in range(0, 66, 2)
        ]
        self.assertEqual(
            words,
            [
                0x6810, 0x00A0,
                0x68F0, 0x0001, 0xA8F0, 0x0008,
                0x68F0, 0x0000, 0xA8F0, 0x0034,
                0xBD50, 0x6000,
                0x68F0, 0x001B, 0xA8F0, 0x0008,
                0xBD50, 0x7566,
                0x68F0, 0x000B, 0xA8F0, 0x0008,
                0x68F0, 0x0000, 0xA8F0, 0x0010,
                0x68F0, 0xABF5, 0xA8F0, 0x0012,
                0xBD50, 0x7566,
                0xD0FF,
            ],
        )

    def test_emits_tail_call(self):
        image = harness.build_program(1, [], tail_calls=[(0x51, 0x4452)])
        words = [
            int.from_bytes(image[offset : offset + 2], "little")
            for offset in range(0, 22, 2)
        ]
        self.assertEqual(
            words,
            [
                0x6810, 0x00A0,
                0x68F0, 0x0001, 0xA8F0, 0x0008,
                0xBD50, 0x6000,
                0xBD51, 0x4452,
                0xD0FF,
            ],
        )

    def test_embeds_raw_stream_without_word_swapping(self):
        payload = bytes.fromhex("4d41534b524f4d00feca")
        image = harness.build_program(
            13, [], embeds=[(0x1000, payload)]
        )

        self.assertEqual(image[0x1000:0x1000 + len(payload)], payload)
        with self.assertRaisesRegex(ValueError, "overlaps"):
            harness.build_program(13, [], embeds=[(0, payload)])
        with self.assertRaisesRegex(ValueError, "past"):
            harness.build_program(
                13, [], embeds=[(harness.PROGRAM_SIZE - 2, payload)]
            )


if __name__ == "__main__":
    unittest.main()
