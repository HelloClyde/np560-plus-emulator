#!/usr/bin/env python3
"""Verify DMCU MUL/UMUL return in R6:R7 without clobbering R4:R5."""

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

    words = (
        0x68F4, 0xA5A5,       # MOV R4,#A5A5
        0x68F5, 0xFE74,       # MOV R5,#FE74 (far-pointer low word)
        0x68F2, 0x0048,       # MOV R2,#0048
        0x68F3, 0x0003,       # MOV R3,#0003
        0xC123,               # UMUL R2,R3 -> R6:R7 = 0000:00D8
        0xAC00, 0x0012,       # AJMP ALWAYS,20:0012
    )

    with tempfile.TemporaryDirectory(prefix="np560-multiply-registers-") as work:
        firmware = Path(work) / "multiply-registers.prg"
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
                    re.search(r"^PC=20:0012\b", state) and
                    re.search(r"\bR4\s*=a5a5\b", state, re.IGNORECASE) and
                    re.search(r"\bR5\s*=fe74\b", state, re.IGNORECASE) and
                    re.search(r"\bR6\s*=0000\b", state, re.IGNORECASE) and
                    re.search(r"\bR7\s*=00d8\b", state, re.IGNORECASE)
                )
                if expected:
                    print("NP560+ multiply register-preservation test passed")
                    print(state.splitlines()[0])
                    return 0
                if emulator.process.poll() is not None:
                    break
                time.sleep(0.01)
            raise AssertionError(
                "UMUL result or preserved registers were incorrect:\n" + state
            )
        finally:
            emulator.close()


if __name__ == "__main__":
    raise SystemExit(main())
