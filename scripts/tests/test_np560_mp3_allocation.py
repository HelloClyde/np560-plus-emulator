#!/usr/bin/env python3
"""Native MP3 allocation/pinning/free against the actual PRG heap functions.

An isolated caller initializes the original heap, optionally holds a pinned
neighbour, acquires/releases the new workspace, and verifies reuse. No host
RAM writes, NAND, fake allocator, production heap reset or codec audio claim.
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
import struct

import build_np560_mp3_allocation as lease
from build_np560_mp3_huffman import ROOT
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr
from test_np560_mac import run

PROGRAM=ROOT/"NP560+V3.80版系统升级程序/NP560.PRG"
PRG_SHA="d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5"
DESC,NEIGHBOUR,RESULT=0x2200,0x2200+lease.DESCRIPTOR_BYTES,0x2400
HEAP_BEGIN,HEAP_END=0x514a40,0x523a40
FUNCTIONS=((0x2577da,0x3e8),(0x315300,0xba),(0x303a56,0x10c),
           (0x308b26,0xf6),(0x308c1c,0xf6),(0x30251e,0x112),
           (0x318abc,0xae),(0x276100,0x34a),(0x30699a,0x102),
           (0x323332,0x7e),(0x30fe0e,0xd2),(0x33197a,0x2e),
           (0x332512,0x28),(0x321bd8,0x86))


def firmware(core):
    original=PROGRAM.read_bytes();assert hashlib.sha256(original).hexdigest()==PRG_SHA
    image=bytearray(original)
    # Preserve the complete immutable source image for existing code aliases,
    # and put the selected original bodies at their linked diagnostic PCs.
    for address,size in FUNCTIONS:
        image[address-0x200000:address-0x200000+size]=original[address-0x030000:address-0x030000+size]
    off=core["code_address"]-0x200000;image[off:off+len(core["code"])]=core["code"]
    rom=bytearray(b"\x00\x0f"*(0x200000//2))
    rom[0x030000:]=original[:0x1d0000]
    expected=[(address,original[address-0x030000:address-0x030000+size]) for address,size in FUNCTIONS]
    return image,rom,expected+[(core["code_address"],core["code"])]


def layout(prefix_bytes, reserve_synthesis=True):
    raw=HEAP_BEGIN+6+(prefix_bytes+6 if prefix_bytes else 0)
    work=raw if (raw&0x7fff)+lease.WORK_STORAGE<=0x8000 else (raw+0x7fff)&~0x7fff
    if not reserve_synthesis:
        size=work-raw+lease.WORK_STORAGE
        if raw+size+6>HEAP_END: return [0]*9
        return [2 if prefix_bytes else 1,size,raw>>16,raw&65535,work>>15,0,0,0,work&0x7fff]
    if work-raw>=lease.SYN_STORAGE:
        syn,left=raw>>15,0x8000|((raw&0x7fff)+2)
        end=work+lease.WORK_STORAGE
    else:
        syn,left=(work>>15)+1,0x8002
        end=(syn<<15)+lease.SYN_STORAGE
    size=max(lease.WORK_STORAGE+lease.SYN_STORAGE,end-raw)
    if raw+size+6>HEAP_END: return [0]*9
    return [2 if prefix_bytes else 1,size,raw>>16,raw&65535,work>>15,syn,left,left+4102,work&0x7fff]


def check(qemu,output,prefix_bytes=0,icount=None, *, reserve_synthesis=True):
    core=lease.build(reserve_synthesis=reserve_synthesis);image,rom,code=firmware(core)
    a=_DMCUAssembler(0x200000);expected=[];count=0
    def const(addr,value): a.emit(0x68F0,value,0xA8F0,addr)
    def factory(target,arg=None):
        if arg is not None: a.emit(0x68F0,arg,0x58F0)
        a.emit(0xBD00|target>>16,target&65535)
        if arg is not None: a.emit(0x50F2)
    def invoke(entry):
        a.emit(0x6810,0,0x6811,0x42,0x68F3,DESC,
               0xBD00|core["entries"][entry]>>16,core["entries"][entry]&65535)
    def sample(reg,value):
        nonlocal count
        a.emit(0x3F10,0xA8F0|reg,RESULT+count*2);count+=1;expected.append(value&65535)
    def record(r0,r2,descriptor):
        sample(0,r0);sample(2,r2)
        for i,v in enumerate(descriptor):
            a.emit(0x6810,0,0x88F0,DESC+i*2);sample(0,v)
    def empty_heap():
        for physical,value in ((HEAP_BEGIN,0),(HEAP_BEGIN+2,0),(HEAP_BEGIN+4,0),
                               *((0x5127ea+i*2,0x8000 if i==0 else 0) for i in range(16))):
            a.emit(0x6810,physical>>15,0x88F0,physical&0x7fff);sample(0,value)
    a.emit(0x6800,2,0x68FF,0x6000,0x68FB,0x4444,0x6810,0)
    for off in range(0,lease.DESCRIPTOR_BYTES,2): const(DESC+off,0)
    factory(0x308c1c)
    if prefix_bytes:
        factory(lease.ALLOC,prefix_bytes)
        a.emit(0x6810,0,0xA8F0,NEIGHBOUR);sample(0,1)
        factory(lease.LOCK,1)
        # The pinned neighbour must survive allocator retries/compaction.
        a.emit(0x6810,0xa2);const(0x4a46,0xbeef)
    descriptor=layout(prefix_bytes,reserve_synthesis);success=bool(descriptor[0])
    invoke("acquire");record(descriptor[0],0 if success else 1,descriptor)
    if success:
        invoke("acquire");record(0,6,descriptor)
    invoke("release");record(0,0,[0]*9)
    invoke("release");record(0,0,[0]*9)
    if prefix_bytes:
        a.emit(0x6810,0xa2,0x88F0,0x4a46);sample(0,0xbeef)
        factory(lease.FREE,1);factory(lease.UNLOCK,1)
    empty_heap()
    # A real second acquisition must reuse the handle and full allocation,
    # without reinitializing the heap or clearing its bitmap in the caller.
    invoke("acquire");record(1,0,layout(0,reserve_synthesis))
    invoke("release");record(0,0,[0]*9)
    empty_heap()
    a.emit(0x6810,0);read_sfr(a.words,0x10,10);read_sfr(a.words,0x11,12)
    words=a.finish();assert len(words)*2+2<0x1000
    name=f"original-heap-prefix-{prefix_bytes:04x}"
    return run(qemu,output,name,words,{10:0,11:0x4444,12:0x42,15:0x6000},
        rom=rom,tail=(0x1000,image[0x1000:]),icount=icount,timeout=30,
        expected_code=code,expected_data=[v-65536 if v>=32768 else v for v in expected],
        capture_ranges=[("heap",HEAP_BEGIN,HEAP_END-HEAP_BEGIN)],
        metadata={"prefix_bytes":prefix_bytes,"expected_acquired":success,"initial_descriptor":descriptor,
            "reserve_synthesis":reserve_synthesis,
            "factory_allocator_bytes_unchanged":True,"native_allocation_sha256":hashlib.sha256(core["code"]).hexdigest(),
            "heap_reset_only_at_isolated_test_start":True,"factory_player_connected":False})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--first-only",action="store_true")
    parser.add_argument("--compact-hle",action="store_true",
                        help="test HLE workspace without native synthesis history")
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    report={"passed":False,"prg_sha256":PRG_SHA,"qemu_sha256":hashlib.sha256(args.qemu.read_bytes()).hexdigest(),"cases":[]}
    try:
        for prefix in ((0,) if args.first_only else (0,0x2000,0x36c0,0x4000,0x5000,0x7000)):
            report["cases"].append(check(args.qemu,args.output,prefix,5 if prefix==0x2000 else None,
                                         reserve_synthesis=not args.compact_hle))
        report["passed"]=all(c["passed"] and c["exit_code"]==0 for c in report["cases"])
    except AssertionError as exc:
        detail=exc.args[0] if exc.args else "assertion failed"
        if isinstance(detail,dict):
            detail={k:detail[k] for k in ("registers","code_phase","first_code_differences","actual_samples","expected_samples") if k in detail}
        report["failure"]=str(detail)[:4000];print(report["failure"],flush=True)
    finally: (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__=="__main__": raise SystemExit(main())
