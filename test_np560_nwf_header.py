#!/usr/bin/env python3
"""Validate an experimental NWF header with the exact resident guest DES.

The harness loads the on-disk 0x200-byte header into external RAM, invokes
resident 02:DEA6 in the same E(K1),D(K2),E(K1) sequence and block count used
by resource-open 1D:668A, then compares RAM with the offline decoded header.
No filesystem or host-side ROM service participates in this check.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from disassembly import build_np560_minimal_nwf as nwf  # noqa: E402
from web.np560_web import Emulator  # noqa: E402


PROGRAM_BASE = 0x200000
PROGRAM_SIZE = 0x400000
DATA_PHYSICAL = 0x510000
DONE_MARKER = 0x4E57


def put_word(image: bytearray, address: int, value: int) -> None:
    offset = address - PROGRAM_BASE
    image[offset:offset + 2] = value.to_bytes(2, "little")


def external_words(data: bytes) -> list[int]:
    if len(data) & 1:
        raise ValueError("external fixture must contain whole words")
    return [
        (data[offset] << 8) | data[offset + 1]
        for offset in range(0, len(data), 2)
    ]


def build_firmware(raw_header: bytes) -> bytes:
    if len(raw_header) != nwf.HEADER_SIZE:
        raise ValueError("NWF harness requires exactly one 0x200-byte header")
    image = bytearray(PROGRAM_SIZE)
    words: list[int] = [
        0x68FF, 0xFFF8,               # MOV R15,#FFF8
        0xBD06, 0xC000,               # initialize resident DES tables
        0x6810, DATA_PHYSICAL >> 15,  # DS0 -> 51:0000
    ]
    logical = DATA_PHYSICAL & 0x7FFF
    for index, value in enumerate(external_words(raw_header)):
        words.extend((0x68F0, value, 0xA8F0, logical + index * 2))

    def emit_call(key_low: int, mode: int) -> None:
        words.extend((
            0x68F0, mode, 0x58F0,
            0x68F0, nwf.PROTECTED_BLOCKS, 0x58F0,
            0x68F0, key_low, 0x58F0,
            0x68F0, 0x0051, 0x58F0,
            0x68F0, nwf.PROTECTED_OFFSET, 0x58F0,
            0x68F0, 0x0051, 0x58F0,
            0xBD02, 0xDEA6,
            0x50FC,
        ))

    emit_call(0x0000, 1)
    emit_call(0x0008, 0)
    emit_call(0x0000, 1)
    words.extend((0x68F0, DONE_MARKER, 0xD0FF))
    for index, word in enumerate(words):
        put_word(image, PROGRAM_BASE + index * 2, word)
    return bytes(image)


def cpu_state(emulator: Emulator) -> str:
    return emulator.qmp.execute(
        "qom-get", {"path": "/machine", "property": "cpu-state"}
    )


def physical_memory(emulator: Emulator, address: int, size: int) -> bytes:
    with tempfile.NamedTemporaryFile(prefix="np560-nwf-pmem-", delete=False) as out:
        path = Path(out.name)
    try:
        emulator.qmp.execute("pmemsave", {
            "val": address, "size": size, "filename": str(path),
        })
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def external_logical_bytes(stored: bytes) -> bytes:
    logical = bytearray(stored)
    for offset in range(0, len(logical), 2):
        logical[offset], logical[offset + 1] = logical[offset + 1], logical[offset]
    return bytes(logical)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--soc-rom", type=Path, required=True)
    parser.add_argument("--nwf", type=Path, required=True)
    args = parser.parse_args()

    candidate = args.nwf.read_bytes()
    report = nwf.inspect_candidate(candidate)
    if not report["valid_offline_candidate"]:
        raise AssertionError(f"offline NWF validation failed: {report['errors']}")
    raw_header = candidate[:nwf.HEADER_SIZE]
    expected = nwf.decode_header(raw_header)

    with tempfile.TemporaryDirectory(prefix="np560-nwf-header-") as directory:
        firmware = Path(directory) / "nwf-header.prg"
        firmware.write_bytes(build_firmware(raw_header))
        emulator = Emulator(
            qemu=args.qemu,
            firmware=firmware,
            soc_rom=args.soc_rom,
            soc_rom_skeleton=True,
            icount_shift=0,
        )
        try:
            deadline = time.monotonic() + 20
            last = ""
            while time.monotonic() < deadline:
                last = cpu_state(emulator)
                if re.search(rf"\bR0\s*={DONE_MARKER:04x}\b", last, re.IGNORECASE):
                    break
                if emulator.process.poll() is not None:
                    raise AssertionError(
                        f"QEMU exited with {emulator.process.returncode}:\n{last}"
                    )
                time.sleep(0.01)
            else:
                raise AssertionError("guest NWF DES did not complete:\n" + last)

            actual = external_logical_bytes(
                physical_memory(emulator, DATA_PHYSICAL, nwf.HEADER_SIZE)
            )
            if actual != expected:
                first = next(
                    (index for index, pair in enumerate(zip(actual, expected))
                     if pair[0] != pair[1]),
                    None,
                )
                raise AssertionError(
                    f"guest/offline NWF header mismatch at {first!r}: "
                    f"actual={actual[first:first + 16].hex()} "
                    f"expected={expected[first:first + 16].hex()}\n{last}"
                )
            for clean in (
                "ROM_HLE=off", "ROM_MISSING=none", "INVALID_CONTROL=none",
                "UNSUPPORTED=none",
            ):
                if clean not in last:
                    raise AssertionError(f"missing {clean!r}:\n{last}")
            print("NP560+ exact guest NWF header transformation passed")
            print(
                f"sha256={report['sha256']} version={report['version']} "
                f"record={report['record_position_hex']} "
                f"application={report['application_code_hex']}"
            )
        finally:
            emulator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
