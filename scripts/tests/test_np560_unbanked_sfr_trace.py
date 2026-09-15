#!/usr/bin/env python3
"""Verify the observer-only IGNDS SFR inventory and unknown-write ring."""

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

    words = (
        0x68F2, 0x1234,       # MOV R2,#1234
        0x68F4, 0xF800,       # MOV R4,#F800 (currently unknown)
        0x3F10,               # IGNDS #0
        0x0A42,               # MOV [R4],R2
        0x68F2, 0x0000,       # MOV R2,#0
        0x68F4, 0xF100,       # MOV R4,#F100 (modelled system control)
        0x3F10,               # IGNDS #0
        0x0A42,               # MOV [R4],R2
        0x6810, 0x0001,       # MOV DS0,#1
        0x68F2, 0x5678,       # MOV R2,#5678
        0x68F4, 0x7800,       # MOV R4,#7800 -> physical F800
        0x0A42,               # MOV [R4],R2
        0x68F2, 0x0000,       # MOV R2,#0
        0x68F4, 0x7100,       # MOV R4,#7100 -> modelled physical F100
        0x0A42,               # MOV [R4],R2
        0x6827, 0xC080,       # MOV REG[27],#C080
        0x7539, 0x8000,       # OR REG[39],#8000
        0x7441, 0x7FFF,       # AND REG[41],#7FFF
        0xD0FF,               # RJMP ALWAYS,self
    )

    with tempfile.TemporaryDirectory(prefix="np560-sfr-trace-") as work:
        firmware = Path(work) / "sfr-trace.prg"
        firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
        emulator = Emulator(qemu=args.qemu, firmware=firmware)
        try:
            deadline = time.monotonic() + 3
            state = ""
            expected = re.compile(
                r"^UNBANKED_SFR_WRITE=TOTAL:2 UNKNOWN:1 "
                r"BUCKETS:.*\bF1=1\b.*\bF8=1\b.*"
                r"TRACE:#0/g0/20:000a/af800=1234/b16/",
                re.MULTILINE,
            )
            while time.monotonic() < deadline:
                state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "cpu-state"}
                )
                if expected.search(state):
                    banked = re.search(
                        r"^BANKED_FXXX_WRITE=TOTAL:2 UNKNOWN:1 "
                        r"BUCKETS:.*\bF1=1\b.*\bF8=1\b.*"
                        r"TRACE:#0/g0/20:0024/l7800/pf800=5678/b16/",
                        state,
                        re.MULTILINE,
                    )
                    if banked is None:
                        time.sleep(0.01)
                        continue
                    direct = re.search(
                        r"^DIRECT_SFR_WRITE=TOTAL:3 "
                        r"COUNTS:27=1,39=1,41=1 "
                        r"TRACE:#0/g0/20:0030/r27=0000>c080/b16/.*;"
                        r"#1/g1/20:0034/r39=0000>8000/b16/.*;"
                        r"#2/g2/20:0038/r41=0000>0000/b16/",
                        state,
                        re.MULTILINE,
                    )
                    if direct is None:
                        time.sleep(0.01)
                        continue
                    print("NP560+ unbanked SFR trace regression passed")
                    print(next(
                        line for line in state.splitlines()
                        if line.startswith("UNBANKED_SFR_WRITE=")
                    ))
                    print(next(
                        line for line in state.splitlines()
                        if line.startswith("BANKED_FXXX_WRITE=")
                    ))
                    print(next(
                        line for line in state.splitlines()
                        if line.startswith("DIRECT_SFR_WRITE=")
                    ))
                    return 0
                if emulator.process.poll() is not None:
                    break
                time.sleep(0.01)
            raise AssertionError(
                "IGNDS SFR observer did not separate modelled and unknown "
                "writes:\n" + state
            )
        finally:
            emulator.close()


if __name__ == "__main__":
    raise SystemExit(main())
