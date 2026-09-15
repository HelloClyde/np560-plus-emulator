#!/usr/bin/env python3
"""Search a read-only NP560 Web/QEMU memory view for exact bytes."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


def integer(value: str) -> int:
    return int(value, 0)


def file_slice(value: str) -> bytes:
    try:
        path_text, slice_text = value.rsplit("@", 1)
        offset_text, size_text = slice_text.split(":", 1)
        offset = int(offset_text, 0)
        size = int(size_text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "file needle must be PATH@OFFSET:SIZE"
        ) from error
    if offset < 0 or size <= 0:
        raise argparse.ArgumentTypeError("file needle range is invalid")
    payload = Path(path_text).read_bytes()
    needle = payload[offset:offset + size]
    if len(needle) != size:
        raise argparse.ArgumentTypeError("file needle extends past EOF")
    return needle


def snapshot(endpoint: str, source: str, base: int, size: int) -> bytes:
    query = urlencode({"source": source, "base": hex(base), "size": hex(size)})
    with urlopen(f"{endpoint.rstrip('/')}?{query}", timeout=30) as response:
        result = json.load(response)
    payload = base64.b64decode(result["frame"], validate=True)
    if len(payload) != size:
        raise RuntimeError(
            f"snapshot 0x{base:06X} returned {len(payload)}, expected {size}"
        )
    return payload


def find_offsets(payload: bytes, needle: bytes) -> list[int]:
    offsets: list[int] = []
    start = 0
    while True:
        found = payload.find(needle, start)
        if found < 0:
            return offsets
        offsets.append(found)
        start = found + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint", default="http://127.0.0.1:8801/api/state"
    )
    parser.add_argument(
        "--source", choices=("memory", "data", "code"), default="data"
    )
    parser.add_argument("--start", type=integer, default=0)
    parser.add_argument("--end", type=integer, default=0x1000000)
    parser.add_argument("--chunk-size", type=integer, default=0x10000)
    needle_group = parser.add_mutually_exclusive_group(required=True)
    needle_group.add_argument("--needle-hex")
    needle_group.add_argument("--needle-file", type=file_slice)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if not 0 <= args.start < args.end <= 0x1000000:
        parser.error("search range is outside the 24-bit address space")
    if not 1 <= args.chunk_size <= 0x10000:
        parser.error("chunk size must be 1..65536")
    try:
        needle = (
            bytes.fromhex(args.needle_hex)
            if args.needle_hex is not None else args.needle_file
        )
    except ValueError as error:
        parser.error(f"invalid hexadecimal needle: {error}")
    if not needle:
        parser.error("needle must not be empty")

    hits: list[int] = []
    carry = b""
    position = args.start
    while position < args.end:
        size = min(args.chunk_size, args.end - position)
        current = snapshot(args.endpoint, args.source, position, size)
        combined = carry + current
        combined_base = position - len(carry)
        for offset in find_offsets(combined, needle):
            address = combined_base + offset
            if args.start <= address and address + len(needle) <= args.end:
                if not hits or hits[-1] != address:
                    hits.append(address)
        carry = combined[-(len(needle) - 1):] if len(needle) > 1 else b""
        position += size

    result = {
        "schema": "np560-live-memory-search-v1",
        "endpoint": args.endpoint,
        "source": args.source,
        "start": args.start,
        "end": args.end,
        "needle_hex": needle.hex(),
        "hits": hits,
        "hit_addresses": [
            f"{address >> 16:02X}:{address & 0xFFFF:04X}"
            for address in hits
        ],
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
