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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))
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


def repeat_pcm(qemu, output, original, count, repeat, icount):
    """Execute the real post-decoder repeat helper, not a missing codec stub."""
    words = initial()
    samples = [0x8000, 0x7FFF]
    for i, sample in enumerate(samples):
        write_word(words, 0x2984 + i * 2, sample)
    for address in range(0x0FFE, 0x1012, 2):
        write_word(words, address, 0x5AA5)
    push(words, [0, 0x2984, 0, 0x1000, count, repeat])
    words += [0xBD08, 0x372A, 0x50FC]
    expected_samples = [value for value in samples[:count] for _ in range(repeat)]
    expected = {i: expected_samples[i] if i < len(expected_samples) else 0x5AA5
                for i in range(8)}
    for i in range(8):
        read_word(words, 0x1000 + i * 2, i)
    read_word(words, 0x0FFE, 8)
    read_word(words, 0x1010, 9)
    read_sfr(words, 0x10, 10)
    read_sfr(words, 0x11, 12)
    expected.update({8: 0x5AA5, 9: 0x5AA5, 10: 0xA2, 12: 0xA2,
                     11: 0x4444, 15: 0x6000})
    return execute(qemu, output, original, f"repeat-pcm-{count}-{repeat}", words,
                   expected, {"original_function": "08:372A..3788",
                              "diagnostic_pcm": samples, "count": count,
                              "repeat": repeat, "codec_executed": False,
                              "filter_executed": False}, icount)


def swap_audio_words(qemu, output, original, count, icount):
    """Execute the original in-place byte-lane swap used by the NPE path."""
    words = initial()
    for address, value in ((0x87FE, 0x5AA5), (0x8800, 0x1234),
                           (0x8802, 0xABCD), (0x8804, 0x5AA5)):
        write_word(words, address, value)
    push(words, [0, 0x8800, count])
    words += [0xBD2C, 0x0E1E, 0x50F6]
    for address, register in ((0x87FE, 2), (0x8800, 3),
                              (0x8802, 4), (0x8804, 5)):
        read_word(words, address, register)
    expected = {2: 0x5AA5, 3: 0x3412 if count else 0x1234,
                4: 0xCDAB if count == 2 else 0xABCD, 5: 0x5AA5,
                11: 0x4444, 15: 0x6000}
    return execute(qemu, output, original, f"swap-audio-words-{count}",
                   words, expected,
                   {"original_function": "2C:0E1E..0E5C",
                    "caller": "25:E218", "word_count": count,
                    "codec_executed": False}, icount)


def gain_pcm(qemu, output, original, current, target, count, icount):
    """Real NPE x2 gain helper with the full PRG, including its gain table."""
    words = initial()
    samples = [-30000, 30000]
    for address, value in ((0x2982, 0x5AA5), (0x2988, 0x5AA5),
                           (0x4A64, (current << 8) | target)):
        write_word(words, address, value)
    for i, sample in enumerate(samples):
        write_word(words, 0x2984 + i * 2, sample & 65535)
    push(words, [0, 0x2984, count])
    words += [0xBD08, 0x3536, 0x50F6]
    level = current + (target > current) - (target < current)
    table = [0, 0x2027, 0x287A, 0x32F5, 0x4027, 0x50C3, 0x65AD, 0x7FFF]
    assert original[0x3057E6:0x3057F6] == b''.join(x.to_bytes(2, 'little') for x in table)
    output_samples = []
    for sample in samples:
        value = 0
        for _ in range(2):
            value = ((value + sample * table[level] * 2 + 32768) // 65536) * 65536
            value = min(2147483647, max(-2147483648, value))
        output_samples.append((value // 65536 if count else sample) & 65535)
    for address, register in ((0x2984, 2), (0x2986, 3), (0x4A64, 4),
                              (0x2982, 5), (0x2988, 6)):
        read_word(words, address, register)
    read_sfr(words, 0x10, 8)
    read_sfr(words, 0x11, 9)
    expected = {2: output_samples[0], 3: output_samples[1],
                4: (level << 8) | target, 5: 0x5AA5, 6: 0x5AA5,
                8: 0xA2, 9: 0xA2, 11: 0x4444, 15: 0x6000}
    return execute(qemu, output, original, f'gain-{current}-{target}-{count}',
                   words, expected, {'original_function': '08:3536..35AA',
                                    'diagnostic_pcm': samples, 'count': count,
                                    'current': current, 'target': target,
                                    'coefficient': table[level],
                                    'codec_executed': False}, icount)


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
                       (0x0837F4, 0x083820), (0x08385C, 0x0838A4),
                       (0x08372A, 0x08378A), (0x083536, 0x0835AC),
                       (0x2C0E1E, 0x2C0E5E),
                       (0x3357E6, 0x3357F6)):
        report["original_ranges"][f"{begin:06X}:{end:06X}"] = hashlib.sha256(
            original[begin-0x30000:end-0x30000]).hexdigest()
    try:
        for icount in (None, 5):
            for current, target, count in ((7, 0, 2), (0, 7, 2), (0, 0, 2),
                                            (7, 7, 2), (7, 0, 0)):
                report["cases"].append(gain_pcm(args.qemu, args.output, original,
                                                 current, target, count, icount))
            for count, repeat in ((2, 4), (0, 4), (2, 0)):
                report["cases"].append(repeat_pcm(args.qemu, args.output, original,
                                                   count, repeat, icount))
            for count in (0, 2):
                report["cases"].append(swap_audio_words(
                    args.qemu, args.output, original, count, icount))
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
