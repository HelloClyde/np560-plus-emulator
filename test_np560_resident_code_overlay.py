#!/usr/bin/env python3
"""Verify the evidenced 05:2286 resident overlay is writable executable RAM."""

from __future__ import annotations

import argparse
import re
import struct
import tempfile
import time
from pathlib import Path

from web.np560_web import Emulator


TARGET = 0x052286


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    args = parser.parse_args()

    # Install `MOV R0,#BEEF; RJMP self` through the ordinary data bus, then
    # enter the resident target through the independent instruction bus.
    words = (
        0x6810, TARGET >> 15,
        0x68F0, 0x68F0, 0xA8F0, TARGET & 0x7FFF,
        0x68F0, 0xBEEF, 0xA8F0, (TARGET + 2) & 0x7FFF,
        0x68F0, 0xD0FF, 0xA8F0, (TARGET + 4) & 0x7FFF,
        0xAD05, TARGET & 0xFFFF,
    )

    with tempfile.TemporaryDirectory(prefix="np560-resident-overlay-") as work:
        firmware = Path(work) / "resident-overlay.prg"
        firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
        # A mapped resident image avoids the strict missing-ROM trap.  Its
        # zero word at TARGET also proves success cannot come from the ROM
        # underneath the writable code alias.
        soc_rom = Path(work) / "resident.bin"
        soc_rom.write_bytes(bytes(TARGET + 6))
        emulator = Emulator(qemu=args.qemu, firmware=firmware, soc_rom=soc_rom)
        try:
            deadline = time.monotonic() + 3
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "cpu-state"}
                )
                if (re.search(r"^PC=05:228a\b", state) and
                        re.search(r"\bR0\s*=beef\b", state, re.IGNORECASE)):
                    print("NP560+ resident executable-overlay regression passed")
                    print(state.splitlines()[0])
                    return 0
                if emulator.process.poll() is not None:
                    break
                time.sleep(0.01)
            raise AssertionError(
                "05:2286 data writes were not executed by the code bus:\n" + state
            )
        finally:
            emulator.close()


if __name__ == "__main__":
    raise SystemExit(main())
