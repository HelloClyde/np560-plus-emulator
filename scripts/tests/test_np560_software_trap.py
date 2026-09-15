#!/usr/bin/env python3
"""Guest TRAP vectors, RAM frames, nesting and strict ROM-hole separation.

The diagnostic guest performs every register/memory write. No NAND is used.
This verifies the documented TRAP operation, not all EXR/IREP exceptions.
"""
from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


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

MAIN, HANDLER, INNER, IRQ, DATA = 0x400, 0x800, 0xA00, 0xC00, 0x2400


def pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def record(body, slot, nseg):
    # Preserve a literal snapshot of live PSR and the real SRAM frame before
    # any flag-changing instruction. R1 is a read-only cursor over the frame.
    for offset, reg in ((0, 1), (2, 0), (4, 0x50)):
        read_sfr(body, reg, 0)
        body += [0x3F10, 0xA8F0, DATA + 32 * slot + offset]
    body += [0x080F, 0x3F10, 0xA8F0, DATA + 32 * slot + 6, 0x081F]
    for i in range(2 if nseg else 3):
        body += [0x3F10, 0x3801, 0x3F10, 0xA8F0, DATA + 32 * slot + 8 + 2 * i]


def make_guest(trap, *, nseg=False, ram=False, nested=None, edit_pc=False,
               repeated=False, hold=False, wrap=False, resident_caller=False):
    mode = (0x20 if nseg else 0) | (2 if ram else 0)
    uses_irq = nested in ("irq-in-trap", "trap-in-irq")
    if uses_irq:
        mode |= 0x8000
    psr = 0x01C4 if uses_irq or repeated else 0x71CF
    image = bytearray(pack([0xD0FF] * 0x8000))
    rom = bytearray(pack([0x0F00] * (0x10000)))
    image[:4] = pack([0xAD20, MAIN])
    main = [0x6800, mode & ~0x8000, 0x68FF, 0x4000, 0x68FB, 0,
            0x6810, 0xA2, 0x6811, 0xA3, 0x68FE, 0]
    # Disabled pending TB RQ must survive a TRAP. The main does not configure
    # an oscillator, so no external event can replace the request under test.
    main += [0x6850, 0x0032]
    if uses_irq and not nseg:
        assert ram
        write_word(main, 0x48, 0xAD20)
        write_word(main, 0x4A, IRQ)
    elif uses_irq:
        image[0x48:0x4C] = pack([0xAD20, IRQ])
    main += [0x6800, mode, 0x6801, psr]
    repeat_at = None
    if repeated:
        repeat_at = len(main)
        main += [0xAE02, 0]  # three passes, TRAP inside a multi-insn REPB
        main += [0x6801, psr]
    if wrap:
        # Initial entry sees R12=0. RETI's 16-bit PC wraps to 20:0000 with
        # R12=1, selecting the completed path without host PC injection.
        image[:12] = pack([0x56C0, 0xAC01, MAIN, 0xAD20, 0x600, 0xD0FF])
        main += [0x68FC, 1, 0xAD20, 0xFFFE]
        image[0xFFFE:] = pack([0x0F00 | trap])
        return_pc = 0
        final = 0x200600
    else:
        main += [0x6851, 0x0013] if nested == "trap-in-irq" else [0x0F00 | trap]
        return_pc = MAIN + len(main) * 2
        if edit_pc:
            main += [0x68FD, 0xDEAD]  # guest edits its stacked PC to skip this
        main += [0x50E1]  # completed foreground iterations
        if repeated:
            main[repeat_at + 1] = MAIN + len(main) * 2
        final = 0x200000 + MAIN + len(main) * 2
        main += [0xD0FF]
    image[MAIN:MAIN + len(main) * 2] = pack(main)
    if resident_caller:
        assert not any((nseg, nested, edit_pc, repeated, hold, wrap))
        rom[0x10000 + MAIN:0x10000 + MAIN + len(main) * 2] = pack(main)
        image[:4] = pack([0xAD01, MAIN])
        final = 0x10000 | (final & 0xFFFF)
    bodies = {HANDLER: [], INNER: [], IRQ: []}
    outer = IRQ if nested == "trap-in-irq" else HANDLER
    record(bodies[outer], 0, nseg)
    inner_return = None
    if nested:
        if nested == "irq-in-trap":
            bodies[outer] += [0x6851, 0x0033]
            second = IRQ
        else:
            bodies[outer] += [0x0F38]
            second = INNER
        inner_return = outer + len(bodies[outer]) * 2
        record(bodies[second], 1, nseg)
        bodies[second] += [0x6801, 0, 0xC610]
    if edit_pc:
        write_word(bodies[outer], 0x4000 - (4 if nseg else 6) +
                   (2 if nseg else 4), return_pc + 4)
    bodies[outer] += [0xD0FF] if hold else [0x6801, 0, 0xC610]
    if hold:
        final = 0x200000 + outer + (len(bodies[outer]) - 1) * 2
    for address, body in bodies.items():
        image[address:address + len(body) * 2] = pack(body)
    vectors = image if nseg else rom
    base = 0 if nseg else 0x10000
    vectors[base + trap * 4:base + trap * 4 + 4] = pack([0xAD20, HANDLER])
    vectors[base + 0xE0:base + 0xE4] = pack([0xAD20, INNER])
    return image, rom, final, return_pc, inner_return, mode, psr


