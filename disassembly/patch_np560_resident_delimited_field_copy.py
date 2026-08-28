#!/usr/bin/env python3
"""Restore the exact resident 06:DD56 delimited-field copy routine.

The update package omits the SoC's internal ROM image, but preserves this
complete call-free routine at 23:DD56.  This patch copies that vendor body
into the corresponding resident-ROM address without rebuilding (and thereby
discarding) the later post-builder ROM lineage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from disassembly import build_np560_reconstructed_rom as rom
except ModuleNotFoundError:
    import build_np560_reconstructed_rom as rom


RESERVED_WORD = 0x0F00


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words_to_bytes(words: list[int]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def patch_image(baseline: bytes) -> tuple[bytes, dict[str, object]]:
    destination = rom.RESIDENT_DELIMITED_FIELD_COPY_06_ADDRESS
    source = rom.RESIDENT_DELIMITED_FIELD_COPY_06_SOURCE
    size = rom.RESIDENT_DELIMITED_FIELD_COPY_06_SIZE
    words = rom.program_source_words(source, size)
    body = words_to_bytes(words)
    end = destination + len(body)

    if words[:5] != [0x2E00, 0x58F2, 0x58F3, 0x58F4, 0x58F5]:
        raise ValueError("23:DD56 does not have the proven function prologue")
    if words[-2:] != [0x2F00, rom.RETS]:
        raise ValueError("23:DD56 does not have the proven closed epilogue")
    if any(word >> 8 == 0xBD for word in words):
        raise ValueError("23:DD56 unexpectedly contains a child SCALL")
    if end > len(baseline):
        raise ValueError("baseline ROM does not cover 06:DD56..06:DFE7")

    expected = words_to_bytes([RESERVED_WORD] * len(words))
    if baseline[destination:end] != expected:
        raise ValueError("06:DD56 target range is not fully reserved")

    patched = bytearray(baseline)
    patched[destination:end] = body
    metadata: dict[str, object] = {
        "destination": "06:DD56..06:DFE7 internal SoC ROM",
        "source": "23:DD56..23:DFE7 exact vendor body",
        "bytes": len(body),
        "abi": (
            "field_copy(destination_far, source_far, delimiter1_byte, "
            "delimiter2_byte) -> advanced_source_far"
        ),
        "callers": 11,
        "properties": [
            "call-free",
            "preserves R2..R5",
            "copies two-byte characters atomically",
            "handles bracketed fields",
            "NUL-terminates destination",
        ],
        "execution_model": (
            "ordinary guest DMCU instructions in reconstructed internal ROM; "
            "no host service or SCALL interception"
        ),
    }
    return bytes(patched), metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    baseline = args.baseline.read_bytes()
    output, patch = patch_image(baseline)
    args.output.write_bytes(output)
    print(f"restored resident 06:DD56; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-resident-delimited-field-copy-v1",
            "baseline": str(args.baseline),
            "baseline_sha256": sha256(baseline),
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
