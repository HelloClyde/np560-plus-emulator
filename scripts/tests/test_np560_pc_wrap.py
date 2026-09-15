#!/usr/bin/env python3
"""Segment-local PC rollover: instruction fetch, calls and repeat, no NAND."""

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
import struct

from test_np560_mac import run


def check(qemu, output, name, icount=None):
    if name == "self-modified-extension":
        return check_self_modified(qemu, output, icount)
    words = [0x6800, 2, 0x6801, 0, 0x68FF, 0x6000,
             0x68F0, 2, 0x68F1, 0]
    entry = 0xFFFE
    if name in ("wide-ending", "far-call-ending", "repeat-last-word"):
        entry = 0xFFFC
    words += [0xAD22, entry]
    final = len(words) * 2
    body = bytearray(0x10040)

    def put(offset, values):
        struct.pack_into(f"<{len(values)}H", body, offset, *values)

    expected = {2: 0xBEEF, 15: 0x6000}
    destination_offset = 0
    if name == "word":
        put(entry, [0xC700])
    elif name == "wide-ending":
        put(entry, [0x68F0, 0x2468])
        expected[0] = 0x2468
    elif name == "wide-straddling":
        put(entry, [0x68F0])
        put(0, [0x2468])
        put(0x10000, [0x1357])
        destination_offset = 2
        expected[0] = 0x2468
    elif name == "untaken-relative":
        put(entry, [0xD100])  # Z is clear: do not take conditional jump.
    elif name in ("far-call-ending", "far-call-straddling"):
        put(entry, [0xBD22])
        put(0 if entry == 0xFFFE else 0xFFFE, [0x0100])
        if entry == 0xFFFE:
            put(0x10000, [0x0100])
            destination_offset = 2
        # Capture the REAL guest stack's CS and PC, then RETS.
        put(0x0100, [0x284F, 0x785F, 2, 0xC620])
        expected.update({4: 0x22, 5: destination_offset})
    elif name == "repeat-last-word":
        put(entry, [0xCF00, 0x5011])  # REP R0; ADD R1,#1 (three times).
        expected[1] = 3
    elif name == "repeat-at-end":
        put(entry, [0xCF00])
        put(0, [0x5011])
        put(0x10000, [0x5011])
        destination_offset = 2
        expected[1] = 3
    else:
        raise ValueError(name)
    # The next segment is a distinct, executable poison path. The old core
    # completes normally with DEAD instead of producing a timeout false positive.
    for base, marker in ((0, 0xBEEF), (0x10000, 0xDEAD)):
        put(base + destination_offset, [0x68F2, marker, 0xAD20, final])
    return run(qemu, output, name + f"-icount{icount}", words, expected,
               tail=(0x20000, body), icount=icount,
               expected_disassembly=("0x0022fffe:  mov reg[0xf0], #0x2468"
                                     if name == "wide-straddling" else None),
               metadata={"entry": f"22:{entry:04X}",
                         "correct_continuation": f"22:{destination_offset:04X}",
                         "adjacent_segment_poison": "23:0000"})


def check_self_modified(qemu, output, icount):
    # Bootstrap and first extension are the SAME physical word AD03. D010
    # is initially SJMP's target, later a short branch from 0002 to 0024.
    # The guest patches only the extension page, leaving the cached FFFE
    # opcode untouched. No host write or global TB flush is used.
    caller = [0xAD03, 0xD010]
    body = bytearray(0x10000 - 0x24)

    def put(address, values):
        struct.pack_into(f"<{len(values)}H", body, address - 0x24, *values)

    put(0x24, [0xC620])
    put(0xD010, [0x6800, 2, 0x68FF, 0x6000, 0x6810, 6,
                 0xBD03, 0xFFFE, 0x0820,
                 0x68F1, 0xBEEF, 0xA8F1, 0,
                 0x88F3, 0,
                 0xBD03, 0xFFFE, 0x0840, 0xAD03, 4])
    put(0xFFFE, [0x68F0])
    return run(qemu, output, f"self-modified-extension-icount{icount}",
               caller, {0: 0xBEEF, 2: 0xAD03, 3: 0xBEEF, 4: 0xBEEF, 15: 0x6000},
               tail=(0x24, body), icount=icount, boot_mode="firmware-vma03",
               metadata={"opcode": "03:FFFE", "guest_patched_extension": "03:0000",
                         "first_immediate": "AD03", "second_immediate": "BEEF"})


CASES = ("word", "wide-ending", "wide-straddling", "untaken-relative",
         "far-call-ending", "far-call-straddling", "repeat-last-word", "repeat-at-end",
         "self-modified-extension")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=CASES)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"passed": False, "qemu_sha256": identity, "cases": []}
    try:
        for name in (args.case,) if args.case else CASES:
            for icount in (None,) if args.case else (None, 5):
                report["cases"].append(check(args.qemu, args.output, name, icount))
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
        report["passed"] = True
    finally:
        # Keep the core identity even when the old core hits the poison path.
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
