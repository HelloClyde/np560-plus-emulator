#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""DMCU signed Q28 Layer III requantization, not PCM/factory ROM bytes.

scalar: R0=signed quantized integer, R1=signed quarter-power exponent;
return R1:R0=signed Q28, R2=status (0 OK, 2 abs(value)>8206, 3 overflow).
Zero and underflow produce zero successfully. Overflow produces zero and
an error, NEVER wrapped/clipped fake audio. Preserve R3..R14, DS and SOCR.

spectrum: R3 -> six near words {channel16, sf39, frequency_index,
quantized576, q28_output576, band_exponents39}. R0=576/R2=0 on success.
Status 2 is an invalid field/value detected before any output mutation;
3 is arithmetic overflow (partial output must be rejected). Preserve all
GPRs except R0/R2, DS and SOCR. Inputs/output/stack must be allocated,
aligned and nonoverlapping. Output is still in Huffman band/window order:
stereo, short-block reorder, antialias, IMDCT and synthesis follow later.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from build_np560_mp3_huffman import ROOT, TABLE_SOURCE, TABLE_SHA
from build_np560_mp3_scalefactors import MAD_SHA
from np560_assembler import _DMCUAssembler
from np560_mp3_workspace import select_workspace
from np560_mp3_link import code_span, near_table
from scan_np560_mpeg_tables import array

ADDRESS, TABLE_ADDRESS = 0x20A800, 0x210000
ROOT_ADDRESS, GEOMETRY_ADDRESS = 0x218080, 0x218100
RQ_SOURCE = ROOT / "doc/sources/libmad-20260907/rq_table.dat"
RQ_SHA = "125186cf44544395db737348bec72f67d7a234f207b9992ed90c4fa4fecaf4e7"


def table_data(geometry_address=GEOMETRY_ADDRESS):
    raw = RQ_SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RQ_SHA
    rows = re.findall(r"\{\s*MAD_F\(0x([0-9a-fA-F]+)\)\s*/\*.*?\*/\s*,\s*(\d+)\s*\}", raw.decode())
    assert len(rows) == 8207
    words = []
    for mantissa, exponent in rows:
        mantissa, exponent = int(mantissa, 16), int(exponent)
        assert 0 <= mantissa < (1 << 27) and 0 <= exponent < 32
        packed = mantissa | (exponent << 27)
        words += [packed & 65535, packed >> 16]
    powers = struct.pack(f"<{len(words)}H", *words)
    raw_mad = (ROOT / "doc/sources/libmad-20260907/layer3.c").read_bytes()
    assert hashlib.sha256(raw_mad).hexdigest() == MAD_SHA
    mad = raw_mad.decode()
    roots = array(mad, "root_table")
    assert len(roots) == 7
    root_data = struct.pack("<7I", *roots)
    raw_ff = TABLE_SOURCE.read_bytes()
    assert hashlib.sha256(raw_ff).hexdigest() == TABLE_SHA
    long_widths, short_widths = (array(raw_ff.decode(), name) for name in ("ff_band_size_long", "ff_band_size_short"))
    pretab = array(mad, "pretab")
    assert len(long_widths) == 198 and len(short_widths) == 117 and len(pretab) == 22
    geometry, entries = [0]*54, []
    for rate in range(9):
        for mode in range(3):  # long, pure short, mixed short
            long_end = 22 if mode == 0 else (0 if mode == 1 else (8 if rate <= 2 else 6))
            short_start = 13 if mode == 0 else (0 if mode == 1 else 3)
            bands = [(long_widths[rate*22+i], pretab[i], 3) for i in range(long_end)]
            bands += [(short_widths[rate*13+i], 0, win) for i in range(short_start, 13) for win in range(3)]
            assert sum(band[0] for band in bands) == 576 and len(bands) <= 39
            # FFmpeg's 8k mixed layout has 72 long lines, not libmad's
            # explicitly uncertain hardcoded 36-line transition.
            if rate == 8 and mode == 2: assert sum(w for w, _, win in bands if win == 3) == 72
            index = rate*3+mode
            geometry[index*2:index*2+2] = [0x8000 | ((geometry_address + len(geometry)*2) & 0x7fff), len(bands)]
            for band in bands: geometry += band
            entries.append({"rate": rate, "mode": mode, "bands": len(bands), "long_end": long_end, "short_start": short_start})
    geometry_data = struct.pack(f"<{len(geometry)}H", *geometry)
    near_table(geometry_address,geometry_data)
    return powers,root_data,geometry_data,entries


