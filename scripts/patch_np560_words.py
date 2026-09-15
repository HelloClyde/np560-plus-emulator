#!/usr/bin/env python3
"""Apply verified 16-bit word patches to an NP560 program image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import NamedTuple


PROGRAM_BASE = 0x200000


class WordPatch(NamedTuple):
    address: int
    expected: int
    replacement: int


def parse_patch(value: str) -> WordPatch:
    try:
        address_text, expected_text, replacement_text = value.split(":", 2)
        address = int(address_text, 0)
        expected = int(expected_text, 0)
        replacement = int(replacement_text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "patch must be ADDRESS:EXPECTED:REPLACEMENT"
        ) from error
    if address < PROGRAM_BASE or address & 1:
        raise argparse.ArgumentTypeError(
            "patch address must be an aligned NP560 program address"
        )
    if not 0 <= expected <= 0xFFFF or not 0 <= replacement <= 0xFFFF:
        raise argparse.ArgumentTypeError("patch words must fit in 16 bits")
    return WordPatch(address, expected, replacement)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def apply_patches(payload: bytes, patches: list[WordPatch]) -> bytes:
    output = bytearray(payload)
    seen: set[int] = set()
    for patch in patches:
        if patch.address in seen:
            raise ValueError(f"duplicate patch address 0x{patch.address:06X}")
        seen.add(patch.address)
        offset = patch.address - PROGRAM_BASE
        if offset + 2 > len(output):
            raise ValueError(f"patch address 0x{patch.address:06X} is outside input")
        actual = int.from_bytes(output[offset:offset + 2], "little")
        if actual != patch.expected:
            raise ValueError(
                f"word mismatch at 0x{patch.address:06X}: "
                f"expected 0x{patch.expected:04X}, got 0x{actual:04X}"
            )
        output[offset:offset + 2] = patch.replacement.to_bytes(2, "little")
    return bytes(output)


def build_manifest(
    input_path: Path,
    input_payload: bytes,
    output_path: Path,
    output_payload: bytes,
    patches: list[WordPatch],
) -> dict[str, object]:
    return {
        "format": "np560-program-word-patch-v1",
        "input": str(input_path.resolve()),
        "input_sha256": sha256(input_payload),
        "output": str(output_path.resolve()),
        "output_sha256": sha256(output_payload),
        "patches": [
            {
                "address": f"0x{patch.address:06X}",
                "file_offset": f"0x{patch.address - PROGRAM_BASE:X}",
                "expected": f"0x{patch.expected:04X}",
                "replacement": f"0x{patch.replacement:04X}",
            }
            for patch in patches
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--patch", action="append", required=True, type=parse_patch,
        help="verified ADDRESS:EXPECTED:REPLACEMENT word patch",
    )
    parser.add_argument(
        "--manifest", type=Path,
        help="JSON manifest path (default: output with .json suffix)",
    )
    args = parser.parse_args()

    input_payload = args.input.read_bytes()
    output_payload = apply_patches(input_payload, args.patch)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output_payload)
    manifest_path = args.manifest or args.output.with_suffix(".json")
    manifest = build_manifest(
        args.input, input_payload, args.output, output_payload, args.patch
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
