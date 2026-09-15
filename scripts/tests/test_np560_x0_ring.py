#!/usr/bin/env python3
"""Original audio ring writer and X0 circular postincrement, no NAND/HLE."""
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

from test_np560_dtu import read_sfr, read_word, write_word
from test_np560_mac import run


def original_writer(qemu, original, output, icount=None):
    start, end = 0x282E04, 0x282E66
    body = original.read_bytes()[start - 0x30000:end - 0x30000]
    words = [0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 1,
             0x6813, 0x40, 0x68F8, 0x7777]
    for address, value in ((0x2400, 0x1122), (0x2402, 0x3344),
                           (0x15FE, 0), (0x1000, 0xBEEF), (0x1600, 0xDEAD),
                           (0x4B00, 0x15FE), (0x4B02, 0)):
        write_word(words, address, value)
    for value in (4, 0x2400, 0):
        words += [0x68F0, value, 0x58F0]
    words += [0xBD28, 0x2E04, 0x50F6]
    for address, register in ((0x4B00, 2), (0x4B02, 3), (0x15FE, 4),
                              (0x1000, 5), (0x1600, 6)):
        read_word(words, address, register)
    read_sfr(words, 0x13, 7)
    return run(qemu, output, f"original-writer-icount{icount}", words,
               {2: 0x1002, 3: 4, 4: 0x1122, 5: 0x3344, 6: 0xDEAD,
                7: 0x40, 8: 0x7777, 15: 0x6000},
               tail=(start - 0x200000, body), icount=icount,
               metadata={"original_function": "28:2E04..2E64",
                         "function_bytes": len(body),
                         "function_sha256": hashlib.sha256(body).hexdigest()})


def original_reader(qemu, original, output, icount=None):
    start, end = 0x282C74, 0x282E04
    body = original.read_bytes()[start - 0x30000:end - 0x30000]
    words = [0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 1,
             0x6813, 0x40, 0x68F8, 0x7777]
    for address, value in ((0x15FE, 0x9090), (0x1000, 0xA0A0),
                           (0x1600, 0xB0B0), (0xF016, 0),
                           (0x4AFE, 0x15FF), (0x4B02, 2)):
        write_word(words, address, value)
    for value in (2, 0x2600, 0, 0x2400, 0):
        words += [0x68F0, value, 0x58F0]
    words += [0xBD28, 0x2C74, 0x50FA]
    for address, register in ((0x4AFE, 2), (0x4B02, 3), (0x2400, 4),
                              (0x2402, 5), (0x1600, 6)):
        read_word(words, address, register)
    read_sfr(words, 0x13, 7)
    return run(qemu, output, f"original-reader-icount{icount}", words,
               # RB0 is R0's high byte; RB1 was cleared by the original
               # routine, so its unsigned-8 to signed-16 conversion scales
               # (sample - 128) by 256, rather than returning an 8-bit value.
               {2: 0x1001, 3: 0, 4: 0x1000, 5: 0x2000, 6: 0xB0B0,
                7: 0x40, 8: 0x7777, 15: 0x6000},
               tail=(start - 0x200000, body), icount=icount,
               metadata={"original_function": "28:2C74..2E02",
                         "function_bytes": len(body),
                         "function_sha256": hashlib.sha256(body).hexdigest()})


def original_mp3_writer(qemu, original, output, *, high_source=False,
                        count=2, icount=None):
    """The MP3 producer uses word counts and 3340, unlike the PCM writer.

    Call the untouched factory body; do not emulate absent 01:49BE/49F8.
    Guest setup supplies a near source or the actual 50:E948 staging bank.
    This isolates copying, ring wrap, far-pointer return and register restore.
    It does not initialize the decoder or prove any decoded audio.
    """
    start, end = 0x16E844, 0x16E898
    body = original.read_bytes()[start - 0x30000:end - 0x30000]
    digest = hashlib.sha256(body).hexdigest()
    assert digest == "43d8da6ecfa3ac223a68f3e9321ff2c53046cc0e9a4e6631fa0d99a1b554ab7b"
    assert count in (0, 2)
    source_segment, source_offset = (0x50, 0xE948) if high_source else (0, 0x2400)
    words = [0x6800, 2, 0x68FF, 0x6000, 0x68FB, 0x5555,
             0x6810, 0, 0x6811, 1, 0x6813, 0x40, 0x68F8, 0x7777]
    for address, value in ((0x15FE, 0xCAFE), (0x1000, 0xBEEF),
                           (0x1600, 0xDEAD), (0x3340, 0x15FE),
                           (0x3342, 0x1234), (0x3346, 0x5678)):
        write_word(words, address, value)
    source_ds = (source_segment << 1) | (source_offset >> 15)
    words += [0x6810, source_ds]
    for index, value in enumerate((0x1122, 0x3344)):
        write_word(words, (source_offset & 0x7FFF) + index * 2,
                   value, banked=True)
    # Deliberately non-default incoming banks; the callee must restore both.
    words += [0x6810, 0xA2, 0x6811, 0xA3]
    for value in (count, source_offset, source_segment):
        words += [0x68F0, value, 0x58F0]
    words += [0xBD16, 0xE844, 0x50F6]
    for address, register in ((0x3340, 2), (0x15FE, 3), (0x1000, 4),
                              (0x1600, 5), (0x3342, 6), (0x3346, 7)):
        read_word(words, address, register)
    read_sfr(words, 0x13, 9)
    read_sfr(words, 0x10, 10)
    read_sfr(words, 0x11, 12)
    name = f"original-mp3-writer-{'far' if high_source else 'near'}-n{count}-icount{icount}"
    return run(qemu, output, name, words,
               {0: source_segment, 1: source_offset + count * 2,
                2: 0x1002 if count else 0x15FE,
                3: 0x1122 if count else 0xCAFE,
                4: 0x3344 if count else 0xBEEF,
                5: 0xDEAD, 6: 0x1234, 7: 0x5678, 8: 0x7777,
                9: 0x40, 10: 0xA2, 11: 0x5555, 12: 0xA3, 15: 0x6000},
               tail=(start - 0x30000, body), boot_mode="firmware-vma03",
               icount=icount,
               metadata={"original_function": "16:E844..E896",
                         "function_bytes": len(body), "function_sha256": digest,
                         "source_far": f"{source_segment:04X}:{source_offset:04X}",
                         "input_count_words": count, "decoder_services_called": False})


