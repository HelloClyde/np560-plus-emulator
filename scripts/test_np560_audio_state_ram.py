#!/usr/bin/env python3
"""Original audio initialization/setup and dispatcher must share F010 RAM.

Guest calls untouched 08:3292, 08:2F22 and 31:D9AA. Rate=0 deliberately
tests state setup only, not decoding, timer output or a playable NPE.
Host input changes physical key state only; no NAND, HLE or RAM injection.
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

from test_np560_dtu import read_word
from web.np560_web import Emulator


CASES = {"idle": (0, 0), "mode40": (0x40, 0),
         "key-held": (0, 1), "mode800": (0x800, 0)}


def check(qemu, original, output, name, mode, keys, icount):
    words = [0x6800, 2, 0x68FF, 0x6000, 0x68FB, 0,
             0x6810, 0xA2, 0x6811, 0xA3, 0xBD08, 0x3292]
    read_word(words, 0xF010, 4)
    words += [0x6810, 1]
    read_word(words, 0x7010, 5, banked=True)
    words += [0xBD31, 0xD9AA]
    read_word(words, 0x2A76, 6, banked=True)  # Scanner itself selects DS0=A2.
    args = [mode] + [0] * 9  # Four null callbacks/buffers; rate selector 0.
    for value in reversed(args):
        words += [0x68F0, value, 0x58F0]
    words += [0xBD08, 0x2F22, 0x70FF, len(args) * 2]
    read_word(words, 0xF010, 7)
    words += [0x6810, 1]
    read_word(words, 0x7010, 8, banked=True)
    read_word(words, 0xF012, 9)
    words += [0xBD31, 0xD9AA]
    read_word(words, 0x2A76, 10, banked=True)
    final_pc = f"PC=20:{len(words) * 2:04x}"
    words += [0xD0FF]
    # Existing board overlays expose 31:D9AA from the NOR source 4E:D9AA,
    # not writable runtime RAM. Preserve that source in this diagnostic
    # firmware, and verify the actual code view before executing anything.
    firmware = bytearray(original)
    struct.pack_into(f"<{len(words)}H", firmware, 0, *words)
    resident = bytearray(b"\x00\x0f" * (0x083314 // 2))
    regions = [(0x082F22, 0x083314), (0x249BD4, 0x249BE8),
               (0x31D9AA, 0x31DA42)]
    blocks = []
    for start, end in regions:
        data = original[start - 0x030000:end - 0x030000]
        assert len(data) == end - start
        target, offset = (resident, start) if start < 0x200000 else (
            firmware, start - 0x200000)
        target[offset:offset + len(data)] = data
        blocks.append({"runtime_start": hex(start), "bytes": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()})
    expected = {4: 4, 5: 4, 6: 0, 7: mode | 2, 8: mode | 2,
                9: 0, 10: int(bool(mode & 0x08F0)), 15: 0x6000}
    result = {"name": name, "passed": False, "mode": mode, "keys": keys,
              "icount": icount, "expected": expected, "original_blocks": blocks,
              "host_guest_memory_writes": 0, "nand_used": False,
              "firmware_sha256": hashlib.sha256(firmware).hexdigest(),
              "resident_sha256": hashlib.sha256(resident).hexdigest()}
    with tempfile.TemporaryDirectory(prefix="np560-audio-state-") as directory:
        root = Path(directory)
        program, rom = root / "caller.prg", root / "original-functions.bin"
        program.write_bytes(firmware)
        rom.write_bytes(resident)
        emulator = Emulator(qemu=qemu, firmware=program, soc_rom=rom,
                            soc_rom_skeleton=True, start_paused=True,
                            icount_shift=icount)
        result["owned_pid"] = emulator.process.pid
        print(f"checking {name}; owned PID={emulator.process.pid}", flush=True)
        try:
            for start, end in regions:
                snapshot = emulator.snapshot("code", start, end - start)
                assert base64.b64decode(snapshot["frame"]) == original[
                    start - 0x030000:end - 0x030000], f"wrong code view at {start:06x}"
            emulator.set_key(keys, 0)
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "cpu-state"})
                if final_pc in state or "UNSUPPORTED=none" not in state:
                    break
                if emulator.process.poll() is not None:
                    raise RuntimeError(f"QEMU exited: {emulator.process.returncode}")
                time.sleep(0.01)
            emulator.qmp.execute("stop")
            state = emulator.qmp.execute("qom-get", {
                "path": "/machine", "property": "cpu-state"})
            (output / f"{name}.cpu.txt").write_text(state, encoding="utf-8")
            registers = {int(k): int(v, 16) for k, v in re.findall(
                r"\bR(\d+)\s*=([0-9a-f]{4})\b",
                "\n".join(state.splitlines()[:5]), re.I)}
            result["registers"] = registers
            result["final_pc_reached"] = final_pc in state
            result["fault_free"] = all(f"{field}=none" in state for field in (
                "ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL"))
            result["passed"] = result["final_pc_reached"] and result["fault_free"] and all(
                registers.get(k) == v for k, v in expected.items())
            print(f"{name}: passed={result['passed']}; registers={registers}", flush=True)
        finally:
            emulator.close()
            result["exit_code"] = emulator.process.returncode
            (output / f"{name}.qemu.log").write_bytes(emulator.log_path.read_bytes())
            (output / f"{name}.json").write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--normal-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    original = args.original_prg.read_bytes()
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"passed": False, "qemu_sha256": identity,
              "original_prg_sha256": hashlib.sha256(original).hexdigest(), "cases": []}
    try:
        for name, (mode, keys) in CASES.items():
            if args.case and args.case != name:
                continue
            for icount in ((None,) if args.normal_only else (None, 5)):
                report["cases"].append(check(args.qemu, original, args.output,
                    f"{name}-icount{icount}", mode, keys, icount))
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
        report["passed"] = all(case["passed"] for case in report["cases"])
    finally:
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
