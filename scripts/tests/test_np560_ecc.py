#!/usr/bin/env python3
"""Verify NP560 F20A/F20C/F20E paired-parity ECC in the guest data path."""

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


SECTOR_WORDS = 256
ECC_RESET = 0xF20A
ECC_PARITY = 0xF20A
ECC_NPARITY = 0xF20C
ECC_FEED = 0xF20E
RESULT_ADDRESS = 0x500100


def digest(words: list[int]) -> tuple[int, int]:
    """Reference the position/complement parity proved by 51:6CB8."""
    parity = 0
    nparity = 0
    for word_index, value in enumerate(words):
        for bit in range(16):
            if value & (1 << bit):
                position = ((word_index & 0xFFF) << 4) | bit
                parity ^= position
                nparity ^= (~position) & 0xFFFF
    return parity, nparity


def descriptor(words: list[int]) -> tuple[int, int, int, int]:
    parity, nparity = digest(words)
    return nparity, parity, nparity ^ parity, 0x6979


def require_exhaustive_single_bit_location() -> None:
    """Exercise the exact correction equations over all 4096 data bits."""
    erased = [0] * SECTOR_WORDS
    stored = descriptor(erased)
    for position in range(SECTOR_WORDS * 16):
        changed = erased.copy()
        changed[position >> 4] ^= 1 << (position & 0xF)
        current = descriptor(changed)
        syndrome_nparity = current[0] ^ stored[0]
        syndrome_parity = current[1] ^ stored[1]
        if not ((syndrome_nparity ^ syndrome_parity) & 1):
            raise AssertionError(f"bit {position:#x} was not recoverable")
        decoded = ((((syndrome_parity >> 4) & 0xFF) << 4) |
                   (syndrome_parity & 0xF))
        if decoded != position:
            raise AssertionError(
                f"bit {position:#x} decoded as {decoded:#x}"
            )


def build_firmware(cases: list[list[int]]) -> tuple[bytes, int]:
    words: list[int] = []
    for case_index, values in enumerate(cases):
        words.extend([
            0x6811, 0x0001,      # MOV DS1, #1, as in exact helper 51:C1B2
            0x4800,              # MOV R0, #0
            0x3F10,              # IGNDS #0
            0xA8F0, ECC_RESET,   # MOV [F20A], R0
            0x68F3, ECC_FEED,    # MOV R3, #F20E
        ])
        for value in values:
            words.extend([
                0x68F0, value,   # MOV R0, #value
                0x0A30,          # MOV [R3], R0 through DS1=1, as at 51:C1E8
            ])
        result_offset = 0x0100 + case_index * 4
        words.extend([
            0x3F11,              # exact unbanked read sequence
            0x88F2, ECC_PARITY,  # MOV R2, [F20A]
            0x88F3, ECC_NPARITY, # MOV R3, [F20C]
            0x6810, 0x00A0,      # selector A0 maps logical 0100 -> 50:0100
            0x6811, 0x00A0,
            0xA8F2, result_offset,
            0xA8F3, result_offset + 2,
        ])
    loop_pc = len(words) * 2
    words.extend([0xAC00, loop_pc])
    return struct.pack(f"<{len(words)}H", *words), loop_pc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    args = parser.parse_args()

    cases = [
        [0x0000] * SECTOR_WORDS,
        [0xFFFF] * SECTOR_WORDS,
        [0x0001] + [0x0000] * (SECTOR_WORDS - 1),
        [0x0000] * 0x7A + [0x0020] + [0x0000] * (SECTOR_WORDS - 0x7B),
        [0x0000] * (SECTOR_WORDS - 1) + [0x8000],
        [((index * 0x9E37) ^ 0xA55A) & 0xFFFF
         for index in range(SECTOR_WORDS)],
    ]
    firmware_bytes, loop_pc = build_firmware(cases)
    require_exhaustive_single_bit_location()

    with tempfile.TemporaryDirectory(prefix="np560-ecc-") as work:
        firmware = Path(work) / "ecc.prg"
        firmware.write_bytes(firmware_bytes)
        emulator = Emulator(qemu=args.qemu, firmware=firmware)
        try:
            deadline = time.monotonic() + 4
            cpu_state = ""
            ecc_state = ""
            while time.monotonic() < deadline:
                cpu_state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "cpu-state"}
                )
                ecc_state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "ecc-state"}
                )
                if (f"PC=20:{loop_pc:04x}" in cpu_state and
                        f"RESETS={len(cases)}" in ecc_state and
                        f"FEEDS={len(cases) * SECTOR_WORDS}" in ecc_state):
                    break
                time.sleep(0.01)
            else:
                raise AssertionError(
                    f"guest ECC harness timed out\n{cpu_state}\n{ecc_state}"
                )

            emulator.qmp.execute("pmemsave", {
                "val": RESULT_ADDRESS,
                "size": len(cases) * 4,
                "filename": str(emulator.frame_path),
            })
            actual = struct.unpack(
                f"<{len(cases) * 2}H", emulator.frame_path.read_bytes()
            )
            expected: list[int] = []
            for values in cases:
                parity, nparity = digest(values)
                expected.extend((parity, nparity))
            if tuple(expected) != actual:
                raise AssertionError(
                    f"guest ECC results {actual!r} != reference {tuple(expected)!r}"
                    f"\n{cpu_state}\n{ecc_state}"
                )

            final_parity, final_nparity = digest(cases[-1])
            required = (
                f"F20A={final_parity:04x}",
                f"F20C={final_nparity:04x}",
                "WORD_INDEX=256",
            )
            for item in required:
                if item not in ecc_state:
                    raise AssertionError(f"missing {item!r} in {ecc_state}")
        finally:
            emulator.close()

    print("NP560+ F20 paired-parity ECC regression passed")
    print("4096/4096 single-bit syndromes decode to the exact word and bit")
    print(ecc_state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
