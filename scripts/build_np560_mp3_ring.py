#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native original MP3 producer-ring -> resident Layer III PCM adapter.

NEW internal DS0:R3 ABI, sharing the PCM driver's allocated workspace.
The real PRG producer 16:E844 writes network-order words into 00:1000..15FF
and publishes its even cursor at 3340. No replacement producer or host
frame slicing is used. reset(R0=even initial ring pointer) clears decoder
histories, binds read/write cursors, and resets the byte/word position.
The factory caller may then set 3350/3352 to a seek position. Each commit
adds the words actually consumed to that full 32-bit word position; the
private relative byte count supplies only the half-word carry, not its base.
free_words returns capacity less occupied words and the caller's observed
two-word guard (02FE). step calls the original header parser 16:E45E and
then the native decoder; a pending MPEG1 granule consumes NO new input.

Opt-in deferred_input_retirement (HLE v3 compatibility contract): retain a
staged compressed frame until all of its PCM has been handed off. Publish
the completed frame's word position, but reclaim its ring window only AFTER
the next free_words calculation (or before the next frame if no query).
The query credit is conservative and repeated queries cannot double-retire.
This is a new software ownership policy, not a recovered factory layout.

Opt-in final_frame (HLE v5): at real producer EOF, a terminal packet may
omit ancillary bytes only if the codec validates all actual audio bits.
Even a complete terminal frame remains owned and unaccounted through its
last PCM handoff/query; the next step accounts and retires it exactly once.
This lets the original DTU interrupt switch to its final queued buffer
before the original input-exhausted path can publish END.

step: R0=576/R2=0 for newly produced PCM; R0=0 otherwise. R2=1 needs input,
2 invalid state/ring geometry, 3 rejected header (one byte skipped, filter
history reset), 4 unsupported layer, 5 CRC mismatch (no consumption),
6 decoder failure (complete frame consumed, subordinate status retained).
CRC covers header low16 + side information, with polynomial 8005/init FFFF.
Format changes clear filter history and publish FORMAT_CHANGE for the
future original-device callback adapter. It is NOT an implemented callback.

