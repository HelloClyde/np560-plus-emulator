#!/usr/bin/env python3
"""Check the direct-SFR/bit-address contract used by original NP560 drivers.

In source 25:47F4..47FA the Timer2 waiter writes REG[53]=0031 and tests
BIT[53].0.  Source 25:4470..44F0 separately demonstrates the compact
BIT[70] alias of R0.  These two address classes must not be conflated.
"""
from __future__ import annotations

import argparse
import base64
import re
import struct
import tempfile
import time
from pathlib import Path

from web.np560_web import Emulator


def run(qemu: Path, name: str, words: list[int], expected: dict[int, int]) -> None:
    with tempfile.TemporaryDirectory(prefix="np560-bit-sfr-") as directory:
        firmware = Path(directory) / "probe.prg"
        firmware.write_bytes(struct.pack(f"<{len(words) + 1}H", *words, 0xD0FF))
        final_pc = f"PC=20:{len(words) * 2:04x}"
        emulator = Emulator(qemu=qemu, firmware=firmware)
        try:
            deadline = time.monotonic() + 3
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "cpu-state"})
                if final_pc.lower() in state.lower():
                    break
                time.sleep(0.01)
            assert final_pc.lower() in state.lower(), state[:1500]
            for reg, value in expected.items():
                match = re.search(rf"\bR{reg}\s*=([0-9a-f]{{4}})\b", state, re.I)
                assert match and int(match[1], 16) == value, (
                    f"{name}: R{reg} expected {value:04X}; {state[:800]}")
            assert "UNSUPPORTED=none" in state, state[:1500]
            print(f"{name}: {expected}")
        finally:
            emulator.close()


