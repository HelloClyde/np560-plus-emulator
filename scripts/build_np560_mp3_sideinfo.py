#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""DMCU Layer III side information, based on libmad III_sideinfo.

New internal ABI, not a factory ROM replacement. R0=lsf (0/1), R1=nch
(1/2), R3=near output (72 words), R12=the entropy core's bit context.
Return R0=consumed bits, R2=status; preserve all other GPRs and DS.
0=success, 1=short input, 2=bad arguments/context, 3=bad big_values,
4=bad block_type, 5=bad scfsi. Preflight errors change no input/output.
Semantic errors consume the full side information and produce diagnostic
fields, but those fields must NOT be used to decode an invalid frame.
Buffers/context must be valid, word aligned, and nonoverlapping with stack.
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

ADDRESS = 0x202000
HEADER = ("main_data_begin", "private_bits", "scfsi0", "scfsi1",
          "data_bitlen", "nch", "ngr", "side_bits")
CHANNEL = ("part2_3_length", "big_values", "global_gain", "scalefac_compress",
           "flags", "block_type", "table0", "table1", "table2",
           "subgain0", "subgain1", "subgain2", "region0", "region1",
           "window_switching", "reserved")
WORDS = len(HEADER) + 4*len(CHANNEL)


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
    def store(base, offset, reg=0):
        ptr(base, offset)
        a.emit(0x0A10 | reg)
    def load(base, offset):
        ptr(base, offset)
        a.emit(0x2801)
    def read(width=None):
        if width is not None: imm(0, width)
        a.emit(0xBD00 | (read_bits >> 16), read_bits & 65535)
    def field(width, offset):
        read(width)
        store(5, offset)
    serial = 0

    def error(status):
        nonlocal serial
        label = f"error_set_{serial}"
        serial += 1
        cmpi(10, 0)
        a.ajmp(label, 2)
        imm(10, status)
        a.label(label)

    a.label("sideinfo")
    for r in (1, *range(3, 15)): push(r)
    a.emit(0x1F10, 0x1F11, *select_workspace(workspace_bank))
    mov(6, 0)
    mov(8, 1)
    mov(4, 3)
    cmpi(6, 1)
    a.ajmp("invalid", 0xA)
    cmpi(8, 1)
    a.ajmp("invalid", 5)
    cmpi(8, 2)
    a.ajmp("invalid", 0xA)
    # Preflight the whole fixed-length sideinfo before mutating anything.
    imm(7, 1)
    imm(11, 72)
    cmpi(6, 0)
    a.ajmp("lsf_size", 2)
    imm(7, 2)
    imm(11, 136)
    a.label("lsf_size")
    cmpi(8, 1)
    a.ajmp("size_ready", 1)
    a.emit(0x4C71)
    imm(11, 136)
    cmpi(6, 0)
    a.ajmp("size_ready", 2)
    imm(11, 256)
    a.label("size_ready")
    load(12, 6)
    cmpi(0, 16)
    a.ajmp("invalid", 0xA)
    load(12, 8)
    a.emit(0x160B)
    a.ajmp("short", 5)
    mov(5, 4)
    imm(1, WORDS)
    imm(0, 0)
    a.label("clear")
    a.emit(0x1A50, 0x5211)
    a.ajmp("clear", 2)
    store(4, 10, 8)
    store(4, 14, 11)
    imm(0, 1)
    cmpi(6, 0)
    a.ajmp("ngr_ready", 2)
    imm(0, 2)
    a.label("ngr_ready")
    store(4, 12)
    imm(0, 8)
    cmpi(6, 0)
    a.ajmp("mdb_width", 2)
    imm(0, 9)
    a.label("mdb_width")
    read()
    store(4, 0)
    # private bit width: MPEG1 mono/stereo 5/3; LSF mono/stereo 1/2.
    mov(0, 8)
    cmpi(6, 0)
    a.ajmp("private_width", 2)
    imm(0, 5)
    cmpi(8, 1)
    a.ajmp("private_width", 1)
    imm(0, 3)
    a.label("private_width")
    read()
    store(4, 2)
    cmpi(6, 0)
    a.ajmp("scfsi_done", 2)
    read(4)
    store(4, 4)
    cmpi(8, 1)
    a.ajmp("scfsi_done", 1)
    read(4)
    store(4, 6)
    a.label("scfsi_done")
    mov(5, 4)
    a.emit(0x70F5, 16)
    imm(9, 0)
    imm(10, 0)
    imm(11, 0)
    a.label("channel")
    field(12, 0)
    a.emit(0x10B0)
    field(9, 2)
    cmpi(0, 288)
    a.ajmp("big_ok", 0xC)  # unsigned <=, including the legal 288 boundary
    error(3)
    a.label("big_ok")
    field(8, 4)
    imm(0, 4)
    cmpi(6, 0)
    a.ajmp("sf_width", 1)
    imm(0, 9)
    a.label("sf_width")
    read()
    store(5, 6)
    field(1, 28)
    cmpi(0, 0)
    a.ajmp("long", 1)
    field(2, 10)
    cmpi(0, 0)
    a.ajmp("block_ok", 2)
    error(4)
    a.label("block_ok")
    cmpi(0, 2)
    a.ajmp("scfsi_ok", 2)
    cmpi(6, 0)
    a.ajmp("scfsi_ok", 2)
    mov(1, 9)
    a.emit(0x4C11, 0x5014, 0x1014, 0x2801)
    cmpi(0, 0)
    a.ajmp("scfsi_ok", 1)
    error(5)
    a.label("scfsi_ok")
    read(1)
    a.emit(0x4C03)
    store(5, 8)
    cmpi(0, 0)
    a.ajmp("region_seven", 2)
    load(5, 10)
    cmpi(0, 2)
    a.ajmp("region_seven", 2)
    imm(0, 8)
    a.ajmp("region_ready")
    a.label("region_seven")
    imm(0, 7)
    a.label("region_ready")
    store(5, 24)
    # libmad sentinel for switched blocks; later band logic clamps it.
    imm(0, 36)
    store(5, 26)
    field(5, 12)
    field(5, 14)
    for offset in (18, 20, 22): field(3, offset)
    a.ajmp("tail_flags")
    a.label("long")
    for offset in (12, 14, 16): field(5, offset)
    field(4, 24)
    field(3, 26)
    a.label("tail_flags")
    imm(0, 2)
    cmpi(6, 0)
    a.ajmp("flags_width", 2)
    imm(0, 3)
    a.label("flags_width")
    read()
    ptr(5, 8)
    a.emit(0x2811, 0x1001)
    store(5, 8)
    a.emit(0x70F5, 32, 0x5091, 0x1698)
    a.ajmp("channel_index", 2)
    imm(9, 0)
    a.label("channel_index")
    a.emit(0x5271)
    a.ajmp("channel", 2)
    store(4, 8, 11)
    load(4, 14)
    mov(2, 10)
    a.ajmp("return")
    a.label("invalid")
    imm(2, 2)
    a.ajmp("no_consumption")
    a.label("short")
    imm(2, 1)
    a.label("no_consumption")
    imm(0, 0)
    a.label("return")
    a.emit(0x1F91, 0x1F90)
    for r in reversed((1, *range(3, 15))): pop(r)
    a.emit(0xC620)
    code = struct.pack(f"<{len(a.words)}H", *a.finish())
    if address & 1 or (address & 0xffff)+len(code) > 0x10000:
        raise ValueError("sideinfo placement overlaps entropy core/tables")
    return {"code": code, "code_address": address, "entries": a.labels,
            "output_words": WORDS, "header": HEADER, "channel": CHANNEL}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    core = build()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "sideinfo.bin").write_bytes(core["code"])
    manifest = {k: v for k, v in core.items() if k != "code"}
    manifest.update(code_bytes=len(core["code"]), code_sha256=hashlib.sha256(core["code"]).hexdigest(),
                    factory_rom_patch=False, complete_mp3_decoder=False)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
