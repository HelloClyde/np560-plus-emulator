#!/usr/bin/env python3
"""Execute the original MPEG header parser to constrain the missing MP3 ABI.

This is not an MP3 decoder or a replacement for 01:4804/49F8. Diagnostic
guest instructions supply four header bytes and inspect the original
16:E45E parser's outputs. The original parser and tables are unchanged.
No NAND, host guest-memory writes, ROM success stubs or audio substitution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from test_np560_dtu import read_sfr, read_word, write_word
from test_np560_mac import run


PARSER = (0x16E45E, 0x16E5B8)
TABLES = (0x3109D6, 0x310AA6)
PARSER_SHA256 = "76d3d1681098deb6717597edb1fe8abc41e45fec854128ee8ba2c2c873ab24e2"
TABLES_SHA256 = "67e225b9cdcf913afd3551a3d678fd37da4cd79d63a42efd5eb8111c41919546"

# Expected outputs are explicit MPEG header values, not read back from the
# firmware table under test. Firmware version codes are 1=MPEG1, 2=MPEG2,
# 0=MPEG2.5. Layer numbers are 1/2/3, channel mode is the original two bits.
# name, header, (version, layer, mode, kbps, Hz, bytes/frame, samples, pad, flag)
# The final byte at 51:25D5 is NOT a verified CRC flag. Original E4A8..E4B0
# shifts R0 left, writes !R0.7 to R0.8, masks RB0, then stores it. Its source
# bit is zero after the earlier shifts, so valid inputs below store 1 for
# either protection bit. Keep this observation separate from CRC semantics.
CASES = (
    ("mpeg1-128-44100-stereo", "fffb9000", (1, 3, 0, 128, 44100, 417, 1152, 0, 1)),
    ("mpeg1-128-44100-crc", "fffa9000", (1, 3, 0, 128, 44100, 417, 1152, 0, 1)),
    ("mpeg1-128-44100-pad-joint", "fffb9264", (1, 3, 1, 128, 44100, 418, 1152, 1, 1)),
    ("mpeg1-320-32000-mono", "fffbe8c0", (1, 3, 3, 320, 32000, 1440, 1152, 0, 1)),
    ("mpeg1-192-48000-crc", "fffab400", (1, 3, 0, 192, 48000, 576, 1152, 0, 1)),
    ("mpeg2-64-22050-mono", "fff380c0", (2, 3, 3, 64, 22050, 208, 576, 0, 1)),
    ("mpeg2-8-16000-stereo", "fff31800", (2, 3, 0, 8, 16000, 36, 576, 0, 1)),
    ("mpeg25-8-8000-mono", "ffe318c0", (0, 3, 3, 8, 8000, 72, 576, 0, 1)),
    ("mpeg25-32-11025-stereo", "ffe34000", (0, 3, 0, 32, 11025, 208, 576, 0, 1)),
    ("mpeg1-layer2-160-44100", "fffd9000", (1, 2, 0, 160, 44100, 522, 1152, 0, 1)),
    # These are parser-level rejection observations, not claims about what
    # the missing resident decoder would do with a complete input stream.
    ("reject-layer1", "ffff4000", None),
    ("reject-free-bitrate", "fffb0000", None),
    ("reject-reserved-version", "ffeb9000", None),
    ("reject-reserved-layer", "fff99000", None),
    ("reject-reserved-rate", "fffb9c00", None),
    ("reject-reserved-bitrate", "fffbf000", None),
)


def original_slice(original, addresses, expected_sha):
    begin, end = addresses
    result = original[begin - 0x030000:end - 0x030000]
    if hashlib.sha256(result).hexdigest() != expected_sha:
        raise ValueError(f"original bytes differ at {begin:06x}..{end:06x}")
    return result


def check(qemu, original, output, case, icount):
    name, header_hex, fields = case
    header = bytes.fromhex(header_hex)
    # DS1=A2 maps A846 to physical 51:2846. Parser expects each pair
    # assembled in file order (FF FB -> word FFFB), not host endian words.
    words = [0x6800, 2, 0x68FF, 0x6000, 0x68FB, 0x4444,
             0x6810, 0xA2, 0x6811, 0xA2]
    write_word(words, 0x3340, 0xBEEF)
    write_word(words, 0x3346, 0xDEAD)
    for address in range(0xA5C8, 0xA5DC, 2):
        write_word(words, address, 0xA55A, banked=True)
    for i in range(2):
        write_word(words, 0xA846 + i * 2,
                   int.from_bytes(header[2*i:2*i+2], "big"), banked=True)
    words += [0xBD16, 0xE45E]
    for address, reg in ((0xA5C8, 1), (0xA5C9, 2), (0xA5CB, 3),
                         (0xA5D4, 8), (0xA5D5, 9)):
        words += [0x99F0 | reg, address]
    for address, reg in ((0xA5CC, 4), (0xA5CE, 5), (0xA5D0, 6), (0xA5D2, 7)):
        read_word(words, address, reg, banked=True)
    read_sfr(words, 0x10, 10)
    read_sfr(words, 0x11, 12)
    read_word(words, 0x3340, 13)
    read_word(words, 0x3346, 14)
    expected = {0: 0 if fields else 0xFFFC, 10: 0xA2, 11: 0x4444,
                12: 0xA2, 13: 0xBEEF, 14: 0xDEAD, 15: 0x6000}
    if fields:
        assert len(fields) == 9
        expected.update(dict(enumerate(fields, 1)))
    # Keep the complete original PRG after a small diagnostic caller area.
    # In VMA03 this retains both the function at 16:E45E and its read-only
    # tables at 31:09D6, including the proper code/data views.
    assert len(words) * 2 + 2 < 0x1000
    return run(qemu, output, f"{name}-icount{icount}", words, expected,
               tail=(0x1000, original[0x1000:]), boot_mode="firmware-vma03",
               icount=icount, metadata={
                   "header_hex": header_hex, "function": "16:E45E..E5B6",
                   "function_sha256": PARSER_SHA256,
                   "tables": "31:09D6..0AA5", "tables_sha256": TABLES_SHA256,
                   "decoder_services_called": False,
                   "decoded_pcm_generated": False,
                   "field_registers": {
                       "version_code": 1, "layer": 2, "channel_mode": 3,
                       "bitrate_kbps": 4, "sample_rate_hz": 5,
                       "frame_bytes": 6, "samples_per_frame": 7,
                       "padding": 8, "unresolved_flag_25d5": 9}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=[c[0] for c in CASES])
    parser.add_argument("--normal-only", action="store_true")
    args = parser.parse_args()
    original = args.original_prg.read_bytes()
    original_slice(original, PARSER, PARSER_SHA256)
    original_slice(original, TABLES, TABLES_SHA256)
    args.output.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"passed": False, "qemu_sha256": digest,
              "original_prg_sha256": hashlib.sha256(original).hexdigest(), "cases": []}
    try:
        for case in CASES:
            if args.case and args.case != case[0]:
                continue
            for icount in ((None,) if args.normal_only else (None, 5)):
                report["cases"].append(check(args.qemu, original, args.output, case, icount))
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == digest
        report["passed"] = all(c["passed"] and c["exit_code"] == 0 for c in report["cases"])
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
