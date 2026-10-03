#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native DMCU Layer III Huffman core, NOT a factory ROM entry replacement.

Build-time tables: saved FFmpeg LGPL-2.1+ MPEG tables. Algorithm reference:
libmad bit.c/layer3.c, GPL-2.0+. See doc/audio/np560_mp3_guest_decoder.md.
No decoding is performed by a QEMU helper or host callback.
"""
from __future__ import annotations

import hashlib
import argparse
import json
from pathlib import Path
import struct

from np560_assembler import _DMCUAssembler
from np560_mp3_workspace import select_workspace
from scan_np560_mpeg_tables import array

ROOT = Path(__file__).resolve().parents[1]
TABLE_SOURCE = ROOT / "doc/sources/ffmpeg-mpeg-tables-20260907/mpegaudiodec_common.c"
TABLE_SHA = "e6a415c3c47670217b49a97ca71adbbed4d98433d852e276539293465cb67151"
BOOKS = (1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16, 24)
CODE_ADDRESS = 0x201000
TABLE_ADDRESS = 0x204000


def codebooks():
    """Expand FFmpeg's lexically ordered lengths, without sorting lengths."""
    raw = TABLE_SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != TABLE_SHA:
        raise ValueError("reference MPEG table identity changed")
    source = raw.decode("utf-8")
    lengths, symbols = array(source, "mpa_hufflens"), array(source, "mpa_huffsymbols")
    sizes = [n + 1 for n in array(source, "mpa_huff_sizes_minus_one")]
    mapping = array(source, "ff_mpa_huff_data")
    base, cursor = {0: {0: ""}}, 0
    assert len(BOOKS) == len(sizes)
    for book, size in zip(BOOKS, sizes):
        entries, code = {}, 0
        for length, symbol in zip(lengths[cursor:cursor+size], symbols[cursor:cursor+size]):
            unit = 1 << (32-length)
            if code % unit:
                raise ValueError("non-prefix-aligned Huffman code")
            entries[symbol] = f"{code >> (32-length):0{length}b}"
            code += unit
        assert code == 1 << 32 and len(entries) == size
        base[book], cursor = entries, cursor + size
    assert cursor == len(lengths) == len(symbols)
    result = {}
    for book in range(32):
        if book in (4, 14):
            continue
        index, linbits = mapping[2*book:2*book+2]
        result[book] = (base[BOOKS[index-1]] if index else base[0], linbits)
    codes, bits = array(source, "mpa_quad_codes"), array(source, "mpa_quad_bits")
    for book in (32, 33):
        offset = (book-32)*16
        result[book] = ({i: f"{codes[offset+i]:0{bits[offset+i]}b}" for i in range(16)}, 0)
    return result


def tables(books):
    # A node is two 16-bit child offsets relative to the entire table block.
    # Leaves have bit15 set and contain an xy nibble pair or v/w/x/y mask.
    words = [0] * (34*2)
    shared = {}

    def tree(entries):
        node = {}
        for symbol, bits in entries.items():
            cursor = node
            for bit in bits:
                assert "leaf" not in cursor
                cursor = cursor.setdefault(bit, {})
            assert not cursor
            cursor["leaf"] = symbol

        def emit(node):
            if "leaf" in node:
                return 0x8000 | node["leaf"]
            assert set(node) == {"0", "1"}
            index = len(words)
            words.extend((0, 0))
            words[index], words[index+1] = emit(node["0"]), emit(node["1"])
            return index*2
        return emit(node)

    for book, (entries, linbits) in books.items():
        key = tuple(entries.items())
        if key not in shared:
            shared[key] = tree(entries)
        words[book*2:book*2+2] = [shared[key], linbits]
    assert len(words)*2 < 0x4000
    return struct.pack(f"<{len(words)}H", *words)


