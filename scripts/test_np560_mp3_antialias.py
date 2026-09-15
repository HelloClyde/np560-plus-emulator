#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native antialias unit tests versus offline widened libmad and real formulas."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import subprocess

from build_np560_mp3_huffman import ROOT
from build_np560_mp3_scalefactors import MAD_SHA
from build_np560_mp3_antialias import build
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr, write_word
from test_np560_mac import run
from test_np560_mp3_requantize import signed_words, FIXTURE
from test_np560_mp3_stereo import words32


def reference_binary(output):
    raw = (ROOT/"doc/sources/libmad-20260907/layer3.c").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MAD_SHA
    text = raw.decode().replace("\r\n", "\n")
    pieces = []
    for name in ("cs", "ca"):
        start = text.index("mad_fixed_t const "+name+"[")
        pieces.append("static "+text[start:text.index("};", start)+2])
    start = text.index("void III_aliasreduce(")
    end = text.index("# if defined(ASO_IMDCT)", start)
    pieces.append("static "+text[start:end])
    (output/"libmad_antialias.inc").write_text("\n".join(pieces), encoding="utf-8")
    binary = output/"antialias-reference"
    result = subprocess.run(["gcc", "-O2", "-std=c99", "-Wall", "-Wextra", "-Werror", "-I", str(output),
        str(ROOT/"scripts/test_np560_mp3_antialias_reference.c"), "-o", str(binary)], capture_output=True, text=True)
    (output/"antialias-reference-compiler.log").write_text(result.stdout+result.stderr, encoding="utf-8")
    if result.returncode: raise RuntimeError(result.stderr)
    return binary


def reference(output, cases, binary=None):
    binary = binary or reference_binary(output)
    rows = [c["mode"]+" "+" ".join(map(str,c["input"])) for c in cases]
    result = subprocess.run([str(binary)], input="\n".join(rows)+"\n", text=True, capture_output=True, check=True)
    rows = result.stdout.splitlines()
    assert len(rows) == len(cases)
    for c, row in zip(cases,rows):
        values = list(map(int,row.split()))
        c["status"],c["expected"] = values[0],values[1:]
        assert len(c["expected"]) == (2 if c["mode"] == "P" else 576)


def cases():
    rng = random.Random(560248)
    edges = [-2**31,-2**30,-65537,-65536,-65535,-1,0,1,65535,65536,65537,2**30,2**31-1]
    pairs = [{"mode":"P","input":[i,a,b]} for i in range(8) for a in edges for b in edges]
    pairs += [{"mode":"P","input":[i]+[rng.randrange(-2**31,2**31) for _ in range(2)]} for i in range(8) for _ in range(16)]
    pairs += [{"mode":"P","input":[i,2**31-1,-2**31]} for i in (8,65535)]
    vectors = []
    for rate in range(9):
        for block,mixed in ((0,0),(1,0),(2,0),(2,1),(3,0)):
            samples = [rng.randrange(-2**29,2**29) for _ in range(576)]
            vectors.append({"mode":"V","input":[rate,block,mixed]+samples})
    # Basis impulses at each butterfly position, touching first and last
    # long boundaries and the extra two 8 kHz mixed boundaries.
    for rate,block,mixed in ((0,0,0),(0,2,1),(8,2,1)):
        for side in (0,1):
            for tap in range(8):
                x = [0]*576
                for edge in (18,36,54,558): x[edge+tap if side else edge-1-tap] = (1<<28)*(-1 if tap%2 else 1)
                vectors.append({"mode":"V","input":[rate,block,mixed]+x})
    for geometry in ((9,0,0),(0,4,0),(0,2,2),(65535,2,0)):
        vectors.append({"mode":"V","input":list(geometry)+list(range(576))})
    for edge in (18,36,558):
        x = [0]*576
        x[edge-1]=x[edge]=2**31-1
        vectors.append({"mode":"V","input":[0,0,0]+x})
    # Pure short must neither round nor flag overflow for full-width data.
    vectors.append({"mode":"V","input":[8,2,0]+[edges[i%len(edges)] for i in range(576)]})
    return pairs,vectors


def payload(records):
    core = build()
    data = bytearray(FIXTURE-0x201000+len(records)*2)
    for key,addr in (("code","code_address"),("tables","table_address")):
        off = core[addr]-0x201000
        data[off:off+len(core[key])] = core[key]
    data[FIXTURE-0x201000:] = struct.pack(f"<{len(records)}H",*(n&65535 for n in records))
    return data


def check_pairs(qemu,output,cases,name,icount=None):
    core,records,expected = build(),[],[]
    for i,c in enumerate(cases):
        socr = 26 if i%2 else 2
        records += [c["input"][0]]+words32(c["input"][1:])+[socr]
        expected += words32(c["expected"])+[c["status"],socr]
    assert len(records)*2 < 0x8000 and 0x2400+len(expected)*2 < 0x5e00
    a = _DMCUAssembler(0x200000)
    a.emit(0x6800,2,0x68FF,0x6000,0x6810,0,0x6811,FIXTURE>>15,
           0x68F9,0x8000,0x68FC,len(cases),0x68F8,0x2400,0x68FB,0x4444,0x68FD,0x5555,0x68FE,0x6666)
    a.label("pair")
    a.emit(0x3829,0x3809,0x3819,0x3839,0x3849,0x3859,0x58F5,0x1F80,
           0xBD20,core["entries"]["pair"]&65535,0x0858,
           0x1A50,0x1A51,0x1A53,0x1A54,0x1A52)
    read_sfr(a.words,0,6)
    a.emit(0x1A56,0x0885,0x52C1)
    a.ajmp("pair",2)
    read_sfr(a.words,0x11,7)
    return run(qemu,output,name,a.finish(),
        {7:FIXTURE>>15,8:0x2400+len(expected)*2,9:0x8000+len(records)*2,11:0x4444,12:0,13:0x5555,14:0x6666,15:0x6000},
        tail=(0x1000,payload(records)),expected_data=signed_words(expected),icount=icount,timeout=90,poll_interval=.25,
        metadata={"pairs":len(cases),"pcm_produced":False,"code_sha256":hashlib.sha256(core["code"]).hexdigest()})


