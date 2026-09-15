#!/usr/bin/env python3
"""Capture the current NP560 web LCD frame as a PNG image."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from urllib.request import urlopen

from PIL import Image


OFF = (0xB7, 0xC8, 0xA1)
ON = (0x24, 0x31, 0x26)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--api", default="http://127.0.0.1:8775/api/state")
    parser.add_argument("--scale", type=int, default=4)
    parser.add_argument(
        "--invert", action="store_true",
        help="apply the same additional polarity inversion as the Web UI",
    )
    args = parser.parse_args()

    with urlopen(args.api, timeout=5) as response:
        state = json.load(response)
    if state["format"] != "gray5" or state["width"] != 240 or state["height"] != 120:
        raise ValueError("API did not return a 240x120 gray5 LCD frame")
    frame = base64.b64decode(state["frame"], validate=True)
    if len(frame) != 240 * 120:
        raise ValueError("LCD frame has an unexpected byte count")

    pixels = bytearray()
    for byte in frame:
        level = byte & 31
        if args.invert:
            level = 31 - level
        mix = level / 31
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
