#!/usr/bin/env python3
"""Compare an NP560 packed framebuffer with the visible ST7529 pixels.

This is an observer-only geometry check.  It does not inject keys or alter the
emulator.  The score is calculated from non-background pixel masks so the
firmware's 4-bit framebuffer can be compared with the controller's 5-bit GRAM.
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
PACKED_SIZE = WIDTH * HEIGHT // 2


def fetch(url: str, source: str, base: int = 0, size: int = PACKED_SIZE) -> dict:
    query = urlencode({"source": source, "base": hex(base), "size": hex(size)})
    with urlopen(f"{url.rstrip('/')}/api/state?{query}", timeout=10) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result


def unpack_nibbles(data: bytes) -> list[list[int]]:
    if len(data) != PACKED_SIZE:
        raise ValueError(f"packed framebuffer has {len(data)} bytes")
    rows = [[0] * WIDTH for _ in range(HEIGHT)]
    for index, value in enumerate(data):
        y, x = divmod(index * 2, WIDTH)
        rows[y][x] = value >> 4
        rows[y][x + 1] = value & 15
    return rows


def unpack_lcd(data: bytes) -> list[list[int]]:
    if len(data) != WIDTH * HEIGHT:
        raise ValueError(f"LCD frame has {len(data)} bytes")
    return [list(data[y * WIDTH:(y + 1) * WIDTH]) for y in range(HEIGHT)]


def transformed_x(x: int, reverse_triplets: bool, phase: int) -> int:
    if not reverse_triplets:
        return x
    group, pixel = divmod(x - phase, 3)
    return group * 3 + (2 - pixel) + phase


def score(
    lcd: list[list[int]], framebuffer: list[list[int]], *, y_flip: bool,
    reverse_triplets: bool, phase: int, dx: int, dy: int,
) -> tuple[int, int, int, int]:
    same = false_positive = false_negative = total = 0
    for y in range(HEIGHT):
        sy = (HEIGHT - 1 - y if y_flip else y) + dy
        if not 0 <= sy < HEIGHT:
            continue
        for x in range(WIDTH):
            sx = transformed_x(x, reverse_triplets, phase) + dx
            if not 0 <= sx < WIDTH:
                continue
            # INV=on makes blank LCD pixels 31; the packed buffer uses zero.
            lcd_on = lcd[y][x] != 31
            fb_on = framebuffer[sy][sx] != 0
            total += 1
            if lcd_on == fb_on:
                same += 1
            elif lcd_on:
                false_positive += 1
            else:
                false_negative += 1
    return same, total, false_positive, false_negative


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--base", type=lambda value: int(value, 0), default=0x503840)
    parser.add_argument("--source", choices=("memory", "data"), default="memory")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output-prefix", type=Path)
    parser.add_argument(
        "--swap-row-pairs", default="",
        help="comma-separated half-open Y ranges to preview adjacent-row swaps",
    )
    args = parser.parse_args()

    lcd = unpack_lcd(base64.b64decode(fetch(args.url, "lcd")["frame"], validate=True))
    framebuffer = unpack_nibbles(base64.b64decode(
        fetch(args.url, args.source, args.base)["frame"], validate=True
    ))

    results = []
    for y_flip in (False, True):
        for reverse_triplets in (False, True):
            for phase in range(3):
                if not reverse_triplets and phase:
                    continue
                for dy in range(-3, 4):
                    for dx in range(-3, 4):
                        values = score(
                            lcd, framebuffer, y_flip=y_flip,
                            reverse_triplets=reverse_triplets, phase=phase,
                            dx=dx, dy=dy,
                        )
                        results.append((*values, y_flip, reverse_triplets, phase, dx, dy))
    results.sort(key=lambda item: (item[0] / item[1], -item[2] - item[3]), reverse=True)
    print(f"SOURCE={args.source}:0x{args.base:06x}")
    for same, total, fp, fn, y_flip, triplets, phase, dx, dy in results[:args.limit]:
        print(
            f"MATCH={same / total:.6f} SAME={same}/{total} FP={fp} FN={fn} "
            f"YFLIP={int(y_flip)} TRIPLET_REVERSE={int(triplets)} "
            f"PHASE={phase} DX={dx:+d} DY={dy:+d}"
        )
    if args.output_prefix:
        args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
        original = Image.new("L", (WIDTH, HEIGHT))
        corrected = Image.new("L", (WIDTH, HEIGHT))
        native = Image.new("L", (WIDTH, HEIGHT))
        for y in range(HEIGHT):
            for x in range(WIDTH):
                original.putpixel((x, y), round(lcd[y][x] * 255 / 31))
                corrected.putpixel(
                    (x, y),
                    round(lcd[y][transformed_x(x, True, 0)] * 255 / 31),
                )
                native.putpixel(
                    (x, y), framebuffer[HEIGHT - 1 - y][x] * 17,
                )
        for suffix, image in (
            ("lcd-original", original),
            ("lcd-triplet-corrected", corrected),
            ("framebuffer-yflip", native),
        ):
            image = image.resize((WIDTH * 4, HEIGHT * 4), Image.Resampling.NEAREST)
            path = args.output_prefix.with_name(f"{args.output_prefix.name}-{suffix}.png")
            image.save(path)
            print(f"{suffix.upper()}={path}")
        if args.swap_row_pairs:
            row_pair_preview = original.copy()
            for item in args.swap_row_pairs.split(","):
                start_text, end_text = item.split(":", 1)
                start, end = int(start_text, 0), int(end_text, 0)
                if not 0 <= start < end <= HEIGHT or (end - start) & 1:
                    raise ValueError(f"invalid even-sized row range: {item}")
                for y in range(start, end, 2):
                    upper = row_pair_preview.crop((0, y, WIDTH, y + 1))
                    lower = row_pair_preview.crop((0, y + 1, WIDTH, y + 2))
                    row_pair_preview.paste(lower, (0, y))
                    row_pair_preview.paste(upper, (0, y + 1))
            row_pair_preview = row_pair_preview.resize(
                (WIDTH * 4, HEIGHT * 4), Image.Resampling.NEAREST
            )
            path = args.output_prefix.with_name(
                f"{args.output_prefix.name}-lcd-row-pair-preview.png"
            )
            row_pair_preview.save(path)
            print(f"LCD-ROW-PAIR-PREVIEW={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
