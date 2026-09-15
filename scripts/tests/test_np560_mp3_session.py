#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Owned native MP3 session, original PCM buffers and complete heap cleanup.

The session object is separately allocated/pinned with real PRG functions.
An optional set of five pinned neighbours reproduces the measured player's
heap geometry, not the player execution itself. Real continuous MP3 bytes
are fed by 16:E844; each successful session step is captured FROM the X0
output buffers exposed by output, not directly from decoder private PCM.
The optional original-player-consumer mode binds 49F8/49BE only inside this
diagnostic ROM and runs unmodified 16:E89C. Its owner resolver is test-only;
there is no production singleton, host decoding in production, or playback claim.
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
import subprocess

import build_np560_mp3_session as session
import build_np560_mp3_allocation as lease
from build_np560_mp3_resident import load_bundle
from np560_assembler import _DMCUAssembler
from np560_mp3_link import fragments
from test_np560_mp3_allocation import PROGRAM,PRG_SHA,FUNCTIONS,HEAP_BEGIN
from test_np560_mp3_frame import fixtures,pcm_artifact,network_words
from test_np560_mac import run

DIAG,RESULT,OWNER_COPY,CAPTURE,STREAM=0x800,0x900,0x700,0x4f0000,0x380000
PHASE_CAPTURE=0x4e0000
NEIGHBOURS=(6172,3072,38,1536,3072)
PARAMS=(0,0x1784,0,0x2084,0,0x1c04,0,0x2504,0,0x2984,0,0x1000,0x300)


