#!/usr/bin/env python3
"""Render pixel-group permutations for an NP560 toolbar capture."""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

from PIL import Image, ImageDraw


WIDTH = 240
HEIGHT = 22
SCALE = 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--select",
        help="render one four-digit permutation instead of the contact sheet",
    )
    parser.add_argument(
        "--mapping",
        choices=("normal", "reverse", "halves", "pairs"),
        help="render one regular mapping instead of four-pixel permutations",
    )
    parser.add_argument("--group-size", type=int, default=4)
    parser.add_argument("--phase", type=int, default=0)
    parser.add_argument(
        "--y-mapping",
        choices=("normal", "reverse", "halves", "pairs"),
        default="normal",
    )
    parser.add_argument("--y-group-size", type=int, default=1)
    parser.add_argument("--y-phase", type=int, default=0)
    parser.add_argument("--scale", type=int, default=SCALE)
    args = parser.parse_args()

    source = Image.open(args.source).convert("L")
    if source.width % WIDTH or source.height < HEIGHT * source.width // WIDTH:
        raise ValueError("source is not an integer-scaled 240-pixel LCD capture")
    input_scale = source.width // WIDTH
    toolbar = source.crop((0, 0, source.width, HEIGHT * input_scale)).resize(
        (WIDTH, HEIGHT), Image.Resampling.NEAREST
    )

    if args.scale <= 0:
        raise ValueError("scale must be positive")
    if args.y_group_size <= 0 or args.y_group_size > HEIGHT:
        raise ValueError("Y group size must be between 1 and 22")
    if args.y_mapping == "halves" and args.y_group_size % 2:
        raise ValueError("Y half swapping requires an even group size")
    if args.mapping:
        if args.group_size <= 0 or args.group_size > WIDTH:
            raise ValueError("group size must be between 1 and 240")
        if args.mapping == "halves" and args.group_size % 2:
            raise ValueError("half swapping requires an even group size")
        permutations = [None]
        columns = rows = 1
    elif args.select:
        if sorted(args.select) != list("0123"):
            raise ValueError("selected permutation must contain 0, 1, 2, 3")
        permutations = [tuple(int(item) for item in args.select)]
        columns = rows = 1
    else:
        permutations = list(itertools.permutations(range(4)))
        columns, rows = 3, 8
    cell_width = WIDTH * args.scale
    cell_height = HEIGHT * args.scale + 18
    sheet = Image.new("L", (cell_width * columns, cell_height * rows), 255)
    draw = ImageDraw.Draw(sheet)
    for item, permutation in enumerate(permutations):
        candidate = Image.new("L", (WIDTH, HEIGHT), 255)
        if args.mapping:
            for y in range(HEIGHT):
                y_group, y_pixel = divmod(y - args.y_phase, args.y_group_size)
                if args.y_mapping == "normal":
                    source_y_pixel = y_pixel
                elif args.y_mapping == "reverse":
                    source_y_pixel = args.y_group_size - 1 - y_pixel
                elif args.y_mapping == "halves":
                    source_y_pixel = (
                        y_pixel + args.y_group_size // 2
                    ) % args.y_group_size
                else:
                    source_y_pixel = y_pixel ^ 1
                source_y = (
                    y_group * args.y_group_size + source_y_pixel + args.y_phase
                )
                for x in range(WIDTH):
                    group, pixel = divmod(x - args.phase, args.group_size)
                    if args.mapping == "normal":
                        source_pixel = pixel
                    elif args.mapping == "reverse":
                        source_pixel = args.group_size - 1 - pixel
                    elif args.mapping == "halves":
                        source_pixel = (pixel + args.group_size // 2) % args.group_size
                    else:
                        source_pixel = pixel ^ 1
                    source_x = group * args.group_size + source_pixel + args.phase
                    if 0 <= source_x < WIDTH and 0 <= source_y < HEIGHT:
                        candidate.putpixel(
                            (x, y), toolbar.getpixel((source_x, source_y))
                        )
            label = (
                f"X={args.mapping}{args.group_size}/p{args.phase} "
                f"Y={args.y_mapping}{args.y_group_size}/p{args.y_phase}"
            )
        else:
            for y in range(HEIGHT):
                for x in range(0, WIDTH, 4):
                    pixels = [toolbar.getpixel((x + index, y)) for index in range(4)]
                    for destination, source_index in enumerate(permutation):
                        candidate.putpixel((x + destination, y), pixels[source_index])
            label = f"{item:02d}: {''.join(str(index) for index in permutation)}"
        candidate = candidate.resize(
            (WIDTH * args.scale, HEIGHT * args.scale), Image.Resampling.NEAREST
        )
        column = item % columns
        row = item // columns
        left = column * cell_width
        top = row * cell_height
        sheet.paste(candidate, (left, top))
        draw.text(
            (left + 4, top + HEIGHT * args.scale + 2),
            label,
            fill=0,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
