#!/usr/bin/env python3
"""Check ASR's SB reset, including the negative-count ASL branch.

CN1916884A PDF pp. 57-58 initializes SB before testing count < 0.
An earlier ordinary SL produces the nonzero SB; no host guest-RAM writes,
NAND, reconstructed codec, or application-state injection is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from test_np560_dtu import read_sfr, read_word, write_word
from test_np560_mac import run


# name, input, signed byte count, expected result, expected SB
CASES = (
    ("negative-one", 0x1234, -1, 0x2468, 0),
    ("negative-four-positive-saturation", 0x1234, -4, 0x7FFF, 0),
    ("negative-four-negative-saturation", 0xF234, -4, 0x8000, 0),
    ("negative-one-signed", 0xFFFE, -1, 0xFFFC, 0),
    ("negative-sixteen-zero", 0, -16, 0, 0),
    ("negative-128-zero", 0, -128, 0, 0),
    ("negative-128-positive", 1, -128, 0x7FFF, 0),
    ("negative-128-negative", 0x8000, -128, 0x8000, 0),
    ("zero-count", 0x1234, 0, 0x1234, 0),
    ("positive-one", 0x8001, 1, 0xC000, 0x8000),
    ("positive-two", 3, 2, 0, 0xC000),
    ("positive-sixteen", 0x8001, 16, 0xFFFF, 0x8001),
)


def check_case(qemu, output, case, icount):
    name, value, count, result, sb = case
    words = [0x6800, 2, 0x68FF, 0x6000,
             # SL R7,RB2 with count=16 leaves A55A in SB.
             0x68F7, 0xA55A, 0x68F1, 0x1000, 0x0C72,
             0x68F0, value, 0x68F1, (count & 255) << 8,
             0x4A02]  # ASR R0,RB2
    read_sfr(words, 2, 2)
    # Both consumers must observe the new SB, not the earlier SL's bits.
    words += [0x4830, 0x5C30, 0x4840, 0x5D40]
    return run(qemu, output, f"{name}-icount{icount}", words,
               {0: result, 2: sb, 3: sb, 4: sb, 7: 0, 15: 0x6000},
               icount=icount,
               metadata={"input": value, "signed_count": count,
                         "prior_sb": 0xA55A, "expected_sb": sb,
                         "source": "CN1916884A PDF pp.57-58"})


def check_original(qemu, output, original, icount):
    # Entire original near-frame/far-return function at source 4E:8ABC.
    # It clears a bit in a table using ASR R0,RB7; SROSB R1,RB7, with
    # a count in 0..15. This is a positive/zero-count regression, NOT
    # evidence that the negative-count defect is hit by this application.
    start, end = 0x4E8ABC, 0x4E8B6A
    body = original.read_bytes()[start - 0x200000:end - 0x200000]
    expected_hash = "673873c842ad2ecf57b79141fe606d3b23d684fd47e3fc80a2a7659e54d5fd08"
    assert hashlib.sha256(body).hexdigest() == expected_hash
    words = [0x6800, 2, 0x68FF, 0x6000, 0x68FB, 0x5500,
             0x6810, 0xA2, 0x6811, 1]
    write_word(words, 0x27EE, 0xFFFF, banked=True)
    words += [0x68F1, 0x1111, 0x68F2, 0x2222, 0x68F3, 0x3333,
              0x68F0, 0x23, 0x58F0, 0xBD4E, 0x8ABC, 0x50F2]
    read_word(words, 0x27EE, 4, banked=True)
    return run(qemu, output, f"original-bit-clear-icount{icount}", words,
               {0: 1, 1: 0x1111, 2: 0x2222, 3: 0x3333, 4: 0xEFFF,
                11: 0x5500, 15: 0x6000},
               tail=(start - 0x200000, body), icount=icount,
               metadata={"source_function": "4E:8ABC..8B68",
                         "function_bytes": len(body),
                         "function_sha256": expected_hash,
                         "negative_count_path_exercised": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = {"qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
                "prg_sha256": hashlib.sha256(args.original_prg.read_bytes()).hexdigest()}
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    results = []
    for icount in ((None,) if args.first_only else (None, 5)):
        for case in (CASES[:1] if args.first_only else CASES):
            results.append(check_case(args.qemu, args.output, case, icount))
        if not args.first_only:
            results.append(check_original(args.qemu, args.output, args.original_prg, icount))
    (args.output / "report.json").write_text(json.dumps({
        "identity": identity, "passed": all(r["passed"] for r in results),
        "results": results}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
