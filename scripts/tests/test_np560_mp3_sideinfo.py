#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare native DMCU sideinfo to the pinned, unmodified libmad function.

No NAND, player state, QEMU modifications, or host guest-memory writes.
The C function runs offline only to provide expected fields for each input.
"""
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
import random
import struct
import subprocess

from build_np560_mp3_huffman import ROOT, build as build_entropy
from build_np560_mp3_sideinfo import build, WORDS
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr, read_word, write_word
from test_np560_mac import run

MAD_SHA = "2da2e4b9176b5935259d3cc032253a9f514309c339770874bc0873413d55cb11"


def pack_side(lsf, nch, seed, *, block=None, big=None, scfsi=None):
    rng = random.Random(seed)
    bits, windows = [], []

    def add(width, value=None):
        value = rng.randrange(1 << width) if value is None else value
        bits.append(f"{value:0{width}b}")
        return value

    add(8 if lsf else 9)
    add((1 if nch == 1 else 2) if lsf else (5 if nch == 1 else 3))
    if not lsf:
        for _ in range(nch): add(4, scfsi)
    for _ in range((1 if lsf else 2)*nch):
        add(12)
        add(9, rng.randrange(289) if big is None else big)
        add(8)
        add(9 if lsf else 4)
        ws = add(1, int(block != 0) if block is not None else None)
        windows.append(ws)
        if ws:
            add(2, (rng.randrange(1, 4) if block is None else block & 3))
            add(1)
            for _ in range(2): add(5)
            for _ in range(3): add(3)
        else:
            for _ in range(3): add(5)
            add(4)
            add(3)
        add(2 if lsf else 3)
    stream = "".join(bits)
    assert len(stream) == ((72 if nch == 1 else 136) if lsf else (136 if nch == 1 else 256))
    return {"lsf": lsf, "nch": nch, "side": stream, "windows": windows, "prefix": seed % 16}


def reference(output, cases):
    path = ROOT / "doc/sources/libmad-20260907/layer3.c"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MAD_SHA
    source = raw.decode("utf-8").replace("\r\n", "\n")
    flags_start = source.index("enum {", source.index("/* --- Layer III"))
    struct_start = source.index("struct sideinfo {")
    func_start = source.index("static\nenum mad_error III_sideinfo(")
    excerpt = (source[:source.index("# ifdef HAVE_CONFIG_H")]
               + source[flags_start:source.index("\n};", flags_start)+3]
               + "\n" + source[struct_start:source.index("\n};", struct_start)+3]
               + "\n" + source[func_start:source.index("\n/*", func_start)])
    (output / "libmad_sideinfo.inc").write_text(excerpt, encoding="utf-8")
    binary = output / "sideinfo-reference"
    subprocess.run(["gcc", "-O2", "-std=c99", "-Wall", "-Wextra", "-Werror",
                    "-I", str(output), str(ROOT / "scripts/test_np560_mp3_sideinfo_reference.c"),
                    "-o", str(binary)], check=True, capture_output=True, text=True)
    inputs = []
    for c in cases:
        data = int(c["side"], 2).to_bytes(len(c["side"])//8, "big")
        inputs.append(f'{c["lsf"]} {c["nch"]} {data.hex()}')
    rows = subprocess.run([str(binary)], input="\n".join(inputs)+"\n", text=True,
                          capture_output=True, check=True).stdout.splitlines()
    assert len(rows) == len(cases)
    for c, row in zip(cases, rows):
        status, consumed, *fields = map(int, row.split())
        assert consumed == len(c["side"]) and len(fields) == WORDS
        for index, ws in enumerate(c["windows"]): fields[8+index*16+14] = ws
        c.update(status=status, consumed=consumed, fields=fields)
    return {"libmad_layer3_sha256": MAD_SHA,
            "function_excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
            "oracle": "unmodified III_sideinfo executed offline; not linked into QEMU"}


def mp3_frames(path):
    """Offline fixture splitting only; does not replace the factory parser."""
    raw = path.read_bytes()
    offset = 0
    if raw.startswith(b"ID3"):
        assert all(n < 128 for n in raw[6:10])
        offset = 10 + sum(n << (7*(3-i)) for i, n in enumerate(raw[6:10]))
        if raw[5] & 0x10: offset += 10
    frames = []
    while offset+4 <= len(raw):
        if raw[offset:offset+3] == b"TAG" and len(raw)-offset == 128: break
        header = int.from_bytes(raw[offset:offset+4], "big")
        version, layer = (header >> 19) & 3, (header >> 17) & 3
        bitrate_index, rate_index = (header >> 12) & 15, (header >> 10) & 3
        assert header >> 21 == 0x7FF and version != 1 and layer == 1
        assert bitrate_index not in (0, 15) and rate_index != 3
        lsf, nch = int(version != 3), 1 if header >> 6 & 3 == 3 else 2
        rates = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160) if lsf else (
            0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
        hz = (44100, 48000, 32000)[rate_index] >> (0 if version == 3 else (1 if version == 2 else 2))
        frame_size = (72000 if lsf else 144000)*rates[bitrate_index]//hz + ((header >> 9) & 1)
        start = offset+4+(0 if header >> 16 & 1 else 2)
        side_size = (9 if nch == 1 else 17) if lsf else (17 if nch == 1 else 32)
        assert start+side_size <= offset+frame_size <= len(raw)
        side = "".join(f"{b:08b}" for b in raw[start:start+side_size])
        header_bits = (8+(1 if nch == 1 else 2)) if lsf else (9+(5 if nch == 1 else 3)+4*nch)
        windows = [int(side[header_bits+i*(63 if lsf else 59)+(38 if lsf else 33)])
                   for i in range((1 if lsf else 2)*nch)]
        frames.append({"lsf": lsf, "nch": nch, "side": side, "windows": windows,
                       "prefix": 0, "file_offset": offset, "frame_bytes": frame_size,
                       "main_data_hex": raw[start+side_size:offset+frame_size].hex()})
        offset += frame_size
    assert frames and offset == len(raw)
    return frames


def stream(c):
    return ("1011001110010110"[:c["prefix"]] + c["side"] + "1101101").ljust(320, "0")


def state(c, consumed):
    loaded = (consumed+15)//16
    cache = 0
    if loaded:
        word = int(stream(c)[(loaded-1)*16:loaded*16], 2)
        cache = (word << (consumed-(loaded-1)*16)) & 65535
    absolute = (c.get("bank", 0) << 15) + (c.get("pointer", 0xA200) & 0x7fff) + loaded*2
    available = c.get("available", c["prefix"]+len(c["side"])+7)
    return [absolute >> 15, 0x8000 | (absolute & 0x7fff), cache, loaded*16-consumed, available-consumed]


def check_batch(qemu, output, entropy, side, name, cases, icount=None, bank=0, pointer=0xA200):
    a = _DMCUAssembler(0x200000)
    a.emit(0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 0x42,
           0x68FC, 0x2000, 0x68F9, 0x8000, 0x68FB, 0x4444,
           0x68F7, 0, 0x68F8, len(cases), 0x68FA, 0x2400)
    for address in (0x1FFE, 0x200A, 0x20FE, 0x2190): write_word(a.words, address, 0xCAFE)
    a.label("next")
    # lsf, nch, available bits, prefix bits, then 20 input words.
    a.emit(0x3849, 0x3859, 0x3809, 0xA8F0, 0x2008, 0x3869)
    for address, value in ((0x2000, bank), (0x2002, pointer), (0x2004, 0), (0x2006, 0)):
        write_word(a.words, address, value)
    for index in range(20):
        absolute = (bank << 15) + (pointer & 0x7fff) + index*2
        a.emit(0x3809, 0x6810, absolute >> 15, 0xA8F0, absolute & 0x7fff)
    a.emit(0x6810, 0, 0x0806, 0xBD20, entropy["entries"]["read_bits"] & 65535)
    a.emit(0x68F0, 0xA55A, 0x68F1, WORDS, 0x68F3, 0x2100)
    a.label("fill")
    a.emit(0x1A30, 0x5211)
    a.ajmp("fill", 2)
    a.emit(0x0804, 0x0815, 0x68F3, 0x2100, 0xBD20, side["entries"]["sideinfo"] & 65535)
    a.emit(0x1AA0, 0x1AA2)
    for address, count in ((0x2000, 5), (0x2100, WORDS)):
        a.emit(0x68F3, address, 0x68F1, count)
        a.label(f"dump_{address}")
        a.emit(0x3803, 0x1AA0, 0x5211)
        a.ajmp(f"dump_{address}", 2)
    for address in (0x1FFE, 0x200A, 0x20FE, 0x2190):
        read_word(a.words, address, 0)
        a.emit(0x1AA0)
    a.emit(0x5071, 0x5281)
    a.ajmp("next", 2)
    read_sfr(a.words, 0x11, 13)
    words = a.finish()
    assert len(words)*2+2 < 0x1000
    records, expected = [], []
    for c in cases:
        c.update(bank=bank, pointer=pointer)
        bits = stream(c)
        available = c.get("available", c["prefix"]+len(c["side"])+7)
        records += [c["lsf"], c["nch"], available, c["prefix"]]
        records += [int(bits[i:i+16], 2) for i in range(0, 320, 16)]
        expected += [c["consumed"], c["status"]] + state(c, c["prefix"]+c["consumed"])
        expected += c["fields"] + [0xCAFE]*4
    assert len(records)*2 < 0x8000 and 0x2400+len(expected)*2 < 0x6000-512
    payload = bytearray(0xF000+len(records)*2)
    for address, code in ((entropy["code_address"], entropy["code"]),
                          (entropy["table_address"], entropy["tables"]),
                          (side["code_address"], side["code"])):
        start = address-entropy["code_address"]
        payload[start:start+len(code)] = code
    payload[0xF000:] = struct.pack(f"<{len(records)}H", *records)
    (output / f"{name}.vectors.json").write_text(json.dumps(cases, indent=2)+"\n", encoding="utf-8")
    return run(qemu, output, name, words,
               {7: len(cases), 8: 0, 9: 0x8000+len(records)*2, 11: 0x4444,
                12: 0x2000, 13: 0x42, 15: 0x6000}, tail=(0x1000, payload), icount=icount,
               expected_data=[(n & 65535) - (65536 if n & 0x8000 else 0) for n in expected],
               metadata={"sideinfo_cases": len(cases), "native_core_sha256": hashlib.sha256(side["code"]).hexdigest(),
                         "factory_rom_services_replaced": False, "pcm_produced": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-only", action="store_true")
    parser.add_argument("--mp3", type=Path, help="Existing MP3 fixture; read-only, no playback")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    entropy, side = build_entropy(), build()
    (args.output / "sideinfo.bin").write_bytes(side["code"])
    cases = []
    for lsf in (0, 1):
        for nch in (1, 2):
            for seed in range(32): cases.append(pack_side(lsf, nch, seed))
            for block in (0, 1, 2, 3, 4):
                for big in (288, 289, 511):
                    for scfsi in (0, 15):
                        cases.append(pack_side(lsf, nch, 7+block+big+scfsi,
                                               block=block, big=big, scfsi=scfsi))
    if args.mp3:
        cases += mp3_frames(args.mp3)
    oracle = reference(args.output, cases)
    errors = []
    for lsf in (0, 1):
        for nch in (1, 2):
            c = next(c for c in cases if c["lsf"] == lsf and c["nch"] == nch)
            for missing in (1, len(c["side"]), len(c["side"])-1):
                errors.append(dict(c, available=c["prefix"]+len(c["side"])-missing,
                                   status=1, consumed=0, fields=[0xA55A]*WORDS))
    for lsf, nch in ((2, 1), (65535, 2), (0, 0), (1, 3), (0, 65535)):
        errors.append(dict(cases[0], lsf=lsf, nch=nch, status=2, consumed=0, fields=[0xA55A]*WORDS))
    report = {"passed": False, "reference": oracle, "cases": [], "pcm_produced": False,
              "code_bytes": len(side["code"]), "code_sha256": hashlib.sha256(side["code"]).hexdigest(),
              "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    try:
        selected = cases[:1] if args.first_only else cases+errors
        for offset in range(0, len(selected), 32):
            report["cases"].append(check_batch(args.qemu, args.output, entropy, side,
                        f"sideinfo-{offset:03d}", selected[offset:offset+32]))
        if not args.first_only:
            report["cases"].append(check_batch(args.qemu, args.output, entropy, side,
                "sideinfo-cross-bank-icount5", cases[:32], icount=5, bank=0xA0, pointer=0xFFFE))
        report["passed"] = all(c["passed"] and c["exit_code"] == 0 for c in report["cases"])
    except AssertionError as exc:
        detail = exc.args[0] if exc.args else "assertion failed"
        if isinstance(detail, dict):
            detail = {"name": detail.get("name"), "registers": detail.get("registers"),
                      "differences": [(i, x, y) for i, (x, y) in enumerate(zip(
                          detail.get("actual_samples", []), detail.get("expected_samples", []))) if x != y][:20]}
        report["failure"] = str(detail)[:2000]
        print(report["failure"], flush=True)
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
