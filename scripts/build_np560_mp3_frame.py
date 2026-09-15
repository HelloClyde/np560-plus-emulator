#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native continuous Layer III entropy-frame driver, NOT PCM/factory ABI.

R3 = aligned near state (SIZE bytes); R12 = raw bit context positioned at
side information, after an externally validated MPEG header and optional
CRC. First five state words are caller inputs: lsf, nch, frequency_index,
intensity_stereo_enabled, payload_bytes. Frequency order is the spectrum
core's 9-row order. Normal non-free-format frame sizes are supported.

Call reset once, and on seek/discontinuity; it preserves those five inputs
and zeroes the remaining state. A frame call owns side parsing, raw reservoir
history and all granule/channel SF dependencies. Records are compact in
gr*nch+ch order; each holds quant[576], sf[39], illegal_is[39], metrics[4].
R0 = valid record count, R2 = status; other GPRs and DS preserved.
1 = short complete raw frame, 2 = invalid arguments/context: no mutation.
3 = invalid sideinfo, 4 = reservoir error, 5 = spectrum error. These consume
the complete raw frame, retain its raw history, invalidate ALL records and
store the subordinate error at DETAIL. No concealment/fake decoded zeros.
CRC and overlapping cross-frame main_data consumption are NOT checked yet.
Caller owns nonoverlapping near state, input context and stack allocations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_np560_mp3_huffman import build as build_entropy
from build_np560_mp3_sideinfo import build as build_side
from build_np560_mp3_reservoir import build as build_reservoir
from build_np560_mp3_scalefactors import build as build_sf
from build_np560_mp3_spectrum import build as build_spectrum
from build_np560_mp3_requantize import build as build_requantize
from build_np560_mp3_stereo import build as build_stereo
from build_np560_mp3_intensity import build as build_intensity
from build_np560_mp3_antialias import build as build_antialias
from build_np560_mp3_hybrid import build as build_hybrid
from build_np560_mp3_synthesis import build as build_synthesis
from build_np560_mp3_dct32 import build as build_dct32
from np560_assembler import _DMCUAssembler
from np560_mp3_workspace import select_workspace
from np560_mp3_link import validate

ADDRESS = 0x20A400
HISTORY_BYTES, VALID, STATUS, DETAIL = 10, 12, 14, 16
SIDE, RES_DESC, BITCTX, SF_DESC, SPEC_DESC = 0x20, 0xB0, 0xC0, 0xD0, 0xE0
HISTORY, MAIN, CAPACITY, RECORDS = 0x100, 0x300, 2048, 0xB00
SF, MASK, METRICS, STRIDE = 0x480, 0x4CE, 0x51C, 0x524
SIZE = RECORDS + 4 * STRIDE


