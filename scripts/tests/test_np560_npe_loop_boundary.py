import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe_np560_npe_loop_boundary import parse_hle, parse_prg_time


class NPELoopBoundaryTests(unittest.TestCase):
    def test_hle_counter_identity(self):
        self.assertEqual(parse_hle("experimental stream-frames=2019 calls=2,4,123,9,0,0"),
                         (4, 2019))
        with self.assertRaises(ValueError):
            parse_hle("disabled")

    def test_prg_time_is_high_word_first(self):
        words = [0] * 16
        words[(0x282a - 0x2828) // 2] = 13
        words[(0x282c - 0x2828) // 2] = 2020
        words[(0x283a - 0x2828) // 2] = 8400
        words[(0x2840 - 0x2828) // 2] = 40400
        words[(0x2844 - 0x2828) // 2] = 40360
        result = parse_prg_time(struct.pack("<16H", *words))
        self.assertEqual(result["total_ms"], 40400)
        self.assertEqual(result["current_ms"], 40360)
        self.assertEqual(result["remaining_ms"], 40)


if __name__ == "__main__":
    unittest.main()
