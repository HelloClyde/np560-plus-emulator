from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import struct
import unittest

from scripts import ensure_np560_fat16_directories as ensure
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
        self.fats = [bytearray(64), bytearray(64)]
        for table in self.fats:
            struct.pack_into("<H", table, 0, 0xFFF8)
            struct.pack_into("<H", table, 2, 0xFFFF)
        self.sectors: dict[int, bytes] = {}
        self.finalized = 0

    def root_bytes(self) -> bytearray:
        return bytearray(self.root)

    def write_root_bytes(self, root: bytes) -> None:
        self.root[:] = root

    def read_fat(self, copy_index: int = 0) -> bytearray:
        return bytearray(self.fats[copy_index])

    def write_fat(self, table: bytes, copy_index: int) -> None:
        self.fats[copy_index][:] = table

    def write_sector(self, lba: int, logical: bytes) -> None:
        self.sectors[lba] = bytes(logical)

    def finalize_allocations(self) -> None:
        self.finalized += 1


class EnsureFat16DirectoryTests(unittest.TestCase):
    def test_creates_guest_format_empty_directory_in_both_fats(self) -> None:
        volume = FakeVolume()
        report = ensure.ensure_directories(volume, ["同步学习"])

        self.assertEqual(report, [{
            "directory": "同步学习",
            "short_name_hex": "CD AC B2 BD D1 A7 CF B0 20 20 20",
            "cluster": 2,
            "created": True,
        }])
        self.assertEqual(volume.root[:11], fat.encode_short_name("同步学习"))
        self.assertEqual(volume.root[11], 0x10)
        self.assertEqual(struct.unpack_from("<H", volume.root, 26)[0], 2)
        for table in volume.fats:
            self.assertEqual(struct.unpack_from("<H", table, 4)[0], 0xFFFF)
        directory = volume.sectors[100] + volume.sectors[101]
        self.assertEqual(directory[:32], fat.dot_entry(".", 2))
        self.assertEqual(directory[32:64], fat.dot_entry("..", 0))
        self.assertEqual(volume.finalized, 1)

    def test_existing_directory_is_preserved(self) -> None:
        volume = FakeVolume()
        name = fat.encode_short_name("同步学习")
        volume.root[:32] = fat.directory_entry(name, 0x10, 7)

        report = ensure.ensure_directories(volume, ["同步学习"])

        self.assertEqual(report[0]["cluster"], 7)
        self.assertFalse(report[0]["created"])
        self.assertEqual(volume.sectors, {})

    def test_rejects_duplicate_request(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicates"):
            ensure.ensure_directories(
                FakeVolume(), ["同步学习", "同步学习"],
            )


if __name__ == "__main__":
    unittest.main()
