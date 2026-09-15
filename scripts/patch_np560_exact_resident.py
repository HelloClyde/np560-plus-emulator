#!/usr/bin/env python3
"""Patch one exact linked PRG routine into a recovered resident-ROM image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROGRAM_BASE = 0x200000
RESERVED_WORD = b"\x00\x0f"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--destination", type=lambda value: int(value, 0),
                        required=True)
    parser.add_argument("--source", type=lambda value: int(value, 0),
                        required=True)
    parser.add_argument("--size", type=lambda value: int(value, 0),
                        required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    baseline = args.baseline.read_bytes()
    program = args.program.read_bytes()
    source_offset = args.source - PROGRAM_BASE
    if (args.destination & 1 or args.source & 1 or args.size <= 0 or
            args.size & 1):
        raise SystemExit("destination, source, and size must be whole words")
    if args.destination + args.size > len(baseline):
        raise SystemExit("destination range is outside the resident ROM")
    if source_offset < 0 or source_offset + args.size > len(program):
        raise SystemExit("source range is outside NP560.PRG")

    old = baseline[args.destination:args.destination + args.size]
    if old != RESERVED_WORD * (args.size // 2):
        raise SystemExit("destination is not an unreconstructed reserved range")
    exact = program[source_offset:source_offset + args.size]
    if exact[:16] != bytes.fromhex(
        "18 2e f1 58 f2 58 f3 58 f4 58 f5 58 f6 58 f7 58"
    ):
        raise SystemExit("source does not begin with the evidenced LINK prologue")
    if exact[-18:] != bytes.fromhex(
        "7f 38 6f 38 5f 38 4f 38 3f 38 2f 38 1f 38 00 2f 20 c6"
    ):
        raise SystemExit("source does not end with the evidenced balanced epilogue")

    patched = bytearray(baseline)
    patched[args.destination:args.destination + args.size] = exact
    output = bytes(patched)
    args.output.write_bytes(output)
    print(
        f"patched {args.size} exact bytes from 0x{args.source:06x} "
        f"to 0x{args.destination:06x}; sha256={sha256(output)}"
    )

    if args.manifest:
        record = {
            "format": "np560-recovered-resident-rom-patch-v1",
            "baseline": str(args.baseline),
            "baseline_sha256": sha256(baseline),
            "program": str(args.program),
            "program_sha256": sha256(program),
            "output": str(args.output),
            "output_sha256": sha256(output),
            "patch": {
                "destination": "1E:AB32",
                "source": "3B:AB32",
                "bytes": args.size,
                "status": (
                    "exact original DMCU routine; one-word input, byte status "
                    "in R0/RB1, balanced LINK #0x18 / UNLINK / RETS body"
                ),
            },
        }
        args.manifest.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
