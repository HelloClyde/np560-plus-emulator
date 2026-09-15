#!/usr/bin/env python3
"""Install the exact application result-object initializer at 26:8296.

Resident 1E:6444 reaches this function immediately after constructing the
result resource path.  The runtime destination contains unrelated flat PRG
bytes beginning with 0x7BEA, while the complete same-linked implementation is
present at 43:8296.  Extend the existing guest installer by one ordinary DMCU
copy loop; QEMU provides writable/executable RAM only.
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
PREVIOUS_EXTENSION_ADDRESS = 0x063EA6
PREVIOUS_EXTENSION_SIZE = 44
EXTENSION_ADDRESS = PREVIOUS_EXTENSION_ADDRESS + PREVIOUS_EXTENSION_SIZE - 2
DESTINATION = 0x268296
SOURCE = 0x438296
SIZE = 0x0388
PROLOGUE = b"\x01\x2e"
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
        raise ValueError("43:8296 no longer starts with LINK #1")
    if exact[-4:] != EPILOGUE:
        raise ValueError("43:8296 no longer ends with UNLINK/RETS")

    extension = extension_bytes()
    end = EXTENSION_ADDRESS + len(extension)
    if end > len(baseline):
        raise ValueError("result-object initializer installer is outside ROM")
    expected = words_to_bytes((RETS,)) + RESERVED_WORD * (
        len(extension) // 2 - 1
    )
    if baseline[EXTENSION_ADDRESS:end] != expected:
        raise ValueError(
            "06:3ED0 result-object initializer range is not RETS/reserved ROM"
        )

    patched = bytearray(baseline)
    patched[EXTENSION_ADDRESS:end] = extension
    metadata: dict[str, object] = {
        "installer_extension": "06:3ED0",
        "installer_extension_bytes": len(extension),
        "destination": "26:8296..26:861D executable overlay RAM",
        "exact_source": "43:8296..43:861D",
        "exact_bytes": SIZE,
        "relocation": "same PC; local control-flow operands unchanged",
        "failure_removed": "26:8296 flat data word 0x7BEA",
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
    print(f"installed application result-object initializer; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-rom01-application-result-object-init-v1",
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
