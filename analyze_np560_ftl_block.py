#!/usr/bin/env python3
"""Inspect one physical FTL/metadata block in an NP560 NAND checkpoint."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


MAGIC = b"NP560N1\0"
HEADER_SIZE = 64


def parse_int(value: str) -> int:
    return int(value, 0)


def spans(data: bytes, erased: int = 0xFF) -> str:
    indexes = [index for index, byte in enumerate(data) if byte != erased]
    if not indexes:
        return "erased"
    return f"non-erased={len(indexes)} range=0x{indexes[0]:x}..0x{indexes[-1]:x}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("block", type=parse_int)
    parser.add_argument(
        "--find-word", action="append", default=[], type=parse_int,
        help="locate a 16-bit little-endian value (repeatable)",
    )
    parser.add_argument("--prefix", type=parse_int, default=32)
    args = parser.parse_args()

    with args.checkpoint.open("rb") as source:
        header = source.read(HEADER_SIZE)
        if len(header) != HEADER_SIZE or header[:8] != MAGIC:
            raise SystemExit("not an NP560 NAND checkpoint")
        (
            version,
            stored_header_size,
            page_data,
            page_oob,
            pages_per_block,
            blocks,
            data_size,
            oob_size,
            _data_hash,
            _oob_hash,
        ) = struct.unpack_from("<6I2Q2I", header, 8)
        if version != 1 or stored_header_size != HEADER_SIZE:
            raise SystemExit("unsupported checkpoint version/header")
        if not 0 <= args.block < blocks:
            parser.error(f"block must be in 0..{blocks - 1}")
        if args.prefix < 1:
            parser.error("--prefix must be positive")

        block_data_offset = (
            stored_header_size + args.block * pages_per_block * page_data
        )
        block_oob_offset = (
            stored_header_size + data_size
            + args.block * pages_per_block * page_oob
        )
        source.seek(block_data_offset)
        data = source.read(pages_per_block * page_data)
        source.seek(block_oob_offset)
        oob = source.read(pages_per_block * page_oob)
        if len(data) != pages_per_block * page_data or len(oob) != pages_per_block * page_oob:
            raise SystemExit("checkpoint is truncated")

        print(
            f"block=0x{args.block:04x} data={spans(data)} oob={spans(oob)}"
        )
        for page in range(pages_per_block):
            page_bytes = data[page * page_data:(page + 1) * page_data]
            page_oob_bytes = oob[page * page_oob:(page + 1) * page_oob]
            if page_bytes == b"\xff" * page_data and page_oob_bytes == b"\xff" * page_oob:
                continue
            print(
                f"p{page:02x} data[{spans(page_bytes)}] "
                f"{page_bytes[:args.prefix].hex()} "
                f"oob[{spans(page_oob_bytes)}] {page_oob_bytes.hex()}"
            )

        for value in args.find_word:
            if not 0 <= value <= 0xFFFF:
                parser.error("--find-word values must fit in 16 bits")
            needle = struct.pack("<H", value)
            locations = []
            start = 0
            while True:
                position = data.find(needle, start)
                if position < 0:
                    break
                page, column = divmod(position, page_data)
                locations.append(f"p{page:02x}:c{column:03x}")
                start = position + 1
            print(
                f"word=0x{value:04x}: "
                + (", ".join(locations) if locations else "NOT_FOUND")
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
