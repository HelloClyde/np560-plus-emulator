#!/usr/bin/env python3
"""A pending IRQ must be reconsidered when CRIT's instruction window ends.

All requests, including the real Timer0 variant, are produced by the guest.
The ISR records the foreground progress and its architectural return PC.
Register-only instructions after the window deliberately share a TCG block.
No NAND, host guest-memory writes or audio-codec substitute is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from test_np560_dtu import read_sfr, write_word
from test_np560_mac import pack, run


def check(qemu, output, count=4, *, timer=False, masked=False, nseg=False,
          wide=False, icount=None):
    mode = 2 | (0x20 if nseg else 0)
    # Start beyond the same-segment vector area; no host changes after reset.
    words = [0xAD20, 0x400] + [0xD0FF] * (0x200 - 2)
    if nseg:
        words[0x48 // 2:0x4C // 2] = [0xAD20, 0x800]
    words += [0x6800, mode, 0x68FF, 0x6000, 0x68FB, 0,
              0x6810, 0x44, 0x6811, 0x45]
    if not nseg:
        write_word(words, 0x48, 0xAD20)
        write_word(words, 0x4A, 0x800)
    if timer:
        assert not masked
        # Timer0 latches RQ while IE=0; stop the timer without clearing RQ.
        # This is the existing real-event setup from test_np560_ignds_irq.
        words += [0xEE00, 0x682E, 0x10, 0xFE00, 0x6826, 31, 0x6851, 0x31,
                  0x6827, 0x8080, 0x9B51, 0x01FE, 0xFF27]
    words += [0x68F9, 0, 0x68F6, 0xFFFF, 0x68F7, 0xFFFF,
              0x6801, 0x01C4]
    if not timer:
        words += [0x6800, mode | (0 if masked else 0x8000)]
    words += [0x3F00 | (count - 1)]
    words += [0x6800, mode | 0x8000] if timer else [0x6851, 0x33]
    # The request/IE write is the first protected instruction and ends a TB.
    # Keep the established encoded 0..3 -> 1..4 count convention; this check
    # does not resolve the manual's missing description of that encoding.
    for _ in range(count - 1):
        words += [0x68F2, 0xBEEF] if wide else [0x5091]
    expected_entry = len(words) * 2
    protected_progress = 0 if wide else count - 1
    # A long straight-line tail exposes delayed IRQ entry at the next TB
    # instead of the first unprotected architectural instruction boundary.
    words += [0x5091] * 12
    read_sfr(words, 0x51, 3)
    read_sfr(words, 0, 4)
    handler = [0x0869, 0x787F, 2 if nseg else 4, 0xC610]
    expected = {3: 0x33 if masked else 0x31,
                4: mode | (0 if masked else 0x8000),
                6: 0xFFFF if masked else protected_progress,
                7: 0xFFFF if masked else expected_entry,
                9: protected_progress + 12, 15: 0x6000}
    if wide:
        expected[2] = 0xBEEF
    name = (f"count-{count}-timer-{timer}-masked-{masked}-nseg-{nseg}"
            f"-wide-{wide}-icount-{icount}")
    return run(qemu, output, name, words, expected,
               rom=pack([0x0F00] * 0x10000), tail=(0x800, pack(handler)),
               icount=icount,
               metadata={"source": "CN1916884A PDF p113",
                         "expected_irq_return_pc": f"20:{expected_entry:04x}",
                         "protected_instructions": count,
                         "hardware_timer": timer, "global_ie_masked": masked})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = {"qemu": str(args.qemu),
                "sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    results = [check(args.qemu, args.output)]
    if not args.first_only:
        for count in (1, 2, 3):
            results.append(check(args.qemu, args.output, count))
        for options in ({"masked": True}, {"nseg": True}, {"wide": True},
                        {"icount": 5}, {"timer": True},
                        {"timer": True, "icount": 5}):
            results.append(check(args.qemu, args.output, **options))
    assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity["sha256"]
    (args.output / "report.json").write_text(json.dumps({
        "identity": identity, "passed": all(r["passed"] for r in results),
        "results": results}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
