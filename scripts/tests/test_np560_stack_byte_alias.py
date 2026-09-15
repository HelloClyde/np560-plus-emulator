#!/usr/bin/env python3
"""Verify bank-zero byte pointers alias unbanked R11 stack-byte operands."""

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

    # The vendor resource reader passes FP-1 as the destination of resident
    # far memcpy 18:6D56.  That routine writes it through a bank-zero general
    # pointer, while the caller consumes it as MOVB RB1,[R11-1].  Both paths
    # must therefore select the same physical byte lane.
    words = (
        0x68FB, 0x2100,       # MOV R11/FP,#2100
        0x6810, 0x0000,       # MOV DS0,#0 (bank-zero X RAM view)
        0x68F0, 0x00A5,       # MOV R0,#00A5 (RB1=A5)
        0x68F3, 0x20FF,       # MOV R3,#20FF (FP-1)
        0x0B31,               # MOVB [R3],RB1 (translated bank-zero path)
        0x793B, 0xFFFF,       # MOVB RB3,[R11-1] (unbanked frame path)
        0x1903,               # MOVZE R0,RB3
        0xAC00, 0x0018,       # AJMP ALWAYS,20:0018
    )

    with tempfile.TemporaryDirectory(prefix="np560-stack-byte-alias-") as work:
        firmware = Path(work) / "stack-byte-alias.prg"
        firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
        emulator = Emulator(qemu=args.qemu, firmware=firmware)
        try:
            deadline = time.monotonic() + 3
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "cpu-state"}
                )
                if (re.search(r"^PC=20:0018\b", state) and
                        re.search(r"\bR0\s*=00a5\b", state)):
                    print("NP560+ stack-byte/data-bus alias regression passed")
                    print(state.splitlines()[0])
                    return 0
                if emulator.process.poll() is not None:
                    break
                time.sleep(0.01)
            raise AssertionError(
                "bank-zero pointer did not alias the R11 byte local:\n" + state
            )
        finally:
            emulator.close()


if __name__ == "__main__":
    raise SystemExit(main())
