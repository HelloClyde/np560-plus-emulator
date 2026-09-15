#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native Q28 Layer III joint stereo, before short reorder; not factory ROM.

pair: R1:R0 = signed left/intensity amplitude, R3 = table index (0..68).
Returns L in R1:R0, R in R4:R3, R2=0 or 2 for invalid table index.
Preserves R5..14, DS and SOCR. Coefficients <=1 cannot overflow Q28.

joint: R3 -> 10 near words {rate_index, mode_extension, channel0_16,
channel1_16, sf_right_39, illegal_right_39, quant_right_576,
left_q28_576, right_q28_576, workspace_44_words}. R0=576/R2=0,
or R0=0/R2=2 invalid input (no mutation), 3 MS overflow (reject partial).
Preserves R1,R3..14, DS/SOCR. All buffers/stack must be aligned, allocated,
and disjoint in DS0=0. SF and quantized inputs are read-only.

The nonzero boundary uses original quantized right samples, so Q28
underflow cannot incorrectly expand the IS region. Short windows are
independent; any nonzero short window disables IS in the mixed long part.
LSF illegal positions come from the actual per-band slen mask, NOT a
fixed sf>=16 test. Untransmitted top bands inherit previous SF AND mask
(long21<-20, short12<-11 per window), following FFmpeg/mpg123's top-band
policy rather than treating SF tail zeros as transmitted IS positions.
This choice is documented, not a claim of original NP560 rounding.

Workspace: bounds[4], modes[39], coefficient_family_base. Mode 0=copy,
1=MS, 2..70=IS table index+2. Caller must reject all output on any error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_np560_mp3_huffman import ROOT
from build_np560_mp3_scalefactors import MAD_SHA
from build_np560_mp3_requantize import GEOMETRY_ADDRESS
from build_np560_mp3_stereo import build as build_ms
from np560_assembler import _DMCUAssembler
from np560_mp3_workspace import select_workspace
from np560_mp3_link import code_span, near_table
from scan_np560_mpeg_tables import array

ADDRESS, TABLE_ADDRESS = 0x20B000, 0x219608
WORK_WORDS = 44


