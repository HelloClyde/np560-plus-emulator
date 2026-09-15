#!/usr/bin/env python3
"""Extend the guest ROM-01 installer with the exact foreground object body.

The exact event callback recovered at 24:162C calls 2D:9DFC.  Flat PRG bytes
at that destination are an unframed middle entry in another function; that
wrong path eventually reaches 2D:B394 and feeds 0xFFF8 into a seven-entry
render jump table.  The updater's linked image at 4A:9DFC is the complete
ABI-compatible LINK #4 function and returns after 0x1AC bytes.

This patch replaces the previous installer RETS with one ordinary DMCU copy
loop followed by RETS.  QEMU only supplies writable/executable overlay RAM;
no host callback, clamping, or ROM service is introduced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from scripts.patch_np560_rom01_modal_callback_closure import (
        RESERVED_WORD,
        RETS,
        copy_code_words,
        words_to_bytes,
    )
except ModuleNotFoundError:
    from patch_np560_rom01_modal_callback_closure import (
        RESERVED_WORD,
        RETS,
        copy_code_words,
        words_to_bytes,
    )


PROGRAM_BASE = 0x200000
# Current reconstructed ROMs keep the cursor-refresh installer's RETS at
# 06:450C, with enough reserved words before the 06:4600 wrapper.  Older ROMs
# used the end of the standalone 06:3900 modal installer.  Accept both exact
# layouts, but never scan for or overwrite an arbitrary RETS.
EXTENSION_ADDRESS = 0x06450C
LEGACY_EXTENSION_ADDRESS = 0x063E52
EXTENSION_ADDRESSES = (EXTENSION_ADDRESS, LEGACY_EXTENSION_ADDRESS)
DESTINATION = 0x2D9DFC
SOURCE = 0x4A9DFC
SIZE = 0x01AC
PROLOGUE = b"\x04\x2e"
EPILOGUE = b"\x00\x2f\x20\xc6"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def program_bytes(program: bytes, address: int, size: int) -> bytes:
    offset = address - PROGRAM_BASE
    if offset < 0 or offset + size > len(program):
        raise ValueError(f"program range 0x{address:06X}+0x{size:X} is absent")
    return program[offset:offset + size]


def extension_bytes() -> bytes:
    return words_to_bytes(tuple(
        copy_code_words(DESTINATION, SOURCE, SIZE) + [RETS]
    ))


def patch_image(baseline: bytes, program: bytes) -> tuple[bytes, dict[str, object]]:
    exact = program_bytes(program, SOURCE, SIZE)
    if exact[:2] != PROLOGUE:
        raise ValueError("4A:9DFC no longer starts with LINK #4")
    if exact[-4:] != EPILOGUE:
        raise ValueError("4A:9DFC no longer ends with UNLINK/RETS at 4A:9FA6")

    extension = extension_bytes()
    expected = words_to_bytes((RETS,)) + RESERVED_WORD * (
        len(extension) // 2 - 1
    )
    extension_address = next((
        address for address in EXTENSION_ADDRESSES
        if address + len(extension) <= len(baseline)
        and baseline[address:address + len(extension)] == expected
    ), None)
    if extension_address is None:
        raise ValueError(
            "neither 06:450C nor legacy 06:3E52 is an exact "
            "RETS/reserved installer tail"
        )
    end = extension_address + len(extension)

    patched = bytearray(baseline)
    patched[extension_address:end] = extension
    metadata: dict[str, object] = {
        "installer_extension": (
            f"{extension_address >> 16:02X}:{extension_address & 0xFFFF:04X}"
        ),
        "installer_extension_bytes": len(extension),
        "destination": "2D:9DFC..2D:9FA7 executable overlay RAM",
        "exact_source": "4A:9DFC..4A:9FA7",
        "exact_bytes": SIZE,
        "relocation": "same PC; local AJMP operands unchanged",
        "failure_removed": "2D:B394 -> 2B:6CE6 -> 27:1A8E data execution",
        "execution_model": "ordinary guest DMCU copy loop; no host HLE",
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
    print(f"installed modal foreground object; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-rom01-modal-foreground-object-v1",
            "baseline": str(args.baseline),
            "baseline_sha256": sha256(baseline),
            "program": str(args.program),
            "program_sha256": sha256(program),
            "output": str(args.output),
            "output_sha256": sha256(output),
            "patch": patch,
        }
        args.manifest.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
