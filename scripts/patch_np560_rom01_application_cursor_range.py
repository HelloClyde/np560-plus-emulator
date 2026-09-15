#!/usr/bin/env python3
"""Extend ROM-01 with the exact linked cursor-range function.

The foreground path at 1F:F4E0 directly calls 2E:A8B6.  Flat PRG bytes at
that destination start in the middle of a computed-dispatch routine, so the
old path returns through an odd table address and executes data.  The
updater's same-PC linked image at 4B:A8B6 is a complete LINK #2 function of
0x170 bytes, ending with UNLINK/RETS at 4B:AA22/AA24.

This patch replaces the preceding supplemental-installer RETS with one
ordinary guest DMCU copy loop followed by RETS.  QEMU supplies only the
writable/executable destination overlay; it does not implement the call.
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
PREVIOUS_EXTENSION_ADDRESS = 0x063E52
PREVIOUS_EXTENSION_SIZE = 44
EXTENSION_ADDRESS = PREVIOUS_EXTENSION_ADDRESS + PREVIOUS_EXTENSION_SIZE - 2
DESTINATION = 0x2EA8B6
SOURCE = 0x4BA8B6
SIZE = 0x0170
PROLOGUE = b"\x02\x2e"
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
        raise ValueError("4B:A8B6 no longer starts with LINK #2")
    if exact[-4:] != EPILOGUE:
        raise ValueError("4B:A8B6 no longer ends with UNLINK/RETS at 4B:AA24")

    extension = extension_bytes()
    end = EXTENSION_ADDRESS + len(extension)
    if end > len(baseline):
        raise ValueError("cursor-range installer falls outside resident ROM")
    expected = words_to_bytes((RETS,)) + RESERVED_WORD * (
        len(extension) // 2 - 1
    )
    if baseline[EXTENSION_ADDRESS:end] != expected:
        raise ValueError(
            "06:3E7C cursor-range installer range is not RETS/reserved ROM"
        )

    patched = bytearray(baseline)
    patched[EXTENSION_ADDRESS:end] = extension
    metadata: dict[str, object] = {
        "installer_extension": "06:3E7C",
        "installer_extension_bytes": len(extension),
        "destination": "2E:A8B6..2E:AA25 executable overlay RAM",
        "exact_source": "4B:A8B6..4B:AA25",
        "exact_bytes": SIZE,
        "relocation": "same PC; local AJMP operands unchanged",
        "failure_removed": "2E:A8B6 mid-function dispatch -> odd 2E:4C11 path",
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
    print(f"installed application cursor range; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-rom01-application-cursor-range-v1",
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
