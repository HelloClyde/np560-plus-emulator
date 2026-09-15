import unittest

from verify_np560_toolbar_frames import compare, decode_expected


class ToolbarOracleTests(unittest.TestCase):
    def test_exact_gray_mapping(self):
        resource = bytes.fromhex("010400000000f0001600") + b"\x0f" * 2640
        expected = decode_expected(resource)
        self.assertEqual(expected, b"\x00\x1e" * 2640)
        frame = expected + bytes(240 * (120 - 22))
        self.assertTrue(compare(frame, expected)["passed"])
        bad = bytearray(frame)
        bad[240 + 3] ^= 2
        result = compare(bad, expected)
        self.assertFalse(result["passed"])
        self.assertEqual(result["mismatch_pixels"], 1)
        self.assertEqual(result["first_mismatch_xy"], [3, 1])
        # No false pass by fitting a shifted / differently selected golden.
        self.assertFalse(compare(frame[1:] + frame[:1], expected)["passed"])

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "header"):
            decode_expected(bytes(2650))
        with self.assertRaisesRegex(ValueError, "length"):
            decode_expected(bytes(2640))
        with self.assertRaisesRegex(ValueError, "dimensions"):
            compare(bytes(5280), bytes(5280))


if __name__ == "__main__":
    unittest.main()
