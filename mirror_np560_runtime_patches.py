#!/usr/bin/env python3
"""Mirror guest-installed NP560 code patches into source-pinned PRG copies.

The reconstructed resident ROM installs application overlays and then patches
some call sites in their writable destinations.  A Harvard QEMU mapping may
source an overlay's instruction view from its immutable linked PRG copy to
protect it from unrelated NAND-buffer writes.  In that case the later guest
patch would otherwise be hidden.  This preflight extracts immediate program
writes from the actual guest installer routines, reports every conflict, and
mirrors only those evidenced words into a derived PRG image.

This is firmware preprocessing, not a host ROM service: the output contains
the same final instruction words that the reconstructed guest installer writes
to its destination code RAM.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from disassembly import build_np560_reconstructed_rom as rom  # noqa: E402
from disassembly.np560_overlay_map import (  # noqa: E402
    DEFAULT_QEMU_SOURCE,
    QemuMapping,
    parse_qemu_mappings,
)


PROGRAM_BASE = 0x200000


def current_resident_routines() -> dict[int, tuple[str, list[int]]]:
    """Build the v416 resident-ROM routine set used by the active emulator."""
    return rom.make_routines(
        initializer_overlay_probe=True,
        probe_rom_08_return=True,
        probe_rom_01_return=True,
        probe_system_main=True,
        probe_storage_global_templates=True,
        factory_linked_startup=True,
    )


def static_program_writes(
    routines: dict[int, tuple[str, Sequence[int]]],
) -> tuple[dict[int, list[int]], dict[int, set[str]]]:
    """Recover immediate DS0/MOV/store writes emitted by guest installers."""
    # Keep write order.  Several installers first copy an original call word
    # and then retarget that same word later in the same guest routine.  A set
    # makes preprocessing alternate between the two values on each run;
    # retaining the sequence makes the final guest-visible write idempotent.
    values: dict[int, list[int]] = defaultdict(list)
    origins: dict[int, set[str]] = defaultdict(set)
    for _base, (name, words) in routines.items():
        ds0: int | None = None
        index = 0
        while index < len(words):
            if words[index] == 0x6810 and index + 1 < len(words):
                ds0 = words[index + 1]
                index += 2
                continue
            if (
                ds0 is not None
                and words[index] == 0x68F0
                and index + 3 < len(words)
                and words[index + 2] == 0xA8F0
            ):
                address = (ds0 << 15) | (words[index + 3] & 0x7FFF)
                values[address].append(words[index + 1])
                origins[address].add(name)
                index += 4
                continue
            index += 1
    return dict(values), dict(origins)


def narrowest_source_mapping(
    address: int,
    mappings: Iterable[QemuMapping],
) -> QemuMapping | None:
    matches = [
        mapping for mapping in mappings
        if mapping.code and mapping.source is not None
        and mapping.base <= address and address + 2 <= mapping.end
    ]
    return min(matches, key=lambda mapping: mapping.size, default=None)


def firmware_word(firmware: bytes, address: int) -> int:
    offset = address - PROGRAM_BASE
    if offset < 0 or offset + 2 > len(firmware):
        raise ValueError(f"source address {address:06X} is outside the PRG")
    return int.from_bytes(firmware[offset:offset + 2], "little")


def planned_source_patches(
    firmware: bytes,
    mappings: Sequence[QemuMapping],
    writes: dict[int, Sequence[int]],
    origins: dict[int, set[str]],
) -> list[dict]:
    patches: dict[int, dict] = {}
    for destination, candidates in sorted(writes.items()):
        mapping = narrowest_source_mapping(destination, mappings)
        if mapping is None:
            continue
        source = mapping.source + destination - mapping.base
        old_word = firmware_word(firmware, source)
        if not candidates:
            continue
        new_word = candidates[-1]
        if new_word == old_word:
            continue
        previous = patches.get(source)
        if previous is not None and previous["new_word"] != new_word:
            raise ValueError(
                f"conflicting mirrored values for source {source:06X}"
            )
        patches[source] = {
            "destination": destination,
            "source": source,
            "old_word": old_word,
            "new_word": new_word,
            "mapping": mapping.symbol,
            "origins": sorted(origins.get(destination, ())),
        }
    return [patches[address] for address in sorted(patches)]


def apply_source_patches(firmware: bytes, patches: Sequence[dict]) -> bytes:
    image = bytearray(firmware)
    for patch in patches:
        offset = patch["source"] - PROGRAM_BASE
        image[offset:offset + 2] = patch["new_word"].to_bytes(2, "little")
    return bytes(image)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--qemu-source", type=Path, default=DEFAULT_QEMU_SOURCE)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    firmware = args.firmware.read_bytes()
    mappings = parse_qemu_mappings(
        args.qemu_source.read_text(encoding="utf-8")
    )
    writes, origins = static_program_writes(current_resident_routines())
    patches = planned_source_patches(
        firmware, mappings, writes, origins
    )
    output = apply_source_patches(firmware, patches)
    document = {
        "format": "np560-source-pinned-runtime-patches-v1",
        "hardware_rom_service": False,
        "input": str(args.firmware.resolve()),
        "input_sha256": hashlib.sha256(firmware).hexdigest(),
        "output": str(args.output.resolve()),
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "patch_words": len(patches),
        "patches": [
            {
                **patch,
                "destination": f"{patch['destination'] >> 16:02X}:"
                               f"{patch['destination'] & 0xFFFF:04X}",
                "source": f"{patch['source'] >> 16:02X}:"
                          f"{patch['source'] & 0xFFFF:04X}",
                "old_word": f"{patch['old_word']:04X}",
                "new_word": f"{patch['new_word']:04X}",
            }
            for patch in patches
        ],
    }
    print(json.dumps(document, ensure_ascii=False, indent=2))
    if not args.dry_run:
        args.output.write_bytes(output)
        manifest = args.manifest or args.output.with_suffix(".json")
        manifest.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
