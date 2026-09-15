#!/usr/bin/env python3
"""IGNDS must mask CPU hardware interrupts through its memory instruction.

The diagnostic guest creates a pending ICR request, overlaps CRIT/IGNDS, and
stores to unbanked RAM while DS points at a different marker. Early entry
consumes IGNDS in the ISR and sends the foreground store to the wrong bank.
No host writes to guest memory; this is not proof of a historical UI root cause.
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

from test_np560_dtu import read_sfr, read_word, write_word
from web.np560_web import Emulator

MAIN, HANDLER = 0x400, 0x800


def pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def check(qemu, output, count=1, *, upper=False, nseg=False, masked=False,
          timer=False, icount=None):
    name = f"count-{count}-upper-{upper}-nseg-{nseg}-masked-{masked}-timer-{timer}-icount-{icount}"
    logical = 0xA600 if upper else 0x2600
    # 22:A600 falls in the diagnostic boot mode's read-only program mapping;
    # use plain data RAM beyond that mapping to exercise DS1 independently.
    ds1 = 0xC1 if upper else 0x45
    mode = 2 | (0x20 if nseg else 0)
    image = bytearray(pack([0xD0FF] * 0x1000))
    image[:4] = pack([0xAD20, MAIN])
    words = [0x6800, mode, 0x68FF, 0x4000, 0x68FB, 0,
             0x6810, 0x44, 0x6811, ds1]
    if nseg:
        image[0x48:0x4C] = pack([0xAD20, HANDLER])
    else:
        write_word(words, 0x48, 0xAD20)
        write_word(words, 0x4A, HANDLER)
    write_word(words, logical, 0x1111)
    write_word(words, logical, 0xEEEE, banked=True)
    if timer:
        assert not masked
        # Actual Timer0 sets RQ while global IE=0. Stop its clock after RQ,
        # retaining the real pending event; no instruction sets ICR.RQ.
        words += [0xEE00, 0x682E, 0x10, 0xFE00, 0x6826, 31, 0x6851, 0x31,
                  0x6827, 0x8080, 0x9B51, 0x01FE, 0xFF27]
    words += [0x68F0, 0x1234, 0x68F9, 0, 0x6801, 0x01C4]
    if timer:
        words += [0x3F01, 0x6800, mode | 0x8000]
    else:
        words += [0x6800, mode | (0 if masked else 0x8000), 0x3F01, 0x6851, 0x33]
    # CRIT ends after IGNDS itself, leaving only IGNDS to block the pending
    # interrupt. Keep the existing encoded 0..3 -> 1..4 count convention.
    words += [0x3F10 | (count - 1)]
    words += [0x5091] * (count - 1)
    words += [0xA8F0, logical]
    expected_entry = 0x200000 + MAIN + len(words) * 2
    read_word(words, logical, 7)
    read_word(words, logical, 8, banked=True)
    read_sfr(words, 0x51, 3)
    read_sfr(words, 0, 4)
    final = 0x200000 + MAIN + len(words) * 2
    words += [0xD0FF]
    image[MAIN:MAIN + len(words) * 2] = pack(words)
    body = [0x88F5, logical, 0x0869, 0xC610]
    image[HANDLER:HANDLER + len(body) * 2] = pack(body)
    result = {"name": name, "passed": False, "host_guest_memory_writes": 0,
              "count": count, "logical_address": logical,
              "banked_address": ((ds1 if upper else 0x44) << 15) | (logical & 0x7FFF),
              "nseg": nseg, "global_ie_masked": masked, "hardware_timer": timer, "icount": icount}
    with tempfile.TemporaryDirectory(prefix="np560-ignds-irq-") as directory:
        firmware = Path(directory) / "caller.prg"
        resident = Path(directory) / "resident.bin"
        firmware.write_bytes(image)
        resident.write_bytes(pack([0x0F00] * 0x10000))
        emulator = Emulator(qemu=qemu, firmware=firmware, soc_rom=resident,
                            soc_rom_skeleton=True, start_paused=True, icount_shift=icount)
        result["owned_pid"] = emulator.process.pid
        try:
            print(f"checking {name}; owned PID={emulator.process.pid}", flush=True)
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
                if f"PC={final >> 16:02x}:{final & 65535:04x}" in state:
                    break
                time.sleep(0.01)
            emulator.qmp.execute("stop")
            state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
            (output / f"{name}.cpu.txt").write_text(state, encoding="utf-8")
            registers = {int(k): int(v, 16) for k, v in re.findall(
                r"\bR(\d+)\s*=([0-9a-f]{4})\b", "\n".join(state.splitlines()[:5]), re.I)}
            result.update(registers=registers, expected_entry=expected_entry,
                          diagnostics=[s for s in state.splitlines() if s.startswith(("IRQ64=", "IRQ_NESTING="))])
            if timer:
                result["timer"] = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "timer0-state"})
                assert re.search(r"\bEXPIRED:[1-9]\d*\b", result["timer"]), result
            assert f"PC={final >> 16:02x}:{final & 65535:04x}" in state, result
            for field in ("UNSUPPORTED", "ROM_MISSING", "INVALID_CONTROL"):
                assert f"{field}=none" in state, result
            expected = {3: 0x33 if masked else 0x31, 4: mode | (0 if masked else 0x8000),
                        5: 0 if masked else 0xEEEE, 6: 0 if masked else count - 1,
                        7: 0x1234, 8: 0xEEEE, 9: count - 1, 15: 0x4000}
            assert all(registers[k] == value for k, value in expected.items()), (expected, result)
            if not masked:
                assert f"LAST_IN:{expected_entry >> 16:02x}:{expected_entry & 65535:04x}/" in state, result
                assert "ENTRIES:1 RETURNS:1" in state and "BAD:0@" in state, result
            else:
                assert "ENTRIES:0 RETURNS:0" in state, result
            result["passed"] = True
            print(f"passed: unbanked={registers[7]:04x}, banked={registers[8]:04x}, ISR read={registers[5]:04x}", flush=True)
        finally:
            emulator.close()
            result["exit_code"] = emulator.process.returncode
            (output / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = {"qemu": str(args.qemu), "sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    results = [check(args.qemu, args.output)]
    if not args.first_only:
        for count in (2, 3, 4):
            results.append(check(args.qemu, args.output, count))
        for options in ({"upper": True}, {"nseg": True}, {"masked": True}, {"icount": 5},
                        {"timer": True}, {"timer": True, "icount": 5}):
            results.append(check(args.qemu, args.output, **options))
    assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity["sha256"], "build changed"
    (args.output / "report.json").write_text(json.dumps({"passed": True, "identity": identity, "cases": results}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
