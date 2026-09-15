#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native Layer III IMDCT/window/overlap/frequency inversion; NOT PCM.

transform: R3 -> {block_type 0..3, X18_Q28, Z36_Q23}. Short inputs are
interleaved X[3*k+window] (the existing FFmpeg-layout reorder), not
libmad's window-major layout. A fused Q28 cosine/window matrix avoids
unwindowed 32-bit overflow. Signed 64-bit dots -> arithmetic >>33 ->
Q23, leaving headroom for full-width Q28 inputs AND inter-block overlap.
R0=36,R2=0, or R0=0,R2=2 invalid type without output mutation.

hybrid: R3 -> {rate 0..8, block_type, mixed 0/1, X576_Q28,
samples576_Q23, overlap576_Q23, workspace160bytes}. Output sample[t][sb]
is time-major; persistent overlap[sb][t] is subband-major. First 2/4
subbands of mixed blocks use normal long transforms (4 only at 8 kHz).
Odd time samples of odd subbands are inverted AFTER overlap addition;
stored overlap is never inverted. R0=576,R2=0; geometry error=2 no
mutation; malformed prior overlap causing overflow=3 (reject partial).

reset: R3 -> one channel's overlap576_Q23; zero it, R0=576,R2=0.
All public entries preserve R1,R3..14, DS and SOCR. Buffers/work/stack/
descriptor must be aligned, allocated and disjoint in near DS0=0.
No history injection, host DSP, fake PCM or original ROM replacement.
Fused matrix rounding/Q23 is explicit, not libmad bit-for-bit rounding.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

from build_np560_mp3_antialias import build as build_math
from np560_assembler import _DMCUAssembler
from np560_mp3_workspace import select_workspace
from np560_mp3_link import code_span, near_table

ADDRESS, TABLE_ADDRESS = 0x20B800, 0x219870
OUTPUT_FRACBITS, WORK_BYTES, MATRIX_BYTES = 23, 160, 36*18*4


