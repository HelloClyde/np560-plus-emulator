#!/usr/bin/env python3
"""Verify the actual TBC/TBICR and software-owned countdown words.

All setup is guest code; no host guest-memory writes or NAND are involved.
Original cases execute unmodified vector installation, TB setup and ISR code.
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

from test_np560_dtu import read_sfr, read_word, write_word
from web.np560_web import Emulator, QMPError


def pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def run(qemu, output, name, words, verify, *, original=None, icount=None,
        reset=False):
    final_pc = f"PC=20:{len(words) * 2:04x}"
    image = bytearray(pack([*words, 0xD0FF]))
    rom = bytearray(b"\x00\x0f" * (0x08427A // 2))
    if original:
        data = original.read_bytes()
        image.extend(bytes(0x32DC66 - 0x200000 - len(image)))
        image[0x1281D4:0x128204] = data[0x2F81D4:0x2F8204]
        image[0x12DC20:0x12DC66] = data[0x2FDC20:0x2FDC66]
        rom[0x0840D0:0x08427A] = data[0x0540D0:0x05427A]
    else:
        # Only for the pre-change binary in the counterexample: harmless
        # legacy handler, so an unrelated missing ROM cannot cause failure.
        rom[0x0840D0:0x0840D2] = pack([0xC610])
    result = {"name": name, "icount": icount, "passed": False,
              "host_guest_memory_writes": 0}
    with tempfile.TemporaryDirectory(prefix="np560-timebase-") as directory:
        firmware, resident = Path(directory) / "caller.prg", Path(directory) / "isr.bin"
        firmware.write_bytes(image)
        resident.write_bytes(rom)
        emulator = Emulator(qemu=qemu, firmware=firmware, soc_rom=resident,
                            soc_rom_skeleton=True, start_paused=True,
                            icount_shift=icount)
        result["owned_pid"] = emulator.process.pid
        try:
            print(f"checking {name}; owned PID={emulator.process.pid}", flush=True)
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 15
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
                if final_pc.lower() in state.lower():
                    break
                time.sleep(0.01)
            emulator.qmp.execute("stop")
            snapshot = emulator.snapshot("data", 0x0490, 12)
            state = snapshot["registers"]
            (output / f"{name}.cpu.txt").write_text(state, encoding="utf-8")
            # Later diagnostics also contain R0/R9 labels. Only the actual
            # register header is authoritative; do not overwrite it with
            # historical trace fields from another instruction.
            header = "\n".join(state.splitlines()[:5])
            registers = {int(k): int(v, 16) for k, v in re.findall(
                r"\bR(\d+)\s*=([0-9a-f]{4})\b", header, re.I) if int(k) < 16}
            try:
                tb = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "timebase-state"})
            except QMPError as error:
                tb = str(error)  # old binary counterexample has no such property
            result.update(registers=registers, timebase=tb,
                          ram=list(struct.unpack("<6H", base64.b64decode(snapshot["frame"]))),
                          diagnostics=[s for s in state.splitlines() if s.startswith(("IRQ64=", "IRQ_NESTING="))])
            assert final_pc.lower() in state.lower(), result
            for field in ("ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL"):
                assert f"{field}=none" in state, (field, state[:1200])
            verify(result)
            # While paused, real oscillator state must not progress.
            time.sleep(0.03)
            after = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "timebase-state"})
            assert after == tb, (tb, after)
            if reset:
                emulator.qmp.execute("system_reset")
                result["reset"] = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "timebase-state"})
                assert result["reset"] == "RUNNING:0 HZ:32768 CONTROL:0000 ICR:0000 EXPIRED:0 UNSUPPORTED_CONFIGS:0"
            result["passed"] = True
            print(f"{name}: {tb}; R4..7={[registers.get(i) for i in range(4, 8)]}", flush=True)
        finally:
            emulator.close()
            result["exit_code"] = emulator.process.returncode
            (output / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def check_frozen(qemu, output, *, icount=None):
    words = [0x6800, 2, 0xEE00, 0x682E, 0x10, 0xFE00]  # IE=0; Timer0 at 32768 Hz
    for address, value in ((0x494, 100), (0x496, 200), (0x498, 300)):
        write_word(words, address, value)
    words += [0x6826, 8191, 0x6827, 0x8080, 0x9B51, 0x01FE, 0xFF27]
    for address, register in ((0x494, 4), (0x496, 5), (0x498, 6)):
        read_word(words, address, register)
    def verify(result):
        assert [result["registers"][i] for i in (4, 5, 6)] == [100, 200, 300], result
        assert result["ram"][2:5] == [100, 200, 300], result
        assert "RUNNING:0" in result["timebase"] and "EXPIRED:0" in result["timebase"]
    return run(qemu, output, f"software-ram-frozen-{icount}", words, verify, icount=icount)


def check_frequency(qemu, output, select, *, icount=None, active_reset=False):
    words = [0x6800, 2, 0x6850, 0, 0x682F, 0x8000 | select,
             0x9B50, 0x01FE]  # EN=0, but actual TB must latch RQ
    if not active_reset:
        words += [0xFF2F]
    read_sfr(words, 0x50, 4)
    read_sfr(words, 0x2F, 5)
    def verify(result):
        assert result["registers"][4] == 2, result
        assert result["registers"][5] == select | (0x8000 if active_reset else 0), result
        assert f"HZ:{32768 >> select} " in result["timebase"], result
        assert re.search(r"\bEXPIRED:[1-9][0-9]*\b", result["timebase"]), result
        assert any("ENTRIES:0 " in s for s in result["diagnostics"]), result
    return run(qemu, output, f"frequency-{select}-{icount}-{active_reset}", words,
               verify, icount=icount, reset=active_reset)


def check_original(qemu, output, original, *, icount=None):
    words = [0x6800, 2, 0x68FF, 0x6000, 0x68FB, 0]
    for value in (0x40D0, 8, 0x10):
        words += [0x68F0, value, 0x58F0]
    words += [0xBD32, 0x81D4, 0x50F6, 0xBD32, 0xDC20]
    # The original software guard keeps the app callback out of this narrow
    # fixture; the ISR's real counter updates and RETI still execute.
    write_word(words, 0xF01E, 1)
    for address, value in ((0x494, 100), (0x496, 3), (0x498, 0)):
        write_word(words, address, value)
    words += [0xEF00]
    loop = len(words) * 2
    read_word(words, 0x4B40, 7)
    words += [0x5674, 0xAC05, loop, 0xFF00, 0xFF2F]
    for address, register in ((0x494, 4), (0x496, 5), (0x498, 6)):
        read_word(words, address, register)
    read_word(words, 0x4B40, 7)
    read_word(words, 0x40, 8)
    read_word(words, 0x42, 9)
    def verify(result):
        r = result["registers"]
        assert 4 <= r[7] <= 100 and r[4] == 100 - r[7], result
        assert (r[5], r[6], r[8], r[9], r[15]) == (0, 0, 0xAD08, 0x40D0, 0x6000), result
        assert result["ram"][2:5] == [r[4], 0, 0], result
        assert "CONTROL:0009" in result["timebase"] and "HZ:64 " in result["timebase"], result
        assert any("BAD:0@" in s for s in result["diagnostics"]), result
    return run(qemu, output, f"original-tb-init-isr-{icount}", words, verify,
               original=original, icount=icount)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path)
    parser.add_argument("--counterexample", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = {"qemu": str(args.qemu), "sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    results = [check_frozen(args.qemu, args.output)]
    if not args.counterexample:
        results.append(check_frozen(args.qemu, args.output, icount=5))
        for select in (0, 9, 14):
            results.append(check_frequency(args.qemu, args.output, select))
        results.append(check_frequency(args.qemu, args.output, 9, icount=5))
        results.append(check_frequency(args.qemu, args.output, 9, active_reset=True))
        if args.original_prg:
            for icount in (None, 5):
                results.append(check_original(args.qemu, args.output, args.original_prg, icount=icount))
    (args.output / "report.json").write_text(json.dumps({"identity": identity, "passed": True, "cases": results}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
