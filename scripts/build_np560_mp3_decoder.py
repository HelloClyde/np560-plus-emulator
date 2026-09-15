#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bank-owned native PCM decoder; not the factory 01:49F8 ABI yet.

DS0:R3 selects an allocated 0x6300-byte near workspace, independent of bank
zero. R3 is an even base offset 0..0x1D00, supplied to every public entry;
all layout constants below are relative to that base, not absolute pointers.
All nested components must use workspace_bank=None. No test oracle, raw
file parser, host callback, fixed success or machine memory reservation.

Caller inputs: MODE_EXT, synthesis bank/two pointers, FRAME's five header
fields, and INPUT (raw bit context after header/CRC). Synthesis state needs
two disjoint 4098-byte areas in another bank. Reset validates ownership
geometry and clears histories, preserving these input/configuration fields.

decode_frame consumes one complete frame and returns its first 576-sample
PCM pair; next_granule drains the second MPEG1 granule WITHOUT new input.
R0=576 per channel/R2=0, buffers PCM[0]/PCM[1], nch=FRAME+2. Mono clears
unused PCM[1]. R0=0 on failure: R2=1 no full input/no pending PCM,
2 invalid config/header, 3..5 entropy errors, 6 previous frame still pending,
7 postprocessing error (DETAIL=stage*256+subordinate status).
Busy and empty-next calls leave all state and output unchanged. Post-stage
failure invalidates pending/output; reset is required to resume filter state.
No partial PCM is published. GPR R1,R3..14, DS and SOCR are preserved.

This workspace's fixed offsets are a NEW internal ABI, not recovered factory
fields. Code is still diagnostic-linked at 20:D400; production ROM placement
and the player's allocation/teardown lifecycle must be supplied before installation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_np560_mp3_frame import components, SIZE as ENTROPY_BYTES, SIDE, RECORDS, SF, MASK, STRIDE, VALID
from np560_assembler import _DMCUAssembler
from np560_mp3_link import code_span

# Existing Harvard alias 20:CE3A..D39B ends immediately before this gap.
# 20:2DE0..338F is NOT free: its code view comes from 3D:2DE0.
ADDRESS, WORKSPACE_BYTES = 0x20D400, 0x6300
MODE_EXT, SYN_BANK, SYN_LEFT, SYN_RIGHT = 0, 2, 4, 6
PENDING, NEXT_RECORD, NEXT_SIDE, PCM_VALID, STATUS, DETAIL, MAGIC = 8, 10, 12, 14, 16, 18, 20
INPUT, FRAME = 0x20, 0x100
SPECTRA, SCRATCH, OVERLAP = (0x2100, 0x2A00), 0x3300, (0x3C00, 0x4500)
HYBRID_OUTPUT, PCM = 0x4E00, (0x5700, 0x5B80)
RQ_DESC, JOINT_DESC, RO_DESC, HB_DESC, SY_DESC = 0x6000, 0x6010, 0x6030, 0x6040, 0x6050
JOINT_WORK, HYBRID_WORK, SYN_WORK, EXPONENTS = 0x6070, 0x60D0, 0x6170, (0x6200, 0x6250)
MAGIC_VALUE = 0x4D33


