#!/usr/bin/env python3
"""Apply verified same-PC resident routines to an existing ROM lineage.

Late NP560 ROMs contain post-builder fixes, so rebuilding a base image can
discard proven work.  This idempotent patcher copies only closed vendor
functions whose exact +0x1D-bank sources survive in NP560.PRG.  A target must
be either fully reserved or already byte-identical; any partial/foreign body
is rejected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

try:
    from disassembly import build_np560_reconstructed_rom as rom
except ModuleNotFoundError:
    import build_np560_reconstructed_rom as rom


RESERVED_WORD = 0x0F00


@dataclass(frozen=True)
class ExactResidentSource:
    destination: int
    source: int
    size: int
    name: str
    expected_calls: tuple[tuple[int, int], ...] = ()


EXACT_RESIDENT_SOURCES = (
    ExactResidentSource(
        rom.RESIDENT_DELIMITED_FIELD_COPY_06_ADDRESS,
        rom.RESIDENT_DELIMITED_FIELD_COPY_06_SOURCE,
        rom.RESIDENT_DELIMITED_FIELD_COPY_06_SIZE,
        "resident_delimited_field_copy_06_dd56",
    ),
    ExactResidentSource(
        rom.RESIDENT_SUFFIX_REPLACE_07_ADDRESS,
        rom.RESIDENT_SUFFIX_REPLACE_07_SOURCE,
        rom.RESIDENT_SUFFIX_REPLACE_07_SIZE,
        "resident_suffix_replace_07_7d74",
        ((0xBD31, 0xAED0), (0xBD32, 0x8204)),
    ),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words_to_bytes(words: list[int]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def validate_source(spec: ExactResidentSource, words: list[int]) -> None:
    if words[0] >> 8 != 0x2E:
        raise ValueError(f"{spec.name} has no LINK prologue")
    if words[-2:] != [0x2F00, rom.RETS]:
        raise ValueError(f"{spec.name} has no closed UNLINK/RETS epilogue")
    calls = {
        (words[index], words[index + 1])
        for index in range(len(words) - 1)
        if words[index] >> 8 == 0xBD
    }
    if calls != set(spec.expected_calls):
        raise ValueError(
            f"{spec.name} call closure changed: "
            f"expected {spec.expected_calls!r}, got {sorted(calls)!r}"
        )


def patch_image(baseline: bytes) -> tuple[bytes, list[dict[str, object]]]:
    patched = bytearray(baseline)
    records: list[dict[str, object]] = []
    for spec in EXACT_RESIDENT_SOURCES:
        words = rom.program_source_words(spec.source, spec.size)
        validate_source(spec, words)
        body = words_to_bytes(words)
        end = spec.destination + len(body)
        if end > len(patched):
            raise ValueError(f"{spec.name} extends beyond the ROM image")
        current = bytes(patched[spec.destination:end])
        reserved = words_to_bytes([RESERVED_WORD] * len(words))
        if current == body:
            action = "already exact"
        elif current == reserved:
            patched[spec.destination:end] = body
            action = "installed"
        else:
            raise ValueError(
                f"{spec.name} target is neither reserved nor already exact"
            )
        records.append({
            "name": spec.name,
            "destination": (
                f"{spec.destination >> 16:02X}:"
                f"{spec.destination & 0xFFFF:04X}"
            ),
            "source": f"{spec.source >> 16:02X}:{spec.source & 0xFFFF:04X}",
            "bytes": spec.size,
            "calls": [f"{word >> 8:02X}:{offset:04X}"
                      for word, offset in spec.expected_calls],
            "action": action,
        })
    return bytes(patched), records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    baseline = args.baseline.read_bytes()
    output, patches = patch_image(baseline)
    args.output.write_bytes(output)
    print(f"applied exact resident sources; sha256={sha256(output)}")
    for patch in patches:
        print(f"  {patch['destination']} {patch['action']}: {patch['name']}")
    if args.manifest:
        record = {
            "format": "np560-exact-resident-sources-v1",
            "baseline": str(args.baseline),
            "baseline_sha256": sha256(baseline),
            "output": str(args.output),
            "output_sha256": sha256(output),
            "patches": patches,
            "execution_model": (
                "ordinary guest DMCU instructions in reconstructed internal "
                "ROM; no host services or SCALL interception"
            ),
        }
        args.manifest.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
