#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""DMCU Q28 MS stereo and short-block reorder, NOT PCM/factory ROM.

ms_pair: R1:R0 = signed M, R4:R3 = signed S; returns signed L/R in
the same pairs, R2=0 or 3 (Q28 overflow, both output pairs zero).
Products, sum and difference are signed 64-bit BEFORE the Q28 shift.
Preserves R5..R14, DS and SOCR (including accumulator saturation).

ms_spectrum: R3 -> {left_q28_576, right_q28_576}, in-place; R0=576,
R2=0 on success, 3 on overflow (reject partial spectrum). Preserves
all other GPRs, DS and SOCR. This is MS ONLY: the caller must NOT apply
it to intensity-stereo bands or interpret its availability as IS support.

reorder: R3 -> {frequency_index, block_type, mixed_0_or_1,
input_q28_576, output_q28_576}. Copies long blocks/prefix unchanged and
interleaves the three short windows within each band. R0=576/R2=0,
or R0=0/R2=2 on invalid geometry (no output mutation). Preserves all
other GPRs and DS/SOCR. Buffers must be aligned, allocated and disjoint
from each other, the descriptor and stack. MS buffers are likewise
disjoint and near (DS0=0); pointer ownership belongs to the caller.

Reuses the pinned public requantization geometry table. No host DSP,
fake PCM, intensity-stereo approximation or original ROM patch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_np560_mp3_requantize import GEOMETRY_ADDRESS, tables as requant_tables
from np560_assembler import _DMCUAssembler
from np560_mp3_workspace import select_workspace

ADDRESS = 0x20AC00
INV_SQRT2 = 0x0B504F33  # libmad Q28; floor(product / 2**28)