def run_original_waiter(qemu: Path, original_prg: Path) -> None:
    """Unmodified original waiter must complete through real Timer2 IRQs."""
    original = original_prg.read_bytes()
    with tempfile.TemporaryDirectory(prefix="np560-original-t2-wait-") as directory:
        root = Path(directory)
        firmware, resident = root / "caller.prg", root / "waiter.bin"
        image = bytearray(b"\x00\x0f" * (0x084F08 // 2))
        for address, size in ((0x083930, 0x64), (0x0847A4, 0x9C)):
            source_offset = address - 0x030000
            image[address:address + size] = original[source_offset:source_offset + size]
        # The transitional board tick is not Timer2 and still uses 08:40D0.
        # Acknowledge only that unrelated source; do not modify the original
        # Timer2 waiter, its vector at 0058, ISR or countdown.
        image[0x0840D0:0x0840D2] = struct.pack("<H", 0xC610)
        # Exact original code, with only a far-to-near test caller added.
        image[0x084F00:0x084F08] = struct.pack("<4H", 0xBC00, 0x47A4, 0xC620, 0xD0FF)
        resident.write_bytes(image)
        # Supply architectural startup configuration, not a patched waiter:
        # RAM vectors, PLL ratio 1:1 (4 MHz), CLKCON divide-by-one.
        caller = [0x68FF, 0x4000, 0x6800, 0x0002, 0x68E9, 0x8000,
                  0xEE00, 0x682E, 0, 0xFE00, 0x68F0, 3, 0xBD08, 0x4F00,
                  0x68F4, 0x600D, 0xD0FF]
        final_pc = f"PC=20:{2 * (len(caller) - 1):04x}"
        firmware.write_bytes(struct.pack(f"<{len(caller)}H", *caller))
        emulator = Emulator(qemu=qemu, firmware=firmware, soc_rom=resident,
                            soc_rom_skeleton=True, start_paused=True)
        try:
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 5
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "cpu-state"})
                if final_pc in state:
                    break
                time.sleep(0.01)
            assert final_pc in state, state[:1500]
            # Snapshot is a read-only data-bus view, not the code-bus alias.
            snapshot = emulator.snapshot("data", 0x4BB8, 2)
            countdown = struct.unpack("<H", base64.b64decode(snapshot["frame"]))[0]
            assert countdown == 0, countdown
            assert "ROM_MISSING=none" in state and "UNSUPPORTED=none" in state, state[:1500]
            assert re.search(r"\bR4\s*=600d\b", state, re.I), state[:1500]
            assert re.search(r"\bR15\s*=4000\b", state, re.I), state[:1500]
            timer = emulator.qmp.execute("qom-get", {
                "path": "/machine", "property": "timer2-state"})
            expired = re.search(r"\bEXPIRED:(\d+)", timer)
            assert expired and int(expired[1]) >= 3, timer
            assert "RUNNING:0" in timer and "ICR:0000" in timer, timer
            assert "PRELOAD:0000" in timer and "CONTROL:0000" in timer, timer
            print("Original 08:47A4: hardware Timer2 returns, countdown=0, restored SP/config; " + timer)
        finally:
            emulator.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path,
                        help="also require the original Timer2 waiter to finish using hardware IRQs")
    args = parser.parse_args()
    # The original Timer2 wait's write and branch, with a fall-through marker.
    run(args.qemu, "Timer2 direct write / bit test", [
        0x6853, 0x0031, 0x68D3, 0xA550,
        0x68F0, 0x600D, 0x9A53, 0x0002, 0x68F0, 0xBAD0,
    ], {0: 0x600D})
    # BCLR must modify 53, not the distinct high register D3.
    run(args.qemu, "Timer2 bit clear / direct read", [
        0x6853, 0x0031, 0x68D3, 0xA551, 0xF053,
        0x1F53, 0x384F, 0x68F0, 0x600D,
        0x76D3, 0xA551, 0xD102, 0x68F0, 0xBAD0,
    ], {4: 0x0030, 0: 0x600D})
    run(args.qemu, "SOCR and GPIO direct / bit views", [
        0x6800, 0x2082, 0xEF00, 0x1F00, 0x384F,
        0xFF00, 0x6831, 0x4000, 0xE631, 0xFE31, 0x1F31, 0x385F,
    ], {4: 0xA082, 5: 0x0040})
    run(args.qemu, "SOCR MMIO / direct / bit state is shared", [
        0x68F0, 0x0082, 0x3F10, 0xA8F0, 0xF100,
        0xEF00, 0x3F10, 0x88F4, 0xF100, 0xFF00,
        0x1F00, 0x385F,
    ], {4: 0x8082, 5: 0x0082})
    run(args.qemu, "SOCR dedicated MMIO byte lanes preserve the other byte", [
        0x6800, 0x0082,
        0x69F1, 0x0012, 0x3F10, 0xA9F1, 0xF100,
        0x69F1, 0x0034, 0x3F10, 0xA9F1, 0xF101,
        0x1F00, 0x384F, 0x3F10, 0x88F5, 0xF100,
    ], {4: 0x1234, 5: 0x1234})
    run(args.qemu, "R0 compact bit alias remains intact", [
        0x68F0, 0x4001, 0xEF70, 0xFE70,
    ], {0: 0x8001})
    run(args.qemu, "high software bit word remains distinct", [
        0x6809, 0x1234, 0x6889, 0x0000, 0xE389,
        0x1F09, 0x384F, 0x68F0, 0x600D,
        0x9A89, 0x0302, 0x68F0, 0xBAD0,
    ], {4: 0x1234, 0: 0x600D})
    run(args.qemu, "BIT[8E] is the original driver's F01C DPRAM word", [
        0x6810, 0xA2, 0x6811, 0xA3, 0x688E, 0xFFFF,
        0x68F0, 0x0100, 0x3F10, 0xA8F0, 0xF01C,
        0xEF8E, 0xF88E, 0x3F10, 0x88F4, 0xF01C,
        0x69F1, 0x0055, 0x3F10, 0xA9F1, 0xF01D,
        0x68F5, 0x600D, 0x9A8E, 0x0002, 0x68F5, 0xBAD0,
        0x6811, 1, 0x88F6, 0xF01C,
    ], {4: 0x8000, 5: 0x600D, 6: 0x8055})
    run(args.qemu, "F010 audio state shares word/byte/bit/internal RAM views", [
        0x6810, 1, 0x6811, 0xA3, 0x68FB, 0, 0x6888, 0xBEEF,
        0x68F0, 0x1200, 0x3F10, 0xA8F0, 0xF010,
        0x88F4, 0x7010, 0xE588,
        0x69F1, 0xAB, 0x3F10, 0xA9F1, 0xF010,
        0x69F1, 0xCD, 0x3F10, 0xA9F1, 0xF011,
        0x88F5, 0x7010, 0x68F6, 0x600D,
        0x9A88, 0x0F02, 0x68F6, 0xBAD0,
        0x787B, 0xF010, 0x68F8, 0x600D,
        0x7688, 0xBEEF, 0xD102, 0x68F8, 0xBAD0,
    ], {4: 0x1200, 5: 0xABCD, 6: 0x600D, 7: 0xABCD, 8: 0x600D})
    run(args.qemu, "DPRAM upper bit address does not modify R15", [
        0x68FF, 0x4000, 0x68F0, 0x1234, 0x3F10, 0xA8F0, 0xF0FE,
        0xEFFF, 0xF2FF, 0x3F10, 0x88F4, 0xF0FE,
        0x68F5, 0x600D, 0x9AFF, 0x0F02, 0x68F5, 0xBAD0,
    ], {4: 0x9230, 5: 0x600D, 15: 0x4000})
    run(args.qemu, "ICR direct / IGNDS / banked / indirect shared state", [
        0x6853, 0x0031, 0x3F10, 0x88F4, 0xF1A6,
        0x6810, 0x0001, 0x88F5, 0x71A6,
        0x68F0, 0xF1A6, 0x2860,
        0x68F0, 0x0033, 0xA8F0, 0x71A6, 0xF153,
        0x1F53, 0x387F, 0x88F8, 0x71A6,
    ], {4: 0x0031, 5: 0x0031, 6: 0x0031, 7: 0x0031, 8: 0x0031})
    run(args.qemu, "Timer2 byte lanes and direct byte preserve high byte", [
        0x682C, 0xABCD, 0x6810, 0x0001,
        0x69F1, 0x0012, 0xA9F1, 0x7158,
        0x69F1, 0x0034, 0xA9F1, 0x7159,
        0x1F2C, 0x384F, 0x692C, 0x0078, 0x88F5, 0x7158,
    ], {4: 0x1234, 5: 0x1278})
    run(args.qemu, "memory-mapped DS0 selects subsequent data bank", [
        0x68F0, 0x0100, 0xA8F0, 0xF120,
        0x68F0, 0xBEAD, 0xA8F0, 0x0600, 0x88F4, 0x0600,
        0x3F10, 0x88F5, 0x0600, 0x1F10, 0x386F,
    ], {4: 0xBEAD, 5: 0x0000, 6: 0x0100})
    run(args.qemu, "PSR is REG01/F102; software word 81 is independent", [
        0x4800, 0x5600, 0x1F01, 0x384F,
        0x6801, 0x000A, 0x3F10, 0x88F5, 0xF102,
        0x6881, 0x55AA, 0x1F01, 0x386F,
        0x68F0, 0x0004, 0x3F10, 0xA8F0, 0xF102,
        0x68F7, 0x600D, 0x9A01, 0x0202, 0x68F7, 0xBAD0,
    ], {4: 0x0001, 5: 0x000A, 6: 0x000A, 7: 0x600D})
    # Exact carry/DS update sequence from the original burner at 51:D73C.
    # ADD R1 does not carry out of bit 15: BMOV must explicitly set PSR.C
    # from R1.15 before ADDC increments the 32-KiB bank selector.
    for before, after, selector in ((0x7FFF, 0, 0x101), (0x0010, 0x0011, 0x100)):
        run(args.qemu, f"original burner 32-KiB carry at {before:04X}", [
            0x6810, 0x0100, 0x68F1, before, 0x5011,
            0x7C71, 0x01F2, 0x7110, 0x0000, 0xFF71, 0x1F10, 0x384F,
        ], {1: after, 4: selector})
    if args.original_prg:
        run_original_waiter(args.qemu, args.original_prg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
