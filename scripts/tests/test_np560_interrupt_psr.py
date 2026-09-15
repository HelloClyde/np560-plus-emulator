#!/usr/bin/env python3
"""Check architectural PSR words in DMCU interrupt and synthetic RETI frames.

These checks exercise TBC/TBICR hardware frames and guest-built synthetic
frames. They are not a complete nesting, timing or CIRQ validation.
The guest explicitly configures the timebase and uses executable vectors.
"""
from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import re
import struct
import tempfile
import time
from pathlib import Path

from test_np560_bit_sfr_addressing import run
from web.np560_web import Emulator


def test_tick_frame(qemu: Path, psr: int, *, direct_enable: bool = False) -> None:
    with tempfile.TemporaryDirectory(prefix="np560-irq-psr-") as directory:
        root = Path(directory)
        firmware, resident = root / "caller.prg", root / "isr.bin"
        # Enable the actual 64 Hz timebase and priority-3 TBICR. Instructions
        # between writing PSR and the idle branch are flag-neutral MOVs.
        enable = [0x6800, 0x8000] if direct_enable else [0x3F10, 0xA8F0, 0xF100]
        words = [0x6850, 0x0031, 0x682F, 0x8009,
                 0x68F0, 0x8000, 0x6801, psr, *enable,
                 0x1F01, 0x384F, 0xD0FD]
        firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
        # Capture the actual hardware frame before changing any flags, then
        # disable future ticks and clobber PSR to prove RETI restores it.
        handler = [0x081F, 0x2821, 0x4800, 0x3F10, 0xA8F0, 0xF100, 0x4840,
                   0x6801, 0x0000, 0xC610]
        image = bytearray(b"\x00\x0f" * ((0x0840D0 + len(handler) * 2) // 2))
        image[0x010040:0x010044] = struct.pack("<2H", 0xAD08, 0x40D0)
        image[0x0840D0:] = struct.pack(f"<{len(handler)}H", *handler)
        resident.write_bytes(image)
        emulator = Emulator(qemu=qemu, firmware=firmware, soc_rom=resident,
                            soc_rom_skeleton=True)
        try:
            deadline = time.monotonic() + 5
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "cpu-state"})
                # R2 holds the stacked PSR; R4 is sampled after RETI. The
                # handler clears both R4 and live PSR, so pre-IRQ sampling
                # cannot accidentally satisfy the restoration assertion.
                r2 = re.search(r"\bR2\s*=([0-9a-f]{4})\b", state, re.I)
                r4 = re.search(r"\bR4\s*=([0-9a-f]{4})\b", state, re.I)
                returned = re.search(r"(?m)^IRQ64=.*\bRETURNS:([1-9][0-9]*)\b", state)
                if returned and r2 and r4 and int(r2[1], 16) == psr and int(r4[1], 16) == psr:
                    break
                time.sleep(0.01)
            assert r2 and int(r2[1], 16) == psr, state[:1600]
            assert r4 and int(r4[1], 16) == psr, state[:1600]
            assert returned, state[:1600]
            assert "UNSUPPORTED=none" in state and "ROM_MISSING=none" in state, state[:1600]
            print(f"hardware frame and RETI restore PSR={psr:04X}, direct IE={direct_enable}")
        finally:
            emulator.close()


def test_direct_interrupt_mask(qemu: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="np560-irq-mask-") as directory:
        root = Path(directory)
        firmware, resident = root / "caller.prg", root / "isr.bin"
        words = [0x6850, 0x0031, 0x682F, 0x8009,
                 0x68F0, 0x8000, 0x3F10, 0xA8F0, 0xF100, 0xFF00, 0xD0FF]
        firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
        image = bytearray(b"\x00\x0f" * (0x0840D4 // 2))
        image[0x010040:0x010044] = struct.pack("<2H", 0xAD08, 0x40D0)
        image[0x0840D0:] = struct.pack("<2H", 0x5051, 0xC610)
        resident.write_bytes(image)
        emulator = Emulator(qemu=qemu, firmware=firmware, soc_rom=resident,
                            soc_rom_skeleton=True)
        try:
            # Observe several actual timebase periods with the CPU's
            # direct IE cleared, not merely before the first tick fires.
            deadline = time.monotonic() + 3
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "cpu-state"})
                ticks = re.search(r"(?m)^IRQ64=.*\bTICKS:([0-9]+)\b", state)
                if ticks and int(ticks[1]) >= 4:
                    break
                time.sleep(0.01)
            assert ticks and int(ticks[1]) >= 4, state[:1600]
            assert re.search(r"\bR5\s*=0000\b", state, re.I), state[:1600]
            assert re.search(r"(?m)^IRQ64=ENABLED:0 .*\bENTRIES:0\b", state), state[:1600]
            print("direct BCLR SOCR.IE masks the MMIO-enabled interrupt source")
        finally:
            emulator.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    args = parser.parse_args()
    for flags in range(16):
        psr = 0x01C0 | flags  # MX, MS and MV, plus every Z/V/C/N combination.
        run(args.qemu, f"synthetic RETI PSR={psr:04X}", [
            0x68F0, 0x0014, 0x58F0,  # PC
            0x68F0, 0x0020, 0x58F0,  # CS
            0x68F0, psr, 0x58F0,     # PSR
            0xC610, 0x1F01, 0x384F,
        ], {4: psr})
    for psr in (0x01C2, 0x01C4, 0x01C8, 0x01CF):
        test_tick_frame(args.qemu, psr)
    test_tick_frame(args.qemu, 0x01C4, direct_enable=True)
    test_direct_interrupt_mask(args.qemu)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
