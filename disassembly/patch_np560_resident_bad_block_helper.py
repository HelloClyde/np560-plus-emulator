#!/usr/bin/env python3
"""Keep the exact NAND bad-block status helper resident.

The exact resident metadata initializer at 1C:28AC calls 24:236A.  A late
application overlay replaces that destination with an unrelated function
suffix, so its RETS unwinds the 1C:28AC call frame and returns a non-status
value to 31:F670.  Relocate the complete same-PC PRG implementation from
41:236A into unused resident ROM and retarget the single resident caller.

This is guest DMCU code recovery, not a QEMU ROM service or host-side HLE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROGRAM_BASE = 0x200000
SOURCE_HELPER = 0x41236A
HELPER_SIZE = 0x0464
RESIDENT_HELPER = 0x064C00
CALL_SITE = 0x1C2A10
ORIGINAL_CALL = (0xBD24, 0x236A)
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


def relocate_local_jumps(helper: bytes) -> tuple[bytes, int]:
    """Relocate same-segment AJMP targets inside the copied function."""
    source_low = SOURCE_HELPER & 0xFFFF
    source_end = source_low + HELPER_SIZE
    destination_low = RESIDENT_HELPER & 0xFFFF
    delta = destination_low - source_low
    words = [
        int.from_bytes(helper[index:index + 2], "little")
        for index in range(0, len(helper), 2)
    ]
    relocated = 0
    for index in range(len(words) - 1):
        if words[index] >> 8 != 0xAC:
            continue
        target = words[index + 1]
        if source_low <= target < source_end:
            words[index + 1] = target + delta
            relocated += 1
    return words_to_bytes(tuple(words)), relocated


def patch_image(baseline: bytes, program: bytes) -> tuple[bytes, dict[str, object]]:
    exact_helper = program_bytes(program, SOURCE_HELPER, HELPER_SIZE)
    if exact_helper[:2] != words_to_bytes((0x2E0C,)):
        raise ValueError("41:236A no longer starts with LINK #0x0C")
    if exact_helper[-4:] != words_to_bytes((0x2F00, 0xC620)):
        raise ValueError("41:236A no longer ends with UNLINK/RETS")
    helper, relocated_jumps = relocate_local_jumps(exact_helper)
    if not relocated_jumps:
        raise ValueError("41:236A no longer contains local AJMP targets")

    helper_end = RESIDENT_HELPER + HELPER_SIZE
    if helper_end > len(baseline):
        raise ValueError("resident helper falls outside the SoC ROM image")
    if baseline[RESIDENT_HELPER:helper_end] != (
        RESERVED_WORD * (HELPER_SIZE // 2)
    ):
        raise ValueError("06:4C00 is no longer an unused resident-ROM range")

    expected_call = words_to_bytes(ORIGINAL_CALL)
    if baseline[CALL_SITE:CALL_SITE + 4] != expected_call:
        raise ValueError("1C:2A10 is not the expected 24:236A call")

    patched = bytearray(baseline)
    patched[RESIDENT_HELPER:helper_end] = helper
    patched[CALL_SITE:CALL_SITE + 4] = words_to_bytes(PATCHED_CALL)
    metadata: dict[str, object] = {
        "resident_helper": "06:4C00",
        "exact_source": "41:236A",
        "bytes": HELPER_SIZE,
        "relocated_local_jumps": relocated_jumps,
        "retargeted_call": "1C:2A10",
        "reason": (
            "late application overlay replaces 24:236A with an unrelated "
            "function suffix"
        ),
        "execution_model": (
            "exact guest DMCU function with position-adjusted local AJMP "
            "operands; no host HLE"
        ),
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
    print(f"installed resident exact bad-block helper; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-resident-bad-block-helper-v1",
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
