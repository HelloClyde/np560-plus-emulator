#!/usr/bin/env python3
"""Execute the original post-decoder channel selector for all four flag inputs.

This isolates 16:EA20..EA40, not the decoder, whole callback or DAC. Guest
instructions supply pointers and flags; no NAND or live-instance RAM edits.
The meaning and producer of F006.bit11 are intentionally not assumed.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import hashlib
import itertools
import json
import struct

from test_np560_mac import run

PRG_SHA = "d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5"
SLICE_SHA = "fd739036e8d28cd91c510d37ce3ca0255beec6ebde2e2f78ae7cee4c8b4cce20"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = args.original_prg.read_bytes()
    assert hashlib.sha256(original).hexdigest() == PRG_SHA
    code = original[0x13EA20:0x13EA42]
    assert hashlib.sha256(code).hexdigest() == SLICE_SHA
    rom = bytearray(b"\x00\x0f" * (0x16EA58 // 2))
    rom[0x16EA20:0x16EA42] = code
    # Near-return original selector needs a diagnostic far-call wrapper.
    rom[0x16EA50:0x16EA58] = struct.pack("<4H", 0xBC00, 0xEA20, 0xC620, 0xD0FF)
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"passed": False, "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
              "prg_sha256": PRG_SHA, "slice_sha256": SLICE_SHA, "cases": [],
              "flag_producer_verified": False, "full_player_verified": False}
    try:
        for b11, b15, b5, b6 in itertools.product((0, 1), repeat=4):
            stereo = bool(b11 and b15 and not b5 and not b6)
            initial = (b5 << 5) | (b6 << 6)
            # JBC clears only the first encountered set bit, only if both
            # BCMP operands were one. Check this side effect as well.
            remaining = initial
            if b11 and b15:
                remaining &= ~(0x20 if b5 else 0x40)
            words = [0x6800, 0x0002, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 0,
                     0x68F0, b11 << 11, 0x3F10, 0xA8F0, 0xF006,
                     0x68F0, b15 << 15, 0x3F10, 0xA8F0, 0xF002,
                     0x68F0, initial, 0x3F10, 0xA8F0, 0xF018,
                     0x68F0, 0x1784, 0xA8F0, 0x4A7C,
                     0x68F0, 0x1C04, 0xA8F0, 0x4A80,
                     0xBD16, 0xEA50, 0x3F10, 0x88F4, 0xF018]
            expected = {1: 0x1784, 2: 0x1C04 if stereo else 0x1784,
                        4: remaining, 15: 0x6000}
            name = f"flags-{b11}{b15}{b5}{b6}"
            report["cases"].append(run(args.qemu, args.output, name, words,
                expected, rom=rom, icount=0, expected_code=[(0x16EA20, code)],
                metadata={"F006_bit11": b11, "F002_bit15": b15,
                          "F018_bit5": b5, "F018_bit6": b6,
                          "distinct_pointers_expected": stereo}))
        report["passed"] = all(c["passed"] and c["exit_code"] == 0 for c in report["cases"])
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
