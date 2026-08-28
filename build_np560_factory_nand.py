#!/usr/bin/env python3
"""Build the minimum factory-seeded NP560+ NAND checkpoint.

The vendor updater does not manufacture the partition descriptor accepted by
its command-2 path.  A real device therefore has to supply that record before
an upgrade starts.  This image keeps every NAND byte erased except for the
physically recovered page 0x3f factory record.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


CHECKPOINT_MAGIC = b"NP560N1\0"
CHECKPOINT_VERSION = 1
HEADER_SIZE = 64
PAGE_DATA = 2048
PAGE_OOB = 64
PAGES_PER_BLOCK = 64
BLOCKS = 4096
PAGES = PAGES_PER_BLOCK * BLOCKS
DATA_SIZE = PAGES * PAGE_DATA
OOB_SIZE = PAGES * PAGE_OOB
FACTORY_PAGE = 0x3F

# Recovered independently from preserved physical NAND checkpoints.  The
# little-endian data begins with CAFE, contains the ASCII signature "KB", and
# carries the fields checked by the original 51:08A6 validator.
# Exact page record emitted by the recovered guest formatter.  DMCU byte
# accesses observe the large-NAND bus order, so the physical bytes contain
# "BK" and 00:02 even though the guest compares logical "KB" and byte 0x02.
FACTORY_DATA_PREFIX = bytes.fromhex(
    "feca e30e 0801 424b 0000 0000 0000 0000 "
    "0000 0000 4508 0500 0002 0000 0000"
)
FACTORY_OOB = bytes(55) + b"\x77" + bytes(8)


def fnv1a(data: bytes | bytearray) -> int:
    """Match np560_nand_trace_hash() in hw/dmcu/np560.c."""
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value


def validate_header_and_hash(checkpoint: bytes) -> None:
    expected_size = HEADER_SIZE + DATA_SIZE + OOB_SIZE
    if len(checkpoint) != expected_size:
        raise AssertionError(f"size {len(checkpoint)} != {expected_size}")
    if checkpoint[:8] != CHECKPOINT_MAGIC:
        raise AssertionError("bad checkpoint magic")
    fields = struct.unpack_from("<6I2Q2I", checkpoint, 8)
    if fields[:8] != (
        CHECKPOINT_VERSION, HEADER_SIZE, PAGE_DATA, PAGE_OOB,
        PAGES_PER_BLOCK, BLOCKS, DATA_SIZE, OOB_SIZE,
    ):
        raise AssertionError(f"bad geometry: {fields[:8]!r}")
    data = checkpoint[HEADER_SIZE:HEADER_SIZE + DATA_SIZE]
    oob = checkpoint[HEADER_SIZE + DATA_SIZE:]
    if fields[8:] != (fnv1a(data), fnv1a(oob)):
        raise AssertionError("bad data/OOB hash")


def build_checkpoint(base_checkpoint: bytes | None = None) -> bytes:
    if base_checkpoint is None:
        data = bytearray(b"\xFF") * DATA_SIZE
        oob = bytearray(b"\xFF") * OOB_SIZE
    else:
        validate_header_and_hash(base_checkpoint)
        data = bytearray(base_checkpoint[HEADER_SIZE:HEADER_SIZE + DATA_SIZE])
        oob = bytearray(base_checkpoint[HEADER_SIZE + DATA_SIZE:])

    data_offset = FACTORY_PAGE * PAGE_DATA
    data[data_offset:data_offset + PAGE_DATA] = (
        FACTORY_DATA_PREFIX + bytes(PAGE_DATA - len(FACTORY_DATA_PREFIX))
    )
    oob_offset = FACTORY_PAGE * PAGE_OOB
    oob[oob_offset:oob_offset + PAGE_OOB] = FACTORY_OOB

    header = bytearray(HEADER_SIZE)
    header[:8] = CHECKPOINT_MAGIC
    struct.pack_into(
        "<6I2Q2I", header, 8,
        CHECKPOINT_VERSION, HEADER_SIZE, PAGE_DATA, PAGE_OOB,
        PAGES_PER_BLOCK, BLOCKS, DATA_SIZE, OOB_SIZE,
        fnv1a(data), fnv1a(oob),
    )
    return bytes(header + data + oob)


def validate_checkpoint(checkpoint: bytes, expect_erased: bool) -> None:
    validate_header_and_hash(checkpoint)
    data = checkpoint[HEADER_SIZE:HEADER_SIZE + DATA_SIZE]
    oob = checkpoint[HEADER_SIZE + DATA_SIZE:]

    page = data[FACTORY_PAGE * PAGE_DATA:(FACTORY_PAGE + 1) * PAGE_DATA]
    if page != FACTORY_DATA_PREFIX + bytes(PAGE_DATA - len(FACTORY_DATA_PREFIX)):
        raise AssertionError("factory data page changed")
    spare = oob[FACTORY_PAGE * PAGE_OOB:(FACTORY_PAGE + 1) * PAGE_OOB]
    if spare != FACTORY_OOB:
        raise AssertionError("factory OOB changed")

    if expect_erased:
        erased_data = (
            data[:FACTORY_PAGE * PAGE_DATA] +
            data[(FACTORY_PAGE + 1) * PAGE_DATA:]
        )
        erased_oob = (
            oob[:FACTORY_PAGE * PAGE_OOB] +
            oob[(FACTORY_PAGE + 1) * PAGE_OOB:]
        )
        if erased_data != b"\xFF" * len(erased_data):
            raise AssertionError("unexpected programmed data outside factory page")
        if erased_oob != b"\xFF" * len(erased_oob):
            raise AssertionError("unexpected programmed OOB outside factory page")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--base-checkpoint", type=Path,
        help=(
            "preserve an updater-formatted FTL checkpoint and replace only "
            "its physical page 0x3f factory record"
        ),
    )
    args = parser.parse_args()

    base_checkpoint = (
        args.base_checkpoint.read_bytes() if args.base_checkpoint else None
    )
    checkpoint = build_checkpoint(base_checkpoint)
    validate_checkpoint(checkpoint, expect_erased=base_checkpoint is None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(checkpoint)
    print(
        f"Wrote {args.output} ({len(checkpoint)} bytes); "
        f"physical page 0x{FACTORY_PAGE:x} contains the factory record; "
        f"base={args.base_checkpoint or 'erased NAND'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
