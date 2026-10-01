"""Check ELF load translation independently of ASLR and nonzero segment offsets."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_np560_host_samples import elf_address, parse_maps


class Symbols(unittest.TestCase):
    def test_nonidentity_file_virtual_address(self):
        segments = [dict(offset=0x2000, vaddr=0x402000, filesz=0x3000)]
        self.assertEqual(elf_address(0x2345, segments), 0x402345)
        for offset in (0x1fff, 0x5000):
            with self.assertRaises(ValueError):
                elf_address(offset, segments)

    def test_ambiguous_segment_rejected(self):
        with self.assertRaises(ValueError):
            elf_address(3, [dict(offset=0, vaddr=0, filesz=4),
                            dict(offset=0, vaddr=8, filesz=4)])

    def test_maps_preserve_paths_and_anonymous(self):
        maps = parse_maps('700000-701000 r-xp 00002000 00:00 12 /tmp/a b\n'
                          '800000-801000 rwxp 00000000 00:00 0\n')
        self.assertEqual(maps[0]['path'], '/tmp/a b')
        self.assertEqual(maps[0]['offset'], 0x2000)
        self.assertEqual(maps[1]['path'], '')


if __name__ == '__main__':
    unittest.main()
