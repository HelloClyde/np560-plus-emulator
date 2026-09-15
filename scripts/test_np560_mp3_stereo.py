#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native MS/reorder versus offline C; not an MP3 player/PCM test."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import subprocess

from build_np560_mp3_huffman import ROOT, TABLE_SOURCE, TABLE_SHA
from build_np560_mp3_requantize import build as build_requant
from build_np560_mp3_stereo import build
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr, write_word
from test_np560_mac import run
from test_np560_mp3_requantize import signed_words, FIXTURE
from test_np560_mp3_spectrum import TEMPLATE_SHA


def reference_binary(output):
    raw = (ROOT/"doc/sources/ffmpeg-mpeg-tables-20260907/mpegaudiodec_template-n8.0.c").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == TEMPLATE_SHA
    text = raw.decode().replace("\r\n", "\n")
    a, b = text.index("static void compute_band_indexes("), text.index("/* layer 1 unscaling */")
    c, d = text.index("static void reorder_block("), text.index("#define ISQRT2")
    common = TABLE_SOURCE.read_bytes()
    assert hashlib.sha256(common).hexdigest() == TABLE_SHA
    common = common.decode()
    pos = common.index("ff_band_size_short[")
    table = common[common.rfind("const uint8_t", 0, pos):common.index("};", pos)+2]
    (output/"ffmpeg_reorder.inc").write_text(table+"\n"+text[a:b]+text[c:d], encoding="utf-8")
    binary = output/"stereo-reference"
    result = subprocess.run(["gcc", "-O2", "-std=c99", "-Wall", "-Wextra", "-Werror", "-I", str(output),
        str(ROOT/"scripts/test_np560_mp3_stereo_reference.c"), "-o", str(binary)], capture_output=True, text=True)
    (output/"stereo-reference-compiler.log").write_text(result.stdout+result.stderr, encoding="utf-8")
    if result.returncode: raise RuntimeError(result.stderr)
    return binary


def reference(output, cases, binary=None):
    binary = binary or reference_binary(output)
    rows = [c["mode"]+" "+" ".join(map(str, c["input"])) for c in cases]
    result = subprocess.run([str(binary)], input="\n".join(rows)+"\n", text=True, capture_output=True, check=True)
    rows = result.stdout.splitlines()
    assert len(rows) == len(cases)
    for c, row in zip(cases, rows):
        values = list(map(int, row.split()))
        c["status"], c["expected"] = values[0], values[1:]
        assert len(c["expected"]) == {"P": 2, "R": 576, "M": 1152}[c["mode"]]


def cases():
    rng = random.Random(560576)
    edges = [-(1 << 31), -(1 << 30), -65537, -65536, -65535, -1, 0, 1, 65535, 65536, 65537, 1 << 30, (1 << 31)-1]
    # All sign/carry combinations, widened-sum successes and true overflows.
    pairs = [{"mode": "P", "input": [m, s]} for m in edges for s in edges]
    pairs += [{"mode": "P", "input": [rng.randrange(-2**31, 2**31) for _ in range(2)]} for _ in range(512)]
    vectors = []
    for rate in range(9):
        for block, mixed in ((0, 0), (1, 0), (2, 0), (2, 1), (3, 0)):
            values = [((i*0x9e3779b9+rate*73) & 0xffffffff)-2**31 for i in range(576)]
            vectors.append({"mode": "R", "input": [rate, block, mixed]+values})
    for geometry in ((9, 2, 0), (0, 4, 0), (0, 2, 2), (-1, 2, 0)):
        vectors.append({"mode": "R", "input": list(geometry)+list(range(576))})
    for i in range(5):
        values = [rng.randrange(-2**29, 2**29) for _ in range(1152)]
        if i > 1:
            index = (0, 19, 575)[i-2]
            values[index] = values[576+index] = 2**31-1
        vectors.append({"mode": "M", "input": values})
    return pairs, vectors


