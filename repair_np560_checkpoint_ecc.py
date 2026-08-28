#!/usr/bin/env python3
"""Normalize factory metadata and rebuild ECC in an NP560 checkpoint copy.

Early clean-room checkpoints preserved the NAND payload and FTL metadata but
stored zero parity halves in descriptors carrying the valid 0x6979 signature.
The original guest validator rejects those sectors.  This utility keeps the
source immutable, copies it, and regenerates only signed descriptors using the
same 512-byte paired-parity format recovered from 31:8C18/51:C1A4.
"""

from __future__ import annotations

import argparse
import mmap
import shutil
import struct
from pathlib import Path

from analyze_np560_ecc_checkpoint import ECC_OFFSETS, ECC_SIGNATURE, sector_descriptor


CHECKPOINT_MAGIC = b"NP560N1\0"
HEADER_SIZE = 64
FACTORY_PAGE = 0x3F
FACTORY_RECORD_SIZE = 0x208
FACTORY_RECORDS = 3
SECTOR_SIZE = 512
FACTORY_DATA_PREFIX = bytes.fromhex(
    "feca e30e 0801 424b 0000 0000 0000 0000 "
    "0000 0000 4508 0500 0002 0000 0000"
)
FACTORY_OOB = bytes(55) + b"\x77" + bytes(8)


def repair_checkpoint(source: Path, destination: Path) -> tuple[int, int]:
    if source.resolve() == destination.resolve():
        raise ValueError("destination must differ from source")
    if destination.exists():
        raise FileExistsError(destination)

    shutil.copyfile(source, destination)
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
                or page_data != 2048
                or page_oob != 64
                or data_size != page_count * page_data
                or oob_size != page_count * page_oob
                or len(image) != HEADER_SIZE + data_size + oob_size
            ):
                raise ValueError("incompatible checkpoint geometry")

            data_base = HEADER_SIZE
            oob_base = data_base + data_size

            # Preserve the record exactly as the recovered guest formatter
            # emits it.  Byte-addressed DMCU fields use the bus order visible
            # here ("BK" and 00:02 physically), not host-order "KB"/02:00.
            factory_base = data_base + FACTORY_PAGE * page_data
            for record in range(FACTORY_RECORDS):
                record_base = factory_base + record * FACTORY_RECORD_SIZE
                image[record_base : record_base + SECTOR_SIZE] = (
                    FACTORY_DATA_PREFIX
                    + bytes(SECTOR_SIZE - len(FACTORY_DATA_PREFIX))
                )
            factory_oob = oob_base + FACTORY_PAGE * page_oob
            image[factory_oob : factory_oob + page_oob] = FACTORY_OOB

            signed = 0
            changed = 0
            for page in range(page_count):
                page_data_offset = data_base + page * page_data
                page_oob_offset = oob_base + page * page_oob
                for sector, descriptor_offset in enumerate(ECC_OFFSETS):
                    target_offset = page_oob_offset + descriptor_offset
                    if struct.unpack_from("<H", image, target_offset + 6)[0] != ECC_SIGNATURE:
                        continue
                    signed += 1
                    expected = sector_descriptor(
                        image, page_data_offset + sector * SECTOR_SIZE
                    )
                    if image[target_offset : target_offset + 8] != expected:
                        image[target_offset : target_offset + 8] = expected
                        changed += 1

            for record in range(FACTORY_RECORDS):
                record_base = factory_base + record * FACTORY_RECORD_SIZE
                descriptor_offset = record_base + SECTOR_SIZE
                if (
                    struct.unpack_from("<H", image, descriptor_offset + 6)[0]
                    != ECC_SIGNATURE
                ):
                    raise ValueError(
                        f"factory record {record} lacks the 0x6979 descriptor signature"
                    )
                signed += 1
                expected = sector_descriptor(image, record_base)
                if image[descriptor_offset : descriptor_offset + 8] != expected:
                    image[descriptor_offset : descriptor_offset + 8] = expected
                    changed += 1

            image.flush()
            return signed, changed
        finally:
            image.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    signed, changed = repair_checkpoint(args.source, args.destination)
    print(f"ECC_SIGNED={signed} ECC_REPAIRED={changed} OUTPUT={args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
