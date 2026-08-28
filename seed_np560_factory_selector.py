#!/usr/bin/env python3
"""Seed the NP560+ factory selector byte in a NAND checkpoint.

The V3.80 updater starts programming at logical byte 0x110000.  The resident
application reads one byte immediately before that payload, at 10:D072, to
select the product variant.  Real hardware therefore supplies this value from
factory-reserved NAND; updater-only checkpoints leave the corresponding page
erased.

This utility patches that one byte in the recovered FTL mapping and emits the
same 51:C1A4 ECC descriptor used by the guest.  It deliberately does not
recompute the checkpoint FNV-1a hashes; run np560_checkpoint_rehash afterwards.
"""

from __future__ import annotations

import argparse
import mmap
import shutil
import struct
from pathlib import Path

from analyze_np560_ecc_checkpoint import sector_descriptor


CHECKPOINT_MAGIC = b"NP560N1\0"
HEADER_SIZE = 64
PAGE_DATA = 2048
PAGE_OOB = 64
PAGES_PER_BLOCK = 64
BLOCKS = 4096
DATA_SIZE = PAGE_DATA * PAGES_PER_BLOCK * BLOCKS
OOB_SIZE = PAGE_OOB * PAGES_PER_BLOCK * BLOCKS

# The FTL table maps logical block 0xE9B (logical data bytes
# 0x10C000..0x10FFFF) to physical block 0xC02.  Address 10:D072 is page 0x1A
# within that block and byte 0x72 within the page.
FACTORY_LOGICAL_ADDRESS = 0x10D072
FACTORY_PHYSICAL_BLOCK = 0xC02
FACTORY_BLOCK_PAGE = 0x1A
FACTORY_PHYSICAL_PAGE = FACTORY_PHYSICAL_BLOCK * PAGES_PER_BLOCK + FACTORY_BLOCK_PAGE
FACTORY_LOGICAL_COLUMN = FACTORY_LOGICAL_ADDRESS & (PAGE_DATA - 1)

# External byte accesses on the 16-bit NAND data bus observe A0 inverted.
FACTORY_PHYSICAL_COLUMN = FACTORY_LOGICAL_COLUMN ^ 1
FACTORY_SECTOR = FACTORY_PHYSICAL_COLUMN // 512
ECC_OFFSET = (22, 30, 38, 46)[FACTORY_SECTOR]
PROGRAMMED_PAGE_MARKER_OFFSET = 55


def _validate_geometry(image: mmap.mmap) -> tuple[int, int]:
    if len(image) < HEADER_SIZE or image[:8] != CHECKPOINT_MAGIC:
        raise ValueError("not an NP560 NAND checkpoint")
    version, header_size, page_data, page_oob, block_pages, blocks = (
        struct.unpack_from("<6I", image, 8)
    )
    data_size, oob_size = struct.unpack_from("<2Q", image, 32)
    expected = HEADER_SIZE + data_size + oob_size
    if (
        version != 1
        or header_size != HEADER_SIZE
        or page_data != PAGE_DATA
        or page_oob != PAGE_OOB
        or block_pages != PAGES_PER_BLOCK
        or blocks != BLOCKS
        or data_size != DATA_SIZE
        or oob_size != OOB_SIZE
        or len(image) != expected
    ):
        raise ValueError("incompatible NP560 NAND geometry or file size")
    return data_size, oob_size


def seed_selector(image: mmap.mmap, selector: int, force: bool = False) -> None:
    """Patch the selector byte and sector-0 ECC in an open checkpoint map."""
    if not 0 <= selector <= 0xFF:
        raise ValueError("selector must fit in one byte")
    data_size, _ = _validate_geometry(image)
    data_base = HEADER_SIZE
    oob_base = data_base + data_size
    page_data_offset = data_base + FACTORY_PHYSICAL_PAGE * PAGE_DATA
    page_oob_offset = oob_base + FACTORY_PHYSICAL_PAGE * PAGE_OOB
    page = image[page_data_offset : page_data_offset + PAGE_DATA]
    spare = image[page_oob_offset : page_oob_offset + PAGE_OOB]

    expected_existing = {0xFF, selector}
    existing = page[FACTORY_PHYSICAL_COLUMN]
    descriptor = spare[ECC_OFFSET : ECC_OFFSET + 8]
    marker = spare[PROGRAMMED_PAGE_MARKER_OFFSET]
    if not force:
        if existing not in expected_existing:
            raise ValueError(
                f"factory selector already contains 0x{existing:02X}; use --force"
            )
        if any(
            byte != 0xFF
            for index, byte in enumerate(page)
            if index != FACTORY_PHYSICAL_COLUMN
        ):
            raise ValueError("factory selector page contains other data; use --force")
        if descriptor != b"\xFF" * 8 and existing == 0xFF:
            raise ValueError("factory selector page already has an ECC descriptor")
        allowed_oob = set(range(ECC_OFFSET, ECC_OFFSET + 8)) | {
            PROGRAMMED_PAGE_MARKER_OFFSET
        }
        if any(
            byte != 0xFF
            for index, byte in enumerate(spare)
            if index not in allowed_oob
        ):
            raise ValueError("factory selector page contains other OOB data; use --force")
        if marker not in (0xFF, 0x00):
            raise ValueError("unexpected programmed-page marker; use --force")

    image[page_data_offset + FACTORY_PHYSICAL_COLUMN] = selector
    sector_offset = page_data_offset + FACTORY_SECTOR * 512
    image[page_oob_offset + ECC_OFFSET : page_oob_offset + ECC_OFFSET + 8] = (
        sector_descriptor(image, sector_offset)
    )
    image[page_oob_offset + PROGRAMMED_PAGE_MARKER_OFFSET] = 0x00

    # Prevent a partially patched file from passing checkpoint validation.
    image[48:56] = b"\x00" * 8
    image.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--selector",
        type=lambda value: int(value, 0),
        required=True,
        help="factory product selector (for example 0x0B)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing seeded selector in the destination",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    destination = args.destination.resolve()
    if source != destination:
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    elif not destination.exists():
        raise FileNotFoundError(destination)

    with destination.open("r+b") as target:
        image = mmap.mmap(target.fileno(), 0)
        try:
            seed_selector(image, args.selector, force=args.force)
        finally:
            image.close()

    print(
        f"SELECTOR=0x{args.selector:02X} LOGICAL=0x{FACTORY_LOGICAL_ADDRESS:06X} "
        f"PHYSICAL_PAGE=0x{FACTORY_PHYSICAL_PAGE:X} "
        f"PHYSICAL_COLUMN=0x{FACTORY_PHYSICAL_COLUMN:X} "
        f"OUTPUT={destination} REHASH_REQUIRED=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
