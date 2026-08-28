#!/usr/bin/env python3
"""Run the exact NP560 path-component parser in a tiny QEMU harness."""

from __future__ import annotations

import argparse
import re
import struct
import tempfile
import time
from pathlib import Path

from web.np560_web import Emulator


PROGRAM_BASE = 0x200000


def copy_range(image: bytearray, source: bytes, destination: int,
               source_address: int, size: int) -> None:
    destination_offset = destination - PROGRAM_BASE
    source_offset = source_address - PROGRAM_BASE
    image[destination_offset:destination_offset + size] = \
        source[source_offset:source_offset + size]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--vendor-program", type=Path, required=True)
    args = parser.parse_args()

    vendor = args.vendor_program.read_bytes()
    image = bytearray(0x140000)

    # The runtime image relocates these exact PRG bodies by -0x1D segments.
    # Include every direct dependency and the sixteen-byte punctuation table,
    # making the result independent of the reconstructed boot sequence.
    for destination, source_address, size in (
        (0x28D7E2, 0x45D7E2, 738),
        (0x30FE0E, 0x4DFE0E, 210),
        (0x31D288, 0x4ED288, 154),
        (0x334588, 0x504588, 26),
        (0x333B86, 0x503B86, 16),
    ):
        copy_range(image, vendor, destination, source_address, size)

    words: list[int] = []

    def emit(*values: int) -> None:
        words.extend(values)

    # Store the CPU-visible byte string "lirt.nwf\0" in internal SRAM.
    for address, value in (
        (0x0E00, 0x6C69),
        (0x0E02, 0x7274),
        (0x0E04, 0x2E6E),
        (0x0E06, 0x7766),
        (0x0E08, 0x0000),
    ):
        emit(0x68F2, value, 0x68F3, address, 0x0A32)

    # parser(output=0000:0E40, input=0000:0E00)
    emit(
        0x68F0, 0x0000, 0x68F1, 0x0E00, 0x58F1, 0x58F0,
        0x68F0, 0x0000, 0x68F1, 0x0E40, 0x58F1, 0x58F0,
        0xBD28, 0xD7E2,
        0x50F8,
    )
    loop_pc = len(words) * 2
    emit(0xAC00, loop_pc)
    image[:len(words) * 2] = struct.pack(f"<{len(words)}H", *words)

    with tempfile.TemporaryDirectory(prefix="np560-path-component-") as work:
        firmware = Path(work) / "path-component.prg"
        firmware.write_bytes(image)
        emulator = Emulator(qemu=args.qemu, firmware=firmware)
        try:
            deadline = time.monotonic() + 5
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "cpu-state"}
                )
                expected = (
                    re.search(rf"^PC=20:{loop_pc:04x}\b", state) and
                    re.search(r"\bR0\s*=0000\b", state) and
                    re.search(r"\bR1\s*=0e08\b", state, re.IGNORECASE)
                )
                if expected:
                    print("NP560+ exact path-component parser test passed")
                    print(state.splitlines()[0])
                    return 0
                if emulator.process.poll() is not None:
                    break
                time.sleep(0.01)
            raise AssertionError(
                "path parser did not return the terminal NUL pointer "
                "0000:0E08:\n" + state
            )
        finally:
            emulator.close()


if __name__ == "__main__":
    raise SystemExit(main())
