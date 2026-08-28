#!/usr/bin/env python3
"""Restore the exact resident result-object allocator at 1E:6444.

The application result-list creator at 31:9E18 calls resident 1E:6444.
The reconstructed SoC ROM still contains reserved words at that address, but
the complete same-PC implementation is present in the upgrade program at
3B:6444.  Copy those original DMCU instructions into mask ROM verbatim.

This is ROM reconstruction only: QEMU executes the guest implementation and
does not synthesize a service or a return value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROGRAM_BASE = 0x200000
SOURCE = 0x3B6444
DESTINATION = 0x1E6444
SIZE = 0x0690
RESERVED_WORD = b"\x00\x0f"
LINK_6B = 0x2E6B
UNLINK = 0x2F00
RETS = 0xC620


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
    if exact[:2] != words_to_bytes((LINK_6B,)):
        raise ValueError("3B:6444 no longer starts with LINK #0x6B")
    if exact[-4:] != words_to_bytes((UNLINK, RETS)):
        raise ValueError("3B:6444 no longer ends with UNLINK/RETS")

    end = DESTINATION + SIZE
    if end > len(baseline):
        raise ValueError("1E:6444 function falls outside the SoC ROM image")
    if baseline[DESTINATION:end] != RESERVED_WORD * (SIZE // 2):
        raise ValueError("1E:6444 destination is no longer entirely reserved")

    patched = bytearray(baseline)
    patched[DESTINATION:end] = exact
    metadata: dict[str, object] = {
        "destination": "1E:6444 mask ROM",
        "exact_source": "3B:6444",
        "exact_bytes": SIZE,
        "entry": "LINK #0x6B",
        "exit": "UNLINK; RETS",
        "relocation": "none (same PC within paired PRG bank)",
        "reason": "31:9E18 calls this result-object allocator",
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
    print(f"restored exact 1E:6444 resident function; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-resident-result-object-alloc-v1",
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
