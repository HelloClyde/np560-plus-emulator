#!/usr/bin/env python3
"""Explicit reconstructed-ROM holes must stop before architectural TRAP.

Real TRAP execution is checked in test_np560_software_trap.py. Ordinary
0Fxx instructions are no longer expected to stop as unsupported.
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

from web.np560_web import Emulator


def check(qemu: Path, minimal: bool = False) -> None:
    with tempfile.TemporaryDirectory(prefix="np560-trap-strict-") as directory:
        root = Path(directory)
        firmware = root / "trap.prg"
        # R0 is a sentinel.  Falling through the trap would change it to BEEF.
        words = [0x68F0, 0x1234, 0x0F00, 0x68F0, 0xBEEF, 0xD0FF]
        rom = root / "resident.bin"
        rom.write_bytes(bytes(0x010000) + struct.pack("<6H", *words))
        words = [0xBD01, 0x0000, 0xD0FF]
        firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
        emulator = Emulator(qemu=qemu, firmware=firmware, soc_rom=rom,
                            soc_rom_skeleton=True, start_paused=True)
        try:
            emulator.qmp.execute('qom-set', {'path': '/machine',
                'property': 'control-observers-minimal', 'value': minimal})
            emulator.qmp.execute('cont')
            address = "01:0004"
            expected = f"ROM_MISSING={address}"
            state = ""
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "cpu-state"})
                if expected.lower() in state.lower():
                    break
                if emulator.process.poll() is not None:
                    break
                time.sleep(0.01)
            assert expected.lower() in state.lower(), state[:1500]
            assert re.search(r"\bR0\s*=1234\b", state, re.I), state[:1500]
            assert f"PC={address}".lower() in state.lower(), state[:1500]
            assert "INVALID_CONTROL=none" in state, state[:1500]
            assert "UNSUPPORTED=none" in state, state[:1500]
            assert "IRQ_NESTING=DEPTH:0 MAX:0 ICR:0 TRAPS:0" in state, state[:1500]
            print(f"{address} explicit ROM hole: stopped before TRAP; R0 preserved; minimal={minimal}")
        finally:
            emulator.close()
        assert emulator.process.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    args = parser.parse_args()
    for minimal in (False, True):
        check(args.qemu, minimal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
