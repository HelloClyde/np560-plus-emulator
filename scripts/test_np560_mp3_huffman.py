#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run the new Layer III entropy core as DMCU instructions, without NAND/HLE.

Full codeword tables are independently checked against libmad's different
lookup-table representation. Test bitstreams are explicitly synthetic
entropy symbols, NOT MP3 frames or decoded PCM.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from build_np560_mp3_huffman import ROOT, build, codebooks
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr, read_word, write_word
from test_np560_mac import run

MAD_SOURCE = ROOT / "doc/sources/libmad-20260907/huffman.c"
MAD_SHA = "ab7bbad837fda91d8382b936d86c53cb8f415404f20da568294fe099730a5c22"


def check_libmad(books):
    raw = MAD_SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MAD_SHA
    source = re.sub(r"/\*.*?\*/", "", raw.decode("utf-8"), flags=re.S)
    parsed = {}
    for kind, name, body in re.findall(
            r"union (huffpair|huffquad) const (hufftab\w+)\[\]\s*=\s*\{(.*?)\};", source, re.S):
        parsed[name] = (kind, [(op, [int(v.strip()) for v in args.split(",")])
                              for op, args in re.findall(r"\b(PTR|V)\(([^)]+)\)", body)])
    header = source.split("mad_huff_pair_table[32] =", 1)[1].split("};", 1)[0]
    descriptors = re.findall(r"\{([^{}]*)\}", header)
    assert len(descriptors) == 32
    reference = {}

    def expand(name, startbits):
        kind, table = parsed[name]
        found = {}

        def walk(offset, width, prefix):
            assert len(prefix) <= 19
            for index in range(1 << width):
                op, fields = table[offset+index]
                bits = f"{index:0{width}b}" if width else ""
                if op == "PTR":
                    walk(fields[0], fields[1], prefix+bits)
                else:
                    values, length = fields[:-1], fields[-1]
                    symbol = 0
                    for value in values:
                        symbol = symbol * (16 if kind == "huffpair" else 2) + value
                    code = prefix+bits[:length]
                    if symbol in found:
                        assert found[symbol] == code
                    found[symbol] = code
        walk(0, startbits, "")
        return found

    for book, fields in enumerate(descriptors):
        match = re.fullmatch(r"\s*(hufftab\w+),\s*(\d+),\s*(\d+)\s*", fields)
        if not match:
            assert book in (4, 14)
            continue
        name, linbits, start = match.groups()
        reference[book] = expand(name, int(start)), int(linbits)
    for book, name in ((32, "hufftabA"), (33, "hufftabB")):
        reference[book] = expand(name, 4), 0
    assert reference == books, "FFmpeg/libmad codewords or linbits disagree"
    return {"libmad_sha256": MAD_SHA, "books_checked": len(reference),
            "codeword_entries_checked": sum(len(codes) for codes, _ in reference.values())}


def symbol_bits(book, code, symbol, linbits, signs=0, escape=0):
    if book < 32:
        magnitudes = [symbol >> 4, symbol & 15]
    else:
        magnitudes = [(symbol >> n) & 1 for n in (3, 2, 1, 0)]
    bits, values = code, []
    for index, magnitude in enumerate(magnitudes):
        if magnitude == 15 and linbits:
            extra = escape & ((1 << linbits)-1)
            bits += f"{extra:0{linbits}b}"
            magnitude += extra
        sign = (signs >> index) & 1
        if magnitude:
            bits += str(sign)
        values.append(-magnitude if sign and magnitude else magnitude)
    return bits, values + [0]*(4-len(values))


def vector(book, bits, values, *, available=None, status=0):
    # Add nonzero unrelated tail bits: consuming one extra bit must fail
    # the context comparison even when decoded magnitudes happen to match.
    stream = bits + "10110101101"
    assert len(stream) <= 64
    return {"book": book, "stream": stream,
            "available": len(stream) if available is None else available,
            "consumed": len(bits) if status == 0 else 0,
            "values": values if status == 0 else [0]*4, "status": status}