def check(qemu,output,mp3,frames,bundle,with_neighbours,icount,player_consumer=False):
    cores,rom,manifest=load_bundle(bundle);entries=cores["session"]["entries"]
    original=PROGRAM.read_bytes();assert hashlib.sha256(original).hexdigest()==PRG_SHA
    raw=mp3.read_bytes();first=frames[0]["file_offset"]
    end=frames[-1]["file_offset"]+frames[-1]["frame_bytes"]
    stream=raw[first:end+(end-first)%2]
    assert len(stream)%2==0 and len(stream)<=1532,"choose a finite prefix that fits the ring"
    nch=frames[0]["nch"];assert all(f["nch"]==nch for f in frames)
    owner_address=HEAP_BEGIN+6+sum(n+6 for n in NEIGHBOURS if with_neighbours)
    owner_bank,owner_offset=owner_address>>15,owner_address&0x7fff
    owner_handle=6 if with_neighbours else 1
    a=_DMCUAssembler(0x30000);expected=[];checks=[];expected_phases=[]
    def imm(r,v): a.emit(0x68f0|r,v&65535)
    def const(addr,v): imm(0,v);a.emit(0xa8f0,addr)
    def call(target): a.emit(0xbd00|target>>16,target&65535)
    def factory(target,arg=None):
        # The diagnostic caller holds no live GPR values across these calls;
        # session's production allocation wrapper preserves its own context.
        if arg is not None: imm(0,arg);a.emit(0x58f0)
        call(target)
        if arg is not None: a.emit(0x50f2)
    def owner(): a.emit(0x6810,owner_bank);imm(3,owner_offset)
    def invoke(name): owner();call(entries[name])
    def sample(r,v,label):
        a.emit(0x3f10,0xa8f0|r,RESULT+2*len(expected));expected.append(v&65535);checks.append(label)
    def result(r0,r2,label): sample(0,r0,label+".r0");sample(2,r2,label+".r2")
    def consume(label,empty=False):
        # The original consumer, not a host emulation of its status logic.
        # Only diagnostic ROM thunks below resolve this test-owned object.
        call(0x16e89c)
        a.emit(0x3f10,0x88f0,0x3346);sample(0,0,label+".factory error")
        # BIT-address 8C is not SFR register 8C. Read the same bit-space
        # operand as the original branch through its documented BMOV form.
        a.emit(0x7c8c,0x7080,0x74f0,1)
        sample(0,int(empty),label+".factory exhausted flag")
        if empty:
            a.emit(0x3f10,0x88f0,0x4a76);sample(0,16,label+".factory fade countdown")
    def field(off,value,label): owner();a.emit(0x88f0,owner_offset+off);sample(0,value,label)
    def output_pair(phase,label,status=0):
        # right far-out argument, then left, as in original 4954 callers.
        for value in (DIAG+0x14,0,DIAG+0x10,0): imm(0,value);a.emit(0x58f0)
        invoke("output");a.emit(0x50f8);result(0,status,label)
        for offset,value in enumerate((0,PARAMS[1+phase*2],0,PARAMS[5+phase*2])):
            a.emit(0x3f10,0x88f0,DIAG+0x10+offset*2);sample(0,value,label+f".ptr{offset}")
    def zero_buffers(label):
        a.emit(0x6810,0);imm(5,0x1784);imm(1,2304);imm(2,0)
        a.label(label);a.emit(0x3805,0x1520,0x5211);a.ajmp(label,2);sample(2,0,label)
    def capture_pcm(label):
        for ch in range(nch):
            a.emit(0x6810,0,0x6811,CAPTURE>>15,0x88f5,DIAG+0x12+ch*4,0x88f6,DIAG+6)
            imm(1,576)
            a.label(label+str(ch));a.emit(0x3805,0x1a60,0x5211);a.ajmp(label+str(ch),2)
            a.emit(0xa8f6,DIAG+6)
    a.emit(0x6800,2,0x68ff,0x6000,0x6810,0,0x6811,0);factory(0x308c1c)
    if with_neighbours:
        for i,size in enumerate(NEIGHBOURS,1):
            factory(lease.ALLOC,size);sample(0,i,f"neighbour-{i}")
            factory(lease.LOCK,i)
    factory(lease.ALLOC,session.SIZE);sample(0,owner_handle,"owner handle")
    factory(lease.LOCK,owner_handle)
    sample(0,owner_address>>16,"owner segment");sample(1,owner_address&65535,"owner offset")
    owner();imm(5,owner_offset);imm(1,session.SIZE//2);imm(0,0)
    a.label("zero_owner");a.emit(0x1a50,0x5211);a.ajmp("zero_owner",2)
    for i,value in enumerate(PARAMS): const(owner_offset+session.CONFIG+i*2,value)
    const(owner_offset+session.SIZE-2,0xbeef)
    a.emit(0x6810,0);imm(5,0x1784);imm(1,2304);imm(0,0x5aa5)
    a.label("dirty_outputs");a.emit(0x1a50,0x5211);a.ajmp("dirty_outputs",2)
    for off,v in ((0x1782,0xcafe),(0x2984,0x1234),(0x2e02,0xcafe)): const(off,v)
    invoke("release");result(0,0,"empty release")
    invoke("step");result(0,8,"closed step")
    # Invalid overlapping PCM buffers must not allocate or erase anything.
    owner();const(owner_offset+session.CONFIG+6,PARAMS[1])
    invoke("create");result(0,2,"overlap rejected")
    field(lease.HANDLE,0,"invalid create owns no lease")
    a.emit(0x3f10,0x88f0,0x1784);sample(0,0x5aa5,"invalid create did not erase outputs")
    owner();const(owner_offset+session.CONFIG+6,PARAMS[3])
    for r in range(8,15): imm(r,0x1111*r)
    invoke("create");result(0,0,"create")
    for r in range(8,15): sample(r,0x1111*r,f"create preserves R{r}")
    invoke("create");result(0,7,"already open")
    output_pair(1,"before first PCM");zero_buffers("created zero buffers")
    invoke("free_words");result(766,0,"empty ring")
    invoke("step");result(0,1,"no input")
    field(session.PHASE,1,"short does not flip");field(session.READY,0,"short no PCM")
    # Busy must not release the acquired block or exchange output buffers.
    owner();const(owner_offset+session.BUSY,1)
    invoke("release");result(0,7,"busy release")
    invoke("reset");result(0,7,"busy reset")
    invoke("step");result(0,7,"busy step")
    invoke("free_words");result(0,7,"busy free words")
    if player_consumer:
        invoke("player_step");result(0,7,"busy player step")
        a.emit(0x3f10,0x88f0,0x3346);sample(0,0,"busy is not a factory fatal error")
    output_pair(1,"busy output",7)
    owner();const(owner_offset+session.BUSY,0)
    a.emit(0x6810,0);const(DIAG+6,0x8000);const(DIAG+8,0x8000)
    if player_consumer:
        # A stopped software-only consumer experiment: no live ISR, stream
        # timer, DTU or audio setup is bypassed and called "playback".
        for group in (0x8c,0x89,0x8a):
            for bit in range(16): a.emit(0xf000|bit<<8|group)
        for off in (0x4a52,0x4a54,0x4a56,0x4a58,0x4a5a,0x4a76,0x4a78): const(off,0)
    for v in (len(stream)//2,0,STREAM>>16): imm(0,v);a.emit(0x58f0)
    call(0x16e844);a.emit(0x50f6)
    phase=1;consumed=0;granules=0;physical_buffers=[[0]*576 for _ in range(4)]
    for frame in frames:
        for gr in range(len(frame["segments"])//nch):
            if gr==0: consumed+=frame["frame_bytes"]
            if player_consumer: consume(f"granule{granules}")
            else: invoke("step");result(576,0,f"granule{granules}")
            phase^=1;output_pair(phase,f"output{granules}")
            capture_pcm(f"capture{granules}-")
            a.acall("capture_four")
            for ch in range(2):
                physical_buffers[phase*2+ch]=(frame["segments"][gr*nch+ch]["synthesis"]["pcm"] if ch<nch else [0]*576)
            expected_phases.extend(v for values in physical_buffers for v in values)
            invoke("free_words");result(766-(len(stream)-consumed+1)//2,0,f"free{granules}")
            granules+=1
    if player_consumer: consume("trailing input",empty=True)
    else: invoke("step");result(0,1,"trailing input")
    field(session.PHASE,phase,"short retains last phase")
    field(session.READY,1,"short retains last PCM")
    a.acall("capture_four");expected_phases.extend(v for values in physical_buffers for v in values)
    invoke("reset");result(0,0,"reset")
    output_pair(1,"reset output");zero_buffers("reset zero buffers")
    field(session.READY,0,"reset clears ready")
    invoke("free_words");result(766,0,"reset ring free")
    invoke("release");result(0,0,"release")
    invoke("release");result(0,0,"repeat release")
    if player_consumer:
        invoke("player_step");result(0,8,"closed player step")
        a.emit(0x3f10,0x88f0,0x3346);sample(0,1,"closed decoder is a factory fatal error")
    for off in range(lease.DESCRIPTOR_BYTES//2): field(off*2,0,f"released descriptor{off}")
    field(session.MAGIC,0,"released magic")
    # Reopen and close the SAME owned control object, without resetting heap.
    invoke("create");result(0,0,"reopen")
    invoke("release");result(0,0,"release reopened")
    field(session.SIZE-2,0xbeef,"owner tail guard")
    for off,v in ((0x1782,0xcafe),(0x2984,0x1234),(0x2e02,0xcafe)):
        a.emit(0x3f10,0x88f0,off);sample(0,v,f"X0 outside guard {off:04x}")
    owner();imm(5,owner_offset);imm(6,0x8000|OWNER_COPY);imm(1,session.SIZE//2);a.emit(0x6811,0)
    a.label("copy_owner");a.emit(0x3805,0x1a60,0x5211);a.ajmp("copy_owner",2)
    factory(lease.FREE,owner_handle);factory(lease.UNLOCK,owner_handle)
    if with_neighbours:
        for handle in range(5,0,-1): factory(lease.FREE,handle);factory(lease.UNLOCK,handle)
    a.emit(0x6810,0xa2)
    for off,v in ((0x4a40,0),(0x4a42,0),(0x4a44,0),*((0x27ea+i*2,0x8000 if i==0 else 0) for i in range(16))):
        a.emit(0x88f0,off);sample(0,v,f"clean heap {off:04x}")
    a.ajmp("end")
    a.label("capture_four")
    a.emit(0x6810,0,0x6811,PHASE_CAPTURE>>15,0x88f6,DIAG+8)
    imm(5,0x1784);imm(1,2304)
    a.label("copy_four");a.emit(0x3805,0x1a60,0x5211);a.ajmp("copy_four",2)
    a.emit(0xa8f6,DIAG+8,0xc600)
    if player_consumer:
        for label,name in (("bind_player_step","player_step"),("bind_player_free","free_words")):
            a.label(label);a.emit(0x1f10,0x58f3)
            invoke(name);a.emit(0x383f,0x1f90,0xc620)
    a.label("end")
    words=a.finish();assert len(words)*2+2<0x1000,("caller too large",len(words)*2)
    assert len(expected_phases)*2<=0x8000
    payload=bytearray(original[0x1000:]);packed=struct.pack(f"<{len(stream)//2}H",*network_words(stream))
    payload[STREAM-0x31000:STREAM-0x31000+len(packed)]=packed
    code=[(addr,original[addr-0x30000:addr-0x30000+size]) for addr,size in FUNCTIONS]
    code += [(addr,data) for core in cores.values() for _,addr,data in fragments(core)]
    if player_consumer:
        rom=bytearray(rom)
        for entry,label in ((0x149f8,"bind_player_step"),(0x149be,"bind_player_free")):
            assert rom[entry:entry+4]==b"\x00\x0f"*2
            target=a.labels[label];jump=struct.pack("<2H",0xad00|target>>16,target&65535)
            rom[entry:entry+4]=jump;code.append((entry,jump))
        rom=bytes(rom)
        for address,size in ((0x16e89c,0x114),(0x0837f4,0x2c),(0x0847a0,4),(0x16edfa,0x4c)):
            code.append((address,original[address-0x30000:address-0x30000+size]))
    case=run(qemu,output,"session",words,{15:0x6000},rom=rom,tail=(0x1000,payload),
        boot_mode="firmware-vma03",icount=icount,timeout=180,poll_interval=.25,
        expected_code=code,capture_ranges=[("checks",RESULT,len(expected)*2),
            ("owner",OWNER_COPY,session.SIZE),("guest-pcm",CAPTURE,granules*nch*1152),
            ("all-output-phases",PHASE_CAPTURE,len(expected_phases)*2)],
        metadata={"rom_sha256":manifest["rom_sha256"],"frames":len(frames),"granules":granules,
            "control_object_allocated_bytes":session.SIZE,"control_object_physical_address":owner_address,
            "original_player_heap_neighbour_sizes":list(NEIGHBOURS) if with_neighbours else [],
            "pcm_captured_from":"original X0 output buffers via session.output far results",
            "factory_player_connected":False,"original_player_consumer_called":player_consumer,
            "owner_resolver":"diagnostic thunk to actual allocated/pinned object" if player_consumer else "explicit session argument",
            "runtime_rom_sha256":hashlib.sha256(rom).hexdigest()})
    actual=struct.unpack(f"<{len(expected)}H",Path(case["captures"]["checks"]["path"]).read_bytes())
    differences=[{"index":i,"check":name,"expected":want,"actual":got} for i,(name,want,got) in enumerate(zip(checks,expected,actual)) if want!=got]
    case["control_checks"]={"count":len(checks),"differences":differences,"passed":not differences}
    (output/"control-checks.json").write_text(json.dumps(case["control_checks"],indent=2)+"\n",encoding="utf-8")
    assert not differences,differences[:20]
    actual_phases=struct.unpack(f"<{len(expected_phases)}h",Path(case["captures"]["all-output-phases"]["path"]).read_bytes())
    phase_differences=[(i,want,got) for i,(want,got) in enumerate(zip(expected_phases,actual_phases)) if want!=got]
    case["phase_checks"]={"snapshots":granules+1,"compared_samples":len(expected_phases),
                          "differences":phase_differences[:20],"passed":not phase_differences}
    (output/"phase-checks.json").write_text(json.dumps(case["phase_checks"],indent=2)+"\n",encoding="utf-8")
    assert not phase_differences,phase_differences[:20]
    return case


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("qemu","mp3","resident-bundle","output"): p.add_argument("--"+arg,type=Path,required=True)
    p.add_argument("--limit",type=int,default=3);p.add_argument("--player-neighbours",action="store_true")
    p.add_argument("--icount",type=int)
    p.add_argument("--original-player-consumer",action="store_true",
                   help="exercise original 16:E89C via diagnostic owner bindings, not full playback")
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    report={"passed":False,"cases":[],"qemu_sha256":hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    try:
        cores,_,_=load_bundle(args.resident_bundle)
        fast=bool(cores["synthesis"].get("fast_dct32",False))
        report["fast_dct32"]=fast
        frames=fixtures(args.mp3,args.output,args.limit,True,True,0,True,True,True,fast_dct=fast)
        case=check(args.qemu,args.output,args.mp3,frames,args.resident_bundle,args.player_neighbours,args.icount,args.original_player_consumer)
        report["cases"].append(case);comparison=pcm_artifact(args.mp3,args.output,frames,case)
        report.update(pcm_comparison=comparison,passed=case["passed"] and case["exit_code"]==0 and comparison["within_8_pcm_lsb"])
    except (AssertionError,subprocess.CalledProcessError) as error:
        report["failure"]=str(error)[:3000];print(report["failure"],flush=True)
    finally: (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__=="__main__": raise SystemExit(main())