def build(address=ADDRESS, cores=None):
    cores = cores or components(workspace_bank=None)
    for name, core in cores.items():
        assert core.get("workspace_bank", "unspecified") is None, (
            "PCM driver requires caller-DS0 components", name)
    a = _DMCUAssembler(address)
    def imm(r,v): a.emit(0x68F0|r,v&65535)
    def mov(d,s): a.emit(0x0800|d<<4|s)
    def cmpi(r,v): a.emit(0x76F0|r,v&65535)
    def ptr(r,offset):
        mov(r,14)
        if offset: a.emit(0x70F0|r,offset)
    def get(r,addr): ptr(1,addr);a.emit(0x2801|r<<4)
    def put(r,addr):
        assert r!=1, "R1 is the descriptor address scratch"
        ptr(1,addr);a.emit(0x0A10|r)
    def constant(addr,v): imm(0,v);put(0,addr)
    def pointer(addr,offset): ptr(0,offset);put(0,addr)
    def call(name,entry):
        target=cores[name]["entries"][entry]
        a.emit(0xBD00|target>>16,target&65535)
    saved=(1,*range(3,15))
    def enter():
        for r in saved: a.emit(0x58F0|r)
        a.emit(0x1F10,0x1F11,0x1F00)
        mov(14,3);cmpi(14,0x8000-WORKSPACE_BYTES);a.ajmp("invalid",0xA)
        mov(0,14);a.emit(0x74F0,1);a.ajmp("invalid",2)
    def leave():
        a.emit(0x1F80,0x1F91,0x1F90)
        for r in reversed(saved): a.emit(0x380F|r<<4)
        a.emit(0xC620)
    def magic():
        get(0,MAGIC);cmpi(0,MAGIC_VALUE);a.ajmp("invalid",2)
    def copy_words(source,dest,count,label):
        ptr(3,source);ptr(5,dest);imm(1,count)
        a.label(label);a.emit(0x3803,0x1A50,0x5211);a.ajmp(label,2)
    def check_stage(stage):
        imm(4,stage<<8);cmpi(2,0);a.ajmp("post_error",2)

    a.label("reset")
    enter()
    # These are allocation constraints, not guessed original RAM fields.
    a.emit(0x1F10,0x380F)
    cmpi(0,0x1ff);a.ajmp("invalid",0xA)
    get(1,SYN_BANK);cmpi(1,0x1ff);a.ajmp("invalid",0xA)
    a.emit(0x1601);a.ajmp("invalid",1)
    for off in (SYN_LEFT,SYN_RIGHT):
        get(0,off);cmpi(0,0x8000);a.ajmp("invalid",5)
        cmpi(0,0xeffe);a.ajmp("invalid",0xA)
        a.emit(0x74F0,1);a.ajmp("invalid",2)
    get(0,SYN_LEFT);get(1,SYN_RIGHT);a.emit(0x1601)
    a.ajmp("left_first",5)
    a.emit(0x1210);mov(0,1);a.ajmp("state_gap")
    a.label("left_first");a.emit(0x1201)
    # Above differences are negative; negate without signed overflow.
    a.label("state_gap");a.emit(0x77F0,65535,0x5001)
    cmpi(0,4098);a.ajmp("invalid",5)
    ptr(3,FRAME);call("frame","reset")
    for offset in OVERLAP:
        ptr(3,offset);call("hybrid","reset")
    get(0,SYN_BANK);put(0,SY_DESC)
    for off in (SYN_LEFT,SYN_RIGHT):
        get(0,off);put(0,SY_DESC+2);ptr(3,SY_DESC);call("synthesis","reset")
        cmpi(2,0);a.ajmp("invalid",2)
    ptr(3,PCM[0]);imm(1,1152);imm(0,0)
    a.label("clear_pcm");a.emit(0x1A30,0x5211);a.ajmp("clear_pcm",2)
    for addr in (PENDING,NEXT_RECORD,NEXT_SIDE,PCM_VALID,STATUS,DETAIL): constant(addr,0)
    constant(MAGIC,MAGIC_VALUE)
    imm(0,0);imm(2,0);a.ajmp("return")

    a.label("decode_frame")
    enter();magic()
    get(0,PENDING);cmpi(0,0);a.ajmp("busy",2)
    get(0,MODE_EXT);cmpi(0,3);a.ajmp("invalid",0xA)
    get(1,FRAME+2);cmpi(1,1);a.ajmp("header_stereo",2)
    cmpi(0,0);a.ajmp("invalid",2)
    a.label("header_stereo")
    # Frame front-end validates the remaining header/bit-context geometry.
    constant(PCM_VALID,0);constant(STATUS,0);constant(DETAIL,0)
    ptr(3,FRAME);ptr(12,INPUT);call("frame","frame")
    cmpi(2,0);a.ajmp("entropy_error",2)
    pointer(NEXT_RECORD,FRAME+RECORDS);pointer(NEXT_SIDE,FRAME+SIDE+16)
    get(0,FRAME);cmpi(0,0);imm(0,1);a.ajmp("one_granule",2)
    imm(0,2)
    a.label("one_granule");put(0,PENDING);a.ajmp("produce")

    a.label("next_granule")
    enter();magic()
    get(0,PENDING);cmpi(0,0);a.ajmp("empty",1)
    constant(PCM_VALID,0);constant(STATUS,0);constant(DETAIL,0)
    a.label("produce")
    get(9,NEXT_RECORD);get(10,NEXT_SIDE);get(11,FRAME+2)
    for ch in (0,1):
        if ch:
            cmpi(11,2);a.ajmp("requant_ready",2)
        mov(0,10)
        if ch: a.emit(0x70F0,32)
        put(0,RQ_DESC)
        mov(0,9)
        if ch: a.emit(0x70F0,STRIDE)
        put(0,RQ_DESC+6);a.emit(0x70F0,SF);put(0,RQ_DESC+2)
        get(0,FRAME+4);put(0,RQ_DESC+4)
        pointer(RQ_DESC+8,SPECTRA[ch]);pointer(RQ_DESC+10,EXPONENTS[ch])
        ptr(3,RQ_DESC);call("requantize","spectrum");check_stage(1)
    a.label("requant_ready")
    get(0,MODE_EXT);cmpi(0,0);a.ajmp("joint_ready",1)
    get(0,FRAME+4);put(0,JOINT_DESC);get(0,MODE_EXT);put(0,JOINT_DESC+2)
    put(10,JOINT_DESC+4);mov(0,10);a.emit(0x70F0,32);put(0,JOINT_DESC+6)
    for off,extra in ((8,SF),(10,MASK),(12,0)):
        mov(0,9);a.emit(0x70F0,STRIDE+extra);put(0,JOINT_DESC+off)
    for off,value in ((14,SPECTRA[0]),(16,SPECTRA[1]),(18,JOINT_WORK)): pointer(JOINT_DESC+off,value)
    ptr(3,JOINT_DESC);call("intensity","joint");check_stage(2)
    a.label("joint_ready")
    for ch in (0,1):
        if ch:
            cmpi(11,2);a.ajmp("mono",2)
        get(0,FRAME+4);put(0,RO_DESC)
        mov(3,10);a.emit(0x70F3,ch*32+10,0x2803);put(0,RO_DESC+2)
        mov(3,10);a.emit(0x70F3,ch*32+8,0x2803,0x4D03,0x74F0,1);put(0,RO_DESC+4)
        pointer(RO_DESC+6,SPECTRA[ch]);pointer(RO_DESC+8,SCRATCH)
        ptr(3,RO_DESC);call("stereo","reorder");check_stage(3)
        copy_words(SCRATCH,SPECTRA[ch],1152,f"reorder_copy_{ch}")
        ptr(3,RO_DESC);call("antialias","spectrum");check_stage(4)
        copy_words(RO_DESC,HB_DESC,3,f"hybrid_geometry_{ch}")
        for off,value in ((6,SPECTRA[ch]),(8,HYBRID_OUTPUT),(10,OVERLAP[ch]),(12,HYBRID_WORK)):
            pointer(HB_DESC+off,value)
        ptr(3,HB_DESC);call("hybrid","hybrid");check_stage(5)
        get(0,SYN_BANK);put(0,SY_DESC);get(0,SYN_LEFT if ch==0 else SYN_RIGHT);put(0,SY_DESC+2)
        # Entropy/reorder staging is dead during synthesis. Reuse that owned
        # lease region for the wider fast DCT; do not grow the heap or
        # overwrite the live exponent arrays next to the old 32-byte work.
        synthesis_work=SCRATCH if cores["synthesis"].get("fast_dct32") else SYN_WORK
        if synthesis_work==SCRATCH:
            assert SCRATCH+cores["synthesis"]["work_bytes"]<=OVERLAP[0]
        for off,value in ((4,HYBRID_OUTPUT),(6,PCM[ch]),(8,synthesis_work)): pointer(SY_DESC+off,value)
        ptr(3,SY_DESC);call("synthesis","granule");check_stage(6)
    a.ajmp("produced")
    a.label("mono")
    ptr(3,PCM[1]);imm(1,576);imm(0,0)
    a.label("clear_unused_channel");a.emit(0x1A30,0x5211);a.ajmp("clear_unused_channel",2)
    a.label("produced")
    a.emit(0x70F9,STRIDE,0x70FA,32)
    cmpi(11,2);a.ajmp("advance_ready",2)
    a.emit(0x70F9,STRIDE,0x70FA,32)
    a.label("advance_ready")
    put(9,NEXT_RECORD);put(10,NEXT_SIDE)
    get(0,PENDING);a.emit(0x5201);put(0,PENDING)
    constant(PCM_VALID,576);imm(2,0);a.ajmp("return")
    a.label("post_error")
    a.emit(0x1542);put(4,DETAIL)
    constant(MAGIC,0);imm(2,7);a.ajmp("failed")
    a.label("entropy_error")
    get(0,FRAME+16);put(0,DETAIL)
    a.label("failed")
    put(2,STATUS);constant(PENDING,0);constant(PCM_VALID,0);imm(0,0);a.ajmp("return")
    for label,status in (("invalid",2),("busy",6),("empty",1)):
        a.label(label);imm(0,0);imm(2,status);a.ajmp("return")
    a.label("return");leave()
    code=struct.pack(f"<{len(a.words)}H",*a.finish())
    code_span(address,code)
    assert FRAME+ENTROPY_BYTES<=SPECTRA[0] and SYN_WORK+32<=EXPONENTS[0]
    return {"code":code,"code_address":address,"entries":a.labels,"workspace_bytes":WORKSPACE_BYTES,
            "workspace_bank":"caller DS0", "workspace_offset":"caller R3",
            "synthesis_state_bytes":8196, "factory_rom_patch":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    cores=components(workspace_bank=None);cores["decoder"]=build(cores=cores)
    manifest={"components":{},"workspace_bytes":WORKSPACE_BYTES,"workspace_bank":"caller DS0","workspace_offset":"caller R3",
              "synthesis_state_bytes":8196,"factory_rom_patch":False,"complete_mp3_decoder":False}
    fragments=[]
    for name,core in cores.items():
        item={"entries":core["entries"],"workspace_bank":core["workspace_bank"],"fragments":[]}
        for key,addr in (("code","code_address"),("tables","table_address")):
            if key not in core: continue
            filename=f"{name}-{key}.bin";data=core[key]
            (args.output/filename).write_bytes(data)
            item["fragments"].append({"file":filename,"address":core[addr],"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
            fragments.append((core[addr],core[addr]+len(data)))
        manifest["components"][name]=item
    fragments.sort();assert all(l[1]<=r[0] for l,r in zip(fragments,fragments[1:]))
    (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(manifest["components"]["decoder"],indent=2))
    return 0


if __name__=="__main__": raise SystemExit(main())
