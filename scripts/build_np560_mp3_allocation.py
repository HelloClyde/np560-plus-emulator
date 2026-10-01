#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Obtain/pin/release MP3 RAM through the original movable-object allocator.

R3 -> nine near words in caller DS0: handle, allocated bytes, physical
segment/offset, workspace bank, synthesis bank, left/right synthesis pointers,
workspace offset. Pass the workspace bank:offset as DS0:R3 to the PCM driver.
The descriptor must be separately owned, aligned, and initially zero. It
must remain outside the acquired block and all allocations the heap moves.
No original shared-state address is invented here. The caller retains the
descriptor throughout the lease. It must serialize use/release with decode.

acquire: R0=real handle/R2=0; busy=6, allocation failure=1, invalid descriptor
geometry=2, invalid returned geometry=3, unstable placement after 3 tries=4.
Failures leave the empty descriptor unchanged and release any acquired handle.
release: deferred free + unlock, clear descriptor, R0=0/R2=0; empty is a no-op.
Preserve R1,R3..14, DS, SOCR. No heap reset, machine reservation or host calls.

This NEW software adapter uses factory functions, not recovered mask-ROM bytes.
Its 20:E000 diagnostic link still requires production ROM placement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_np560_mp3_decoder import WORKSPACE_BYTES
from np560_assembler import _DMCUAssembler
from np560_mp3_link import code_span

ADDRESS, DESCRIPTOR_BYTES, SYNTHESIS_BYTES = 0x20E000, 18, 8196
# Own the boundary words too: the decoder's normal buffer checks must never
# write a guard into a neighbouring original heap header. Each history has
# a two-byte margin before/after it; the near workspace has a trailing word.
WORK_STORAGE, SYN_STORAGE = WORKSPACE_BYTES+2, SYNTHESIS_BYTES+8
ALLOC, LOCK, FREE, UNLOCK = 0x2577DA, 0x315300, 0x303A56, 0x308B26
HANDLE, ALLOCATED, SEGMENT, OFFSET, WORK_BANK, SYN_BANK, LEFT, RIGHT, WORK_OFFSET = range(0,18,2)