def build(address=ADDRESS, workspace_bank=0, *, geometry_address=GEOMETRY_ADDRESS):
    a = _DMCUAssembler(address)

    def imm(r, value): a.emit(0x68F0 | r, value & 65535)
    def mov(dst, src): a.emit(0x0800 | dst << 4 | src)
    def cmpi(r, value): a.emit(0x76F0 | r, value & 65535)
    def push(r): a.emit(0x58F0 | r)
    def pop(r): a.emit(0x380F | r << 4)
    def load(dst, base, offset):
        mov(1, base)
        if offset: a.emit(0x70F1, offset)
        a.emit(0x2801 | dst << 4)
    def call(entry): a.emit(0xBD00 | address >> 16, a.labels[entry] & 65535)
    def negate_words(regs):
        for r in regs: a.emit(0x77F0 | r, 65535)
        a.emit(0x70F0 | regs[0], 1)
        for r in regs[1:]: a.emit(0x71F0 | r, 0)

    a.label("ms_pair")
    for r in range(5, 15): push(r)
    a.emit(0x1F00, 0x1F00, 0x385F, 0x74F5, 0xFFEF, 0x58F5, 0x1F80)
    push(3)
    push(4)
    a.acall("multiply_inv")
    for dst, src in zip(range(8, 12), range(4)): mov(dst, src)
    pop(1)
    pop(0)
    a.acall("multiply_inv")
    for dst, src in zip((12, 13, 14, 4), range(4)): mov(dst, src)
    a.emit(0x1008, 0x1119, 0x112A, 0x113B)
    a.acall("pack_q28")
    cmpi(2, 0)
    a.ajmp("pair_error", 2)
    push(0)
    push(1)
    for dst, src in zip(range(4), range(8, 12)): mov(dst, src)
    a.emit(0x120C, 0x131D, 0x132E, 0x1334)
    a.acall("pack_q28")
    mov(3, 0)
    mov(4, 1)
    pop(1)
    pop(0)
    cmpi(2, 0)
    a.ajmp("pair_return", 1)
    a.label("pair_error")
    for r in (0, 1, 3, 4): imm(r, 0)
    a.label("pair_return")
    a.emit(0x1F80)
    for r in reversed(range(5, 15)): pop(r)
    a.emit(0xC620)

    a.label("multiply_inv")
    # R1:R0 signed -> R3:R2:R1:R0 signed 64-bit. Preserve R8..14,
    # which hold the other product in the enclosing butterfly.
    for r in range(8, 15): push(r)
    mov(8, 0)
    mov(9, 1)
    mov(14, 1)
    a.emit(0x74FE, 0x8000)
    a.ajmp("abs_ready", 1)
    negate_words((8, 9))
    a.label("abs_ready")
    imm(10, INV_SQRT2 & 65535)
    imm(11, INV_SQRT2 >> 16)
    imm(2, 0)
    imm(3, 0)
    a.emit(0xBE3C, 0x080A)
    mov(0, 7)
    mov(1, 6)
    a.emit(0xBE3C, 0x090A, 0x1017, 0x1126, 0x71F3, 0,
           0xBE3C, 0x080B, 0x1017, 0x1126, 0x71F3, 0,
           0xBE3C, 0x090B, 0x1027, 0x1136)
    cmpi(14, 0)
    a.ajmp("product_ready", 1)
    negate_words((0, 1, 2, 3))
    a.label("product_ready")
    for r in reversed(range(8, 15)): pop(r)
    a.emit(0xC600)

    a.label("pack_q28")
    # Bits above product bit 59 must be its sign extension. Checking
    # BEFORE packing prevents both positive and negative wraparound.
    cmpi(3, 0x8000)
    a.ajmp("pack_negative", 6)
    cmpi(3, 0x0800)
    a.ajmp("pack_overflow", 6)
    a.ajmp("pack_ready")
    a.label("pack_negative")
    cmpi(3, 0xF800)
    a.ajmp("pack_overflow", 5)
    a.label("pack_ready")
    mov(0, 1)
    a.emit(0x4D0C)
    mov(1, 2)
    a.emit(0x4C24, 0x1002, 0x4D1C, 0x4C34, 0x1013)
    imm(2, 0)
    a.emit(0xC600)
    a.label("pack_overflow")
    imm(2, 3)
    a.emit(0xC600)

    saved = (1, *range(3, 15))
    a.label("ms_spectrum")
    for r in saved: push(r)
    a.emit(0x1F10, *select_workspace(workspace_bank), 0x38C3, 0x28D3)
    imm(14, 576)
    a.label("ms_coefficient")
    mov(5, 12)
    mov(6, 13)
    a.emit(0x3805, 0x2815, 0x3836, 0x2846)
    call("ms_pair")
    cmpi(2, 0)
    a.ajmp("ms_failed", 2)
    mov(5, 12)
    mov(6, 13)
    a.emit(0x1A50, 0x1A51, 0x1A63, 0x1A64, 0x50C4, 0x50D4, 0x52E1)
    a.ajmp("ms_coefficient", 2)
    imm(0, 576)
    a.ajmp("ms_return")
    a.label("ms_failed")
    imm(0, 0)
    a.label("ms_return")
    a.emit(0x1F90)
    for r in reversed(saved): pop(r)
    a.emit(0xC620)

    a.label("reorder")
    for r in saved: push(r)
    a.emit(0x1F10, 0x1F11, *select_workspace(workspace_bank), 0x6811, geometry_address >> 15)
    mov(4, 3)
    load(0, 4, 0)
    cmpi(0, 8)
    a.ajmp("invalid_reorder", 0xA)
    mov(10, 0)
    load(8, 4, 2)
    cmpi(8, 3)
    a.ajmp("invalid_reorder", 0xA)
    load(9, 4, 4)
    cmpi(9, 1)
    a.ajmp("invalid_reorder", 0xA)
    load(7, 4, 6)
    load(6, 4, 8)
    imm(14, 0)
    cmpi(8, 2)
    a.ajmp("reorder_mode", 2)
    mov(14, 9)
    a.emit(0x50E1)
    a.label("reorder_mode")
    mov(0, 10)
    a.emit(0x100A, 0x100A, 0x100E, 0x4C02, 0x70F0, 0x8000 | (geometry_address & 0x7fff),
           0x0830, 0x3803, 0x28A3, 0x0850)
    a.label("reorder_band")
    a.emit(0x38D5, 0x5052, 0x3805)  # width, skip pretab, window
    cmpi(0, 3)
    a.ajmp("short_band", 2)
    a.label("copy_long")
    a.emit(0x3807, 0x3817, 0x1A60, 0x1A61, 0x52D1)
    a.ajmp("copy_long", 2)
    a.emit(0x52A1)
    a.ajmp("next_reorder_band")
    a.label("short_band")
    mov(0, 13)
    a.emit(0x4C02)
    mov(9, 7)
    a.emit(0x1090)
    mov(3, 9)
    a.emit(0x1030)
    a.label("copy_triplet")
    for src in (7, 9, 3):
        a.emit(0x3800 | src, 0x3810 | src, 0x1A60, 0x1A61)
    a.emit(0x52D1)
    a.ajmp("copy_triplet", 2)
    mov(7, 3)
    a.emit(0x505C, 0x52A3)  # skip the two identical-width window records
    a.label("next_reorder_band")
    cmpi(10, 0)
    a.ajmp("reorder_band", 2)
    imm(0, 576)
    imm(2, 0)
    a.ajmp("reorder_return")
    a.label("invalid_reorder")
    imm(0, 0)
    imm(2, 2)
    a.label("reorder_return")
    a.emit(0x1F91, 0x1F90)
    for r in reversed(saved): pop(r)
    a.emit(0xC620)
    code = struct.pack(f"<{len(a.words)}H", *a.finish())
    assert address % 2 == 0 and (address & 0xffff)+len(code) <= 0x10000
    return {"code": code, "code_address": address, "entries": a.labels,
            "geometry_address": geometry_address, "intensity_stereo_available": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    core = build()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/"code.bin").write_bytes(core["code"])
    manifest = {k: v for k, v in core.items() if k != "code"}
    manifest.update(code_bytes=len(core["code"]), code_sha256=hashlib.sha256(core["code"]).hexdigest(),
                    geometry_source_table_sha256=hashlib.sha256(requant_tables()[0]).hexdigest(),
                    factory_rom_patch=False, pcm_produced=False, license="GPL-2.0-or-later")
    (args.output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