def words32(values):
    result = []
    for v in values: result += [v & 65535, (v >> 16) & 65535]
    return result


def payload(records):
    data = bytearray(FIXTURE-0x201000+len(records)*2)
    for core in (build_requant(), build()):
        for key, addr in (("code", "code_address"), ("tables", "table_address")):
            if key not in core: continue
            off = core[addr]-0x201000
            data[off:off+len(core[key])] = core[key]
    data[FIXTURE-0x201000:] = struct.pack(f"<{len(records)}H", *(n&65535 for n in records))
    return data


def check_pairs(qemu, output, cases, name, icount=None):
    core, records, expected = build(), [], []
    for i, c in enumerate(cases):
        records += words32(c["input"]) + [26 if i % 2 else 2]
        expected += words32(c["expected"]) + [c["status"], 26 if i % 2 else 2]
    assert len(records)*2 < 0x8000 and 0x2400+len(expected)*2 < 0x5e00
    a = _DMCUAssembler(0x200000)
    a.emit(0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, FIXTURE >> 15,
           0x68F9, 0x8000, 0x68FC, len(cases), 0x68F8, 0x2400, 0x68FB, 0x4444,
           0x68FD, 0x5555, 0x68FE, 0x6666)
    a.label("pair")
    a.emit(0x3809, 0x3819, 0x3839, 0x3849, 0x3859, 0x58F5, 0x1F80,
           0xBD20, core["entries"]["ms_pair"] & 65535, 0x0858,
           0x1A50, 0x1A51, 0x1A53, 0x1A54, 0x1A52)
    read_sfr(a.words, 0, 6)
    a.emit(0x1A56, 0x0885, 0x52C1)
    a.ajmp("pair", 2)
    read_sfr(a.words, 0x11, 7)
    return run(qemu, output, name, a.finish(),
        {7: FIXTURE >> 15, 8: 0x2400+len(expected)*2, 9: 0x8000+len(records)*2, 11: 0x4444,
         12: 0, 13: 0x5555, 14: 0x6666, 15: 0x6000}, tail=(0x1000, payload(records)),
        expected_data=signed_words(expected), icount=icount, timeout=60, poll_interval=.25,
        metadata={"pairs": len(cases), "pcm_produced": False, "code_sha256": hashlib.sha256(core["code"]).hexdigest()})


