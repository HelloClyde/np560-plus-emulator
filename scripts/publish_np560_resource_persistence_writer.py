#!/usr/bin/env python3
"""Publish the exact NP560 resource-setting writer into its runtime PCs.

The V3.80 upgrade PRG contains complete linked implementations in banks
45/4F/50, while the corresponding runtime banks 28/32/33 contain unrelated
flat fragments.  The reconstructed resident installer copies these functions
through the guest data bus.  QEMU's program-NOR instruction view cannot add
three more subpage aliases without exceeding the DMCU target's fixed physical
section table, so the canonical derived runtime PRG mirrors the same shipped
bytes into the three destination windows before launch.

This is deterministic firmware preprocessing, not a host ROM or storage
service: the CPU executes the original DMCU words and all calls, NAND writes,
errors, and return values remain guest-controlled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROGRAM_BASE = 0x200000
PERSISTENCE_WRITER_MODULES = (
    ("resource-persist-wrapper", 0x32EBAE, 0x4FEBAE, 0x0040),
    ("resource-persist-bridge", 0x330D7E, 0x500D7E, 0x0032),
    ("resource-persist-page-write", 0x280F92, 0x450F92, 0x0312),
)


def _slice(program: bytes, address: int, size: int) -> bytes:
    offset = address - PROGRAM_BASE
    if offset < 0 or offset + size > len(program):
        raise ValueError(
            f"program range {address:06X}+0x{size:X} is outside the PRG"
        )
    return program[offset:offset + size]


def publish_persistence_writer(program: bytes) -> tuple[bytes, dict]:
    image = bytearray(program)
    modules: list[dict] = []
    for name, destination, source, size in PERSISTENCE_WRITER_MODULES:
        if source - destination != 0x1D0000 or size <= 0 or size & 1:
            raise ValueError(f"invalid persistence module contract: {name}")
        shipped = _slice(program, source, size)
        before = _slice(program, destination, size)
        target_offset = destination - PROGRAM_BASE
        image[target_offset:target_offset + size] = shipped
        modules.append({
            "name": name,
            "destination": f"{destination >> 16:02X}:{destination & 0xFFFF:04X}",
            "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
            "bytes": size,
            "changed": before != shipped,
            "before_sha256": hashlib.sha256(before).hexdigest(),
            "source_sha256": hashlib.sha256(shipped).hexdigest(),
        })
    output = bytes(image)
    manifest = {
        "format": "np560-resource-persistence-writer-publication-v1",
        "hardware_rom_service": False,
        "host_storage_service": False,
        "guest_instruction_set": "DMCU",
        "source_delta": "0x1D0000",
        "modules": modules,
        "input_sha256": hashlib.sha256(program).hexdigest(),
        "output_sha256": hashlib.sha256(output).hexdigest(),
    }
    return output, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("program", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output, manifest = publish_persistence_writer(args.program.read_bytes())
    document = {
        **manifest,
        "input": str(args.program.resolve()),
        "output": str(args.output.resolve()),
    }
    print(json.dumps(document, ensure_ascii=False, indent=2))
    if not args.dry_run:
        args.output.write_bytes(output)
        manifest_path = args.manifest or args.output.with_suffix(".json")
        manifest_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
