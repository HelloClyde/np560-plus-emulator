#!/usr/bin/env python3
"""Restore the exact resident handler reached by foreground event 0xE0.

The recovered dispatcher at 3B:F734 maps a physical matrix key to event 0xE0
and calls resident 15:F0EE from 3B:F886.  That resident range is absent from
the upgrade payload, but the complete same-PC factory load image survives at
32:F0EE..32:FF03 in NP560.PRG.  Copying it to 15:F0EE preserves every local
AJMP PC and every already-linked resident SCALL target.

This installs ordinary guest DMCU instructions in the reconstructed SoC ROM;
it does not add a QEMU callback, ROM service, or host-side event handler.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROGRAM_BASE = 0x200000
DESTINATION = 0x15F0EE
SOURCE = 0x32F0EE
SIZE = 0x0E16
RESERVED_WORD = b"\x00\x0f"
PROLOGUE = (0x2E57,)
EPILOGUE = (0x2F00, 0xC620)


def words_to_bytes(words: tuple[int, ...]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def program_bytes(program: bytes, address: int, size: int) -> bytes:
    offset = address - PROGRAM_BASE
    if offset < 0 or offset + size > len(program):
        raise ValueError(f"program range 0x{address:06X}+0x{size:X} is absent")
    return program[offset:offset + size]


def patch_image(baseline: bytes, program: bytes) -> tuple[bytes, dict[str, object]]:
    exact = program_bytes(program, SOURCE, SIZE)
    if exact[:2] != words_to_bytes(PROLOGUE):
        raise ValueError("32:F0EE no longer starts with LINK #0x57")
    if exact[-4:] != words_to_bytes(EPILOGUE):
        raise ValueError("32:F0EE no longer ends with UNLINK/RETS at 32:FF02")

    end = DESTINATION + SIZE
    if end > len(baseline):
        raise ValueError("15:F0EE handler falls outside the SoC ROM image")
    if baseline[DESTINATION:end] != RESERVED_WORD * (SIZE // 2):
        raise ValueError("15:F0EE..15:FF03 is no longer reserved resident ROM")

    patched = bytearray(baseline)
    patched[DESTINATION:end] = exact
    metadata: dict[str, object] = {
        "destination": "15:F0EE..15:FF03",
        "exact_source": "32:F0EE..32:FF03",
        "bytes": SIZE,
        "relocation": "same PC; local AJMP operands unchanged",
        "discovered_by": "3B:F886 SCALL after exact matrix event 0xE0",
        "execution_model": "exact guest DMCU code in SoC ROM; no host HLE",
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
    print(f"installed resident event-E0 handler; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-resident-event-e0-handler-v1",
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
