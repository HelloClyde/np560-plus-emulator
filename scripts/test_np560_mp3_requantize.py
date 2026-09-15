#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native Q28 requantization against pinned offline C references, NOT PCM."""
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
from build_np560_mp3_scalefactors import MAD_SHA
from build_np560_mp3_requantize import build, RQ_SOURCE, RQ_SHA
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr, write_word
from test_np560_mac import run
from test_np560_mp3_spectrum import TEMPLATE_SHA

FIXTURE = 0x3C8000
MAD = ROOT / "doc/sources/libmad-20260907"


def reference_binary(output):
    raw = (MAD/"layer3.c").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MAD_SHA
    assert hashlib.sha256(RQ_SOURCE.read_bytes()).hexdigest() == RQ_SHA
    text = raw.decode().replace("\r\n", "\n")
    start = text.index("static\nstruct fixedfloat")
    stop = text.index("/*\n * coefficients for aliasing reduction", start)
    fn = text.index("static\nmad_fixed_t III_requantize(")
    end = text.index("/* we must take care", fn)
    # Preserve libmad's expressions/rounding, but widen its intermediate
    # and return type. An unsigned shift-five value may become a valid
    # signed Q28 magnitude AFTER multiplying by 2^(-1/4..-3/4).
    # The wrapper applies the final asymmetric signed range, including -8.
    body = text[fn:end].replace("mad_fixed_t III_requantize(", "int64_t III_requantize(")
    body = body.replace("mad_fixed_t requantized;", "int64_t requantized;")
    body = body.replace("exp >= 5", "exp >= 6")
    body = body.replace("requantized = MAD_F_MAX;", "overflow = 1; requantized = MAD_F_MAX;")
    source = text[start:stop] + body
    (output/"libmad_requantize.inc").write_text(source, encoding="utf-8")
    template = (ROOT/"doc/sources/ffmpeg-mpeg-tables-20260907/mpegaudiodec_template-n8.0.c").read_bytes()
    assert hashlib.sha256(template).hexdigest() == TEMPLATE_SHA
    text = template.decode().replace("\r\n", "\n")
    a, b = text.index("static void compute_band_indexes("), text.index("/* layer 1 unscaling */")
    c, d = text.index("static void exponents_from_scale_factors("), text.index("static void switch_buffer(")
    raw = TABLE_SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == TABLE_SHA
    common = raw.decode()
    arrays = []
    for name in ("ff_band_size_long", "ff_band_size_short", "ff_mpa_pretab"):
        pos = common.index(name+"[")
        arrays.append(common[common.rfind("const uint8_t", 0, pos):common.index("};", pos)+2])
    (output/"ffmpeg_exponents.inc").write_text("\n".join(arrays)+"\n"+text[a:b]+text[c:d], encoding="utf-8")
    binary = output/"requant-reference"
    command = ["gcc", "-O2", "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wno-error=sign-compare", "-I", str(output), "-I", str(MAD),
               str(ROOT/"scripts/test_np560_mp3_requantize_reference.c"), "-o", str(binary)]
    result = subprocess.run(command, capture_output=True, text=True)
    (output/"reference-compiler.log").write_text(result.stdout+result.stderr, encoding="utf-8")
    if result.returncode: raise RuntimeError(result.stderr)
    return binary


def scalar_cases():
    edges = [0, 1, -1, 2, -2, 15, 16, 255, -255, 8191, 8192, 8206, -8206, 8207, -8207, -32768]
    exponents = [-32768, -256, -211, -145, -140, -129, -128, -127, -126, -125,
                 -100, -65, -64, -63, -62, -61, -60, -59, -58, -57, -4, -3, -2, -1,
                 0, 1, 2, 3, 4, 11, 12, 13, 45, 32767]
    cases = [{"value": val, "exp": exp} for val in edges for exp in exponents]
    cases += [{"value": i if i % 2 else -i, "exp": (-216, -139, -100, -65, -64, -60, -59, -58)[i % 8]}
              for i in range(8207)]
    for i, c in enumerate(cases): c["socr"] = 26 if i % 2 else 2
    return cases


