#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native sideinfo -> reservoir checks, with raw-history byte oracle.

Expected buffers are compared by the guest; the host only reads the first
mismatch record. Short runs use no NAND and never touch a user instance.
"""
from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import hashlib
import json
from pathlib import Path
import random
import struct

from build_np560_mp3_huffman import build as build_entropy
from build_np560_mp3_sideinfo import build as build_side
from build_np560_mp3_reservoir import build
from np560_assembler import _DMCUAssembler
from test_np560_dtu import read_sfr, write_word
from test_np560_mac import run
from test_np560_mp3_sideinfo import mp3_frames, reference

HISTORY, OUTPUT, CAPACITY = 0x2800, 0x3000, 2048


def words(data):
    data += bytes(len(data) % 2)
    return [int.from_bytes(data[i:i+2], "big") for i in range(0, len(data), 2)]


def prepare(cases):
    history = b""
    history_memory = bytearray(b"\xA5\x5A"*256)
    records, details = [], []
    for index, c in enumerate(cases):
        if c.get("reset", False): history = b""
        payload = bytes.fromhex(c["payload"])
        mdb, declared = c.get("mdb", 0), c.get("data_bits", len(payload)*8)
        capacity = c.get("capacity", CAPACITY)
        side = bytes.fromhex(c.get("side", ""))
        stream = side + payload
        stream += bytes(len(stream) % 2)
        available = c.get("available", (len(side)+len(payload))*8)
        initial = [0x42, 0, 0, c.get("cached_bits", 0), available]
        desc = [HISTORY, len(history), mdb, len(payload), OUTPUT, capacity, 0x2010, declared]
        status = 0
        if mdb > 511 or len(payload) > 8191 or mdb+len(payload) > 8191 or capacity < mdb+len(payload) or initial[3] > 16:
            status = 2
        elif available < len(stream)*8-(8 if len(side+payload) % 2 else 0):
            status = 1
        elif mdb > len(history):
            status = 3
        elif declared > (mdb+len(payload))*8:
            status = 4
        consumed = (len(side)+len(payload))*8 if status not in (1, 2) else 0
        output = bytearray(b"\xA5\x5A"*(CAPACITY//2))
        outctx = [0xD000+i for i in range(5)]
        if status not in (1, 2):
            prefix = (history[-mdb:] if mdb else b"") if status != 3 else bytes(mdb)
            assembled = prefix+payload
            assert len(assembled) <= CAPACITY
            output[:len(assembled)] = assembled
            if len(assembled) % 2: output[len(assembled)] = 0
            history = (history+payload)[-511:]
            history_memory[:len(history)] = history
            if len(history) % 2: history_memory[len(history)] = 0
            desc[1] = len(history)
            outctx = [0, OUTPUT | 0x8000, 0, 0, declared if status == 0 else 0]
        count = len(records)
        # next pointer, expected pointer, reset, mdb, length, capacity,
        # declared bits, available bits, cached bits, lsf, nch, side bytes.
        header = [0, 0, int(c.get("reset", False)), mdb, len(payload), capacity,
                  declared, available, initial[3], c.get("lsf", 0), c.get("nch", 1), len(side)]
        input_pointer = 0x8000+2*(count+len(header))
        initial[1] = input_pointer
        loaded = (consumed+15)//16
        state = list(initial)
        if consumed:
            state = [0x42, input_pointer+loaded*2, 0, loaded*16-consumed, available-consumed]
            if consumed % 16:
                state[2] = (words(stream)[loaded-1] << 8) & 65535
        expected = [(0x2300, [mdb+len(payload) if status == 0 else 0, status]),
                    (0x2000, state), (0x2010, outctx), (0x2200, desc),
                    (HISTORY, words(bytes(history_memory))), (OUTPUT, words(bytes(output))),
                    (0x1FFE, [0xCAFE]), (0x200A, [0xCAFE]), (0x201A, [0xCAFE]),
                    (0x21FE, [0xCAFE]), (0x2210, [0xCAFE]),
                    (HISTORY-2, [0xCAFE]), (HISTORY+512, [0xCAFE]),
                    (OUTPUT-2, [0xCAFE]), (OUTPUT+CAPACITY, [0xCAFE])]
        encoded = []
        for address, values in expected: encoded += [address, len(values)] + values
        encoded += [0, 0]
        header[1] = input_pointer+len(stream)
        header[0] = header[1]+len(encoded)*2
        records += header+words(stream)+encoded
        details.append({"index": index, "input": c, "expected_status": status,
                        "expected_history_hex": history.hex(), "expected_ranges": [(addr, len(vals)) for addr, vals in expected]})
    assert len(records)*2 < 0x8000
    return records, details


def check(qemu, output, name, cases, icount=None):
    entropy, side, reservoir = build_entropy(), build_side(), build()
    records, details = prepare(cases)
    a = _DMCUAssembler(0x200000)
    a.emit(0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 0x42,
           0x68FC, 0x2000, 0x68F9, 0x8000, 0x68FB, 0x4444,
           0x68F7, 0, 0x68F8, 0, 0x68FA, len(cases))
    for address in (0x1FFE, 0x200A, 0x201A, 0x21FE, 0x2210,
                    HISTORY-2, HISTORY+512, OUTPUT-2, OUTPUT+CAPACITY):
        write_word(a.words, address, 0xCAFE)
    for address in range(0x2400, 0x2408, 2): write_word(a.words, address, 0)
    write_word(a.words, 0x2200, HISTORY)
    write_word(a.words, 0x2202, 0)
    write_word(a.words, 0x2208, OUTPUT)
    write_word(a.words, 0x220C, 0x2010)
    a.emit(0x68F0, 0xA55A, 0x68F3, HISTORY, 0x68F1, 256)
    a.label("init_history")
    a.emit(0x1A30, 0x5211)
    a.ajmp("init_history", 2)
    a.label("frame")
    a.emit(0x3869, 0x38D9, 0x3809, 0x76F0, 0)
    a.ajmp("keep_history", 1)
    write_word(a.words, 0x2202, 0)
    a.label("keep_history")
    for address in (0x2204, 0x2206, 0x220A, 0x220E, 0x2008, 0x2006):
        a.emit(0x3809, 0xA8F0, address)
    a.emit(0x3849, 0x3859, 0x38E9, 0xA8F9, 0x2002)
    write_word(a.words, 0x2000, 0x42)
    write_word(a.words, 0x2004, 0)
    for i in range(5): write_word(a.words, 0x2010+2*i, 0xD000+i)
    a.emit(0x68F0, 0xA55A, 0x68F3, OUTPUT, 0x68F1, CAPACITY//2)
    a.label("clear_output")
    a.emit(0x1A30, 0x5211)
    a.ajmp("clear_output", 2)
    a.emit(0x76FE, 0)
    a.ajmp("no_sideinfo", 1)
    a.emit(0x0804, 0x0815, 0x68F3, 0x2100, 0xBD20, side["entries"]["sideinfo"] & 65535)
    # These are NATIVE parser outputs, not copied from the host expectation.
    a.emit(0x88F0, 0x2100, 0xA8F0, 0x2204, 0x88F0, 0x2108, 0xA8F0, 0x220E)
    a.label("no_sideinfo")
    a.emit(0x68F3, 0x2200, 0xBD20, reservoir["entries"]["reservoir"] & 65535,
           0xA8F0, 0x2300, 0xA8F2, 0x2302, 0x089D)
    a.label("range")
    a.emit(0x3839, 0x3859, 0x76F5, 0)
    a.ajmp("frame_done", 1)
    a.label("compare")
    a.emit(0x3803, 0x3819, 0x1601)
    a.ajmp("same", 1)
    a.emit(0x76F7, 0)
    a.ajmp("already_failed", 2)
    a.emit(0xA8F8, 0x2400, 0xA8F3, 0x2402, 0xA8F0, 0x2404, 0xA8F1, 0x2406)
    a.label("already_failed")
    a.emit(0x5071)
    a.label("same")
    a.emit(0x5251)
    a.ajmp("compare", 2)
    a.ajmp("range")
    a.label("frame_done")
    a.emit(0x0896, 0x5081, 0x52A1)
    a.ajmp("frame", 2)
    read_sfr(a.words, 0x11, 13)
    program = a.finish()
    assert len(program)*2+2 < 0x1000
    payload = bytearray(0xF000+len(records)*2)
    for address, data in ((entropy["code_address"], entropy["code"]), (entropy["table_address"], entropy["tables"]),
                          (side["code_address"], side["code"]), (reservoir["code_address"], reservoir["code"])):
        start = address-entropy["code_address"]
        payload[start:start+len(data)] = data
    payload[0xF000:] = struct.pack(f"<{len(records)}H", *records)
    (output / f"{name}.vectors.json").write_text(json.dumps(details, indent=2)+"\n", encoding="utf-8")
    result = run(qemu, output, name, program,
               {8: len(cases), 9: 0x8000+len(records)*2, 10: 0, 11: 0x4444,
                12: 0x2000, 13: 0x42, 15: 0x6000},
               tail=(0x1000, payload), expected_data=[0]*4, icount=icount,
               metadata={"frames": len(cases), "native_sideinfo_frames": sum(bool(c.get("side")) for c in cases),
                         "reservoir_sha256": hashlib.sha256(reservoir["code"]).hexdigest(),
                         "compared_memory_words": sum(sum(n for _, n in d["expected_ranges"]) for d in details),
                         "pcm_produced": False, "factory_rom_services_replaced": False})
    assert result["registers"][7] == 0
    return result


def synthetic():
    rng = random.Random(560)
    def item(length, mdb=0, **kwargs):
        return dict(payload=bytes(rng.randrange(256) for _ in range(length)).hex(), mdb=mdb, **kwargs)
    return [item(3, reset=True), item(5, 3), item(0, 8), item(101, 1), item(1, 109),
            item(509, 110), item(1, 511), item(600, 511), item(17, 511),
            item(0, 511), item(7, 1), item(1, 511, reset=True), item(4, 1),
            item(7, 5, data_bits=97), item(1, 12),
            item(7, 0, available=55), item(7, 512), item(7, 0, capacity=6),
            item(7, 0, cached_bits=17), item(0, 0, data_bits=1), item(23, 13)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-only", action="store_true")
    parser.add_argument("--mp3", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cases = synthetic()
    if args.first_only: cases = cases[:1]
    if args.mp3:
        frames = mp3_frames(args.mp3)
        reference(args.output, frames)
        for frame in frames:
            assert frame["status"] == 0
            cases.append({"payload": frame["main_data_hex"], "mdb": frame["fields"][0],
                          "data_bits": frame["fields"][4], "lsf": frame["lsf"], "nch": frame["nch"],
                          "side": int(frame["side"], 2).to_bytes(len(frame["side"])//8, "big").hex(),
                          "file_offset": frame["file_offset"], "reset": frame is frames[0]})
    report = {"passed": False, "cases": [], "pcm_produced": False,
              "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    # Keep short native runs. At a chunk boundary, establish history by
    # ingesting its exact raw bytes through the SAME native reservoir API.
    history = b""
    try:
        for start in range(0, len(cases), 6):
            group = cases[start:start+6]
            bootstrap = [{"payload": history.hex(), "mdb": 0, "reset": True}] if history else []
            prepared = bootstrap+group
            report["cases"].append(check(args.qemu, args.output, f"reservoir-{start:03d}", prepared))
            _, detail = prepare(prepared)
            history = bytes.fromhex(detail[-1]["expected_history_hex"])
        if not args.first_only:
            report["cases"].append(check(args.qemu, args.output, "reservoir-icount5", synthetic()[:6], icount=5))
        report["passed"] = all(c["passed"] and c["exit_code"] == 0 for c in report["cases"])
    except AssertionError as exc:
        detail = exc.args[0] if exc.args else "assertion failed"
        if isinstance(detail, dict):
            detail = {k: detail[k] for k in ("name", "registers", "actual_samples", "expected_samples") if k in detail}
        report["failure"] = str(detail)[:2000]
        print(report["failure"], flush=True)
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
