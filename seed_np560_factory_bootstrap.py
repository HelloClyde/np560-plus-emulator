#!/usr/bin/env python3
"""Seed the inferred NP560+ factory bootstrap record in a NAND checkpoint.

The V3.80 updater starts at logical byte 0x110000, so it cannot recreate the
factory-reserved bytes immediately before the payload.  Exact guest code reads
an enable byte at 10:D03F, a 50-byte NUL-terminated path at 10:D040, and a
product selector at 10:D072.  The recovered FTL maps this range to physical
block C02, page 1A.

This utility provisions those bytes in a *copy* of a checkpoint and emits the
same sector ECC descriptor as the guest.  The path and selector remain explicit
command-line inputs because no true-device factory dump is available.  It does
not intercept guest file calls or replace any ROM service.  Run
np560_checkpoint_rehash on the result before booting it.
"""

from __future__ import annotations

import argparse
import mmap
import shutil
from pathlib import Path

from analyze_np560_ecc_checkpoint import sector_descriptor
from seed_np560_factory_selector import (
    ECC_OFFSET,
    FACTORY_PHYSICAL_PAGE,
    HEADER_SIZE,
    PAGE_DATA,
    PAGE_OOB,
    PROGRAMMED_PAGE_MARKER_OFFSET,
    _validate_geometry,
)


RESOURCE_FLAG_ADDRESS = 0x10D03F
RESOURCE_PATH_ADDRESS = 0x10D040
RESOURCE_PATH_SIZE = 0x32
FACTORY_SELECTOR_ADDRESS = 0x10D072


def physical_column(logical_address: int) -> int:
    """Map a logical byte address through the external NAND A0 inversion."""
    return (logical_address & (PAGE_DATA - 1)) ^ 1


RESOURCE_FLAG_COLUMN = physical_column(RESOURCE_FLAG_ADDRESS)
FACTORY_SELECTOR_COLUMN = physical_column(FACTORY_SELECTOR_ADDRESS)
FACTORY_SECTOR = RESOURCE_FLAG_COLUMN // 512


def _logical_record(path: str, selector: int, encoding: str) -> dict[int, int]:
    if not 0 <= selector <= 0xFF:
        raise ValueError("selector must fit in one byte")
    encoded = path.encode(encoding)
    if b"\0" in encoded:
        raise ValueError("resource path contains an embedded NUL")
    if len(encoded) >= RESOURCE_PATH_SIZE:
        raise ValueError(
            f"encoded path needs {len(encoded) + 1} bytes including NUL; "
            f"field holds {RESOURCE_PATH_SIZE}"
        )

    record = {RESOURCE_FLAG_ADDRESS: 1, FACTORY_SELECTOR_ADDRESS: selector}
    padded_path = encoded + b"\0" * (RESOURCE_PATH_SIZE - len(encoded))
    record.update({
        RESOURCE_PATH_ADDRESS + index: value
        for index, value in enumerate(padded_path)
    })
    return record


def seed_factory_bootstrap(
    image: mmap.mmap,
    path: str,
    selector: int,
    *,
    encoding: str = "gb18030",
    force: bool = False,
) -> bytes:
    """Patch the factory flag/path/selector and sector-0 ECC."""
    record = _logical_record(path, selector, encoding)
    encoded = path.encode(encoding)
    data_size, _ = _validate_geometry(image)
    data_base = HEADER_SIZE
    oob_base = data_base + data_size
    page_data_offset = data_base + FACTORY_PHYSICAL_PAGE * PAGE_DATA
    page_oob_offset = oob_base + FACTORY_PHYSICAL_PAGE * PAGE_OOB
    page = image[page_data_offset : page_data_offset + PAGE_DATA]
    spare = image[page_oob_offset : page_oob_offset + PAGE_OOB]

    expected_columns = {
        physical_column(address): value for address, value in record.items()
    }
    ecc_offset = ECC_OFFSET
    if not force:
        for column, existing in enumerate(page):
            if column in expected_columns:
                if existing not in (0xFF, expected_columns[column]):
                    logical = column ^ 1
                    raise ValueError(
                        f"factory page byte D{logical:03X} already contains "
                        f"0x{existing:02X}; use --force"
                    )
            elif existing != 0xFF:
                raise ValueError("factory bootstrap page contains other data; use --force")

        allowed_oob = set(range(ecc_offset, ecc_offset + 8)) | {
            PROGRAMMED_PAGE_MARKER_OFFSET
        }
        if any(
            value != 0xFF
            for index, value in enumerate(spare)
            if index not in allowed_oob
        ):
            raise ValueError("factory bootstrap page contains other OOB data; use --force")
        if spare[PROGRAMMED_PAGE_MARKER_OFFSET] not in (0xFF, 0x00):
            raise ValueError("unexpected programmed-page marker; use --force")

    for address, value in record.items():
        image[page_data_offset + physical_column(address)] = value

    sector_offset = page_data_offset + FACTORY_SECTOR * 512
    image[page_oob_offset + ecc_offset : page_oob_offset + ecc_offset + 8] = (
        sector_descriptor(image, sector_offset)
    )
    image[page_oob_offset + PROGRAMMED_PAGE_MARKER_OFFSET] = 0x00

    # Prevent a partially patched file from passing checkpoint validation.
    image[48:56] = b"\x00" * 8
    image.flush()
    return encoded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--path", required=True, help="guest resource path")
    parser.add_argument("--encoding", default="gb18030")
    parser.add_argument(
        "--selector",
        type=lambda value: int(value, 0),
        required=True,
        help="factory product selector",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace other factory-page data in the destination",
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
            encoded = seed_factory_bootstrap(
                image,
                args.path,
                args.selector,
                encoding=args.encoding,
                force=args.force,
            )
        finally:
            image.close()

    print(
        f"FLAG=1@0x{RESOURCE_FLAG_ADDRESS:06X} "
        f"PATH={encoded!r}@0x{RESOURCE_PATH_ADDRESS:06X} "
        f"SELECTOR=0x{args.selector:02X}@0x{FACTORY_SELECTOR_ADDRESS:06X} "
        f"PHYSICAL_PAGE=0x{FACTORY_PHYSICAL_PAGE:X} "
        f"OUTPUT={destination} REHASH_REQUIRED=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
