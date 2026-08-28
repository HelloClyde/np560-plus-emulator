#!/usr/bin/env python3
"""Pair-swap an exact word-aligned NAND data span and refresh touched ECC."""

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
SECTOR_DATA = 512


def parse_span(value: str) -> tuple[int, int]:
    try:
        offset_text, length_text = value.split(":", 1)
        offset = int(offset_text, 0)
        length = int(length_text, 0)
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError(
            "span must be DATA_OFFSET:LENGTH"
        ) from error
    if offset < 0 or length <= 0 or offset & 1 or length & 1:
        raise argparse.ArgumentTypeError(
            "span offset and positive length must both be word aligned"
        )
    return offset, length


def patch_span(
    source: Path,
    destination: Path,
    span: tuple[int, int],
) -> tuple[int, int]:
    if source.resolve() == destination.resolve():
        raise ValueError("destination must differ from source")
    if destination.exists():
        raise FileExistsError(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    offset, length = span
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
                or offset > data_size
                or length > data_size - offset
            ):
                raise ValueError("incompatible checkpoint geometry or span")

            data_base = HEADER_SIZE
            physical = bytearray(
                image[data_base + offset : data_base + offset + length]
            )
            physical[0::2], physical[1::2] = physical[1::2], physical[0::2]
            image[data_base + offset : data_base + offset + length] = physical

            first_sector = offset // SECTOR_DATA
            last_sector = (offset + length - 1) // SECTOR_DATA
            oob_base = data_base + data_size
            for absolute_sector in range(first_sector, last_sector + 1):
                page = absolute_sector // (PAGE_DATA // SECTOR_DATA)
                sector = absolute_sector % (PAGE_DATA // SECTOR_DATA)
                descriptor_offset = oob_base + page * PAGE_OOB + ECC_OFFSETS[sector]
                if (
                    struct.unpack_from("<H", image, descriptor_offset + 6)[0]
                    != ECC_SIGNATURE
                ):
                    continue
                sector_offset = data_base + absolute_sector * SECTOR_DATA
                image[descriptor_offset : descriptor_offset + 8] = sector_descriptor(
                    image, sector_offset
                )
                repaired += 1

            image[48:56] = b"\0" * 8
            image.flush()
        finally:
            image.close()
    return last_sector - first_sector + 1, repaired


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--span", type=parse_span, required=True)
    args = parser.parse_args()

    sectors, repaired = patch_span(args.source, args.destination, args.span)
    print(
        f"SPAN_OFFSET=0x{args.span[0]:X} SPAN_LENGTH=0x{args.span[1]:X} "
        f"SECTORS_TOUCHED={sectors} ECC_REPAIRED={repaired} "
        f"OUTPUT={args.destination.resolve()} REHASH_REQUIRED=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
