#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native scalefactor fields and bit consumption vs original libmad functions."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from build_np560_mp3_huffman import ROOT, build as build_entropy
from build_np560_mp3_scalefactors import build, MAD_SHA
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr, write_word
from test_np560_mac import run

PREVIOUS = [(i*7+5) & 31 for i in range(39)]
GUARDS = (0x1FFE, 0x200A, 0x21FE, 0x224E, 0x227E, 0x22CE, 0x22FE, 0x234E)


def source_excerpt():
    raw = (ROOT / "doc/sources/libmad-20260907/layer3.c").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MAD_SHA
    source = raw.decode().replace("\r\n", "\n")
    result = source[:source.index("# ifdef HAVE_CONFIG_H")]
    start = source.index("enum {", source.index("/* --- Layer III"))
    stop = source.index("\n};", source.index("struct sideinfo {"))+3
    result += source[start:stop]
    for name in ("sflen_table[", "nsfb_table["):
        marker = source.index(name)
        start = source.rfind("static", 0, marker)
        result += "\n" + source[start:source.index("\n};", marker)+3]
    for name in ("III_scalefactors_lsf(", "III_scalefactors("):
        start = source.index("static\nunsigned int " + name)
        result += "\n" + source[start:source.index("\n/*", start)]
    return result


def reference(output, cases):
    excerpt = source_excerpt()
    (output / "libmad_scalefactors.inc").write_text(excerpt, encoding="utf-8")
    binary = output / "scalefactors-reference"
    subprocess.run(["gcc", "-O2", "-std=c99", "-Wall", "-Wextra", "-Werror", "-I", str(output),
                    str(ROOT / "scripts/test_np560_mp3_scalefactors_reference.c"), "-o", str(binary)],
                   check=True, capture_output=True, text=True)
    inputs = [" ".join(str(c[k]) for k in ("lsf", "comp", "block", "flags", "scfsi", "intensity", "prefix"))
              + " " + c["stream"] for c in cases]
    rows = subprocess.run([str(binary)], input="\n".join(inputs)+"\n", text=True,
                          check=True, capture_output=True).stdout.splitlines()
    assert len(rows) == len(cases)
    for c, row in zip(cases, rows):
        values = list(map(int, row.split()))
        assert len(values) == 80
        c.update(consumed=values[0], out_flags=values[1], sf=values[2:41], mask=values[41:], status=0)
    return {"libmad_layer3_sha256": MAD_SHA, "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest()}


def vectors():
    result = []
    for lsf, count in ((0, 16), (1, 512)):
        for comp in range(count):
            for block, mixed in ((0, 0), (2, 0), (2, 8)):
                for value in range(2 if lsf else 16):
                    seed = comp+value+mixed+block
                    result.append({"lsf": lsf, "comp": comp, "block": block, "flags": mixed | seed % 4,
                                   "scfsi": 0 if lsf else value, "intensity": value if lsf else 0,
                                   "prefix": seed % 16, "alias": int(not lsf and value % 2 == 1),
                                   "budget": 4095, "available": 512,
                                   "stream": bytes((i*37+seed*13) & 255 for i in range(64)).hex()})
    return result


def context(c, bank, pointer):
    consumed = c["prefix"]+c["consumed"]
    loaded = (consumed+15)//16
    cache = 0
    if loaded:
        raw = bytes.fromhex(c["stream"])
        value = int.from_bytes(raw[(loaded-1)*2:loaded*2], "big")
        cache = (value << (consumed-(loaded-1)*16)) & 65535
    absolute = (bank << 15)+(pointer & 0x7fff)+loaded*2
    return [absolute >> 15, 0x8000 | (absolute & 0x7fff), cache, loaded*16-consumed, c["available"]-consumed]


def check(qemu, output, name, cases, bank=0, pointer=0xA100, icount=None, trace=False):
    entropy, sf = build_entropy(), build()
    a = _DMCUAssembler(0x200000)
    a.emit(0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 0x42,
           0x68FC, 0x2000, 0x68F9, 0x8000, 0x68FB, 0x4444,
           0x68F7, 0, 0x68F8, len(cases), 0x68FA, 0x2400)
    for address in GUARDS: write_word(a.words, address, 0xCAFE)
    for address, value in ((0x2082, 0x20C0), (0x2088, 0x2200), (0x208C, 0x2280)):
        write_word(a.words, address, value)
    a.label("next")
    for address in (0x2080, 0x20C6, 0x20CA, 0x20C8, 0x2084, 0x208A, 0x20C0, 0x2008):
        a.emit(0x3809, 0xA8F0, address)
    a.emit(0x3869, 0x3859)
    for address, value in ((0x2000, bank), (0x2002, pointer), (0x2004, 0), (0x2006, 0)):
        write_word(a.words, address, value)
    for i in range(32):
        absolute = (bank << 15)+(pointer & 0x7fff)+i*2
        a.emit(0x3809, 0x6810, absolute >> 15, 0xA8F0, absolute & 0x7fff)
    a.emit(0x6810, 0, 0x0806, 0xBD20, entropy["entries"]["read_bits"] & 65535)
    for i, value in enumerate(PREVIOUS): write_word(a.words, 0x2300+i*2, value)
    a.emit(0x68F3, 0x2200, 0x68F4, 0x2280, 0x68F1, 39, 0x68F0, 0xA55A)
    a.label("fill")
    a.emit(0x1A30, 0x1A40, 0x5211)
    a.ajmp("fill", 2)
    write_word(a.words, 0x2086, 0x2300)
    a.emit(0x76F5, 0)
    a.ajmp("no_alias", 1)
    a.emit(0x68F3, 0x2300, 0x68F4, 0x2200, 0x68F1, 39)
    a.label("alias_copy")
    a.emit(0x3803, 0x1A40, 0x5211)
    a.ajmp("alias_copy", 2)
    write_word(a.words, 0x2086, 0x2200)
    a.label("no_alias")
    a.emit(0x68F3, 0x2080, 0xBD20, sf["entries"]["scalefactors"] & 65535,
           0x1AA0, 0x1AA2, 0x88F0, 0x20C8, 0x1AA0)
    for address, count in ((0x2000, 5), (0x2200, 39), (0x2280, 39)):
        a.emit(0x68F3, address, 0x68F1, count)
        a.label(f"dump_{address:x}")
        a.emit(0x3803, 0x1AA0, 0x5211)
        a.ajmp(f"dump_{address:x}", 2)
    for address in GUARDS: a.emit(0x88F0, address, 0x1AA0)
    a.emit(0x5071, 0x5281)
    a.ajmp("next", 2)
    read_sfr(a.words, 0x11, 13)
    program = a.finish()
    assert len(program)*2+2 < 0x1000
    records, expected = [], []
    for c in cases:
        records += [c[k] for k in ("lsf", "comp", "block", "flags", "scfsi", "intensity",
                                  "budget", "available", "prefix", "alias")]
        raw = bytes.fromhex(c["stream"])
        records += [int.from_bytes(raw[i:i+2], "big") for i in range(0, 64, 2)]
        expected += [c["consumed"], c["status"], c["out_flags"]]+context(c, bank, pointer)+c["sf"]+c["mask"]+[0xCAFE]*len(GUARDS)
    assert len(records)*2 < 0x8000 and 0x2400+len(expected)*2 < 0x5E00
    payload = bytearray(0xF000+len(records)*2)
    for core in (entropy, sf):
        for key, addr in (("code", "code_address"), ("tables", "table_address")):
            start = core[addr]-entropy["code_address"]
            payload[start:start+len(core[key])] = core[key]
    payload[0xF000:] = struct.pack(f"<{len(records)}H", *records)
    (output / f"{name}.vectors.json").write_text(json.dumps(cases, indent=2)+"\n", encoding="utf-8")
    return run(qemu, output, name, program,
               {7: len(cases), 8: 0, 9: 0x8000+len(records)*2, 11: 0x4444, 12: 0x2000, 13: 0x42, 15: 0x6000},
               tail=(0x1000, payload), icount=icount, expected_disassembly="scall 20:1000" if trace else None,
               expected_data=[(n & 65535)-(65536 if n & 0x8000 else 0) for n in expected],
               metadata={"scalefactor_cases": len(cases), "native_core_sha256": hashlib.sha256(sf["code"]).hexdigest(),
                         "table_sha256": hashlib.sha256(sf["tables"]).hexdigest(),
                         "factory_rom_services_replaced": False, "pcm_produced": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cases = vectors()
    oracle = reference(args.output, cases)
    # Preflight is deliberately transactional, unlike the reference's
    # partial read before reporting an error. Compare unchanged state.
    errors = []
    for c in cases[::97]:
        if not c["consumed"]: continue
        for status, overrides in ((1, {"available": c["prefix"]+c["consumed"]-1}),
                                  (3, {"budget": c["consumed"]-1})):
            errors.append(dict(c, **overrides, consumed=0, status=status, out_flags=c["flags"],
                               sf=PREVIOUS if c["alias"] else [0xA55A]*39, mask=[0xA55A]*39))
    for overrides in ({"lsf": 2}, {"comp": 16}, {"block": 4}, {"scfsi": 16}, {"intensity": 2},
                      {"budget": 4096}, {"lsf": 1, "comp": 512}):
        c = cases[0]
        errors.append(dict(c, **overrides, consumed=0, status=2, out_flags=c["flags"], sf=[0xA55A]*39, mask=[0xA55A]*39))
    report = {"passed": False, "reference": oracle, "cases": [], "pcm_produced": False,
              "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    try:
        selected = cases[48:49] if args.first_only else cases+errors
        for start in range(0, len(selected), 64):
            report["cases"].append(check(args.qemu, args.output, f"scalefactors-{start:04d}", selected[start:start+64], trace=args.first_only))
        if not args.first_only:
            report["cases"].append(check(args.qemu, args.output, "scalefactors-cross-bank", cases[-64:],
                                         bank=0xA0, pointer=0xFFFE, icount=5))
        report["passed"] = all(c["passed"] and c["exit_code"] == 0 for c in report["cases"])
    except AssertionError as exc:
        detail = exc.args[0] if exc.args else "assertion failed"
        if isinstance(detail, dict):
            detail = {"name": detail.get("name"), "registers": detail.get("registers"),
                      "differences": [(i, x, y) for i, (x, y) in enumerate(zip(detail.get("actual_samples", []),
                          detail.get("expected_samples", []))) if x != y][:20]}
        report["failure"] = str(detail)[:2000]
        print(report["failure"], flush=True)
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
