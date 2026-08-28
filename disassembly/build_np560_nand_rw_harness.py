#!/usr/bin/env python3
"""Build a guest DMCU harness for reconstructed NAND read/program/erase."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROGRAM_SIZE = 0x400000
PAGE = 0x120
BLOCK = PAGE // 64
TRANSFER_SIZE = 16
OOB_PAGE = 0x140
OOB_BLOCK = OOB_PAGE // 64
OOB_COLUMN = 2048
OOB_TRANSFER_SIZE = 64
OOB_PROBE_COLUMN = OOB_COLUMN + 54
PROGRAM_BASE = 0x200000
SOURCE = 0x200500
OOB_SOURCE = 0x200600
READBACK = 0x500600
ERASED_READBACK = 0x500700
OOB_READBACK = 0x500800
OOB_PROBE_READBACK = 0x500900
ERASED_STATUS_READBACK = 0x500A00
PATTERN = bytes.fromhex("00112233445566778899aabbccddeeff")
OOB_PATTERN = bytes(range(OOB_TRANSFER_SIZE))


def mov_r0(value: int) -> list[int]:
    if not 0 <= value <= 0xFFFF:
        raise ValueError("immediate does not fit in 16 bits")
    return [0x4800 | value] if value < 16 else [0x68F0, value]


def push(value: int) -> list[int]:
    return [*mov_r0(value), 0x58F0]


def transfer(
    entry: int,
    buffer: int,
    *,
    page: int = PAGE,
    column: int = 0,
    length: int = TRANSFER_SIZE,
) -> list[int]:
    # Push the seven ABI words in reverse order so SP points at page_hi.
    if not 0 <= buffer <= 0xFFFFFF:
        raise ValueError("buffer must be a 24-bit physical address")
    if not 0 <= page <= 0xFFFFFFFF:
        raise ValueError("page must be a 32-bit value")
    if not 0 <= column <= 0xFFFF or not 0 <= length <= 0xFFFF:
        raise ValueError("column and length must be 16-bit values")
    words: list[int] = []
    for value in (0, length, buffer & 0xFFFF, buffer >> 16,
                  column, page & 0xFFFF, page >> 16):
        words.extend(push(value))
    words.extend([0xBD02, entry, 0x50FE])
    return words


def build_program(mode: str = "roundtrip") -> tuple[bytes, int]:
    roundtrip = [
        *transfer(0xBCC6, SOURCE),
        *transfer(0xBBF6, READBACK),
        *push(BLOCK),
        0xBD02, 0xBDD6,
        0x50F2,
        *transfer(0xBBF6, ERASED_READBACK),
        *transfer(
            0xBBF6, ERASED_STATUS_READBACK, page=PAGE,
            column=OOB_PROBE_COLUMN, length=1,
        ),
        *transfer(
            0xBCC6, OOB_SOURCE, page=OOB_PAGE,
            column=OOB_COLUMN, length=OOB_TRANSFER_SIZE,
        ),
        *transfer(
            0xBBF6, OOB_READBACK, page=OOB_PAGE,
            column=OOB_COLUMN, length=OOB_TRANSFER_SIZE,
        ),
        *transfer(
            0xBBF6, OOB_PROBE_READBACK, page=OOB_PAGE,
            column=OOB_PROBE_COLUMN, length=1,
        ),
    ]
    persist_write = [
        *push(BLOCK),
        0xBD02, 0xBDD6,
        0x50F2,
        *push(OOB_BLOCK),
        0xBD02, 0xBDD6,
        0x50F2,
        *transfer(0xBCC6, SOURCE),
        *transfer(
            0xBCC6, OOB_SOURCE, page=OOB_PAGE,
            column=OOB_COLUMN, length=OOB_TRANSFER_SIZE,
        ),
    ]
    persist_read = [
        *transfer(0xBBF6, READBACK),
        *transfer(
            0xBBF6, OOB_READBACK, page=OOB_PAGE,
            column=OOB_COLUMN, length=OOB_TRANSFER_SIZE,
        ),
        *transfer(
            0xBBF6, OOB_PROBE_READBACK, page=OOB_PAGE,
            column=OOB_PROBE_COLUMN, length=1,
        ),
    ]
    programs = {
        "roundtrip": roundtrip,
        "persist-write": persist_write,
        "persist-read": persist_read,
    }
    try:
        words = [*programs[mode], 0xD0FF]
    except KeyError as exc:
        raise ValueError(f"unknown NAND harness mode: {mode}") from exc
    image = bytearray(PROGRAM_SIZE)
    for index, word in enumerate(words):
        image[index * 2 : index * 2 + 2] = word.to_bytes(2, "little")
    source_offset = SOURCE - PROGRAM_BASE
    image[source_offset : source_offset + len(PATTERN)] = PATTERN
    oob_source_offset = OOB_SOURCE - PROGRAM_BASE
    image[oob_source_offset : oob_source_offset + len(OOB_PATTERN)] = OOB_PATTERN
    return bytes(image), (len(words) - 1) * 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--mode", choices=("roundtrip", "persist-write", "persist-read"),
        default="roundtrip",
    )
    args = parser.parse_args()

    image, loop = build_program(args.mode)
    args.output.write_bytes(image)
    manifest_path = args.manifest or args.output.with_suffix(".json")
    info = {
        "format": "np560-nand-rw-guest-harness-v2",
        "warning": "Test fixture; not product firmware.",
        "mode": args.mode,
        "page": PAGE,
        "block": BLOCK,
        "transfer_size": TRANSFER_SIZE,
        "oob_page": OOB_PAGE,
        "oob_column": OOB_COLUMN,
        "oob_transfer_size": OOB_TRANSFER_SIZE,
        "oob_probe_column": OOB_PROBE_COLUMN,
        "source": f"{SOURCE >> 16:02X}:{SOURCE & 0xFFFF:04X}",
        "oob_source": f"{OOB_SOURCE >> 16:02X}:{OOB_SOURCE & 0xFFFF:04X}",
        "readback": f"{READBACK >> 16:02X}:{READBACK & 0xFFFF:04X}",
        "erased_readback": (
            f"{ERASED_READBACK >> 16:02X}:{ERASED_READBACK & 0xFFFF:04X}"
        ),
        "oob_readback": (
            f"{OOB_READBACK >> 16:02X}:{OOB_READBACK & 0xFFFF:04X}"
        ),
        "oob_probe_readback": (
            f"{OOB_PROBE_READBACK >> 16:02X}:"
            f"{OOB_PROBE_READBACK & 0xFFFF:04X}"
        ),
        "erased_status_readback": (
            f"{ERASED_STATUS_READBACK >> 16:02X}:"
            f"{ERASED_STATUS_READBACK & 0xFFFF:04X}"
        ),
        "loop": f"20:{loop:04X}",
        "pattern": PATTERN.hex(),
        "oob_pattern": OOB_PATTERN.hex(),
    }
    manifest_path.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(image):,} bytes to {args.output.resolve()}")
    print(f"wrote {manifest_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
