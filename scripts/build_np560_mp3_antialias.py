#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native DMCU Q28 Layer III alias reduction, after short reorder.

pair: R1:R0=A, R4:R3=B, R2=coefficient index 0..7. Returns rotated
A/B in the same pairs, R2=0; invalid index=2, final Q28 overflow=3,
both outputs zero on error. Preserves R5..14, DS and SOCR. Four signed
64-bit products are summed BEFORE the arithmetic Q28 shift; no early
product truncation or signed 32-bit input negation.

spectrum: R3 -> four near words {rate_index, block_type, mixed_0_or_1,
reordered_q28_576}. In-place, R0=576/R2=0; invalid geometry R0=0/R2=2
without mutation; overflow R0=0/R2=3 (caller must reject partial output).
Preserves all other GPRs and DS/SOCR. All buffers, descriptor and stack
are aligned, allocated and disjoint, DS0=0; ownership is the caller's.
Long/start/stop blocks: 31 boundaries. Pure short: none. Mixed: only
internal long boundaries, one normally, three at 8 kHz (72 long lines).
The latter follows the established long-prefix geometry, not libmad's
fixed 36-line mixed call; full 8 kHz mixed PCM conformance is unproven.

Uses the pinned libmad cs/ca constants; not original ROM bytes, PCM,
factory ABI, or a host decoder. Private multiply_positive/multiply_signed/pack_q28
entries use RETC, pair/spectrum use RETS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_np560_mp3_huffman import ROOT
from build_np560_mp3_scalefactors import MAD_SHA
from np560_assembler import _DMCUAssembler
from np560_mp3_workspace import select_workspace
from np560_mp3_link import code_span, near_table
from scan_np560_mpeg_tables import array

ADDRESS, TABLE_ADDRESS = 0x20B500, 0x219830


def tables():
    raw = (ROOT/"doc/sources/libmad-20260907/layer3.c").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MAD_SHA
    cs, ca = array(raw.decode(), "cs"), array(raw.decode(), "ca")
    # ca uses -MAD_F(...); array extracts magnitudes, as deliberately
    # needed for A'=A*cs+B*abs(ca), B'=B*cs-A*abs(ca).
    assert len(cs) == len(ca) == 8 and all(0 < v < 1 << 28 for v in cs+ca)
    return struct.pack("<16I", *(v for pair in zip(cs, ca) for v in pair))


