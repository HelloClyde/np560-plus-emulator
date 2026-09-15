#!/usr/bin/env python3
"""DMCU register DSP arithmetic and unmodified original sample gain routines.

No NAND, host guest-memory writes, codec substitute or menu bypass. Partial
memory MAC / AGU coverage lives in test_np560_memory_mac.py; this suite
retains explicit stops for forms whose address-register maps are unverified.
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

from test_np560_dtu import read_sfr, write_word
from web.np560_web import Emulator

MASK40 = (1 << 40) - 1
SAMPLES = [-32768, -30000, -16384, -1, 0, 1, 8192, 16384, 30000, 32767]
FUNCTIONS = {1: (0x0834C4, 0x083536), 2: (0x083536, 0x0835AC),
             3: (0x0835AC, 0x083626), 4: (0x083626, 0x0836A4),
             6: (0x0836A4, 0x08372A)}


def pack(words):
    return struct.pack(f"<{len(words)}H", *(x & 65535 for x in words))


def run(qemu, output, name, words, expected, *, rom=None, tail=None,
        expected_data=None, icount=None, fault=None, metadata=None,
        boot_mode="firmware", expected_disassembly=None,
        expected_lcd=None, expected_annunciators=None, expected_lcd_state=None,
        timeout=10, poll_interval=0.01, capture_ranges=None, expected_code=None,
        profile_pc=False, rom_mp3_hle_base=0, minimal=False):
    final = (0x030000 if boot_mode == "firmware-vma03" else 0x200000) + len(words) * 2
    words = [*words, 0xD0FF]
    program = bytearray(pack(words))
    if tail:
        offset, data = tail
        assert offset >= len(program)
        program.extend(bytes(offset + len(data) - len(program)))
        program[offset:offset + len(data)] = data
    result = {"name": name, "passed": False, "icount": icount, "minimal": minimal,
              "host_guest_memory_writes": 0, "nand_used": False,
              "metadata": metadata or {}, "expected": expected,
              "expected_fault": fault}
    with tempfile.TemporaryDirectory(prefix="np560-mac-") as directory:
        firmware = Path(directory) / "caller.prg"
        firmware.write_bytes(program)
        resident = None
        if rom is not None:
            resident = Path(directory) / "original-functions.bin"
            resident.write_bytes(rom)
        emulator = Emulator(qemu=qemu, firmware=firmware, soc_rom=resident,
                            boot_mode=boot_mode,
                            soc_rom_skeleton=resident is not None,
                            rom_mp3_hle_base=rom_mp3_hle_base,
                            start_paused=True, icount_shift=icount)
        result["owned_pid"] = emulator.process.pid
        try:
            print(f"checking {name}; owned PID={emulator.process.pid}", flush=True)
            def verify_code(phase):
                for address, expected_bytes in expected_code or ():
                    data = base64.b64decode(emulator.snapshot("code", address, len(expected_bytes))["frame"])
                    (output/f"{name}.code-{address:06x}-{phase}.bin").write_bytes(data)
                    differences = [(address+i,a,b) for i,(a,b) in enumerate(zip(data,expected_bytes)) if a!=b]
                    assert not differences, {"code_phase":phase,"first_code_differences":differences[:12]}
            verify_code("before")
            if expected_disassembly is not None:
                asm_path = (output / f"{name}.asm.log").resolve()
                assert not emulator.qmp.hmp(f"logfile {json.dumps(str(asm_path))}")
                assert not emulator.qmp.hmp("log in_asm")
            if minimal:
                emulator.qmp.execute('qom-set', {'path':'/machine', 'property':'control-observers-minimal', 'value':True})
            emulator.qmp.execute("cont")
            started = time.monotonic()
            deadline = started + timeout
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
                if profile_pc:
                    match = re.match(r"PC=([0-9a-f]+):([0-9a-f]+)", state, re.I)
                    if match:
                        result.setdefault("pc_samples", []).append({
                            "elapsed_seconds": time.monotonic()-started,
                            "pc": int(match[1],16)*65536+int(match[2],16)})
                if f"PC={final >> 16:02x}:{final & 65535:04x}" in state or "UNSUPPORTED=none" not in state:
                    break
                time.sleep(poll_interval)
            emulator.qmp.execute("stop")
            state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
            (output / f"{name}.cpu.txt").write_text(state, encoding="utf-8")
            registers = {int(k): int(v, 16) for k, v in re.findall(
                r"\bR(\d+)\s*=([0-9a-f]{4})\b", "\n".join(state.splitlines()[:5]), re.I)}
            result["registers"] = registers
            if rom_mp3_hle_base:
                result["rom_mp3_hle"] = json.loads(emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "rom-mp3-hle-state"}))
            result.update(timeout_seconds=timeout, poll_interval_seconds=poll_interval,
                          elapsed_seconds=time.monotonic()-started)
            verify_code("after")
            # Preserve guest mismatch evidence even if a long run reaches
            # its deadline before the normal end-of-program assertion.
            if expected_data is not None:
                snapshot = emulator.snapshot("data", 0x2400, len(expected_data) * 2)
                data = base64.b64decode(snapshot["frame"])
                actual = list(struct.unpack(f"<{len(expected_data)}h", data))
                result.update(expected_samples=expected_data, actual_samples=actual)
            # Read-only capture of this owned, stopped guest. Never substitute
            # reference values for its output; retain bytes even after failure.
            for label, address, size in capture_ranges or ():
                assert re.fullmatch(r"[a-z0-9_-]+", label) and 0 <= address < 0x1000000
                assert 0 < size <= 0x1000000-address
                data = bytearray()
                for offset in range(0, size, 0x8000):
                    snapshot = emulator.snapshot("data", address+offset, min(size-offset, 0x8000))
                    data.extend(base64.b64decode(snapshot["frame"]))
                path = output / f"{name}.{label}.bin"
                path.write_bytes(data)
                result.setdefault("captures", {})[label] = {
                    "path": str(path), "address": address, "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest()}
            assert "ROM_MISSING=none" in state and "INVALID_CONTROL=none" in state, state[:2000]
            if fault:
                assert f"UNSUPPORTED={fault}" in state, state[:2000]
            else:
                assert "UNSUPPORTED=none" in state, state[:2000]
                assert f"PC={final >> 16:02x}:{final & 65535:04x}" in state, state[:1500]
            assert all(registers[k] == v for k, v in expected.items()), result
            if expected_disassembly is not None:
                assert not emulator.qmp.hmp("log none")
                assembly = asm_path.read_text(encoding="utf-8")
                assert expected_disassembly in assembly, assembly
                assert "Disassembler disagrees" not in assembly, assembly
                result["expected_disassembly"] = expected_disassembly
            if expected_data is not None:
                assert actual == expected_data, result
            if expected_lcd_state is not None:
                lcd_state = emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "lcd-state"})
                (output / f"{name}.lcd.txt").write_text(lcd_state, encoding="utf-8")
                result["lcd_state_checks"] = {
                    token: token in lcd_state for token in expected_lcd_state}
                assert all(result["lcd_state_checks"].values()), result["lcd_state_checks"]
            for property_name, expected_bytes in (
                    ("lcd-frame", expected_lcd),
                    ("lcd-annunciators", expected_annunciators)):
                if expected_bytes is None:
                    continue
                actual = base64.b64decode(emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": property_name}))
                (output / f"{name}.{property_name}.bin").write_bytes(actual)
                assert len(actual) == len(expected_bytes), (property_name, len(actual))
                differences = [(i, a, e) for i, (a, e) in enumerate(
                    zip(actual, expected_bytes)) if a != e]
                result[property_name] = {
                    "different_bytes": len(differences),
                    "first_differences": differences[:16],
                    "actual_sha256": hashlib.sha256(actual).hexdigest(),
                    "expected_sha256": hashlib.sha256(expected_bytes).hexdigest()}
                assert not differences, result[property_name]
            result["passed"] = True
            print(f"passed {name}", flush=True)
        finally:
            emulator.close()
            result["exit_code"] = emulator.process.returncode
            # Preserve fatal native/QMP diagnostics alongside register results.
            # A process abort may happen before cpu-state can be collected.
            log_output = output / f"{name}.qemu.log"
            log_output.write_bytes(emulator.log_path.read_bytes())
            result["qemu_log"] = str(log_output)
            (output / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def check_original(qemu, output, original, multiplier, gain, icount=None):
    prg = original.read_bytes()
    start, end = FUNCTIONS[multiplier]
    body = prg[start - 0x30000:end - 0x30000]
    # DS1=66 with logical D7E6 maps to physical 33:57E6, not 33:D7E6.
    # Carry the original eight-entry data table into that diagnostic mapping.
    table = prg[0x3057E6:0x3057F6]
    coefficient = struct.unpack("<8h", table)[gain]
    assert list(struct.unpack("<8H", table)) == [0, 0x2027, 0x287A, 0x32F5,
                                                0x4027, 0x50C3, 0x65AD, 0x7FFF]
    rom = bytearray(pack([0x0F00] * ((end + 1) // 2)))
    rom[start:end] = body
    words = [0x6800, 2, 0x6810, 0, 0x6811, 1, 0x68FF, 0x6000, 0x68FB, 0,
             0x68F5, 0xA555]
    for i, sample in enumerate(SAMPLES):
        write_word(words, 0x2400 + 2 * i, sample)
    write_word(words, 0x4A64, gain * 0x101)
    for value in (len(SAMPLES), 0x2400, 0):
        words += [0x68F0, value, 0x58F0]
    words += [0xBD08, start & 65535, 0x50F6]
    read_sfr(words, 0, 2)
    read_sfr(words, 0x10, 3)
    read_sfr(words, 0x11, 4)
    expected = []
    for sample in SAMPLES:
        accumulator = 0
        for _ in range(multiplier):
            accumulator = ((accumulator + sample * coefficient * 2 + 32768) // 65536) * 65536
            accumulator = min(2147483647, max(-2147483648, accumulator))
        expected.append(accumulator // 65536)
    return run(qemu, output, f"original-x{multiplier}-gain{gain}-icount{icount}", words,
               {2: 2, 3: 0, 4: 1, 15: 0x6000}, rom=rom,
               tail=(0x1357E6, table), expected_data=expected, icount=icount,
               metadata={"function": f"08:{start & 65535:04X}", "function_bytes": len(body),
                         "function_sha256": hashlib.sha256(body).hexdigest(),
                         "table_source_offset": 0x3057E6, "coefficient": coefficient,
                         "table_sha256": hashlib.sha256(table).hexdigest()})


def arithmetic_cases():
    # Expected mathematical values are independent constants / integer
    # products. Negative 40-bit results are encoded only at the comparison.
    for signs, x, y, product in ((0, -2, -3, 6), (1, -2, 65535, -131070),
                                  (2, 65535, -2, -131070), (3, 65535, 65535, 4294836225)):
        yield f"signs-{signs}", 0x30 | signs * 4, 0x0001, 7, x, y, 2, product, None
    yield "mac-add", 0x10, 1, 0x123456789, 2, 3, 2, 0x12345678F, None
    yield "mac-sub", 0x11, 1, 2, 2, 3, 2, -4, None
    yield "mac-zero-operands-not-rndst", 0x10, 0, 1, 3, 99, 2, 10, None
    yield "fractional", 0x30, 1, 0, 16384, 16384, 10, 0x20000000, None
    yield "unsigned-no-fractional", 0x3C, 1, 0, 16384, 16384, 10, 0x10000000, None
    yield "round-positive-half", 0xB0, 1, 0, 1, 32767, 2, 0, 1
    yield "round-negative-half", 0xA0, 0, -32768, 77, 99, 2, 0, 5
    yield "saturation-positive", 0x70, 1, 0, -32768, -32768, 10, 2147483647, 0x80
    yield "saturation-negative", 0x50, 1, -2147483648, -1, 1, 2, -2147483648, 0x8C
    yield "global-mas", 0x30, 1, 0, -32768, -32768, 26, 2147483647, 0x80
    yield "round-only-saturation", 0x68, 0, 2147483648, 77, 99, 2, 2147483647, 0x80
    yield "forty-bit-signed-overflow", 0x10, 1, (1 << 39) - 1, 1, 1, 2, -(1 << 39), 0x4A
    yield "forty-bit-carry", 0x10, 1, -1, 1, 1, 2, 0, 5
    yield "muls-operand-acc-overlap", 0x30, 0x0607, 0x0000020003, 99, 99, 2, 6, None


def check_arithmetic(qemu, output, case, icount=None):
    name, cfg, ext, acc, x, y, socr, value, flags = case
    encoded = acc & MASK40
    words = [0x68FF, 0x4000, 0x6800, socr, 0x68F0, x, 0x68F1, y,
             0x68F5, 0xA500 | (encoded >> 32), 0x68F6, (encoded >> 16) & 65535,
             0x68F7, encoded & 65535, 0x6801, 0x31CF, 0xBE00 | cfg, ext]
    read_sfr(words, 1, 4)
    value &= MASK40
    expected = {5: 0xA500 | (value >> 32), 6: (value >> 16) & 65535,
                7: value & 65535, 15: 0x4000}
    if flags is not None:
        expected[4] = 0x3100 | flags
    return run(qemu, output, f"{name}-icount{icount}", words, expected, icount=icount)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--original-prg", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--first-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = {"qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
                "prg_sha256": hashlib.sha256(args.original_prg.read_bytes()).hexdigest()}
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    results = [check_original(args.qemu, args.output, args.original_prg, 1, 7)]
    if not args.first_only:
        for multiplier, gain in ((1, 1), (1, 0), (2, 7), (3, 4), (4, 2), (6, 6)):
            results.append(check_original(args.qemu, args.output, args.original_prg, multiplier, gain))
        results.append(check_original(args.qemu, args.output, args.original_prg, 2, 7, icount=5))
        for case in arithmetic_cases():
            results.append(check_arithmetic(args.qemu, args.output, case))
        for opcode, ext in ((0xBE12, 0), (0xBEF2, 1), (0xBE20, 1), (0xBEF0, 0x1000), (0xBE00, 0x0404)):
            words = [0x68F0, 0x1234, opcode, ext, 0x68F0, 0xBEEF]
            results.append(run(args.qemu, args.output, f"unimplemented-{opcode:04x}-{ext:04x}",
                               words, {0: 0x1234}, fault=f"20:0004 WORD={opcode:04x}"))
    assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity["qemu_sha256"], "build changed"
    (args.output / "report.json").write_text(json.dumps({"passed": True, "identity": identity,
                                                        "cases": results}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
