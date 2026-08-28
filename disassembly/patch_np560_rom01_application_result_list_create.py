#!/usr/bin/env python3
"""Extend ROM-01 with the exact application result-list creator.

The post-modal scanner at 28:94C2 calls 31:9E18 with an eight-entry limit.
Flat PRG bytes at that destination are a large-function suffix, while the
same-linked source at 4E:9E18 is the complete LINK #3 list creator through
its balanced RETS at 4E:9EBE.  Without the guest copy the suffix returns zero
before the scanner can resolve a handle or construct the root menu.

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
    from disassembly.patch_np560_rom01_modal_callback_closure import (
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
PREVIOUS_EXTENSION_ADDRESS = 0x063E7C
PREVIOUS_EXTENSION_SIZE = 44
EXTENSION_ADDRESS = PREVIOUS_EXTENSION_ADDRESS + PREVIOUS_EXTENSION_SIZE - 2
DESTINATION = 0x319E18
SOURCE = 0x4E9E18
SIZE = 0x00A8
PROLOGUE = b"\x03\x2e"
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
        raise ValueError("4E:9E18 no longer starts with LINK #3")
    if exact[-4:] != EPILOGUE:
        raise ValueError("4E:9E18 no longer ends with UNLINK/RETS at 4E:9EBE")

    extension = extension_bytes()
    end = EXTENSION_ADDRESS + len(extension)
    if end > len(baseline):
        raise ValueError("result-list installer falls outside resident ROM")
    expected = words_to_bytes((RETS,)) + RESERVED_WORD * (
        len(extension) // 2 - 1
    )
    if baseline[EXTENSION_ADDRESS:end] != expected:
        raise ValueError(
            "06:3EA6 result-list installer range is not RETS/reserved ROM"
        )

    patched = bytearray(baseline)
    patched[EXTENSION_ADDRESS:end] = extension
    metadata: dict[str, object] = {
        "installer_extension": "06:3EA6",
        "installer_extension_bytes": len(extension),
        "destination": "31:9E18..31:9EBF executable overlay RAM",
        "exact_source": "4E:9E18..4E:9EBF",
        "exact_bytes": SIZE,
        "relocation": "same PC; local AJMP operands unchanged",
        "failure_removed": "31:9E18 flat function suffix -> zero result count",
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
    print(f"installed application result-list creator; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-rom01-application-result-list-create-v1",
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
