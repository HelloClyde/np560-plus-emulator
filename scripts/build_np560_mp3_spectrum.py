#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native part2/part3 -> 576 signed quantized integers, NOT PCM.

R12=bit context; R3=4 near words {sf_descriptor, frequency_index,
quantized_output, metrics}. Frequency indices follow FFmpeg's 9-row table:
44100,48000,32000,22050,24000,16000,11025,12000,8000.
Metrics: {part2_bits, big_value_lines, coded_lines, stuffing_bits}.
R0=coded lines,R2=status; preserve other GPRs and DS. Status 1=short
whole segment,2=invalid geometry (no mutation); 3=scalefactor failure,
4=bad Huffman table,5=truncated big_values. Semantic errors drain the
declared part2_3 segment and invalidate output; caller MUST reject it.
Success also drains stuffing and preserves following segments' cached bits.
Caller owns aligned, nonoverlapping DS0=0 near arrays (quantized:576 words,
metrics:4 words), SF descriptors/state and reset/frame lifecycle.
"""
from __future__ import annotations

import hashlib
import argparse
import json
from pathlib import Path
import struct

from build_np560_mp3_huffman import build as build_entropy, TABLE_SOURCE, TABLE_SHA
from build_np560_mp3_scalefactors import build as build_sf
from np560_assembler import _DMCUAssembler
from np560_mp3_workspace import select_workspace
from scan_np560_mpeg_tables import array

ADDRESS, TABLE_ADDRESS = 0x20A000, 0x207000


def tables(address=TABLE_ADDRESS):
    raw = TABLE_SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == TABLE_SHA
    widths = array(raw.decode(), "ff_band_size_long")
    assert len(widths) == 198
    ptr = 0x8000 | (address & 0x7fff)
    words = [ptr+18+i*46 for i in range(9)]
    for row in range(9):
        boundaries = [0]
        for width in widths[row*22:row*22+22]: boundaries.append(boundaries[-1]+width)
        assert boundaries[-1] == 576
        words += boundaries
    return struct.pack(f"<{len(words)}H", *words)


def build(address=ADDRESS, table_address=TABLE_ADDRESS, workspace_bank=0, *, entropy=None, sf=None):
    entropy = entropy or build_entropy(workspace_bank=workspace_bank)
    sf = sf or build_sf(workspace_bank=workspace_bank)
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
    def store(base, offset, reg):
        ptr(base, offset)
        a.emit(0x0A10 | reg)
    def call(entry): a.emit(0xBD00 | entry >> 16, entry & 65535)
    def metric(offset, reg):
        load(3, 5, 6)
        store(3, offset, reg)
    def push(r): a.emit(0x58F0 | r)
    def pop(r): a.emit(0x380F | r << 4)

    a.label("spectrum")
    for r in (1, *range(3, 15)): push(r)
    a.emit(0x1F10, 0x1F11, *select_workspace(workspace_bank), 0x6811, table_address >> 15)
    mov(5, 3)
    load(3, 5, 0)
    load(6, 3, 2)
    load(4, 5, 2)
    cmpi(4, 8)
    a.ajmp("invalid", 0xA)
    load(0, 6, 0)
    cmpi(0, 4095)
    a.ajmp("invalid", 0xA)
    load(8, 6, 2)
    cmpi(8, 288)
    a.ajmp("invalid", 0xA)
    load(2, 12, 6)
    cmpi(2, 16)
    a.ajmp("invalid", 0xA)
    load(13, 12, 8)
    a.emit(0x16D0)
    a.ajmp("short", 5)
    a.emit(0x12D0)  # available beyond THIS part2_3 segment
    load(2, 6, 28)
    cmpi(2, 1)
    a.ajmp("invalid", 0xA)
    cmpi(2, 0)
    a.ajmp("long", 1)
    load(2, 6, 10)
    cmpi(2, 0)
    a.ajmp("invalid", 1)
    cmpi(2, 3)
    a.ajmp("invalid", 0xA)
    imm(9, 36)
    imm(10, 576)
    cmpi(2, 2)
    a.ajmp("start_stop", 2)
    cmpi(4, 8)
    a.ajmp("regions_ready", 2)
    imm(9, 72)
    a.ajmp("regions_ready")
    a.label("start_stop")
    cmpi(4, 2)
    a.ajmp("regions_ready", 0xC)
    imm(9, 54)
    cmpi(4, 8)
    a.ajmp("regions_ready", 2)
    imm(9, 108)
    a.ajmp("regions_ready")
    a.label("long")
    load(9, 6, 24)
    cmpi(9, 15)
    a.ajmp("invalid", 0xA)
    load(10, 6, 26)
    cmpi(10, 7)
    a.ajmp("invalid", 0xA)
    mov(3, 4)
    a.emit(0x4C31, 0x70F3, 0x8000 | (table_address & 0x7fff), 0x2833,
           0x5091, 0x10A9, 0x50A1)
    cmpi(10, 22)
    a.ajmp("region_clamped", 0xC)
    imm(10, 22)
    a.label("region_clamped")
    a.emit(0x4C91, 0x1093, 0x2899, 0x4CA1, 0x10A3)
    # R10 is X2: copy pointer to ordinary R1 before dereferencing.
    mov(1, 10)
    a.emit(0x28A1)
    a.label("regions_ready")
    load(0, 6, 0)
    store(12, 8, 0)
    imm(0, 0)
    load(3, 5, 6)
    for offset in (0, 2, 4, 6): store(3, offset, 0)
    load(7, 5, 4)
    imm(4, 576)
    a.label("clear")
    a.emit(0x1A70, 0x5241)
    a.ajmp("clear", 2)
    load(7, 5, 4)
    imm(11, 0)
    imm(14, 0)
    load(3, 5, 0)
    call(sf["entries"]["scalefactors"])
    metric(0, 0)
    cmpi(2, 0)
    a.ajmp("sf_ok", 1)
    imm(14, 3)
    a.ajmp("finish")
    a.label("sf_ok")
    mov(0, 8)
    a.emit(0x4C01)
    metric(2, 0)
    cmpi(8, 0)
    a.ajmp("count1", 1)
    a.label("pair")
    a.emit(0x16B9)
    a.ajmp("book0", 5)
    a.emit(0x16BA)
    a.ajmp("book1", 5)
    load(0, 6, 16)
    a.ajmp("decode_pair")
    a.label("book0")
    load(0, 6, 12)
    a.ajmp("decode_pair")
    a.label("book1")
    load(0, 6, 14)
    a.label("decode_pair")
    cmpi(0, 31)
    a.ajmp("pair_book_valid", 0xC)
    imm(2, 2)
    a.ajmp("pair_error")
    a.label("pair_book_valid")
    call(entropy["entries"]["huffman"])
    cmpi(2, 0)
    a.ajmp("pair_error", 2)
    a.emit(0x1A70, 0x1A71, 0x50B2, 0x5281)
    a.ajmp("pair", 2)
    a.label("count1")
    cmpi(11, 572)
    a.ajmp("finish", 0xA)
    load(0, 12, 8)
    cmpi(0, 0)
    a.ajmp("finish", 1)
    load(0, 6, 8)
    a.emit(0x74F0, 1, 0x70F0, 32)
    call(entropy["entries"]["huffman"])
    cmpi(2, 1)
    a.ajmp("finish", 1)  # transactional underflow means stuffing bits
    cmpi(2, 0)
    a.ajmp("pair_error", 2)
    a.emit(0x1A70, 0x1A71, 0x1A73, 0x1A74, 0x50B4)
    a.ajmp("count1")
    a.label("pair_error")
    imm(14, 5)
    cmpi(2, 2)
    a.ajmp("finish", 2)
    imm(14, 4)
    a.label("finish")
    metric(4, 11)
    load(0, 12, 8)
    metric(6, 0)
    a.label("drain")
    load(0, 12, 8)
    cmpi(0, 0)
    a.ajmp("drained", 1)
    cmpi(0, 16)
    a.ajmp("drain_width", 0xC)
    imm(0, 16)
    a.label("drain_width")
    call(entropy["entries"]["read_bits"])
    a.ajmp("drain")
    a.label("drained")
    store(12, 8, 13)
    mov(0, 11)
    mov(2, 14)
    a.ajmp("return")
    for name, status in (("short", 1), ("invalid", 2)):
        a.label(name)
        imm(0, 0)
        imm(2, status)
        a.ajmp("return")
    a.label("return")
    a.emit(0x1F91, 0x1F90)
    for r in reversed((1, *range(3, 15))): pop(r)
    a.emit(0xC620)
    code = struct.pack(f"<{len(a.words)}H", *a.finish())
    data = tables(table_address)
    assert address % 2 == 0 and (address & 0xffff)+len(code) <= 0x10000
    assert table_address % 2 == 0 and (table_address & 0x7fff)+len(data) <= 0x8000
    return {"code": code, "tables": data, "code_address": address,
            "table_address": table_address, "entries": a.labels}


def main():
    from build_np560_mp3_sideinfo import build as build_side
    from build_np560_mp3_reservoir import build as build_reservoir

    parser = argparse.ArgumentParser(description="Build native MP3 front-end fragments, NOT a bootable ROM/player")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cores = {"entropy": build_entropy(), "sideinfo": build_side(), "reservoir": build_reservoir(),
             "scalefactors": build_sf(), "spectrum": build()}
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {"components": {}, "factory_rom_patch": False, "end_to_end_frame_driver": False,
                "pcm_produced": False, "complete_mp3_decoder": False, "license": "GPL-2.0-or-later"}
    for name, core in cores.items():
        component = {"entries": core["entries"], "fragments": []}
        for key, address in (("code", "code_address"), ("tables", "table_address")):
            if key not in core: continue
            filename = f"{name}-{key}.bin"
            (args.output / filename).write_bytes(core[key])
            component["fragments"].append({"file": filename, "address": core[address], "bytes": len(core[key]),
                                           "sha256": hashlib.sha256(core[key]).hexdigest()})
        manifest["components"][name] = component
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({name: component["fragments"] for name, component in manifest["components"].items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
