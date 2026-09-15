#!/usr/bin/env python3
"""Guest-MMIO ST7529 partial display, retained RAM and status-register checks."""
from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import hashlib
import json
from pathlib import Path

from test_np560_lcd_formats import command, read_bytes, setup, write_bytes
from test_np560_mac import run


LINES = (19, 20, 23, 24, 39, 40, 43, 44, 71, 72, 75, 76, 136, 139, 140, 159)
PIXELS = (1, 8, 21)


def partial_case(qemu, output, name, commands, band, *, li=0, inverse=False,
                 hidden_write=False):
    words = setup(mode=2, window=(0, 0, 0, 159))
    command(words, 0xCA, 0, 39, 0)  # Full 160-line controller duty.
    command(words, 0xBB, 1)
    command(words, 0xBC, li, 0, 2)
    for line in LINES:
        command(words, 0x75, line, line)
        write_bytes(words, [p << 3 for p in PIXELS])
    for cmd in commands:
        command(words, *cmd)
    if hidden_write:
        command(words, 0x75, 76, 76)
        write_bytes(words, [0xF8, 0x30, 0x48])
        if band is None:
            command(words, 0xA9)

    # Reads must retain all pixels, including those hidden by PTLIN.
    expected_data = []
    for line in LINES:
        command(words, 0x75, line, line)
        read_bytes(words, 3)
        pixels = (31, 6, 9) if hidden_write and line == 76 else PIXELS
        expected_data.extend(p << 3 for p in pixels)

    frame = bytearray(240 * 120)
    for y in range(120):
        # Existing COMSCN=1 glass contract. LI reverses all 160 RAM lines.
        line = y + 20 if li else 139 - y
        if band is not None and not band[0] <= line <= band[1]:
            continue
        if not inverse:
            frame[y * 240:(y + 1) * 240] = bytes([31]) * 240
        if line in LINES:
            pixels = (31, 6, 9) if hidden_write and line == 76 else PIXELS
            frame[y * 240:y * 240 + 3] = bytes(
                p if inverse else 31 - p for p in pixels)
    annunciators = bytearray(60)
    for plane, line in enumerate((19, 140) if not li else (140, 19)):
        if band is None or band[0] <= line <= band[1]:
            annunciators[plane * 30] = 7
    return run(qemu, output, name, words,
               {3: 0x2400 + 2 * len(expected_data), 15: 0x4000},
               expected_data=expected_data, expected_lcd=bytes(frame),
               expected_annunciators=bytes(annunciators),
               metadata={"device": "ST7529", "partial_band_lines": band,
                         "inverse": inverse, "li": li,
                         "write_hidden_gram": hidden_write})


def status_case(qemu, output):
    words = setup(mode=2)
    expected = []
    for commands, value in (
            ([], 0xCA),  # Reset scroll mode=whole, display on, normal.
            ([(0xBC, 4, 0, 2)], 0xDA),
            ([(0xA8, 10, 18)], 0xDB),
            ([(0xA7,)], 0xD9),
            ([(0xAE,)], 0xD1),
            ([(0xAA, 0, 39, 39, 1)], 0x51),
            ([(0xA9,)], 0x50),
            ([(0xBC, 0, 0, 2)], 0x40),
            ([(0xAF,), (0xA6,)], 0x4A)):
        for cmd in commands:
            command(words, *cmd)
        command(words, 0x25)  # NOP selects the normal STREAD register.
        words.extend([0x2940, 0x1944, 0x1A34])  # Read A0=0, store in RAM.
        expected.append(value)
    return run(qemu, output, "status-register-bits", words,
               {3: 0x2400 + 2 * len(expected), 15: 0x4000},
               expected_data=expected)


CASES = [
    ("partial-blocks-10-through-18", [(0xA8, 10, 18)], (40, 75), {}),
    ("single-four-line-block", [(0xA8, 5, 5)], (20, 23), {}),
    ("partial-out-restores-gram", [(0xA8, 10, 18), (0xA9,)], None, {}),
    ("partial-with-line-inverse", [(0xA8, 10, 18)], (40, 75), {"li": 1}),
    ("partial-with-optical-inverse", [(0xA8, 10, 18), (0xA7,)],
     (40, 75), {"inverse": True}),
    ("partial-unused-parameter-bits", [(0xA8, 0xCA, 0xD2)], (40, 75), {}),
    ("out-of-range-preserves-partial", [(0xA8, 10, 18), (0xA8, 40, 44)],
     (40, 75), {}),
    ("out-of-range-preserves-full", [(0xA8, 40, 44)], None, {}),
    ("partial-status-electrodes", [(0xA8, 35, 35)], (140, 143), {}),
    ("hidden-gram-write", [(0xA8, 10, 18)], (40, 75), {"hidden_write": True}),
    ("partial-out-reveals-hidden-write", [(0xA8, 10, 18)], None,
     {"hidden_write": True}),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--first-only", action="store_true")
    parser.add_argument("--status-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"qemu_sha256": identity, "passed": False, "cases": []}
    try:
        if not args.status_only:
            for name, commands, band, options in CASES:
                report["cases"].append(partial_case(
                    args.qemu, args.output, name, commands, band, **options))
                if args.first_only:
                    break
        if not args.first_only:
            report["cases"].append(status_case(args.qemu, args.output))
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
        report["passed"] = True
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
