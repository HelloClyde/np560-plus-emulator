#!/usr/bin/env python3

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import mmap
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_np560_ecc_checkpoint import sector_descriptor
from seed_np560_factory_bootstrap import (
    FACTORY_SECTOR,
    FACTORY_SELECTOR_ADDRESS,
    RESOURCE_FLAG_ADDRESS,
    RESOURCE_PATH_ADDRESS,
    RESOURCE_PATH_SIZE,
    physical_column,
    seed_factory_bootstrap,
)
from seed_np560_factory_selector import (
    BLOCKS,
    CHECKPOINT_MAGIC,
    DATA_SIZE,
    ECC_OFFSET,
    FACTORY_PHYSICAL_PAGE,
    HEADER_SIZE,
    OOB_SIZE,
    PAGE_DATA,
    PAGE_OOB,
    PAGES_PER_BLOCK,
    PROGRAMMED_PAGE_MARKER_OFFSET,
)


def make_sparse_checkpoint(path: Path) -> tuple[int, int]:
    with path.open("w+b") as target:
        target.truncate(HEADER_SIZE + DATA_SIZE + OOB_SIZE)
        header = bytearray(b"\xFF" * HEADER_SIZE)
        header[:8] = CHECKPOINT_MAGIC
        struct.pack_into(
            "<6I2Q2I",
            header,
            8,
            1,
            HEADER_SIZE,
            PAGE_DATA,
            PAGE_OOB,
            PAGES_PER_BLOCK,
            BLOCKS,
            DATA_SIZE,
            OOB_SIZE,
            0x12345678,
            0x9ABCDEF0,
        )
        target.write(header)
        page_data = HEADER_SIZE + FACTORY_PHYSICAL_PAGE * PAGE_DATA
        page_oob = HEADER_SIZE + DATA_SIZE + FACTORY_PHYSICAL_PAGE * PAGE_OOB
        target.seek(page_data)
        target.write(b"\xFF" * PAGE_DATA)
        target.seek(page_oob)
        target.write(b"\xFF" * PAGE_OOB)
    return page_data, page_oob


class FactoryBootstrapSeedTest(unittest.TestCase):
    def test_seeds_logical_record_bus_lane_ecc_and_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "sparse.nand"
            page_data, page_oob = make_sparse_checkpoint(checkpoint)
            with checkpoint.open("r+b") as target:
                image = mmap.mmap(target.fileno(), 0)
                try:
                    path = r"0:\多媒体\lirt.nwf"
                    encoded = seed_factory_bootstrap(image, path, 0x06)
                    self.assertEqual(encoded, path.encode("gb18030"))
                    self.assertEqual(
                        image[page_data + physical_column(RESOURCE_FLAG_ADDRESS)], 1
                    )
                    expected_path = encoded + b"\0" * (RESOURCE_PATH_SIZE - len(encoded))
                    for index, value in enumerate(expected_path):
                        self.assertEqual(
                            image[
                                page_data
                                + physical_column(RESOURCE_PATH_ADDRESS + index)
                            ],
                            value,
                        )
                    self.assertEqual(
                        image[
                            page_data + physical_column(FACTORY_SELECTOR_ADDRESS)
                        ],
                        0x06,
                    )
                    sector_offset = page_data + FACTORY_SECTOR * 512
                    self.assertEqual(
                        image[page_oob + ECC_OFFSET : page_oob + ECC_OFFSET + 8],
                        sector_descriptor(image, sector_offset),
                    )
                    self.assertEqual(
                        image[page_oob + PROGRAMMED_PAGE_MARKER_OFFSET], 0x00
                    )
                    self.assertEqual(image[48:56], b"\x00" * 8)
                finally:
                    image.close()

    def test_rejects_unrelated_factory_page_data_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "sparse.nand"
            page_data, _ = make_sparse_checkpoint(checkpoint)
            with checkpoint.open("r+b") as target:
                image = mmap.mmap(target.fileno(), 0)
                try:
                    image[page_data + 0x180] = 0x12
                    with self.assertRaisesRegex(ValueError, "other data"):
                        seed_factory_bootstrap(image, r"0:\lirt.nwf", 0x06)
                finally:
                    image.close()

    def test_rejects_path_without_room_for_nul(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "sparse.nand"
            make_sparse_checkpoint(checkpoint)
            with checkpoint.open("r+b") as target:
                image = mmap.mmap(target.fileno(), 0)
                try:
                    with self.assertRaisesRegex(ValueError, "including NUL"):
                        seed_factory_bootstrap(
                            image, "x" * RESOURCE_PATH_SIZE, 0x06, encoding="ascii"
                        )
                finally:
                    image.close()


if __name__ == "__main__":
    unittest.main()