def vectors(book, codes, linbits):
    result = []
    for symbol, code in codes.items():
        bits, values = symbol_bits(book, code, symbol, linbits,
                                   signs=(symbol ^ book) & 15,
                                   escape=(1 << linbits)-1 if symbol & 1 else 0)
        result.append(vector(book, bits, values))
    # All signs for boundary magnitudes, including maximum escaped values.
    for symbol in set((min(codes), max(codes))):
        for signs in range(4 if book < 32 else 16):
            bits, values = symbol_bits(book, codes[symbol], symbol, linbits,
                                       signs=signs, escape=(1 << linbits)-1)
            result.append(vector(book, bits, values))
            if bits:
                result.append(vector(book, bits, values, available=len(bits)-1, status=1))
    # Check rollback at each point in a longest encoded symbol, including
    # codeword, first escape/sign, second escape/sign and count1 sign bits.
    symbol = max(codes, key=lambda s: len(codes[s]) + (linbits if s >> 4 == 15 else 0)
                 + (linbits if s & 15 == 15 else 0))
    bits, values = symbol_bits(book, codes[symbol], symbol, linbits, signs=15, escape=0x1fff)
    result += [vector(book, bits, values, available=n, status=1) for n in range(len(bits))]
    if book == 0:
        result.append(vector(0, "", [0]*4, available=0))
    return result


def expected_state(vector, bank, pointer):
    count = vector["consumed"]
    loaded = (count+15)//16
    absolute = (bank << 15) + (pointer & 0x7fff) + loaded*2
    cache = 0
    if loaded:
        word = int(vector["stream"].ljust(64, "0")[(loaded-1)*16:loaded*16], 2)
        cache = (word << (count - (loaded-1)*16)) & 65535
    return [absolute >> 15, 0x8000 | (absolute & 0x7fff), cache,
            loaded*16-count, vector["available"]-count]