def build(address=ADDRESS, workspace_bank=0, *, table_address=TABLE_ADDRESS):
    a = _DMCUAssembler(address)
    def imm(r, v): a.emit(0x68F0 | r, v & 65535)
    def mov(d, s): a.emit(0x0800 | d << 4 | s)
    def cmpi(r, v): a.emit(0x76F0 | r, v & 65535)
    def push(r): a.emit(0x58F0 | r)
    def pop(r): a.emit(0x380F | r << 4)
    def negate(regs):
        for r in regs: a.emit(0x77F0 | r, 65535)
        a.emit(0x70F0 | regs[0], 1)
        for r in regs[1:]: a.emit(0x71F0 | r, 0)
    def product(lo, hi, offset):
        mov(0, lo)
        mov(1, hi)
        mov(5, 14)
        if offset: a.emit(0x70F5, offset)
        a.emit(0x38A5, 0x28B5)
        a.acall("multiply_positive")
    def save_product():
        for r in (3, 2, 1, 0): push(r)
    def load_product():
        for r in (4, 5, 6, 7): pop(r)

    a.label("pair")
    for r in range(5, 15): push(r)
    a.emit(0x1F11, 0x1F00)
    cmpi(2, 7)
    a.ajmp("invalid_pair", 0xA)
    a.emit(0x1F00, 0x385F, 0x74F5, 0xFFEF, 0x58F5, 0x1F80,
           0x6811, table_address >> 15)
    mov(8, 0)
    mov(9, 1)
    mov(12, 3)
    mov(13, 4)
    mov(14, 2)
    a.emit(0x4CE3, 0x70FE, 0x8000 | (table_address & 0x7fff))
    product(8, 9, 0)
    save_product()
    product(12, 13, 4)
    load_product()
    a.emit(0x1004, 0x1115, 0x1126, 0x1137)
    a.acall("pack_q28")
    cmpi(2, 0)
    a.ajmp("pair_error", 2)
    push(0)
    push(1)
    product(12, 13, 0)
    save_product()
    product(8, 9, 4)
    load_product()
    a.emit(0x1240, 0x1351, 0x1362, 0x1373)
    for dst, src in zip(range(4), range(4, 8)): mov(dst, src)
    a.acall("pack_q28")
    mov(3, 0)
    mov(4, 1)
    pop(1)
    pop(0)
    cmpi(2, 0)
    a.ajmp("pair_return", 1)
    a.ajmp("pair_error")
    a.label("invalid_pair")
    imm(2, 2)
    a.label("pair_error")
    for r in (0, 1, 3, 4): imm(r, 0)
    a.label("pair_return")
    a.emit(0x1F80, 0x1F91)
    for r in reversed(range(5, 15)): pop(r)
    a.emit(0xC620)

    a.label("multiply_positive")
    # Signed int32 R1:R0 times uint32 R11:R10 -> signed 64-bit R3..0.
    # Four unsigned hardware products, followed by exact sign extension:
    # U(x)*U(y) - (x<0 ? U(y)<<32 : 0), modulo 2^64. No magnitude
    # conversion or product negation; only one saved register is needed.
    # Caller clears MAS. Clobbers R4..7 only; R5:R4 retains the original x
    # for multiply_signed's extra correction. Preserves R8..14, DS/SOCR.
    # R5's low byte is ARX and every MUL overwrites it. Keep x.high in
    # saved R8 throughout the four products, not in the accumulator.
    push(8)
    mov(4, 0)
    mov(8, 1)
    imm(2, 0)
    imm(3, 0)
    a.emit(0xBE3C, 0x040A)
    mov(0, 7)
    mov(1, 6)
    a.emit(0xBE3C, 0x080A, 0x1017, 0x1126, 0x71F3, 0,
           0xBE3C, 0x040B, 0x1017, 0x1126, 0x71F3, 0,
           0xBE3C, 0x080B, 0x1027, 0x1136)
    mov(5, 8)
    pop(8)
    cmpi(5, 0x8000)
    a.ajmp("positive_product_return", 5)
    a.emit(0x122A, 0x133B)
    a.label("positive_product_return")
    a.emit(0xC600)

    a.label("multiply_signed")
    # int32 * int32 uses the same unsigned partial products, with one
    # further high-half subtraction when y is negative. INT32_MIN is
    # ordinary input, not an absolute-value overflow special case.
    a.acall("multiply_positive")
    cmpi(11, 0x8000)
    a.ajmp("signed_product_return", 5)
    a.emit(0x1224, 0x1335)
    a.label("signed_product_return")
    a.emit(0xC600)

    a.label("pack_q28")
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
    a.label("spectrum")
    for r in saved: push(r)
    a.emit(0x1F10, *select_workspace(workspace_bank), 0x38A3, 0x38B3, 0x38C3, 0x28D3)
    for r, limit in ((10, 8), (11, 3), (12, 1)):
        cmpi(r, limit)
        a.ajmp("invalid_spectrum", 0xA)
    imm(14, 31)
    cmpi(11, 2)
    a.ajmp("boundaries_ready", 2)
    cmpi(12, 0)
    a.ajmp("spectrum_success", 1)
    imm(14, 1)
    cmpi(10, 8)
    a.ajmp("boundaries_ready", 2)
    imm(14, 3)
    a.label("boundaries_ready")
    a.emit(0x70FD, 72)
    a.label("boundary")
    mov(8, 13)
    a.emit(0x5284)
    mov(9, 13)
    imm(10, 0)
    a.label("butterfly")
    mov(5, 8)
    mov(6, 9)
    a.emit(0x3805, 0x2815, 0x3836, 0x2846)
    mov(2, 10)
    a.emit(0xBD00 | address >> 16, a.labels["pair"] & 65535)
    cmpi(2, 0)
    a.ajmp("spectrum_failed", 2)
    mov(5, 8)
    mov(6, 9)
    a.emit(0x1A50, 0x0A51, 0x1A63, 0x0A64, 0x5284, 0x5094, 0x50A1)
    cmpi(10, 8)
    a.ajmp("butterfly", 5)
    a.emit(0x70FD, 72, 0x52E1)
    a.ajmp("boundary", 2)
    a.label("spectrum_success")
    imm(0, 576)
    imm(2, 0)
    a.ajmp("spectrum_return")
    a.label("invalid_spectrum")
    imm(2, 2)
    a.label("spectrum_failed")
    imm(0, 0)
    a.label("spectrum_return")
    a.emit(0x1F90)
    for r in reversed(saved): pop(r)
    a.emit(0xC620)
    code = struct.pack(f"<{len(a.words)}H", *a.finish())
    code_span(address,code);near_table(table_address,tables())
    return {"code": code, "code_address": address, "tables": tables(),
            "table_address": table_address, "entries": a.labels}


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
