#!/usr/bin/env python3
"""Capture the native ST7529 frame exposed by the NP560 Web bridge."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

from PIL import Image


LCD_OFF = (0xB7, 0xC8, 0xA1)
LCD_ON = (0x24, 0x31, 0x26)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765/api/state")
    parser.add_argument(
        "--input-gray5", type=Path,
        help="render a local 240x120 gray5 capture instead of querying Web",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scale", type=int, default=4)
    args = parser.parse_args()

    if args.input_gray5:
        state = {"format": "gray5", "width": 240, "height": 120}
        frame = args.input_gray5.read_bytes()
    else:
        with urlopen(args.url, timeout=10) as response:
            state = json.load(response)
        if state.get("format") != "gray5":
            raise SystemExit(
                f"unexpected frame format: {state.get('format')!r}"
            )
        frame = base64.b64decode(state["frame"], validate=True)
    width = int(state["width"])
    height = int(state["height"])
    if len(frame) != width * height:
        raise SystemExit(
            f"unexpected frame size: {len(frame)} != {width * height}"
        )

    pixels = []
    for raw in frame:
        level = (raw & 31) / 31
        pixels.append(tuple(
            round(off + (on - off) * level)
            for off, on in zip(LCD_OFF, LCD_ON)
        ))
    image = Image.new("RGB", (width, height))
    image.putdata(pixels)
    if args.scale > 1:
        image = image.resize(
            (width * args.scale, height * args.scale),
            Image.Resampling.NEAREST,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)

    levels = sorted({value & 31 for value in frame})
    active = sum((value & 31) != 0 for value in frame)
    print(f"wrote {args.output.resolve()}")
    print(
        f"FRAME={width}x{height} ACTIVE={active}/{len(frame)} "
        f"LEVELS={','.join(map(str, levels))} "
        f"SHA256={hashlib.sha256(frame).hexdigest()}"
    )
    print(str(state.get("lcd_state", "")).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
