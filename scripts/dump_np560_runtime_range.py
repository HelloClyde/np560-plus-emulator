#!/usr/bin/env python3
"""Linearly disassemble a physical range exposed by the NP560 web API."""

from __future__ import annotations

import argparse
import base64
import json
from urllib.parse import urlencode
from urllib.request import urlopen

from np560_disasm import decode


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
    if address < 0 or address & 1 or size <= 0 or size & 1:
        raise argparse.ArgumentTypeError("range must contain positive whole words")
    return address, size


def read_range(api: str, source: str, address: int, size: int) -> bytes:
    query = urlencode({"source": source, "base": hex(address), "size": hex(size)})
    with urlopen(f"{api}?{query}", timeout=5) as response:
        state = json.load(response)
    payload = base64.b64decode(state["frame"], validate=True)
    if len(payload) != size:
        raise ValueError(f"API returned {len(payload)} bytes, expected {size}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ranges", nargs="+", type=parse_range)
    parser.add_argument("--api", default="http://127.0.0.1:8775/api/state")
    parser.add_argument(
        "--source", choices=("data", "memory"), default="data",
        help="read raw external RAM or the CPU-visible physical address space",
    )
    args = parser.parse_args()

    for address, size in args.ranges:
        payload = read_range(args.api, args.source, address, size)
        segment = address >> 16
        start_index = (address & 0xFFFF) // 2
        words = [0] * start_index
        words.extend(
            int.from_bytes(payload[index:index + 2], "little")
            for index in range(0, len(payload), 2)
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
