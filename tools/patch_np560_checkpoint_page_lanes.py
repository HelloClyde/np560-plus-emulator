#!/usr/bin/env python3
"""Pair-swap selected NP560 NAND data pages and refresh their ECC.

This is a narrow diagnostic used to distinguish an incorrectly staged update
payload from a NAND-controller DMA byte-lane bug.  It never edits its source
checkpoint and requires explicit physical page numbers.
"""

from __future__ import annotations

import argparse
import mmap
import shutil
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qemu-dmcu"))

from analyze_np560_ecc_checkpoint import ECC_OFFSETS, ECC_SIGNATURE, sector_descriptor


CHECKPOINT_MAGIC = b"NP560N1\0"
HEADER_SIZE = 64
PAGE_DATA = 2048
PAGE_OOB = 64


def parse_page(value: str) -> int:
    page = int(value, 0)
    if page < 0:
        raise argparse.ArgumentTypeError("page must be non-negative")
    return page


def patch_pages(source: Path, destination: Path, pages: list[int]) -> tuple[int, int]:
    if source.resolve() == destination.resolve():
        raise ValueError("destination must differ from source")
    if destination.exists():
        raise FileExistsError(destination)
    if not pages:
        raise ValueError("at least one physical page is required")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    repaired = 0
    with destination.open("r+b") as target:
        image = mmap.mmap(target.fileno(), 0)
        try:
            if len(image) < HEADER_SIZE or image[:8] != CHECKPOINT_MAGIC:
                raise ValueError("not an NP560 NAND checkpoint")
            version, header_size, page_data, page_oob, block_pages, blocks = (
                struct.unpack_from("<6I", image, 8)
            )
            data_size, oob_size = struct.unpack_from("<2Q", image, 32)
            page_count = block_pages * blocks
            if (
                version != 1
                or header_size != HEADER_SIZE
                or page_data != PAGE_DATA
                or page_oob != PAGE_OOB
                or data_size != page_count * page_data
                or oob_size != page_count * page_oob
                or len(image) != HEADER_SIZE + data_size + oob_size
            ):
                raise ValueError("incompatible checkpoint geometry")

            data_base = HEADER_SIZE
            oob_base = data_base + data_size
            for page in sorted(set(pages)):
                if page >= page_count:
                    raise ValueError(
                        f"physical page 0x{page:X} exceeds 0x{page_count - 1:X}"
                    )
                page_offset = data_base + page * PAGE_DATA
                physical = bytearray(image[page_offset : page_offset + PAGE_DATA])
                physical[0::2], physical[1::2] = physical[1::2], physical[0::2]
                image[page_offset : page_offset + PAGE_DATA] = physical

                page_oob_offset = oob_base + page * PAGE_OOB
                for sector, descriptor_offset in enumerate(ECC_OFFSETS):
                    target_offset = page_oob_offset + descriptor_offset
                    if (
                        struct.unpack_from("<H", image, target_offset + 6)[0]
                        != ECC_SIGNATURE
                    ):
                        continue
                    sector_offset = page_offset + sector * 512
                    image[target_offset : target_offset + 8] = sector_descriptor(
                        image, sector_offset
                    )
                    repaired += 1

            # The standalone native rehasher will fill these after this
            # bounded edit.  Zero values prevent a partially patched copy
            # from being mistaken for a valid checkpoint.
            image[48:56] = b"\0" * 8
            image.flush()
        finally:
            image.close()
    return len(set(pages)), repaired


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--page", type=parse_page, action="append", required=True)
    args = parser.parse_args()

    page_count, repaired = patch_pages(args.source, args.destination, args.page)
    print(
        f"PAGES_SWAPPED={page_count} ECC_REPAIRED={repaired} "
        f"OUTPUT={args.destination.resolve()} REHASH_REQUIRED=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
