#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native PCM synthesis versus integer, mathematical and libmad references."""
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
from build_np560_mp3_antialias import build as build_math
from build_np560_mp3_synthesis import build,window,D_SHA
from build_np560_mp3_dct32 import build as build_dct32, source_function
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr,write_word
from test_np560_mac import run
from test_np560_mp3_requantize import signed_words,FIXTURE
from test_np560_mp3_stereo import words32

SYNTH_SHA="c7a49ee84744f3d6a7ef2fa5be69bfc3d65056b9748fc58978843df0deafd5f5"
DSP_SHA="b4c590d2bc880017cdda8c857f4340274449f4749c992f1d1cef785f9196d7a8"


def reference_binary(output,fast=False):
    raw=(ROOT/"doc/sources/libmad-20260907/synth.c").read_bytes()
    assert hashlib.sha256(raw).hexdigest()==SYNTH_SHA
    text=raw.decode().replace("\r\n","\n")
    pieces=['static mad_fixed_t const D[17][32] = {\n#include "D.dat"\n};']
    for name in ("dct32","synth_full"):
        match=re.search(r"\bvoid "+name+r"\([^;]+?\)\s*\{",text,re.S)
        assert match,name
        end=match.end();depth=1
        while depth:
            depth+=(text[end]=="{")-(text[end]=="}");end+=1
        pieces.append("static "+text[match.start():end])
    (output/"libmad_synthesis_float.inc").write_text("\n".join(pieces),encoding="utf-8")
    raw=(ROOT/"doc/sources/libmad-20260907/D.dat").read_bytes()
    assert hashlib.sha256(raw).hexdigest()==D_SHA
    (output/"D.dat").write_bytes(raw)
    raw=(ROOT/"doc/sources/ffmpeg-mpeg-tables-20260907/mpegaudiodsp_data.c").read_bytes()
    assert hashlib.sha256(raw).hexdigest()==DSP_SHA
    text=raw.decode();start=text.index("const int32_t ff_mpa_enwindow[")
    table=text[start:text.index("};",start)+2]
    (output/"ffmpeg_synthesis_window.inc").write_text(table,encoding="utf-8")
    from scan_np560_mpeg_tables import array
    half=array(text,"ff_mpa_enwindow");full=[0]*512
    for i,v in enumerate(half):
        full[i]=v
        if i: full[512-i]=-v if i&63 else v
    assert full==window() # independently reconstruct all 512 signed taps
    binary=output/"synthesis-reference"
    if fast:
        (output/"libmad_dct32_wide.inc").write_text("static "+source_function().replace(
            "void dct32(","void dct32_wide(").replace("mad_fixed_t","int64_t")+"\n")
    p=subprocess.run(["gcc","-O2","-std=c99","-Wall","-Wextra","-Werror",*(["-DNP560_FAST_DCT"] if fast else []),"-I",str(output),
        str(ROOT/"scripts/test_np560_mp3_synthesis_reference.c"),"-lm","-o",str(binary)],capture_output=True,text=True)
    (output/"synthesis-reference-compiler.log").write_text(p.stdout+p.stderr,encoding="utf-8")
    if p.returncode: raise RuntimeError(p.stderr)
    return binary


def reference(output,cases,binary=None):
    binary=binary or reference_binary(output)
    p=subprocess.run([str(binary)],input="\n".join(c["mode"]+" "+" ".join(map(str,c["input"])) for c in cases)+"\n",
                     capture_output=True,text=True,check=True)
    rows=p.stdout.splitlines();assert len(rows)==len(cases)
    for c,row in zip(cases,rows):
        values=list(map(int,row.split()));ns=576 if c["mode"]=="G" else 32
        c.update(status=values[0],head=values[1],pcm=values[2:2+ns],state=values[2+ns:])
        assert len(c["state"])==1024
    return p.stderr.strip()