def build(address=ADDRESS, *, reserve_synthesis=True):
    a=_DMCUAssembler(address)
    def imm(r,v): a.emit(0x68F0|r,v&65535)
    def mov(d,s): a.emit(0x0800|d<<4|s)
    def cmpi(r,v): a.emit(0x76F0|r,v&65535)
    def caller_bank(): a.emit(0x58FD,0x1F90)
    def field(off):
        caller_bank();mov(1,14)
        if off: a.emit(0x70F1,off)
    def get(r,off): field(off);a.emit(0x2801|r<<4)
    def put(r,off): field(off);a.emit(0x0A10|r)
    def native(target,arg):
        # Do not depend on undocumented scratch-register preservation in a
        # factory child. Only the actual R0:R1 result escapes this wrapper.
        for r in range(3,15): a.emit(0x58F0|r)
        a.emit(0x58F0|arg,0xBD00|target>>16,target&65535,0x50F2)
        for r in reversed(range(3,15)): a.emit(0x380F|r<<4)
    def enter():
        for r in (1,*range(3,15)): a.emit(0x58F0|r)
        a.emit(0x1F10,0x1F11,0x1F00,0x1F10,0x38DF)
        mov(14,3);cmpi(14,0x8000-DESCRIPTOR_BYTES);a.ajmp("invalid",0xA)
        mov(0,14);a.emit(0x74F0,1);a.ajmp("invalid",2)
    a.label("acquire");enter()
    get(0,HANDLE);cmpi(0,0);a.ajmp("busy",2)
    imm(4,WORK_STORAGE+(SYN_STORAGE if reserve_synthesis else 0));imm(3,3)
    a.label("allocate")
    cmpi(3,0);a.ajmp("unstable",1)
    a.emit(0x5231)
    native(ALLOC,4);cmpi(0,0);a.ajmp("no_memory",1)
    mov(5,0);native(LOCK,5);mov(6,0);mov(7,1)
    cmpi(6,0xff);a.ajmp("bad_geometry",0xA)
    mov(0,6);a.emit(0x1507);a.ajmp("bad_geometry",1)
    mov(0,7);a.emit(0x74F0,1);a.ajmp("bad_geometry",2)
    # Convert the original physical segment:offset into hardware DS bank.
    mov(8,6);a.emit(0x4C81);mov(0,7);a.emit(0x4D0F,0x1080)
    mov(2,7);a.emit(0x74F2,0x7fff)
    imm(9,0x8000);a.emit(0x1292)
    if not reserve_synthesis:
        # HLE-only: host codec owns synthesis history. Keep the complete near
        # workspace and guard, including actual compressed/PCM buffers.
        # If it crosses a bank, own the prefix as well via the real allocator.
        imm(12,WORK_STORAGE)
        cmpi(2,0x8000-WORK_STORAGE);a.ajmp("compact_ready",0xC)
        a.emit(0x5081);imm(2,0);a.emit(0x10C9)
        a.label("compact_ready")
        # Explicit absent pointers, never a borrowed or invented RAM region.
        imm(9,0);imm(10,0);imm(11,0);a.ajmp("layout_ready")
    # If the near workspace already fits at the returned pointer, do not
    # discard that space to align to the next bank. R2 is its base offset.
    cmpi(2,0x8000-WORK_STORAGE);a.ajmp("workspace_here",0xC)
    a.emit(0x5081);imm(2,0)
    # Otherwise use the bank boundary, placing history in the prefix where
    # possible. All margins and alignment bytes remain inside the lease.
    cmpi(9,SYN_STORAGE);a.ajmp("history_before",6)
    mov(12,9);a.emit(0x70FC,0x8000+SYN_STORAGE)
    a.ajmp("history_after")
    a.label("workspace_here")
    mov(12,9);a.emit(0x70FC,SYN_STORAGE)
    a.label("history_after")
    mov(9,8);a.emit(0x5091);imm(10,0x8002);imm(11,0x9008)
    a.ajmp("layout_ready")
    a.label("history_before")
    mov(12,9);a.emit(0x70FC,WORK_STORAGE)
    mov(9,8);a.emit(0x5291);mov(10,7);a.emit(0x75FA,0x8000,0x50A2)
    mov(11,10);a.emit(0x70FB,4102)
    a.label("layout_ready")
    for r in (8,9): cmpi(r,0x1ff);a.ajmp("bad_geometry",0xA)
    a.emit(0x16C4);a.ajmp("owned",0xC)
    # First learn the actual allocator-selected position, then resize via
    # its own free/allocate API. No guessed heap address or header edits.
    a.acall("drop_handle");mov(4,12);a.ajmp("allocate")
    a.label("owned")
    for off,r in ((HANDLE,5),(ALLOCATED,4),(SEGMENT,6),(OFFSET,7),
                  (WORK_BANK,8),(SYN_BANK,9),(LEFT,10),(RIGHT,11),(WORK_OFFSET,2)): put(r,off)
    mov(0,5);imm(2,0);a.ajmp("return")
    a.label("bad_geometry");a.acall("drop_handle");imm(2,3);a.ajmp("failure")

    a.label("release");enter()
    get(5,HANDLE);cmpi(5,0);a.ajmp("released",1)
    cmpi(5,255);a.ajmp("invalid",0xA)
    a.acall("drop_handle")
    imm(0,0)
    for off in range(0,DESCRIPTOR_BYTES,2): put(0,off)
    a.label("released");imm(0,0);imm(2,0);a.ajmp("return")
    a.label("drop_handle")
    # 303A56 marks a pinned object for deferred free; 308B26 releases its
    # pin, clears the handle bitmap, and invokes the original compactor.
    native(FREE,5);native(UNLOCK,5);a.emit(0xC600)
    for label,status in (("no_memory",1),("invalid",2),("unstable",4),("busy",6)):
        a.label(label);imm(2,status);a.ajmp("failure")
    a.label("failure");imm(0,0)
    a.label("return")
    a.emit(0x1F80,0x1F91,0x1F90)
    for r in reversed((1,*range(3,15))): a.emit(0x380F|r<<4)
    a.emit(0xC620)
    code=struct.pack(f"<{len(a.words)}H",*a.finish())
    code_span(address,code)
    return {"code":code,"code_address":address,"entries":a.labels,
            "descriptor_bytes":DESCRIPTOR_BYTES,"factory_rom_patch":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    core=build();(args.output/"allocation-code.bin").write_bytes(core["code"])
    manifest={k:v for k,v in core.items() if k!="code"}
    manifest.update(bytes=len(core["code"]),sha256=hashlib.sha256(core["code"]).hexdigest())
    (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(manifest,indent=2));return 0


if __name__=="__main__": raise SystemExit(main())
