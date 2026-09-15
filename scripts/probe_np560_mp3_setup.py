#!/usr/bin/env python3
"""Observe original MPEG parsing -> audio setup -> the first missing service.

Headers, not decoder results, are supplied by diagnostic guest instructions.
Unchanged PRG code performs initialization, parsing and 1D:33CE setup. A
strict low-ROM hole stops execution without a success stub. This narrows
the missing MP3 ABI; it is NOT a full player, decoder or playback test.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import struct
import tempfile
import time
from pathlib import Path

from test_np560_dtu import write_word
from test_np560_mp3_header import CASES, PARSER, PARSER_SHA256, TABLES, TABLES_SHA256, original_slice
from web.np560_web import Emulator


SELECTED = {"mpeg1-128-44100-stereo", "mpeg2-64-22050-mono",
            "mpeg2-8-16000-stereo", "mpeg25-8-8000-mono",
            "mpeg25-32-11025-stereo"}
MP3_ARGS = [0, 0x1784, 0, 0x2084, 0, 0x1C04, 0, 0x2504,
            0, 0x2984, 0, 0x1000, 0x300]


def observe(qemu, original, output, case, icount):
    name, header_hex, fields = case
    header = bytes.fromhex(header_hex)
    words = [0x6800, 2, 0x68FF, 0x6000, 0x68FB, 0x4444,
             0xBD08, 0x3292, 0x6810, 0xA2, 0x6811, 0xA2]
    for i in range(2):
        write_word(words, 0xA846 + 2*i,
                   int.from_bytes(header[2*i:2*i+2], "big"), banked=True)
    words += [0xBD16, 0xE45E, 0xBD1D, 0x33CE, 0xD0FF]
    firmware = bytearray(original)
    assert len(words) * 2 < 0x1000
    struct.pack_into(f"<{len(words)}H", firmware, 0, *words)
    low_rate = fields[3] < 32
    expected_hole = "02:acd8" if low_rate else "01:4804"
    label = f"{name}-icount{icount}"
    result = {"name": label, "header_hex": header_hex, "icount": icount,
              "expected_hole": expected_hole, "passed": False,
              "host_guest_memory_writes": 0, "nand_used": False,
              "missing_service_bypassed": False, "decoded_pcm_generated": False,
              "diagnostic_firmware_sha256": hashlib.sha256(firmware).hexdigest()}
    with tempfile.TemporaryDirectory(prefix="np560-mp3-setup-") as directory:
        root = Path(directory)
        program, rom = root / "caller.prg", root / "strict-holes.bin"
        program.write_bytes(firmware)
        rom.write_bytes(b"\x00\x0f" * (0x30000 // 2))
        emulator = Emulator(qemu=qemu, firmware=program, soc_rom=rom,
                            soc_rom_skeleton=True, start_paused=True,
                            boot_mode="firmware-vma03", icount_shift=icount)
        result["owned_pid"] = emulator.process.pid
        print(f"observing {label}; owned PID={emulator.process.pid}", flush=True)
        try:
            for start, end in (PARSER, TABLES, (0x1D33CE, 0x1D3764),
                               (0x2FA6BA, 0x2FA7EE), (0x082F22, 0x083314),
                               (0x2497AC, 0x2498FC), (0x2499D2, 0x2499F6),
                               (0x08378A, 0x0837BA)):
                actual = base64.b64decode(emulator.snapshot("code", start, end-start)["frame"])
                assert actual == original[start-0x30000:end-0x30000], hex(start)
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
                if ("ROM_MISSING=none" not in state or "UNSUPPORTED=none" not in state
                        or "INVALID_CONTROL=none" not in state):
                    break
                if emulator.process.poll() is not None:
                    raise RuntimeError(f"QEMU terminated: {emulator.process.returncode}")
                time.sleep(0.01)
            emulator.qmp.execute("stop")
            state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
            (output / f"{label}.cpu.txt").write_text(state, encoding="utf-8")
            regs = {int(k): int(v, 16) for k, v in re.findall(
                r"\bR(\d+)\s*=([0-9a-f]{4})\b", "\n".join(state.splitlines()[:5]), re.I)}
            result["registers"] = regs
            result["diagnostics"] = [line for line in state.splitlines() if line.startswith(
                ("PC=", "ROM_MISSING=", "ROM_CALL=", "ROM_CALL_STACK=", "UNSUPPORTED=", "INVALID_CONTROL="))]
            for suffix, source, address, size in (
                    ("stack", "data", regs[15], 48),
                    ("parser", "memory", 0x5125C8, 20),
                    ("stream", "data", 0x4A52, 0x5C),
                    ("output_buffers", "data", 0x4AB0, 10),
                    ("decoder", "data", 0x333E, 0xA8),
                    ("repeat", "memory", 0x512AF0, 4),
                    ("locals", "data", (regs[11]-8) & 65535, 8)):
                data = base64.b64decode(emulator.snapshot(source, address, size)["frame"])
                (output / f"{label}.{suffix}.bin").write_bytes(data)
                result[suffix] = {"address": hex(address), "words_le": list(struct.unpack(f"<{size//2}H", data))}
            assert f"rom_missing={expected_hole}" in state.lower(), result["diagnostics"]
            assert "UNSUPPORTED=none" in state and "INVALID_CONTROL=none" in state
            actual_args = result["stack"]["words_le"][2:]
            expected_args = [20] if low_rate else MP3_ARGS
            assert actual_args[:len(expected_args)] == expected_args, actual_args
            result["observed_args"] = actual_args[:len(expected_args)]
            # 4A60 is populated by the original setup table, before the
            # decoder init. The low-bitrate paths stop before that callback.
            configured_hz = result["stream"]["words_le"][(0x4A60-0x4A52)//2]
            result["configured_hz"] = configured_hz
            assert configured_hz == (0 if low_rate else fields[4]), configured_hz
            # This is the PRG driver's block length and CH0-A/CH0-B/
            # CH1-A/CH1-B pointers, NOT the missing decoder's private state.
            expected_buffers = ([0] * 5 if low_rate else
                                [0x240, 0x1784, 0x2084, 0x1C04, 0x2504])
            result["expected_output_buffers"] = expected_buffers
            assert result["output_buffers"]["words_le"] == expected_buffers, result["output_buffers"]
            result["passed"] = True
            print(f"{label}: first hole {expected_hole}, args={expected_args}, configured_hz={configured_hz}", flush=True)
        finally:
            emulator.close()
            result["exit_code"] = emulator.process.returncode
            (output / f"{label}.qemu.log").write_bytes(emulator.log_path.read_bytes())
            (output / f"{label}.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=sorted(SELECTED))
    parser.add_argument("--normal-only", action="store_true")
    args = parser.parse_args()
    original = args.original_prg.read_bytes()
    original_slice(original, PARSER, PARSER_SHA256)
    original_slice(original, TABLES, TABLES_SHA256)
    args.output.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"passed": False, "qemu_sha256": digest,
              "original_prg_sha256": hashlib.sha256(original).hexdigest(), "cases": []}
    try:
        for case in CASES:
            if case[0] not in SELECTED or (args.case and args.case != case[0]):
                continue
            for icount in ((None,) if args.normal_only else (None, 5)):
                report["cases"].append(observe(args.qemu, original, args.output, case, icount))
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == digest
        report["passed"] = all(c["passed"] and c["exit_code"] == 0 for c in report["cases"])
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
