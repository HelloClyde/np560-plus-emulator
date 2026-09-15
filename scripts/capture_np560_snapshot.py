#!/usr/bin/env python3
"""Capture an NP560 Web/QEMU LCD frame and compact diagnostic sidecar."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from PIL import Image


DIAGNOSTIC_PREFIXES = (
    "PC=", "STACK_CHAIN=", "IRQ64=", "IRQ_REPEAT=", "FAR_COPY_IRQ=",
    "FAR_COPY_CALLS=", "APPLICATION_STATE=", "STORAGE_GEOMETRY=",
    "RESOURCE_CANDIDATES=", "RESOURCE_IO=", "FAR_COPY_BAD=",
    "INVALID_CONTROL=", "HARDWARE_INIT_RETURN=", "ROM_MISSING=", "HLE_FB=",
    "APPLICATION_STATE_WRITE=", "RESOURCE_RECOVERY_WORD=", "EVENT_STATE=",
    "IRQ64=", "TIMER64=", "NATIVE_REFRESH=", "MENU_OVERLAY_COPY=",
    "APPLICATION_TRACE=", "FILE_ATTACH_FRAME=",
)


def fetch_state(url: str, timeout: float) -> dict[str, Any]:
    with urlopen(f"{url.rstrip('/')}/api/state", timeout=timeout) as response:
        state = json.load(response)
    if not isinstance(state, dict) or "error" in state:
        raise ValueError(f"invalid Web/QEMU state: {state!r}")
    return state


def decode_gray5(state: dict[str, Any]) -> Image.Image:
    if state.get("format") != "gray5":
        raise ValueError(f"LCD capture requires gray5, got {state.get('format')!r}")
    width = int(state["width"])
    height = int(state["height"])
    raw = base64.b64decode(state["frame"], validate=True)
    if len(raw) != width * height:
        raise ValueError(
            f"LCD frame is {len(raw)} bytes, expected {width * height}"
        )
    # Match the Web's explicit optical-darkness contract, not controller codes:
    # 0 is unpowered/light and 31 is dark. PNG luminance runs the other way.
    pixels = bytes(round((31 - (value & 31)) * 255 / 31) for value in raw)
    return Image.frombytes("L", (width, height), pixels)


def compact_diagnostics(registers: str) -> list[str]:
    return [
        line for line in registers.splitlines()
        if line.startswith(DIAGNOSTIC_PREFIXES)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--scale", type=int, default=4)
    args = parser.parse_args()
    if args.scale < 1:
        parser.error("--scale must be at least 1")

    state = fetch_state(args.url, args.timeout)
    image = decode_gray5(state)
    if args.scale != 1:
        image = image.resize(
            (image.width * args.scale, image.height * args.scale),
            Image.Resampling.NEAREST,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)

    sidecar = args.output.with_suffix(".json")
    sidecar.write_text(json.dumps({
        "url": args.url,
        "running": state.get("running"),
        "status": state.get("status"),
        "lcd_state": state.get("lcd_state"),
        "nand_state": state.get("nand_state"),
        "soc_rom_configured": state.get("soc_rom_configured"),
        "soc_rom_size": state.get("soc_rom_size"),
        "soc_rom_sha256": state.get("soc_rom_sha256"),
        "diagnostics": compact_diagnostics(str(state.get("registers", ""))),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PNG {args.output}")
    print(f"STATE {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
