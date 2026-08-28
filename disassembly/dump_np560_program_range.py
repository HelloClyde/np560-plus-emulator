#!/usr/bin/env python3
"""Linearly disassemble selected ranges from an NP560 program image."""

from __future__ import annotations

import argparse
from pathlib import Path

from np560_disasm import decode


DEFAULT_IMAGE = (
    Path(__file__).resolve().parents[1]
    / "NP560+V3.80版系统升级程序"
    / "NP560.PRG"
)


def parse_range(value: str) -> tuple[int, int]:
    try:
        address_text, size_text = value.split("+", 1)
        segment_text, pc_text = address_text.split(":", 1)
        address = (int(segment_text, 16) << 16) | int(pc_text, 16)
        size = int(size_text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "range must be SEG:PC+SIZE"
        ) from error
    if address & 1 or size <= 0 or size & 1:
        raise argparse.ArgumentTypeError("range must contain whole words")
    return address, size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ranges", nargs="+", type=parse_range)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument(
        "--base-segment", type=lambda value: int(value, 0), default=0x20,
    )
    args = parser.parse_args()

    image = args.image.read_bytes()
    base = args.base_segment << 16
    limit = base + len(image)
    for address, size in args.ranges:
        if address < base or address + size > limit:
            raise SystemExit(
                f"range {address >> 16:02X}:{address & 0xFFFF:04X}"
                " is outside the program image"
            )
        payload = image[address - base:address - base + size]
        segment = address >> 16
        start_index = (address & 0xFFFF) // 2
        words = [0] * start_index
        words.extend(
            int.from_bytes(payload[offset:offset + 2], "little")
            for offset in range(0, len(payload), 2)
        )
        print(f"--- {segment:02X}:{address & 0xFFFF:04X}+0x{size:X}")
        index = start_index
        end = start_index + size // 2
        while index < end:
            instruction = decode(words, index, segment)
            raw = " ".join(f"{word:04X}" for word in instruction.words)
            print(f"{instruction.address}  {raw:<9}  {instruction.text}")
            index += instruction.size
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
