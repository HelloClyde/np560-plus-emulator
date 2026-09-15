#!/usr/bin/env python3
"""Install three exact children of the application result-object path.

After the exact 26:8296 initializer is restored, resident 1E:6444 reaches
30:826A and subsequently depends on 32:D016 and 32:BED6.  Their complete
same-linked implementations are present in the upgrade PRG.  Append ordinary
guest DMCU copy loops for all three statically established dependencies.
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
PREVIOUS_EXTENSION_ADDRESS = 0x063ED0
PREVIOUS_EXTENSION_SIZE = 44
EXTENSION_ADDRESS = PREVIOUS_EXTENSION_ADDRESS + PREVIOUS_EXTENSION_SIZE - 2

OVERLAYS: tuple[tuple[int, int, int, bytes, bytes, str], ...] = (
    (0x30826A, 0x4D826A, 0x00FA, b"\x04\x2e", b"\x00\x2f\x20\xc6",
     "result_object_header"),
    (0x32D016, 0x4FD016, 0x004A, b"\x00\x2e", b"\x00\x2f\x20\xc6",
     "result_object_header_copy"),
    (0x32BED6, 0x4FBED6, 0x0050, b"\x01\x2e", b"\x00\x2f\x20\xc6",
     "result_object_finalize"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def program_bytes(program: bytes, address: int, size: int) -> bytes:
    offset = address - PROGRAM_BASE
    if offset < 0 or offset + size > len(program):
        raise ValueError(f"program range 0x{address:06X}+0x{size:X} is absent")
    return program[offset:offset + size]


def extension_bytes() -> bytes:
    words: list[int] = []
    for destination, source, size, _head, _tail, _name in OVERLAYS:
        words.extend(copy_code_words(destination, source, size))
    words.append(RETS)
    return words_to_bytes(tuple(words))


def patch_image(baseline: bytes, program: bytes) -> tuple[bytes, dict[str, object]]:
    for destination, source, size, head, tail, name in OVERLAYS:
        exact = program_bytes(program, source, size)
        if exact[:len(head)] != head:
            raise ValueError(f"{source:06X} {name} prologue changed")
        if exact[-len(tail):] != tail:
            raise ValueError(f"{source:06X} {name} epilogue changed")

    extension = extension_bytes()
    end = EXTENSION_ADDRESS + len(extension)
    if end > len(baseline):
        raise ValueError("result-object child installer is outside ROM")
    expected = words_to_bytes((RETS,)) + RESERVED_WORD * (
        len(extension) // 2 - 1
    )
    if baseline[EXTENSION_ADDRESS:end] != expected:
        raise ValueError("06:3EFA child installer range is not RETS/reserved ROM")

    patched = bytearray(baseline)
    patched[EXTENSION_ADDRESS:end] = extension
    entries = []
    for destination, source, size, _head, _tail, name in OVERLAYS:
        entries.append({
            "name": name,
            "destination": f"{destination >> 16:02X}:{destination & 0xFFFF:04X}",
            "exact_source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
            "exact_bytes": size,
        })
    metadata: dict[str, object] = {
        "installer_extension": "06:3EFA",
        "installer_extension_bytes": len(extension),
        "overlays": entries,
        "execution_model": "ordinary guest DMCU copy loops; no host HLE",
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
    print(f"installed three application result-object children; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-rom01-application-result-object-children-v1",
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
