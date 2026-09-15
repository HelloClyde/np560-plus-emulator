
# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import unittest

from inspect_np560_media_sectors import (
    describe_sector,
    fat_bpb,
    mbr_partitions,
    swap_adjacent_bytes,
)


class MediaSectorInspectionTests(unittest.TestCase):
    def test_adjacent_byte_swap_round_trips(self) -> None:
        source = bytes(range(32))
        self.assertEqual(swap_adjacent_bytes(swap_adjacent_bytes(source)), source)

    def test_vendor_partition_table_is_recognized(self) -> None:
        sector = bytearray(512)
        entry = 0x1BE
        sector[entry] = 0x80
        sector[entry + 4] = 0x01
        sector[entry + 8:entry + 12] = (32).to_bytes(4, "little")
        sector[entry + 12:entry + 16] = (907744).to_bytes(4, "little")
        sector[510:512] = b"\x55\xAA"

        self.assertEqual(
            mbr_partitions(bytes(sector)),
            [{
                "index": 0,
                "boot": 0x80,
                "type": 0x01,
                "start_lba": 32,
                "sectors": 907744,
            }],
        )
        self.assertEqual(describe_sector(bytes(sector))[0], "MBR")

    def test_vendor_fat16_bpb_is_recognized(self) -> None:
        sector = bytearray(512)
        sector[0x0B:0x0D] = (512).to_bytes(2, "little")
        sector[0x0D] = 16
        sector[0x0E:0x10] = (1).to_bytes(2, "little")
        sector[0x10] = 2
        sector[0x11:0x13] = (512).to_bytes(2, "little")
        sector[0x16:0x18] = (222).to_bytes(2, "little")
        sector[0x20:0x24] = (907744).to_bytes(4, "little")
        sector[510:512] = b"\x55\xAA"

        self.assertEqual(
            fat_bpb(bytes(sector)),
            {
                "bytes_per_sector": 512,
                "sectors_per_cluster": 16,
                "reserved_sectors": 1,
                "fat_count": 2,
                "root_entries": 512,
                "total_sectors": 907744,
                "sectors_per_fat_16": 222,
                "hidden_sectors": 0,
            },
        )
        self.assertEqual(describe_sector(bytes(sector))[0], "FAT_BPB")

    def test_random_signature_is_not_enough(self) -> None:
        sector = bytearray(512)
        sector[510:512] = b"\x55\xAA"
        self.assertIsNone(describe_sector(bytes(sector)))


if __name__ == "__main__":
    unittest.main()