def tables(table_address=TABLE_ADDRESS, root_address=ROOT_ADDRESS, geometry_address=GEOMETRY_ADDRESS):
    powers,roots,geometry,entries = table_data(geometry_address)
    data = bytearray(powers)
    data.extend(bytes(root_address-table_address-len(data)));data.extend(roots)
    data.extend(bytes(geometry_address-table_address-len(data)));data.extend(geometry)
    return bytes(data),entries


def build(address=ADDRESS, workspace_bank=0, *, table_address=TABLE_ADDRESS,
          root_address=ROOT_ADDRESS, geometry_address=GEOMETRY_ADDRESS,
          power_pages=None, power_directory=None, power_page_entries=1024):
    assert power_page_entries in (256,512,1024)
    if power_pages is None:
        assert power_directory is None and table_address % 0x8000 == 0
    else:
        assert len(power_pages)==(8207+power_page_entries-1)//power_page_entries and power_directory is not None
    a = _DMCUAssembler(address)

    def imm(r, val): a.emit(0x68F0 | r, val & 65535)
    def mov(dst, src): a.emit(0x0800 | dst << 4 | src)
    def cmpi(r, val): a.emit(0x76F0 | r, val & 65535)
    def push(r): a.emit(0x58F0 | r)
    def pop(r): a.emit(0x380F | r << 4)
    def load(dst, base, offset):
        mov(1, base)
        if offset: a.emit(0x70F1, offset)
        a.emit(0x2801 | dst << 4)
    def negate(r):
        imm(3, 0)
        a.emit(0x1230 | r)
        mov(r, 3)
    def return_scalar():
        a.emit(0x1F80, 0x1F91, 0x1F90)
        for r in reversed(range(3, 15)): pop(r)
        a.emit(0xC620)

    a.label("scalar")
    for r in range(3, 15): push(r)
    a.emit(0x1F10, 0x1F11, 0x1F00, *select_workspace(workspace_bank))
    # Four full unsigned 16x16 products must not inherit global 32-bit
    # accumulator saturation. Preserve all other SOCR bits, including IRQs.
    a.emit(0x1F00, 0x384F, 0x74F4, 0xFFEF, 0x58F4, 0x1F80)
    imm(14, 0)
    cmpi(0, 0x8000)
    a.ajmp("positive_value", 5)
    imm(14, 1)
    negate(0)
    a.label("positive_value")
    cmpi(0, 8206)
    a.ajmp("invalid_scalar", 0xA)
    cmpi(0, 0)
    a.ajmp("zero", 1)
    mov(12, 1)
    cmpi(12, 0x8000)
    a.ajmp("positive_exp", 5)
    negate(12)
    mov(13, 12)
    a.emit(0x74FD, 3, 0x4DC2)
    negate(12)
    imm(3, 3)
    a.emit(0x123D)
    mov(13, 3)
    a.ajmp("exponent_ready")
    a.label("positive_exp")
    mov(13, 12)
    a.emit(0x74FD, 3, 0x50D3, 0x4DC2)
    a.label("exponent_ready")
    mov(3, 0)
    if power_pages is None:
        # Historical contiguous bank-aligned diagnostic table.
        a.emit(0x4D3D, 0x70F3, table_address >> 15, 0x58F3, 0x1F91,
               0x74F0, 8191, 0x4C02, 0x70F0, 0x8000, 0x0830, 0x3883, 0x2893)
    else:
        # Explicit power-of-two pages of 256..1024 packed entries. The guest
        # reads bank:pointer from a ROM directory; no host table lookup.
        # Each four-byte entry stays in its allocated DS page.
        a.emit(0x4D30|(power_page_entries.bit_length()-1),0x4C32,0x70F3,0x8000|(power_directory&0x7fff),
               0x6811,power_directory>>15,0x3883,0x2833,0x58F8,0x1F91,
               0x74F0,power_page_entries-1,0x4C02,0x1030,0x3883,0x2893)
    mov(3, 9)
    a.emit(0x4D3B, 0x10C3, 0x74F9, 0x07FF)
    cmpi(12, 0x8000)
    a.ajmp("shift_right", 6)
    # A shift of five may exceed signed 32 bits BEFORE multiplication by
    # a negative fractional power, yet the final Q28 value can still fit.
    # Keep that intermediate unsigned, and range-check after the root.
    cmpi(12, 6)
    a.ajmp("overflow", 6)
    cmpi(12, 0)
    a.ajmp("scaled", 1)
    a.label("left_loop")
    a.emit(0x1088, 0x1199, 0x52C1)
    a.ajmp("left_loop", 2)
    a.ajmp("scaled")
    a.label("shift_right")
    negate(12)
    cmpi(12, 32)
    a.ajmp("zero", 6)
    a.label("right_loop")
    mov(4, 8)
    a.emit(0x74F4, 1)
    mov(3, 9)
    a.emit(0x74F3, 1, 0x4C3F, 0x4D81, 0x4D91, 0x1083, 0x52C1)
    a.ajmp("right_loop", 2)
    a.emit(0x1084, 0x71F9, 0)  # half-up rounding at the final discarded bit
    a.label("scaled")
    cmpi(13, 3)
    a.ajmp("no_root", 1)
    a.emit(0x6811, root_address >> 15)
    mov(3, 13)
    a.emit(0x4C32, 0x70F3, 0x8000 | (root_address & 0x7fff), 0x38A3, 0x28B3)
    # R9:R8 * R11:R10 -> R3:R2:R1:R0, unsigned, no fractional mode.
    imm(2, 0)
    imm(3, 0)
    a.emit(0xBE3C, 0x080A)
    mov(0, 7)
    mov(1, 6)
    a.emit(0xBE3C, 0x090A, 0x1017, 0x1126, 0x71F3, 0,
           0xBE3C, 0x080B, 0x1017, 0x1126, 0x71F3, 0,
           0xBE3C, 0x090B, 0x1027, 0x1136)
    # The useful Q28 result spans product bits 28..59.
    cmpi(3, 0x1000)
    a.ajmp("overflow", 6)
    mov(0, 1)
    a.emit(0x4D0C)
    mov(1, 2)
    a.emit(0x4C24, 0x1002, 0x4D1C, 0x4C34, 0x1013)
    a.ajmp("magnitude_range")
    a.label("no_root")
    mov(0, 8)
    mov(1, 9)
    a.label("magnitude_range")
    cmpi(1, 0x8000)
    a.ajmp("sign", 5)
    a.ajmp("overflow", 0xA)
    cmpi(0, 0)
    a.ajmp("overflow", 2)
    cmpi(14, 0)
    a.ajmp("overflow", 1)  # +8 is out of range; exact -8 is representable
    a.label("sign")
    cmpi(14, 0)
    a.ajmp("success", 1)
    # Two-word two's complement, with the low-word carry retained.
    a.emit(0x77F0, 0xFFFF, 0x77F1, 0xFFFF, 0x70F0, 1, 0x71F1, 0)
    a.label("success")
    imm(2, 0)
    a.ajmp("scalar_return")
    a.label("invalid_scalar")
    imm(2, 2)
    a.ajmp("scalar_error")
    a.label("overflow")
    imm(2, 3)
    a.label("scalar_error")
    imm(0, 0)
    imm(1, 0)
    a.ajmp("scalar_return")
    a.label("zero")
    imm(0, 0)
    imm(1, 0)
    imm(2, 0)
    a.label("scalar_return")
    return_scalar()

    a.label("spectrum")
    for r in (1, *range(3, 15)): push(r)
    a.emit(0x1F10, 0x1F11, *select_workspace(workspace_bank), 0x6811, geometry_address >> 15)
    mov(4, 3)
    load(0, 4, 4)
    cmpi(0, 8)
    a.ajmp("invalid_spectrum", 0xA)
    mov(10, 0)
    load(8, 4, 2)
    load(7, 4, 6)
    load(6, 4, 8)
    load(9, 4, 10)
    load(4, 4, 0)
    load(11, 4, 4)
    cmpi(11, 255)
    a.ajmp("invalid_spectrum", 0xA)
    a.emit(0x72FB, 210)
    load(0, 4, 8)
    cmpi(0, 15)
    a.ajmp("invalid_spectrum", 0xA)
    imm(12, 1)
    a.emit(0x74F0, 2)
    a.ajmp("multiplier_ready", 1)
    imm(12, 2)
    a.label("multiplier_ready")
    load(0, 4, 10)
    cmpi(0, 3)
    a.ajmp("invalid_spectrum", 0xA)
    imm(14, 0)
    cmpi(0, 2)
    a.ajmp("mode_ready", 2)
    imm(14, 1)
    load(0, 4, 8)
    a.emit(0x74F0, 8)
    a.ajmp("mode_ready", 1)
    imm(14, 2)
    a.label("mode_ready")
    for offset in (18, 20, 22):
        load(0, 4, offset)
        cmpi(0, 7)
        a.ajmp("invalid_spectrum", 0xA)
    mov(3, 8)
    imm(13, 39)
    a.label("validate_sf")
    a.emit(0x3803)
    cmpi(0, 31)
    a.ajmp("invalid_spectrum", 0xA)
    a.emit(0x52D1)
    a.ajmp("validate_sf", 2)
    mov(3, 7)
    imm(13, 576)
    a.label("validate_quant")
    a.emit(0x3803)
    cmpi(0, 0x8000)
    a.ajmp("quant_positive", 5)
    imm(1, 0)
    a.emit(0x1210, 0x0801)
    a.label("quant_positive")
    cmpi(0, 8206)
    a.ajmp("invalid_spectrum", 0xA)
    a.emit(0x52D1)
    a.ajmp("validate_quant", 2)
    # Geometry headers contain an ordinary DS1 pointer and band count.
    mov(0, 10)
    a.emit(0x100A, 0x100A, 0x100E, 0x4C02, 0x70F0, 0x8000 | (geometry_address & 0x7fff),
           0x0830, 0x3803, 0x28A3, 0x0850)
    mov(3, 9)
    imm(0, 0)
    imm(13, 39)
    a.label("clear_exponents")
    a.emit(0x1A30, 0x52D1)
    a.ajmp("clear_exponents", 2)
    a.label("band")
    a.emit(0x38D5, 0x38E5, 0x3825)
    load(0, 4, 8)
    a.emit(0x74F0, 4)
    a.ajmp("pre_ready", 2)
    imm(14, 0)
    a.label("pre_ready")
    mov(3, 8)
    a.emit(0x2803, 0x5082, 0x100E, 0x4C01)
    cmpi(12, 1)
    a.ajmp("sf_scaled", 1)
    a.emit(0x4C01)
    a.label("sf_scaled")
    mov(14, 11)
    a.emit(0x12E0)
    cmpi(2, 3)
    a.ajmp("band_exponent", 1)
    mov(3, 2)
    a.emit(0x4C31, 0x1034, 0x70F3, 18, 0x2803, 0x4C03, 0x12E0)
    a.label("band_exponent")
    a.emit(0x1A9E)
    a.label("coefficient")
    a.emit(0x3807)
    mov(1, 14)
    a.emit(0xBD00 | address >> 16, a.labels["scalar"] & 65535)
    cmpi(2, 0)
    a.ajmp("spectrum_error", 2)
    a.emit(0x1A60, 0x1A61, 0x52D1)
    a.ajmp("coefficient", 2)
    a.emit(0x52A1)
    a.ajmp("band", 2)
    imm(0, 576)
    imm(2, 0)
    a.ajmp("spectrum_return")
    a.label("invalid_spectrum")
    imm(2, 2)
    a.label("spectrum_error")
    imm(0, 0)
    a.label("spectrum_return")
    a.emit(0x1F91, 0x1F90)
    for r in reversed((1, *range(3, 15))): pop(r)
    a.emit(0xC620)
    code = struct.pack(f"<{len(a.words)}H", *a.finish())
    code_span(address,code)
    core = {"code":code,"code_address":address,"entries":a.labels,
            "geometry_address":geometry_address,"root_address":root_address}
    if power_pages is None:
        data,geometry = tables(table_address,root_address,geometry_address)
        core.update(tables=data,table_address=table_address,geometry=geometry)
    else:
        powers,roots,geometry,entries = table_data(geometry_address)
        directory = struct.pack(f"<{len(power_pages)*2}H",*(v for page in power_pages for v in (page>>15,0x8000|(page&0x7fff))))
        page_bytes=power_page_entries*4
        parts = [(f"power-{i}",page,powers[i*page_bytes:(i+1)*page_bytes]) for i,page in enumerate(power_pages)]
        parts += [("power-directory",power_directory,directory),("roots",root_address,roots),
                  ("geometry",geometry_address,geometry)]
        for _,target,data in parts: near_table(target,data)
        core.update(table_parts=[{"name":name,"address":target,"data":data} for name,target,data in parts],
                    power_page_entries=power_page_entries,geometry=entries)
    return core


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
    manifest.update(rq_source_sha256=RQ_SHA, factory_rom_patch=False, pcm_produced=False,
                    complete_mp3_decoder=False, license="GPL-2.0-or-later")
    (args.output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k not in ("entries", "geometry")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
