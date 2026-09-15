#!/usr/bin/env python3
"""Compare the NP560 root-menu labels with the resident 12x12 font table.

This is an observer-only diagnostic.  It reads the ST7529 frame and the
linked font window, then tries the plausible byte, bit, and row orders for the
ten fixed top-menu glyphs.  It does not inject keys or modify guest memory.
"""

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
FONT_BASE = 0x343960
FONT_BYTES = 24
LABELS = ("学习", "辞典", "网络", "记事", "系统")
X_ORIGINS = ((9, 22), (58, 71), (106, 119), (155, 168), (202, 215))


def fetch(url: str, source: str, base: int, size: int) -> bytes:
    query = urlencode({"source": source, "base": hex(base), "size": hex(size)})
    with urlopen(f"{url.rstrip('/')}/api/state?{query}", timeout=10) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(result["error"])
    return base64.b64decode(result["frame"], validate=True)


def gbk_address(character: str) -> tuple[int, int]:
    encoded = character.encode("gbk")
    if len(encoded) != 2 or not all(0xA1 <= value <= 0xFE for value in encoded):
        raise ValueError(f"{character!r} is not in the 94x94 GBK table")
    code = (encoded[0] << 8) | encoded[1]
    index = (encoded[0] - 0xA1) * 94 + encoded[1] - 0xA1
    return code, FONT_BASE + index * FONT_BYTES


def row_order(rows: list[int], order: str) -> list[int]:
    if order == "normal":
        return rows
    if order == "reverse":
        return list(reversed(rows))
    if order == "pairs":
        return [rows[index ^ 1] for index in range(len(rows))]
    if order == "reverse-pairs":
        rows = list(reversed(rows))
        return [rows[index ^ 1] for index in range(len(rows))]
    raise ValueError(order)


def glyph(raw: bytes, endian: str, order: str, bit_order: str,
          bit_offset: int) -> list[list[bool]]:
    rows = [int.from_bytes(raw[index:index + 2], endian)
            for index in range(0, FONT_BYTES, 2)]
    rows = row_order(rows, order)
    result = []
    for value in rows:
        bits = [bool(value & (1 << bit)) for bit in range(15, -1, -1)]
        if bit_order == "lsb":
            bits.reverse()
        result.append(bits[bit_offset:bit_offset + 12])
    return result


def source_x(x: int, order: str) -> int:
    """Return the source pixel for a four-pixel framebuffer word order."""
    group, pixel = divmod(x, 4)
    if order == "normal":
        return x
    if order == "byte-pairs":
        return group * 4 + ((pixel + 2) & 3)
    if order == "pair-reverse":
        return group * 4 + (pixel ^ 1)
    if order == "word-reverse":
        return group * 4 + (3 - pixel)
    raise ValueError(order)


def difference(frame: bytes, expected: list[list[bool]], x: int, y: int,
               inks: frozenset[int], pixel_order: str,
               split_y: int | None) -> int:
    return sum(
        (
            frame[
                (y + row) * WIDTH +
                source_x(
                    x + column,
                    pixel_order if split_y is None or y + row >= split_y
                    else "normal",
                )
            ] in inks
        ) != expected[row][column]
        for row in range(12) for column in range(12)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument(
        "--inks", default="1",
        help="comma-separated ST7529 gray values treated as glyph pixels",
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--preview", type=Path)
    parser.add_argument(
        "--preview-pixels",
        choices=("normal", "byte-pairs", "pair-reverse", "word-reverse"),
        default="pair-reverse",
    )
    parser.add_argument("--preview-split", type=int, default=10)
    args = parser.parse_args()
    inks = frozenset(int(value, 0) for value in args.inks.split(","))

    frame = fetch(args.url, "lcd", 0, WIDTH * HEIGHT)
    raw_glyphs = []
    for button, label in enumerate(LABELS):
        for character, origin in zip(label, X_ORIGINS[button]):
            code, address = gbk_address(character)
            raw_glyphs.append((character, code, address, origin,
                               fetch(args.url, "memory", address, FONT_BYTES)))

    candidates = []
    pixel_orders = ("normal", "byte-pairs", "pair-reverse", "word-reverse")
    split_rows = (None, *range(5, 18))
    font_candidates = []
    for endian in ("little", "big"):
        for order in ("normal", "reverse", "pairs", "reverse-pairs"):
            for bit_order in ("msb", "lsb"):
                for bit_offset in range(5):
                    total = 0
                    positions = []
                    for character, code, address, origin, raw in raw_glyphs:
                        expected = glyph(raw, endian, order, bit_order, bit_offset)
                        best = min(
                            (
                                difference(
                                    frame, expected, x, y, inks,
                                    "normal", None,
                                ),
                                x,
                                y,
                            )
                            for x in range(origin - 2, origin + 3)
                            for y in range(3, 8)
                        )
                        total += best[0]
                        positions.append((character, *best))
                    font_candidates.append((
                        total, endian, order, bit_order, bit_offset, positions,
                    ))

    # Pixel-order exploration is substantially larger than the font-table
    # search.  Retain the eight best baseline font interpretations; a bus-lane
    # permutation cannot make a poor row/bit interpretation into the winner.
    font_candidates.sort(key=lambda item: item[0])
    for (_baseline, endian, order, bit_order, bit_offset,
         _baseline_positions) in font_candidates[:8]:
                    for pixel_order in pixel_orders:
                        for split_y in split_rows if pixel_order != "normal" else (None,):
                            total = 0
                            positions = []
                            for character, code, address, origin, raw in raw_glyphs:
                                expected = glyph(
                                    raw, endian, order, bit_order, bit_offset
                                )
                                best = min(
                                    (
                                        difference(
                                            frame, expected, x, y, inks,
                                            pixel_order, split_y,
                                        ),
                                        x,
                                        y,
                                    )
                                    for x in range(origin - 2, origin + 3)
                                    for y in range(3, 8)
                                )
                                total += best[0]
                                positions.append((character, *best))
                            candidates.append((
                                total, endian, order, bit_order, bit_offset,
                                pixel_order, split_y, positions,
                            ))

    candidates.sort(key=lambda item: item[0])
    for (total, endian, order, bit_order, bit_offset, pixel_order, split_y,
         positions) in candidates[:args.limit]:
        compact = ",".join(
            f"{character}:{errors}@{x},{y}"
            for character, errors, x, y in positions
        )
        print(
            f"ERRORS={total:4d}/{len(raw_glyphs) * 144} "
            f"ENDIAN={endian:6s} ROWS={order:13s} BITS={bit_order} "
            f"OFFSET={bit_offset} PIXELS={pixel_order:12s} "
            f"SPLIT={split_y if split_y is not None else '-':>2} POS={compact}"
        )
    print("GLYPHS=" + ",".join(
        f"{character}/{code:04x}@{address:06x}:{raw.hex()}"
        for character, code, address, _origin, raw in raw_glyphs
    ))
    if args.preview:
        image = Image.new("L", (WIDTH, HEIGHT))
        for y in range(HEIGHT):
            order = (
                args.preview_pixels
                if y >= args.preview_split and y < 18
                else "normal"
            )
            for x in range(WIDTH):
                image.putpixel(
                    (x, y),
                    round(frame[y * WIDTH + source_x(x, order)] * 255 / 31),
                )
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        image.resize(
            (WIDTH * 4, HEIGHT * 4), Image.Resampling.NEAREST
        ).save(args.preview)
        print(f"PREVIEW={args.preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
