import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe_np560_npe_stream_window import compare_window, matching_prefix


class NPEStreamWindowTests(unittest.TestCase):
    def test_prefix_boundary_and_zero_tail(self):
        section = b"original" + b"payload"
        guest = b"original" + bytes(7)
        result = compare_window(guest, section)
        self.assertEqual(result["matching_prefix_bytes"], 8)
        self.assertFalse(result["full_window_equal"])
        self.assertTrue(result["guest_remaining_zero"])

    def test_complete_match_and_shorter_input(self):
        self.assertEqual(matching_prefix(b"abc", b"abcdef"), 3)
        result = compare_window(b"abc", b"abcdef")
        self.assertTrue(result["full_window_equal"])
        self.assertIsNone(result["guest_remaining_zero"])

    def test_longer_guest_rejected(self):
        with self.assertRaises(ValueError):
            compare_window(b"abcd", b"abc")


if __name__ == "__main__":
    unittest.main()
