#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native hybrid unit and two-granule overlap tests; not PCM/player tests."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import struct
import subprocess

from build_np560_mp3_huffman import ROOT
from build_np560_mp3_scalefactors import MAD_SHA
from build_np560_mp3_antialias import build as build_math
from build_np560_mp3_hybrid import build
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr, write_word
from test_np560_mac import run
from test_np560_mp3_requantize import signed_words,FIXTURE
from test_np560_mp3_stereo import words32


def reference_binary(output):
    # Independent fast libmad transform topology, using its pinned
    # constants but long-double operations, verifies phase, gain, window
    # shapes and the interleaved-to-window-major short layout conversion.
    raw=(ROOT/"doc/sources/libmad-20260907/layer3.c").read_bytes()
    assert hashlib.sha256(raw).hexdigest()==MAD_SHA
    short=(ROOT/"doc/sources/libmad-20260907/imdct_s.dat").read_bytes()
    assert hashlib.sha256(short).hexdigest()=="492893124349428a04a9ac363834f8050372367e91d6e523ba8532d701614a20"
    text=raw.decode().replace("\r\n","\n")
    pieces=[]
    for name in ("window_l","window_s"):
        start=text.index("mad_fixed_t const "+name+"[")
        pieces.append("static "+text[start:text.index("};",start)+2])
    pieces.append('static mad_fixed_t const imdct_s[6][6] = {\n#include "imdct_s.dat"\n};')
    for name in ("fastsdct","sdctII","dctIV","imdct36","III_imdct_l","III_imdct_s"):
        match=re.search(r"\bvoid "+name+r"\([^;]+?\)\s*(?:/\*.*?\*/\s*)?\{",text,re.S)
        assert match,name
        end=match.end();depth=1
        while depth:
            depth+=(text[end]=="{")-(text[end]=="}")
            end+=1
        body=text[match.start():end]
        if name=="fastsdct": body=body.replace("  enum {","  const mad_fixed_t").replace("  };","  ;")
        pieces.append("static "+body)
    (output/"imdct_s.dat").write_bytes(short)
    (output/"libmad_hybrid_float.inc").write_text("\n".join(pieces),encoding="utf-8")
    binary=output/"hybrid-reference"
    p=subprocess.run(["gcc","-O2","-std=c99","-Wall","-Wextra","-Werror","-I",str(output),
        str(ROOT/"scripts/test_np560_mp3_hybrid_reference.c"),"-lm","-o",str(binary)],capture_output=True,text=True)
    (output/"hybrid-reference-compiler.log").write_text(p.stdout+p.stderr,encoding="utf-8")
    if p.returncode: raise RuntimeError(p.stderr)
    return binary


def reference(output,cases,binary=None):
    binary=binary or reference_binary(output)
    p=subprocess.run([str(binary)],input="\n".join(c["mode"]+" "+" ".join(map(str,c["input"])) for c in cases)+"\n",
                     capture_output=True,text=True,check=True)
    rows=p.stdout.splitlines()
    assert len(rows)==len(cases)
    for c,row in zip(cases,rows):
        values=list(map(int,row.split()))
        c["status"],c["expected"]=values[0],values[1:]
        assert len(c["expected"])==(36 if c["mode"]=="T" else 1152)
    return p.stderr.strip()


