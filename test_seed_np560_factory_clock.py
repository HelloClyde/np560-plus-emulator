#!/usr/bin/env python3

from __future__ import annotations

import mmap
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_np560_ecc_checkpoint import sector_descriptor
from seed_np560_factory_bootstrap import physical_column
from seed_np560_factory_clock import (
    FACTORY_CLOCK_ADDRESS,
    FACTORY_CLOCK_SECTOR,
    encode_factory_clock,
    seed_factory_clock,
)
from seed_np560_factory_selector import (
    DATA_SIZE,
    ECC_OFFSET,
    FACTORY_PHYSICAL_PAGE,
    HEADER_SIZE,
    PAGE_DATA,
    PAGE_OOB,
    PROGRAMMED_PAGE_MARKER_OFFSET,
)
from test_seed_np560_factory_bootstrap import make_sparse_checkpoint


class FactoryClockSeedTest(unittest.TestCase):
    def test_encodes_layout_consumed_by_clock_validator(self) -> None:
        self.assertEqual(
            encode_factory_clock(datetime(2026, 8, 26, 12, 34, 56)),
            bytes.fromhex("ea0708001a000c0022003800"),
        )

    def test_seeds_bus_lane_ecc_marker_and_invalidates_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "sparse.nand"
            page_data, page_oob = make_sparse_checkpoint(checkpoint)
            value = datetime(2026, 8, 26, 12, 34, 56)
            with checkpoint.open("r+b") as target:
                image = mmap.mmap(target.fileno(), 0)
                try:
                    encoded = seed_factory_clock(image, value)
                    for index, byte in enumerate(encoded):
                        self.assertEqual(
                            image[
                                page_data
                                + physical_column(FACTORY_CLOCK_ADDRESS + index)
                            ],
                            byte,
                        )
                    sector_offset = page_data + FACTORY_CLOCK_SECTOR * 512
                    ecc_offset = ECC_OFFSET + FACTORY_CLOCK_SECTOR * 8
                    self.assertEqual(
                        image[page_oob + ecc_offset : page_oob + ecc_offset + 8],
                        sector_descriptor(image, sector_offset),
                    )
                    self.assertEqual(
                        image[page_oob + PROGRAMMED_PAGE_MARKER_OFFSET], 0x00
                    )
                    self.assertEqual(image[48:56], b"\x00" * 8)
                finally:
                    image.close()

    def test_rejects_existing_different_clock_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "sparse.nand"
            page_data, _ = make_sparse_checkpoint(checkpoint)
            with checkpoint.open("r+b") as target:
                image = mmap.mmap(target.fileno(), 0)
                try:
                    image[
                        page_data + physical_column(FACTORY_CLOCK_ADDRESS)
                    ] = 0x12
                    with self.assertRaisesRegex(ValueError, "use --force"):
                        seed_factory_clock(image, datetime(2026, 8, 26))
                finally:
                    image.close()

    def test_rejects_year_outside_firmware_bounds(self) -> None:
        with self.assertRaisesRegex(ValueError, "1901..2100"):
            encode_factory_clock(datetime(1900, 1, 1))


if __name__ == "__main__":
    unittest.main()