def check(qemu, output, name, trap=0x37, *, icount=None, skeleton=True, **options):
    image, rom, final, ret, inner_ret, mode, psr = make_guest(trap, **options)
    nseg, nested = options.get("nseg", False), options.get("nested")
    result = {"name": name, "passed": False, "host_guest_memory_writes": 0,
              "icount": icount, "soc_rom_skeleton": skeleton, "options": options}
    with tempfile.TemporaryDirectory(prefix="np560-trap-") as directory:
        firmware, resident = Path(directory) / "caller.prg", Path(directory) / "vectors.bin"
        firmware.write_bytes(image)
        resident.write_bytes(rom)
        emulator = Emulator(qemu=qemu, firmware=firmware, soc_rom=resident,
                            soc_rom_skeleton=skeleton, icount_shift=icount,
                            start_paused=True)
        result["owned_pid"] = emulator.process.pid
        try:
            print(f"checking {name}; owned PID={emulator.process.pid}", flush=True)
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
                if f"PC={final >> 16:02x}:{final & 65535:04x}" in state or any(
                        field in state for field in ("UNSUPPORTED=20:", "ROM_MISSING=01:")):
                    break
                time.sleep(0.01)
            emulator.qmp.execute("stop")
            snapshot = emulator.snapshot("data", DATA, 64)
            state = snapshot["registers"]
            (output / f"{name}.cpu.txt").write_text(state, encoding="utf-8")
            r = {int(k): int(v, 16) for k, v in re.findall(
                r"\bR(\d+)\s*=([0-9a-f]{4})\b", "\n".join(state.splitlines()[:5]), re.I)}
            records = struct.unpack("<32H", base64.b64decode(snapshot["frame"]))
            result.update(registers=r, records=list(records), diagnostics=[s for s in state.splitlines()
                          if s.startswith(("IRQ64=", "IRQ_NESTING=", "IRQ_REPEAT="))])
            assert f"PC={final >> 16:02x}:{final & 65535:04x}" in state, result
            for field in ("UNSUPPORTED", "ROM_MISSING", "INVALID_CONTROL"):
                assert f"{field}=none" in state, (field, result)
            traps = 3 if options.get("repeated") else 2 if nested == "trap-in-trap" else 1
            assert re.search(rf"\bTRAPS:{traps}\b", state), result
            frame_size = 4 if nseg else 6
            outer_psr = psr | 0x5000 if nested == "trap-in-irq" else psr
            assert records[:5] == (outer_psr, mode, 0x32, 0x4000 - frame_size, psr), result
            caller_cs = 1 if options.get("resident_caller") else 0x20
            assert records[5:5 + (1 if nseg else 2)] == ((ret,) if nseg else (caller_cs, ret)), result
            if nested:
                live = psr | 0x7000 if nested == "irq-in-trap" else outer_psr
                assert records[16:21] == (live, mode, 0x32, 0x4000 - 2 * frame_size, outer_psr), result
                assert records[21:21 + (1 if nseg else 2)] == ((inner_ret,) if nseg else (0x20, inner_ret)), result
            if options.get("hold"):
                emulator.qmp.execute("system_reset")
                reset = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
                assert "IRQ_NESTING=DEPTH:0 MAX:0 ICR:0 TRAPS:0" in reset, reset[:1500]
                result["active_reset_passed"] = True
            else:
                assert r[15] == 0x4000 and "IRQ_NESTING=DEPTH:0" in state, result
                assert r[14] == (0 if options.get("wrap") else 3 if options.get("repeated") else 1), result
                bad = 1 if options.get("edit_pc") else 0
                assert f"BAD:{bad}@" in state, result
                if options.get("edit_pc"):
                    assert r[13] == 0, result
            result["passed"] = True
            print(f"{name}: passed; frame={list(records[:7])}", flush=True)
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
    results = [check(args.qemu, args.output, "segmented-ie-masked")]
    if not args.first_only:
        for name, options in (
            ("trap-zero", {"trap": 0}), ("trap-max-ram-bit", {"trap": 255, "ram": True}),
            ("resident-trap", {"resident_caller": True}),
            ("resident-trap-zero", {"trap": 0, "resident_caller": True, "skeleton": False}),
            ("nseg", {"nseg": True}), ("icount", {"icount": 5}),
            ("trap-in-trap", {"nested": "trap-in-trap"}),
            ("irq-in-trap", {"nested": "irq-in-trap", "ram": True}),
            ("trap-in-irq", {"nested": "trap-in-irq", "ram": True}),
            ("foreground-repeat", {"repeated": True}),
            ("ram-return-authority", {"edit_pc": True}),
            ("pc-wrap", {"wrap": True}), ("active-reset", {"hold": True}),
        ):
            results.append(check(args.qemu, args.output, name, **options))
    assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity["sha256"], \
        "QEMU changed during the run; do not combine results across builds"
    (args.output / "report.json").write_text(json.dumps({"passed": True, "identity": identity,
                                                       "cases": results}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