def matrices():
    result = []
    for block in range(4):
        matrix = []
        for n in range(36):
            row = []
            for k in range(18):
                if block == 2:
                    t = n-6-6*(k%3)
                    value = (math.cos(math.pi/24*(2*t+7)*(2*(k//3)+1))
                             * math.sin(math.pi/12*(t+.5))) if 0 <= t < 12 else 0.
                else:
                    window = math.sin(math.pi/36*(n+.5))
                    if block == 1 and n >= 18:
                        window = 1. if n < 24 else math.sin(math.pi/12*(n-18+.5)) if n < 30 else 0.
                    if block == 3 and n < 18:
                        window = 0. if n < 6 else math.sin(math.pi/12*(n-6+.5)) if n < 12 else 1.
                    value = math.cos(math.pi/72*(2*n+19)*(2*k+1))*window
                row.append(round(value*(1<<28)))
            # Full signed input width cannot overflow a signed 64-bit
            # accumulator; Q23 windowed samples stay strictly within
            # +/-2^30, so two legitimately generated overlaps fit int32.
            assert sum(abs(v) for v in row) < 16*(1<<28)
            matrix.append(row)
        result.append(matrix)
    return result


def build(address=ADDRESS, workspace_bank=0, *, table_address=TABLE_ADDRESS, math_core=None):
    a = _DMCUAssembler(address)
    math_core = math_core or build_math(workspace_bank=workspace_bank)
    assert address>>16 == math_core["entries"]["multiply_signed"]>>16, "hybrid RETC math helper must share CS"
    def imm(r,v): a.emit(0x68F0|r,v&65535)
    def mov(d,s): a.emit(0x0800|d<<4|s)
    def cmpi(r,v): a.emit(0x76F0|r,v&65535)
    def push(r): a.emit(0x58F0|r)
    def pop(r): a.emit(0x380F|r<<4)
    def negate(regs):
        for r in regs: a.emit(0x77F0|r,65535)
        a.emit(0x70F0|regs[0],1)
        for r in regs[1:]: a.emit(0x71F0|r,0)
    saved = (1,*range(3,15))
    def enter():
        for r in saved: push(r)
        a.emit(0x1F10,0x1F11,0x1F00,*select_workspace(workspace_bank))
    def leave():
        a.emit(0x1F80,0x1F91,0x1F90)
        for r in reversed(saved): pop(r)
        a.emit(0xC620)

    a.label("transform")
    enter()
    a.emit(0x3803,0x38C3,0x28D3)
    cmpi(0,3)
    a.ajmp("invalid_transform",0xA)
    # A zero input subband still yields real zero windowed output. The
    # hybrid caller MUST consume it to emit/clear the previous tail.
    mov(7,12)
    imm(8,36)
    imm(2,0)
    a.label("scan_zero")
    a.emit(0x3817,0x1521,0x5281)
    a.ajmp("scan_zero",2)
    cmpi(2,0)
    a.ajmp("nonzero_transform",2)
    mov(7,13)
    imm(8,72)
    imm(0,0)
    a.label("zero_transform")
    a.emit(0x1A70,0x5281)
    a.ajmp("zero_transform",2)
    a.ajmp("transform_success")
    a.label("nonzero_transform")
    # Clear accumulator saturation while preserving the full SOCR.
    a.emit(0x1F00,0x385F,0x74F5,0xFFEF,0x58F5,0x1F80,0x6811,table_address>>15)
    for block in range(3):
        cmpi(0,block)
        a.ajmp(f"matrix_{block}",1)
    imm(9,0x8000|(table_address+3*MATRIX_BYTES)&0x7fff)
    a.ajmp("matrix_ready")
    for block in range(3):
        a.label(f"matrix_{block}")
        imm(9,0x8000|(table_address+block*MATRIX_BYTES)&0x7fff)
        a.ajmp("matrix_ready")
    a.label("matrix_ready")
    imm(14,36)
    a.label("row")
    push(12)
    imm(8,18)
    for r in range(4): imm(r,0)
    a.label("term")
    for r in (3,2,1,0): push(r)
    mov(7,12)
    a.emit(0x3807,0x3817)
    mov(12,7)
    mov(5,9)
    a.emit(0x38A5,0x38B5)
    mov(9,5)
    mov(4,10)
    a.emit(0x154B)
    a.ajmp("zero_product",1)
    mov(4,0)
    a.emit(0x1541)
    a.ajmp("zero_product",1)
    a.emit(0xBC00,math_core["entries"]["multiply_signed"]&65535)
    a.ajmp("accumulate")
    a.label("zero_product")
    for r in range(4): imm(r,0)
    a.label("accumulate")
    for r in (4,5,6,7): pop(r)
    a.emit(0x1004,0x1115,0x1126,0x1137,0x5281)
    a.ajmp("term",2)
    pop(12)
    # Signed 64-bit >>33, producing Q23. The row norm proof above means
    # neither this packing nor later valid overlap needs saturation.
    mov(0,2)
    a.emit(0x4D01)
    mov(4,3)
    a.emit(0x4C4F,0x1504)
    mov(1,3)
    a.emit(0x4D11)
    cmpi(3,0x8000)
    a.ajmp("packed",5)
    a.emit(0x75F1,0x8000)
    a.label("packed")
    mov(7,13)
    a.emit(0x1A70,0x1A71)
    mov(13,7)
    a.emit(0x52E1)
    a.ajmp("row",2)
    a.label("transform_success")
    imm(0,36)
    imm(2,0)
    a.ajmp("transform_return")
    a.label("invalid_transform")
    imm(0,0)
    imm(2,2)
    a.label("transform_return")
    leave()

    a.label("hybrid")
    enter()
    a.emit(0x3803,0x38A3,0x3893,0x38B3,0x38C3,0x38D3,0x28E3)
    for r,limit in ((0,8),(10,3),(9,1)):
        cmpi(r,limit)
        a.ajmp("invalid_hybrid",0xA)
    cmpi(10,2)
    a.ajmp("mixed_count",1)
    imm(9,32)
    a.ajmp("hybrid_ready")
    a.label("mixed_count")
    cmpi(9,0)
    a.ajmp("hybrid_ready",1)
    imm(9,2)
    cmpi(0,8)
    a.ajmp("hybrid_ready",2)
    imm(9,4)
    a.label("hybrid_ready")
    imm(8,0)
    a.label("subband")
    mov(0,10)
    cmpi(10,2)
    a.ajmp("block_ready",2)
    a.emit(0x1689)
    a.ajmp("block_ready",6)
    imm(0,0)
    a.label("block_ready")
    mov(3,14)
    a.emit(0x70F3,144)
    mov(5,3)
    a.emit(0x1A50,0x1A5B,0x0A5E,0xBD00|address>>16,a.labels["transform"]&65535)
    push(11)
    mov(3,14)
    mov(5,14)
    a.emit(0x70F5,72)
    mov(6,12)
    mov(7,13)
    imm(4,18)
    a.label("overlap")
    a.emit(0x3803,0x3813,0x2827,0x5072,0x28B7,0x5272)
    push(1)
    a.emit(0x1002,0x111B)
    pop(2)
    a.emit(0x172B,0x74F2,0x8000)
    a.ajmp("sum_ok",2)
    mov(2,11)
    a.emit(0x1721,0x74F2,0x8000)
    a.ajmp("overlap_error",2)
    a.label("sum_ok")
    mov(2,8)
    a.emit(0x74F2,1)
    a.ajmp("inversion_done",1)
    mov(2,4)
    a.emit(0x74F2,1)
    a.ajmp("inversion_done",1)
    cmpi(1,0x8000)
    a.ajmp("invert",2)
    cmpi(0,0)
    a.ajmp("overlap_error",1)
    a.label("invert")
    negate((0,1))
    a.label("inversion_done")
    a.emit(0x1A60,0x1A61,0x70F6,124,0x3805,0x3815,0x1A70,0x1A71,0x5241)
    a.ajmp("overlap",2)
    pop(11)
    a.emit(0x70FB,72,0x50C4,0x70FD,72,0x5081)
    cmpi(8,32)
    a.ajmp("subband",5)
    imm(0,576)
    imm(2,0)
    a.ajmp("hybrid_return")
    a.label("overlap_error")
    pop(11)
    imm(0,0)
    imm(2,3)
    a.ajmp("hybrid_return")
    a.label("invalid_hybrid")
    imm(0,0)
    imm(2,2)
    a.label("hybrid_return")
    leave()

    a.label("reset")
    enter()
    imm(0,0)
    imm(4,1152)
    a.label("clear_overlap")
    a.emit(0x1A30,0x5241)
    a.ajmp("clear_overlap",2)
    imm(0,576)
    imm(2,0)
    leave()
    code = struct.pack(f"<{len(a.words)}H",*a.finish())
    code_span(address,code)
    table = struct.pack("<2592i",*(v for m in matrices() for row in m for v in row))
    near_table(table_address,table)
    return {"code":code,"code_address":address,"tables":table,"table_address":table_address,
            "entries":a.labels,"output_fracbits":OUTPUT_FRACBITS,"work_bytes":WORK_BYTES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    core = build()
    args.output.mkdir(parents=True,exist_ok=False)
    manifest = {k:v for k,v in core.items() if k not in ("code","tables")}
    for key in ("code","tables"):
        (args.output/(key+".bin")).write_bytes(core[key])
        manifest[key+"_bytes"] = len(core[key])
        manifest[key+"_sha256"] = hashlib.sha256(core[key]).hexdigest()
    manifest.update(pcm_produced=False,factory_rom_patch=False,license="GPL-2.0-or-later")
    (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(manifest,indent=2))


if __name__ == "__main__":
    main()