def check_batch(qemu, output, core, name, cases, *, icount=None, bank=0, pointer=0xA200,
                entry="huffman", resident_rom=None):
    rom = None
    if resident_rom is not None:
        rom = bytearray(resident_rom.read_bytes())
        for data,address in ((core["code"],core["code_address"]),(core["tables"],core["table_address"])):
            assert 0x10000 <= address < address+len(data) <= 0x30000
            assert rom[address:address+len(data)] == b"\x00\x0f"*(len(data)//2), "resident placement overwrites existing service"
            rom[address:address+len(data)] = data
    fixture_bank = 8 if rom is not None else 0x42
    a = _DMCUAssembler(0x030000 if rom is not None else 0x200000)
    a.emit(0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, fixture_bank,
           0x68FC, 0x2000, 0x68F9, 0x8000, 0x68FB, 0x4444,
           0x68F6, 0, 0x68F7, 0, 0x68F8, len(cases), 0x68FA, 0x2400)
    for address in (0x1FFE, 0x200A): write_word(a.words, address, 0xCAFE)
    a.label("next")
    a.emit(0x3809, 0x58F0, 0x3809, 0xA8F0, 0x2008)
    for address, value in ((0x2000, bank), (0x2002, pointer), (0x2004, 0), (0x2006, 0)):
        write_word(a.words, address, value)
    for index in range(4):
        absolute = (bank << 15) + (pointer & 0x7fff) + index*2
        a.emit(0x3809, 0x6810, absolute >> 15, 0xA8F0, absolute & 0x7fff)
    a.emit(0x6810, 0, 0x380F)
    if entry == "read_bits":
        a.emit(0x68F1, 0x1234, 0x68F3, 0x3456, 0x68F4, 0x4567)
    a.emit(0xBD00 | (core["entries"][entry] >> 16), core["entries"][entry] & 65535)
    for index, reg in enumerate((0, 1, 3, 4, 2)):
        a.emit(0x1AA0 | reg)
        a.emit(0x3859, 0x1605 | reg << 4)
        a.ajmp(f"out{index}", 1)
        a.emit(0x5061)
        a.label(f"out{index}")
    for index in range(5):
        a.emit(0x3859, 0x88F0, 0x2000+2*index, 0x1AA0, 0x1605)
        a.ajmp(f"state{index}", 1)
        a.emit(0x5061)
        a.label(f"state{index}")
    a.emit(0x5071, 0x5281)
    a.ajmp("next", 2)
    read_sfr(a.words, 0x11, 13)
    read_word(a.words, 0x200A, 10)
    read_word(a.words, 0x1FFE, 14)
    words = a.finish()
    assert len(words)*2+2 < 0x1000
    records, expected_outputs = [], []
    for case in cases:
        raw = case["stream"].ljust(64, "0")
        records += [case["book"], case["available"]]
        records += [int(raw[i:i+16], 2) for i in range(0, 64, 16)]
        records += [v & 65535 for v in case["values"]] + [case["status"]]
        records += expected_state(case, bank, pointer)
        expected_outputs += case["values"] + [case["status"]] + expected_state(case, bank, pointer)
    assert len(records) == len(cases)*16 and len(records)*2 < 0x8000
    payload = bytearray(0x10000+len(records)*2-0x1000)
    if rom is None:
        payload[:len(core["code"])] = core["code"]
        offset = core["table_address"]-core["code_address"]
        payload[offset:offset+len(core["tables"])] = core["tables"]
    payload[0xF000:] = struct.pack(f"<{len(records)}H", *records)
    (output / f"{name}.vectors.json").write_text(json.dumps(cases, indent=2)+"\n", encoding="utf-8")
    result = run(qemu, output, name, words,
               {7: len(cases), 8: 0, 9: 0x8000+len(records)*2, 10: 0xCAFE, 11: 0x4444,
                12: 0x2000, 13: fixture_bank, 14: 0xCAFE, 15: 0x6000},
               rom=rom,boot_mode="firmware-vma03" if rom is not None else "firmware",
               tail=(0x1000, payload), icount=icount,
               expected_code=[(core["code_address"],core["code"])]+
                   ([(core["table_address"],core["tables"])] if rom is not None else []),
               expected_data=[(v & 65535) - (65536 if v & 0x8000 else 0) for v in expected_outputs],
               metadata={"entropy_symbols": len(cases), "input_bank": bank,
                         "input_pointer": pointer, "entry": entry,
                         "native_core_sha256": hashlib.sha256(core["code"]).hexdigest(),
                         "resident_code_and_tables":rom is not None,
                         "resident_input_sha256":hashlib.sha256(resident_rom.read_bytes()).hexdigest() if rom is not None else None,
                         "factory_rom_services_replaced": False, "pcm_produced": False})
    assert result["registers"][6] == 0
    return result


def bit_vectors():
    result = []
    pattern = "1010011011010011" * 4
    for width in range(17):
        for available in (width, max(0, width-1), 32):
            status = 0 if width <= available else 1
            value = int(pattern[:width] or "0", 2) if status == 0 else 0
            result.append({"book": width, "stream": pattern, "available": available,
                           "consumed": width if status == 0 else 0,
                           "values": [value, 0x1234, 0x3456, 0x4567], "status": status})
    for width in (17, 32, 65535):
        result.append({"book": width, "stream": pattern, "available": 32,
                       "consumed": 0, "values": [0, 0x1234, 0x3456, 0x4567], "status": 2})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-only", action="store_true")
    parser.add_argument("--bits-only", action="store_true")
    parser.add_argument("--resident-rom",type=Path,help="test code/tables relocated into checked holes in this ROM, using VMA03; source image is not modified")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    books = codebooks()
    core = build(0x012400,0x01c000) if args.resident_rom else build()
    reference = check_libmad(books)
    (args.output / "core.bin").write_bytes(core["code"])
    (args.output / "tables.bin").write_bytes(core["tables"])
    report = {"passed": False, "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
              "reference": reference, "code_bytes": len(core["code"]), "table_bytes": len(core["tables"]),
              "entries": core["entries"], "pcm_produced": False, "cases": []}
    try:
        selected = () if args.bits_only else ((1,) if args.first_only else books)
        for book in selected:
            codes, linbits = books[book]
            report["cases"].append(check_batch(args.qemu, args.output, core,
                                    f"book-{book}", vectors(book, codes, linbits),resident_rom=args.resident_rom))
        if not args.first_only and not args.bits_only:
            invalid = [vector(book, "", [0]*4, status=2) for book in (4, 14, 34, 65535)]
            report["cases"].append(check_batch(args.qemu, args.output, core, "invalid-books", invalid,resident_rom=args.resident_rom))
            for book in (1, 23, 32, 33):
                codes, linbits = books[book]
                report["cases"].append(check_batch(args.qemu, args.output, core,
                    f"book-{book}-far-wrap-icount5", vectors(book, codes, linbits),
                    bank=0xA0, pointer=0xFFFE, icount=5,resident_rom=args.resident_rom))
        if not args.first_only:
            for icount in (None, 5):
                report["cases"].append(check_batch(args.qemu, args.output, core,
                    f"read-bits-icount{icount}", bit_vectors(), icount=icount, entry="read_bits",resident_rom=args.resident_rom))
        report["passed"] = all(case["passed"] and case["exit_code"] == 0 for case in report["cases"])
    except AssertionError as error:
        detail = error.args[0] if error.args else "assertion failed"
        if isinstance(detail, dict):
            expected = detail.get("expected_samples", [])
            actual = detail.get("actual_samples", [])
            detail = {"name": detail.get("name"), "registers": detail.get("registers"),
                      "first_differences": [(i, got, wanted) for i, (got, wanted)
                                             in enumerate(zip(actual, expected)) if got != wanted][:16]}
        report["failure"] = str(detail)[:1500]
        print(report["failure"], flush=True)
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
