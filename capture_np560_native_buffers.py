#!/usr/bin/env python3
"""Capture the NP560 LCD, native framebuffers, and root-entry snapshots."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from PIL import Image


WIDTH = 240
HEIGHT = 120
PACKED_SIZE = WIDTH * HEIGHT // 2


def fetch(url: str, source: str, base: int = 0, size: int = PACKED_SIZE) -> dict:
    query = urlencode({"source": source, "base": hex(base), "size": hex(size)})
    with urlopen(f"{url.rstrip('/')}/api/state?{query}", timeout=10) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result


def unpack_frame(data: bytes) -> Image.Image:
    if len(data) != PACKED_SIZE:
        raise ValueError(f"packed framebuffer size is {len(data)}, expected {PACKED_SIZE}")
    pixels = bytearray(WIDTH * HEIGHT)
    for index, value in enumerate(data):
        pixels[index * 2] = (value >> 4) * 17
        pixels[index * 2 + 1] = (value & 0x0f) * 17
    return Image.frombytes("L", (WIDTH, HEIGHT), bytes(pixels))


def lcd_frame(state: dict) -> Image.Image:
    data = base64.b64decode(state["frame"], validate=True)
    if len(data) != WIDTH * HEIGHT:
        raise ValueError(f"LCD frame size is {len(data)}, expected {WIDTH * HEIGHT}")
    pixels = bytes(round((value & 31) * 255 / 31) for value in data)
    return Image.frombytes("L", (WIDTH, HEIGHT), pixels)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="output filename prefix")
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--scale", type=int, default=4)
    args = parser.parse_args()
    if args.scale < 1:
        parser.error("scale must be positive")

    captures = {
        "lcd": lcd_frame(fetch(args.url, "lcd")),
        "back": unpack_frame(base64.b64decode(
            fetch(args.url, "memory", 0x500000)["frame"], validate=True
        )),
        "front": unpack_frame(base64.b64decode(
            fetch(args.url, "memory", 0x503840)["frame"], validate=True
        )),
        "root-entry-back": unpack_frame(base64.b64decode(
            fetch(args.url, "root-entry-back")["frame"], validate=True
        )),
        "root-entry-front": unpack_frame(base64.b64decode(
            fetch(args.url, "root-entry-front")["frame"], validate=True
        )),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for name, image in captures.items():
        if args.scale != 1:
            image = image.resize(
                (WIDTH * args.scale, HEIGHT * args.scale),
                Image.Resampling.NEAREST,
            )
        path = args.output.with_name(f"{args.output.name}-{name}.png")
        image.save(path)
        print(f"{name.upper()}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