def cases():
    rng=random.Random(560512)
    def case(mode,x,bank=0,head=0,action=0,old=None):
        return {"mode":mode,"input":[bank,0x8100,head,action]+x+(old or [0]*1024)}
    slots=[]
    for k in range(32):
        x=[0]*32;x[k]=1<<18
        slots.append(case("S",x))
    for x in ([0]*32,[-2**31]*32,[2**31-1]*32,[-2**31 if k%2 else 2**31-1 for k in range(32)]): slots.append(case("S",x))
    for _ in range(8): slots.append(case("S",[rng.randrange(-2**20,2**20) for _ in range(32)]))
    slots.append(case("S",[0]*32,old=[rng.randrange(-2**30,2**30) for _ in range(1024)]))
    slots.append(case("S",[0]*32,head=1))
    slots.append(case("S",[0]*32,head=4096))
    # Far DS1 state rather than only bank-zero addresses, and real keep.
    sequences=[[case("S",[rng.randrange(-2**18,2**18) for _ in range(32)],bank=0x30),
                case("S",[0]*32,bank=0x30,action=1)]]
    granules=[case("G",[rng.randrange(-2**14,2**14) for _ in range(576)]),
              case("G",[rng.randrange(-2**31,2**31) for _ in range(576)]),
              case("G",[0]*576,old=[rng.randrange(-2**27,2**27) for _ in range(1024)]),
              case("G",[0]*576,action=2,old=[0x12345678]*1024),
              case("G",[rng.randrange(-2**16,2**16) for _ in range(576)],bank=0x30)]
    return slots,granules,sequences


def payload(records,fast=False):
    data=bytearray(FIXTURE-0x201000+len(records)*2)
    dct=build_dct32() if fast else None
    for core in (build_math(),build(fast_core=dct),*([dct] if dct else [])):
        for key,addr in (("code","code_address"),("tables","table_address")):
            if key not in core: continue
            off=core[addr]-0x201000;data[off:off+len(core[key])]=core[key]
    data[FIXTURE-0x201000:]=struct.pack(f"<{len(records)}H",*(n&65535 for n in records))
    return data


