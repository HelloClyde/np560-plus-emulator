#!/usr/bin/env python3
"""Verify IGNDS preserves the DMCU high-byte-first SRAM byte lane."""

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    args = parser.parse_args()

    # Store word 0x1234 at internal SRAM 0x2000.  IGNDS selects the unbanked
    # SRAM view, but byte address 0x2000 must still name the high byte (0x12)
    # and 0x2001 the low byte (0x34).  The NP560 clock renderer relies on the
    # same rule when reading the eight glyph rows staged at 0x4844.
    words = (
        0x6810, 0x0000,       # MOV DS0,#0
        0x68F2, 0x1234,       # MOV R2,#1234
        0x68F4, 0x2000,       # MOV R4,#2000
        0x0A42,               # MOV [R4],R2
        0x3F10,               # IGNDS #0
        0x2974,               # MOVB RB7,[R4]
        0x1927,               # MOVZE R2,RB7
        0x5041,               # ADD R4,#1
        0x3F10,               # IGNDS #0
        0x2974,               # MOVB RB7,[R4]
        0x1937,               # MOVZE R3,RB7
        0xD0FF,               # RJMP ALWAYS,self
    )

    with tempfile.TemporaryDirectory(prefix="np560-ignds-byte-lane-") as work:
        firmware = Path(work) / "ignds-byte-lane.prg"
        firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
        emulator = Emulator(qemu=args.qemu, firmware=firmware)
        try:
            deadline = time.monotonic() + 3
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "cpu-state"}
                )
                if (re.search(r"^PC=20:001c\b", state) and
                        re.search(r"\bR2\s*=0012\b", state) and
                        re.search(r"\bR3\s*=0034\b", state)):
                    print("NP560+ IGNDS byte-lane regression passed")
                    print(state.splitlines()[0])
                    return 0
                if emulator.process.poll() is not None:
                    break
                time.sleep(0.01)
            raise AssertionError(
                "IGNDS did not preserve high-byte-first SRAM lanes:\n" + state
            )
        finally:
            emulator.close()


if __name__ == "__main__":
    raise SystemExit(main())