def build(address=ADDRESS, workspace_bank=0, *, side=None, reservoir=None, spectrum=None):
    side = side or build_side(workspace_bank=workspace_bank)
    reservoir = reservoir or build_reservoir(workspace_bank=workspace_bank)
    spectrum = spectrum or build_spectrum(workspace_bank=workspace_bank)
    a = _DMCUAssembler(address)

    def imm(r, value): a.emit(0x68F0 | r, value)
    def mov(dst, src): a.emit(0x0800 | dst << 4 | src)
    def cmpi(r, value): a.emit(0x76F0 | r, value)
    def push(r): a.emit(0x58F0 | r)
    def pop(r): a.emit(0x380F | r << 4)
    def ptr(dst, base, offset):
        mov(dst, base)
        if offset: a.emit(0x70F0 | dst, offset)
    def load(dst, base, offset):
        ptr(1, base, offset)
        a.emit(0x2801 | dst << 4)
    def store(base, offset, reg):
        ptr(1, base, offset)
        a.emit(0x0A10 | reg)
    def constant(offset, value):
        imm(0, value)
        store(5, offset, 0)
    def field_pointer(offset, target):
        ptr(0, 5, target)
        store(5, offset, 0)
    def call(core, entry):
        entry = core["entries"][entry]
        a.emit(0xBD00 | entry >> 16, entry & 65535)
    saved = (1, *range(3, 15))
    def prologue():
        for r in saved: push(r)
        a.emit(0x1F10, 0x1F11, *select_workspace(workspace_bank))

    a.label("frame")
    prologue()
    mov(5, 3)
    load(6, 5, 0)
    cmpi(6, 1)
    a.ajmp("invalid", 0xA)
    load(7, 5, 2)
    cmpi(7, 1)
    a.ajmp("invalid", 5)
    cmpi(7, 2)
    a.ajmp("invalid", 0xA)
    load(0, 5, 4)
    cmpi(0, 8)
    a.ajmp("invalid", 0xA)
    cmpi(6, 0)
    a.ajmp("lsf_rate", 2)
    cmpi(0, 2)
    a.ajmp("invalid", 0xA)
    a.ajmp("rate_valid")
    a.label("lsf_rate")
    cmpi(0, 3)
    a.ajmp("invalid", 5)
    a.label("rate_valid")
    load(0, 5, 6)
    cmpi(0, 1)
    a.ajmp("invalid", 0xA)
    cmpi(7, 2)
    a.ajmp("intensity_valid", 1)
    cmpi(0, 0)
    a.ajmp("invalid", 2)
    a.label("intensity_valid")
    load(0, 5, HISTORY_BYTES)
    cmpi(0, 511)
    a.ajmp("invalid", 0xA)
    load(4, 5, 8)
    cmpi(4, CAPACITY - 511)
    a.ajmp("invalid", 0xA)
    load(0, 12, 6)
    cmpi(0, 16)
    a.ajmp("invalid", 0xA)
    # Exact sideinfo lengths, including odd byte counts. No raw input or
    # decoder state mutation until the whole frame is available.
    imm(8, 72)
    cmpi(6, 0)
    a.ajmp("side_size", 2)
    imm(8, 136)
    a.label("side_size")
    cmpi(7, 1)
    a.ajmp("total_size", 1)
    a.emit(0x4C81)
    cmpi(6, 0)
    a.ajmp("stereo_lsf", 2)
    a.emit(0x72F8, 16)
    a.ajmp("total_size")
    a.label("stereo_lsf")
    a.emit(0x5288)
    a.label("total_size")
    a.emit(0x4C43, 0x1048)
    load(0, 12, 8)
    a.emit(0x1604)
    a.ajmp("short", 5)

    constant(VALID, 0)
    constant(STATUS, 0)
    constant(DETAIL, 0)
    mov(0, 6)
    ptr(3, 5, SIDE)
    mov(1, 7)
    call(side, "sideinfo")
    mov(4, 2)  # Semantic side error retained while raw history advances.
    field_pointer(RES_DESC, HISTORY)
    load(0, 5, HISTORY_BYTES)
    store(5, RES_DESC + 2, 0)
    load(0, 5, SIDE)
    store(5, RES_DESC + 4, 0)
    load(0, 5, 8)
    store(5, RES_DESC + 6, 0)
    field_pointer(RES_DESC + 8, MAIN)
    constant(RES_DESC + 10, CAPACITY)
    field_pointer(RES_DESC + 12, BITCTX)
    load(0, 5, SIDE + 8)
    cmpi(4, 0)
    a.ajmp("reservoir_bits", 1)
    imm(0, 0)
    a.label("reservoir_bits")
    store(5, RES_DESC + 14, 0)
    ptr(3, 5, RES_DESC)
    call(reservoir, "reservoir")
    load(0, 5, RES_DESC + 2)
    store(5, HISTORY_BYTES, 0)
    cmpi(4, 0)
    a.ajmp("side_error", 2)
    cmpi(2, 0)
    a.ajmp("reservoir_error", 2)

    ptr(12, 5, BITCTX)
    store(5, SF_DESC, 6)
    field_pointer(SPEC_DESC, SF_DESC)
    load(0, 5, 4)
    store(5, SPEC_DESC + 2, 0)
    ptr(13, 5, SIDE + 16)
    ptr(9, 5, RECORDS)
    mov(8, 7)
    cmpi(6, 0)
    a.ajmp("segments_ready", 2)
    a.emit(0x4C81)
    a.label("segments_ready")
    imm(10, 0)  # channel within granule
    imm(11, 0)  # compact record index
    a.label("segment")
    store(5, SF_DESC + 2, 13)
    ptr(0, 9, SF)
    store(5, SF_DESC + 8, 0)
    a.emit(0x16B7)
    a.ajmp("previous_ready", 5)
    a.emit(0x72F0, STRIDE)
    cmpi(7, 1)
    a.ajmp("previous_ready", 1)
    a.emit(0x72F0, STRIDE)
    a.label("previous_ready")
    store(5, SF_DESC + 6, 0)
    imm(0, 0)
    a.emit(0x16B7)
    a.ajmp("scfsi_ready", 5)
    ptr(3, 5, SIDE + 4)
    cmpi(10, 0)
    a.ajmp("scfsi_channel", 1)
    a.emit(0x5032)
    a.label("scfsi_channel")
    a.emit(0x2803)
    a.label("scfsi_ready")
    store(5, SF_DESC + 4, 0)
    imm(0, 0)
    cmpi(6, 0)
    a.ajmp("intensity_ready", 1)
    cmpi(10, 1)
    a.ajmp("intensity_ready", 2)
    load(0, 5, 6)
    a.label("intensity_ready")
    store(5, SF_DESC + 10, 0)
    ptr(0, 9, MASK)
    store(5, SF_DESC + 12, 0)
    store(5, SPEC_DESC + 4, 9)
    ptr(0, 9, METRICS)
    store(5, SPEC_DESC + 6, 0)
    ptr(3, 5, SPEC_DESC)
    call(spectrum, "spectrum")
    cmpi(2, 0)
    a.ajmp("spectrum_error", 2)
    a.emit(0x50B1, 0x50A1, 0x16A7)
    a.ajmp("next_channel", 5)
    imm(10, 0)
    a.label("next_channel")
    a.emit(0x70F9, STRIDE, 0x70FD, 32, 0x16B8)
    a.ajmp("segment", 5)
    store(5, VALID, 8)
    mov(0, 8)
    imm(2, 0)
    a.ajmp("return")

    a.label("side_error")
    mov(2, 4)
    imm(0, 3)
    a.ajmp("semantic_error")
    a.label("reservoir_error")
    imm(0, 4)
    a.ajmp("semantic_error")
    a.label("spectrum_error")
    imm(0, 5)
    a.label("semantic_error")
    store(5, DETAIL, 2)
    store(5, STATUS, 0)
    mov(2, 0)
    imm(0, 0)
    store(5, BITCTX + 8, 0)
    a.ajmp("return")
    for label, status in (("short", 1), ("invalid", 2)):
        a.label(label)
        imm(0, 0)
        imm(2, status)
        a.ajmp("return")

    a.label("reset")
    prologue()
    a.emit(0x503A)
    imm(1, (SIZE - 10) // 2)
    imm(0, 0)
    a.label("reset_word")
    a.emit(0x1A30, 0x5211)
    a.ajmp("reset_word", 2)
    imm(2, 0)
    a.label("return")
    a.emit(0x1F91, 0x1F90)
    for r in reversed(saved): pop(r)
    a.emit(0xC620)
    code = struct.pack(f"<{len(a.words)}H", *a.finish())
    assert address % 2 == 0 and (address & 0xffff)+len(code) <= 0x10000
    return {"code": code, "code_address": address, "entries": a.labels}


def components(workspace_bank=0, layout=None, *, fast_dct=False):
    def options(name):
        result = dict((layout or {}).get(name,{}))
        assert "workspace_bank" not in result, "all dependencies share caller workspace policy"
        return dict(result,workspace_bank=workspace_bank)
    cores = {}
    cores["entropy"] = build_entropy(**options("entropy"))
    cores["sideinfo"] = build_side(entropy=cores["entropy"],**options("sideinfo"))
    cores["reservoir"] = build_reservoir(entropy=cores["entropy"],**options("reservoir"))
    cores["scalefactors"] = build_sf(entropy=cores["entropy"],**options("scalefactors"))
    cores["spectrum"] = build_spectrum(entropy=cores["entropy"],sf=cores["scalefactors"],**options("spectrum"))
    cores["frame"] = build(side=cores["sideinfo"],reservoir=cores["reservoir"],spectrum=cores["spectrum"],**options("frame"))
    cores["requantize"] = build_requantize(**options("requantize"))
    geometry = cores["requantize"]["geometry_address"]
    cores["stereo"] = build_stereo(geometry_address=geometry,**options("stereo"))
    cores["intensity"] = build_intensity(geometry_address=geometry,ms=cores["stereo"],**options("intensity"))
    cores["antialias"] = build_antialias(**options("antialias"))
    cores["hybrid"] = build_hybrid(math_core=cores["antialias"],**options("hybrid"))
    if fast_dct or "dct32" in (layout or {}): cores["dct32"]=build_dct32(**options("dct32"))
    cores["synthesis"] = build_synthesis(math_core=cores["antialias"],fast_core=cores.get("dct32"),**options("synthesis"))
    for core in cores.values():
        core["workspace_bank"] = workspace_bank
    validate(cores)
    return cores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {"components": {}, "state_bytes": SIZE, "factory_rom_patch": False,
                "continuous_entropy_frame_driver": True, "requantize_spectrum_available": True, "pcm_produced": False,
                "ms_stereo_available": True, "short_reorder_available": True, "intensity_stereo_available": True,
                "antialias_available": True,
                "hybrid_available": True, "hybrid_output_fracbits": 23,
                "synthesis_available": True, "synthesis_pcm_format": "s16le",
                "complete_mp3_decoder": False, "license": "GPL-2.0-or-later"}
    for name, core in components().items():
        item = {"entries": core["entries"], "workspace_bank": core["workspace_bank"], "fragments": []}
        for key, address in (("code", "code_address"), ("tables", "table_address")):
            if key not in core: continue
            filename = f"{name}-{key}.bin"
            (args.output / filename).write_bytes(core[key])
            item["fragments"].append({"file": filename, "address": core[address], "bytes": len(core[key]),
                                      "sha256": hashlib.sha256(core[key]).hexdigest()})
        manifest["components"][name] = item
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["components"]["frame"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
