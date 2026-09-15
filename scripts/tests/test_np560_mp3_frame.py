#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""One autonomous guest run across raw MP3 frames, offline entropy oracle.

The fixture contains raw sideinfo/payload and read-only expected results.
Only the native decoder writes sideinfo, history, SF and spectra. Neither
per-frame history bootstraps nor per-granule SF injection are permitted.
Host reference identity requantization exposes integers, NOT PCM/audio.
Optional --pcm runs all native stages, then captures actual guest PCM16.
Offline references are never linked into QEMU or used as playback output.
"""
from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import wave

from build_np560_mp3_frame import (components, HISTORY_BYTES, VALID, STATUS, DETAIL,
    SIDE, BITCTX, HISTORY, MAIN, RECORDS, SF, MASK, METRICS, STRIDE, SIZE)
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr, write_word
from test_np560_mac import run
from test_np560_mp3_sideinfo import mp3_frames, reference as side_reference
from test_np560_mp3_spectrum import real_cases, reference

STATE, INPUT, RESULT, TRACE = 0x2800, 0x2000, 0x2300, 0x2400
# The full-file oracle no longer fits a single NOR bank. 21..3C:38CF
# contains existing Harvard text/font aliases (notably 26:527C), while
# 49:DC00 begins the machine's writable object workspace. Use the bounded
# unaliased interval between them; never modify the machine's mappings.
FIXTURE_ADDRESS, FIXTURE_END = 0x3C8000, 0x49DC00
GUARDS = (INPUT - 2, INPUT + 10, STATE - 2, STATE + SIZE)
RQ_OUTPUTS, RQ_EXP, RQ_DESC, RQ_RESULT = (0x0100, 0x0A00, 0x1300, 0x5400), 0x5200, 0x2350, 0x2310
MS_RESULT, RO_RESULT, MS_DESC, RO_DESC, MODE_EXT, SCRATCH = 0x2340, 0x2320, 0x2360, 0x2370, 0x2390, 0x4800
JOINT_DESC, JOINT_WORK, JOINT_TAGS = 0x23A0, 0x2260, 0x5100
AA_RESULT = 0x23C0
HB_RESULT, HB_OVERLAP, HB_OUTPUT, HB_WORK, HB_DESC = 0x23D0, (0x6000, 0x6900), 0x7200, 0x7B00, 0x7BC0
HB_GUARDS = (0x7BA0, 0x7BCE, 0x7FFE)
SY_BANK, SY_STATE = 0x30, (0x8100, 0xA100)
SY_DESC, SY_WORK, SY_RESULT = 0x7C20, 0x7BE0, 0x23E0
SY_GUARDS = (0x7C00, 0x7C2A)
PCM_ADDRESS, PCM_END, PCM_POINTER = 0x190000, 0x1F0000, 0x7C30


def network_words(data):
    data += bytes(len(data) % 2)
    return [int.from_bytes(data[i:i+2], "big") for i in range(0, len(data), 2)]


def far(word_offset):
    address = FIXTURE_ADDRESS + word_offset * 2
    return [address >> 15, 0x8000 | (address & 0x7fff)]


def context(raw, word_offset, consumed, available):
    loaded = (consumed + 15) // 16
    bank, pointer = far(word_offset + loaded)
    cache = 0
    if loaded:
        cache = (network_words(raw)[loaded-1] << (consumed - 16*(loaded-1))) & 65535
    return [bank, pointer, cache, loaded*16 - consumed, available - consumed]


def fixtures(path, output, limit=None, requant=False, postprocess=False, post_start=0, antialias=False, hybrid=False, pcm=False, *, fast_dct=False):
    cases = real_cases(path, output)
    reference(output, cases)
    frames = mp3_frames(path)
    side_reference(output, frames)
    if limit: frames = frames[:limit]
    by_frame = {}
    for c in cases: by_frame.setdefault(c["frame"], []).append(c)
    result = [dict(f, segments=by_frame[i]) for i, f in enumerate(frames)]
    if post_start >= len(result): raise ValueError("--post-start must precede the actual end of the MP3 prefix")
    if requant:
        from test_np560_mp3_requantize import reference as requant_reference
        comparisons = []
        for frame in result[post_start:]:
            for c in frame["segments"]:
                q = {k: copy.deepcopy(c[k]) for k in ("rate", "channel", "sf", "quant")}
                q["channel"][4] = c["flags"]  # includes native LSF preflag
                c["requant"] = q
                comparisons.append(q)
        requant_reference(output, comparisons, "V")
    if postprocess:
        from test_np560_mp3_stereo import reference as stereo_reference, reference_binary
        from test_np560_mp3_intensity import reference as joint_reference, reference_binary as joint_binary
        binary, raw = reference_binary(output), path.read_bytes()
        joint_ref = joint_binary(output)
        for f in result[post_start:]:
            header = int.from_bytes(raw[f["file_offset"]:f["file_offset"]+4], "big")
            f["mode_ext"] = (header >> 4) & 3 if (header >> 6) & 3 == 1 else 0
            for c in f["segments"]:
                assert c["requant"]["status"] == 0
                c["post"] = c["requant"]["q28"][:]
            if f["mode_ext"]:
                assert f["nch"] == 2
                for j in range(0, len(f["segments"]), 2):
                    l, r = f["segments"][j:j+2]
                    assert l["channel"][5] == r["channel"][5] and l["channel"][4]&8 == r["channel"][4]&8
                    channels = [copy.deepcopy(l["channel"]), copy.deepcopy(r["channel"])]
                    channels[0][4], channels[1][4] = l["flags"], r["flags"]
                    c = {"mode": "J", "rate": l["rate"], "ext": f["mode_ext"], "channels": channels,
                         "sf": r["sf"], "mask": r["mask"], "quant": r["quant"], "left": l["post"], "right": r["post"]}
                    joint_reference(output, [c], joint_ref)
                    assert c["status"] == 0
                    l["post"], r["post"] = c["expected"][:576], c["expected"][576:]
                    l["joint_tags"] = c["tags"]
            for c in f["segments"]:
                ro = {"mode": "R", "input": [c["rate"], c["channel"][5], int(bool(c["flags"]&8))]+c["post"]}
                stereo_reference(output, [ro], binary)
                assert ro["status"] == 0
                c["post"] = ro["expected"]
    if antialias:
        from test_np560_mp3_antialias import reference as alias_reference, reference_binary as alias_binary
        binary = alias_binary(output)
        for f in result[post_start:]:
            for c in f["segments"]:
                aa = {"mode": "V", "input": [c["rate"], c["channel"][5], int(bool(c["flags"]&8))]+c["post"]}
                alias_reference(output, [aa], binary)
                assert aa["status"] == 0
                c["antialias"] = aa
                c["post"] = aa["expected"]
    if hybrid:
        assert antialias and not post_start
        from test_np560_mp3_hybrid import reference as hybrid_reference, reference_binary as hybrid_binary
        binary = hybrid_binary(output)
        overlap = [[0]*576 for _ in range(2)]
        for f in result:
            for c in f["segments"]:
                h = {"mode": "H", "input": [c["rate"], c["channel"][5], int(bool(c["flags"]&8)), 0]
                     +c["post"]+overlap[c["ch"]]}
                hybrid_reference(output, [h], binary)
                assert h["status"] == 0
                c["hybrid"] = h
                overlap[c["ch"]] = h["expected"][576:]
            f["overlap"] = copy.deepcopy(overlap)
    if pcm:
        assert hybrid and not post_start
        from test_np560_mp3_synthesis import reference as synthesis_reference, reference_binary as synthesis_binary
        binary = synthesis_binary(output,fast=fast_dct)
        states = [{"head": 0, "state": [0]*1024} for _ in range(2)]
        for f in result:
            for c in f["segments"]:
                old = states[c["ch"]]
                s = {"mode": "G", "input": [SY_BANK, SY_STATE[c["ch"]], old["head"], 0]
                     +c["hybrid"]["expected"][:576]+old["state"]}
                synthesis_reference(output, [s], binary)
                assert s["status"] == 0
                c["synthesis"] = s
                states[c["ch"]] = {"head": s["head"], "state": s["state"]}
            f["synthesis_states"] = copy.deepcopy(states)
    return result


def prepare(frames):
    records, details, history = [], [], b""
    pcm = any("synthesis" in c for f in frames for c in f["segments"])
    # Track prior record content to detect unexpected clearing or mixing
    # of unused records as well as actual per-granule outputs.
    memory = [0] * (SIZE // 2)
    for i, f in enumerate(frames):
        if f.get("reset", i == 0):
            history = b""
            memory[5:] = [0] * (SIZE // 2 - 5)
        payload = bytes.fromhex(f["main_data_hex"])
        side = int(f["side"], 2).to_bytes(len(f["side"]) // 8, "big")
        raw = side + payload
        fields, segments = f["fields"], f["segments"]
        inputs = [f["lsf"], f["nch"], segments[0]["rate"],
                  max(c["intensity"] for c in segments), len(payload)]
        inputs = f.get("inputs", inputs)
        available = f.get("available", len(raw)*8)
        initial_cached = f.get("cached", 0)
        status, detail = f.get("expected_status", 0), f.get("expected_detail", 0)
        memory[:5] = inputs
        start = len(records)
        header = [0, 0, 0, 0, int(f.get("reset", i == 0))] + inputs + [available, initial_cached, f.get("mode_ext", 0)]
        input_offset = start + len(header)
        consumed = 0 if status in (1, 2) else len(raw)*8
        input_ctx = context(raw, input_offset, consumed, available)
        if not consumed: input_ctx[3] = initial_cached
        expected = [(RESULT, [len(segments) if status == 0 else 0, status]), (INPUT, input_ctx)]
        if status not in (1, 2):
            mdb = fields[0]
            assembled = (history[-mdb:] if mdb else b"") + payload
            if detail == 3 and status == 4: assembled = bytes(mdb) + payload
            history = (history + payload)[-511:]
            memory[HISTORY_BYTES//2:DETAIL//2+1] = [len(history), len(segments) if status == 0 else 0, status, detail]
            memory[SIDE//2:SIDE//2+72] = fields
            history_words = network_words(history)
            memory[HISTORY//2:HISTORY//2+len(history_words)] = history_words
            main_words = network_words(assembled)
            memory[MAIN//2:MAIN//2+len(main_words)] = main_words
            expected += [(STATE+MAIN, main_words)]
            if status == 0:
                for j, c in enumerate(segments):
                    rec = c["quant"] + c["sf"] + c["mask"] + [c["part2"], c["channel"][1]*2, c["coded"], c["stuffing"]]
                    assert len(rec)*2 == STRIDE
                    begin = (RECORDS + j*STRIDE)//2
                    memory[begin:begin+len(rec)] = [n & 65535 for n in rec]
                    memory[(SIDE+16+j*32+8)//2] = c["flags"]
                    if "requant" in c:
                        q = c["requant"]
                        assert q["status"] == 0
                        qwords = []
                        samples = c["hybrid"]["expected"][:576] if "hybrid" in c else c.get("post", q["q28"])
                        if "synthesis" in c:
                            qwords = [v&65535 for v in c["synthesis"]["pcm"]]
                        else:
                            for value in samples: qwords += [value&65535, (value>>16)&65535]
                        expected += [(RQ_RESULT+j*4, [576, 0]), (RQ_EXP+j*0x50, q["exponents"]),
                                     (RQ_OUTPUTS[j], qwords)]
                        if "post" in c:
                            expected += [(RO_RESULT+j*4, [576, 0])]
                            if "antialias" in c: expected += [(AA_RESULT+j*4, [576, 0])]
                            if "hybrid" in c: expected += [(HB_RESULT+j*4, [576, 0])]
                            if "synthesis" in c: expected += [(SY_RESULT+j*4, [576, 0])]
                            if f["mode_ext"] and not j % 2:
                                expected += [(MS_RESULT+j*2, [576, 0]), (JOINT_TAGS+j*0x28, c["joint_tags"])]
                consumed_main = fields[4]
                loaded = (consumed_main+15)//16
                cache = 0
                if loaded:
                    cache = (main_words[loaded-1] << (consumed_main-16*(loaded-1))) & 65535
                expected += [(STATE+BITCTX, [0, (STATE+MAIN+loaded*2) | 0x8000, cache,
                                             loaded*16-consumed_main, 0])]
            else:
                expected += [(STATE+BITCTX+8, [0])]
        # Preflight checks compare the complete prior outputs unchanged;
        # successful checks include unused records to catch stale-state bugs.
        for offset, count in ((0, 9), (SIDE, 72), (HISTORY, 256), (RECORDS, 4*STRIDE//2)):
            if status in (3, 4, 5) and offset == RECORDS: continue
            expected.append((STATE+offset, memory[offset//2:offset//2+count]))
        expected += [(addr, [0xCAFE]) for addr in GUARDS]
        if "overlap" in f:
            for ch in range(2):
                values = []
                for v in f["overlap"][ch]: values += [v&65535, (v>>16)&65535]
                expected.append((HB_OVERLAP[ch], values))
            expected += [(addr, [0xCAFE]) for addr in HB_GUARDS]
        if "synthesis_states" in f:
            for ch, s in enumerate(f["synthesis_states"]):
                values = [s["head"]]
                for v in s["state"]: values += [v&65535, (v>>16)&65535]
                address = (SY_BANK << 15)+(SY_STATE[ch]&0x7fff)
                expected += [(address, values), (address-2, [0xCAFE]), (address+4098, [0xCAFE])]
            expected += [(addr, [0xCAFE]) for addr in SY_GUARDS]
        encoded = []
        for address, values in expected:
            encoded += ([address>>15, address&0x7fff] if pcm else [address])+[len(values)]+[n&65535 for n in values]
        encoded += [0, 0, 0] if pcm else [0, 0]
        expected_offset = input_offset + (len(raw)+1)//2
        end = expected_offset + len(encoded)
        header[:4] = far(end) + far(expected_offset)
        records += header + network_words(raw) + encoded
        details.append({"index": i, "file_offset": f["file_offset"], "frame_bytes": f["frame_bytes"],
                        "main_data_begin": fields[0], "history_bytes": len(history),
                        "segments": len(segments), "status": status, "detail": detail, "mode_extension": f.get("mode_ext"),
                        "reset": bool(header[4]), "test": f.get("test", "real-frame"), "input_far": far(input_offset),
                        "compared_words": sum(len(values) for _, values in expected)})
    return records, details


def check(qemu, output, name, frames, icount=None):
    cores = components()
    hybrid = any("hybrid" in c for f in frames for c in f["segments"])
    pcm = any("synthesis" in c for f in frames for c in f["segments"])
    pcm_bytes = 1152*sum(len(f["segments"]) for f in frames) if pcm else 0
    assert PCM_ADDRESS+pcm_bytes <= PCM_END
    records, details = prepare(frames)
    assert FIXTURE_ADDRESS + len(records)*2 <= FIXTURE_END
    a = _DMCUAssembler(0x200000)
    a.emit(0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, FIXTURE_ADDRESS >> 15,
           0x68FC, INPUT, 0x68F9, 0x8000 | (FIXTURE_ADDRESS & 0x7fff), 0x68FE, FIXTURE_ADDRESS >> 15,
           0x68F7, 0, 0x68F8, 0, 0x68FA, len(frames))
    for addr in GUARDS: write_word(a.words, addr, 0xCAFE)
    if hybrid:
        for addr in HB_GUARDS: write_word(a.words, addr, 0xCAFE)
    if pcm:
        for addr in SY_GUARDS: write_word(a.words, addr, 0xCAFE)
        for off, value in ((0, SY_BANK), (4, HB_OUTPUT), (8, SY_WORK)):
            write_word(a.words, SY_DESC+off, value)
        write_word(a.words, PCM_POINTER, PCM_ADDRESS>>15)
        write_word(a.words, PCM_POINTER+2, 0x8000|(PCM_ADDRESS&0x7fff))
        a.emit(0x1F11, 0x6811, SY_BANK)
        for ptr in SY_STATE:
            for addr in (ptr-2, ptr+4098):
                a.emit(0x68F3, addr, 0x68F0, 0xCAFE, 0x0A30)
        a.emit(0x1F91)
    for addr in range(TRACE, TRACE+8, 2): write_word(a.words, addr, 0)
    a.label("frame")
    # Record pointers are far; inputs/expectations can span NOR banks.
    for reg in (6, 4, 13, 11):
        a.acall("get_word")
        a.emit(0x0800 | reg << 4)
    a.acall("get_word")
    a.emit(0x76F0, 0)
    a.ajmp("keep_state", 1)
    a.emit(0x68F3, STATE, 0xBD20, cores["frame"]["entries"]["reset"] & 65535)
    if hybrid:
        for addr in HB_OVERLAP:
            a.emit(0x68F3, addr, 0xBD20, cores["hybrid"]["entries"]["reset"] & 65535)
    if pcm:
        for ptr in SY_STATE:
            write_word(a.words, SY_DESC+2, ptr)
            a.emit(0x68F3, SY_DESC, 0xBD20, cores["synthesis"]["entries"]["reset"] & 65535)
    a.label("keep_state")
    a.emit(0x68F3, STATE, 0x68F5, 5)
    a.label("input_fields")
    a.acall("get_word")
    a.emit(0x1A30, 0x5251)
    a.ajmp("input_fields", 2)
    for addr in (INPUT+8, INPUT+6):
        a.acall("get_word")
        a.emit(0xA8F0, addr)
    a.acall("get_word")
    a.emit(0xA8F0, MODE_EXT)
    a.emit(0xA8FE, INPUT, 0xA8F9, INPUT+2)
    write_word(a.words, INPUT+4, 0)
    a.emit(0x68F3, STATE, 0xBD20, cores["frame"]["entries"]["frame"] & 65535,
           0xA8F0, RESULT, 0xA8F2, RESULT+2)
    if any("requant" in c for f in frames for c in f["segments"]):
        rq_start = next(i for i, f in enumerate(frames) if any("requant" in c for c in f["segments"]))
        a.emit(0x76F8, rq_start)
        a.ajmp("requant_done", 5)
        a.emit(0x76F2, 0)
        a.ajmp("requant_done", 2)
        for j in range(4):
            a.emit(0x88F0, STATE+VALID, 0x76F0, j+1)
            a.ajmp("requant_done", 5)
            for offset, value in ((0, STATE+SIDE+16+j*32), (2, STATE+RECORDS+j*STRIDE+SF),
                                  (6, STATE+RECORDS+j*STRIDE), (8, RQ_OUTPUTS[j]), (10, RQ_EXP+j*0x50)):
                write_word(a.words, RQ_DESC+offset, value)
            a.emit(0x88F0, STATE+4, 0xA8F0, RQ_DESC+4, 0x68F3, RQ_DESC,
                   0xBD20, cores["requantize"]["entries"]["spectrum"] & 65535,
                   0xA8F0, RQ_RESULT+j*4, 0xA8F2, RQ_RESULT+j*4+2)
        a.label("requant_done")
    if any("post" in c for f in frames for c in f["segments"]):
        post_start = next(i for i, f in enumerate(frames) if any("post" in c for c in f["segments"]))
        a.emit(0x76F8, post_start)
        a.ajmp("post_done", 5)
        a.emit(0x88F0, RESULT+2, 0x76F0, 0)
        a.ajmp("post_done", 2)
        for j in range(4):
            for addr in (RO_RESULT+j*4, RO_RESULT+j*4+2): write_word(a.words, addr, 0xA55A)
            a.emit(0x88F0, STATE+VALID, 0x76F0, j+1)
            a.ajmp("requant_status_ready", 5)
            a.emit(0x88F0, RQ_RESULT+j*4+2, 0x76F0, 0)
            a.ajmp("post_done", 2)
        a.label("requant_status_ready")
        a.emit(0x88F0, MODE_EXT, 0x76F0, 0)
        a.ajmp("ms_done", 1)
        # The native joint stage decides MS/IS per band, using native
        # right quantized samples, SF and illegal-position masks.
        a.emit(0x76F0, 3)
        a.ajmp("post_done", 0xA)
        a.emit(0x88F0, STATE+2, 0x76F0, 2)
        a.ajmp("post_done", 2)
        for j in (0, 2):
            a.emit(0x88F0, STATE+VALID, 0x76F0, j+2)
            a.ajmp("ms_done", 5)
            a.emit(0x88F0, STATE+4, 0xA8F0, JOINT_DESC, 0x88F0, MODE_EXT, 0xA8F0, JOINT_DESC+2)
            for off, value in ((4, STATE+SIDE+16+j*32), (6, STATE+SIDE+16+(j+1)*32),
                    (8, STATE+RECORDS+(j+1)*STRIDE+SF), (10, STATE+RECORDS+(j+1)*STRIDE+MASK),
                    (12, STATE+RECORDS+(j+1)*STRIDE), (14, RQ_OUTPUTS[j]), (16, RQ_OUTPUTS[j+1]), (18, JOINT_WORK)):
                write_word(a.words, JOINT_DESC+off, value)
            a.emit(0x68F3, JOINT_DESC, 0xBD20, cores["intensity"]["entries"]["joint"] & 65535,
                   0xA8F0, MS_RESULT+j*2, 0xA8F2, MS_RESULT+j*2+2, 0x76F2, 0)
            a.ajmp("post_done", 2)
            a.emit(0x68F3, JOINT_WORK+8, 0x68F5, JOINT_TAGS+j*0x28, 0x68F1, 39)
            a.label(f"copy_joint_tags_{j}")
            a.emit(0x3803, 0x1A50, 0x5211)
            a.ajmp(f"copy_joint_tags_{j}", 2)
        a.label("ms_done")
        for j in range(4):
            a.emit(0x88F0, STATE+VALID, 0x76F0, j+1)
            a.ajmp("post_done", 5)
            a.emit(0x88F0, STATE+4, 0xA8F0, RO_DESC,
                   0x88F0, STATE+SIDE+16+j*32+10, 0xA8F0, RO_DESC+2,
                   0x88F0, STATE+SIDE+16+j*32+8, 0x4D03, 0x74F0, 1, 0xA8F0, RO_DESC+4)
            write_word(a.words, RO_DESC+6, RQ_OUTPUTS[j])
            write_word(a.words, RO_DESC+8, SCRATCH)
            a.emit(0x68F3, RO_DESC, 0xBD20, cores["stereo"]["entries"]["reorder"] & 65535,
                   0xA8F0, RO_RESULT+j*4, 0xA8F2, RO_RESULT+j*4+2, 0x76F2, 0)
            a.ajmp("post_done", 2)
            a.emit(0x68F3, SCRATCH, 0x68F5, RQ_OUTPUTS[j], 0x68F1, 1152)
            a.label(f"copy_reorder_{j}")
            a.emit(0x3803, 0x1A50, 0x5211)
            a.ajmp(f"copy_reorder_{j}", 2)
            if any("antialias" in c for f in frames for c in f["segments"]):
                # RO_DESC's first four words are exactly the antialias
                # descriptor; the in-place buffer now contains native
                # reordered samples, never host-preprocessed spectra.
                a.emit(0x68F3, RO_DESC, 0xBD20, cores["antialias"]["entries"]["spectrum"] & 65535,
                       0xA8F0, AA_RESULT+j*4, 0xA8F2, AA_RESULT+j*4+2, 0x76F2, 0)
                a.ajmp("post_done", 2)
            if hybrid:
                a.emit(0x68F3, RO_DESC, 0x68F5, HB_DESC, 0x68F1, 3)
                a.label(f"hybrid_geometry_{j}")
                a.emit(0x3803, 0x1A50, 0x5211)
                a.ajmp(f"hybrid_geometry_{j}", 2)
                for offset, value in ((6, RQ_OUTPUTS[j]), (8, HB_OUTPUT), (10, HB_OVERLAP[0]), (12, HB_WORK)):
                    write_word(a.words, HB_DESC+offset, value)
                if j%2:
                    a.emit(0x88F0, STATE+2, 0x76F0, 2)
                    a.ajmp(f"hybrid_channel_{j}", 2)
                    write_word(a.words, HB_DESC+10, HB_OVERLAP[1])
                    a.label(f"hybrid_channel_{j}")
                a.emit(0x68F3, HB_DESC, 0xBD20, cores["hybrid"]["entries"]["hybrid"] & 65535,
                       0xA8F0, HB_RESULT+j*4, 0xA8F2, HB_RESULT+j*4+2, 0x76F2, 0)
                a.ajmp("post_done", 2)
                if pcm:
                    write_word(a.words, SY_DESC+2, SY_STATE[0])
                    write_word(a.words, SY_DESC+6, RQ_OUTPUTS[j])
                    if j%2:
                        a.emit(0x88F0, STATE+2, 0x76F0, 2)
                        a.ajmp(f"synthesis_channel_{j}", 2)
                        write_word(a.words, SY_DESC+2, SY_STATE[1])
                        a.label(f"synthesis_channel_{j}")
                    a.emit(0x68F3, SY_DESC, 0xBD20, cores["synthesis"]["entries"]["granule"]&65535,
                           0xA8F0, SY_RESULT+j*4, 0xA8F2, SY_RESULT+j*4+2, 0x76F2, 0)
                    a.ajmp("post_done", 2)
                    a.emit(0x68F3, RQ_OUTPUTS[j])
                    a.acall("capture_pcm")
                else:
                    a.emit(0x68F3, HB_OUTPUT, 0x68F5, RQ_OUTPUTS[j], 0x68F1, 1152)
                    a.label(f"copy_hybrid_{j}")
                    a.emit(0x3803, 0x1A50, 0x5211)
                    a.ajmp(f"copy_hybrid_{j}", 2)
        a.label("post_done")
    a.emit(0x089B, 0x08ED, 0x58FE, 0x1F91)
    a.label("range")
    if pcm:
        a.acall("get_word")
        a.emit(0x58F0, 0x1F90)  # DS0 reads the expected range's real bank
    a.acall("get_word")
    a.emit(0x0830)
    a.acall("get_word")
    a.emit(0x0850, 0x76F5, 0)
    a.ajmp("frame_done", 1)
    a.label("compare")
    a.acall("get_word")
    a.emit(0x0810, 0x3803, 0x1601)
    a.ajmp("same", 1)
    a.emit(0x76F7, 0)
    a.ajmp("already_failed", 2)
    if pcm: a.emit(0x1F10, 0x6810, 0)
    a.emit(0xA8F8, TRACE, 0xA8F3, TRACE+2, 0xA8F0, TRACE+4, 0xA8F1, TRACE+6)
    if pcm: a.emit(0x1F90)
    a.label("already_failed")
    a.emit(0x5071)
    a.label("same")
    a.emit(0x5251)
    a.ajmp("compare", 2)
    a.ajmp("range")
    a.label("frame_done")
    if pcm: a.emit(0x6810, 0)
    a.emit(0x0894, 0x08E6, 0x58FE, 0x1F91, 0x5081, 0x52A1)
    a.ajmp("frame", 2)
    read_sfr(a.words, 0x11, 13)
    a.ajmp("end")
    a.label("get_word")
    a.emit(0x2809, 0x5092)
    a.ajmp("word_ready", 2)
    a.emit(0x68F9, 0x8000, 0x50E1, 0x58FE, 0x1F91)
    a.label("word_ready")
    a.emit(0xC600)
    if pcm:
        a.label("capture_pcm")
        for r in (0, 1, 2, 3, 5): a.emit(0x58F0|r)
        a.emit(0x1F11, 0x88F2, PCM_POINTER, 0x58F2, 0x1F91,
               0x88F5, PCM_POINTER+2, 0x68F1, 576)
        a.label("capture_word")
        a.emit(0x3803, 0x1A50, 0x76F5, 0)
        a.ajmp("capture_pointer_ready", 2)
        a.emit(0x68F5, 0x8000, 0x5021, 0x58F2, 0x1F91)
        a.label("capture_pointer_ready")
        a.emit(0x5211)
        a.ajmp("capture_word", 2)
        a.emit(0xA8F2, PCM_POINTER, 0xA8F5, PCM_POINTER+2, 0x1F91)
        for r in (5, 3, 2, 1, 0): a.emit(0x380F|r<<4)
        a.emit(0xC600)
    a.label("end")
    program = a.finish()
    assert len(program)*2+2 < 0x1000
    payload = bytearray(FIXTURE_ADDRESS-0x201000+len(records)*2)
    for core in cores.values():
        for key, addr in (("code", "code_address"), ("tables", "table_address")):
            if key not in core: continue
            start = core[addr]-0x201000
            payload[start:start+len(core[key])] = core[key]
    start = FIXTURE_ADDRESS-0x201000
    payload[start:] = struct.pack(f"<{len(records)}H", *records)
    end_bank, end_ptr = far(len(records))
    (output/f"{name}.frames.json").write_text(json.dumps(details, indent=2)+"\n", encoding="utf-8")
    # A full file stays in ONE QEMU process; the deadline is explicit and
    # allows the slow diagnostic CPU to finish without chunk bootstraps.
    return run(qemu, output, name, program,
               {7: 0, 8: len(frames), 9: end_ptr, 10: 0, 12: INPUT, 13: end_bank, 14: end_bank, 15: 0x6000},
               tail=(0x1000, payload), expected_data=[0]*4, icount=icount,
               timeout=max(180, len(frames)*(35 if pcm else 18 if hybrid else 4)), poll_interval=0.25,
               capture_ranges=[("guest-pcm", PCM_ADDRESS, pcm_bytes)] if pcm else None,
               metadata={"frames": len(frames), "segments": sum(len(f["segments"]) for f in frames),
                         "single_continuous_guest": True, "history_bootstraps": 0,
                         "host_sf_injections": 0, "pcm_produced": pcm, "pcm_bytes": pcm_bytes,
                         "host_synthesis_history_injections": 0,
                         "synthesis_sha256": hashlib.sha256(cores["synthesis"]["code"]).hexdigest(),
                         "factory_rom_services_replaced": False, "state_bytes": SIZE,
                         "fixture_address": FIXTURE_ADDRESS, "fixture_bytes": len(records)*2,
                         "frame_sha256": hashlib.sha256(cores["frame"]["code"]).hexdigest(),
                         "requantized_segments": sum("requant" in c for f in frames for c in f["segments"]),
                         "requantize_sha256": hashlib.sha256(cores["requantize"]["code"]).hexdigest(),
                         "postprocessed_segments": sum("post" in c for f in frames for c in f["segments"]),
                         "ms_granules": sum(len(f["segments"])//2 for f in frames if f.get("mode_ext") == 2 and "post" in f["segments"][0]),
                         "is_granules": sum(len(f["segments"])//2 for f in frames if f.get("mode_ext", 0)&1 and "post" in f["segments"][0]),
                         "combined_granules": sum(len(f["segments"])//2 for f in frames if f.get("mode_ext") == 3 and "post" in f["segments"][0]),
                         "native_entropy_warmup_frames": next((i for i, f in enumerate(frames) if "post" in f["segments"][0]), 0),
                         "intensity_sha256": hashlib.sha256(cores["intensity"]["code"]).hexdigest(),
                         "antialiased_segments": sum("antialias" in c for f in frames for c in f["segments"]),
                         "antialias_sha256": hashlib.sha256(cores["antialias"]["code"]).hexdigest(),
                         "hybrid_segments": sum("hybrid" in c for f in frames for c in f["segments"]),
                         "hybrid_output_fracbits": 23 if hybrid else None,
                         "hybrid_sha256": hashlib.sha256(cores["hybrid"]["code"]).hexdigest(),
                         "host_overlap_injections": 0,
                         "stereo_sha256": hashlib.sha256(cores["stereo"]["code"]).hexdigest(),
                         "compared_words": sum(d["compared_words"] for d in details)})


def pcm_artifact(path, output, frames, case, *, hle=False):
    """Package ONLY captured guest samples, and compare an offline decoder.

    The host interleaves channels and writes the WAV header, not audio data
    synthesis. No delay search, gain correction or silence insertion is used.
    FFmpeg's packet metadata must explain any omitted Xing/Info-only frames;
    those must have zero spectra/PCM. Decoder delay trimming is disabled.
    """
    captured = Path(case["captures"]["guest-pcm"]["path"]).read_bytes()
    assert hashlib.sha256(captured).hexdigest() == case["captures"]["guest-pcm"]["sha256"]
    expected = [v for f in frames for c in f["segments"] for v in c["synthesis"]["pcm"]]
    values = list(struct.unpack(f"<{len(captured)//2}h", captured))
    assert len(values) == len(expected)
    integer_peak = max((abs(a-b) for a,b in zip(values,expected)),default=0)
    if hle:
        assert case["rom_mp3_hle"]["enabled"]
        # Different mature codec arithmetic is not bit-identical to the
        # reconstructed integer filter. Still require both this numerical
        # bound and the independent FFmpeg comparison below. Guest PCM is
        # untouched; never feed the reference back into the device.
        assert integer_peak <= 8, ("HLE vs integer reference",integer_peak)
    else:
        assert values == expected, "captured PCM differs from the independent integer reference"
    nch = frames[0]["nch"]
    rate_index = frames[0]["segments"][0]["rate"]
    hz = (44100, 48000, 32000, 22050, 24000, 16000, 11025, 12000, 8000)[rate_index]
    interleaved, cursor = [], 0
    for f in frames:
        assert f["nch"] == nch and f["segments"][0]["rate"] == rate_index
        for gr in range(len(f["segments"])//nch):
            channels = [values[cursor+ch*576:cursor+(ch+1)*576] for ch in range(nch)]
            cursor += nch*576
            interleaved.extend(v for row in zip(*channels) for v in row)
    assert cursor == len(values)
    audio = struct.pack(f"<{len(interleaved)}h", *interleaved)
    wav_path = output/"guest-decoded.wav"
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(nch);w.setsampwidth(2);w.setframerate(hz);w.writeframes(audio)
    raw = path.read_bytes()
    first, last = frames[0]["file_offset"], frames[-1]
    prefix = raw[first:last["file_offset"]+last["frame_bytes"]]
    probe = subprocess.run(["ffprobe", "-v", "error", "-f", "mp3", "-select_streams", "a",
        "-show_packets", "-show_entries", "packet=pos,size,side_data_list", "-of", "json", "pipe:0"],
        input=prefix, capture_output=True)
    (output/"ffmpeg-probe.log").write_bytes(probe.stderr)
    (output/"ffmpeg-packets.json").write_bytes(probe.stdout)
    probe.check_returncode()
    packets = json.loads(probe.stdout)["packets"]
    positions = [(f["file_offset"]-first, f["frame_bytes"]) for f in frames]
    packet_positions = [(int(p["pos"]), int(p["size"])) for p in packets]
    omitted = len(positions)-len(packet_positions)
    assert omitted >= 0 and positions[omitted:] == packet_positions, "unexplained demuxer packet selection"
    skipped_samples = 0
    for f in frames[:omitted]:
        contents = raw[f["file_offset"]:f["file_offset"]+f["frame_bytes"]]
        assert b"Xing" in contents or b"Info" in contents, "not a metadata frame"
        assert all(not any(c["quant"]) and not any(c["synthesis"]["pcm"]) for c in f["segments"])
        assert not any(interleaved[skipped_samples:skipped_samples+len(f["segments"])*576])
        skipped_samples += len(f["segments"])*576
    reference = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-flags", "+bitexact", "-flags2", "+skip_manual",
        "-f", "mp3", "-i", "pipe:0", "-map", "0:a:0", "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1"],
        input=prefix, capture_output=True)
    (output/"ffmpeg-reference.log").write_bytes(reference.stderr)
    (output/"ffmpeg-reference.s16le").write_bytes(reference.stdout)
    reference.check_returncode()
    ref = list(struct.unpack(f"<{len(reference.stdout)//2}h", reference.stdout))
    compared = interleaved[skipped_samples:]
    errors = [a-b for a,b in zip(compared, ref)]
    peak_error = max(map(abs, errors), default=0)
    comparison = {"guest_wav": str(wav_path), "guest_pcm_sha256": hashlib.sha256(audio).hexdigest(),
        "guest_samples": len(interleaved), "compared_guest_samples": len(compared), "reference_samples": len(ref), "channels": nch, "hz": hz,
        "samples_per_channel": len(interleaved)//nch, "duration_seconds": len(interleaved)/nch/hz,
        "peak_sample": max(map(abs, interleaved), default=0), "nonzero_samples": sum(v!=0 for v in interleaved),
        "max_absolute_difference": peak_error, "rms_difference": (sum(e*e for e in errors)/len(errors))**.5 if errors else None,
        "equal_length": len(compared)==len(ref), "delay_adjustment_samples": 0, "gain_adjustment": False,
        "demuxer_omitted_zero_metadata_frames": omitted, "excluded_zero_metadata_samples_per_channel": skipped_samples//nch,
        "automatic_decoder_delay_trimming": False, "guest_wav_trimmed": False,
        "within_8_pcm_lsb": len(compared)==len(ref) and peak_error<=8,
        "comparison_scope": ("HLE" if hle else "native") + " MP3 prefix; explicit zero metadata frame exclusion only, no standard/original-ROM identity claim",
        "ffmpeg_offline_only": True, "factory_player_connected": False,
        "rom_mp3_hle": hle,"max_integer_reference_difference": integer_peak,
        "ffmpeg_version": subprocess.run(["ffmpeg", "-version"],capture_output=True,text=True,check=True).stdout.splitlines()[0]}
    (output/"pcm-comparison.json").write_text(json.dumps(comparison,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(comparison), flush=True)
    return comparison


def recovery_cases(frames):
    """Faults are in raw bytes or API inputs, not decoded guest memory."""
    assert len(frames) >= 7
    result = [copy.deepcopy(frames[0])]
    candidate = frames[1]
    raw_bits = len(candidate["side"]) + len(bytes.fromhex(candidate["main_data_hex"]))*8
    for label in ("short-input", "wrong-rate-family", "bad-cache", "oversized-payload"):
        f = copy.deepcopy(candidate)
        f["expected_status"] = 1 if label == "short-input" else 2
        f["test"] = label
        if label == "short-input": f["available"] = raw_bits - 1
        elif label == "bad-cache": f["cached"] = 17
        else:
            f["inputs"] = [f["lsf"], f["nch"], f["segments"][0]["rate"],
                           max(c["intensity"] for c in f["segments"]), len(bytes.fromhex(f["main_data_hex"]))]
            f["inputs"][2 if label == "wrong-rate-family" else 4] = (0 if f["lsf"] else 3) if label == "wrong-rate-family" else 1538
        result.append(f)
    result.append(copy.deepcopy(candidate))

    def mutate(frame, bit_offset, width, value):
        frame["side"] = frame["side"][:bit_offset] + f"{value:0{width}b}" + frame["side"][bit_offset+width:]

    def header_bits(f):
        return (8+(1 if f["nch"] == 1 else 2)) if f["lsf"] else (9+(5 if f["nch"] == 1 else 3)+4*f["nch"])

    # Malformed sideinfo still contributes its unmodified raw payload to
    # the following frame's history, but is never decoded as valid audio.
    f = copy.deepcopy(frames[2])
    mutate(f, header_bits(f)+12, 9, 289)
    f["fields"][9] = 289
    f.update(expected_status=3, expected_detail=3, test="bad-side-big-values")
    result += [f, copy.deepcopy(frames[3])]
    # Make an active Huffman table reserved while retaining the original
    # declared sizes and raw payload; next frame must still recover.
    f = copy.deepcopy(frames[4])
    assert f["fields"][9] > 0
    start = header_bits(f)+12+9+8+(9 if f["lsf"] else 4)+1+(3 if f["windows"][0] else 0)
    mutate(f, start, 5, 4)
    f["fields"][14] = 4
    f.update(expected_status=5, expected_detail=4, test="reserved-huffman-table")
    result += [f, copy.deepcopy(frames[5])]

    # Start at a nonzero backpointer after explicit discontinuity. Failed
    # frames refill history natively; recovery occurs only when sufficient
    # actual prefix bytes have arrived, not by bootstrapping old state.
    history = b""
    for i, original in enumerate(frames[2:]):
        f = copy.deepcopy(original)
        f["reset"] = i == 0
        if f["fields"][0] > len(history): f.update(expected_status=4, expected_detail=3)
        f["test"] = "seek-missing-history-recovery"
        result.append(f)
        history = (history+bytes.fromhex(f["main_data_hex"]))[-511:]
    assert any(f.get("expected_status") == 4 for f in result)
    assert result[-1].get("expected_status", 0) == 0
    # Reset back to the real beginning, including stale SF/IS/output state.
    for i, original in enumerate(frames[:3]):
        f = copy.deepcopy(original)
        f["reset"] = i == 0
        f["test"] = "replay-after-reset"
        result.append(f)
    return result


def mode_cases(output):
    """Zero-bit spectra still have observable LSF illegal-is SF masks.

    Switching joint-stereo off must clear them, and changing mono/stereo
    must not consume obsolete record slots. These are synthetic frames.
    """
    frames, segments = [], []
    for i, (lsf, nch, rate, intensity) in enumerate(((1, 2, 3, 1), (1, 2, 3, 0),
            (0, 1, 2, 0), (1, 1, 8, 0), (0, 2, 0, 1), (1, 2, 4, 1))):
        side_bits = (72 if nch == 1 else 136) if lsf else (136 if nch == 1 else 256)
        frames.append({"lsf": lsf, "nch": nch, "side": "0"*side_bits, "windows": [0]*((1 if lsf else 2)*nch),
                       "main_data_hex": "", "file_offset": i, "frame_bytes": 4+side_bits//8,
                       "rate": rate, "intensity": intensity, "test": "synthetic-mode-transition"})
    side_reference(output, frames)
    for i, f in enumerate(frames):
        f["segments"] = []
        for j in range(f["fields"][5]*f["fields"][6]):
            gr, ch = divmod(j, f["nch"])
            c = {"lsf": f["lsf"], "rate": f["rate"], "scfsi": 0,
                 "intensity": int(f["lsf"] and ch == 1 and f["intensity"]),
                 "prefix": 0, "channel": f["fields"][8+16*j:24+16*j],
                 "previous": [0]*39, "stream": "0000", "frame": i, "gr": gr, "ch": ch,
                 "kind": "synthetic"}
            segments.append(c)
            f["segments"].append(c)
        f["inputs"] = [f["lsf"], f["nch"], f["rate"], f["intensity"], 0]
    reference(output, segments)
    assert any(frames[0]["segments"][1]["mask"])
    assert not any(frames[1]["segments"][1]["mask"])
    return frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mp3", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--icount", type=int)
    parser.add_argument("--recovery", action="store_true")
    parser.add_argument("--modes", action="store_true")
    parser.add_argument("--requant", action="store_true", help="Also call native Q28 stage; defaults to first 8 consecutive frames")
    parser.add_argument("--postprocess", action="store_true", help="Implies --requant, then native MS/IS and short reorder")
    parser.add_argument("--antialias", action="store_true", help="Implies --postprocess, then native antialias on reordered Q28")
    parser.add_argument("--hybrid", action="store_true", help="Implies --antialias, then native IMDCT/window/persistent overlap/inversion to Q23 subbands, NOT PCM")
    parser.add_argument("--pcm", action="store_true", help="Implies --hybrid, then native synthesis with persistent channel state; captures actual guest PCM16")
    parser.add_argument("--recheck-pcm-from", type=Path, help="Offline-only: check an existing successful native capture in a new output directory; no QEMU rerun")
    parser.add_argument("--post-start", type=int, default=0, help="Native entropy warmup frames before Q28/joint comparisons; no history injection")
    args = parser.parse_args()
    if args.recheck_pcm_from and not args.pcm: parser.error("--recheck-pcm-from requires --pcm")
    if args.pcm: args.hybrid = True
    if args.hybrid: args.antialias = True
    if args.antialias: args.postprocess = True
    if args.postprocess: args.requant = True
    if args.post_start < 0 or (args.post_start and not args.postprocess): parser.error("--post-start must be nonnegative and used with --postprocess")
    if args.hybrid and args.post_start: parser.error("--hybrid requires processing history from frame zero; --post-start is not allowed")
    if args.limit is not None and args.post_start >= args.limit: parser.error("--post-start must precede --limit")
    if args.limit is not None and args.limit < 1: parser.error("--limit must be positive")
    if not args.mp3 and not args.modes: parser.error("--mp3 is required unless --modes is selected")
    if args.modes and args.recovery: parser.error("--modes and --recovery are separate suites")
    if args.requant and (args.modes or args.recovery): parser.error("--requant uses an unmodified MP3 prefix, not the error/mode suites")
    if args.requant and args.limit is None: args.limit = args.post_start+8
    args.output.mkdir(parents=True, exist_ok=False)
    frames = mode_cases(args.output) if args.modes else fixtures(args.mp3, args.output, args.limit, args.requant, args.postprocess, args.post_start, args.antialias, args.hybrid, args.pcm)
    if args.recovery: frames = recovery_cases(frames)
    report = {"passed": False, "cases": [], "pcm_produced": False,
              "mp3_sha256": hashlib.sha256(args.mp3.read_bytes()).hexdigest() if not args.modes else None,
              "synthetic_modes": args.modes,
              "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    try:
        if args.recheck_pcm_from:
            previous = json.loads((args.recheck_pcm_from/"report.json").read_text(encoding="utf-8"))
            for key in ("mp3_sha256", "qemu_sha256"): assert report[key] == previous[key]
            case = json.loads((args.recheck_pcm_from/"continuous-frames.json").read_text(encoding="utf-8"))
            assert case["passed"] and case["exit_code"] == 0 and case["metadata"]["frames"] == len(frames)
            case["captures"]["guest-pcm"]["path"] = str(args.recheck_pcm_from/"continuous-frames.guest-pcm.bin")
            report.update(offline_only=True, native_guest_rerun=False, source_report=str(args.recheck_pcm_from/"report.json"))
        else:
            case = check(args.qemu, args.output, "continuous-frames", frames, args.icount)
            report.update(offline_only=False, native_guest_rerun=True)
        report["cases"].append(case)
        report["passed"] = all(c["passed"] and c["exit_code"] == 0 for c in report["cases"])
        if args.pcm and report["passed"]:
            report["pcm_comparison"] = pcm_artifact(args.mp3, args.output, frames, report["cases"][0])
            report["pcm_produced"] = True
            report["passed"] = report["pcm_comparison"]["within_8_pcm_lsb"]
    except AssertionError as exc:
        detail = exc.args[0] if exc.args else "assertion failed"
        if isinstance(detail, dict):
            detail = {k: detail[k] for k in ("name", "registers", "actual_samples", "expected_samples") if k in detail}
        report["failure"] = str(detail)[:2000]
        print(report["failure"], flush=True)
    finally:
        (args.output/"report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
