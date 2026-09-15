#!/usr/bin/env python3
"""Capture the guest's packed 4-bit NP560 framebuffer as a PNG."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from PIL import Image


OFF = (0xB7, 0xC8, 0xA1)
ON = (0x24, 0x31, 0x26)
DEFAULT_BASE = 0x503840
SIZE = 240 * 120 // 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--api", default="http://127.0.0.1:8775/api/state")
    parser.add_argument(
        "--base", type=lambda value: int(value, 0), default=DEFAULT_BASE,
        help="24-bit packed framebuffer base (default: 0x503840)",
    )
    parser.add_argument("--scale", type=int, default=4)
    args = parser.parse_args()

    query = urlencode({
        "source": "memory", "base": hex(args.base), "size": hex(SIZE),
    })
    with urlopen(f"{args.api}?{query}", timeout=5) as response:
        state = json.load(response)
    packed = base64.b64decode(state["frame"], validate=True)
    if len(packed) != SIZE:
        raise ValueError("native framebuffer has an unexpected size")

    pixels = bytearray()
    for y in range(119, -1, -1):
        row = packed[y * 120:(y + 1) * 120]
        for value in row:
            for level in (value >> 4, value & 0x0F):
                mix = level / 15
                pixels.extend(
                    round(OFF[channel] + (ON[channel] - OFF[channel]) * mix)
                    for channel in range(3)
                )
    image = Image.frombytes("RGB", (240, 120), bytes(pixels))
    if args.scale != 1:
        image = image.resize(
            (240 * args.scale, 120 * args.scale), Image.Resampling.NEAREST
        )
    image.save(args.output)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
