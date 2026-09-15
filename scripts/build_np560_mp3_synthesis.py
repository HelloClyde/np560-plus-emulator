#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native 32-subband polyphase synthesis -> signed PCM16, not factory ABI.

slot: R3 -> {state_bank, state_ptr, X32_Q23, PCM32_s16, work32bytes}.
granule: same descriptor, X576_Q23(time-major), PCM576_s16; 18 slots.
reset: R3 -> {state_bank,state_ptr,...}; clears one channel's state.
State is banked DS1 memory: aligned ptr in 8000..EFFE, bank<=01FF,
4098 bytes = head_byte_offset + V1024_Q17. Reset head=0. Each slot
decrements head by 256 modulo4096, without shifting/injecting history.
Other buffers/work/descriptor/stack are allocated, aligned, disjoint in
near DS0=0; state must also be disjoint, including across data aliases.

All public entries preserve R1,R3..14, DS and SOCR. Success R0=32/576/
1024 respectively, R2=0. Invalid state geometry/head R0=0,R2=2 before
state/output mutation (granule may write work); reject partial granules.
PCM clipping is normal output saturation, not a decode failure.

Q26 cosine matrix -> 64-bit dots -> Q17 V history; full signed Q23
input width is safe. Exact Q16 window -> 64-bit sum; add 2^17, >>18,
then saturate PCM16 (nearest, ties toward +infinity). Matrix has 32
unique rows, with exact V symmetries filling the other 32 positions.
Rounding/headroom choices are explicit, not original ROM/libmad bits.
Work words: bank,base,head,input,output,chunk,counter,clip_count, then
five-word mutable granule slot descriptor. No host codec or fake PCM.
Optional fast_core replaces only the matrix with the wide libmad DCT;
work then requires 1102 bytes (descriptor at32, fast scratch at40).
Its Q28 intermediate rounding is explicit; old Q26 V bytes are not the
oracle for that algorithm. Windowing, PCM rounding and ring layout stay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct

from build_np560_mp3_huffman import ROOT
from build_np560_mp3_antialias import build as build_math
from np560_assembler import _DMCUAssembler
from np560_mp3_workspace import select_workspace
from np560_mp3_link import code_span, near_table

ADDRESS,TABLE_ADDRESS=0x201400,0x21C0F0
WINDOW_ADDRESS=TABLE_ADDRESS+4096
STATE_BYTES,WORK_BYTES,V_FRACBITS=4098,32,17
D_SHA="3d12dec8a4e0afd1cdfa78b9e8db598196259feb0e65511f494532381202588d"


