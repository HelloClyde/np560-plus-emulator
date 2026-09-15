#!/usr/bin/env python3
"""Create a validated NP560.PRG diagnostic variant with word patches."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROGRAM_BASE = 0x200000
PROGRAM_SIZE = 0x400000


def number(value: str) -> int:
    return int(value, 0)


def word_patch(value: str) -> tuple[int, int, int]:
    try:
        address_text, expected_text, replacement_text = value.split(":", 2)
        address = number(address_text)
        expected = number(expected_text)
        replacement = number(replacement_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "word patch must be ADDRESS:EXPECTED:REPLACEMENT"
        ) from exc
    if not PROGRAM_BASE <= address < PROGRAM_BASE + PROGRAM_SIZE or address & 1:
        raise argparse.ArgumentTypeError("word address is outside aligned NP560.PRG")
    if not 0 <= expected <= 0xFFFF or not 0 <= replacement <= 0xFFFF:
        raise argparse.ArgumentTypeError("expected and replacement must be 16-bit")
    return address, expected, replacement


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--word", action="append", type=word_patch, required=True,
        help="validated ADDRESS:EXPECTED:REPLACEMENT values (repeatable)",
    )
    args = parser.parse_args()

    source = args.input.read_bytes()
    if len(source) != PROGRAM_SIZE:
        parser.error(f"input must be {PROGRAM_SIZE} bytes, got {len(source)}")

    patched = bytearray(source)
    manifest_patches = []
    seen = set()
    for address, expected, replacement in args.word:
        if address in seen:
            parser.error(f"duplicate patch address 0x{address:06X}")
        seen.add(address)
        offset = address - PROGRAM_BASE
        actual = int.from_bytes(patched[offset:offset + 2], "little")
        if actual != expected:
            parser.error(
                f"0x{address:06X} contains 0x{actual:04X}, expected 0x{expected:04X}"
            )
        patched[offset:offset + 2] = replacement.to_bytes(2, "little")
        manifest_patches.append({
            "address": f"0x{address:06X}",
            "file_offset": f"0x{offset:06X}",
            "expected": f"0x{expected:04X}",
            "replacement": f"0x{replacement:04X}",
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    manifest = {
        "format": "np560-program-word-patch-v1",
        "input": str(args.input.resolve()),
        "input_sha256": hashlib.sha256(source).hexdigest(),
        "output": str(args.output.resolve()),
        "output_sha256": hashlib.sha256(patched).hexdigest(),
        "patches": manifest_patches,
    }
    manifest_path = args.output.with_suffix(".json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(patched):,} bytes to {args.output.resolve()}")
    print(f"wrote {manifest_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
