
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
import build_np560_rom_skeleton as skeleton


class RomSkeletonTests(unittest.TestCase):
    def test_parse_and_build_sparse_stubs(self):
        first = skeleton.parse_stub("02:BAC4")
        second = skeleton.parse_stub("02:BAC8=zero")
        image = skeleton.build_image([first, second])

        self.assertEqual(first.mode, "rets")
        self.assertEqual(first.display_address, "02:BAC4")
        self.assertEqual(
            int.from_bytes(image[0x2BAC4 : 0x2BAC6], "little"), skeleton.RETS
        )
        self.assertEqual(
            int.from_bytes(image[0x2BAC6 : 0x2BAC8], "little"), skeleton.RESERVED
        )
        self.assertEqual(
            int.from_bytes(image[0x2BAC8 : 0x2BACA], "little"),
            skeleton.MOV_R0_ZERO,
        )
        self.assertEqual(
            int.from_bytes(image[0x2BACA : 0x2BACC], "little"), skeleton.RETS
        )

    def test_rejects_overlapping_stubs(self):
        with self.assertRaisesRegex(ValueError, "overlaps"):
            skeleton.build_image(
                [skeleton.parse_stub("02:BAC4=zero"), skeleton.parse_stub("02:BAC6")]
            )

    def test_zero32_clears_return_pair(self):
        stub = skeleton.parse_stub("02:BB1E=zero32")
        image = skeleton.build_image([stub])
        words = [
            int.from_bytes(image[offset : offset + 2], "little")
            for offset in range(0x2BB1E, 0x2BB24, 2)
        ]
        self.assertEqual(
            words,
            [skeleton.MOV_R0_ZERO, skeleton.MOV_R1_ZERO, skeleton.RETS],
        )

    def test_pair_sets_arbitrary_return_registers(self):
        stub = skeleton.parse_stub("02:BB1E=pair:0x1234:0x76EC")
        image = skeleton.build_image([stub])
        words = [
            int.from_bytes(image[offset : offset + 2], "little")
            for offset in range(0x2BB1E, 0x2BB28, 2)
        ]
        self.assertEqual(stub.values, (0x1234, 0x76EC))
        self.assertEqual(words, [0x68F0, 0x1234, 0x68F1, 0x76EC, skeleton.RETS])

    def test_rejects_odd_address(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            skeleton.parse_stub("02:BAC5")


if __name__ == "__main__":
    unittest.main()
