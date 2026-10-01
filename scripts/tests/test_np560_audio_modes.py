"""Original data extraction guards, not EQ processing or UI execution tests."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_np560_audio_modes import extract


class AudioModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (Path(__file__).resolve().parents[2] /
                   'NP560+V3.80版系统升级程序' / 'NP560.PRG').read_bytes()

    def test_byte_lanes_and_nonsequential_selection(self):
        report = extract(self.raw)
        self.assertEqual(report['menu_index_to_mode'], [0,1,9,6,4,10,5,11,13,3,8,2,7,12])
        row = report['menu_rows'][2]
        self.assertEqual(row['mode'], 9)
        self.assertEqual(row['table_address'], 0x305a06)
        self.assertEqual(row['coefficient_words'][:3], [30152,38698,42055])
        self.assertFalse(report['frequency_mapping_verified'])

    def test_disabled_mode_still_selects_first_table(self):
        rows = extract(self.raw)['menu_rows']
        self.assertEqual(rows[0]['coefficient_words'], rows[1]['coefficient_words'])
        self.assertFalse(rows[0]['enabled'])
        self.assertTrue(rows[1]['enabled'])

    def test_rejects_unpinned_image(self):
        with self.assertRaises(ValueError):
            extract(self.raw[:-1])


if __name__ == '__main__':
    unittest.main()
