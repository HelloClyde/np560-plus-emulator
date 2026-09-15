#!/usr/bin/env python3
"""Independent REP/SRC and REPB/RC, including the original map scroll body.

All writes are executed by the diagnostic guest. No NAND, host RAM injection,
game-name workaround or replacement drawing routine is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from test_np560_dtu import write_word
from test_np560_icr_vectors import vector_for
from test_np560_mac import pack, run


def simple(qemu, output, case, icount):
    words = [0x6800, 2, 0x68FF, 0x7000, 0x68F0, 0,
             0x68F1, 4, 0x68F2, 2, 0x68FC, 0]
    block = len(words)
    words += [0xAF02 if "register" in case else 0xAE02, 0]
    words += [0xCF01] if "register" in case else [0xBF00, 4]
    words += [0x5001]  # five inner additions, on EACH of three outer passes
    if "tail" not in case:
        words += [0x50C1]
    words[block + 1] = len(words) * 2
    return run(qemu, output, f"{case}-icount{icount}", words,
               {0: 15, 1: 4, 2: 2, 12: 0 if "tail" in case else 3,
                15: 0x7000}, icount=icount)


def interrupted(qemu, output, icount):
    # Each legal repeated MOV to ICR0 produces one real interrupt. The low
    # ISR itself requests a higher-priority ISR, exercising both saved repeat
    # engines through the existing nested IRQ context, not a forced host IRQ.
    words = [0x6800, 2, 0x68FF, 0x7000, 0x6810, 0,
             0x68F1, 4, 0x68F9, 0, 0x68FA, 0, 0x68FC, 0]
    for addr, value in ((vector_for(0), 0xAD20), (vector_for(0) + 2, 0x1000),
                        (vector_for(1), 0xAD20), (vector_for(1) + 2, 0x1020)):
        write_word(words, addr, value)
    words += [0x6801, 0x01C4, 0x6800, 0x8002]
    block = len(words)
    words += [0xAE02, 0, 0xCF01, 0x6850, 3, 0x50C1]
    words[block + 1] = len(words) * 2
    words += [0x6800, 2]
    handlers = bytearray(0x30)
    handlers[:8] = pack([0x6851, 0x33, 0x50A1, 0xC610])
    handlers[0x20:0x24] = pack([0x5091, 0xC610])
    # Match the existing IRQ suite's strict mapped ROM fixture. Handlers
    # are not supplied by this ROM: the guest installs real RAM vectors.
    rom = pack([0x0F00] * 0x8000)
    return run(qemu, output, f"nested-irq-icount{icount}", words,
               {1: 4, 9: 15, 10: 15, 12: 3, 15: 0x7000},
               tail=(0x1000, handlers), rom=rom, icount=icount)


def original_scroll(qemu, output, original, direction, icount):
    prg = original.read_bytes()
    body = prg[0x0A78D2:0x0A7B02]
    assert len(body) == 0x230 and body[:2] == pack([0x2E0A])
    rom = bytearray(pack([0x0F00] * (0x0D7B02 // 2)))
    rom[0x0D78D2:] = body  # exact original code, no call/branch edits
    words = [0x6800, 2, 0x68FF, 0x7000, 0x68FB, 0,
             0x6810, 0, 0x6811, 1]
    # The function resolves this original framebuffer far pointer through
    # its own DS1/F2E0 sequence. Place a full-sized buffer in low test SRAM.
    # The original first sets DS1=0, so logical 84FC reads physical 04FC.
    write_word(words, 0x04FC, 0)
    write_word(words, 0x04FE, 0x2400)
    initial = pack([(i * 73 + 0x1234) & 0xFFFF for i in range(7200)])
    # Ordinary branch loop, independent of the repeat engines under test.
    # Unrolling write_word here exceeds the 64 KiB code segment.
    words += [0x68F0, 0x1234, 0x68F1, 0x2400, 0x68F2, 7200]
    fill = len(words) * 2
    words += [0x1A10, 0x70F0, 73, 0x5221, 0xAC02, fill]
    # Same rectangle and step used by original 22:D776 map scrolling.
    x1, y1, x2, y2, step = 0, 4, 239, 115, 16
    for value in (direction, step, y2, x2, y1, x1):
        words += [0x68F0, value, 0x58F0]
    words += [0xBD0D, 0x78D2, 0x50FC]
    expected = bytearray(initial)
    if direction in (0, 1):
        for y in range(y1, y2 + 1):
            row = (119 - y) * 120
            left, right, shift = x1 // 2, x2 // 2 + 1, step // 2
            if direction == 0:
                expected[row + left:row + right - shift] = initial[
                    row + left + shift:row + right]
            else:
                expected[row + left + shift:row + right] = initial[
                    row + left:row + right - shift]
    else:
        for y in range(y1, y2 - step + 1):
            src_y, dst_y = ((y + step, y) if direction == 2 else (y, y + step))
            src, dst = (119 - src_y) * 120, (119 - dst_y) * 120
            expected[dst:dst + 120] = initial[src:src + 120]
    return run(qemu, output, f"original-{direction}-icount{icount}", words,
               {15: 0x7000}, rom=rom, icount=icount,
               expected_data=list(struct.unpack("<7200h", expected)),
               metadata={"original_function": "0D:78D2", "source": "2A:78D2",
                         "sha256": hashlib.sha256(body).hexdigest(),
                         "rectangle": [x1, y1, x2, y2], "step": step,
                         "direction": direction, "buffer_bytes": 14400})


CASES = ("immediate", "register", "immediate-tail", "register-tail",
         "nested-irq", "original-left", "original-right", "original-up", "original-down")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=CASES)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"passed": False, "qemu_sha256": identity, "cases": []}
    try:
        for case in (args.case,) if args.case else CASES:
            for icount in (None,) if args.case else (None, 5):
                if case == "nested-irq":
                    result = interrupted(args.qemu, args.output, icount)
                elif case.startswith("original-"):
                    result = original_scroll(args.qemu, args.output, args.original_prg,
                                             CASES.index(case) - 5, icount)
                else:
                    result = simple(args.qemu, args.output, case, icount)
                report["cases"].append(result)
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
        report["passed"] = True
    except AssertionError as error:
        # Full expected/actual framebuffer is retained in the case JSON.
        report["failure"] = str(error)[:1600]
        print(report["failure"], flush=True)
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
