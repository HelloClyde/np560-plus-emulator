#!/usr/bin/env python3
"""Run the vendor's exact 51:6CB8 ECC corrector against injected faults."""

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import struct
import tempfile
import time
from pathlib import Path

from analyze_np560_ecc_checkpoint import sector_descriptor
from web.np560_web import Emulator


DATA_BASES = (0x0200, 0x0400, 0x0600)
DESCRIPTOR_BASE = 0x1000
RESULT_BASE = 0x1100
PHYSICAL_SEGMENT = 0x0050
DATA_SELECTOR = 0x00A0
CORRECTOR = 0x516CB8


def append_store_words(code: list[int], address: int, values: list[int]) -> None:
    code.extend([0x68F1, address])        # MOV R1, #address
    for value in values:
        code.extend([
            0x68F0, value & 0xFFFF,      # MOV R0, #value
            0x1A10,                      # MOV [R1++], R0
        ])


def append_corrector_call(
    code: list[int], data_address: int, descriptor_address: int, result: int,
) -> None:
    # The exact callers push descriptor(lo,hi), then data(lo,hi).  After LINK,
    # 51:6CB8 consequently observes data at [R11+6/+8] and descriptor at
    # [R11+A/+C].
    code.extend([
        0x68F0, PHYSICAL_SEGMENT,        # descriptor high
        0x68F1, descriptor_address,      # descriptor low
        0x68F2, PHYSICAL_SEGMENT,        # data high
        0x68F3, data_address,            # data low
        0x58F1, 0x58F0,                  # push descriptor low, high
        0x58F3, 0x58F2,                  # push data low, high
        0xBD00 | (CORRECTOR >> 16), CORRECTOR & 0xFFFF,
        0x50F8,                          # ADD SP, #8
        0x6810, DATA_SELECTOR,           # MOV DS0, #A0
        0xA8F0, result,                  # MOV [result], R0
    ])


def build_firmware(cases: list[list[int]], descriptor: bytes) -> tuple[bytes, int]:
    code: list[int] = [
        0x6810, DATA_SELECTOR,            # 50:0000..7fff data window
        0x6811, DATA_SELECTOR,
    ]
    descriptor_words = list(struct.unpack("<4H", descriptor))
    for index, values in enumerate(cases):
        append_store_words(code, DATA_BASES[index], values)
        append_store_words(
            code, DESCRIPTOR_BASE + index * 8, descriptor_words,
        )
        append_corrector_call(
            code, DATA_BASES[index], DESCRIPTOR_BASE + index * 8,
            RESULT_BASE + index * 2,
        )
    loop_pc = len(code) * 2
    code.extend([0xAC00, loop_pc])
    return struct.pack(f"<{len(code)}H", *code), loop_pc


def physical_memory(emulator: Emulator, address: int, size: int) -> bytes:
    emulator.qmp.execute("pmemsave", {
        "val": address, "size": size, "filename": str(emulator.frame_path),
    })
    return emulator.frame_path.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--burn-code", type=Path, required=True)
    args = parser.parse_args()

    original = [
        ((index * 0x9E37) ^ 0xA55A) & 0xFFFF for index in range(256)
    ]
    clean = original.copy()
    single = original.copy()
    single[0x7A] ^= 1 << 5
    double = original.copy()
    double[0] ^= 0x0003
    cases = [clean, single, double]
    descriptor = sector_descriptor(struct.pack("<256H", *original))
    firmware_bytes, loop_pc = build_firmware(cases, descriptor)

    with tempfile.TemporaryDirectory(prefix="np560-ecc-correct-") as work:
        firmware = Path(work) / "correct.prg"
        firmware.write_bytes(firmware_bytes)
        emulator = Emulator(
            qemu=args.qemu, firmware=firmware, burn_code=args.burn_code,
        )
        try:
            deadline = time.monotonic() + 8
            cpu_state = ""
            while time.monotonic() < deadline:
                cpu_state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "cpu-state"}
                )
                if f"PC=20:{loop_pc:04x}" in cpu_state:
                    break
                if emulator.process.poll() is not None:
                    raise AssertionError(
                        f"QEMU exited with {emulator.process.returncode}\n{cpu_state}"
                    )
                time.sleep(0.01)
            else:
                raise AssertionError(f"corrector harness timed out\n{cpu_state}")

            results = struct.unpack(
                "<3H", physical_memory(
                    emulator, (PHYSICAL_SEGMENT << 16) | RESULT_BASE, 6,
                )
            )
            if results != (0x0000, 0x0002, 0xFFF9):
                raise AssertionError(
                    f"vendor corrector returned {results!r}, expected "
                    "(0, 2, 0xfff9)"
                )
            expected_data = (original, original, double)
            for index, expected in enumerate(expected_data):
                actual = physical_memory(
                    emulator,
                    (PHYSICAL_SEGMENT << 16) | DATA_BASES[index], 512,
                )
                if actual != struct.pack("<256H", *expected):
                    raise AssertionError(
                        f"case {index} data differs after correction"
                    )
            ecc_state = emulator.qmp.execute(
                "qom-get", {"path": "/machine", "property": "ecc-state"}
            )
            for expected in ("RESETS=3", "FEEDS=768"):
                if expected not in ecc_state:
                    raise AssertionError(f"missing {expected} in {ecc_state}")
        finally:
            emulator.close()

    print("NP560+ vendor 51:6CB8 ECC correction regression passed")
    print("clean=0000 single-bit=0002/restored double-bit=fff9/rejected")
    print(ecc_state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
