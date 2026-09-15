#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native Layer III scalefactors; libmad-based, not the factory ABI.

R12=bit context. R3=7 near words {lsf, channel, scfsi, previous_sf,
output_sf, intensity_right, output_illegal_positions}. SF/mask arrays are
39 words; channel is the 16-word sideinfo layout. All objects must be
allocated/aligned/nonoverlapping in the selected DS0 near memory (default
bank zero; workspace_bank=None preserves caller DS0), except previous_sf
may equal output_sf (MPEG1 reuse). Returns R0=part2 bits,R2=status;
all other GPRs/DS preserved. 0=success,1=short input,2=invalid arguments,
3=scalefactors exceed part2_3 budget. Errors mutate no buffers/context.
LSF preflag is ORed into channel flags only after successful preflight.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_np560_mp3_huffman import ROOT, build as build_entropy
from np560_assembler import _DMCUAssembler
from np560_mp3_workspace import select_workspace
from scan_np560_mpeg_tables import array

# 20:2DE0..3390 is a linked foreground-overlay window in the existing
# machine. Use unused diagnostic NOR space, not an unrelated ROM overlay.
ADDRESS, TABLE_ADDRESS = 0x206800, 0x205800
MAD_SHA = "2da2e4b9176b5935259d3cc032253a9f514309c339770874bc0873413d55cb11"


