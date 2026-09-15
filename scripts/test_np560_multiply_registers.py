#!/usr/bin/env python3
"""DMCU MUL fractional mode, MUL/UMUL V, and register preservation.

CN1916884A PDF pp. 32/33 and SOCR.FR definition. C's prose names V in
both tables, so this probe deliberately masks C rather than declaring its
unchanged implementation correct. No NAND or host guest-memory writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from test_np560_dtu import read_sfr
from test_np560_mac import run


# name, opcode, SOCR, lhs, rhs, high/low result, Z/N/V in architectural PSR.
# Fixed values, not a copy of the emulator's multiplication implementation.
CASES = (
    ("fractional-positive", 0xC001, 0x000A, 0x4000, 0x4000, 0x2000, 0x0000, 0),
    ("fractional-negative", 0xC001, 0x000A, 0xC000, 0x4000, 0xE000, 0x0000, 8),
    ("fractional-overflow", 0xC001, 0x000A, 0x8000, 0x8000, 0x8000, 0x0000, 10),
    ("fractional-small-negative", 0xC001, 0x000A, 0xFFFF, 1, 0xFFFF, 0xFFFE, 8),
    ("fractional-zero", 0xC001, 0x000A, 0, 0x8000, 0, 0, 1),
    ("integer-positive", 0xC001, 0x0002, 0x4000, 0x4000, 0x1000, 0, 0),
    ("integer-negative", 0xC001, 0x0002, 0x8000, 0x7FFF, 0xC000, 0x8000, 8),
    ("integer-extreme", 0xC001, 0x0002, 0x8000, 0x8000, 0x4000, 0, 0),
    ("umul-clears-overflow", 0xC101, 0x0002, 0x48, 3, 0, 0xD8, 0),
    ("umul-ignores-fr", 0xC101, 0x000A, 0x4000, 0x4000, 0x1000, 0, 0),
    ("umul-high-bit", 0xC101, 0x000A, 0xFFFF, 0xFFFF, 0xFFFE, 1, 8),
    ("umul-zero", 0xC101, 0x000A, 0, 0xFFFF, 0, 0, 1),
    ("source-result-alias", 0xC067, 0x000A, 0xC000, 0x4000, 0xE000, 0, 8),
)


def check_case(qemu, output, case, *, icount=None):
    name, opcode, socr, left, right, high, low, flags = case
    source_left, source_right = (opcode >> 4) & 15, opcode & 15
    words = [0x68FF, 0x4000, 0x6800, socr,
             0x68F4, 0xA5A5, 0x68F5, 0xFE74,
             0x68F6, 0x1357, 0x68F7, 0x2468,
             0x68F0 | source_left, left, 0x68F0 | source_right, right,
             # Start V opposite its expected result to check set and clear.
             0x6801, 0x31CD if flags & 2 else 0x31CF, opcode]
    read_sfr(words, 1, 3)
    words += [0x74F3, 0xFFFB]  # Exclude the unverified architectural C bit.
    expected = {3: 0x31C0 | flags, 4: 0xA5A5, 5: 0xFE74,
                6: high, 7: low, 15: 0x4000}
    if source_left not in (6, 7):
        expected[source_left] = left
    if source_right not in (6, 7):
        expected[source_right] = right
    return run(qemu, output, f"{name}-icount{icount}", words, expected,
               icount=icount, metadata={"opcode": opcode, "socr": socr,
                                        "unverified_flags": ["C"]})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case", choices=[item[0] for item in CASES])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="np560-multiply-registers-") as work:
        output = args.output or Path(work) / "results"
        output.mkdir(parents=True, exist_ok=False)
        identity = {"qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
        report = {"passed": False, "identity": identity, "cases": []}
        try:
            for case in CASES:
                if args.case and case[0] != args.case:
                    continue
                report["cases"].append(check_case(args.qemu, output, case))
            if not args.case:
                report["cases"].append(check_case(args.qemu, output, CASES[0], icount=5))
                report["cases"].append(check_case(args.qemu, output, CASES[2], icount=5))
            assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity["qemu_sha256"]
            report["passed"] = True
        finally:
            (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("NP560+ multiply semantics and register-preservation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