def check(qemu,output,cases,name,icount=None,fast=False):
    core,records,expected=build(fast_core=build_dct32() if fast else None),[],[]
    mode=cases[0]["mode"];assert all(c["mode"]==mode for c in cases)
    ns=576 if mode=="G" else 32
    guards=(0xfe,0x1102,0x2080,0x21a0,0x21ca,0x5b00)
    work=0x7000 if fast else 0x2180
    if fast: guards+=(work-2,work+core["work_bytes"])
    for c in cases:
        records+=c["input"][:4]+words32(c["input"][4:])
        expected+=[0 if c["status"] else ns,c["status"],c["head"]]+[v&65535 for v in c["pcm"]]
        expected+=words32(c["state"])+words32(c["input"][4:4+ns])+[0xcafe]*len(guards)
    assert len(records)*2<0x8000 and 0x2400+len(expected)*2<0x5b00
    a=_DMCUAssembler(0x200000)
    a.emit(0x6800,26,0x68FF,0x6000,0x6810,0,0x6811,FIXTURE>>15,
           0x68F9,0x8000,0x68F6,0x2400,0x68F7,0,0x68F8,len(cases),0x68FB,0x4444)
    for addr in guards: write_word(a.words,addr,0xcafe)
    for off,val in ((4,0x1200),(6,0x1c00),(8,work)): write_word(a.words,0x21c0+off,val)
    a.label("case")
    for addr in (0x21c0,0x21c2,0x21e0): a.emit(0x3809,0xa8f0,addr)
    a.emit(0x38C9,0x68F3,0x1200,0x68F4,ns*2)
    a.label("load_input")
    a.emit(0x3809,0x1A30,0x5241);a.ajmp("load_input",2)
    a.emit(0x76FC,1);a.ajmp("keep_state",1)
    # Read fixture with DS1; write far state using DS0 temporarily.
    a.emit(0x88F0,0x21c0,0x58F0,0x1F90,0x68F3,0x0100,0x68F4,2048)
    # State ptr is 8100 in all native ownership tests; head is first.
    a.emit(0x6810,0,0x88F0,0x21e0,0x88F1,0x21c0,0x58F1,0x1F90,0x1A30)
    a.label("load_state")
    a.emit(0x3809,0x1A30,0x5241);a.ajmp("load_state",2)
    a.emit(0x6810,0,0x76FC,2);a.ajmp("state_ready",2)
    a.emit(0x68F3,0x21c0,0xBD20,core["entries"]["reset"]&65535);a.ajmp("state_ready")
    a.label("keep_state")
    a.emit(0x70F9,4096)
    a.label("state_ready")
    a.emit(0x68F3,0x1c00,0x68F4,ns,0x68F0,0xa55a)
    a.label("poison_pcm")
    a.emit(0x1A30,0x5241);a.ajmp("poison_pcm",2)
    a.emit(0x68F3,0x21c0,0xBD20,core["entries"]["granule" if mode=="G" else "slot"]&65535,0x1A60,0x1A62)
    a.emit(0x88F0,0x21c0,0x58F0,0x1F91,0x68F3,0x8100,0x3803,0x1A60)
    # Output near PCM first, then state using the far bank, then input.
    for number,(addr,count) in enumerate(((0x1c00,ns),(0x8102,2048),(0x1200,ns*2))):
        a.emit(0x68F3,addr,0x68F4,count)
        a.label(f"dump_{number}")
        a.emit(0x3803,0x1A60,0x5241);a.ajmp(f"dump_{number}",2)
    a.emit(0x6811,FIXTURE>>15)
    for addr in guards: a.emit(0x88F0,addr,0x1A60)
    a.emit(0x5071,0x5281);a.ajmp("case",2)
    read_sfr(a.words,0,12);read_sfr(a.words,0x11,5)
    (output/f"{name}.vectors.json").write_text(json.dumps(cases)+"\n",encoding="utf-8")
    return run(qemu,output,name,a.finish(),{5:FIXTURE>>15,6:0x2400+len(expected)*2,7:len(cases),8:0,
        9:0x8000+len(records)*2,11:0x4444,12:26,15:0x6000},tail=(0x1000,payload(records,fast)),
        expected_data=signed_words(expected),icount=icount,timeout=180,poll_interval=.25,
        metadata={"mode":mode,"cases":len(cases),"pcm_generated":True,"factory_rom_patch":False,
                  "code_sha256":hashlib.sha256(core["code"]).hexdigest(),"fast_dct32":fast})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--first-only",action="store_true")
    p.add_argument("--fast-dct32",action="store_true");args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    slots,granules,sequences=cases()
    if args.first_only: slots=slots[::12]+slots[-3:];granules=granules[::3]
    binary=reference_binary(args.output,args.fast_dct32)
    errors=[reference(args.output,slots+granules,binary)]+[reference(args.output,s,binary) for s in sequences]
    report={"passed":False,"cases":[],"slots":len(slots),"granules":len(granules),"sequences":len(sequences),
            "reference_checks":errors,"qemu_sha256":hashlib.sha256(args.qemu.read_bytes()).hexdigest(),"fast_dct32":args.fast_dct32}
    try:
        for i in range(0,len(slots),2): report["cases"].append(check(args.qemu,args.output,slots[i:i+2],f"slots-{i:03d}",fast=args.fast_dct32))
        for i,g in enumerate(granules): report["cases"].append(check(args.qemu,args.output,[g],f"granule-{i}",fast=args.fast_dct32))
        for i,s in enumerate(sequences): report["cases"].append(check(args.qemu,args.output,s,f"history-{i}",fast=args.fast_dct32))
        if not args.first_only: report["cases"].append(check(args.qemu,args.output,[granules[0]],"granule-icount5",5,fast=args.fast_dct32))
        report["passed"]=all(c["passed"] and c["exit_code"]==0 for c in report["cases"])
    except AssertionError as exc:
        detail=exc.args[0] if exc.args else "assertion failed"
        if isinstance(detail,dict): detail={"name":detail.get("name"),"registers":detail.get("registers"),
            "differences":[(i,x,y) for i,(x,y) in enumerate(zip(detail.get("actual_samples",[]),detail.get("expected_samples",[]))) if x!=y][:18]}
        report["failure"]=str(detail)[:2500];print(report["failure"],flush=True)
    finally: (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__=="__main__": raise SystemExit(main())