def build(code_address=CODE_ADDRESS, table_address=TABLE_ADDRESS, workspace_bank=0):
    """Return native code/tables and addresses; no factory ROM is patched.

    New internal ABI: R12 -> five near words {DS bank, next word pointer
    with bit15 set, left-aligned cache, cached bits, available bits}.
    Words contain stream bytes in network/MSB-first order. This is an
    explicit core boundary, not a claim about the original input-ring ABI.
    read_bits: R0=0..16 -> R0=value, R2=status; preserves R1,R3..R14,banks.
    huffman: R0=book(0..33) -> R0,R1,R3,R4=values, R2=status;
    preserves R5..R14,banks. Pair books return R3=R4=0.
    Status: 0 success, 1 insufficient bits, 2 invalid request. Huffman errors
    restore all five stream words, allowing a caller to refill/retry.
    Context/data must be valid allocated memory; it is not a public ABI.
    """
    if code_address & 1 or table_address & 1:
        raise ValueError("unaligned placement")
    table_bank = table_address >> 15
    table_ptr = 0x8000 | (table_address & 0x7fff)
    a = _DMCUAssembler(code_address)

    def imm(r, value): a.emit(0x68F0 | r, value)
    def mov(dst, src): a.emit(0x0800 | dst << 4 | src)
    def load(dst, offset):
        mov(1, 12)
        if offset: a.emit(0x5010 | offset)
        a.emit(0x2801 | dst << 4)
    def save(src, offset):
        mov(1, 12)
        if offset: a.emit(0x5010 | offset)
        a.emit(0x0A00 | 1 << 4 | src)
    def cmpi(r, value): a.emit(0x76F0 | r, value)
    def push(r): a.emit(0x58F0 | r)
    def pop(r): a.emit(0x380F | r << 4)

    a.label("read_bits")
    a.acall("bits")
    a.emit(0xC620)
    a.label("huffman")
    for r in range(5, 12): push(r)
    a.emit(0x1F10, 0x1F11, *select_workspace(workspace_bank))
    for offset in range(0, 10, 2):
        load(5, offset)
        push(5)
    cmpi(0, 33)
    a.ajmp("invalid", 0xA)
    for reserved in (4, 14):
        cmpi(0, reserved)
        a.ajmp("invalid", 1)
    mov(10, 0)
    a.emit(0x6811, table_bank, 0x4C02, 0x70F0, table_ptr)
    # Descriptor {root,linbits}; R0 is now a banked table pointer.
    a.emit(0x3850, 0x2870)
    a.label("node")
    cmpi(5, 0x8000)
    a.ajmp("leaf", 6)
    imm(0, 1)
    a.acall("bits")
    cmpi(2, 0)
    a.ajmp("rollback", 2)
    a.emit(0x4C01, 0x1050, 0x70F5, table_ptr, 0x2855)
    a.ajmp("node")
    a.label("leaf")
    mov(6, 5)
    a.emit(0x74F6, 0xFF)
    cmpi(10, 32)
    a.ajmp("quad", 6)
    mov(0, 6)
    a.emit(0x4D04)
    a.acall("value")
    cmpi(2, 0)
    a.ajmp("rollback", 2)
    mov(8, 0)
    mov(0, 6)
    a.emit(0x74F0, 15)
    a.acall("value")
    cmpi(2, 0)
    a.ajmp("rollback", 2)
    mov(9, 0)
    imm(10, 0)
    imm(11, 0)
    a.ajmp("success")
    a.label("quad")
    imm(7, 0)
    for index, target in enumerate((8, 9, 10, 11)):
        mov(0, 6)
        if index != 3: a.emit(0x4D00 | (3-index))
        a.emit(0x74F0, 1)
        a.acall("value")
        cmpi(2, 0)
        a.ajmp("rollback", 2)
        mov(target, 0)
    a.label("success")
    mov(0, 8)
    mov(1, 9)
    mov(3, 10)
    mov(4, 11)
    imm(2, 0)
    a.emit(0x50FA)
    a.ajmp("restore")
    a.label("invalid")
    imm(2, 2)
    a.label("rollback")
    for offset in reversed(range(0, 10, 2)):
        pop(5)
        save(5, offset)
    for r in (0, 1, 3, 4): imm(r, 0)
    a.label("restore")
    a.emit(0x1F91, 0x1F90)
    for r in reversed(range(5, 12)): pop(r)
    a.emit(0xC620)

    # Decode an escape value followed immediately by its own sign bit,
    # before processing the other value (libmad layer3.c ordering).
    a.label("value")
    push(5)
    mov(5, 0)
    cmpi(0, 15)
    a.ajmp("sign", 2)
    cmpi(7, 0)
    a.ajmp("sign", 1)
    mov(0, 7)
    a.acall("bits")
    cmpi(2, 0)
    a.ajmp("value_end", 2)
    a.emit(0x1050)
    a.label("sign")
    cmpi(5, 0)
    a.ajmp("value_ok", 1)
    imm(0, 1)
    a.acall("bits")
    cmpi(2, 0)
    a.ajmp("value_end", 2)
    cmpi(0, 0)
    a.ajmp("value_ok", 1)
    # 0 - magnitude, using an ordinary register subtraction.
    imm(0, 0)
    a.emit(0x1205)
    mov(5, 0)
    a.label("value_ok")
    mov(0, 5)
    imm(2, 0)
    a.label("value_end")
    pop(5)
    a.emit(0xC600)

    a.label("bits")
    for r in (1, 3, 4, 5, 6, 7, 9): push(r)
    a.emit(0x1F10, 0x1F11, *select_workspace(workspace_bank))
    cmpi(0, 16)
    a.ajmp("bits_invalid", 0xA)
    load(6, 8)
    a.emit(0x1660)  # CMP R6,R0
    a.ajmp("bits_short", 5)
    load(7, 0)
    load(3, 2)
    load(4, 4)
    load(5, 6)
    cmpi(5, 16)
    a.ajmp("bits_invalid", 0xA)
    a.emit(0x1260)  # SUB R6,R0
    mov(9, 0)
    imm(0, 0)
    cmpi(9, 0)
    a.ajmp("bits_commit", 1)
    a.label("bit_loop")
    cmpi(5, 0)
    a.ajmp("cached", 2)
    push(7)
    a.emit(0x1F91, 0x2843, 0x5032)  # DS1=R7; cache=[R3]; ptr+=2
    a.ajmp("not_wrap", 2)
    imm(3, 0x8000)
    a.emit(0x5071)
    a.label("not_wrap")
    imm(5, 16)
    a.label("cached")
    a.emit(0x4C01, 0x4C41, 0x71F0, 0, 0x5251, 0x5291)
    a.ajmp("bit_loop", 2)
    a.label("bits_commit")
    for r, offset in ((7, 0), (3, 2), (4, 4), (5, 6), (6, 8)): save(r, offset)
    imm(2, 0)
    a.ajmp("bits_end")
    a.label("bits_short")
    imm(2, 1)
    imm(0, 0)
    a.ajmp("bits_end")
    a.label("bits_invalid")
    imm(2, 2)
    imm(0, 0)
    a.label("bits_end")
    a.emit(0x1F91, 0x1F90)
    for r in reversed((1, 3, 4, 5, 6, 7, 9)): pop(r)
    a.emit(0xC600)

    code = struct.pack(f"<{len(a.words)}H", *a.finish())
    data = tables(codebooks())
    if (code_address & 0xffff)+len(code) > 0x10000 or (table_address & 0x7fff)+len(data) > 0x8000:
        raise ValueError("core/table placement overlaps or crosses table bank")
    return {"code": code, "tables": data, "entries": a.labels,
            "code_address": code_address, "table_address": table_address,
            "table_source_sha256": TABLE_SHA}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    core = build()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {key: value for key, value in core.items() if key not in ("code", "tables")}
    for key in ("code", "tables"):
        (args.output / (key+".bin")).write_bytes(core[key])
        manifest[key+"_bytes"] = len(core[key])
        manifest[key+"_sha256"] = hashlib.sha256(core[key]).hexdigest()
    manifest.update(factory_rom_patch=False, complete_mp3_decoder=False, license="GPL-2.0-or-later")
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
