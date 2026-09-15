#!/usr/bin/env python3
"""Guest-driven priority/preemption, real RETI frames and repeat suspension.

No host writes to guest memory, NAND or ROM service interception. A small
diagnostic guest installs vectors and uses software RQ or actual Timer0 RQ.
These checks do not claim complete IRQ timing, IREP or legacy-tick fidelity.
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

from test_np560_icr_vectors import vector_for
from web.np560_web import Emulator


PSR = 0x01C4
MAIN = 0x400
DATA = 0x2000
ENTRY_REGS = [4, 5, 6, 7]
EXIT_REGS = [13, 10, 9, 8]


def pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def sfr(words, address, register):
    words += [0x1F00 | address, 0x380F | register << 4]


def store(words, address, register=0):
    words += [0xA8F0 | register, address]


def make_guest(levels, *, nseg=False, repeats=1, synthetic=False,
               ed=False, hold=False, edited_return=False, timer=False):
    mode = 2 | (0x20 if nseg else 0)
    handlers = [0x800 + i * 0x100 for i in range(len(levels))]
    image = bytearray(pack([0xD0FF] * 0x1000))
    image[:4] = pack([0xAD20, MAIN])
    main = [0x6800, mode, 0x68FF, 0x4000, 0x68FB, 0,
            0x68FE, 0, 0x68FC, 0]
    if timer:
        assert len(levels) == 2 and not (ed or synthetic or edited_return)
        main += [0x68E9, 0x8020, 0xEE00, 0x682E, 2, 0xFE00, 0x6826, 3999]
    for i, handler in enumerate(handlers):
        vector = vector_for(i)
        if nseg:
            image[vector:vector + 4] = pack([0xAD20, handler])
        else:
            for address, value in ((vector, 0xAD20), (vector + 2, handler)):
                main += [0x68F0, value, 0x3F10]
                store(main, address)
    main += [0x6801, PSR, 0x6800, 0x8000 | mode]
    if repeats > 1:
        repeat_at = len(main)
        main += [0xAE00 | (repeats - 1), 0]
    main += [0x68FC, 0, 0x6801, PSR, 0x6850, 3 | levels[0] << 4]
    resume = [MAIN + len(main) * 2]
    sfr(main, 1, 3)
    main += [0x50E1]  # foreground-only progress, once per repeat iteration
    if repeats > 1:
        main[repeat_at + 1] = MAIN + len(main) * 2
    main += [0x6800, mode]
    final_pc = 0x200000 + MAIN + len(main) * 2
    main += [0xD0FF]
    image[MAIN:MAIN + len(main) * 2] = pack(main)

    for i, handler in enumerate(handlers):
        body = []
        if timer and i == 1:
            body += [0x6827, 0x0080]  # stop actual periodic source in its ISR
        # Record actual live PSR and the RAM frame, not expected host values.
        sfr(body, 1, 0)
        store(body, DATA + i * 16)
        body += [0x080F]  # R0 = SP
        store(body, DATA + i * 16 + 2)
        frame_sp = 0x4000 - (i + 1) * (4 if nseg else 6)
        # Dynamic SP-based reads also make non-preempting cases observable.
        body += [0x081F]
        for field in range(2 if nseg else 3):
            body += [0x2801]  # R0 = [R1]
            store(body, DATA + i * 16 + 4 + field * 2)
            body += [0x5012]  # R1 += 2
        body += [0x50C1, 0x080C | ENTRY_REGS[i] << 4]
        if i == 0 and synthetic:
            # Guest-built RETI enters a same-ISR callback with CIRQ cleared.
            # It must not retire the still-live hardware frame/repeat shadow.
            size = 14 if nseg else 20
            callback = handler + len(body) * 2 + size
            body += [0x68F0, callback, 0x58F0]
            if not nseg:
                body += [0x68F0, 0x20, 0x58F0]
            body += [0x68F0, levels[i] << 12 | PSR, 0x58F0, 0xC610]
        else:
            body += [0x6801, 0x4000 | levels[i] << 12 | PSR]
        if i + 1 < len(levels):
            request = 0x43 if ed else (3 | levels[i + 1] << 4)
            if timer:
                request &= ~2  # no software RQ: only the timer may raise it
            body += [0x6850 + i + 1, request]
            if timer:
                body += [0x6827, 0x8080]
            resume.append(handler + len(body) * 2)
            if timer:
                # Cannot finish the low-priority ISR until its higher-
                # priority timer handler actually runs and writes R10.
                body += [0x56A0, 0xAC01, resume[-1]]
            if edited_return and i == 0:
                body += [0x68F2, 0xDEAD]  # must be skipped by edited RAM PC
                resume[-1] += 4
        elif hold:
            body += [0xD0FF]
        if edited_return and i == 1:
            body += [0x68F0, resume[i]]
            store(body, frame_sp + (2 if nseg else 4))
        body += [0x50C1, 0x080C | EXIT_REGS[i] << 4, 0xC610]
        assert len(body) * 2 < 0x100
        image[handler:handler + len(body) * 2] = pack(body)
    rom = bytearray(b"\x00\x0f" * (0x0840D2 // 2))
    rom[0x0840D0:] = pack([0xC610])  # isolated legacy source, not an ICR
    return image, rom, final_pc, resume


def check(qemu, name, levels=(0, 1, 2, 3), *, output, nseg=False,
          repeats=1, synthetic=False, ed=False, hold=False,
          edited_return=False, icount=None, timer=False):
    image, rom, final_pc, resume = make_guest(
        levels, nseg=nseg, repeats=repeats, synthetic=synthetic,
        ed=ed, hold=hold, edited_return=edited_return, timer=timer)
    result = {"name": name, "levels": levels, "icount": icount,
              "nseg": nseg, "repeats": repeats, "synthetic": synthetic,
              "hardware_timer": timer, "host_guest_memory_writes": 0, "passed": False}
    with tempfile.TemporaryDirectory(prefix="np560-irq-nesting-") as directory:
        root = Path(directory)
        firmware, resident = root / "caller.prg", root / "vectors.bin"
        firmware.write_bytes(image)
        resident.write_bytes(rom)
        emulator = Emulator(qemu=qemu, firmware=firmware, soc_rom=resident,
                            soc_rom_skeleton=True, start_paused=True,
                            icount_shift=icount)
        result["owned_pid"] = emulator.process.pid
        try:
            print(f"checking {name}; owned PID={emulator.process.pid}", flush=True)
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 5
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "cpu-state"})
                if (f"PC={final_pc >> 16:02x}:{final_pc & 0xffff:04x}" in state or
                        (hold and "IRQ_NESTING=DEPTH:4 MAX:4" in state)):
                    break
                time.sleep(0.01)
            emulator.qmp.execute("stop")
            snapshot = emulator.snapshot("data", DATA, 16 * len(levels))
            state = snapshot["registers"]
            (output / f"{name}.cpu.txt").write_text(state, encoding="utf-8")
            registers = {int(k): int(v, 16) for k, v in re.findall(
                r"\bR(\d+)\s*=([0-9a-f]{4})\b", state, re.I) if int(k) < 16}
            raw = base64.b64decode(snapshot["frame"], validate=True)
            frames = [list(struct.unpack_from("<8H", raw, 16 * i)) for i in range(len(levels))]
            result.update(registers=registers, frames=frames, resume=resume,
                          diagnostics=[line for line in state.splitlines()
                                       if line.startswith(("IRQ64=", "IRQ_REPEAT=", "IRQ_NESTING="))])
            for field in ("ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL"):
                assert f"{field}=none" in state, field
            if hold:
                assert "IRQ_NESTING=DEPTH:4 MAX:4" in state, result
                emulator.qmp.execute("system_reset")
                reset = emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "cpu-state"})
                (output / f"{name}.reset.txt").write_text(reset, encoding="utf-8")
                assert "IRQ_NESTING=DEPTH:0 MAX:0 ICR:0" in reset, reset[:1500]
                assert "IRQ_REPEAT=SAVES:0 RESTORES:0 CONFLICTS:0 SAVED:0" in reset
                result["reset_cleared_active_contexts"] = True
            else:
                assert f"PC={final_pc >> 16:02x}:{final_pc & 0xffff:04x}" in state
                preempts = len(levels) > 2 or levels[1] > levels[0] or synthetic
                depth = len(levels) if preempts else 1
                order = (list(range(len(levels))) + list(reversed(range(len(levels))))) if preempts else [0, 0, 1, 1]
                seen = set()
                for sequence, layer in enumerate(order, 1):
                    register = EXIT_REGS[layer] if layer in seen else ENTRY_REGS[layer]
                    assert registers[register] == sequence, (register, sequence, result)
                    seen.add(layer)
                assert registers[15] == 0x4000 and registers[14] == repeats
                assert registers[3] == PSR, result
                for i, frame in enumerate(frames):
                    nesting = i + 1 if preempts else 1
                    parent_psr = (PSR | 0x4000 | levels[i - 1] << 12) if i and preempts else PSR
                    if i == 1 and synthetic:
                        parent_psr &= ~0x4000
                    if i == 1 and timer:
                        # The timer can interrupt CMP or the following
                        # branch. Check upper PSR and every legal boundary;
                        # low arithmetic flags depend on the exact boundary.
                        assert frame[2] & 0xFFF0 == parent_psr & 0xFFF0, frame
                        assert frame[4] in (resume[i], resume[i] + 2), frame
                        parent_psr = frame[2]
                    expected = [PSR | 0x4000 | levels[i] << 12,
                                0x4000 - nesting * (4 if nseg else 6), parent_psr]
                    if not nseg:
                        expected += [0x20]
                    expected += [(resume[i] - (4 if edited_return and i == 1 else 0))
                                 if preempts or i == 0 else resume[0]]
                    if i == 1 and timer:
                        expected[0] = (frame[2] & ~0x3000) | 0x4000 | levels[i] << 12
                        expected[-1] = frame[4]
                    assert frame[:len(expected)] == expected, (i, expected, frame, result)
                assert f"IRQ_NESTING=DEPTH:0 MAX:{depth} ICR:0" in state, result
                irq = next(line for line in state.splitlines() if line.startswith("IRQ64="))
                assert re.search(rf"\bBAD:{1 if edited_return else 0}@", irq), irq
                if repeats > 1:
                    assert f"IRQ_REPEAT=SAVES:{repeats} RESTORES:{repeats} CONFLICTS:0 SAVED:0" in state
                if edited_return:
                    assert registers[2] == 0, result
                if timer:
                    status = emulator.qmp.execute("qom-get", {
                        "path": "/machine", "property": "timer0-state"})
                    result["timer"] = status
                    assert "RUNNING:0" in status and "CONTROL:0080" in status, status
                    assert re.search(r"\bEXPIRED:[1-9][0-9]*\b", status), status
            result["passed"] = True
            print(f"{name}: passed", flush=True)
        finally:
            emulator.close()
            result["exit_code"] = emulator.process.returncode
            (output / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=("first", "all"), default="all")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = {"path": str(args.qemu), "sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    results = [check(args.qemu, "four-priorities", output=args.output)]
    if args.case == "all":
        for name, options in (
            ("equal-pending", {"levels": (1, 1)}),
            ("lower-pending", {"levels": (2, 1)}),
            ("nseg", {"nseg": True}),
            ("icount", {"icount": 5}),
            ("foreground-repeat", {"repeats": 5}),
            ("synthetic-cirq-clear", {"levels": (1, 1), "synthetic": True, "repeats": 5}),
            ("dtu-completion", {"levels": (1, 3), "ed": True}),
            ("hardware-timer", {"levels": (1, 3), "timer": True}),
            ("hardware-timer-icount", {"levels": (1, 3), "timer": True, "icount": 5}),
            ("ram-return-authority", {"levels": (1, 3), "edited_return": True}),
            ("active-reset", {"hold": True}),
        ):
            results.append(check(args.qemu, name, output=args.output, **options))
    (args.output / "report.json").write_text(json.dumps({
        "qemu": identity, "passed": all(r["passed"] for r in results), "cases": results,
    }, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
