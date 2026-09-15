#!/usr/bin/env python3
"""Full-width native MP3 multiply helpers against independent integer products."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import struct

from build_np560_mp3_antialias import build
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr
from test_np560_mac import run
from test_np560_mp3_requantize import FIXTURE, signed_words


def check(qemu, output, pairs, signed, name, icount=None):
    core = build()
    words, expected = [], []
    for x, y in pairs:
        words += [x & 65535, (x >> 16) & 65535,
                  y & 65535, (y >> 16) & 65535]
        product = x * y
        expected += [(product >> shift) & 65535 for shift in (0, 16, 32, 48)]
        expected += [y & 65535, (y >> 16) & 65535]
    a = _DMCUAssembler(0x200000)
    # FR remains on to exercise unsigned MUL's documented non-fractional
    # behavior; MAS is off as required by the private helper contract.
    a.emit(0x6800, 10, 0x68FF, 0x6000, 0x6810, 0, 0x6811, FIXTURE >> 15,
           0x68F8, 0x2400, 0x68F9, 0x8000, 0x68FC, len(pairs),
           0x68FD, 0xC0DE, 0x68FE, 0xFACE)
    a.label("next")
    a.emit(0x3809, 0x3819, 0x38A9, 0x38B9, 0xBC00,
           core["entries"]["multiply_signed" if signed else "multiply_positive"] & 65535,
           0x0858, 0x1A50, 0x1A51, 0x1A52, 0x1A53, 0x1A5A, 0x1A5B,
           0x0885, 0x52C1)
    a.ajmp("next", 2)
    read_sfr(a.words, 0, 4)
    read_sfr(a.words, 0x11, 5)
    data = bytearray(FIXTURE - 0x201000 + len(words) * 2)
    start = core["code_address"] - 0x201000
    data[start:start + len(core["code"])] = core["code"]
    data[FIXTURE - 0x201000:] = struct.pack(f"<{len(words)}H", *words)
    return run(qemu, output, name, a.finish(),
               {4: 10, 5: FIXTURE >> 15, 8: 0x2400 + len(expected)*2,
                9: 0x8000 + len(words)*2, 12: 0, 13: 0xC0DE, 14: 0xFACE, 15: 0x6000},
               tail=(0x1000, data), expected_data=signed_words(expected),
               timeout=45, poll_interval=.1, icount=icount,
               metadata={"signed_coefficient": signed, "pairs": len(pairs),
                         "code_sha256": hashlib.sha256(core["code"]).hexdigest()})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    edges = [-2**31, -2**31+1, -65537, -65536, -65535, -1, 0, 1,
             32767, 32768, 65535, 65536, 65537, 2**31-1]
    rng = random.Random(5606432)
    report = {"passed": False, "cases": [],
              "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    try:
        for signed in (False, True):
            ys = edges if signed else sorted({v & 0xFFFFFFFF for v in edges} | {0xFFFFFFFF})
            pairs = [(x, y) for x in edges for y in ys]
            pairs += [(rng.randrange(-2**31, 2**31),
                       rng.randrange(-2**31, 2**31) if signed else rng.randrange(2**32))
                      for _ in range(512)]
            for i in range(0, len(pairs), 256):
                report["cases"].append(check(args.qemu, args.output, pairs[i:i+256], signed,
                                              f"signed-{int(signed)}-{i}"))
            report["cases"].append(check(args.qemu, args.output, pairs[:32], signed,
                                          f"signed-{int(signed)}-icount", 5))
        report["passed"] = all(c["passed"] and c["exit_code"] == 0 for c in report["cases"])
    except AssertionError as error:
        detail = error.args[0] if error.args else "assertion failed"
        if isinstance(detail, dict):
            detail = {"name": detail.get("name"),
                      "differences": [(i, x, y) for i, (x, y) in enumerate(zip(
                          detail.get("actual_samples", []), detail.get("expected_samples", [])))
                                      if x != y][:12]}
        report["failure"] = str(detail)[:2000]
        print(report["failure"], flush=True)
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2)+"\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
