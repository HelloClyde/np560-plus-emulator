#!/usr/bin/env python3
"""Execute reconstructed resident 02:DEA6 against FIPS DES vectors."""

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import re
import tempfile
import time
from pathlib import Path

from web.np560_web import Emulator


PROGRAM_BASE = 0x200000
PROGRAM_SIZE = 0x400000
DATA_PHYSICAL = 0x510000
PLAINTEXT = bytes.fromhex("0123456789ABCDEF")
KEY = bytes.fromhex("133457799BBCDFF1")
CIPHERTEXT = bytes.fromhex("85E813540F0AB405")
DONE_MARKER = 0xD35D


def put_word(image: bytearray, address: int, value: int) -> None:
    offset = address - PROGRAM_BASE
    image[offset:offset + 2] = value.to_bytes(2, "little")


def external_words(data: bytes) -> list[int]:
    """Pack logical bytes for the DMCU external bus's inverted A0 lane."""
    if len(data) & 1:
        raise ValueError("external test data must contain whole words")
    return [
        (data[offset] << 8) | data[offset + 1]
        for offset in range(0, len(data), 2)
    ]


def build_firmware() -> bytes:
    image = bytearray(PROGRAM_SIZE)
    words: list[int] = [
        0x68FF, 0xFFF8,               # MOV R15,#FFF8
        0xBD06, 0xC000,               # initialize DES tables in guest RAM
        0x6810, DATA_PHYSICAL >> 15,  # DS0 -> 51:0000
    ]
    logical = DATA_PHYSICAL & 0x7FFF
    fixtures = PLAINTEXT + CIPHERTEXT + KEY
    for index, value in enumerate(external_words(fixtures)):
        words.extend((0x68F0, value, 0xA8F0, logical + index * 2))

    def emit_call(data_low: int, mode: int) -> None:
        # Push the six observed caller words in source order.  SCALL then
        # creates its own four-byte far-return frame below them.
        words.extend((
            0x68F0, mode, 0x58F0,
            0x68F0, 1, 0x58F0,
            0x68F0, 0x0010, 0x58F0,   # key low
            0x68F0, 0x0051, 0x58F0,   # key high
            0x68F0, data_low, 0x58F0,
            0x68F0, 0x0051, 0x58F0,
            0xBD02, 0xDEA6,
            0x50FC,                   # caller removes 12 argument bytes
        ))

    emit_call(0x0000, 1)              # encrypt known plaintext
    emit_call(0x0008, 0)              # decrypt known ciphertext
    words.extend((
        0x68F0, DONE_MARKER,
        0xD0FF,                       # stable completion self-loop
    ))
    for index, word in enumerate(words):
        put_word(image, PROGRAM_BASE + index * 2, word)
    return bytes(image)


def cpu_state(emulator: Emulator) -> str:
    return emulator.qmp.execute(
        "qom-get", {"path": "/machine", "property": "cpu-state"}
    )


def physical_memory(emulator: Emulator, address: int, size: int) -> bytes:
    with tempfile.NamedTemporaryFile(prefix="np560-des-pmem-", delete=False) as out:
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
        logical[offset], logical[offset + 1] = (
            logical[offset + 1], logical[offset]
        )
    return bytes(logical)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--soc-rom", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="np560-des-") as directory:
        firmware = Path(directory) / "des-vector.prg"
        firmware.write_bytes(build_firmware())
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
                if re.search(rf"\bR0\s*={DONE_MARKER:04x}\b", last,
                             re.IGNORECASE):
                    break
                if emulator.process.poll() is not None:
                    raise AssertionError(
                        f"QEMU exited with {emulator.process.returncode}:\n{last}"
                    )
                time.sleep(0.01)
            else:
                raise AssertionError(
                    "guest DES vector did not reach completion:\n" + last
                )

            actual = external_logical_bytes(
                physical_memory(emulator, DATA_PHYSICAL, 16)
            )
            expected = CIPHERTEXT + PLAINTEXT
            if actual != expected:
                raise AssertionError(
                    "resident DES known-answer mismatch: "
                    f"expected={expected.hex()} actual={actual.hex()}\n{last}"
                )
            for clean in (
                "ROM_HLE=off", "ROM_MISSING=none", "INVALID_CONTROL=none",
                "UNSUPPORTED=none",
            ):
                if clean not in last:
                    raise AssertionError(f"missing {clean!r}:\n{last}")
            print("NP560+ guest DES encryption/decryption vectors passed")
            print(f"encrypt={actual[:8].hex()} decrypt={actual[8:].hex()}")
        finally:
            emulator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
