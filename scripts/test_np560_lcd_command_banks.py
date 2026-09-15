#!/usr/bin/env python3
"""Guest-MMIO checks of ST7529 EXT decoding and programmed gray registers.

No assumed PWM-to-optical curve; table assertions concern the digital register
contents only. RAM readback and visible output check cross-bank isolation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from test_np560_lcd_formats import byte_write, command, read_bytes, setup, write_bytes
from test_np560_mac import run

GRAY1 = [0, 2, 4, 8, 10, 12, 14, 16, 19, 21, 23, 24, 25, 27, 29, 31]
GRAY2 = list(range(31, 15, -1))
WIRE = [8, 64, 168]


def table_token(bank, values):
    return f"GRAY{bank}=" + ",".join(f"{v:02x}" for v in values) + " "


def initial():
    words = setup(mode=2, window=(0, 0, 20, 20))
    command(words, 0xBB, 1)
    command(words, 0xA7)
    write_bytes(words, WIRE)
    return words


def final_read(words):
    command(words, 0x30)
    read_bytes(words, 3)


def cases():
    words = initial()
    command(words, 0x31)
    write_bytes(words, [0xF8] * 3)  # 5C is RAMWR only in EXT=0.
    final_read(words)
    yield "ext1-does-not-enable-ramwr", words, WIRE, ()

    for name, invalid in (
        ("display-controls", [(0xA6,), (0xAE,), (0x95,)]),
        ("window-and-scan", [(0x15, 7, 7), (0x75, 43, 43),
                             (0xBC, 7, 1, 1), (0xBB, 6), (0xCA, 0, 39, 0)]),
        ("partial-and-scroll", [(0xA8, 0, 0), (0xAA, 0, 0, 0, 1), (0xAB, 4)]),
    ):
        words = initial()
        command(words, 0x31)
        for operation in invalid:
            command(words, *operation)
        final_read(words)
        yield f"ext1-isolates-{name}", words, WIRE, (
            "DISPLAY=on SLEEP=off INV=on EXT=0", "COM=1 DUTY=4 SCAN=00,00,02",
            "WINDOW=C0-0,L20-20")

    words = initial()
    command(words, 0x31)
    command(words, 0x20, *(v | 0xE0 for v in GRAY1))
    command(words, 0x21, *GRAY2)
    final_read(words)
    yield "gray-banks-16-entries-unused-bits", words, WIRE, (
        table_token(1, GRAY1), table_token(2, GRAY2), "PWM=unmodeled")

    words = initial()
    command(words, 0x31)
    command(words, 0x20, *GRAY1)
    command(words, 0x21, *GRAY2)
    command(words, 0x30)
    command(words, 0x20, 7)  # Power control, not gray1[0].
    command(words, 0x21, *([0] * 16))  # Not Gray2 in this bank.
    final_read(words)
    yield "ext0-does-not-overwrite-gray-registers", words, WIRE, (
        table_token(1, GRAY1), table_token(2, GRAY2))

    words = initial()
    command(words, 0x31)
    command(words, 0x20, *GRAY1)
    command(words, 0x21, *GRAY2)
    command(words, 0x20, *GRAY2)
    # Extra data past PB16 does not wrap to index zero or spill into GRAM.
    for value in (1, 2, 3):
        byte_write(words, True, value)
    final_read(words)
    yield "gray-complete-reprogram-and-extra-data", words, WIRE, (
        table_token(1, GRAY2), table_token(2, GRAY2))

    words = initial()
    command(words, 0x31)
    command(words, 0x20, *GRAY1[:15])
    # This asserts reception progress, not undocumented partial-table commit.
    yield "gray-receives-sixteenth-parameter", words, [], ("EXT=1 CMD=20", "PARAM=15/16")

    words = initial()
    command(words, 0x31)
    command(words, 0x32, 7, 2, 5)
    yield "analog-command-parameter-length", words, [], ("EXT=1 CMD=32", "PARAM=3/3")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--first-only", action="store_true")
    parser.add_argument("--icount", type=int)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"qemu_sha256": identity, "passed": False, "cases": []}
    frame = bytearray(240 * 120)
    frame[119 * 240:119 * 240 + 3] = bytes([1, 8, 21])
    try:
        for name, words, expected, state in cases():
            report["cases"].append(run(
                args.qemu, args.output, name, words,
                {3: 0x2400 + len(expected) * 2, 15: 0x4000},
                expected_data=expected or None, expected_lcd=bytes(frame),
                expected_lcd_state=state or None, icount=args.icount,
                metadata={"optical_pwm_mapping_tested": False,
                          "datasheet": "ST7529 v1.8 pp36-38,50"}))
            if args.first_only:
                break
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
        report["passed"] = True
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
