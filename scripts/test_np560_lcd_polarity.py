#!/usr/bin/env python3
"""Check NP560 positive-glass output polarity without changing stored pixels.

The original driver writes packed ink 15 as F0 with DISINV selected; the
positive-mode panel must show that ink dark and packed background 0 light.
ST7529 DISNOR/DISINV must still complement the output, never the RAM readback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from test_np560_lcd_formats import command, read_bytes, setup, write_bytes
from test_np560_mac import run


def cases():
    pixels = (0, 30, 31, 1, 8, 21)
    wire = [p << 3 for p in pixels]
    for name, commands, mode in (
        ("factory-disinv-ink-background", [(0xA7,)], "inverse"),
        ("disnor-complements-output", [(0xA7,), (0xA6,)], "normal"),
        ("disinv-restores-output", [(0xA7,), (0xA6,), (0xA7,)], "inverse"),
        ("display-off-is-unpowered-glass", [(0xA7,), (0xAE,)], "off"),
        ("sleep-is-unpowered-glass", [(0xA7,), (0x95,)], "off"),
        ("sleep-out-retains-polarity", [(0xA7,), (0x95,), (0x94,)], "inverse"),
        ("partial-undriven-is-not-inverted", [(0xA8, 5, 5), (0xA6,)], "partial"),
    ):
        words = setup(mode=2, window=(0, 1, 20, 20))
        command(words, 0xBB, 1)
        write_bytes(words, wire)
        expected = []
        for operation in commands:
            command(words, *operation)
            read_bytes(words, len(wire))
            expected.extend(wire)
        # Export contract is optical darkness: 0=unpowered/light, 31=dark.
        frame = bytearray([31 if mode == "normal" else 0] * (240 * 120))
        if mode == "partial":
            frame[116 * 240:] = bytes([31]) * (4 * 240)
        if mode != "off":
            observed_row = pixels if mode == "inverse" else (31, 1, 0, 30, 23, 10)
            frame[119 * 240:119 * 240 + 6] = bytes(observed_row)
        yield name, words, expected, bytes(frame)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--first-only", action="store_true")
    parser.add_argument("--icount", type=int)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"passed": False, "qemu_sha256": digest, "cases": []}
    try:
        for name, words, expected, frame in cases():
            report["cases"].append(run(
                args.qemu, args.output, name, words,
                {3: 0x2400 + len(expected) * 2, 15: 0x4000},
                expected_data=expected, expected_lcd=frame, icount=args.icount,
                metadata={"encoding": "gray5-darkness", "firmware_ink": "F0 with A7",
                          "ram_readback_after_every_command": True}))
            if args.first_only:
                break
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == digest
        report["passed"] = True
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
