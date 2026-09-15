#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native Layer III main_data assembly/history, not an original ROM ABI.

R12=input bit context; R3=descriptor of 8 near words:
{history_buffer, history_bytes, main_data_begin, payload_bytes,
 output_buffer, output_capacity_bytes, output_bit_context, part2_3_bits}.
History allocation is 512 bytes (only up to 511 valid), MSB-first words.
Output allocation is capacity rounded UP to whole words. Buffers, context,
descriptor and active stack must be allocated, aligned and nonoverlapping.
R0=assembled bytes (0 on error), R2=status, preserve every other GPR/DS.
0=success; 1=input short; 2=bad arguments/capacity/context (no mutations);
3=insufficient prior history; 4=part2_3 length exceeds assembled bits.
Errors 3/4 still consume payload and update raw history for future frames,
but invalidate output context (available_bits=0). On 3 the absent prefix
is zeroed as scratch, NEVER presented as successfully recovered data.
Caller resets history_bytes=0 on seek/reset/discontinuity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_np560_mp3_huffman import build as build_entropy
from np560_assembler import _DMCUAssembler
from np560_mp3_workspace import select_workspace

ADDRESS = 0x202800


def build(address=ADDRESS, entropy=None, workspace_bank=0):
    entropy = entropy or build_entropy(workspace_bank=workspace_bank)
    read_bits = entropy["entries"]["read_bits"]
    a = _DMCUAssembler(address)

    def imm(r, value): a.emit(0x68F0 | r, value)
    def mov(dst, src): a.emit(0x0800 | dst << 4 | src)
    def cmpi(r, value): a.emit(0x76F0 | r, value)
    def push(r): a.emit(0x58F0 | r)
    def pop(r): a.emit(0x380F | r << 4)
    def ptr(base, offset):
        mov(1, base)
        if offset: a.emit(0x70F1, offset)
    def load(r, offset):
        ptr(4, offset)
        a.emit(0x2801 | r << 4)
    def store(base, offset, reg):
        ptr(base, offset)
        a.emit(0x0A10 | reg)
    def reader_from_offset():
        # R0=byte offset, R5=base -> R5=word pointer,R6=low-byte flag.
        mov(6, 0)
        a.emit(0x74F6, 1, 0x74F0, 0xFFFE, 0x1050)
    def flush():
        # No postincrement: an odd final byte is zero padded in its word.
        label = f"flushed_{a.pc:x}"
        cmpi(11, 0)
        a.ajmp(label, 1)
        a.emit(0x0A9A)
        a.label(label)

    a.label("reservoir")
    for r in (1, *range(3, 15)): push(r)
    a.emit(0x1F10, 0x1F11, *select_workspace(workspace_bank))
    mov(4, 3)
    load(5, 0)
    load(6, 2)
    load(7, 4)
    load(8, 6)
    load(9, 8)
    load(10, 10)
    for r in (6, 7):
        cmpi(r, 511)
        a.ajmp("invalid", 0xA)
    cmpi(8, 8191)
    a.ajmp("invalid", 0xA)
    mov(0, 8)
    a.emit(0x1007)
    cmpi(0, 8191)
    a.ajmp("invalid", 0xA)
    a.emit(0x16A0)
    a.ajmp("invalid", 5)
    ptr(12, 6)
    a.emit(0x2801)
    cmpi(0, 16)
    a.ajmp("invalid", 0xA)
    ptr(12, 8)
    a.emit(0x2801)
    mov(1, 8)
    a.emit(0x4C13, 0x1601)
    a.ajmp("short", 5)
    imm(14, 0)
    a.emit(0x1667)
    a.ajmp("history_valid", 6)
    imm(14, 3)
    a.ajmp("length_valid")
    a.label("history_valid")
    mov(0, 7)
    a.emit(0x1008, 0x4C03)
    load(13, 14)
    a.emit(0x160D)
    a.ajmp("length_valid", 6)
    imm(14, 4)
    a.label("length_valid")
    imm(10, 0)
    imm(11, 0)
    cmpi(7, 0)
    a.ajmp("payload", 1)
    cmpi(14, 3)
    a.ajmp("missing_prefix", 1)
    mov(0, 6)
    a.emit(0x1207)
    reader_from_offset()
    a.label("prefix")
    a.acall("get_byte")
    a.acall("put_byte")
    a.emit(0x5271)
    a.ajmp("prefix", 2)
    a.ajmp("payload")
    a.label("missing_prefix")
    imm(0, 0)
    a.acall("put_byte")
    a.emit(0x5271)
    a.ajmp("missing_prefix", 2)
    a.label("payload")
    mov(7, 8)
    cmpi(7, 0)
    a.ajmp("assembled", 1)
    a.label("payload_loop")
    imm(0, 8)
    a.emit(0xBD00 | (read_bits >> 16), read_bits & 65535)
    a.acall("put_byte")
    a.emit(0x5271)
    a.ajmp("payload_loop", 2)
    a.label("assembled")
    flush()
    # Preserve the last min(511, old_history+payload) RAW main_data bytes.
    # Keeping only this frame's main_data_begin prefix would lose valid
    # history required by a later frame with a larger backpointer.
    load(5, 0)
    mov(9, 5)
    load(0, 2)
    imm(7, 0)
    cmpi(8, 511)
    a.ajmp("retain_ready", 6)
    imm(7, 511)
    a.emit(0x1278, 0x1607)
    a.ajmp("retain_ready", 6)
    mov(7, 0)
    a.label("retain_ready")
    a.emit(0x1207)
    reader_from_offset()
    imm(10, 0)
    imm(11, 0)
    cmpi(7, 0)
    a.ajmp("history_payload", 1)
    a.label("retain")
    a.acall("get_byte")
    a.acall("put_byte")
    a.emit(0x5271)
    a.ajmp("retain", 2)
    a.label("history_payload")
    mov(7, 8)
    cmpi(7, 511)
    a.ajmp("payload_tail", 0xC)
    imm(7, 511)
    a.label("payload_tail")
    load(0, 4)
    a.emit(0x1008, 0x1207)
    load(5, 8)
    reader_from_offset()
    cmpi(7, 0)
    a.ajmp("history_done", 1)
    a.label("append")
    a.acall("get_byte")
    a.acall("put_byte")
    a.emit(0x5271)
    a.ajmp("append", 2)
    a.label("history_done")
    flush()
    load(0, 2)
    a.emit(0x1008)
    cmpi(0, 511)
    a.ajmp("history_count", 0xC)
    imm(0, 511)
    a.label("history_count")
    store(4, 2, 0)
    load(5, 12)
    imm(0, 0)
    for offset in (0, 4, 6): store(5, offset, 0)
    if workspace_bank != 0:
        # The assembled payload lives in this workspace, not bank-zero RAM.
        a.emit(0x1F10, 0x380F)
        store(5, 0, 0)
    load(0, 8)
    a.emit(0x70F0, 0x8000)
    store(5, 2, 0)
    load(0, 14)
    cmpi(14, 0)
    a.ajmp("output_valid", 1)
    imm(0, 0)
    a.label("output_valid")
    store(5, 8, 0)
    mov(2, 14)
    cmpi(2, 0)
    a.ajmp("no_consumption_result", 2)
    load(0, 4)
    a.emit(0x1008)
    a.ajmp("return")
    a.label("invalid")
    imm(2, 2)
    a.ajmp("no_consumption_result")
    a.label("short")
    imm(2, 1)
    a.label("no_consumption_result")
    imm(0, 0)
    a.label("return")
    a.emit(0x1F91, 0x1F90)
    for r in reversed((1, *range(3, 15))): pop(r)
    a.emit(0xC620)

    a.label("get_byte")
    a.emit(0x2805)
    cmpi(6, 0)
    a.ajmp("get_low", 2)
    a.emit(0x4D08)
    imm(6, 1)
    a.emit(0xC600)
    a.label("get_low")
    a.emit(0x74F0, 255, 0x5052)
    imm(6, 0)
    a.emit(0xC600)

    a.label("put_byte")
    cmpi(11, 0)
    a.ajmp("put_low", 2)
    mov(10, 0)
    a.emit(0x4CA8)
    imm(11, 1)
    a.emit(0xC600)
    a.label("put_low")
    a.emit(0x10A0, 0x1A9A)
    imm(11, 0)
    a.emit(0xC600)
    code = struct.pack(f"<{len(a.words)}H", *a.finish())
    if address & 1 or (address & 0xffff)+len(code) > 0x10000:
        raise ValueError("reservoir overlaps entropy tables")
    return {"code": code, "code_address": address, "entries": a.labels}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    core = build()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "reservoir.bin").write_bytes(core["code"])
    manifest = {k: v for k, v in core.items() if k != "code"}
    manifest.update(code_bytes=len(core["code"]), code_sha256=hashlib.sha256(core["code"]).hexdigest(),
                    factory_rom_patch=False, complete_mp3_decoder=False)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