def window():
    raw=(ROOT/"doc/sources/libmad-20260907/D.dat").read_bytes()
    assert hashlib.sha256(raw).hexdigest()==D_SHA
    text=re.sub(r"/\*.*?\*/","",raw.decode(),flags=re.S)
    values=[(-1 if sign else 1)*int(value,16) for sign,value in re.findall(r"(-?)\s*PRESHIFT\((0x[0-9a-fA-F]+)\)",text)]
    assert len(values)==17*32 and all(v%4096==0 for v in values)
    rows=[values[i:i+32] for i in range(0,len(values),32)]
    assert all(r[:16]==r[16:] for r in rows)
    return [(rows[j][i] if j<=16 else -rows[32-j][31-i])//4096 for i in range(16) for j in range(32)]


def tables(table_address=TABLE_ADDRESS,*,fast=False):
    rows=[[round(math.cos(math.pi/64*(16+i)*(2*k+1))*(1<<26)) for k in range(32)]
          for i in (*range(16),*range(33,49))]
    assert max(sum(abs(v) for v in row) for row in rows)<=32*(1<<26)
    data=bytearray() if fast else bytearray(struct.pack("<1024i",*(v for row in rows for v in row)))
    w=window()
    for j in range(32):
        for i in range(16):
            off=4*(128*(i//2)+(96 if i%2 else 0)+j)
            data.extend(struct.pack("<Hi",off,w[j+32*i]))
    assert len(data)==(3072 if fast else 7168)
    near_table(table_address,data)
    return bytes(data)


def build(address=ADDRESS, workspace_bank=0, *, table_address=TABLE_ADDRESS, math_core=None, fast_core=None):
    a = _DMCUAssembler(address)
    math_core = math_core or build_math(workspace_bank=workspace_bank)
    assert address>>16 == math_core["entries"]["multiply_signed"]>>16, "synthesis RETC math helper must share CS"
    window_address = table_address+(0 if fast_core else 4096)
    def imm(r,v): a.emit(0x68F0|r,v&65535)
    def mov(d,s): a.emit(0x0800|d<<4|s)
    def cmpi(r,v): a.emit(0x76F0|r,v&65535)
    def push(r): a.emit(0x58F0|r)
    def pop(r): a.emit(0x380F|r<<4)
    def ds1(r): push(r);a.emit(0x1F91)
    def load(r,off):
        mov(5,14)
        if off: a.emit(0x70F5,off)
        a.emit(0x2805|r<<4)
    def store(r,off):
        mov(5,14)
        if off: a.emit(0x70F5,off)
        a.emit(0x0A50|r)
    def negate(regs):
        for r in regs: a.emit(0x77F0|r,65535)
        a.emit(0x70F0|regs[0],1)
        for r in regs[1:]: a.emit(0x71F0|r,0)
    saved=(1,*range(3,15))
    def enter():
        for r in saved: push(r)
        a.emit(0x1F10,0x1F11,0x1F00,*select_workspace(workspace_bank))
    def leave():
        a.emit(0x1F80,0x1F91,0x1F90)
        for r in reversed(saved): pop(r)
        a.emit(0xC620)
    def geometry(error):
        cmpi(10,0x1ff);a.ajmp(error,0xA)
        cmpi(11,0x8000);a.ajmp(error,5)
        cmpi(11,0xeffe);a.ajmp(error,0xA)
        mov(0,11);a.emit(0x74F0,1);a.ajmp(error,2)
    def save_sum():
        for r in (3,2,1,0): push(r)
    def accumulate():
        for r in (4,5,6,7): pop(r)
        a.emit(0x1004,0x1115,0x1126,0x1137)

    a.label("slot")
    enter()
    a.emit(0x38A3,0x38B3,0x38C3,0x38D3,0x28E3)
    geometry("invalid_slot")
    ds1(10)
    mov(5,11);a.emit(0x2805)
    cmpi(0,0xf00);a.ajmp("invalid_slot",0xA)
    mov(1,0);a.emit(0x74F1,255);a.ajmp("invalid_slot",2)
    a.emit(0x72F0,256,0x74F0,4095,0x0A50)
    # Persist descriptor fields before the matrix clobbers temporary regs.
    store(10,0);store(11,2);store(0,4);store(12,6);store(13,8)
    a.emit(0x100B,0x5002)
    store(0,10)
    mov(13,0)
    imm(0,0);store(0,14)
    a.emit(0x1F00,0x385F,0x74F5,0xffef,0x58F5,0x1F80)
    # Zero slots still advance the real ring and emit its older tail.
    mov(7,12);imm(8,64);imm(2,0)
    a.label("scan_zero")
    a.emit(0x3817,0x1521,0x5281);a.ajmp("scan_zero",2)
    cmpi(2,0);a.ajmp("dct_nonzero",2)
    mov(7,13);imm(8,128);imm(0,0)
    a.label("zero_chunk")
    a.emit(0x1A70,0x5281);a.ajmp("zero_chunk",2)
    a.ajmp("window_begin")
    a.label("dct_nonzero")
    if fast_core:
        # Existing slot scratch stays at 0..31; descriptor32..39 and the
        # explicitly owned fast-DCT scratch follow. This is a guest call,
        # not a host function or hidden extra heap allocation.
        store(12,32);load(0,0);store(0,34);load(0,10);store(0,36)
        mov(0,14);a.emit(0x70f0,40);store(0,38)
        mov(3,14);a.emit(0x70f3,32)
        target=fast_core["entries"]["dct32"];a.emit(0xbd00|target>>16,target&65535)
        cmpi(2,0);a.ajmp("invalid_slot",2);a.ajmp("window_begin")
    else:
        # Explicit matrix baseline; fast builds do not generate this code.
        a.emit(0x6811,table_address>>15)
        imm(9,0x8000|(table_address&0x7fff));imm(0,32);store(0,12)
        a.label("dct_row")
        push(12);imm(8,32)
        for r in range(4): imm(r,0)
        a.label("dct_term")
        save_sum()
        mov(7,12);a.emit(0x3807,0x3817);mov(12,7)
        mov(5,9);a.emit(0x38A5,0x38B5);mov(9,5)
        a.acall("signed_product")
        accumulate()
        a.emit(0x5281);a.ajmp("dct_term",2)
        pop(12)
        # Q23*Q26 >>32 = Q17. Whole input width stays within +/-2^30.
        load(0,0);ds1(0)
        mov(5,13);a.emit(0x1A52,0x0A53,0x50D4)
        a.emit(0x6811,table_address>>15)
        load(0,12);a.emit(0x5201);store(0,12)
        cmpi(0,16);a.ajmp("dct_count",2)
        a.emit(0x70FD,68) # skip V16..32 before unique rows V33..48
        a.label("dct_count")
        cmpi(0,0);a.ajmp("dct_row",2)
        load(0,0);ds1(0)
        load(7,10);mov(5,7);mov(6,7);a.emit(0x70F6,128);imm(8,16)
        a.label("mirror_negative")
        a.emit(0x3805,0x3815)
        negate((0,1))
        a.emit(0x1A60,0x0A61,0x5266,0x5281);a.ajmp("mirror_negative",2)
        mov(5,7);a.emit(0x70F5,64);imm(0,0);a.emit(0x1A50,0x0A50)
        mov(5,7);a.emit(0x70F5,132);mov(6,7);a.emit(0x70F6,252);imm(8,15)
        a.label("mirror_positive")
        a.emit(0x3805,0x3815,0x1A60,0x0A61,0x5266,0x5281);a.ajmp("mirror_positive",2)
    a.label("window_begin")
    load(12,2);a.emit(0x50C2)
    load(13,8)
    imm(9,0x8000|(window_address&0x7fff));a.emit(0x6811,window_address>>15)
    imm(0,32);store(0,12)
    a.label("pcm_sample")
    imm(8,16)
    for r in range(4): imm(r,0)
    a.label("window_term")
    save_sum()
    mov(5,9);a.emit(0x3805,0x38A5,0x38B5);mov(9,5)
    load(2,4);a.emit(0x1002,0x74F0,4095,0x100C);mov(6,0)
    load(0,0);ds1(0)
    a.emit(0x3806,0x2816,0x6811,window_address>>15)
    a.acall("signed_product")
    accumulate()
    a.emit(0x5281);a.ajmp("window_term",2)
    # Round Q33 to PCM15 then clip, retaining the 64-bit sum until now.
    a.emit(0x70F1,2,0x71F2,0,0x71F3,0)
    cmpi(3,0x8000);a.ajmp("pcm_negative",6)
    cmpi(3,0);a.ajmp("clip_positive",2)
    cmpi(2,2);a.ajmp("clip_positive",6)
    a.ajmp("pcm_pack")
    a.label("pcm_negative")
    cmpi(3,65535);a.ajmp("clip_negative",2)
    cmpi(2,0xfffe);a.ajmp("clip_negative",5)
    a.label("pcm_pack")
    mov(0,1);a.emit(0x4D02,0x4C2E,0x1502);a.ajmp("pcm_store")
    a.label("clip_positive")
    imm(0,32767);a.ajmp("clip_count")
    a.label("clip_negative")
    imm(0,32768)
    a.label("clip_count")
    load(1,14);a.emit(0x5011);store(1,14)
    a.label("pcm_store")
    mov(5,13);a.emit(0x1A50);mov(13,5)
    load(0,12);a.emit(0x5201);store(0,12)
    cmpi(0,0);a.ajmp("pcm_sample",2)
    imm(0,32);imm(2,0);a.ajmp("slot_return")
    a.label("invalid_slot")
    imm(0,0);imm(2,2)
    a.label("slot_return")
    leave()

    a.label("signed_product")
    mov(4,0);a.emit(0x1541);a.ajmp("product_zero",1)
    mov(4,10);a.emit(0x154B);a.ajmp("product_zero",1)
    # Tail-call the full signed helper; keep the caller's RETC frame.
    a.emit(0xAC00,math_core["entries"]["multiply_signed"]&65535)
    a.label("product_zero")
    for r in range(4): imm(r,0)
    a.emit(0xC600)

    a.label("granule")
    enter()
    mov(5,3);a.emit(0x70F5,8,0x28E5)
    mov(5,14);a.emit(0x70F5,16);mov(14,5);imm(4,5)
    a.label("copy_descriptor")
    a.emit(0x3803,0x1A50,0x5241);a.ajmp("copy_descriptor",2)
    imm(8,18)
    a.label("granule_slot")
    mov(3,14);a.emit(0xBD00|address>>16,a.labels["slot"]&65535)
    cmpi(2,0);a.ajmp("granule_failed",2)
    mov(5,14);a.emit(0x5054,0x2805,0x70F0,128,0x1A50,0x2805,0x70F0,64,0x0A50,0x5281)
    a.ajmp("granule_slot",2)
    imm(0,576);a.ajmp("granule_return")
    a.label("granule_failed")
    imm(0,0)
    a.label("granule_return")
    leave()

    a.label("reset")
    enter()
    a.emit(0x38A3,0x28B3)
    geometry("invalid_reset")
    ds1(10);mov(5,11);imm(4,2049);imm(0,0)
    a.label("clear_state")
    a.emit(0x1A50,0x5241);a.ajmp("clear_state",2)
    imm(0,1024);imm(2,0);a.ajmp("reset_return")
    a.label("invalid_reset")
    imm(0,0);imm(2,2)
    a.label("reset_return")
    leave()
    code=struct.pack(f"<{len(a.words)}H",*a.finish())
    assert address+len(code)<=0x202000
    code_span(address,code)
    return {"code":code,"code_address":address,"tables":tables(table_address,fast=bool(fast_core)),"table_address":table_address,
            "entries":a.labels,"state_bytes":STATE_BYTES,"work_bytes":40+fast_core["work_bytes"] if fast_core else WORK_BYTES,
            "v_fracbits":V_FRACBITS,"fast_dct32":bool(fast_core)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();core=build()
    args.output.mkdir(parents=True,exist_ok=False)
    manifest={k:v for k,v in core.items() if k not in ("code","tables")}
    for key in ("code","tables"):
        (args.output/(key+".bin")).write_bytes(core[key])
        manifest[key+"_bytes"]=len(core[key]);manifest[key+"_sha256"]=hashlib.sha256(core[key]).hexdigest()
    manifest.update(pcm_format="s16le",factory_rom_patch=False,license="GPL-2.0-or-later")
    (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(manifest,indent=2))


if __name__=="__main__": main()