def cases():
    rng=random.Random(56036)
    transforms=[]
    for block in range(4):
        for k in range(18):
            for value in (1<<28,-(1<<28)):
                x=[0]*18
                x[k]=value
                transforms.append({"mode":"T","input":[block]+x})
        for x in ([0]*18,[-2**31]*18,[2**31-1]*18,[-2**31 if k%2 else 2**31-1 for k in range(18)]):
            transforms.append({"mode":"T","input":[block]+x})
        for _ in range(12): transforms.append({"mode":"T","input":[block]+[rng.randrange(-2**31,2**31) for _ in range(18)]})
    for block in (4,65535): transforms.append({"mode":"T","input":[block]+list(range(18))})
    vectors=[]
    for rate in range(9):
        for block,mixed in ((0,0),(1,0),(2,0),(2,1),(3,0)):
            vectors.append({"mode":"H","input":[rate,block,mixed,0]+[rng.randrange(-2**31,2**31) for _ in range(576)]+[0]*576})
    for geometry in ((9,0,0),(0,4,0),(0,2,2),(65535,2,0)):
        vectors.append({"mode":"H","input":list(geometry)+[0]+list(range(576))+list(range(576))})
    x=[0]*576;x[0]=2**31-1
    old=[0]*576;old[0]=2**31-1
    vectors.append({"mode":"H","input":[0,0,0,0]+x+old})
    old=[0]*576;old[19]=-2**31 # odd sb/time: negation cannot fit
    vectors.append({"mode":"H","input":[0,2,0,0]+[0]*576+old})
    # Full previous tails must be emitted/cleared even with a zero spectrum.
    vectors.append({"mode":"H","input":[8,2,1,0]+[0]*576+[rng.randrange(-2**30,2**30) for _ in range(576)]})
    sequences=[]
    for first,second,mixed,rate in ((0,1,0,0),(1,2,0,0),(2,2,0,0),(2,3,0,0),(3,0,0,0),(2,2,1,8)):
        sequences.append([
            {"mode":"H","input":[rate,first,mixed,0]+[rng.randrange(-2**30,2**30) for _ in range(576)]+[0]*576},
            {"mode":"H","input":[rate,second,mixed,1]+[rng.randrange(-2**30,2**30) for _ in range(576)]+[0]*576}])
    for action in (1,2):
        sequences.append([
            {"mode":"H","input":[0,0,0,0]+[rng.randrange(-2**30,2**30) for _ in range(576)]+[0]*576},
            {"mode":"H","input":[0,0,0,action]+[0]*576+[0x12345678]*576}])
    return transforms,vectors,sequences


def payload(records):
    data=bytearray(FIXTURE-0x201000+len(records)*2)
    for core in (build_math(),build()):
        for key,addr in (("code","code_address"),("tables","table_address")):
            off=core[addr]-0x201000
            data[off:off+len(core[key])]=core[key]
    data[FIXTURE-0x201000:]=struct.pack(f"<{len(records)}H",*(n&65535 for n in records))
    return data


