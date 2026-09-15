#!/usr/bin/env python3
"""Exercise ST7529 bus packing through guest MMIO, without NAND or HLE."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from test_np560_mac import run


def byte_write(words, data, value):
    words.extend([0x69F4, value, 0x0B14 if data else 0x0B04])


def command(words, value, *parameters):
    byte_write(words, False, value)
    for value in parameters:
        byte_write(words, True, value)


def setup(*, mode=1, scan=0, clr=0, window=(0, 1, 20, 21)):
    # R0/R1 select the two physical byte ports; R3 collects RAMRD results
    # in internal RAM. Only guest instructions write memory or registers.
    words = [0x6800, 2, 0x68FF, 0x4000, 0x6810, 0, 0x6811, 0x1E0,
             0x68F0, 0x8001, 0x68F1, 0x8003, 0x68F3, 0x2400]
    command(words, 0x30)
    command(words, 0x94)
    command(words, 0xAF)
    if mode is not None:
        command(words, 0xBC, scan, clr, mode)
    if window is not None:
        command(words, 0x15, *window[:2])
        command(words, 0x75, *window[2:])
    return words


def write_bytes(words, values):
    command(words, 0x5C)
    for value in values:
        byte_write(words, True, value)


def read_bytes(words, count):
    command(words, 0x5D)
    # ST7529 v1.8 section 7.2: first read fills the internal bus holder.
    # Its returned value is unspecified and must not be used as pixel data.
    words.append(0x2941)
    for _ in range(count):
        # MOVB RB4,[R1]; MOVZE R4,RB4; MOV [R3++],R4.
        words.extend([0x2941, 0x1944, 0x1A34])


def cases():
    # Fixed wire examples from the datasheet bit allocation, not an
    # implementation of the emulator's unpacker in the test oracle.
    packed = [0x0A, 0x35, 0x3C, 0xC2, 0xCE, 0x59, 0xF9, 0x89]
    # P0/P1/P2 per column group: (1,8,21),(7,19,2),(25,25,25),(31,6,9).
    pixels = [1, 8, 21, 7, 19, 2, 25, 25, 25, 31, 6, 9]
    words = setup()
    write_bytes(words, packed)
    command(words, 0xBC, 0, 0, 2)
    read_bytes(words, 12)
    yield "packed-write-three-byte-read", words, [p << 3 for p in pixels]

    words = setup(mode=2)
    write_bytes(words, [p << 3 for p in pixels])
    command(words, 0xBC, 0, 0, 1)
    read_bytes(words, 10)  # One extra group proves address-window wrap.
    canonical = [0x0A, 0x15, 0x3C, 0xC2, 0xCE, 0x59, 0xF9, 0x89]
    yield "three-byte-write-packed-read-wrap", words, canonical + canonical[:2]

    words = setup(scan=4)
    write_bytes(words, packed)
    command(words, 0xBC, 0, 0, 2)
    read_bytes(words, 12)
    ordered = pixels[:3] + pixels[6:9] + pixels[3:6] + pixels[9:]
    yield "packed-line-first-window", words, [p << 3 for p in ordered]

    words = setup(clr=1)
    write_bytes(words, packed)
    command(words, 0xBC, 0, 0, 2)
    read_bytes(words, 12)
    reversed_pixels = [p for i in range(0, 12, 3) for p in pixels[i:i+3][::-1]]
    yield "packed-clr-reversal", words, [p << 3 for p in reversed_pixels]

    words = setup(mode=2)
    write_bytes(words, [p << 3 for p in pixels])
    command(words, 0xBC, 0, 1, 1)
    read_bytes(words, 8)
    yield "packed-read-clr-reversal", words, [0xAA, 1, 0x14, 0xC7, 0xCE, 0x59, 0x49, 0x9F]

    words = setup(window=(0, 0, 20, 20))
    write_bytes(words, [0x0A, 0x15])
    command(words, 0x5C)
    byte_write(words, True, 0xFF)  # Not a complete 15-bit RAM write.
    command(words, 0xBC, 0, 0, 2)  # Cancels the incomplete pair.
    read_bytes(words, 3)
    yield "command-cancels-partial-write", words, [8, 64, 168]

    words = setup(window=(0, 0, 20, 20))
    write_bytes(words, [0xFF])
    write_bytes(words, [0x0A, 0x15])  # RAMWR itself restarts byte assembly.
    read_bytes(words, 1)  # Leave the packed read half consumed.
    read_bytes(words, 2)  # RAMRD restarts at the first byte.
    yield "command-restarts-write-and-read", words, [0x0A, 0x0A, 0x15]

    words = setup(mode=None, window=None)
    write_bytes(words, [0x0A, 0x15, 0x3C, 0xC2])
    command(words, 0xBC, 0, 0, 2)
    read_bytes(words, 6)
    yield "reset-default-format-and-window", words, [56, 152, 16] * 2

    words = setup(mode=0xF9, window=(84, 84, 159, 159))
    write_bytes(words, [0x0A, 0x15])
    command(words, 0xBC, 0, 0, 2)
    read_bytes(words, 6)
    yield "last-column-last-line-and-unused-mode-bits", words, [8, 64, 168] * 2

    words = setup(window=(0, 0, 20, 20))
    write_bytes(words, [0x0A, 0x15])
    command(words, 0xBC, 0, 0, 7)  # Reserved, not an alias for 3B3P.
    write_bytes(words, [0xFF] * 3)
    command(words, 0xBC, 0, 0, 2)
    read_bytes(words, 3)
    yield "reserved-format-does-not-reinterpret-pixels", words, [8, 64, 168]

    words = setup(mode=2)
    write_bytes(words, [p << 3 for p in pixels])
    read_bytes(words, 12)
    yield "existing-three-byte-mode", words, [p << 3 for p in pixels]

    words = setup(mode=2, window=(0, 0, 20, 20))
    write_bytes(words, [8, 64, 168])
    write_bytes(words, [0xF8, 0xF8])
    read_bytes(words, 3)  # A new command cancels the unfinished 3B3P group.
    write_bytes(words, [0xF8])
    command(words, 0xBC, 0, 0, 1)
    read_bytes(words, 2)
    yield "three-byte-partial-write-cancellation", words, [8, 64, 168, 0x0A, 0x15]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-only", action="store_true")
    parser.add_argument("--case", choices=[name for name, _, _ in cases()])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"qemu_sha256": identity, "passed": False, "cases": []}
    try:
        for name, words, expected in cases():
            if args.case is not None and name != args.case:
                continue
            report["cases"].append(run(
                args.qemu, args.output, name, words,
                {3: 0x2400 + 2 * len(expected), 15: 0x4000},
                expected_data=expected,
                metadata={"device": "ST7529", "interface": "8-bit MMIO"}))
            if args.first_only:
                break
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
        report["passed"] = True
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
