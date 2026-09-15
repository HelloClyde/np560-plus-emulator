#!/usr/bin/env python3
"""Install the remaining exact application result-scan overlay chain.

Runtime comparison after v97 proves that the restored matcher/object path is
exact, while fifteen statically identified scanner dependencies still contain
unrelated flat PRG bodies.  Append guest DMCU copy loops for those original
same-linked implementations.  Already exact overlays and the two previously
completed modal-cleanup paths are deliberately left untouched.
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
PREVIOUS_EXTENSION_ADDRESS = 0x063F78
PREVIOUS_EXTENSION_SIZE = 44
EXTENSION_ADDRESS = PREVIOUS_EXTENSION_ADDRESS + PREVIOUS_EXTENSION_SIZE - 2

# destination, exact PRG source, byte count, exact first word, label
OVERLAYS: tuple[tuple[int, int, int, bytes, str], ...] = (
    (0x2BD756, 0x48D756, 0x0218, b"\x0a\x2e", "result_flag_update"),
    (0x318F74, 0x4E8F74, 0x00AC, b"\x04\x2e", "result_table_init"),
    (0x32446C, 0x4F446C, 0x0076, b"\x02\x2e", "result_table_release"),
    (0x2C9C66, 0x499C66, 0x01EA, b"\x0a\x2e", "result_flag_read"),
    (0x32AEEC, 0x4FAEEC, 0x0056, b"\x02\x2e", "result_file_release"),
    (0x2479F2, 0x4179F2, 0x0442, b"\xfc\x2e", "result_context_release"),
    (0x32A9D2, 0x4FA9D2, 0x0054, b"\x01\x2e", "result_object_release"),
    (0x27AF22, 0x44AF22, 0x0336, b"\x04\x2e", "result_record_table"),
    (0x321722, 0x4F1722, 0x0086, b"\x00\x2e", "result_text_length"),
    (0x323B74, 0x4F3B74, 0x007C, b"\x00\x2e", "result_item_render"),
    (0x25AA58, 0x42AA58, 0x03D6, b"\x06\x2e", "result_text_render"),
    (0x327B42, 0x4F7B42, 0x0066, b"\x00\x2e", "result_glyph_render_alt"),
    (0x2F37B0, 0x4C37B0, 0x014C, b"\x01\x2e", "file_path_resolve"),
    (0x31B83C, 0x4EB83C, 0x00A0, b"\x02\x2e", "file_root_lookup"),
    (0x325592, 0x4F5592, 0x0070, b"\x00\x2e", "file_object_release"),
)
EPILOGUE = b"\x00\x2f\x20\xc6"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def program_bytes(program: bytes, address: int, size: int) -> bytes:
    offset = address - PROGRAM_BASE
    if offset < 0 or offset + size > len(program):
        raise ValueError(f"program range 0x{address:06X}+0x{size:X} is absent")
    return program[offset:offset + size]


def extension_bytes() -> bytes:
    words: list[int] = []
    for destination, source, size, _head, _name in OVERLAYS:
        words.extend(copy_code_words(destination, source, size))
    words.append(RETS)
    return words_to_bytes(tuple(words))


def patch_image(baseline: bytes, program: bytes) -> tuple[bytes, dict[str, object]]:
    for _destination, source, size, head, name in OVERLAYS:
        exact = program_bytes(program, source, size)
        if exact[:2] != head:
            raise ValueError(f"{source:06X} {name} prologue changed")
        if exact[-4:] != EPILOGUE:
            raise ValueError(f"{source:06X} {name} epilogue changed")

    extension = extension_bytes()
    end = EXTENSION_ADDRESS + len(extension)
    if end > len(baseline):
        raise ValueError("result-scan chain installer is outside ROM")
    expected = words_to_bytes((RETS,)) + RESERVED_WORD * (
        len(extension) // 2 - 1
    )
    if baseline[EXTENSION_ADDRESS:end] != expected:
        raise ValueError("06:3FA2 scan-chain range is not RETS/reserved ROM")

    patched = bytearray(baseline)
    patched[EXTENSION_ADDRESS:end] = extension
    entries = [{
        "name": name,
        "destination": f"{destination >> 16:02X}:{destination & 0xFFFF:04X}",
        "exact_source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
        "exact_bytes": size,
    } for destination, source, size, _head, name in OVERLAYS]
    metadata: dict[str, object] = {
        "installer_extension": "06:3FA2",
        "installer_extension_bytes": len(extension),
        "overlays": entries,
        "selection": (
            "all runtime-mismatched result-scan dependencies except the two "
            "already completed modal-cleanup paths"
        ),
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
    print(f"installed exact application result-scan chain; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-rom01-application-result-scan-chain-v1",
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
