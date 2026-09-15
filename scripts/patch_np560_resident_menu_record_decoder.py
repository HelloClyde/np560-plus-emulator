#!/usr/bin/env python3
"""Restore the exact resident menu-record decoder at 11:5C12.

The menu page renderer at 18:A292 calls resident 11:5C12 with its 0x3c-byte
work records.  The V3.80 upgrade program contains the complete same-PC body
at 2E:5C12, including four calls to the already recovered 30:FE0E memory-fill
primitive and a balanced epilogue.  This patch copies those vendor DMCU
instructions verbatim; QEMU executes them as guest code without host HLE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROGRAM_BASE = 0x200000
SOURCE = 0x2E5C12
DESTINATION = 0x115C12
SIZE = 0x16A4
RESERVED_WORD = b"\x00\x0f"
LINK_39 = 0x2E39
UNLINK = 0x2F00
RETS = 0xC620
MEMORY_FILL_CALL = bytes.fromhex("30 bd 0e fe")


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
    exact = program_bytes(program, SOURCE, SIZE)
    if exact[:2] != words_to_bytes((LINK_39,)):
        raise ValueError("2E:5C12 no longer starts with LINK #0x39")
    if exact[-16:] != words_to_bytes((
        0x386F, 0x385F, 0x384F, 0x383F,
        0x382F, 0x381F, UNLINK, RETS,
    )):
        raise ValueError("2E:5C12 no longer ends with its balanced epilogue")
    if exact.count(MEMORY_FILL_CALL) != 4:
        raise ValueError("2E:5C12 no longer has four SCALL 30:FE0E dependencies")

    end = DESTINATION + SIZE
    if end > len(baseline):
        raise ValueError("11:5C12 function falls outside the SoC ROM image")
    if baseline[DESTINATION:end] != RESERVED_WORD * (SIZE // 2):
        raise ValueError("11:5C12 destination is no longer entirely reserved")

    patched = bytearray(baseline)
    patched[DESTINATION:end] = exact
    metadata: dict[str, object] = {
        "destination": "11:5C12 mask ROM",
        "exact_source": "2E:5C12",
        "exact_bytes": SIZE,
        "entry": "LINK #0x39",
        "exit": "balanced register restore; UNLINK; RETS",
        "dependencies": ["four exact SCALL 30:FE0E memory-fill calls"],
        "relocation": "none (same PC within paired PRG bank)",
        "reason": "18:A292 calls this menu-page work-record decoder",
        "execution_model": (
            "exact original guest DMCU instructions; no host HLE or ROM service"
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
    print(f"restored exact 11:5C12 resident decoder; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-resident-menu-record-decoder-v1",
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