def check_vectors(qemu,output,cases,name,icount=None):
    core,records,expected = build(),[],[]
    guards = (0xfe,0xa00,0x204e,0x2058,0x4ffe,0x5900)
    for c in cases:
        records += c["input"][:3]+words32(c["input"][3:])
        expected += [0 if c["status"] else 576,c["status"]]+words32(c["expected"])+[0xcafe]*len(guards)
    assert len(records)*2 < 0x8000 and 0x2400+len(expected)*2 < 0x4ffe
    a = _DMCUAssembler(0x200000)
    a.emit(0x6800,26,0x68FF,0x6000,0x6810,0,0x6811,FIXTURE>>15,
           0x68F9,0x8000,0x68F6,0x2400,0x68F7,0,0x68F8,len(cases),0x68FB,0x4444)
    for addr in guards: write_word(a.words,addr,0xcafe)
    write_word(a.words,0x2056,0x0100)
    a.label("vector")
    for addr in (0x2050,0x2052,0x2054): a.emit(0x3809,0xa8f0,addr)
    a.emit(0x68F3,0x0100,0x68F4,1152)
    a.label("input")
    a.emit(0x3809,0x1A30,0x5241)
    a.ajmp("input",2)
    a.emit(0x68F3,0x2050,0xBD20,core["entries"]["spectrum"]&65535,0x1A60,0x1A62,
           0x68F3,0x0100,0x68F4,1152)
    a.label("dump")
    a.emit(0x3803,0x1A60,0x5241)
    a.ajmp("dump",2)
    for addr in guards: a.emit(0x88F0,addr,0x1A60)
    a.emit(0x5071,0x5281)
    a.ajmp("vector",2)
    read_sfr(a.words,0,12)
    read_sfr(a.words,0x11,5)
    (output/f"{name}.vectors.json").write_text(json.dumps(cases)+"\n",encoding="utf-8")
    return run(qemu,output,name,a.finish(),
        {5:FIXTURE>>15,6:0x2400+len(expected)*2,7:len(cases),8:0,9:0x8000+len(records)*2,11:0x4444,12:26,15:0x6000},
        tail=(0x1000,payload(records)),expected_data=signed_words(expected),icount=icount,timeout=90,poll_interval=.25,
        metadata={"vectors":len(cases),"pcm_produced":False,"code_sha256":hashlib.sha256(core["code"]).hexdigest()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--first-only",action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    pairs,vectors = cases()
    if args.first_only:
        pairs = pairs[::17]+pairs[-2:]
        vectors = [vectors[i] for i in (0,2,3,43)]+vectors[-4:]
    reference(args.output,pairs+vectors)
    constants = [-.6,-.535,-.33,-.185,-.095,-.041,-.0142,-.0037]
    max_error = 0.
    for c in pairs:
        if c["status"]: continue
        i,a,b = c["input"]
        cs = 1/math.sqrt(1+constants[i]**2)
        ca = constants[i]*cs
        delta = max(abs(c["expected"][0]-(a*cs-b*ca)),abs(c["expected"][1]-(b*cs+a*ca)))
        assert delta < 9  # two <=0.5-LSB constants times full-range input, plus floor
        max_error = max(max_error,delta)
    report = {"passed":False,"cases":[],"pcm_produced":False,"pairs":len(pairs),"vectors":len(vectors),
        "qemu_sha256":hashlib.sha256(args.qemu.read_bytes()).hexdigest(),"formula_max_q28_lsb_error":max_error}
    try:
        for i in range(0,len(pairs),256):
            report["cases"].append(check_pairs(args.qemu,args.output,pairs[i:i+256],f"pairs-{i:04d}"))
        for i in range(0,len(vectors),4):
            report["cases"].append(check_vectors(args.qemu,args.output,vectors[i:i+4],f"vectors-{i:03d}"))
        if not args.first_only:
            report["cases"].append(check_pairs(args.qemu,args.output,pairs[-130:],"pairs-icount5",5))
            report["cases"].append(check_vectors(args.qemu,args.output,[vectors[0],vectors[2],vectors[43],vectors[-2]],"vectors-icount5",5))
        report["passed"] = all(c["passed"] and c["exit_code"]==0 for c in report["cases"])
    except AssertionError as exc:
        detail = exc.args[0] if exc.args else "assertion failed"
        if isinstance(detail,dict):
            detail = {"name":detail.get("name"),"registers":detail.get("registers"),
                "differences":[(i,x,y) for i,(x,y) in enumerate(zip(detail.get("actual_samples",[]),detail.get("expected_samples",[]))) if x!=y][:16]}
        report["failure"] = str(detail)[:2500]
        print(report["failure"],flush=True)
    finally:
        (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