def pointer_case(qemu, output, name, opcode, *, length=6, pointer=0x1004,
                 operand=7, ext=None, expected=None, fault=False):
    words = [0x6800, 2, 0x68FF, 0x4000, 0x6810, 0, 0x6811, 1]
    for address, value in ((0x1004, 3), (0x1006, 0xDEAD), (0x2400, 5)):
        write_word(words, address, value)
    words += [0x6813, length, 0x68F8, pointer, 0x68F0, operand,
              0x68F1, 0x2400, 0x68F9, 0x1004]
    fault_text = f"20:{len(words) * 2:04x} WORD={opcode:04x}" if fault else None
    words += [opcode] + ([] if ext is None else [ext])
    read_word(words, 0x1004, 4)
    read_word(words, 0x1006, 5)
    read_word(words, 0x2400, 6)
    return run(qemu, output, name, words, expected or {}, fault=fault_text,
               metadata={"xm0": length, "initial_x0": pointer})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-only", action="store_true")
    parser.add_argument("--mp3-only", action="store_true",
                        help="Check only the distinct factory MP3 producer contract")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = {"qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
                "prg_sha256": hashlib.sha256(args.original_prg.read_bytes()).hexdigest()}
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    results = []
    if args.mp3_only:
        for high_source, count in ((False, 2), (True, 2), (True, 0)):
            for icount in (None, 5):
                results.append(original_mp3_writer(args.qemu, args.original_prg,
                    args.output, high_source=high_source, count=count, icount=icount))
    else:
        results.append(original_writer(args.qemu, args.original_prg, args.output))
    if not args.first_only and not args.mp3_only:
        results.append(original_writer(args.qemu, args.original_prg, args.output, 5))
        results.append(original_reader(args.qemu, args.original_prg, args.output))
        results.append(original_reader(args.qemu, args.original_prg, args.output, 5))
        cases = [
            ("word-read", 0x3808, dict(expected={0: 3, 8: 0x1000})),
            ("byte-read", 0x3908, dict(pointer=0x1005, expected={0: 0x0307, 8: 0x1000})),
            ("word-write", 0x1A80, dict(expected={4: 7, 8: 0x1000})),
            ("alu-read", 0x3008, dict(expected={0: 10, 8: 0x1000})),
            ("copy-source", 0x3A18, dict(expected={6: 3, 8: 0x1000, 1: 0x2400})),
            ("copy-both", 0x5A81, dict(expected={4: 5, 8: 0x1000, 1: 0x2402})),
            # The shift count is RB0 (R0's high byte), not the 16-bit R0.
            ("shift-write", 0x2C80, dict(operand=0x0100, expected={4: 6, 8: 0x1000})),
            ("exponent-read", 0x1E18, dict(expected={8: 0x1000})),
            ("linear", 0x3808, dict(length=0, expected={0: 3, 8: 0x1006})),
            ("other-register", 0x3809, dict(expected={0: 3, 8: 0x1004, 9: 0x1006})),
            ("immediate-bypasses", 0x6A08, dict(ext=2, expected={5: 7, 8: 0x1004})),
            ("predecrement-bypasses", 0x5880,
             dict(pointer=0x1000, expected={8: 0x0FFE, 15: 0x4000})),
            ("bit-reversal-explicit-stop", 0x3808,
             dict(length=0xFFFF, fault=True, expected={0: 7, 8: 0x1004})),
            ("outside-ring-explicit-stop", 0x1A80,
             dict(pointer=0x1006, fault=True, expected={0: 7, 8: 0x1006})),
        ]
        for name, opcode, options in cases:
            results.append(pointer_case(args.qemu, args.output, name, opcode, **options))
    assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity["qemu_sha256"]
    (args.output / "report.json").write_text(json.dumps(
        {"passed": True, "identity": identity, "cases": results}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
