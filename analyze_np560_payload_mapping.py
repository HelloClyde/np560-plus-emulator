#!/usr/bin/env python3
"""Locate NP560 update-payload bytes in a complete NAND checkpoint.

The vendor updater streams 512-byte sectors, while the emulated NAND stores
2048-byte physical pages.  This read-only tool searches stable payload slices
in the checkpoint data area and reports the corresponding physical block,
page, and column.  It is intended to distinguish a bad FTL lookup from a bad
burn/checkpoint layout without modifying either input.
"""

from __future__ import annotations

import argparse
import mmap
import struct
from pathlib import Path


MAGIC = b"NP560N1\0"
HEADER_SIZE = 64
DEFAULT_SIGNATURE_SIZE = 96


def parse_int(value: str) -> int:
    return int(value, 0)


def default_offsets(payload_size: int) -> list[int]:
    candidates = [
        0,
        0x200,
        0x400,
        0x1000,
        0x10000,
        0x100000,
        0x400000,
        0x800000,
        0x1000000,
        0x2000000,
        max(0, payload_size - 0x400),
    ]
    return sorted({offset for offset in candidates if offset < payload_size})


def stable_signature(payload: bytes, offset: int, wanted: int) -> tuple[int, bytes]:
    """Return the first non-uniform signature at or after *offset*."""
    limit = min(len(payload), offset + 0x2000)
    for start in range(offset, max(offset, limit - wanted + 1), 16):
        signature = payload[start:start + wanted]
        if len(signature) != wanted:
            break
        if len(set(signature)) >= 8:
            return start, signature
    return offset, payload[offset:offset + wanted]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument(
        "--offset",
        action="append",
        default=[],
        type=parse_int,
        help="payload byte offset to locate (repeatable; default: samples)",
    )
    parser.add_argument(
        "--signature-size", type=parse_int, default=DEFAULT_SIGNATURE_SIZE,
    )
    parser.add_argument("--max-matches", type=int, default=8)
    args = parser.parse_args()

    payload = args.payload.read_bytes()
    if args.signature_size < 16:
        parser.error("--signature-size must be at least 16")
    offsets = args.offset or default_offsets(len(payload))

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
            raise SystemExit(
                f"unsupported checkpoint version/header {version}/{stored_header_size}"
            )
        expected_data = page_data * pages_per_block * blocks
        expected_oob = page_oob * pages_per_block * blocks
        if data_size != expected_data or oob_size != expected_oob:
            raise SystemExit("checkpoint geometry and data/OOB sizes disagree")

        mapping = mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            data_start = stored_header_size
            data_end = data_start + data_size
            print(
                f"payload={len(payload)} checkpoint-data={data_size} "
                f"geometry={blocks}x{pages_per_block}x{page_data}"
            )
            for requested in offsets:
                if requested < 0 or requested >= len(payload):
                    print(f"payload+0x{requested:x}: OUT_OF_RANGE")
                    continue
                actual, signature = stable_signature(
                    payload, requested, args.signature_size,
                )
                if len(signature) != args.signature_size:
                    print(f"payload+0x{requested:x}: TOO_SHORT")
                    continue
                matches: list[int] = []
                position = mapping.find(signature, data_start, data_end)
                while position >= 0 and len(matches) < args.max_matches:
                    matches.append(position)
                    position = mapping.find(signature, position + 1, data_end)
                if not matches:
                    print(
                        f"payload+0x{actual:08x} "
                        f"sig={signature[:8].hex()}: NOT_FOUND"
                    )
                    continue
                locations = []
                for position in matches:
                    data_offset = position - data_start
                    physical_page, column = divmod(data_offset, page_data)
                    block, page = divmod(physical_page, pages_per_block)
                    locations.append(
                        f"b{block:04x}:p{page:02x}:c{column:03x}"
                        f"(data+0x{data_offset:08x})"
                    )
                print(
                    f"payload+0x{actual:08x} sig={signature[:8].hex()}: "
                    + ", ".join(locations)
                )
        finally:
            mapping.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
