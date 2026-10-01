import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verify_np560_npe_codec_trace import compare_trace, swapped_stream


class NPECodecTraceTests(unittest.TestCase):
    def test_odd_frame_boundary_preserves_global_word_swap(self):
        section = b"\x20\x0d\x00\x02" + bytes(range(44))
        swapped = swapped_stream(section)
        self.assertEqual(swapped[20:23], bytes((21, 20, 23)))
        rows = [{"index": 3 + index,
                 "frame_hex": swapped[index * 21:(index + 1) * 21].hex()}
                for index in range(2)]
        result = compare_trace(section, rows, 3, 21)
        self.assertEqual(result["matching_prefix_frames"], 2)
        self.assertIsNone(result["first_mismatch"])

    def test_reports_first_bad_byte(self):
        section = b"\x20\x0d\x00\x02" + bytes(range(44))
        swapped = swapped_stream(section)
        damaged = bytearray(swapped[21:42])
        damaged[10] ^= 0x55
        rows = [{"index": 3, "frame_hex": swapped[:21].hex()},
                {"index": 4, "frame_hex": damaged.hex()}]
        result = compare_trace(section, rows, 3, 21)
        self.assertEqual(result["matching_prefix_frames"], 1)
        self.assertEqual(result["first_mismatch"]["first_different_byte"], 10)

    def test_bounded_prefix_ignores_next_stream(self):
        section = b"\x20\x0d\x00\x01" + bytes(range(22))
        swapped = swapped_stream(section)
        rows = [{"index": 3, "frame_hex": swapped[:21].hex()},
                {"index": 4, "frame_hex": (b"\xff" * 21).hex()}]
        result = compare_trace(section, rows, 3, 21, max_frames=1)
        self.assertEqual(result["matching_prefix_frames"], 1)
        self.assertEqual(result["checked_frames"], 1)

    def test_bounded_prefix_rejects_short_trace(self):
        section = b"\x20\x0d\x00\x02" + bytes(range(44))
        swapped = swapped_stream(section)
        with self.assertRaisesRegex(ValueError, "trace ended"):
            compare_trace(section, [{"index": 3, "frame_hex": swapped[:21].hex()}],
                          3, 21, max_frames=2)


if __name__ == "__main__":
    unittest.main()
