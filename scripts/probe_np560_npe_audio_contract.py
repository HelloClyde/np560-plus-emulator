#!/usr/bin/env python3
"""Execute original NPE header and audio timing functions, not a codec.

Only explicit diagnostic guest inputs are supplied. B6DE/B7AA, ACD8/AD92
are neither called nor replaced. Actual compressed-frame consumption and
decoded sample counts remain unknown. No NAND or host guest-RAM writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from test_np560_dtu import read_sfr, read_word, write_word
from test_np560_mac import run

PRG_SHA256 = "d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5"


def initial():
    return [0x6800, 2, 0x68FF, 0x6000, 0x68FB, 0x4444,
            0x6810, 0xA2, 0x6811, 0xA2]


def push(words, values):
    for value in reversed(values):
        words += [0x68F0, value, 0x58F0]


def execute(qemu, output, original, name, words, expected, metadata, icount):
    assert len(words)*2+2 < 0x1000
    return run(qemu, output, name+f"-icount{icount}", words, expected,
               tail=(0x1000, original[0x1000:]), boot_mode="firmware-vma03",
               metadata=metadata, icount=icount)


def header(qemu, output, original, lookahead, icount):
    # First six file-order bytes, including two bytes after the count.
    # The zero-lookahead case is explicitly synthetic, not a second NPE.
    raw = bytes.fromhex("200d0534"+lookahead)
    words = initial()
    for i in range(0, len(raw), 2):
        write_word(words, 0x8800+i, int.from_bytes(raw[i:i+2], "little"))
    push(words, [0, 0x8800])
    words += [0xBD2C, 0x0C56, 0x50F4]
    read_word(words, 0xA82A, 1, banked=True)
    read_word(words, 0xA82C, 2, banked=True)
    read_word(words, 0xA82E, 3, banked=True)
    read_word(words, 0xA836, 4, banked=True)
    read_word(words, 0xA830, 5, banked=True)
    read_word(words, 0xA83A, 6, banked=True)
    read_word(words, 0xA83C, 7, banked=True)
    read_sfr(words, 0x10, 8)
    read_sfr(words, 0x11, 9)
    expected = {0: 0, 1: 13, 2: 1332, 3: 63 if lookahead == "f16b" else 0,
                4: 3 if lookahead == "f16b" else 0, 5: 8000, 6: 8400,
                7: 8000, 8: 0xA2, 9: 0xA2, 11: 0x4444, 15: 0x6000}
    return execute(qemu, output, original, "header-"+lookahead, words, expected,
                   {"original_function": "2C:0C56..0D70", "six_input_bytes": raw.hex(),
                    "synthetic_lookahead": lookahead != "f16b", "codec_executed": False}, icount)


def timing(qemu, output, original, rate, count, increment, icount):
    words = initial()
    for address in range(0x4A52, 0x4A5C, 2):
        write_word(words, address, 0)
    push(words, [rate, count])
    words += [0xBD08, 0x385C, 0x50F4, 0xBD08, 0x37F4, 0xBD08, 0x37F4]
    for address, register in ((0x4A52, 2), (0x4A54, 3), (0x4A56, 4),
                              (0x4A58, 5), (0x4A5A, 6)):
        read_word(words, address, register)
    doubled = increment * 2
    expected = {2: doubled >> 32, 3: (doubled >> 16) & 65535,
                4: doubled & 65535, 5: increment >> 16, 6: increment & 65535,
                11: 0x4444, 15: 0x6000}
    return execute(qemu, output, original, f"clock-{rate}-{count}", words, expected,
                   {"original_functions": ["08:385C..38A2", "08:37F4..381E"],
                    "sample_rate": rate, "diagnostic_sample_count": count,
                    "expected_increment_q16_ms": increment,
                    "actual_decoder_sample_count_proven": False}, icount)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = args.original_prg.read_bytes()
    if hashlib.sha256(original).hexdigest() != PRG_SHA256:
        parser.error("original PRG hash differs")
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"passed": False, "original_prg_sha256": PRG_SHA256,
              "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
              "codec_executed": False, "cases": [], "original_ranges": {}}
    for begin, end in ((0x2C0C56, 0x2C0D72), (0x32B788, 0x32B7DA),
                       (0x0837F4, 0x083820), (0x08385C, 0x0838A4)):
        report["original_ranges"][f"{begin:06X}:{end:06X}"] = hashlib.sha256(
            original[begin-0x30000:end-0x30000]).hexdigest()
    try:
        for icount in (None, 5):
            for lookahead in ("f16b", "0000"):
                report["cases"].append(header(args.qemu, args.output, original, lookahead, icount))
            for rate, count, increment in ((8000, 160, 20 << 16),
                                            (32000, 320, 10 << 16),
                                            (44100, 576, 0xD0FAC)):
                report["cases"].append(timing(args.qemu, args.output, original,
                                               rate, count, increment, icount))
        report["passed"] = all(c["passed"] and c["exit_code"] == 0 for c in report["cases"])
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
