from __future__ import annotations

import struct
import unittest

from scripts import inject_np560_npe_fat16 as fat


class NpeFat16ImportTests(unittest.TestCase):
    def test_logical_sector_mapping_matches_recovered_factory_locations(self) -> None:
        self.assertEqual(fat.logical_block_and_sector(1), (0, 0x21))
        self.assertEqual(fat.logical_block_and_sector(223), (0, 0xFF))
        self.assertEqual(fat.logical_block_and_sector(445), (1, 0xDD))
        self.assertEqual(fat.logical_block_and_sector(493), (2, 0x0D))

    def test_chinese_directory_and_game_fit_dbcs_short_names(self) -> None:
        self.assertEqual(
            fat.encode_short_name("应用程序"),
            "应用程序".encode("gb18030") + b"   ",
        )
        self.assertEqual(
            fat.encode_short_name("英雄传奇", "npe"),
            "英雄传奇".encode("gb18030") + b"NPE",
        )

    def test_directory_entry_pins_attribute_cluster_and_size(self) -> None:
        name = fat.encode_short_name("英雄传奇", "NPE")
        entry = fat.directory_entry(name, 0x20, 6, 2_053_994)
        self.assertEqual(entry[:11], name)
        self.assertEqual(entry[11], 0x20)
        self.assertEqual(struct.unpack_from("<H", entry, 26)[0], 6)
        self.assertEqual(struct.unpack_from("<I", entry, 28)[0], 2_053_994)

    def test_dot_entries_match_guest_created_directory_records(self) -> None:
        current = fat.dot_entry(".", 5)
        parent = fat.dot_entry("..", 0)
        self.assertEqual(current[:11], b".       \x00\x00\x00")
        self.assertEqual(parent[:11], b"..      \x00\x00\x00")
        self.assertEqual(current[11], 0x16)
        self.assertEqual(parent[11], 0x16)
        self.assertEqual(struct.unpack_from("<H", current, 26)[0], 5)
        self.assertEqual(struct.unpack_from("<H", parent, 26)[0], 0)

    def test_parse_recovered_fat16_geometry(self) -> None:
        bpb = bytearray(512)
        bpb[0x0B:0x0D] = (512).to_bytes(2, "little")
        bpb[0x0D] = 16
        bpb[0x0E:0x10] = (1).to_bytes(2, "little")
        bpb[0x10] = 2
        bpb[0x11:0x13] = (512).to_bytes(2, "little")
        bpb[0x16:0x18] = (222).to_bytes(2, "little")
        bpb[0x20:0x24] = (907_744).to_bytes(4, "little")
        bpb[510:512] = b"\x55\xAA"
        layout = fat.parse_bpb(bytes(bpb))
        self.assertEqual(layout["root_start"], 445)
        self.assertEqual(layout["data_start"], 477)
        self.assertEqual(layout["cluster_bytes"], 8192)

    def test_free_cluster_allocator_is_deterministic(self) -> None:
        table = bytearray(32)
        for cluster, value in ((0, 0xFFF8), (1, 0xFFFF), (2, 0xFFFF), (3, 0xFFFF)):
            struct.pack_into("<H", table, cluster * 2, value)
        self.assertEqual(fat._free_clusters(table, 3), [4, 5, 6])

    def test_short_name_rejects_oversize_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit is 8"):
            fat.encode_short_name("应用程序一")
        with self.assertRaisesRegex(ValueError, "three"):
            fat.encode_short_name("GAME", "LONG")

    def test_file_chain_reader_rejects_loops(self) -> None:
        class Volume:
            layout = {
                "data_start": 1,
                "sectors_per_cluster": 1,
            }

            @staticmethod
            def read_sector(_lba: int) -> bytes:
                return b"A" * fat.SECTOR_SIZE

        table = bytearray(16)
        struct.pack_into("<H", table, 2 * 2, 3)
        struct.pack_into("<H", table, 3 * 2, 2)
        with self.assertRaisesRegex(ValueError, "loops"):
            fat._read_file_chain(Volume(), table, 2, fat.SECTOR_SIZE * 3)

    def test_file_chain_reader_requires_eoc_at_declared_end(self) -> None:
        class Volume:
            layout = {
                "data_start": 1,
                "sectors_per_cluster": 1,
            }

            @staticmethod
            def read_sector(_lba: int) -> bytes:
                return b"A" * fat.SECTOR_SIZE

        table = bytearray(16)
        struct.pack_into("<H", table, 2 * 2, 3)
        with self.assertRaisesRegex(ValueError, "continues"):
            fat._read_file_chain(Volume(), table, 2, fat.SECTOR_SIZE)


if __name__ == "__main__":
    unittest.main()