def check(qemu,output,cases,name,icount=None):
    core,records,expected=build(),[],[]
    mode=cases[0]["mode"]
    assert all(c["mode"]==mode for c in cases)
    guards=(0xfe,0x1ca0,0x1cfe,0x1d0e,0x5b00,0x5c00)
    for c in cases:
        fields=1 if mode=="T" else 4
        records+=c["input"][:fields]+words32(c["input"][fields:])
        expected += [0 if c["status"] else (36 if mode=="T" else 576),c["status"]]
        expected += words32(c["input"][fields:fields+(18 if mode=="T" else 576)])
        expected += words32(c["expected"])+[0xcafe]*len(guards)
    assert len(records)*2<0x8000 and 0x2400+len(expected)*2<0x5b00
    a=_DMCUAssembler(0x200000)
    a.emit(0x6800,26,0x68FF,0x6000,0x6810,0,0x6811,FIXTURE>>15,
           0x68F9,0x8000,0x68F6,0x2400,0x68F7,0,0x68F8,len(cases),0x68FB,0x4444)
    for addr in guards: write_word(a.words,addr,0xcafe)
    for off,val in (((2,0x0100),(4,0x1300)) if mode=="T" else ((6,0x0100),(8,0x1300),(10,0xa00),(12,0x1c00))):
        write_word(a.words,0x1d00+off,val)
    a.label("case")
    for addr in ((0x1d00,) if mode=="T" else (0x1d00,0x1d02,0x1d04)):
        a.emit(0x3809,0xa8f0,addr)
    if mode=="H": a.emit(0x38C9)
    a.emit(0x68F3,0x0100,0x68F4,36 if mode=="T" else 1152)
    a.label("load_input")
    a.emit(0x3809,0x1A30,0x5241)
    a.ajmp("load_input",2)
    if mode=="H":
        a.emit(0x76FC,1)
        a.ajmp("keep_history",1)
        a.emit(0x68F3,0xa00,0x68F4,1152)
        a.label("load_history")
        a.emit(0x3809,0x1A30,0x5241)
        a.ajmp("load_history",2)
        a.emit(0x76FC,2)
        a.ajmp("history_ready",2)
        a.emit(0x68F3,0xa00,0xBD20,core["entries"]["reset"]&65535)
        a.ajmp("history_ready")
        a.label("keep_history")
        a.emit(0x70F9,2304)
        a.label("history_ready")
    a.emit(0x68F3,0x1300,0x68F4,72 if mode=="T" else 1152,0x68F0,0xa55a)
    a.label("poison_output")
    a.emit(0x1A30,0x5241)
    a.ajmp("poison_output",2)
    a.emit(0x68F3,0x1d00,0xBD20,core["entries"]["transform" if mode=="T" else "hybrid"]&65535,0x1A60,0x1A62)
    for number,(addr,count) in enumerate(((0x100,36),(0x1300,72)) if mode=="T" else ((0x100,1152),(0x1300,1152),(0xa00,1152))):
        a.emit(0x68F3,addr,0x68F4,count)
        a.label(f"dump_{number}")
        a.emit(0x3803,0x1A60,0x5241)
        a.ajmp(f"dump_{number}",2)
    for addr in guards: a.emit(0x88F0,addr,0x1A60)
    a.emit(0x5071,0x5281)
    a.ajmp("case",2)
    read_sfr(a.words,0,12)
    read_sfr(a.words,0x11,5)
    (output/f"{name}.vectors.json").write_text(json.dumps(cases)+"\n",encoding="utf-8")
    return run(qemu,output,name,a.finish(),
        {5:FIXTURE>>15,6:0x2400+len(expected)*2,7:len(cases),8:0,9:0x8000+len(records)*2,11:0x4444,12:26,15:0x6000},
        tail=(0x1000,payload(records)),expected_data=signed_words(expected),icount=icount,timeout=180,poll_interval=.25,
        metadata={"mode":mode,"vectors":len(cases),"output_fracbits":23,"pcm_produced":False,
                  "code_sha256":hashlib.sha256(core["code"]).hexdigest(),
                  "native_history_reuses":sum(c["mode"]=="H" and c["input"][3]==1 for c in cases)})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--first-only",action="store_true")
    parser.add_argument("--reference-only",action="store_true",help="Only independent mathematical/libmad crosschecks, no QEMU execution")
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    transforms,vectors,sequences=cases()
    if args.first_only:
        transforms=transforms[::13]+transforms[-2:]
        vectors=[vectors[i] for i in (0,2,43)]+vectors[-3:]
        sequences=sequences[-2:]
    binary=reference_binary(args.output)
    errors=[reference(args.output,transforms+vectors,binary)]
    errors += [reference(args.output,seq,binary) for seq in sequences]
    report={"passed":False,"cases":[],"pcm_produced":False,"output_fracbits":23,
        "transforms":len(transforms),"vectors":len(vectors),"sequences":len(sequences),"formula_checks":errors,
        "qemu_sha256":hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    if args.reference_only:
        report.update(passed=True,offline_only=True)
        (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(report,indent=2))
        return 0
    try:
        for mode,items,batch in (("T",transforms,48),("H",vectors,2)):
            for i in range(0,len(items),batch): report["cases"].append(check(args.qemu,args.output,items[i:i+batch],f"{mode}-{i:03d}"))
        for i,seq in enumerate(sequences): report["cases"].append(check(args.qemu,args.output,seq,f"history-{i}"))
        if not args.first_only:
            report["cases"].append(check(args.qemu,args.output,transforms[-18:],"T-icount5",5))
            report["cases"].append(check(args.qemu,args.output,sequences[-2],"history-icount5",5))
        report["passed"]=all(c["passed"] and c["exit_code"]==0 for c in report["cases"])
    except AssertionError as exc:
        detail=exc.args[0] if exc.args else "assertion failed"
        if isinstance(detail,dict):
            detail={"name":detail.get("name"),"registers":detail.get("registers"),
                "differences":[(i,x,y) for i,(x,y) in enumerate(zip(detail.get("actual_samples",[]),detail.get("expected_samples",[]))) if x!=y][:18]}
        report["failure"]=str(detail)[:2500]
        print(report["failure"],flush=True)
    finally:
        (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
