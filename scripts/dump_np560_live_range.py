#!/usr/bin/env python3
"""Disassemble a read-only physical-memory snapshot from NP560 Web/QEMU."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
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
    if address + size > 0x1000000:
        raise argparse.ArgumentTypeError("range is outside the 24-bit address space")
    return address, size


def fetch_memory(endpoint: str, source: str, address: int, size: int) -> bytes:
    query = urlencode({"source": source, "base": hex(address), "size": hex(size)})
    with urlopen(f"{endpoint.rstrip('/')}?{query}", timeout=15) as response:
        state = json.load(response)
    payload = base64.b64decode(state["frame"], validate=True)
    if len(payload) != size:
        raise ValueError(f"Web endpoint returned {len(payload)} bytes, expected {size}")
    return payload


def disassemble(payload: bytes, address: int) -> list[str]:
    segment = address >> 16
    start_index = (address & 0xFFFF) // 2
    words = [0] * start_index
    words.extend(
        int.from_bytes(payload[index:index + 2], "little")
        for index in range(0, len(payload), 2)
    )
    lines: list[str] = []
    index = start_index
    end = start_index + len(payload) // 2
    while index < end:
        instruction = decode(words, index, segment)
        raw = " ".join(f"{word:04X}" for word in instruction.words)
        lines.append(f"{instruction.address}  {raw:<9}  {instruction.text}")
        index += instruction.size
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ranges", nargs="+", type=parse_range)
    parser.add_argument(
        "--endpoint", default="http://127.0.0.1:8778/api/state",
        help="NP560 Web state endpoint (default: %(default)s)",
    )
    parser.add_argument(
        "--source", choices=("memory", "data", "code"), default="code",
        help="DMCU address space to snapshot (default: %(default)s)",
    )
    parser.add_argument(
        "--raw-output", type=Path,
        help="write the one requested range as raw bytes",
    )
    parser.add_argument(
        "--raw-only", action="store_true",
        help="suppress disassembly (requires --raw-output)",
    )
    args = parser.parse_args()
    if args.raw_output is not None and len(args.ranges) != 1:
        parser.error("--raw-output requires exactly one range")
    if args.raw_only and args.raw_output is None:
        parser.error("--raw-only requires --raw-output")

    for address, size in args.ranges:
        payload = fetch_memory(args.endpoint, args.source, address, size)
        if args.raw_output is not None:
            args.raw_output.parent.mkdir(parents=True, exist_ok=True)
            args.raw_output.write_bytes(payload)
            print(f"wrote {args.raw_output} ({len(payload)} bytes)")
        if args.raw_only:
            continue
        print(f"--- {address >> 16:02X}:{address & 0xFFFF:04X}+0x{size:X}")
        print("\n".join(disassemble(payload, address)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
