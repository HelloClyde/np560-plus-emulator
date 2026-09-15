#!/usr/bin/env python3
"""Render and compare each byte/nibble interpretation of the NP560 toolbar.

This diagnostic is observer-only.  It fetches the captured serialized toolbar,
the completed SRAM object, and the LCD frame, then renders the plausible pixel
orders side by side.  Keeping this as a script makes candidate testing
repeatable while the DMA and CPU lane models are refined.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from PIL import Image, ImageDraw


WIDTH = 240
HEIGHT = 22
HEADER = 10
OBJECT_BYTES = HEADER + WIDTH * HEIGHT // 2


def fetch(url: str, source: str, base: int = 0, size: int = 1) -> bytes:
    query = urlencode({"source": source, "base": hex(base), "size": hex(size)})
    with urlopen(f"{url.rstrip('/')}/api/state?{query}", timeout=10) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(result["error"])
    return base64.b64decode(result["frame"], validate=True)


def pair_swap(raw: bytes) -> bytes:
    result = bytearray(raw)
    for offset in range(0, len(result) - 1, 2):
        result[offset], result[offset + 1] = result[offset + 1], result[offset]
    return bytes(result)


def pixels(raw: bytes, byte_order: str, nibble_order: str) -> list[int]:
    body = raw[HEADER:OBJECT_BYTES]
    if byte_order == "pairs":
        body = pair_swap(body)
    elif byte_order == "reverse4":
        body = b"".join(
            body[offset:offset + 4][::-1]
            for offset in range(0, len(body), 4)
        )
    elif byte_order != "normal":
        raise ValueError(byte_order)

    result: list[int] = []
    for value in body:
        pair = (value >> 4, value & 15)
        if nibble_order == "lo-hi":
            pair = pair[::-1]
        elif nibble_order != "hi-lo":
            raise ValueError(nibble_order)
        result.extend(pair)
    return result


def binary(values: list[int]) -> list[bool]:
    # Toolbar data uses zero as white and nonzero values for outlines and ink.
    return [value != 0 for value in values]


def best_binary_alignment(candidate: list[int], lcd: bytes) -> tuple[int, int, int, bool]:
    expected = binary(candidate)
    best = (WIDTH * HEIGHT + 1, 0, 0, False)
    for invert in (False, True):
        observed = [(value < 16) ^ invert for value in lcd[:WIDTH * HEIGHT]]
        for dy in range(-2, 3):
            for dx in range(-4, 5):
                errors = samples = 0
                for y in range(HEIGHT):
                    sy = y + dy
                    if not 0 <= sy < HEIGHT:
                        continue
                    for x in range(WIDTH):
                        sx = x + dx
                        if not 0 <= sx < WIDTH:
                            continue
                        errors += expected[sy * WIDTH + sx] != observed[y * WIDTH + x]
                        samples += 1
                score = round(errors * WIDTH * HEIGHT / samples)
                best = min(best, (score, dx, dy, invert))
    return best


def render(values: list[int], scale: int = 3) -> Image.Image:
    image = Image.new("L", (WIDTH, HEIGHT))
    image.putdata([255 - value * 17 for value in values])
    return image.resize((WIDTH * scale, HEIGHT * scale), Image.Resampling.NEAREST)


def nand_toolbar(path: Path) -> bytes:
    """Extract sectors FB789..FB78E from their observed physical FTL block."""
    image = path.read_bytes()
    physical_block = 0x490

    def sector(logical: int) -> bytes:
        page = physical_block * 64 + ((logical & 0xFF) >> 2)
        column = (logical & 3) * 512
        # Checkpoints have a fixed 64-byte header followed by the compact
        # 2048-byte data plane; OOB bytes live in a separate trailing plane.
        offset = 64 + page * 2048 + column
        return image[offset:offset + 512]

    chunks = [sector(logical) for logical in range(0xFB789, 0xFB78F)]
    return chunks[0][0xCF:] + b"".join(chunks[1:5]) + chunks[5][:0x129]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dump-dir", type=Path)
    parser.add_argument("--nand", type=Path)
    args = parser.parse_args()

    source = fetch(args.url, "root-top-source", size=OBJECT_BYTES)
    obj = fetch(args.url, "root-top-object", size=OBJECT_BYTES)
    lcd = fetch(args.url, "lcd", size=WIDTH * 120)
    staging = fetch(args.url, "memory", base=0x511000, size=0xA40)

    if args.dump_dir:
        args.dump_dir.mkdir(parents=True, exist_ok=True)
        (args.dump_dir / "root-top-source.bin").write_bytes(source)
        (args.dump_dir / "root-top-object.bin").write_bytes(obj)
        (args.dump_dir / "root-top-staging-511000.bin").write_bytes(staging)

    candidates: list[tuple[str, list[int], tuple[int, int, int, bool]]] = []
    inputs = [
        ("source", source),
        ("object", obj),
        ("object-pairs-to-logical", pair_swap(obj)),
    ]
    if args.nand:
        nand = nand_toolbar(args.nand)
        inputs.append(("nand-serialized", nand))
        if args.dump_dir:
            (args.dump_dir / "root-top-nand-serialized.bin").write_bytes(nand)
    for input_name, raw in inputs:
        for byte_order in ("normal", "pairs", "reverse4"):
            for nibble_order in ("hi-lo", "lo-hi"):
                name = f"{input_name} / {byte_order} / {nibble_order}"
                values = pixels(raw, byte_order, nibble_order)
                score = best_binary_alignment(values, lcd)
                candidates.append((name, values, score))

    candidates.sort(key=lambda item: item[2])
    scale = 3
    label_height = 20
    canvas = Image.new(
        "RGB", (WIDTH * scale, len(candidates) * (HEIGHT * scale + label_height)),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    for index, (name, values, score) in enumerate(candidates):
        top = index * (HEIGHT * scale + label_height)
        draw.text(
            (3, top + 3),
            f"{name}; mismatch={score[0]}/{WIDTH * HEIGHT} "
            f"dx={score[1]} dy={score[2]} invert={int(score[3])}",
            fill="black",
        )
        canvas.paste(render(values, scale).convert("RGB"), (0, top + label_height))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output)
    print(f"SOURCE_HEADER={source[:HEADER].hex()}")
    print(f"OBJECT_HEADER={obj[:HEADER].hex()}")
    for name, _values, score in candidates:
        print(
            f"MISMATCH={score[0]:4d}/{WIDTH * HEIGHT} DX={score[1]:+d} "
            f"DY={score[2]:+d} INV={int(score[3])} {name}"
        )
    print(f"OUTPUT={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
