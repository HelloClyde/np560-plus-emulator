import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verify_np560_npe_dac_reference import compare_changes


class NPEDACReferenceTests(unittest.TestCase):
    def test_repeated_samples_and_presentation_delay(self):
        result = compare_changes([0, 4, 4, -3, 32767],
                                 [0, 0, 8, 8, 8, 8, -6, -6, 32767, 32767, 0],
                                 gain=2)
        self.assertEqual(result["matching_prefix_runs"], 3)
        self.assertEqual(result["matching_prefix_reference_samples"], 4)
        self.assertIsNone(result["first_mismatch"])

    def test_reports_value_mismatch(self):
        result = compare_changes([0, 1, 2, 3], [0, 2, 2, 7, 7, 0], gain=2)
        self.assertEqual(result["matching_prefix_runs"], 1)
        self.assertEqual(result["first_mismatch"], {"expected": 4, "actual": 7})


if __name__ == "__main__":
    unittest.main()
