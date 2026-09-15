#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fast long IMDCT: native vs independent pinned-C topology and mathematics."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import subprocess

import build_np560_mp3_imdct36 as corelib
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr, write_word
from test_np560_mac import run
from test_np560_mp3_requantize import signed_words

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=0x238000


def vectors():
    rng=random.Random(560136);result=[]
    for block in (0,1,3):
        for k in range(18):
            for amplitude in (1<<28,-(1<<28)):
                x=[0]*18;x[k]=amplitude;result.append((block,x))
        for x in ([0]*18,[1]*18,[-1]*18,[-(1<<31)]*18,[(1<<31)-1]*18,
                  [-(1<<31) if i%2 else (1<<31)-1 for i in range(18)]):result.append((block,x))
        for _ in range(20):result.append((block,[rng.randrange(-(1<<31),1<<31) for _ in range(18)]))
    return result


def reference(output,cases):
    text=corelib.source_text();pieces=[]
    for name in ("window_l","window_s"):
        start=text.index("mad_fixed_t const "+name+"[")
        pieces.append("static "+text[start:text.index("};",start)+2])
    pieces += ["static "+corelib.function(name) for name in
               ("fastsdct","sdctII","dctIV","imdct36","III_imdct_l")]
    (output/"libmad_imdct36_wide.inc").write_text("\n".join(pieces))
    binary=output/"imdct36-reference"
    compiled=subprocess.run(["gcc","-O2","-std=c99","-Wall","-Wextra","-Werror","-I",str(output),
                             str(ROOT/"scripts/test_np560_mp3_imdct36_reference.c"),"-o",str(binary)],capture_output=True,text=True)
    (output/"reference-compiler.log").write_text(compiled.stdout+compiled.stderr)
    assert compiled.returncode==0,compiled.stderr
    ref=subprocess.run([str(binary)],input="\n".join(" ".join(map(str,[b]+x)) for b,x in cases)+"\n",
                       capture_output=True,text=True,check=True)
    values=[list(map(int,line.split())) for line in ref.stdout.splitlines()]
    assert len(values)==len(cases)
    maximum=0.
    for (block,x),actual in zip(cases,values):
        assert actual==corelib.evaluate(block,x), (block,x,actual,corelib.evaluate(block,x))
        for n,y in enumerate(actual):
            win=math.sin(math.pi/36*(n+.5))
            if block==1 and n>=18:win=1. if n<24 else math.sin(math.pi/12*(n-18+.5)) if n<30 else 0.
            if block==3 and n<18:win=0. if n<6 else math.sin(math.pi/12*(n-6+.5)) if n<12 else 1.
            ideal=sum(v*math.cos(math.pi/72*(2*n+19)*(2*k+1)) for k,v in enumerate(x))*win/32
            maximum=max(maximum,abs(y-ideal))
    assert maximum<32,maximum
    return values,maximum


def check(qemu,output,cases,expected,name,icount=None):
    core=corelib.build();records=b"".join(struct.pack("<H18i",b,*x) for b,x in cases)
    expected_words=[];guards=(0xfe,0x290,0x808,0xffe,0x1000+core["work_bytes"])
    for (block,x),z in zip(cases,expected):
        words32=lambda values:struct.unpack(f"<{len(values)*2}H",struct.pack(f"<{len(values)}i",*values))
        expected_words += [36 if block in (0,1,3) else 0,0 if block in (0,1,3) else 2]
        expected_words += list(words32(x))+list(words32(z))+[0xcafe]*len(guards)
    a=_DMCUAssembler(0x200000)
    a.emit(0x6800,26,0x68ff,0x7e00,0x6810,0,0x6811,FIXTURE>>15,
           0x68f9,0x8000,0x68f6,0x2400,0x68f8,len(cases),0x68fb,0x4444)
    a.label("case")
    for addr,val in ((0x802,0x100),(0x804,0x200),(0x806,0x1000),*((x,0xcafe) for x in guards)):
        write_word(a.words,addr,val)
    a.emit(0x3809,0xa8f0,0x800,0x68f3,0x100,0x68f4,36)
    a.label("input");a.emit(0x3809,0x1a30,0x5241);a.ajmp("input",2)
    a.emit(0x68f3,0x200,0x68f4,72,0x68f0,0xa55a)
    a.label("poison");a.emit(0x1a30,0x5241);a.ajmp("poison",2)
    a.emit(0x68f3,0x800,0xbd00|core["code_address"]>>16,core["entries"]["transform"]&65535,0x1a60,0x1a62)
    for i,(addr,count) in enumerate(((0x100,36),(0x200,72))):
        a.emit(0x68f3,addr,0x68f4,count);a.label(f"copy{i}")
        a.emit(0x3803,0x1a60,0x5241);a.ajmp(f"copy{i}",2)
    for addr in guards:a.emit(0x88f0,addr,0x1a60)
    a.emit(0x5281);a.ajmp("case",2)
    read_sfr(a.words,0,12);read_sfr(a.words,0x11,5)
    tail=bytearray(FIXTURE-0x201000+len(records))
    for key,where in (("code","code_address"),("tables","table_address")):
        off=core[where]-0x201000;tail[off:off+len(core[key])]=core[key]
    tail[FIXTURE-0x201000:]=records
    (output/f"{name}.vectors.json").write_text(json.dumps(cases)+"\n")
    return run(qemu,output,name,a.finish(),
        {5:FIXTURE>>15,6:0x2400+len(expected_words)*2,8:0,9:0x8000+len(records),11:0x4444,12:26,15:0x7e00},
        tail=(0x1000,tail),expected_data=signed_words(expected_words),icount=icount,timeout=180,poll_interval=.25,
        metadata={"vectors":len(cases),"work_bytes":core["work_bytes"],"pcm_produced":False,
                  "code_sha256":hashlib.sha256(core["code"]).hexdigest()},
        expected_code=[(core["code_address"],core["code"])])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--first-only",action="store_true");args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    items=vectors()
    if args.first_only:items=items[::23]
    expected,error=reference(args.output,items)
    items += [(b,list(range(18))) for b in (2,4,65535)]
    expected += [[-1520786086]*36 for _ in range(3)]  # untouched A55AA55A
    report={"passed":False,"qemu_sha256":hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
            "range_proof":corelib.range_proof(),"maximum_math_q23_difference":error,"cases":[]}
    try:
        for i in range(0,len(items),32):
            report["cases"].append(check(args.qemu,args.output,items[i:i+32],expected[i:i+32],f"long-{i}"))
        report["cases"].append(check(args.qemu,args.output,items[-10:],expected[-10:],"long-icount",5))
        report["passed"]=True
    except AssertionError as exc:
        detail=exc.args[0] if exc.args else "assertion"
        if isinstance(detail,dict) and "actual_samples" in detail:detail={"name":detail.get("name"),"registers":detail.get("registers"),
            "differences":[(i,x,y) for i,(x,y) in enumerate(zip(detail.get("actual_samples",[]),detail.get("expected_samples",[]))) if x!=y][:18]}
        report["failure"]=str(detail)[:2500];print(report["failure"],flush=True)
    finally:(args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    return 0 if report["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
