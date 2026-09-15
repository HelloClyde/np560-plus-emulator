#!/usr/bin/env python3
"""Run the unmodified nine-copy PRG initializer to its missing ROM tail."""

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import re
import time
from pathlib import Path

from web.np560_web import Emulator


EXPECTED = {
    0x5322DE: bytes(range(0x14, 0x18)),
    0x532364: bytes([0x30]),
    0x532376: bytes(range(0x34, 0x36)),
    0x5323A2: bytes(range(0x3E, 0x40)),
    0x53237A: bytes(range(0x38, 0x3A)),
    0x532378: bytes(range(0x36, 0x38)),
    0x53228E: bytes(range(0x10, 0x14)),
    0x532366: bytes(range(0x32, 0x34)),
    0x5322DA: bytes(range(0x20, 0x24)),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--soc-rom", type=Path, required=True)
    args = parser.parse_args()

    emulator = Emulator(
        qemu=args.qemu,
        firmware=args.firmware,
        soc_rom=args.soc_rom,
        soc_rom_skeleton=True,
    )
    try:
        deadline = time.monotonic() + 15
        while True:
            state = emulator.qmp.execute(
                "qom-get", {"path": "/machine", "property": "cpu-state"}
            )
            if re.search(r"\bROM_MISSING=03:026a\b", state, re.IGNORECASE):
                break
            if emulator.process.poll() is not None:
                raise AssertionError(
                    f"QEMU exited with {emulator.process.returncode}:\n{state}"
                )
            if time.monotonic() >= deadline:
                raise AssertionError(
                    "vendor initializer did not reach resident continuation 03:026A:\n"
                    + state
                )
            time.sleep(0.01)

        for address, expected in EXPECTED.items():
            emulator.qmp.execute(
                "pmemsave",
                {"val": address, "size": len(expected),
                 "filename": str(emulator.frame_path)},
            )
            actual = emulator.frame_path.read_bytes()
            if actual != expected:
                raise AssertionError(
                    f"initializer copy at {address:06X}: "
                    f"{actual.hex()} != {expected.hex()}"
                )
        print("NP560+ vendor nine-copy initializer probe passed")
        print(state)
    finally:
        emulator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
