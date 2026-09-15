#!/usr/bin/env python3
"""Exercise DMCU ICR software requests through guest-installed vector code.

Not a Timer2/nesting/DTU implementation test. No host guest-memory writes.
The legacy board tick has a separate RETI fixture and is not called Timer2.
"""
from __future__ import annotations

import argparse
import re
import struct
import tempfile
import time
from pathlib import Path

from web.np560_web import Emulator


def vector_for(source: int) -> int:
    return 0x40 + source * 8 if source < 16 else 0xC0 + (source - 16) * 4


def check(qemu: Path, name: str, source: int = 3, *, ram: bool = True,
          nseg: bool = False, icr: int = 0x33, psr: int = 0x01C4,
          accepted: bool = True, masked_first: bool = False,
          icount: int | None = None, original_prg: Path | None = None) -> None:
    reg, vector = 0x50 + source, vector_for(source)
    handler = 0x200
    mode = (2 if ram else 0) | (0x20 if nseg else 0)
    words = [0x68FF, 0x4000, 0x68FB, 0]
    if ram and not nseg:
        # The guest itself installs the executable SJMP, just as the
        # original Timer2 driver does; never interpret vector data on host.
        words += [0x68F0, 0xAD20, 0x3F10, 0xA8F0, vector,
                  0x68F0, handler, 0x3F10, 0xA8F0, vector + 2]
    if original_prg is not None:
        assert source == 3 and not nseg
        words += [0x68F0, 1, 0xA8F0, 0x4BB8, 0x682D, 0x0080]
    words += [0x6801, psr]
    if masked_first:
        # RQ survives a disabled source, then EN makes it deliverable.
        words += [0x6800, mode | 0x8000, 0x6800 | reg, icr & ~1,
                  0x1F00 | reg, 0x388F, 0x6800 | reg, icr]
    else:
        # A request also survives global IE=0 and fires after IE is set.
        words += [0x6800 | reg, icr, 0x6800, mode | 0x8000]
    words += [0x6800, mode, 0x1F01, 0x386F]
    if original_prg is not None:
        words += [0x1F53, 0x388F, 0x88F9, 0x4BB8, 0x1F2D, 0x38AF]
    final_pc = f"PC=20:{len(words) * 2:04x}"
    words += [0xD0FF]
    image = bytearray(b"\xff\xd0" * 0x200)
    image[:len(words) * 2] = struct.pack(f"<{len(words)}H", *words)
    isr = [0x68F4, source + 1, 0x1F01, 0x385F,
           0x1F00 | reg, 0x387F, 0x082F, 0xC610]
    if original_prg is not None:
        isr[-1:] = [0xAD08, 0x481A]
    image[handler:handler + len(isr) * 2] = struct.pack(f"<{len(isr)}H", *isr)
    # ROM vectors and NSEG vectors are instruction bytes, not pointers.
    rom = bytearray(b"\x00\x0f" * (0x084840 // 2))
    rom[0x0840D0:0x0840D2] = struct.pack("<H", 0xC610)
    if original_prg is not None:
        original = original_prg.read_bytes()
        # Unmodified original T2 ISR. Only the source of RQ is software in
        # this check; it must decrement 4BB8 and clear 2D/53 itself.
        rom[0x08481A:0x084840] = original[0x05481A:0x054840]
    if nseg:
        assert len(words) * 2 <= vector, "test caller overlaps its vector"
        image[vector:vector + 4] = struct.pack("<2H", 0xAD20, handler)
    elif not ram:
        rom[0x10000 + vector:0x10004 + vector] = struct.pack("<2H", 0xAD20, handler)
    with tempfile.TemporaryDirectory(prefix="np560-icr-") as directory:
        root = Path(directory)
        firmware, resident = root / "caller.prg", root / "vectors.bin"
        firmware.write_bytes(image)
        resident.write_bytes(rom)
        emulator = Emulator(qemu=qemu, firmware=firmware, soc_rom=resident,
                            soc_rom_skeleton=True, icount_shift=icount,
                            start_paused=True)
        try:
            print(f"checking {name}; owned QEMU PID={emulator.process.pid}", flush=True)
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 4
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "cpu-state"})
                if final_pc.lower() in state.lower():
                    break
                time.sleep(0.01)
            assert final_pc.lower() in state.lower(), (name, state[:2000])
            expected = {4: source + 1 if accepted else 0, 6: psr, 15: 0x4000}
            if accepted:
                expected.update({2: 0x3FFC if nseg else 0x3FFA,
                                 5: (psr & ~0x3000) | 0x4000 |
                                 (0x3000 if icr & 0x40 else (icr & 0x30) << 8),
                                 7: icr & ~2})
            if masked_first:
                expected[8] = icr & ~1
            if original_prg is not None:
                expected.update({8: 0, 9: 0, 10: 0})
            for register, value in expected.items():
                match = re.search(rf"\bR{register}\s*=([0-9a-f]{{4}})\b", state, re.I)
                assert match and int(match[1], 16) == value, (name, expected, state[:2000])
            for field in ("ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL"):
                assert f"{field}=none" in state, (name, state[:2000])
            print(f"{name}: {expected}", flush=True)
        finally:
            emulator.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path)
    args = parser.parse_args()
    for source in (0, 3, 15, 16, 31):
        check(args.qemu, f"RAM vector source {source}", source)
    check(args.qemu, "ROM vector selected by SOCR.RAM=0", ram=False)
    check(args.qemu, "NSEG four-byte frame and RETI", nseg=True)
    check(args.qemu, "RQ survives EN=0", masked_first=True)
    check(args.qemu, "empty ED channel requests CPU refill", icr=0x73)
    check(args.qemu, "empty ED channel 0 uses completion priority 3", icr=0x43)
    check(args.qemu, "priority below CPRI remains pending", psr=0x3000, icr=0x23, accepted=False)
    check(args.qemu, "equal priority allowed in foreground", psr=0x3000)
    check(args.qemu, "equal priority blocked by CIRQ", psr=0x7000, accepted=False)
    check(args.qemu, "software IRQ is precise under icount", icount=5)
    if args.original_prg:
        check(args.qemu, "original T2 ISR consumes a software IRQ",
              original_prg=args.original_prg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