Direct shared writes use proved 3340,3350/3352,33E4 and parser input
51:2846/2848; the original parser retains its own outputs/side effects.
All new private fields live in the
leased workspace, not guessed factory RAM. Staging reuses SCRATCH before
the decoder's reorder stage; no extra unowned buffer is allocated.
Original 01:4804/49F8 entry wrappers, DAC ownership and teardown are pending.
"""
from __future__ import annotations

import struct
import build_np560_mp3_decoder as decoder
from np560_assembler import _DMCUAssembler
from np560_mp3_link import code_span

ADDRESS=0x20e400
READ,BYTES_LO,BYTES_HI,MAGIC,HDR0,HDR1,LENGTH,BODY_START,BODY_BYTES,SIDE_BYTES,CRC = range(0x40,0x56,2)
LAST_FORMAT,FORMAT_CHANGE,BITRATE,STATUS,CORE_STATUS=range(0x56,0x60,2)
RECLAIM_END,RECLAIM_PENDING,STAGED=range(0x60,0x66,2)
FINAL_INPUT=0x66  # v5 actual last packet at producer EOF; LENGTH is actual input.
MAGIC_VALUE=0x5247
RING_BEGIN,RING_END,RING_WORDS,WRITER=0x1000,0x1600,0x300,0x3340
PARSER=0x16e45e


def build(address=ADDRESS,core=None,*,deferred_input_retirement=False,final_frame=False):
    assert not final_frame or deferred_input_retirement
    core=core or decoder.build()
    a=_DMCUAssembler(address)
    def imm(r,v): a.emit(0x68f0|r,v&65535)
    def mov(d,s): a.emit(0x0800|d<<4|s)
    def cmpi(r,v): a.emit(0x76f0|r,v&65535)
    def ptr(r,off):
        mov(r,14)
        if off: a.emit(0x70f0|r,off)
    def get(r,off): ptr(1,off);a.emit(0x2801|r<<4)
    def put(r,off):
        assert r!=1
        ptr(1,off);a.emit(0x0a10|r)
    def const(off,v): imm(0,v);put(0,off)
    def native(entry):
        ptr(3,0);target=core["entries"][entry]
        a.emit(0xbd00|target>>16,target&65535)
    saved=(1,*range(3,15))
    def enter():
        for r in saved: a.emit(0x58f0|r)
        a.emit(0x1f10,0x1f11,0x1f00);mov(14,3)
        cmpi(14,0x8000-decoder.WORKSPACE_BYTES);a.ajmp("invalid",0xa)
        mov(4,14);a.emit(0x74f4,1);a.ajmp("invalid",2)
    def valid():
        get(0,MAGIC);cmpi(0,MAGIC_VALUE);a.ajmp("invalid",2)
    def ring_pointer(r,odd=False,error="invalid"):
        cmpi(r,RING_BEGIN);a.ajmp(error,5)
        cmpi(r,RING_END);a.ajmp(error,6)
        if not odd:
            mov(0,r);a.emit(0x74f0,1);a.ajmp(error,2)

    a.label("reset");enter();mov(5,0);ring_pointer(5)
    native("reset");cmpi(2,0);a.ajmp("invalid",2)
    imm(0,0)
    last_field=FINAL_INPUT if final_frame else STAGED if deferred_input_retirement else CORE_STATUS
    for off in range(READ,last_field+2,2): put(0,off)
    put(5,READ);const(LAST_FORMAT,65535);const(MAGIC,MAGIC_VALUE)
    a.emit(0x6811,0,0xa8f5,0x8000|WRITER)
    imm(0,0);a.emit(0xa8f0,0xb350,0xa8f0,0xb352)
    imm(2,0);a.ajmp("status_return")

    a.label("free_words");enter();valid();a.acall("available")
    # ceil(available bytes / 2) retains the partially consumed word too.
    a.emit(0x5061,0x4d61);imm(0,RING_WORDS-2);a.emit(0x1206)
    if deferred_input_retirement:
        # Return a safe credit from the current retained input window, THEN
        # reclaim its completed frame. The original E906 compares this
        # window with the consumption delta of the immediately preceding
        # decode. Repeated queries return the newly enlarged capacity.
        a.emit(0x58f0);a.acall("retire_input");a.emit(0x380f)
    imm(2,0);a.ajmp("return")

    a.label("step");enter();valid()
    get(0,decoder.PENDING);cmpi(0,0);a.ajmp("new_frame",1)
    const(FORMAT_CHANGE,0)
    native("next_granule");a.ajmp("decoded")
    a.label("new_frame")
    if deferred_input_retirement:
        if final_frame:
            # Coming back for another step acknowledges the previous PCM
            # handoff. Retain the real final input window through the prior
            # query, so E906 cannot publish END before the next DTU switch.
            get(0,FINAL_INPUT);cmpi(0,0);a.ajmp("no_final_to_finish",1)
            a.acall("finish_input")
            a.label("no_final_to_finish")
        # A caller is also allowed to decode again without querying space.
        a.acall("retire_input")
    a.acall("available")
    cmpi(6,4);a.ajmp("short",5)
    for off in (HDR0,HDR1): a.acall("ring_word");put(0,off)
    put(5,BODY_START)
    # The factory field parser is not a byte-stream sync scanner.
    get(0,HDR0);a.emit(0x74f0,0xffe0);cmpi(0,0xffe0);a.ajmp("bad_header",2)
    a.emit(0x6811,0xa2)
    get(0,HDR0);a.emit(0xa8f0,0xa846)
    get(0,HDR1);a.emit(0xa8f0,0xa848)
    # Real factory parser, with its original tables and global outputs.
    # Only R0 is assumed to survive as its result; private state is saved.
    for r in range(3,15): a.emit(0x58f0|r)
    a.emit(0x1f10,0x1f11,0x6810,0xa2,0x6811,0xa2,0xbd16,0xe45e,0x1f91,0x1f90)
    for r in reversed(range(3,15)): a.emit(0x380f|r<<4)
    cmpi(0,0);a.ajmp("bad_header",2)
    # Use the same byte loads as the verified parser contract. DMCU byte
    # lane order is not a host little-endian uint16 pair of version/layer.
    a.emit(0x6811,0xa2,0x99f0,0xa5c9)
    cmpi(0,3);a.ajmp("unsupported_layer",2)
    a.emit(0x99f4,0xa5c8,0x88f7,0xa5d0)
    cmpi(7,(RING_WORDS-2)*2);a.ajmp("invalid",0xa)
    if final_frame:
        const(FINAL_INPUT,0)
        a.emit(0x1676);a.ajmp("frame_length_ready",5)
        # The original producer publishes BIT89.7 only after its final
        # source buffers are exhausted. Read it; never manufacture EOF.
        # Preserve the ACTUAL byte count, not the nominal header length.
        a.emit(0x7c89,0x7070,0x74f0,1);a.ajmp("terminal_input",2)
        # A complete frame without EOF stays ordinary. A live partial
        # packet must wait for actual producer input, not use final decode.
        a.emit(0x1676);a.ajmp("short",0xa);a.ajmp("frame_length_ready")
        a.label("terminal_input")
        mov(7,6);const(FINAL_INPUT,1)
        a.label("frame_length_ready")
    else:
        a.emit(0x1676);a.ajmp("short",0xa)
    put(7,LENGTH)
    # Published headers come from actual ring data, never test-oracle fields.
    imm(0,1);cmpi(4,1);a.ajmp("lsf_ready",2);imm(0,0)
    a.label("lsf_ready");put(0,decoder.FRAME)
    get(0,HDR1);mov(8,0);a.emit(0x4d86,0x74f8,3)
    imm(9,2);cmpi(8,3);a.ajmp("channels_ready",2);imm(9,1)
    a.label("channels_ready");put(9,decoder.FRAME+2)
    a.emit(0x4d0a,0x74f0,3)
    cmpi(4,1);a.ajmp("rate_ready",1)
    a.emit(0x5003);cmpi(4,2);a.ajmp("rate_ready",1);a.emit(0x5003)
    a.label("rate_ready");put(0,decoder.FRAME+4)
    # Format identity is rate_index*4+nch; variable bitrate is not a reset.
    a.emit(0x4c02,0x1009);put(0,FORMAT_CHANGE)
    imm(0,0);cmpi(8,1);a.ajmp("mode_ready",2)
    get(0,HDR1);a.emit(0x4d04,0x74f0,3)
    a.label("mode_ready");put(0,decoder.MODE_EXT)
    a.emit(0x74f0,1);put(0,decoder.FRAME+6)
    imm(8,17);cmpi(4,1);a.ajmp("side_lsf",2)
    cmpi(9,1);a.ajmp("side_ready",1);imm(8,32);a.ajmp("side_ready")
    a.label("side_lsf");cmpi(9,1);a.ajmp("side_ready",2);imm(8,9)
    a.label("side_ready");put(8,SIDE_BYTES)
    a.emit(0x6811,0xa2,0x88f0,0xa5cc);put(0,BITRATE)
    get(0,HDR0);a.emit(0x74f0,1);imm(9,4);a.ajmp("header_length_ready",2);imm(9,6)
    a.label("header_length_ready")
    mov(0,8);a.emit(0x1009,0x1670);a.ajmp("short" if final_frame else "bad_header",5)
    mov(0,7);a.emit(0x1209);put(0,BODY_BYTES)
    a.emit(0x1208);put(0,decoder.FRAME+8)
    get(5,BODY_START);cmpi(9,6);a.ajmp("crc_ready",2)
    a.acall("ring_word");put(0,CRC);put(5,BODY_START)
    imm(4,65535);get(0,HDR1);imm(1,16);a.acall("crc_bits")
    a.label("crc_side")
    a.acall("ring_byte");a.emit(0x4c08);imm(1,8);a.acall("crc_bits")
    a.emit(0x5281);a.ajmp("crc_side",2)
    get(0,CRC);a.emit(0x1640);a.ajmp("bad_crc",2)
    a.label("crc_ready")
    # History cannot be carried across different sample/channel geometry.
    get(4,FORMAT_CHANGE);get(0,LAST_FORMAT);a.emit(0x1640)
    a.ajmp("same_format",1)
    native("reset");cmpi(2,0);a.ajmp("core_failed",2)
    put(4,LAST_FORMAT);const(FORMAT_CHANGE,1);a.ajmp("stage")
    a.label("same_format");const(FORMAT_CHANGE,0)
    a.label("stage")
    get(5,BODY_START);get(8,BODY_BYTES);ptr(7,decoder.SCRATCH)
    a.label("stage_pair")
    a.acall("ring_byte");mov(9,0);a.emit(0x4c98,0x5281)
    a.ajmp("stage_last",1)
    a.acall("ring_byte");a.emit(0x1590,0x5281)
    a.label("stage_last");a.emit(0x1a79)
    cmpi(8,0);a.ajmp("stage_pair",2)
    # Complete source was copied into leased scratch before any cursor is
    # published; subsequent native reorder may reuse this very same area.
    if deferred_input_retirement:
        put(5,RECLAIM_END);const(STAGED,1)
    else:
        get(6,LENGTH);a.acall("commit")
    a.emit(0x1f10,0x380f);put(0,decoder.INPUT)
    ptr(0,decoder.SCRATCH);a.emit(0x75f0,0x8000);put(0,decoder.INPUT+2)
    const(decoder.INPUT+4,0);const(decoder.INPUT+6,0)
    get(0,BODY_BYTES);a.emit(0x4c03);put(0,decoder.INPUT+8)
    get(0,BITRATE);a.emit(0x6811,0,0xa8f0,0xb3e4)
    native("decode_frame")
    a.label("decoded");cmpi(2,0);a.ajmp("core_failed",2)
    if deferred_input_retirement:
        a.emit(0x58f0,0x58f2)
        get(0,decoder.PENDING);cmpi(0,0);a.ajmp("input_still_pending",2)
        if final_frame:
            # Final PCM is queued, not yet consumed. Keep this ACTUAL input
            # occupied (and unaccounted) until the next step, never invent
            # a guard byte or return fake space to suppress original END.
            get(0,FINAL_INPUT);cmpi(0,0);a.ajmp("input_still_pending",2)
        a.acall("finish_input")
        a.label("input_still_pending");a.emit(0x382f,0x380f)
    a.ajmp("status_return")
    a.label("core_failed");put(2,CORE_STATUS)
    if deferred_input_retirement:
        a.acall("finish_input")
    imm(2,6);imm(0,0);a.ajmp("status_return")
    a.label("bad_header")
    get(5,READ);a.acall("ring_byte");imm(6,1);a.acall("commit")
    native("reset");const(LAST_FORMAT,65535)
    imm(2,3);imm(0,0);a.ajmp("status_return")
    for label,status in (("short",1),("unsupported_layer",4),("bad_crc",5)):
        a.label(label);imm(2,status);imm(0,0);a.ajmp("status_return")
    a.label("invalid");imm(2,2);imm(0,0);a.ajmp("return")
    a.label("status_return");put(2,STATUS)
    a.label("return")
    a.emit(0x1f80,0x1f91,0x1f90)
    for r in reversed(saved): a.emit(0x380f|r<<4)
    a.emit(0xc620)

    a.label("available")
    get(5,READ);ring_pointer(5,True,"available_invalid")
    a.emit(0x6811,0,0x88f6,0x8000|WRITER);ring_pointer(6,error="available_invalid")
    a.emit(0x1265);a.ajmp("available_nonnegative",6)
    a.emit(0x70f6,RING_END-RING_BEGIN)
    a.label("available_nonnegative")
    cmpi(6,(RING_WORDS-2)*2);a.ajmp("available_invalid",0xa)
    a.emit(0xc600)
    a.label("available_invalid");a.emit(0x50f2);a.ajmp("invalid")
    a.label("ring_word")
    a.acall("ring_byte");a.emit(0x4c08,0x58f0)
    a.acall("ring_byte");a.emit(0x383f,0x1503,0xc600)
    a.label("ring_byte")
    mov(3,5);a.emit(0x74f3,0xfffe,0x75f3,0x8000,0x6811,0,0x2803)
    mov(1,5);a.emit(0x74f1,1);a.ajmp("low_byte",2)
    a.emit(0x4d08)
    a.label("low_byte");a.emit(0x74f0,255,0x5051)
    cmpi(5,RING_END);a.ajmp("byte_ready",5);imm(5,RING_BEGIN)
    a.label("byte_ready");a.emit(0xc600)
    a.label("crc_bits")
    a.emit(0x1740)
    a.label("crc_bit");mov(0,4);a.emit(0x74f0,0x8000,0x4c41)
    cmpi(0,0);a.ajmp("crc_no_poly",1);a.emit(0x77f4,0x8005)
    a.label("crc_no_poly");a.emit(0x5211);a.ajmp("crc_bit",2);a.emit(0xc600)
    a.label("commit")
    put(5,READ)
    a.label("account_input");get(0,BYTES_LO);get(2,BYTES_HI)
    # 1D:3792/3796 sets the absolute file word position after decoder reset.
    # Keep that caller-owned base. A 32-bit byte total would both erase seek
    # and discard the top bit of this 32-bit *word* position. Only the old
    # relative-byte parity participates in the word delta for this commit.
    mov(4,0);a.emit(0x74f4,1,0x1046,0x4d41)
    a.emit(0x1006,0x71f2,0);put(0,BYTES_LO);put(2,BYTES_HI)
    a.emit(0x6811,0,0x88f6,0xb350,0x88f7,0xb352,
        0x1074,0x71f6,0,0xa8f6,0xb350,0xa8f7,0xb352,0xc600)
    if deferred_input_retirement:
        # Decode completion and writable-ring reclamation are distinct.
        # MPEG-1 owns its entire frame until both PCM granules are handed
        # off; LSF completes in one call. No original EOF/ready bit is edited.
        a.label("finish_input")
        get(0,STAGED);cmpi(0,0);a.ajmp("finish_input_return",1)
        get(6,LENGTH);a.acall("account_input")
        const(STAGED,0);const(RECLAIM_PENDING,1)
        a.label("finish_input_return");a.emit(0xc600)
        a.label("retire_input")
        get(0,RECLAIM_PENDING);cmpi(0,0);a.ajmp("retire_input_return",1)
        get(0,RECLAIM_END);put(0,READ);const(RECLAIM_PENDING,0)
        a.label("retire_input_return");a.emit(0xc600)
    code=struct.pack(f"<{len(a.words)}H",*a.finish());code_span(address,code)
    assert FINAL_INPUT+2<=decoder.FRAME and decoder.SCRATCH+(RING_WORDS-2)*2<=decoder.OVERLAP[0]
    return {"code":code,"code_address":address,"entries":a.labels,
            "workspace_bank":"caller DS0","workspace_offset":"caller R3",
            "factory_player_connected":False}
