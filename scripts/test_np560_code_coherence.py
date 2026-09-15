#!/usr/bin/env python3
"""Guest-only executable-RAM writes across QEMU translation-page boundaries.

No NAND, production/reconstructed ROM, runtime host writes or cache-flush
commands. Internal-RAM cases use an all-trap range fixture solely to declare
the executable address range; guest instructions install the entire body.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import tempfile
import time
from pathlib import Path

from web.np560_web import Emulator


def check(qemu, output, name, entry, body, patch, internal=False,
          byte=False, in_place=False, *, icount=None, instruction_clock=False):
    words = [0x6800, 2, 0x68FF, 0x6000, 0x6810, 6]
    replacement = 0xBE34 if byte else 0xBEEF
    if internal:
        words += [0x68FB, entry]
        for index, word in enumerate(body):
            words += [0x68F0, word, 0x6A0B, index * 2]
        words += [0x68F1, 0x1234, 0xBD00, entry, 0x0820,
                  0x68F1, 0xBE if byte else replacement]
        if not in_place:
            # RB3 is R1's low byte; RB1 would read R0's low byte.
            words += [0x6B3B if byte else 0x6A1B, patch]
        words += [0xBD00, entry, 0x0840, 0x783B, patch]
    else:
        words += [0xBD03, entry, 0x0820,           # Keep first return in R2.
                  0x68F1, 0xBEEF, 0xA8F1, patch,  # Guest data-side store.
                  0x88F3, patch,                  # Read written word into R3.
                  0xBD03, entry, 0x0840]          # Keep second return in R4.
    final = 0x030000 + len(words) * 2
    words.append(0xD0FF)
    image = bytearray(0x2000)
    struct.pack_into(f"<{len(words)}H", image, 0, *words)
    if not internal:
        struct.pack_into(f"<{len(body)}H", image, entry, *body)
    expected = {0: replacement, 2: 0x1234, 3: replacement,
                4: replacement, 15: 0x6000}
    result = {"name": name, "passed": False, "entry": entry, "patch": patch,
              "icount": icount, "internal_sram": internal, "host_guest_memory_writes": 0,
              "byte_write": byte, "same_block_write": in_place,
              "nand_used": False, "expected": expected,
              "firmware_sha256": hashlib.sha256(image).hexdigest()}
    with tempfile.TemporaryDirectory(prefix="np560-code-coherence-") as directory:
        firmware = Path(directory) / "selfmod.prg"
        firmware.write_bytes(image)
        resident = None
        if internal:
            resident = Path(directory) / "executable-range-only.bin"
            resident.write_bytes(struct.pack("<H", 0x0F00) * 0x4000)
        emulator = Emulator(qemu=qemu, firmware=firmware, boot_mode="firmware-vma03",
                            soc_rom=resident, soc_rom_skeleton=resident is not None,
                            start_paused=True, icount_shift=icount)
        result["owned_pid"] = emulator.process.pid
        print(f"checking {name}; owned PID={emulator.process.pid}", flush=True)
        try:
            if instruction_clock:
                emulator.qmp.execute("qom-set", {"path":"/machine", "property":"instruction-clock", "value":True})
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
                if (f"PC=03:{final & 65535:04x}" in state or
                        any(f"{field}=none" not in state for field in
                            ("ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL"))):
                    break
                if emulator.process.poll() is not None:
                    raise RuntimeError(f"QEMU exited: {emulator.process.returncode}")
                time.sleep(0.01)
            emulator.qmp.execute("stop")
            state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
            if instruction_clock:
                clock = emulator.qmp.execute("qom-get", {"path":"/machine", "property":"instruction-clock-state"})
                count = emulator.qmp.execute("query-replay")["icount"]
                result.update(instruction_clock=clock, raw_icount=count)
                assert "FAULT:0" in clock and f"INSTRUCTIONS:{count} " in clock, result
            (output / f"{name}.cpu.txt").write_text(state, encoding="utf-8")
            registers = {int(k): int(v, 16) for k, v in re.findall(
                r"\bR(\d+)\s*=([0-9a-f]{4})\b", "\n".join(state.splitlines()[:5]), re.I)}
            result["registers"] = registers
            for field in ("ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL"):
                assert f"{field}=none" in state, state[:1200]
            assert f"PC=03:{final & 65535:04x}" in state, state[:1200]
            assert all(registers[k] == v for k, v in expected.items()), result
            result["passed"] = True
            print(f"passed {name}", flush=True)
        finally:
            emulator.close()
            result["exit_code"] = emulator.process.returncode
            (output / f"{name}.qemu.log").write_bytes(emulator.log_path.read_bytes())
            (output / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


CASES = {
    "same-page": (0x0800, [0x68F0, 0x1234, 0xC620], 0x0802),
    "cross-page-opcode": (0x0FFC, [0xC700, 0xC700, 0x68F0, 0x1234, 0xC620], 0x1002),
    "cross-page-extension": (0x0FFE, [0x68F0, 0x1234, 0xC620], 0x1000),
    "internal-sram": (0x0500, [0x68F0, 0x1234, 0xC620], 2, True),
    "internal-byte": (0x0500, [0x68F0, 0x1234, 0xC620], 2, True, True),
    # Original firmware installs an IRQ body at 00:1202. The old board only
    # exposed X RAM through 00:102D, so instruction fetch saw unrelated ROM.
    "internal-relocated-code": (0x1202, [0x68F0, 0x1234, 0xC620], 2, True),
    # Exercise the last complete six-byte body in architectural 32 KiB X RAM.
    # Do not extend executable RAM into the separate Y memory at 00:8000.
    "internal-x-upper-bound": (0x7FFA, [0x68F0, 0x1234, 0xC620], 2, True),
    # The store changes the following MOV's immediate in the executing TB.
    # Merely invalidating future lookups cannot stop the already running TB.
    "internal-same-block": (0x0500, [0x6A1B, 6, 0x68F0, 0x1234, 0xC620],
                            6, True, False, True),
}


def check_original_relocated_irq(qemu, output, program, *, icount=None):
    """Run the unchanged factory clock ISR from guest-installed X RAM.

    A software ICR request makes the failure deterministic. This does not
    claim to reproduce the factory operation that temporarily swaps vectors.
    """
    body = program.read_bytes()[0x54288:0x5435E]
    assert hashlib.sha256(body).hexdigest() == (
        "f2882b72d2e5947b00f3c395209b3ca6f8be3197445571608e1aed93dfdf008f")
    words = [0x6800, 2, 0x68FF, 0x6000, 0x68FB, 0x1202]
    for index, (word,) in enumerate(struct.iter_unpack("<H", body)):
        words += [0x68F0, word, 0x6A0B, index * 2]
    # Install the RAM vector with guest instructions, never a host patch.
    words += [0x6810, 0, 0x68F0, 0xAD00, 0xA8F0, 0x40,
              0x68F0, 0x1202, 0xA8F0, 0x42,
              0x68F0, 3, 0xA8F0, 0x4B40,
              0x6810, 0xA1, 0x68F0, 0x0A14, 0xA8F0, 0x3840,
              0x6810, 0x66, 0x68F0, 0x1111, 0x68F1, 0x2222,
              0x68F2, 0x3333, 0x6850, 0x33, 0x6800, 0x8002,
              0x6800, 2, 0x1F10, 0x385F,
              0x6810, 0, 0x88F6, 0x4B40,
              0x6810, 0xA1, 0x88F7, 0x3840]
    final = 0x030000 + len(words) * 2
    words += [0xD0FF]
    image = struct.pack(f"<{len(words)}H", *words)
    name = f"original-relocated-irq-icount{icount}"
    expected = {0: 0x1111, 1: 0x2222, 2: 0x3333, 5: 0x66,
                6: 4, 7: 0x0B14, 15: 0x6000}
    result = {"name": name, "passed": False, "icount": icount,
              "expected": expected, "factory_body_sha256": hashlib.sha256(body).hexdigest(),
              "host_guest_memory_writes": 0, "nand_used": False}
    with tempfile.TemporaryDirectory(prefix="np560-xram-irq-") as directory:
        root = Path(directory)
        firmware, resident = root / "caller.prg", root / "range.bin"
        firmware.write_bytes(image)
        resident.write_bytes(struct.pack("<H", 0x0F00) * 0x4000)
        emulator = Emulator(qemu=qemu, firmware=firmware, boot_mode="firmware-vma03",
                            soc_rom=resident, soc_rom_skeleton=True,
                            start_paused=True, icount_shift=icount)
        result["owned_pid"] = emulator.process.pid
        print(f"checking {name}; owned PID={emulator.process.pid}", flush=True)
        try:
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "cpu-state"})
                if (f"PC=03:{final & 65535:04x}" in state or
                        any(f"{field}=none" not in state for field in
                            ("ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL"))):
                    break
                if emulator.process.poll() is not None:
                    raise RuntimeError(f"QEMU exited: {emulator.process.returncode}")
                time.sleep(0.01)
            emulator.qmp.execute("stop")
            state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
            (output / f"{name}.cpu.txt").write_text(state, encoding="utf-8")
            registers = {int(k): int(v, 16) for k, v in re.findall(
                r"\bR(\d+)\s*=([0-9a-f]{4})\b", "\n".join(state.splitlines()[:5]), re.I)}
            result["registers"] = registers
            for field in ("ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL"):
                assert f"{field}=none" in state, state[:1200]
            assert f"PC=03:{final & 65535:04x}" in state, state[:1200]
            assert all(registers[k] == v for k, v in expected.items()), result
            assert "ENTRIES:1 RETURNS:1" in state, state[:1800]
            assert "LAST_OUT:00:12d2>03:" in state, state[:1800]
            result["passed"] = True
            print(f"passed {name}: factory IRQ advances tick and seconds, restores context", flush=True)
        finally:
            emulator.close()
            result["exit_code"] = emulator.process.returncode
            (output / f"{name}.qemu.log").write_bytes(emulator.log_path.read_bytes())
            (output / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case", choices=(*CASES, "original-relocated-irq"))
    parser.add_argument("--original-prg", type=Path)
    parser.add_argument("--instruction-clock", action="store_true",
                        help="test only partial instruction clock with fixed shift=0")
    args = parser.parse_args()
    if args.instruction_clock and args.original_prg:
        parser.error("instruction-clock currently covers executable-write cases only")
    if args.case == "original-relocated-irq" and not args.original_prg:
        parser.error("original-relocated-irq requires --original-prg")
    args.output.mkdir(parents=True, exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"passed": False, "qemu_sha256": identity, "cases": []}
    try:
        for name, parameters in CASES.items():
            if args.case and args.case != name:
                continue
            for icount in ((0,) if args.instruction_clock else (None, 5)):
                report["cases"].append(check(args.qemu, args.output, f"{name}-icount{icount}",
                                              *parameters, icount=icount,
                                              instruction_clock=args.instruction_clock))
        if args.original_prg and args.case in (None, "original-relocated-irq"):
            for icount in (None, 5):
                report["cases"].append(check_original_relocated_irq(
                    args.qemu, args.output, args.original_prg, icount=icount))
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
        report["passed"] = True
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
