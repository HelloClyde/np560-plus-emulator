#!/usr/bin/env python3
"""Verify DMCU byte operands use the high-byte-first word-bus lane."""

from __future__ import annotations

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

    # Word accesses serialize 0x1234 as physical bytes 34 12.  DMCU logical
    # byte address 2000 must therefore select 12, while 2001 selects 34.  This
    # specifically exercises a translated general-register pointer into bank
    # zero; R11/R15 use the separate unbanked stack-SRAM path.
    words = (
        0x6810, 0x0000,       # MOV DS0,#0 (bank-0 internal X RAM view)
        0x68F2, 0x1234,       # MOV R2,#1234
        0x68F3, 0x2000,       # MOV R3,#2000
        0x0A32,               # MOV [R3],R2
        0x2933,               # MOVB RB3,[R3]
        0x1903,               # MOVZE R0,RB3
        0x5031,               # ADD R3,#1
        0x2933,               # MOVB RB3,[R3]
        0x1913,               # MOVZE R1,RB3
        0xAC00, 0x0018,       # AJMP ALWAYS,20:0018
    )

    with tempfile.TemporaryDirectory(prefix="np560-internal-byte-lane-") as work:
        firmware = Path(work) / "internal-byte-lane.prg"
        firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
        emulator = Emulator(qemu=args.qemu, firmware=firmware)
        try:
            deadline = time.monotonic() + 3
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "cpu-state"}
                )
                expected = (
                    re.search(r"^PC=20:0018\b", state) and
                    re.search(r"\bR0\s*=0012\b", state) and
                    re.search(r"\bR1\s*=0034\b", state)
                )
                if expected:
                    print("NP560+ internal byte-lane regression passed")
                    print(state.splitlines()[0])
                    return 0
                if emulator.process.poll() is not None:
                    break
                time.sleep(0.01)
            raise AssertionError(
                "internal byte operands did not select high-byte-first lanes:\n" +
                state
            )
        finally:
            emulator.close()


if __name__ == "__main__":
    raise SystemExit(main())
