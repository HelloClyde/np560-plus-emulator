#!/usr/bin/env python3

from __future__ import annotations

import mmap
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_np560_ecc_checkpoint import ECC_OFFSETS, sector_descriptor
from seed_np560_factory_selector import (
    DATA_SIZE,
    HEADER_SIZE,
    PAGE_DATA,
    PAGE_OOB,
    PROGRAMMED_PAGE_MARKER_OFFSET,
)
from seed_np560_factory_userinfo import (
    DIRECTORY_ENTRY_SIZE,
    FAT1_ENTRY_OFFSET,
    FAT1_PHYSICAL_PAGE,
    FAT2_ENTRY_OFFSET,
    FAT2_PHYSICAL_PAGE,
    ROOT_PHYSICAL_PAGE,
    USERINFO_CLUSTER,
    USERINFO_DATA_OFFSET,
    USERINFO_DATA_PHYSICAL_PAGE,
    USERINFO_DATA_SIZE,
    USERINFO_ATTRIBUTE,
    USERINFO_ENTRY_OFFSET,
    USERINFO_FILE_SIZE,
    USERINFO_SHORT_NAME,
    crc16_ccitt,
    factory_userinfo_payload,
    pair_swap,
    seed_factory_userinfo,
    userinfo_directory_entry,
)
from test_seed_np560_factory_bootstrap import make_sparse_checkpoint


class FactoryUserinfoSeedTest(unittest.TestCase):
    def test_builds_complete_fat_83_entry(self) -> None:
        entry = userinfo_directory_entry()
        self.assertEqual(len(entry), DIRECTORY_ENTRY_SIZE)
        self.assertEqual(entry[:11], b"USERINFOSYS")
        self.assertEqual(entry[11], USERINFO_ATTRIBUTE)
        self.assertEqual(entry[12:26], b"\x00" * 14)
        self.assertEqual(struct.unpack_from("<H", entry, 26)[0], USERINFO_CLUSTER)
        self.assertEqual(struct.unpack_from("<I", entry, 28)[0], USERINFO_FILE_SIZE)

    def test_builds_guest_crc_validated_payload(self) -> None:
        payload = factory_userinfo_payload()
        self.assertEqual(len(payload), USERINFO_FILE_SIZE)
        self.assertEqual(payload[:7], b"V1.0  \x00")
        self.assertEqual(
            struct.unpack_from("<H", payload, USERINFO_DATA_SIZE)[0],
            crc16_ccitt(payload[:USERINFO_DATA_SIZE]),
        )

    def test_seeds_logical_slot_ecc_marker_and_invalidates_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "sparse.nand"
            make_sparse_checkpoint(checkpoint)
            page_data = HEADER_SIZE + ROOT_PHYSICAL_PAGE * PAGE_DATA
            page_oob = HEADER_SIZE + DATA_SIZE + ROOT_PHYSICAL_PAGE * PAGE_OOB
            with checkpoint.open("r+b") as target:
                image = mmap.mmap(target.fileno(), 0)
                try:
                    for page in (
                        ROOT_PHYSICAL_PAGE, FAT1_PHYSICAL_PAGE,
                        FAT2_PHYSICAL_PAGE, USERINFO_DATA_PHYSICAL_PAGE,
                    ):
                        data = HEADER_SIZE + page * PAGE_DATA
                        oob = HEADER_SIZE + DATA_SIZE + page * PAGE_OOB
                        image[data:data + PAGE_DATA] = b"\x00" * PAGE_DATA
                        image[oob:oob + PAGE_OOB] = b"\xFF" * PAGE_OOB
                    seed_factory_userinfo(image)
                    logical = pair_swap(
                        image[page_data : page_data + PAGE_DATA]
                    )
                    self.assertEqual(
                        logical[
                            USERINFO_ENTRY_OFFSET :
                            USERINFO_ENTRY_OFFSET + DIRECTORY_ENTRY_SIZE
                        ],
                        userinfo_directory_entry(),
                    )
                    sector = USERINFO_ENTRY_OFFSET // 512
                    descriptor = ECC_OFFSETS[sector]
                    self.assertEqual(
                        image[
                            page_oob + descriptor : page_oob + descriptor + 8
                        ],
                        sector_descriptor(image, page_data + sector * 512),
                    )
                    self.assertEqual(
                        image[page_oob + PROGRAMMED_PAGE_MARKER_OFFSET], 0x00
                    )
                    self.assertEqual(image[48:56], b"\x00" * 8)
                    for page, offset in (
                        (FAT1_PHYSICAL_PAGE, FAT1_ENTRY_OFFSET),
                        (FAT2_PHYSICAL_PAGE, FAT2_ENTRY_OFFSET),
                    ):
                        data = HEADER_SIZE + page * PAGE_DATA
                        fat = pair_swap(image[data:data + PAGE_DATA])
                        self.assertEqual(
                            struct.unpack_from("<H", fat, offset)[0], 0xFFFF
                        )
                    data = HEADER_SIZE + USERINFO_DATA_PHYSICAL_PAGE * PAGE_DATA
                    payload = pair_swap(image[data:data + PAGE_DATA])[
                        USERINFO_DATA_OFFSET:
                        USERINFO_DATA_OFFSET + USERINFO_FILE_SIZE
                    ]
                    self.assertEqual(payload, factory_userinfo_payload())
                finally:
                    image.close()

    def test_rejects_occupied_slot_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "sparse.nand"
            make_sparse_checkpoint(checkpoint)
            page_data = HEADER_SIZE + ROOT_PHYSICAL_PAGE * PAGE_DATA
            with checkpoint.open("r+b") as target:
                image = mmap.mmap(target.fileno(), 0)
                try:
                    for page in (
                        FAT1_PHYSICAL_PAGE, FAT2_PHYSICAL_PAGE,
                        USERINFO_DATA_PHYSICAL_PAGE,
                    ):
                        data = HEADER_SIZE + page * PAGE_DATA
                        image[data:data + PAGE_DATA] = b"\x00" * PAGE_DATA
                    logical = bytearray(b"\x00" * PAGE_DATA)
                    logical[USERINFO_ENTRY_OFFSET] = ord("X")
                    image[page_data : page_data + PAGE_DATA] = pair_swap(logical)
                    with self.assertRaisesRegex(ValueError, "occupied"):
                        seed_factory_userinfo(image)
                finally:
                    image.close()

    def test_short_name_is_exact_eleven_bytes(self) -> None:
        self.assertEqual(USERINFO_SHORT_NAME, b"USERINFOSYS")
        self.assertEqual(len(USERINFO_SHORT_NAME), 11)


if __name__ == "__main__":
    unittest.main()
