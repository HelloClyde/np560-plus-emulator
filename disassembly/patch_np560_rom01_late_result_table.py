#!/usr/bin/env python3
"""Reinstall two exact vendor result-table wrappers at the ROM01 boundary.

The shipped ROM01 continuation first installs resident/menu overlays, then
loads the foreground application into the same writable program window.  In
the recovered image that ordering leaves 33:51E0 and 33:51F2 containing stale
foreground instructions when 2B:4F5A later calls them.

This patch adds only guest DMCU instructions.  A small wrapper in an evidenced
reserved ROM06 gap calls the original 06:3000 dependency installer and then
writes the two exact 18-byte routines from NP560.PRG into their linked runtime
destinations.  QEMU does not intercept or service either call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence


PROGRAM_BASE = 0x200000
ROM01_CALL_ADDRESS = 0x011598
ORIGINAL_INSTALLER_ADDRESS = 0x063000
LATE_INSTALLER_ADDRESS = 0x063830
RESERVED_WORD = b"\x00\x0f"
RETS = 0xC620

ALLOC_DESTINATION = 0x3351E0
ALLOC_SOURCE = 0x5051E0
POINTER_DESTINATION = 0x3351F2
POINTER_SOURCE = 0x5051F2
WRAPPER_SIZE = 0x12

EXPECTED_CALL_WORDS = (0xBD06, 0x3000)
EXPECTED_ALLOC_BYTES = bytes.fromhex(
    "00 2E 0B 78 06 00 F0 58 25 BD DA 77 F2 50 00 2F 20 C6"
)
EXPECTED_POINTER_BYTES = bytes.fromhex(
    "00 2E 0B 78 06 00 F0 58 31 BD 00 53 F2 50 00 2F 20 C6"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words_to_bytes(words: Sequence[int]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def program_bytes(program: bytes, address: int, size: int) -> bytes:
    offset = address - PROGRAM_BASE
    if offset < 0 or offset + size > len(program):
        raise ValueError(f"PRG source 0x{address:06x}+0x{size:x} is outside image")
    return program[offset:offset + size]


def embedded_writes(destination: int, payload: bytes) -> list[int]:
    """Encode exact words as ordinary DMCU DS0/MOV immediate stores."""
    if destination & 1 or len(payload) & 1 or not payload:
        raise ValueError("embedded program writes require positive whole words")
    logical = destination & 0x7FFF
    if logical + len(payload) > 0x8000:
        raise ValueError("embedded program write crosses a 32-KiB bank")
    words = [0x6810, destination >> 15]
    for index in range(0, len(payload), 2):
        value = int.from_bytes(payload[index:index + 2], "little")
        words.extend((0x68F0, value, 0xA8F0, logical + index))
    return words


def late_installer_words(alloc: bytes, pointer: bytes) -> list[int]:
    """Call the original closure installer, then restore the overwritten leaves."""
    words = [
        0xBD00 | (ORIGINAL_INSTALLER_ADDRESS >> 16),
        ORIGINAL_INSTALLER_ADDRESS & 0xFFFF,
    ]
    words.extend(embedded_writes(ALLOC_DESTINATION, alloc))
    # Both destinations share DS0 page 0x66.  Remove the duplicate selector so
    # the final register state remains identical to the original 06:3000 path.
    pointer_words = embedded_writes(POINTER_DESTINATION, pointer)
    if pointer_words[:2] != [0x6810, ALLOC_DESTINATION >> 15]:
        raise ValueError("result-table wrappers unexpectedly span DS0 pages")
    words.extend(pointer_words[2:])
    words.append(RETS)
    return words


def patch_image(baseline: bytes, program: bytes) -> tuple[bytes, dict[str, object]]:
    alloc = program_bytes(program, ALLOC_SOURCE, WRAPPER_SIZE)
    pointer = program_bytes(program, POINTER_SOURCE, WRAPPER_SIZE)
    if alloc != EXPECTED_ALLOC_BYTES:
        raise ValueError("50:51E0 exact allocation-wrapper signature changed")
    if pointer != EXPECTED_POINTER_BYTES:
        raise ValueError("50:51F2 exact pointer-wrapper signature changed")

    expected_call = words_to_bytes(EXPECTED_CALL_WORDS)
    if baseline[ROM01_CALL_ADDRESS:ROM01_CALL_ADDRESS + 4] != expected_call:
        raise ValueError("01:1598 no longer calls the original 06:3000 installer")

    installer = words_to_bytes(late_installer_words(alloc, pointer))
    end = LATE_INSTALLER_ADDRESS + len(installer)
    if end > len(baseline):
        raise ValueError("late installer falls outside the resident ROM image")
    old_gap = baseline[LATE_INSTALLER_ADDRESS:end]
    if old_gap != RESERVED_WORD * (len(installer) // 2):
        raise ValueError("06:3830 late-installer range is no longer reserved")

    patched = bytearray(baseline)
    patched[ROM01_CALL_ADDRESS:ROM01_CALL_ADDRESS + 4] = words_to_bytes((
        0xBD00 | (LATE_INSTALLER_ADDRESS >> 16),
        LATE_INSTALLER_ADDRESS & 0xFFFF,
    ))
    patched[LATE_INSTALLER_ADDRESS:end] = installer
    metadata: dict[str, object] = {
        "rom01_call": "01:1598 -> 06:3830",
        "late_installer": "06:3830",
        "late_installer_bytes": len(installer),
        "original_dependency_installer": "06:3000",
        "guest_writes": [
            {"destination": "33:51E0", "source": "50:51E0", "bytes": 18},
            {"destination": "33:51F2", "source": "50:51F2", "bytes": 18},
        ],
    }
    return bytes(patched), metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    baseline = args.baseline.read_bytes()
    program = args.program.read_bytes()
    output, patch = patch_image(baseline, program)
    args.output.write_bytes(output)
    print(
        f"installed {patch['late_installer_bytes']} bytes of guest DMCU code at "
        f"0x{LATE_INSTALLER_ADDRESS:06x}; sha256={sha256(output)}"
    )

    if args.manifest:
        record = {
            "format": "np560-rom01-late-result-table-patch-v1",
            "baseline": str(args.baseline),
            "baseline_sha256": sha256(baseline),
            "program": str(args.program),
            "program_sha256": sha256(program),
            "output": str(args.output),
            "output_sha256": sha256(output),
            "patch": patch,
            "execution_model": "ordinary guest DMCU instructions; no host HLE",
        }
        args.manifest.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