def tables():
    raw = (ROOT / "doc/sources/libmad-20260907/layer3.c").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MAD_SHA
    source = raw.decode("utf-8")
    nsfb, slen = array(source, "nsfb_table"), array(source, "sflen_table")
    assert len(nsfb) == 72 and len(slen) == 32
    words = []
    for intensity, count in ((False, 512), (True, 256)):
        for value in range(count):
            if not intensity:
                if value < 400:
                    widths = [(value >> 4)//5, (value >> 4) % 5, (value % 16) >> 2, value % 4]
                    group = 0
                elif value < 500:
                    n = value-400
                    widths, group = [(n >> 2)//5, (n >> 2) % 5, n % 4, 0], 1
                else:
                    n = value-500
                    widths, group = [n//3, n % 3, 0, 0], 2
            elif value < 180:
                widths, group = [value//36, (value % 36)//6, value % 6, 0], 3
            elif value < 244:
                n = value-180
                widths, group = [(n % 64) >> 4, (n % 16) >> 2, n % 4, 0], 4
            else:
                n = value-244
                widths, group = [n//3, n % 3, 0, 0], 5
            words += [sum(w << (4*i) for i, w in enumerate(widths)),
                      group*24 + (0x8000 if group == 2 else 0)]
    assert len(words)*2 == 3072
    words += nsfb
    for i in range(16):
        w1, w2 = slen[2*i:2*i+2]
        words += [w1 | w1 << 4 | w2 << 8 | w2 << 12, w1 | w2 << 4]
    assert len(words)*2 == 3280
    words += [6, 5, 5, 5, 18, 18, 0, 0, 17, 18, 0, 0]
    return struct.pack(f"<{len(words)}H", *words)


def build(address=ADDRESS, table_address=TABLE_ADDRESS, entropy=None, workspace_bank=0):
    entropy = entropy or build_entropy(workspace_bank=workspace_bank)
    read_bits = entropy["entries"]["read_bits"]
    table_ptr = 0x8000 | (table_address & 0x7fff)
    a = _DMCUAssembler(address)

    def imm(r, value): a.emit(0x68F0 | r, value)
    def mov(dst, src): a.emit(0x0800 | dst << 4 | src)
    def cmpi(r, value): a.emit(0x76F0 | r, value)
    def ptr(base, offset):
        mov(1, base)
        if offset: a.emit(0x70F1, offset)
    def load(r, base, offset):
        ptr(base, offset)
        a.emit(0x2801 | r << 4)
    def push(r): a.emit(0x58F0 | r)
    def pop(r): a.emit(0x380F | r << 4)

    a.label("scalefactors")
    for r in (1, *range(3, 15)): push(r)
    a.emit(0x1F10, 0x1F11, *select_workspace(workspace_bank), 0x6811, table_address >> 15)
    mov(4, 3)
    load(11, 4, 0)
    load(7, 4, 2)
    load(8, 4, 4)
    load(14, 4, 10)
    for r in (11, 14):
        cmpi(r, 1)
        a.ajmp("invalid", 0xA)
    cmpi(8, 15)
    a.ajmp("invalid", 0xA)
    load(0, 12, 6)
    cmpi(0, 16)
    a.ajmp("invalid", 0xA)
    load(0, 7, 10)
    cmpi(0, 3)
    a.ajmp("invalid", 0xA)
    imm(9, 0)
    cmpi(0, 2)
    a.ajmp("block_ready", 2)
    imm(9, 1)
    load(0, 7, 8)
    a.emit(0x74F0, 8)
    cmpi(0, 0)
    a.ajmp("block_ready", 1)
    imm(9, 2)
    a.label("block_ready")
    load(0, 7, 6)
    imm(13, 0)
    cmpi(11, 0)
    a.ajmp("mpeg1", 1)
    cmpi(0, 511)
    a.ajmp("invalid", 0xA)
    cmpi(14, 0)
    a.ajmp("lsf_index", 1)
    a.emit(0x4D01, 0x70F0, 512)
    a.label("lsf_index")
    a.emit(0x4C02, 0x70F0, table_ptr, 0x0850, 0x38A5, 0x2805)
    cmpi(0, 0x8000)
    a.ajmp("no_preflag", 5)
    imm(13, 4)
    a.emit(0x74F0, 0x7fff)
    a.label("no_preflag")
    a.emit(0x4C93, 0x1090, 0x70F9, table_ptr+3072)
    imm(8, 0)
    a.ajmp("configuration")
    a.label("mpeg1")
    cmpi(0, 15)
    a.ajmp("invalid", 0xA)
    a.emit(0x4C02, 0x70F0, table_ptr+3216)
    cmpi(9, 0)
    a.ajmp("m1_index", 1)
    a.emit(0x5002)
    imm(8, 0)
    a.label("m1_index")
    a.emit(0x28A0, 0x4C93, 0x70F9, table_ptr+3280)
    imm(14, 0)
    a.label("configuration")
    # R9=four counts,R10=four packed widths,R8=long MPEG1 reuse mask.
    imm(3, 0)
    for part in range(4):
        mov(0, 8)
        a.emit(0x74F0, 8 >> part)
        a.ajmp(f"sum_done_{part}", 2)
        load(0, 9, part*2)
        cmpi(0, 0)
        a.ajmp(f"sum_done_{part}", 1)
        mov(6, 10)
        if part: a.emit(0x4D60 | part*4)
        a.emit(0x74F6, 15)
        a.label(f"sum_{part}")
        a.emit(0x1036, 0x5201)
        a.ajmp(f"sum_{part}", 2)
        a.label(f"sum_done_{part}")
    load(0, 7, 0)
    cmpi(0, 4095)
    a.ajmp("invalid", 0xA)
    a.emit(0x1603)
    a.ajmp("budget", 5)
    load(0, 12, 8)
    a.emit(0x1603)
    a.ajmp("short", 5)
    cmpi(13, 0)
    a.ajmp("flags_ready", 1)
    load(0, 7, 8)
    a.emit(0x74F0, 0xFFFB, 0x5004, 0x0A10)
    a.label("flags_ready")
    # Do not clear the prefix: previous_sf may alias output_sf on gr1.
    load(5, 4, 8)
    load(7, 4, 12)
    load(11, 4, 6)
    for part in range(4):
        load(6, 9, part*2)
        cmpi(6, 0)
        a.ajmp(f"part_done_{part}", 1)
        mov(13, 10)
        if part: a.emit(0x4DD0 | part*4)
        a.emit(0x74FD, 15)
        mov(0, 8)
        a.emit(0x74F0, 8 >> part)
        a.ajmp(f"reuse_{part}", 2)
        imm(1, 1)
        mov(0, 13)
        cmpi(0, 0)
        a.ajmp(f"max_ready_{part}", 1)
        a.label(f"max_{part}")
        a.emit(0x4C11, 0x5201)
        a.ajmp(f"max_{part}", 2)
        a.label(f"max_ready_{part}")
        a.emit(0x5211)
        a.label(f"read_{part}")
        mov(0, 13)
        a.emit(0xBD00 | (read_bits >> 16), read_bits & 65535, 0x1A50)
        cmpi(14, 0)
        a.ajmp(f"mask_zero_{part}", 1)
        a.emit(0x1601)
        a.ajmp(f"mask_zero_{part}", 2)
        imm(0, 1)
        a.ajmp(f"mask_store_{part}")
        a.label(f"mask_zero_{part}")
        imm(0, 0)
        a.label(f"mask_store_{part}")
        a.emit(0x1A70, 0x50B2, 0x5261)
        a.ajmp(f"read_{part}", 2)
        a.ajmp(f"part_done_{part}")
        a.label(f"reuse_{part}")
        # R11 is FP: dereferencing it always reads internal SRAM, even
        # when DS0 selects caller-owned RAM. Use an ordinary data pointer.
        mov(1, 11)
        a.emit(0x3801, 0x1A50)
        mov(11, 1)
        imm(0, 0)
        a.emit(0x1A70, 0x5261)
        a.ajmp(f"reuse_{part}", 2)
        a.label(f"part_done_{part}")
    # Zero all unused scalefactor/mask slots up to 39 (not just slot 21).
    load(1, 4, 8)
    a.emit(0x70F1, 78)
    imm(0, 0)
    a.label("tail")
    a.emit(0x1651)
    a.ajmp("done", 6)
    a.emit(0x1A50, 0x1A70)
    a.ajmp("tail")
    a.label("done")
    mov(0, 3)
    imm(2, 0)
    a.ajmp("return")
    for name, status in (("invalid", 2), ("short", 1), ("budget", 3)):
        a.label(name)
        imm(2, status)
        imm(0, 0)
        a.ajmp("return")
    a.label("return")
    a.emit(0x1F91, 0x1F90)
    for r in reversed((1, *range(3, 15))): pop(r)
    a.emit(0xC620)
    code = struct.pack(f"<{len(a.words)}H", *a.finish())
    data = tables()
    assert address % 2 == 0 and (address & 0xffff)+len(code) <= 0x10000
    assert (table_address & 0x7fff)+len(data) <= 0x8000
    return {"code": code, "tables": data, "code_address": address,
            "table_address": table_address, "entries": a.labels, "libmad_sha256": MAD_SHA}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    core = build()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {k: v for k, v in core.items() if k not in ("code", "tables")}
    for key in ("code", "tables"):
        (args.output / (key+".bin")).write_bytes(core[key])
        manifest[key+"_bytes"] = len(core[key])
        manifest[key+"_sha256"] = hashlib.sha256(core[key]).hexdigest()
    manifest.update(factory_rom_patch=False, complete_mp3_decoder=False)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