def check_vectors(qemu, output, cases, name, icount=None):
    core, records, expected = build(), [], []
    mode = cases[0]["mode"]
    assert all(c["mode"] == mode for c in cases)
    guards = (0x00fe, 0x1300, 0x204e, 0x205a, 0x4ffe, 0x5900)
    for c in cases:
        records += c["input"][:3]+words32(c["input"][3:]) if mode == "R" else words32(c["input"])
        expected += [576 if not c["status"] else 0, c["status"]]+words32(c["expected"])+[0xcafe]*len(guards)
    assert len(records)*2 < 0x8000 and 0x2400+len(expected)*2 < 0x4ffe
    a = _DMCUAssembler(0x200000)
    a.emit(0x6800, 26, 0x68FF, 0x6000, 0x6810, 0, 0x6811, FIXTURE >> 15,
           0x68F9, 0x8000, 0x68F6, 0x2400, 0x68F7, 0, 0x68F8, len(cases), 0x68FB, 0x4444)
    for addr in guards: write_word(a.words, addr, 0xcafe)
    if mode == "R":
        write_word(a.words, 0x2056, 0x0100)
        write_word(a.words, 0x2058, 0x5000)
    else:
        write_word(a.words, 0x2050, 0x0100)
        write_word(a.words, 0x2052, 0x0a00)
    a.label("vector")
    if mode == "R":
        for addr in (0x2050, 0x2052, 0x2054): a.emit(0x3809, 0xa8f0, addr)
    a.emit(0x68F3, 0x0100, 0x68F4, 1152 if mode == "R" else 2304)
    a.label("input")
    a.emit(0x3809, 0x1A30, 0x5241)
    a.ajmp("input", 2)
    if mode == "R":
        a.emit(0x68F3, 0x5000, 0x68F4, 1152, 0x68F0, 0xa55a)
        a.label("clear")
        a.emit(0x1A30, 0x5241)
        a.ajmp("clear", 2)
    entry = "reorder" if mode == "R" else "ms_spectrum"
    a.emit(0x68F3, 0x2050, 0xBD20, core["entries"][entry] & 65535, 0x1A60, 0x1A62,
           0x68F3, 0x5000 if mode == "R" else 0x0100, 0x68F4, 1152 if mode == "R" else 2304)
    a.label("dump")
    a.emit(0x3803, 0x1A60, 0x5241)
    a.ajmp("dump", 2)
    for addr in guards: a.emit(0x88F0, addr, 0x1A60)
    a.emit(0x5071, 0x5281)
    a.ajmp("vector", 2)
    read_sfr(a.words, 0, 12)
    read_sfr(a.words, 0x11, 5)
    (output/f"{name}.vectors.json").write_text(json.dumps(cases)+"\n", encoding="utf-8")
    return run(qemu, output, name, a.finish(),
        {5: FIXTURE >> 15, 6: 0x2400+len(expected)*2, 7: len(cases), 8: 0,
         9: 0x8000+len(records)*2, 11: 0x4444, 12: 26, 15: 0x6000},
        tail=(0x1000, payload(records)), expected_data=signed_words(expected), icount=icount,
        timeout=60, poll_interval=.25, metadata={"mode": mode, "vectors": len(cases),
        "pcm_produced": False, "code_sha256": hashlib.sha256(core["code"]).hexdigest()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    pairs, vectors = cases()
    if args.first_only:
        pairs = pairs[:169]
        vectors = vectors[2:4]+vectors[-5:-4]
    reference(args.output, pairs+vectors)
    # Separate real-valued check: catch systematic scaling mistakes even
    # if the C and guest integer formula agree. For a signed 33-bit sum,
    # the pinned Q28 invsqrt2 adds less than 4 LSB; floor adds <1 LSB.
    max_error = 0.0
    for c in pairs:
        if c["status"]: continue
        m, s = c["input"]
        delta = max(abs(c["expected"][0]-(m+s)/math.sqrt(2)), abs(c["expected"][1]-(m-s)/math.sqrt(2)))
        assert delta < 5
        max_error = max(max_error, delta)
    report = {"passed": False, "cases": [], "pcm_produced": False, "intensity_stereo_available": False,
              "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(), "formula_max_q28_lsb_error": max_error}
    try:
        report["cases"].append(check_pairs(args.qemu, args.output, pairs, "ms-pairs"))
        for mode, batch in (("R", 4), ("M", 2)):
            selected = [c for c in vectors if c["mode"] == mode]
            for i in range(0, len(selected), batch):
                report["cases"].append(check_vectors(args.qemu, args.output, selected[i:i+batch], f"{mode}-{i:03d}"))
        if not args.first_only:
            report["cases"].append(check_pairs(args.qemu, args.output, pairs[-128:], "ms-pairs-icount5", 5))
            for mode in ("R", "M"):
                selected = [c for c in vectors if c["mode"] == mode and c["status"] == 0]
                report["cases"].append(check_vectors(args.qemu, args.output, selected[-2:], f"{mode}-icount5", 5))
        report["passed"] = all(c["passed"] and c["exit_code"] == 0 for c in report["cases"])
    except AssertionError as exc:
        detail = exc.args[0] if exc.args else "assertion failed"
        if isinstance(detail, dict):
            detail = {"name": detail.get("name"), "registers": detail.get("registers"),
                "differences": [(i, x, y) for i, (x, y) in enumerate(zip(detail.get("actual_samples", []), detail.get("expected_samples", []))) if x != y][:16]}
        report["failure"] = str(detail)[:2500]
        print(report["failure"], flush=True)
    finally:
        (args.output/"report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
