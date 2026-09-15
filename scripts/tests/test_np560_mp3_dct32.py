#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Full-width DMCU fast DCT versus independently executed pinned libmad C."""
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

from build_np560_mp3_dct32 import build,source_function,range_proof,WORK_BYTES
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr,write_word
from test_np560_mac import run
from test_np560_mp3_requantize import FIXTURE,signed_words
from test_np560_mp3_stereo import words32


def reference_binary(output):
    (output/"libmad_dct32_wide.inc").write_text("static "+source_function()+"\n")
    binary=output/"dct32-reference"
    process=subprocess.run(["gcc","-O2","-std=c99","-Wall","-Wextra","-Werror",
        "-I",str(output),str((Path(__file__).resolve().parent.parent / 'test_np560_mp3_dct32_reference.c')),
        "-lm","-o",str(binary)],capture_output=True,text=True)
    (output/"reference-compiler.log").write_text(process.stdout+process.stderr)
    assert process.returncode==0,process.stderr
    return binary


def check(qemu,output,vectors,expected,name,bank=0,icount=None):
    core=build();records=words32([v for x in vectors for v in x]);want=[]
    # Input 1200, scratch 1600..1A26, descriptor 1B00, far output8100.
    # Result accumulation starts at2400; preserve the input and guard both
    # scratch and output. No test values are written from the host at runtime.
    a=_DMCUAssembler(0x200000)
    a.emit(0x6800,26,0x68ff,0x6000,0x6810,0,0x6811,FIXTURE>>15,
           0x68f9,0x8000,0x68f6,0x2400,0x68f7,len(vectors),0x68fb,0x4444)
    for off,v in enumerate((0x1200,bank,0x8100,0x1600)): write_word(a.words,0x1b00+off*2,v)
    for address in (0x15fe,0x1600+WORK_BYTES): write_word(a.words,address,0xcafe)
    a.emit(0x1f11,0x6811,bank)
    for address in (0x80fe,0x8200): write_word(a.words,address,0xcafe,banked=True)
    a.emit(0x1f91)
    a.label("next")
    a.emit(0x68f3,0x1200,0x68f4,64)
    a.label("copy_input");a.emit(0x3809,0x1a30,0x5241);a.ajmp("copy_input",2)
    a.emit(0x68f3,0x1b00,0xbd00|core["code_address"]>>16,core["entries"]["dct32"]&65535,
           0x1a60,0x1a62,0x1f11,0x6811,bank,0x68f3,0x8100,0x68f4,128)
    a.label("copy_output");a.emit(0x3803,0x1a60,0x5241);a.ajmp("copy_output",2)
    for address in (0x80fe,0x8200): a.emit(0x88f0,address,0x1a60)
    a.emit(0x1f91,0x68f3,0x1200,0x68f4,64)
    a.label("keep_input");a.emit(0x3803,0x1a60,0x5241);a.ajmp("keep_input",2)
    for address in (0x15fe,0x1600+WORK_BYTES): a.emit(0x88f0,address,0x1a60)
    a.emit(0x5271);a.ajmp("next",2)
    read_sfr(a.words,0,4);read_sfr(a.words,0x11,5)
    for x,y in zip(vectors,expected): want += [64,0]+words32(y)+[0xcafe]*2+words32(x)+[0xcafe]*2
    assert 0x2400+len(want)*2<0x5b00
    payload=bytearray(FIXTURE-0x201000+len(records)*2)
    start=core["code_address"]-0x201000;payload[start:start+len(core["code"])]=core["code"]
    payload[FIXTURE-0x201000:]=struct.pack(f"<{len(records)}H",*records)
    return run(qemu,output,name,a.finish(),{4:26,5:FIXTURE>>15,6:0x2400+len(want)*2,
        7:0,9:0x8000+len(records)*2,11:0x4444,15:0x6000},tail=(0x1000,payload),
        expected_data=signed_words(want),timeout=90,poll_interval=.1,icount=icount,
        expected_code=[(core["code_address"],core["code"])],
        metadata={"vectors":len(vectors),"output_bank":bank,"native_code_bytes":len(core["code"]),
                  "source_sha256":core["source_sha256"],"range_proof":range_proof()})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--first-only",action="store_true");args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    rng=random.Random(5603280)
    vectors=[[0]*32,[-2**31]*32,[2**31-1]*32,
             [-2**31 if i%2 else 2**31-1 for i in range(32)]]
    for k in range(32):
        for v in (1<<18,-2**31,2**31-1):
            row=[0]*32;row[k]=v;vectors.append(row)
    vectors += [[rng.randrange(-2**31,2**31) for _ in range(32)] for _ in range(64)]
    vectors += [[rng.randrange(-2**20,2**20) for _ in range(32)] for _ in range(16)]
    if args.first_only: vectors=vectors[:6]
    binary=reference_binary(args.output)
    result=subprocess.run([str(binary)],input="\n".join(" ".join(map(str,x)) for x in vectors)+"\n",
                          capture_output=True,text=True)
    (args.output/"reference-output.txt").write_text(result.stdout)
    (args.output/"reference-checks.txt").write_text(result.stderr)
    assert result.returncode==0,result.stderr
    expected=[list(map(int,line.split())) for line in result.stdout.splitlines()]
    assert len(expected)==len(vectors) and all(len(y)==64 for y in expected)
    (args.output/"vectors.json").write_text(json.dumps(vectors)+"\n")
    report={"passed":False,"vectors":len(vectors),"cases":[],"reference_checks":result.stderr.strip(),
            "range_proof":range_proof(),"qemu_sha256":hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    try:
        for i in range(0,len(vectors),16):
            report["cases"].append(check(args.qemu,args.output,vectors[i:i+16],expected[i:i+16],f"vectors-{i}",
                                         bank=0 if i==0 else 0x30))
        report["cases"].append(check(args.qemu,args.output,vectors[:4],expected[:4],"icount",bank=0x30,icount=5))
        report["passed"]=all(c["passed"] and c["exit_code"]==0 for c in report["cases"])
    except AssertionError as error:
        detail=error.args[0] if error.args else "assertion failed"
        if isinstance(detail,dict):
            detail={"name":detail.get("name"),"registers":detail.get("registers"),
                    "differences":[(i,x,y) for i,(x,y) in enumerate(zip(detail.get("actual_samples",[]),
                        detail.get("expected_samples",[]))) if x!=y][:16]}
        report["failure"]=str(detail)[:2500];print(report["failure"],flush=True)
    finally: (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    return 0 if report["passed"] else 1


if __name__=="__main__": raise SystemExit(main())
