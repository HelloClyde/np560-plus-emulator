#!/usr/bin/env python3
"""Prove data writes cannot corrupt PRG/NOR instruction fetches."""

from __future__ import annotations

import argparse
import re
import tempfile
import time
from pathlib import Path

from web.np560_web import Emulator


PROGRAM_SIZE = 0x400000
TARGET = 0x506000


def put_word(image: bytearray, physical: int, value: int) -> None:
    offset = physical - 0x200000
    image[offset:offset + 2] = value.to_bytes(2, "little")


def build_firmware() -> bytes:
    image = bytearray(PROGRAM_SIZE)
    words = (
        0x6810, 0x00A0,       # MOV DS0,#bank(50:6000)
        0x4800,               # MOV R0,#0
        0xA8F0, 0x6000,       # MOV [50:6000],R0 on the data bus
        0xAD50, 0x6000,       # SJMP 50:6000 on the code bus
    )
    for index, word in enumerate(words):
        put_word(image, 0x200000 + index * 2, word)
    put_word(image, TARGET, 0x68F0)      # MOV R0,#0xBEEF
    put_word(image, TARGET + 2, 0xBEEF)
    put_word(image, TARGET + 4, 0xD0FF)  # RJMP ALWAYS,self
    return bytes(image)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="np560-memory-split-") as directory:
        firmware = Path(directory) / "memory-split.prg"
        firmware.write_bytes(build_firmware())
        emulator = Emulator(qemu=args.qemu, firmware=firmware)
        try:
            deadline = time.monotonic() + 5
            while True:
                state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "cpu-state"}
                )
                if re.search(r"\bR0\s*=beef\b", state, re.IGNORECASE):
                    break
                if emulator.process.poll() is not None:
                    raise AssertionError(
                        f"QEMU exited with {emulator.process.returncode}:\n{state}"
                    )
                if time.monotonic() >= deadline:
                    raise AssertionError(
                        "data write corrupted or hid the NOR code target:\n" + state
                    )
                time.sleep(0.01)

            emulator.qmp.execute(
                "pmemsave",
                {"val": TARGET, "size": 4,
                 "filename": str(emulator.frame_path)},
            )
            data_bytes = emulator.frame_path.read_bytes()
            if data_bytes != b"\x00" * 4:
                raise AssertionError(
                    f"data side unexpectedly exposes NOR at 50:6000: {data_bytes.hex()}"
                )
            print("NP560+ NOR/code and external-data RAM split test passed")
            print(state)
        finally:
            emulator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
