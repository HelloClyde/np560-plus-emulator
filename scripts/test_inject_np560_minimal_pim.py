from __future__ import annotations

import struct
import unittest

from scripts import inject_np560_minimal_pim as pim
from scripts import inject_np560_npe_fat16 as fat


class FakeVolume:
    def __init__(self) -> None:
        self.layout = {
            "fat_count": 2,
            "cluster_bytes": 1024,
            "sectors_per_cluster": 2,
            "data_start": 100,
        }
        self.root = bytearray(1024)
        directory_name = fat.encode_short_name(pim.DEFAULT_DIRECTORY)
        self.root[:32] = fat.directory_entry(directory_name, 0x10, 2)
        self.fats = [bytearray(128), bytearray(128)]
        for table in self.fats:
            struct.pack_into("<H", table, 0, 0xFFF8)
            struct.pack_into("<H", table, 2, 0xFFFF)
            struct.pack_into("<H", table, 4, 0xFFFF)
        directory = bytearray(1024)
        directory[:32] = fat.dot_entry(".", 2)
        directory[32:64] = fat.dot_entry("..", 0)
        self.sectors = {
            100: bytes(directory[:512]),
            101: bytes(directory[512:]),
        }
        self.finalized = 0

    def root_bytes(self) -> bytearray:
        return bytearray(self.root)

    def read_sector(self, lba: int) -> bytes:
        return self.sectors.get(lba, b"\xFF" * fat.SECTOR_SIZE)

    def write_sector(self, lba: int, logical: bytes) -> None:
        self.sectors[lba] = bytes(logical)

    def read_fat(self, copy_index: int = 0) -> bytearray:
        return bytearray(self.fats[copy_index])

    def write_fat(self, table: bytes, copy_index: int) -> None:
        self.fats[copy_index][:] = table

    def finalize_allocations(self) -> None:
        self.finalized += 1


class MinimalPimTests(unittest.TestCase):
    def test_default_directory_matches_captured_gbk_path(self) -> None:
        self.assertEqual(pim.DEFAULT_DIRECTORY, "我的邮件")
        self.assertEqual(
            fat.encode_short_name(pim.DEFAULT_DIRECTORY),
            bytes.fromhex("CE D2 B5 C4 D3 CA BC FE 20 20 20"),
        )

    def test_recovered_empty_pim_layout_is_exact(self) -> None:
        self.assertEqual(len(pim.MINIMAL_PIM_HEADER), 0x40)
        self.assertEqual(len(pim.MINIMAL_PIM), 0x4A)
        self.assertEqual(pim.MINIMAL_PIM[:8], b"NOAHPIM\0")
        self.assertEqual(pim.MINIMAL_PIM[8:13], b"V1.0\0")
        self.assertEqual(pim.MINIMAL_PIM[0x10:0x12], b"\x00\x40")
        self.assertEqual(pim.MINIMAL_PIM[0x3C:0x40], b"\x55\xAA\x55\xAA")
        self.assertEqual(pim.MINIMAL_PIM[-2:], b"\x00\x4A")

    def test_injects_file_and_preserves_guest_dot_records(self) -> None:
        volume = FakeVolume()
        report = pim.inject_minimal_pim(volume)

        self.assertTrue(report["created"])
        self.assertEqual(report["file_size"], 0x4A)
        self.assertEqual(report["file_first_cluster"], 3)
        for table in volume.fats:
            self.assertEqual(struct.unpack_from("<H", table, 6)[0], 0xFFFF)
        directory = volume.sectors[100] + volume.sectors[101]
        self.assertEqual(directory[:32], fat.dot_entry(".", 2))
        self.assertEqual(directory[32:64], fat.dot_entry("..", 0))
        self.assertEqual(directory[64:75], b"NMINBOX PIM")
        file_data = volume.sectors[102] + volume.sectors[103]
        self.assertEqual(file_data[:0x4A], pim.MINIMAL_PIM)
        self.assertEqual(volume.finalized, 1)

    def test_second_injection_is_idempotent(self) -> None:
        volume = FakeVolume()
        pim.inject_minimal_pim(volume)
        report = pim.inject_minimal_pim(volume)

        self.assertFalse(report["created"])
        self.assertTrue(report["byte_exact"])

    def test_lowercase_extension_ab_preserves_literal_path_case(self) -> None:
        volume = FakeVolume()
        report = pim.inject_minimal_pim(
            volume, lowercase_extension=True,
        )

        self.assertEqual(report["extension_case"], "lower")
        directory = volume.sectors[100] + volume.sectors[101]
        self.assertEqual(directory[64:75], b"NMINBOX pim")

    def test_file_first_ab_removes_only_expected_dot_records(self) -> None:
        volume = FakeVolume()
        report = pim.inject_minimal_pim(
            volume, lowercase_extension=True, omit_dot_entries=True,
        )

        self.assertEqual(report["directory_layout"], "diagnostic-file-first")
        directory = volume.sectors[100] + volume.sectors[101]
        self.assertEqual(directory[:11], b"NMINBOX pim")
        self.assertEqual(directory[32], 0)


if __name__ == "__main__":
    unittest.main()
