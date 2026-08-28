#!/usr/bin/env python3
"""Seed the NP560+ factory clock record in a NAND checkpoint copy.

The recovered application reads twelve logical bytes at ``10:D01F`` through
the normal NAND-backed mask-resource reader.  The factory bootstrap image has
those bytes erased (all ``FF``), which deliberately sends the firmware to its
first-boot year/month/day modal before it can attach the main resource file.

This utility writes a deterministic guest-visible clock record, refreshes the
affected NAND sector ECC, and invalidates the checkpoint hashes.  It does not
intercept the clock reader or replace a ROM service.  Run
``np560_checkpoint_rehash`` on the output before booting it.
"""

from __future__ import annotations

import argparse
import mmap
import shutil
from datetime import datetime
from pathlib import Path

from analyze_np560_ecc_checkpoint import sector_descriptor
from seed_np560_factory_bootstrap import physical_column
from seed_np560_factory_selector import (
    ECC_OFFSET,
    FACTORY_PHYSICAL_PAGE,
    HEADER_SIZE,
    PAGE_DATA,
    PAGE_OOB,
    PROGRAMMED_PAGE_MARKER_OFFSET,
    _validate_geometry,
)


FACTORY_CLOCK_ADDRESS = 0x10D01F
FACTORY_CLOCK_SIZE = 12
FACTORY_CLOCK_COLUMNS = tuple(
    physical_column(FACTORY_CLOCK_ADDRESS + index)
    for index in range(FACTORY_CLOCK_SIZE)
)
FACTORY_CLOCK_SECTOR = min(FACTORY_CLOCK_COLUMNS) // 512


def encode_factory_clock(value: datetime) -> bytes:
    """Return the exact sparse-byte clock layout consumed by 4C:4D94."""
    if not 1901 <= value.year <= 2100:
        raise ValueError("factory clock year must be in 1901..2100")
    return bytes((
        value.year & 0xFF,
        value.year >> 8,
        value.month,
        0,
        value.day,
        0,
        value.hour,
        0,
        value.minute,
        0,
        value.second,
        0,
    ))


def seed_factory_clock(
    image: mmap.mmap,
    value: datetime,
    *,
    force: bool = False,
) -> bytes:
    """Patch the factory clock bytes and the containing sector descriptor."""
    encoded = encode_factory_clock(value)
    data_size, _ = _validate_geometry(image)
    data_base = HEADER_SIZE
    oob_base = data_base + data_size
    page_data_offset = data_base + FACTORY_PHYSICAL_PAGE * PAGE_DATA
    page_oob_offset = oob_base + FACTORY_PHYSICAL_PAGE * PAGE_OOB

    for index, byte in enumerate(encoded):
        offset = page_data_offset + physical_column(FACTORY_CLOCK_ADDRESS + index)
        existing = image[offset]
        if not force and existing not in (0xFF, byte):
            raise ValueError(
                f"factory clock byte D{FACTORY_CLOCK_ADDRESS + index:03X} "
                f"already contains 0x{existing:02X}; use --force"
            )
        image[offset] = byte

    sector_offset = page_data_offset + FACTORY_CLOCK_SECTOR * 512
    ecc_offset = ECC_OFFSET + FACTORY_CLOCK_SECTOR * 8
    image[page_oob_offset + ecc_offset : page_oob_offset + ecc_offset + 8] = (
        sector_descriptor(image, sector_offset)
    )
    image[page_oob_offset + PROGRAMMED_PAGE_MARKER_OFFSET] = 0x00

    # Prevent a partially patched file from passing checkpoint validation.
    image[48:56] = b"\x00" * 8
    image.flush()
    return encoded


def parse_clock(text: str) -> datetime:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "clock must use YYYY-MM-DDTHH:MM:SS"
        ) from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--clock", type=parse_clock, required=True)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace a previously seeded clock value",
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
            encoded = seed_factory_clock(image, args.clock, force=args.force)
        finally:
            image.close()

    print(
        f"CLOCK={args.clock.isoformat()} BYTES={encoded.hex()} "
        f"LOGICAL=0x{FACTORY_CLOCK_ADDRESS:06X} "
        f"PHYSICAL_PAGE=0x{FACTORY_PHYSICAL_PAGE:X} "
        f"OUTPUT={destination} REHASH_REQUIRED=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
