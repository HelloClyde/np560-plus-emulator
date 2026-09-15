#!/usr/bin/env python3
"""Verify DMCU far-call frames bypass an overlapping board MMIO window."""

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

    # 20:0000  MOV REG[FF], #F342   ; R15/SP
    # 20:0004  SCALL 20:0010        ; return PC is stored at SRAM F340
    # 20:0008  MOV R0, #7           ; durable success marker
    # 20:000A  AJMP 20:000A
    # 20:0010  RETS
    #
    # Board data-bus MMIO also occupies numeric address F340.  If SCALL is
    # incorrectly dispatched through that window, its saved 0008 is dropped
    # and RETS goes back to 20:0000 instead of reaching the marker loop.
    words = (
        0x68FF, 0xF342,
        0xBD20, 0x0010,
        0x4807,
        0xAC00, 0x000A,
        0xC700,
        0xC620,
    )

    with tempfile.TemporaryDirectory(prefix="np560-stack-mmio-") as work:
        firmware = Path(work) / "stack-mmio.prg"
        firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
        emulator = Emulator(qemu=args.qemu, firmware=firmware)
        try:
            deadline = time.monotonic() + 3
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "cpu-state"}
                )
                if (re.search(r"^PC=20:000a\b", state) and
                        re.search(r"\bR0\s*=0007\b", state) and
                        re.search(r"\bR15=f342\b", state)):
                    print("NP560+ internal stack/MMIO alias regression passed")
                    print(state.splitlines()[0])
                    return 0
                time.sleep(0.01)
            raise AssertionError(
                "far return did not preserve the PC across SRAM F340:\n" + state
            )
        finally:
            emulator.close()


if __name__ == "__main__":
    raise SystemExit(main())