def tables():
    raw = (ROOT/"doc/sources/libmad-20260907/layer3.c").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MAD_SHA
    m1, lsf = array(raw.decode(), "is_table"), array(raw.decode(), "is_lsf_table")
    assert len(m1) == 7 and len(lsf) == 30
    pairs = [(m1[i], m1[6-i]) for i in range(7)]
    for scale in range(2):
        for pos in range(31):
            opposite = 1 << 28 if not pos else lsf[scale*15+(pos-1)//2]
            pairs.append((opposite, 1 << 28) if pos % 2 else (1 << 28, opposite))
    assert len(pairs) == 69 and all(0 <= v <= 1 << 28 for p in pairs for v in p)
    return struct.pack("<138I", *(v for p in pairs for v in p))


def build(address=ADDRESS, workspace_bank=0, *, table_address=TABLE_ADDRESS,
          geometry_address=GEOMETRY_ADDRESS, ms=None):
    a = _DMCUAssembler(address)
    ms = ms or build_ms(workspace_bank=workspace_bank,geometry_address=geometry_address)
    def imm(r, v): a.emit(0x68F0 | r, v & 65535)
    def mov(d, s): a.emit(0x0800 | d << 4 | s)
    def cmpi(r, v): a.emit(0x76F0 | r, v & 65535)
    def push(r): a.emit(0x58F0 | r)
    def pop(r): a.emit(0x380F | r << 4)
    def load(r, base, offset):
        mov(1, base)
        if offset: a.emit(0x70F1, offset)
        a.emit(0x2801 | r << 4)
    def negate(regs):
        for r in regs: a.emit(0x77F0 | r, 65535)
        a.emit(0x70F0 | regs[0], 1)
        for r in regs[1:]: a.emit(0x71F0 | r, 0)
    def call(entry): a.emit(0xBD00 | address >> 16, a.labels[entry] & 65535)

    a.label("pair")
    for r in range(5, 15): push(r)
    a.emit(0x1F11, 0x1F00)
    cmpi(3, 68)
    a.ajmp("invalid_pair", 0xA)
    a.emit(0x1F00, 0x385F, 0x74F5, 0xFFEF, 0x58F5, 0x1F80,
           0x6811, table_address >> 15)
    mov(8, 0)
    mov(9, 1)
    a.emit(0x4C33, 0x70F3, 0x8000 | (table_address & 0x7fff),
           0x38A3, 0x38B3, 0x38C3, 0x28D3)
    a.acall("scale")
    push(0)
    push(1)
    mov(0, 8)
    mov(1, 9)
    mov(10, 12)
    mov(11, 13)
    a.acall("scale")
    mov(3, 0)
    mov(4, 1)
    pop(1)
    pop(0)
    imm(2, 0)
    a.ajmp("pair_return")
    a.label("invalid_pair")
    for r in (0, 1, 3, 4): imm(r, 0)
    imm(2, 2)
    a.label("pair_return")
    a.emit(0x1F80, 0x1F91)
    for r in reversed(range(5, 15)): pop(r)
    a.emit(0xC620)

    a.label("scale")
    for r in (8, 9, 14): push(r)
    mov(8, 0)
    mov(9, 1)
    mov(14, 1)
    a.emit(0x74FE, 0x8000)
    a.ajmp("magnitude", 1)
    negate((8, 9))
    a.label("magnitude")
    imm(2, 0)
    imm(3, 0)
    a.emit(0xBE3C, 0x080A)
    mov(0, 7)
    mov(1, 6)
    a.emit(0xBE3C, 0x090A, 0x1017, 0x1126, 0x71F3, 0,
           0xBE3C, 0x080B, 0x1017, 0x1126, 0x71F3, 0,
           0xBE3C, 0x090B, 0x1027, 0x1136)
    cmpi(14, 0)
    a.ajmp("signed_product", 1)
    negate((0, 1, 2, 3))
    a.label("signed_product")
    mov(0, 1)
    a.emit(0x4D0C)
    mov(1, 2)
    a.emit(0x4C24, 0x1002, 0x4D1C, 0x4C34, 0x1013)
    for r in (14, 9, 8): pop(r)
    a.emit(0xC600)

    saved = (1, *range(3, 15))
    a.label("joint")
    for r in saved: push(r)
    a.emit(0x1F10, 0x1F11, *select_workspace(workspace_bank), 0x6811, geometry_address >> 15)
    mov(4, 3)
    load(0, 4, 0)
    cmpi(0, 8)
    a.ajmp("invalid", 0xA)
    load(0, 4, 2)
    cmpi(0, 3)
    a.ajmp("invalid", 0xA)
    # Validate both sideinfo records. Joint modes require synchronous
    # block switching; independent stereo is allowed to differ.
    for ch_offset in (4, 6):
        load(7, 4, ch_offset)
        load(0, 7, 10)
        cmpi(0, 3)
        a.ajmp("invalid", 0xA)
        load(0, 7, 8)
        cmpi(0, 15)
        a.ajmp("invalid", 0xA)
    load(0, 4, 2)
    cmpi(0, 0)
    a.ajmp("success", 1)  # independent stereo; no scratch/output writes
    load(6, 4, 4)
    for off in (8, 10):
        load(2, 6, off)
        load(0, 7, off)
        if off == 8: a.emit(0x74F2, 8, 0x74F0, 8)
        a.emit(0x1602)
        a.ajmp("invalid", 2)
    load(0, 4, 2)
    a.emit(0x74F0, 1)
    a.ajmp("preflight_ready", 1)
    load(0, 7, 6)
    cmpi(0, 511)
    a.ajmp("invalid", 0xA)
    load(8, 4, 8)
    load(9, 4, 10)
    load(14, 4, 0)
    cmpi(14, 3)
    a.ajmp("validate_sf", 6)
    cmpi(0, 15)
    a.ajmp("invalid", 0xA)
    a.label("validate_sf")
    imm(13, 39)
    a.label("sf_word")
    mov(3, 8)
    a.emit(0x2803, 0x5082, 0x3829)
    cmpi(0, 31)
    a.ajmp("invalid", 0xA)
    cmpi(2, 1)
    a.ajmp("invalid", 0xA)
    cmpi(14, 3)
    a.ajmp("sf_valid", 5)
    cmpi(0, 31)
    a.ajmp("sf_valid", 2)
    cmpi(2, 0)
    a.ajmp("invalid", 1)  # LSF position 31 must be marked illegal
    a.label("sf_valid")
    a.emit(0x52D1)
    a.ajmp("sf_word", 2)
    a.label("preflight_ready")
    load(11, 4, 18)
    mov(3, 11)
    imm(0, 0)
    imm(13, WORK_WORDS)
    a.label("clear_work")
    a.emit(0x1A30, 0x52D1)
    a.ajmp("clear_work", 2)
    # 0 = MPEG1; 7/38 = LSF intensity_scale 0/1 coefficient family.
    load(0, 4, 0)
    cmpi(0, 3)
    a.ajmp("family_ready", 5)
    load(7, 4, 6)
    load(0, 7, 6)
    a.emit(0x74F0, 1)
    mov(2, 0)
    a.emit(0x4C05, 0x1202, 0x5007)
    mov(1, 11)
    a.emit(0x70F1, 86, 0x0A10)
    a.label("family_ready")
    a.acall("geometry")
    load(7, 4, 12)
    imm(12, 1)
    a.label("scan_band")
    a.emit(0x38D5, 0x5052, 0x38E5)
    imm(2, 0)
    a.label("scan_quant")
    a.emit(0x3807, 0x1520, 0x52D1)
    a.ajmp("scan_quant", 2)
    cmpi(2, 0)
    a.ajmp("scan_next", 1)
    mov(1, 14)
    a.emit(0x4C11, 0x101B, 0x0A1C)
    a.label("scan_next")
    a.emit(0x50C1, 0x52A1)
    a.ajmp("scan_band", 2)
    # For mixed blocks, ANY nonzero short window suppresses long-part IS.
    mov(3, 11)
    imm(13, 4)
    imm(2, 0)
    a.label("max_bound")
    a.emit(0x3803, 0x1602)
    a.ajmp("max_keep", 0xC)
    mov(2, 0)
    a.label("max_keep")
    a.emit(0x52D1)
    a.ajmp("max_bound", 2)
    mov(1, 11)
    a.emit(0x5016, 0x0A12)
    a.acall("geometry")
    load(6, 4, 14)
    load(7, 4, 16)
    load(8, 4, 8)
    load(9, 4, 10)
    imm(12, 1)
    a.label("band")
    a.emit(0x38D5, 0x5052, 0x38E5)
    load(0, 4, 2)
    a.emit(0x74F0, 1)
    a.ajmp("non_is", 1)
    mov(1, 14)
    a.emit(0x4C11, 0x101B, 0x2801, 0x16C0)
    a.ajmp("non_is", 0xC)
    # Infer the untransmitted final SF without modifying the original SF
    # (which is still needed for SCFSI and other granules).
    mov(0, 12)
    a.emit(0x5201)
    cmpi(14, 3)
    a.ajmp("short_tail", 2)
    cmpi(10, 1)
    a.ajmp("sf_index_ready", 2)
    a.emit(0x5201)
    a.ajmp("sf_index_ready")
    a.label("short_tail")
    cmpi(10, 3)
    a.ajmp("sf_index_ready", 0xA)
    a.emit(0x5203)
    a.label("sf_index_ready")
    a.emit(0x4C01)
    mov(1, 8)
    a.emit(0x1010, 0x2831)
    load(14, 11, 86)
    cmpi(14, 0)
    a.ajmp("lsf_position", 2)
    cmpi(3, 7)
    a.ajmp("non_is", 6)
    a.ajmp("is_position")
    a.label("lsf_position")
    mov(1, 9)
    a.emit(0x1010, 0x2821)
    cmpi(2, 0)
    a.ajmp("non_is", 2)
    a.label("is_position")
    a.emit(0x103E, 0x5032)
    a.ajmp("mode_ready")
    a.label("non_is")
    load(3, 4, 2)
    a.emit(0x74F3, 2, 0x4D31)
    a.label("mode_ready")
    mov(14, 3)
    mov(1, 12)
    a.emit(0x4C11, 0x5016, 0x101B, 0x0A1E)
    cmpi(14, 0)
    a.ajmp("transform", 2)
    mov(0, 13)
    a.emit(0x4C02, 0x1060, 0x1070)
    a.ajmp("next_band")
    a.label("transform")
    push(4)
    a.emit(0x3806, 0x3816)
    cmpi(14, 1)
    a.ajmp("is_transform", 2)
    a.emit(0x3837, 0x3847, 0xBD00 | ms["entries"]["ms_pair"] >> 16, ms["entries"]["ms_pair"] & 65535)
    a.ajmp("transformed")
    a.label("is_transform")
    a.emit(0x5074)
    mov(3, 14)
    a.emit(0x5232)
    call("pair")
    a.label("transformed")
    cmpi(2, 0)
    a.ajmp("transform_error", 2)
    mov(2, 6)
    a.emit(0x5224, 0x1A20, 0x1A21)
    mov(2, 7)
    a.emit(0x5224, 0x1A23, 0x1A24)
    pop(4)
    a.emit(0x52D1)
    a.ajmp("transform", 2)
    a.label("next_band")
    a.emit(0x50C1, 0x52A1)
    a.ajmp("band", 2)
    a.label("success")
    imm(0, 576)
    imm(2, 0)
    a.ajmp("return")
    a.label("transform_error")
    pop(4)
    a.ajmp("failed")
    a.label("invalid")
    imm(2, 2)
    a.label("failed")
    imm(0, 0)
    a.label("return")
    a.emit(0x1F91, 0x1F90)
    for r in reversed(saved): pop(r)
    a.emit(0xC620)

    a.label("geometry")
    load(0, 4, 0)
    mov(10, 0)
    load(7, 4, 6)
    load(0, 7, 10)
    imm(14, 0)
    cmpi(0, 2)
    a.ajmp("geometry_mode", 2)
    load(14, 7, 8)
    a.emit(0x4DE3, 0x74FE, 1, 0x50E1)
    a.label("geometry_mode")
    mov(0, 10)
    a.emit(0x100A, 0x100A, 0x100E, 0x4C02, 0x70F0, 0x8000 | (geometry_address & 0x7fff),
           0x0830, 0x3803, 0x28A3, 0x0850, 0xC600)
    code = struct.pack(f"<{len(a.words)}H", *a.finish())
    code_span(address,code);near_table(table_address,tables())
    return {"code": code, "code_address": address, "tables": tables(), "table_address": table_address,
            "entries": a.labels, "workspace_words": WORK_WORDS, "intensity_stereo_available": True,
            "terminal_sf_policy": "inherit previous band's SF and illegal mask; same short window"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    core = build()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {k: v for k, v in core.items() if k not in ("code", "tables")}
    for key in ("code", "tables"):
        (args.output/(key+".bin")).write_bytes(core[key])
        manifest[key+"_bytes"] = len(core[key])
        manifest[key+"_sha256"] = hashlib.sha256(core[key]).hexdigest()
    manifest.update(factory_rom_patch=False, pcm_produced=False, license="GPL-2.0-or-later")
    (args.output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
