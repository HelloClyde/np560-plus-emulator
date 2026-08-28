#!/usr/bin/env python3

from __future__ import annotations

import mmap
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_np560_ecc_checkpoint import sector_descriptor
from seed_np560_factory_selector import (
    BLOCKS,
    CHECKPOINT_MAGIC,
    DATA_SIZE,
    ECC_OFFSET,
    FACTORY_PHYSICAL_COLUMN,
    FACTORY_PHYSICAL_PAGE,
    HEADER_SIZE,
    OOB_SIZE,
    PAGE_DATA,
    PAGE_OOB,
    PAGES_PER_BLOCK,
    PROGRAMMED_PAGE_MARKER_OFFSET,
    seed_selector,
)


class FactorySelectorSeedTest(unittest.TestCase):
    def test_seeds_bus_lane_ecc_and_invalidates_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "sparse.nand"
            with checkpoint.open("w+b") as target:
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
                target.flush()
                image = mmap.mmap(target.fileno(), 0)
                try:
                    seed_selector(image, 0x0B)
                    self.assertEqual(image[page_data + FACTORY_PHYSICAL_COLUMN], 0x0B)
                    self.assertEqual(
                        image[page_oob + ECC_OFFSET : page_oob + ECC_OFFSET + 8],
                        sector_descriptor(image, page_data),
                    )
                    self.assertEqual(
                        image[page_oob + PROGRAMMED_PAGE_MARKER_OFFSET], 0x00
                    )
                    self.assertEqual(image[48:56], b"\x00" * 8)
                finally:
                    image.close()


if __name__ == "__main__":
    unittest.main()
