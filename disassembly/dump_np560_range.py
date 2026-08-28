#!/usr/bin/env python3
"""Linearly disassemble one or more physical ranges from NP560.PRG."""

from __future__ import annotations

import argparse
from pathlib import Path

from np560_disasm import decode


DEFAULT_PROGRAM = (
    Path(__file__).resolve().parents[1]
    / "NP560+V3.80版系统升级程序"
    / "NP560.PRG"
)
PROGRAM_BASE = 0x200000


def parse_range(value: str) -> tuple[int, int]:
    try:
        address_text, size_text = value.split("+", 1)
        if ":" in address_text:
            segment_text, pc_text = address_text.split(":", 1)
            address = (int(segment_text, 16) << 16) | int(pc_text, 16)
        else:
            address = int(address_text, 0)
        size = int(size_text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "range must be SEG:PC+SIZE or ADDRESS+SIZE"
        ) from error
    if address < PROGRAM_BASE or address & 1 or size <= 0 or size & 1:
        raise argparse.ArgumentTypeError(
            "range must be even, non-empty, and inside the PRG mapping"
        )
    return address, size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ranges", nargs="+", type=parse_range)
    parser.add_argument("--program", type=Path, default=DEFAULT_PROGRAM)
    args = parser.parse_args()

    program = args.program.read_bytes()
    words = [
        int.from_bytes(program[index:index + 2], "little")
        for index in range(0, len(program), 2)
    ]
    for address, size in args.ranges:
        start = (address - PROGRAM_BASE) // 2
        end = start + size // 2
        if start < 0 or end > len(words):
            parser.error(f"range {address:06X}+{size:#x} is outside the PRG")
        print(f"--- {address >> 16:02X}:{address & 0xFFFF:04X}+0x{size:X}")
        index = start
        while index < end:
            instruction = decode(words, index, PROGRAM_BASE >> 16)
            raw = " ".join(f"{word:04X}" for word in instruction.words)
            print(f"{instruction.address}  {raw:<9}  {instruction.text}")
            index += instruction.size
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
