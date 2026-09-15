#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Owned MP3 session: real heap lease -> ring decode -> caller's X0 PCM.

NEW internal ABI: DS0:R3 is a stable, separately owned SIZE-byte object.
The caller zeroes it and supplies CONFIG's original 13 initialization words.
create/reset/free_words/step/output/release keep all non-result registers.
output also accepts the original 4954 two far output arguments on the stack;
it writes the current pair, including zeroed B buffers before the first step.
The first successful step fills A, then B, publishing only after both copies.
Short/error/busy calls do not exchange buffers. reset clears both phases.

Only the known original X0 output contract is supported: four disjoint even
buffers inside 1600..7FFF, original 1000/0300 compressed ring. The fifth
far argument is retained but NOT appropriated as persistent private storage.
External buffers and this object must remain owned throughout the session.
The owner controls object lifetime; an atomic bounded-CRIT BUSY claim rejects
nested access/release. Far output arguments must not alias session storage.
The owner must stop/unregister stream callbacks before releasing the object.

R0=576/R2=0 for PCM; other successful commands return R0=0/R2=0, except
free_words. Ring errors retain codes 1..6; 7 busy/already open, 8 closed,
9 allocation failure, 10 initialization/reset core failure, 11 release
failure (DETAIL retained and the owner remains open for cleanup).
This is NOT an installed factory singleton, nor the original error-code ABI.
No private original RAM field, hardware reservation, host decoder or fake PCM.

