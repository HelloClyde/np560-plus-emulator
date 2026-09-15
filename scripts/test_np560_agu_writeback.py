#!/usr/bin/env python3
"""Check ordinary AGU writeback uses pre-instruction modifier state.

Guest instructions deliberately write the memory alias of XM0/XM2. These
are architectural boundary cases, not evidence that a factory application
uses this alias or that the MP3 decoder has been restored. No NAND/HLE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from test_np560_dtu import read_sfr, write_word
from test_np560_mac import run


CASES = {
    # name: opcode, old XM0, old XM2, X0, X2, R1, R0, expected XM0/XM2/X0/X2/R1
    "word-store-linear": (0x1A80, 0, 0, 0xF126, 0x2400, 0x2400, 1,
                          (1, 0, 0xF128, 0x2400, 0x2400)),
    "word-store-circular": (0x1A80, 8, 0, 0xF126, 0x2400, 0x2400, 0,
                            (0, 0, 0xF120, 0x2400, 0x2400)),
    "byte-store-linear": (0x1B80, 0, 0, 0xF127, 0x2400, 0x2400, 0x0100,
                          (1, 0, 0xF128, 0x2400, 0x2400)),
    "byte-store-circular": (0x1B80, 8, 0, 0xF127, 0x2400, 0x2400, 0,
                            (0, 0, 0xF120, 0x2400, 0x2400)),
    "copy-updates-source-modifier": (0x3A18, 8, 0, 0x2400, 0x2600, 0xF126, 0,
                                     (1, 0, 0x2402, 0x2600, 0xF126)),
    "copy-updates-destination-modifier": (0x5A81, 0, 0, 0xF126, 0x2600, 0x2400, 0,
                                          (1, 0, 0xF128, 0x2600, 0x2402)),
    "copy-two-agu-updates-source-modifier": (0x5A8A, 0, 8, 0xF12E, 0x2400, 0x2600, 0,
                                            (0, 1, 0xF130, 0x2402, 0x2600)),
    "shift-updates-modifier": (0x2D80, 8, 0, 0xF126, 0x2400, 0x2400, 0x0300,
                               (1, 0, 0xF120, 0x2400, 0x2400)),
}


def check(qemu, output, name, spec, icount, minimal=False):
    opcode, xm0, xm2, x0, x2, r1, r0, expected = spec
    words = [0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 1]
    write_word(words, 0x2400, 1)
    words += [0x6813, xm0, 0x6817, xm2, 0x68F8, x0, 0x68FA, x2,
              0x68F1, r1, 0x68F0, r0, opcode]
    read_sfr(words, 0x13, 4)
    read_sfr(words, 0x17, 5)
    return run(qemu, output, f"{name}-icount{icount}", words,
               {**dict(zip((4, 5, 8, 10, 1), expected)), 15: 0x6000}, icount=icount, minimal=minimal,
               metadata={"opcode": f"{opcode:04X}", "old_xm0": xm0,
                         "old_xm2": xm2, "initial_x0": x0, "initial_x2": x2})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--normal-only", action="store_true")
    parser.add_argument('--minimal', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"passed": False, "qemu_sha256": identity, "cases": []}
    try:
        for name, spec in CASES.items():
            if args.case and args.case != name:
                continue
            for icount in ((None,) if args.normal_only else (None, 5)):
                report["cases"].append(check(args.qemu, args.output, name, spec, icount, args.minimal))
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
        report["passed"] = all(case["passed"] for case in report["cases"])
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