def vector_cases():
    rng = random.Random(56028)
    cases = []
    for rate in range(9):
        for block, mixed in ((0, 0), (1, 0), (2, 0), (2, 8), (3, 0)):
            for scale_pre in (0, 2, 4, 6):
                ch = [0, 0, rng.randrange(80, 151), 0, mixed|scale_pre, block, 0, 0, 0,
                      rng.randrange(8), rng.randrange(8), rng.randrange(8), 0, 0, int(block != 0), 0]
                # Include zeros, signed maximal escapes, and varied carries.
                quant = [rng.randrange(-8206, 8207) for _ in range(576)]
                quant[:9] = [0, 1, -1, 15, -15, 8191, 8192, 8206, -8206]
                cases.append({"rate": rate, "channel": ch, "sf": [rng.randrange(32) for _ in range(39)],
                              "quant": quant, "kind": "all-band-geometries"})
    for kind in ("bad-rate", "bad-gain", "bad-flags", "bad-block", "bad-subgain", "bad-sf", "bad-quant"):
        c = {"rate": 0, "channel": [0, 0, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
             "sf": [0]*39, "quant": [0]*576, "kind": kind}
        if kind == "bad-rate": c["rate"] = 9
        elif kind == "bad-gain": c["channel"][2] = 256
        elif kind == "bad-flags": c["channel"][4] = 16
        elif kind == "bad-block": c["channel"][5] = 4
        elif kind == "bad-subgain": c["channel"][11] = 8
        elif kind == "bad-sf": c["sf"][38] = 32
        else: c["quant"][575] = -32768
        cases.append(c)
    return cases


def reference(output, cases, mode, binary=None):
    binary = binary or reference_binary(output)
    rows = []
    for c in cases:
        fields = [c["value"], c["exp"]] if mode == "S" else [c["rate"]]+c["channel"]+c["sf"]+c["quant"]
        rows.append(mode+" "+" ".join(map(str, fields)))
    result = subprocess.run([str(binary)], input="\n".join(rows)+"\n", text=True, capture_output=True, check=True)
    rows = result.stdout.splitlines()
    assert len(rows) == len(cases)
    for c, row in zip(cases, rows):
        values = list(map(int, row.split()))
        c["status"] = values[0]
        if mode == "S":
            assert len(values) == 2
            c["result"] = values[1]
        else:
            assert len(values) == 616
            c["exponents"], c["q28"] = values[1:40], values[40:]


def overflow_cases():
    cases = []
    # Exact unit coefficients at exponent 45 are out of Q28 range. The
    # first two 44.1k long bands are four lines each. Check that a scalar
    # failure propagates without writing a counterfeit clipped sample.
    for index in (0, 5):
        quant = [0]*576
        quant[index] = 1
        cases.append({"rate": 0, "channel": [0, 0, 255, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                      "sf": [0]*39, "quant": quant, "kind": f"q28-overflow-at-{index}", "status": 3,
                      "exponents": [45]*(index//4+1)+[0]*(39-index//4-1),
                      "q28": [0]*index+[-1520786086]*(576-index)})
    return cases


def formula_crosscheck(cases):
    """Independent double evaluation of the public Layer III formula.

    At most 32 Q28 LSBs allow normalized-table/root rounding, not PCM
    tolerance. This also catches premature intermediate overflow even
    when the translated C and guest implementations make the same error.
    """
    maximum, checked = 0.0, 0
    for c in cases:
        if abs(c["value"]) > 8206: continue
        if not c["value"]:
            assert c["status"] == 0 and c["result"] == 0
            continue
        if c["exp"] > 128:
            assert c["status"] == 3
            continue
        amplitude = abs(c["value"])**(4.0/3.0) * 2.0**(c["exp"]/4.0) * 2.0**28
        if c["status"] == 3:
            assert amplitude >= 2147483647-32, c
        else:
            delta = abs(c["result"]-math.copysign(amplitude, c["value"]))
            assert delta <= 32, (c, delta)
            maximum = max(maximum, delta)
            checked += 1
    return {"nonzero_successes": checked, "maximum_q28_lsb_error": maximum, "limit_q28_lsb": 32}


def payload(core, records, resident=False):
    start = 0x031000 if resident else 0x201000
    data = bytearray(FIXTURE-start+len(records)*2)
    if not resident:
        for key, addr in (("code", "code_address"), ("tables", "table_address")):
            offset = core[addr]-start
            data[offset:offset+len(core[key])] = core[key]
    data[FIXTURE-start:] = struct.pack(f"<{len(records)}H", *(n&65535 for n in records))
    return data


def signed_words(words):
    return [(x&65535)-(65536 if x&0x8000 else 0) for x in words]


def check_scalar(qemu, output, name, cases, icount=None, resident_bundle=None):
    rom=None;code_checks=None
    if resident_bundle:
        from build_np560_mp3_resident import load_bundle
        from np560_mp3_link import fragments
        cores,rom,_=load_bundle(resident_bundle);core=cores["requantize"]
        code_checks=[(address,data) for _,address,data in fragments(core)]
    else: core=build()
    records,expected=[],[]
    for c in cases:
        records += [c["value"], c["exp"], c["socr"]]
        expected += [c["result"] & 65535, (c["result"] >> 16)&65535, c["status"], c["socr"]]
    assert len(records)*2 < 0x8000 and 0x2400+len(expected)*2 < 0x5E00
    a = _DMCUAssembler(0x030000 if rom is not None else 0x200000)
    a.emit(0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, FIXTURE >> 15,
           0x68F9, 0x8000, 0x68F6, 0x2400, 0x68F7, 0, 0x68F8, len(cases),
           0x68FB, 0x4444, 0x68FC, 0x5555, 0x68FD, 0x6666, 0x68FE, 0x7777)
    a.label("case")
    a.emit(0x3809, 0x3819, 0x3849, 0x58F4, 0x1F80, 0xBD00|core["entries"]["scalar"]>>16, core["entries"]["scalar"] & 65535,
           0x1A60, 0x1A61, 0x1A62)
    read_sfr(a.words, 0, 4)
    a.emit(0x1A64, 0x5071, 0x5281)
    a.ajmp("case", 2)
    read_sfr(a.words, 0x11, 5)
    result = run(qemu, output, name, a.finish(),
                 {5: FIXTURE >> 15, 6: 0x2400+len(expected)*2, 7: len(cases), 8: 0,
                  9: 0x8000+len(records)*2, 11: 0x4444, 12: 0x5555, 13: 0x6666, 14: 0x7777, 15: 0x6000},
                 tail=(0x1000, payload(core, records,rom is not None)), expected_data=signed_words(expected), icount=icount,
                 rom=rom,boot_mode="firmware-vma03" if rom is not None else "firmware",expected_code=code_checks,
                 timeout=60, poll_interval=0.25, metadata={"scalar_cases": len(cases), "pcm_produced": False,
                  "resident_code_and_paged_tables":rom is not None,
                  "code_sha256": hashlib.sha256(core["code"]).hexdigest()})
    return result


def check_vector(qemu, output, name, cases, icount=None):
    core, records, expected = build(), [], []
    guards = (0x0FFE, 0x1480, 0x207E, 0x20A0, 0x20FE, 0x214E, 0x21FE, 0x224E, 0x4FFE, 0x5900)
    for c in cases:
        records += [c["rate"]]+c["channel"]+c["sf"]+c["quant"]
        expected += [576 if c["status"] == 0 else 0, c["status"]]+c["exponents"]
        for v in c["q28"]: expected += [v&65535, (v>>16)&65535]
        expected += [0xCAFE]*len(guards)
    assert len(records)*2 < 0x8000 and 0x2400+len(expected)*2 < 0x4FFE
    a = _DMCUAssembler(0x200000)
    a.emit(0x6800, 26, 0x68FF, 0x6000, 0x6810, 0, 0x6811, FIXTURE >> 15,
           0x68F9, 0x8000, 0x68F6, 0x2400, 0x68F7, 0, 0x68F8, len(cases), 0x68FB, 0x4444)
    for addr in guards: write_word(a.words, addr, 0xCAFE)
    for i, value in enumerate((0x2080, 0x2100, 0, 0x1000, 0x5000, 0x2200)):
        write_word(a.words, 0x2050+2*i, value)
    a.label("case")
    a.emit(0x3809, 0xA8F0, 0x2054)
    for addr, count in ((0x2080, 16), (0x2100, 39), (0x1000, 576)):
        a.emit(0x68F3, addr, 0x68F4, count)
        a.label(f"input_{addr:x}")
        a.emit(0x3809, 0x1A30, 0x5241)
        a.ajmp(f"input_{addr:x}", 2)
    for addr, count in ((0x5000, 1152), (0x2200, 39)):
        a.emit(0x68F3, addr, 0x68F4, count, 0x68F0, 0xA55A)
        a.label(f"clear_{addr:x}")
        a.emit(0x1A30, 0x5241)
        a.ajmp(f"clear_{addr:x}", 2)
    a.emit(0x68F3, 0x2050, 0xBD20, core["entries"]["spectrum"] & 65535, 0x1A60, 0x1A62)
    for addr, count in ((0x2200, 39), (0x5000, 1152)):
        a.emit(0x68F3, addr, 0x68F4, count)
        a.label(f"dump_{addr:x}")
        a.emit(0x3803, 0x1A60, 0x5241)
        a.ajmp(f"dump_{addr:x}", 2)
    for addr in guards: a.emit(0x88F0, addr, 0x1A60)
    a.emit(0x5071, 0x5281)
    a.ajmp("case", 2)
    read_sfr(a.words, 0, 12)
    read_sfr(a.words, 0x11, 5)
    (output/f"{name}.vectors.json").write_text(json.dumps(cases, indent=2)+"\n", encoding="utf-8")
    return run(qemu, output, name, a.finish(),
               {5: FIXTURE >> 15, 6: 0x2400+len(expected)*2, 7: len(cases), 8: 0,
                9: 0x8000+len(records)*2, 11: 0x4444, 12: 26, 15: 0x6000},
               tail=(0x1000, payload(core, records)), expected_data=signed_words(expected), icount=icount,
               timeout=60, poll_interval=0.25, metadata={"spectra": len(cases), "pcm_produced": False,
                "code_sha256": hashlib.sha256(core["code"]).hexdigest()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-only", action="store_true")
    parser.add_argument("--resident-bundle",type=Path,help="use relocated scalar/paged tables; currently requires --scalars-only")
    suite = parser.add_mutually_exclusive_group()
    suite.add_argument("--vectors-only", action="store_true")
    suite.add_argument("--scalars-only", action="store_true")
    suite.add_argument("--errors-only", action="store_true")
    args = parser.parse_args()
    if args.resident_bundle and not args.scalars_only: parser.error("--resident-bundle requires --scalars-only")
    args.output.mkdir(parents=True, exist_ok=False)
    binary = reference_binary(args.output)
    scalars = [] if args.vectors_only or args.errors_only else scalar_cases()
    vectors = [] if args.scalars_only else vector_cases()
    if args.errors_only: vectors = vectors[-7:]
    if args.first_only:
        scalars = [{"value": val, "exp": exp, "socr": 26} for val, exp in ((1, 0), (-1, 0), (2, -1), (-8206, -65),
                   (8192, -59), (8206, -58), (-1, 12), (1, 12), (8207, 0), (1, -32768), (1, 32767))] if scalars else []
        vectors = vectors[:1]
    if scalars: reference(args.output, scalars, "S", binary)
    if vectors: reference(args.output, vectors, "V", binary)
    if vectors and not args.first_only: vectors += overflow_cases()
    report = {"passed": False, "cases": [], "pcm_produced": False,
              "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(), "rq_source_sha256": RQ_SHA}
    if scalars: report["formula_crosscheck"] = formula_crosscheck(scalars)
    try:
        for start in range(0, len(scalars), 1024):
            report["cases"].append(check_scalar(args.qemu, args.output, f"scalar-{start:04d}", scalars[start:start+1024],resident_bundle=args.resident_bundle))
        for start in range(0, len(vectors), 4):
            report["cases"].append(check_vector(args.qemu, args.output, f"spectrum-{start:03d}", vectors[start:start+4]))
        if not args.first_only:
            if scalars: report["cases"].append(check_scalar(args.qemu, args.output, "scalar-icount5", scalars[-1024:], 5,resident_bundle=args.resident_bundle))
            if vectors: report["cases"].append(check_vector(args.qemu, args.output, "spectrum-icount5", vectors[-4:], 5))
        report["passed"] = all(c["passed"] and c["exit_code"] == 0 for c in report["cases"])
    except AssertionError as exc:
        detail = exc.args[0] if exc.args else "assertion failed"
        if isinstance(detail, dict):
            detail = {"name": detail.get("name"), "registers": detail.get("registers"),
                      "differences": [(i, x, y) for i, (x, y) in enumerate(zip(detail.get("actual_samples", []), detail.get("expected_samples", []))) if x != y][:16]}
        report["failure"] = str(detail)[:2200]
        print(report["failure"], flush=True)
    finally:
        (args.output/"report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
