#!/usr/bin/env python3
"""Keep the exact NAND-geometry MSB helper resident after late overlays.

The exact 1E:5084 storage initializer is recovered from PRG 3B:5084.  It
calls 33:2F1A three times while deriving the sector and erase geometry.
Although the early dependency installer restores the exact 50:2F1A helper,
the later application-module copy overwrites 33:2F1A with an unrelated flat
body before the second storage initialization.

Copy the exact, call-free helper into unused resident ROM and retarget only
the three calls in the already exact 1E:5084 body.  All computation remains
ordinary guest DMCU code; QEMU supplies no return value or ROM service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROGRAM_BASE = 0x200000
SOURCE_HELPER = 0x502F1A
HELPER_SIZE = 0x0024
RESIDENT_HELPER = 0x064B00
CALL_SITES = (0x1E5658, 0x1E567A, 0x1E56B2)
ORIGINAL_CALL = (0xBD33, 0x2F1A)
PATCHED_CALL = (0xBD06, RESIDENT_HELPER & 0xFFFF)
RESERVED_WORD = b"\x00\x0f"


def words_to_bytes(words: tuple[int, ...]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def program_bytes(program: bytes, address: int, size: int) -> bytes:
    offset = address - PROGRAM_BASE
    if offset < 0 or offset + size > len(program):
        raise ValueError(f"program range 0x{address:06X}+0x{size:X} is absent")
    return program[offset:offset + size]


def patch_image(baseline: bytes, program: bytes) -> tuple[bytes, dict[str, object]]:
    helper = program_bytes(program, SOURCE_HELPER, HELPER_SIZE)
    if helper[:2] != words_to_bytes((0x58F5,)):
        raise ValueError("50:2F1A no longer starts with the expected R5 save")
    if helper[-2:] != words_to_bytes((0xC620,)):
        raise ValueError("50:2F1A no longer ends with RETS")

    helper_end = RESIDENT_HELPER + HELPER_SIZE
    if helper_end > len(baseline):
        raise ValueError("resident helper falls outside the SoC ROM image")
    if baseline[RESIDENT_HELPER:helper_end] != (
        RESERVED_WORD * (HELPER_SIZE // 2)
    ):
        raise ValueError("06:4B00 is no longer an unused resident-ROM range")

    expected_call = words_to_bytes(ORIGINAL_CALL)
    patched_call = words_to_bytes(PATCHED_CALL)
    for address in CALL_SITES:
        if baseline[address:address + len(expected_call)] != expected_call:
            raise ValueError(
                f"1E:5084 call at 0x{address:06X} is not the expected 33:2F1A"
            )

    patched = bytearray(baseline)
    patched[RESIDENT_HELPER:helper_end] = helper
    for address in CALL_SITES:
        patched[address:address + len(patched_call)] = patched_call

    metadata: dict[str, object] = {
        "resident_helper": "06:4B00",
        "exact_source": "50:2F1A",
        "bytes": HELPER_SIZE,
        "retargeted_calls": [f"{address >> 16:02X}:{address & 0xFFFF:04X}"
                             for address in CALL_SITES],
        "reason": (
            "late application overlay replaces 33:2F1A before the second "
            "storage initialization"
        ),
        "execution_model": "ordinary guest DMCU instructions; no host HLE",
    }
    return bytes(patched), metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    baseline = args.baseline.read_bytes()
    program = args.program.read_bytes()
    output, patch = patch_image(baseline, program)
    args.output.write_bytes(output)
    print(f"installed resident exact MSB helper; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-resident-msb-helper-v1",
            "baseline": str(args.baseline),
            "baseline_sha256": sha256(baseline),
            "program": str(args.program),
            "program_sha256": sha256(program),
            "output": str(args.output),
            "output_sha256": sha256(output),
            "patch": patch,
        }
        args.manifest.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