player_step retains the explicit owner ABI but translates step's result for
the original 49F8 consumer: bit0=1 only for completed PCM, bit0=0 otherwise;
3346 is zero for PCM/short/busy and nonzero for a genuine decode failure.
The nonzero value is a new generic failure indication, NOT a recovered
factory numeric error. It does not supply the missing singleton resolver,
format callbacks, EOF ownership, or stop/exit cleanup.
"""
from __future__ import annotations

import struct

import build_np560_mp3_allocation as lease
import build_np560_mp3_decoder as decoder
from build_np560_mp3_ring import FORMAT_CHANGE as RING_FORMAT_CHANGE
from np560_assembler import _DMCUAssembler
from np560_mp3_link import code_span

ADDRESS,SIZE,CONFIG=0x20ec00,0x50,18
MAGIC,BUSY,PHASE,READY,STATUS,DETAIL,FORMAT_CHANGE=range(44,58,2)
OUTPUT=0x40
MAGIC_VALUE=0x534d
PCM_BYTES=1152


def build(address=ADDRESS,*,allocation,ring,pcm_copy=None,priming=False):
    a=_DMCUAssembler(address)
    def imm(r,v): a.emit(0x68f0|r,v&65535)
    def mov(d,s): a.emit(0x0800|d<<4|s)
    def cmpi(r,v): a.emit(0x76f0|r,v&65535)
    def owner_bank(): a.emit(0x58fd,0x1f90)
    def ptr(r,off):
        mov(r,14)
        if off: a.emit(0x70f0|r,off)
    def get(r,off): owner_bank();ptr(1,off);a.emit(0x2801|r<<4)
    def put(r,off):
        assert r!=1
        owner_bank();ptr(1,off);a.emit(0x0a10|r)
    def const(off,v): imm(0,v);put(0,off)
    def call(core,name):
        target=core["entries"][name];a.emit(0xbd00|target>>16,target&65535)
    def allocation_call(name): owner_bank();ptr(3,0);call(allocation,name)
    def core_bank():
        get(4,lease.WORK_BANK);get(3,lease.WORK_OFFSET);a.emit(0x58f4,0x1f90)
    def ring_call(name): core_bank();call(ring,name)
    saved=(1,*range(3,15))
    def enter():
        for r in saved: a.emit(0x58f0|r)
        a.emit(0x1f10,0x1f11,0x1f00,0x1f10,0x38df);mov(14,3)
        cmpi(14,0x8000-SIZE);a.ajmp("invalid",0xa)
        mov(0,14);a.emit(0x74f0,1);a.ajmp("invalid",2)
    def opened():
        get(0,MAGIC);cmpi(0,MAGIC_VALUE);a.ajmp("claimed_closed",2)
    def claim():
        owner_bank();ptr(1,BUSY)
        # CRIT's two-bit operand encodes 1..4 protected instructions.
        # Preload one, then protect load, compare, conditional jump, store.
        # On the busy branch its first result MOV exhausts the mask.
        # No interrupt may release the lease between our test and set.
        imm(4,1);a.emit(0x3f03,0x2801,0x76f0,0);a.ajmp("busy",2)
        a.emit(0x0a14)

    a.label("create");enter();claim()
    get(0,MAGIC);cmpi(0,0);a.ajmp("claimed_busy",2)
    get(0,lease.HANDLE);cmpi(0,0);a.ajmp("claimed_busy",2)
    for i in range(4):
        get(0,CONFIG+4*i);cmpi(0,0);a.ajmp("claimed_invalid",2)
        get(5,CONFIG+4*i+2)
        cmpi(5,0x1600);a.ajmp("claimed_invalid",5)
        cmpi(5,0x8000-PCM_BYTES);a.ajmp("claimed_invalid",0xa)
        mov(0,5);a.emit(0x74f0,1);a.ajmp("claimed_invalid",2)
        # The owner object cannot itself overlap an X0 output buffer.
        cmpi(13,0);a.ajmp(f"owner_clear_{i}",2)
        mov(6,14);a.emit(0x70f6,SIZE,0x1665);a.ajmp(f"owner_clear_{i}",0xc)
        mov(6,5);a.emit(0x70f6,PCM_BYTES,0x166e);a.ajmp("claimed_invalid",0xa)
        a.label(f"owner_clear_{i}")
        for j in range(i):
            get(6,CONFIG+4*j+2);a.emit(0x1656)
            a.ajmp(f"order_{i}_{j}",5);a.emit(0x1256);a.ajmp(f"gap_{i}_{j}")
            a.label(f"order_{i}_{j}");a.emit(0x1265);mov(5,6)
            a.label(f"gap_{i}_{j}");cmpi(5,PCM_BYTES);a.ajmp("claimed_invalid",5)
            get(5,CONFIG+4*i+2)
    for off,value in ((CONFIG+20,0),(CONFIG+22,0x1000),(CONFIG+24,0x300)):
        get(0,off);cmpi(0,value);a.ajmp("claimed_invalid",2)
    allocation_call("acquire");cmpi(2,0);a.ajmp("allocation_failed",2)
    for source,dest in ((lease.SYN_BANK,decoder.SYN_BANK),
                        (lease.LEFT,decoder.SYN_LEFT),(lease.RIGHT,decoder.SYN_RIGHT)):
        get(6,source);core_bank();mov(1,3);a.emit(0x70f1,dest,0x0a16)
    imm(0,0x1000);ring_call("reset");cmpi(2,0);a.ajmp("create_failed",2)
    const(MAGIC,MAGIC_VALUE);a.ajmp("reset_outputs")

    a.label("reset");enter();claim();opened()
    imm(0,0x1000);ring_call("reset");cmpi(2,0);a.ajmp("reset_failed",2)
    a.label("reset_outputs")
    for i in range(4):
        get(5,CONFIG+4*i+2);a.emit(0x75f5,0x8000,0x6811,0)
        imm(1,576);imm(0,0)
        a.label(f"clear_{i}");a.emit(0x1a50,0x5211);a.ajmp(f"clear_{i}",2)
    const(PHASE,1);const(READY,0);const(DETAIL,0);const(FORMAT_CHANGE,0)
    a.acall("publish");imm(0,0);imm(2,0);a.ajmp("mutation_return")

    a.label("free_words");enter();claim();opened();ring_call("free_words");a.ajmp("mutation_return")
    a.label("step");enter();claim();opened()
    ring_call("step");cmpi(2,0);a.ajmp("step_failed",2)
    if priming:
        # v6 can own decoded PCM without publishing it during startup.
        # Translate this to the existing nonfatal/no-output public result.
        cmpi(0,0);a.ajmp("priming_no_pcm",1)
    cmpi(0,576);a.ajmp("unexpected_core",2)
    get(12,PHASE);a.emit(0x77fc,1)
    if pcm_copy is not None:
        # Optional HLE of OUR reconstructed ROM's software copy only.
        # The caller owns BUSY; both destination buffers must finish before
        # the unchanged PHASE/READY publication and original callbacks.
        owner_bank();ptr(3,0);mov(0,12)
        a.emit(0xbd00|pcm_copy>>16,pcm_copy&65535)
        cmpi(2,0);a.ajmp("step_failed",2)
        cmpi(0,576);a.ajmp("unexpected_core",2)
    else:
        for channel in range(2):
            # Read current phase's destination without publishing it yet.
            owner_bank();ptr(5,CONFIG+8*channel+2);mov(6,12);a.emit(0x4c62,0x1056,0x2875)
            a.emit(0x75f7,0x8000,0x6811,0);core_bank()
            mov(6,3);a.emit(0x70f6,decoder.PCM[channel]);imm(1,576)
            a.label(f"copy_{channel}");a.emit(0x3806,0x1a70,0x5211);a.ajmp(f"copy_{channel}",2)
    put(12,PHASE);const(READY,1);const(DETAIL,0)
    core_bank();mov(1,3);a.emit(0x70f1,RING_FORMAT_CHANGE,0x2801);put(0,FORMAT_CHANGE)
    a.acall("publish");imm(0,576);imm(2,0);a.ajmp("mutation_return")

    a.label("output");enter();claim();opened()
    # 13 saved GPRs + DS0/DS1/SOCR, then the 4-byte SCALL return frame.
    mov(11,15)
    for ch in range(2):
        arg=36+ch*4
        a.emit(0x786b,arg,0x787b,arg+2)
        cmpi(6,0xff);a.ajmp("claimed_invalid",0xa)
        cmpi(7,0xfffc);a.ajmp("claimed_invalid",0xa)
        mov(0,7);a.emit(0x74f0,1);a.ajmp("claimed_invalid",2)
    for ch in range(2):
        arg=36+ch*4
        a.emit(0x786b,arg,0x787b,arg+2)
        mov(0,7);a.emit(0x4d0f,0x4c61,0x1060,0x58f6,0x1f91,0x75f7,0x8000)
        for off in (OUTPUT+ch*4,OUTPUT+ch*4+2): get(0,off);a.emit(0x1a70)
    imm(0,0);imm(2,0);a.ajmp("mutation_return")

    a.label("release");enter();claim()
    get(0,MAGIC);cmpi(0,0);a.ajmp("already_closed",1)
    cmpi(0,MAGIC_VALUE);a.ajmp("claimed_invalid",2)
    if "release" in ring["entries"]:
        ring_call("release");cmpi(2,0);a.ajmp("release_failed",2)
    const(MAGIC,0);allocation_call("release")
    cmpi(2,0);a.ajmp("release_failed",2)
    const(READY,0);const(DETAIL,0);const(FORMAT_CHANGE,0)
    for off in range(OUTPUT,OUTPUT+8,2): const(off,0)
    imm(0,0);imm(2,0);a.ajmp("mutation_return")
    a.label("already_closed");imm(0,0);imm(2,0);a.ajmp("mutation_return")

    a.label("allocation_failed");put(2,DETAIL);imm(0,0);imm(2,9);a.ajmp("mutation_return")
    a.label("create_failed");put(2,DETAIL)
    if "release" in ring["entries"]:
        ring_call("release");cmpi(2,0);a.ajmp("release_failed",2)
    allocation_call("release")
    cmpi(2,0);a.ajmp("release_failed",2)
    imm(2,10);imm(0,0);a.ajmp("mutation_return")
    a.label("reset_failed");put(2,DETAIL);const(READY,0);imm(2,10);imm(0,0);a.ajmp("mutation_return")
    a.label("release_failed");put(2,DETAIL);const(MAGIC,MAGIC_VALUE);imm(2,11);imm(0,0);a.ajmp("mutation_return")
    a.label("unexpected_core");imm(2,6)
    if priming:
        a.ajmp("step_failed")
        a.label("priming_no_pcm");imm(2,1)
    a.label("step_failed");put(2,DETAIL);imm(0,0);a.ajmp("mutation_return")
    for name,status in (("claimed_invalid",2),("claimed_busy",7),("claimed_closed",8)):
        a.label(name);imm(0,0);imm(2,status);a.ajmp("mutation_return")
    a.label("mutation_return")
    # Publish status BEFORE dropping ownership; a nested caller must never
    # have its newer status overwritten by our post-unlock epilogue.
    put(2,STATUS);imm(4,0);put(4,BUSY);a.ajmp("return")
    for name,status in (("invalid",2),("busy",7)):
        a.label(name);imm(0,0);imm(2,status);a.ajmp("return")
    a.label("return")
    a.emit(0x1f80,0x1f91,0x1f90)
    for r in reversed(saved): a.emit(0x380f|r<<4)
    a.emit(0xc620)

    a.label("publish")
    get(6,PHASE);a.emit(0x4c62)
    for ch in range(2):
        owner_bank();ptr(5,CONFIG+8*ch);a.emit(0x1056)
        for off in (OUTPUT+ch*4,OUTPUT+ch*4+2): a.emit(0x3805);put(0,off)
    a.emit(0xc600)

    a.label("player_step")
    # Do not leak internal R0=576 (whose bit0 is ZERO) to 16:E89C. The
    # original BMOVN would otherwise treat every successful granule as an
    # exhausted decoder and enter its fade/stop path. Keep the core's R2
    # detail for diagnostics; the PRG consumes only R0 bit0 and 3346 here.
    a.emit(0x58f1)
    target=a.labels["step"];a.emit(0xbd00|target>>16,target&65535)
    imm(1,0)
    cmpi(2,0);a.ajmp("player_no_pcm",2)
    cmpi(0,576);a.ajmp("player_failure",2)
    imm(0,1);a.ajmp("player_return")
    a.label("player_no_pcm")
    cmpi(2,1);a.ajmp("player_empty",1)
    cmpi(2,7);a.ajmp("player_empty",1)
    a.label("player_failure");imm(1,1)
    a.label("player_empty");imm(0,0)
    a.label("player_return")
    a.emit(0x3f10,0xa8f1,0x3346,0x381f,0xc620)
    words=a.finish()
    windows=[i for i,w in enumerate(words) if w==0x3f03]
    assert len(windows)==6
    for i in windows:
        assert words[i-2:i]==[0x68f4,1]
        assert words[i+1:i+7]==[0x2801,0x76f0,0,0xac02,a.labels["busy"]&65535,0x0a14]
    code=struct.pack(f"<{len(words)}H",*words);code_span(address,code)
    return {"code":code,"code_address":address,"entries":a.labels,
            "object_bytes":SIZE,"factory_player_connected":False}
