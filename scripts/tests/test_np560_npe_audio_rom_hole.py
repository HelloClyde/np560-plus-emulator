import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe_np560_npe_audio_rom_hole import ADDRESS, HOLE, RETS, make_probe


class AudioRomHoleProbeTests(unittest.TestCase):
    def test_only_acd8_changes(self):
        source = bytes([0x55]) * ADDRESS + HOLE + bytes([0xaa]) * 32
        result = make_probe(source)
        self.assertEqual(result[:ADDRESS], source[:ADDRESS])
        self.assertEqual(result[ADDRESS:ADDRESS + 2], RETS)
        self.assertEqual(result[ADDRESS + 2:], source[ADDRESS + 2:])

    def test_refuses_non_hole(self):
        source = bytes([0]) * (ADDRESS + 2)
        with self.assertRaisesRegex(ValueError, "not the expected"):
            make_probe(source)


if __name__ == "__main__":
    unittest.main()
