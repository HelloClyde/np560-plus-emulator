#!/usr/bin/env python3
"""Audit reconstructed high-bank overlays on the QEMU code bus.

The ROM builder records each relocation as an ``*_OVERLAY_DESTINATION``.
QEMU must expose every such writable destination on both the data and code
buses.  A missing alias leaves the PRG's erased FFFF bytes visible to fetches,
even though the guest loader wrote the recovered function into data RAM.  A
data-backed alias is not sufficient for these relocated high-bank routines:
storage buffers later reuse that RAM, so their instruction views must remain
bound to the exact linked PRG sources recorded by the builder.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import re
from pathlib import Path

from np560_overlay_map import parse_qemu_mappings


@dataclass(frozen=True)
class Overlay:
    name: str
    destination: int
    source: int | None
    size: int | None


def builder_overlays(text: str, minimum: int) -> list[Overlay]:
    constants = {
        name: int(value, 16)
        for name, value in re.findall(
            r"^(\w+)\s*=\s*(0x[0-9a-fA-F]+)\s*$", text, re.MULTILINE
        )
    }
    result = []
    suffix = "_OVERLAY_DESTINATION"
    for name, destination in constants.items():
        if not name.endswith(suffix) or destination < minimum:
            continue
        prefix = name[: -len(suffix)]
        result.append(Overlay(
            name=name,
            destination=destination,
            source=constants.get(f"{prefix}_OVERLAY_SOURCE"),
            size=constants.get(f"{prefix}_OVERLAY_SIZE"),
        ))
    return sorted(result, key=lambda item: (item.destination, item.name))


def qemu_late_overlay_bases(text: str) -> set[int]:
    return set(qemu_late_overlay_sources(text))


def qemu_late_overlay_sources(text: str) -> dict[int, int | None]:
    return {
        mapping.base: mapping.source
        for mapping in parse_qemu_mappings(text)
        if mapping.code
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("builder", type=Path)
    parser.add_argument("qemu_model", type=Path)
    parser.add_argument("--minimum", type=lambda value: int(value, 0),
                        default=0x5C0000)
    args = parser.parse_args()

    overlays = builder_overlays(
        args.builder.read_text(encoding="utf-8"), args.minimum
    )
    mapped = qemu_late_overlay_sources(
        args.qemu_model.read_text(encoding="utf-8")
    )
    missing = [item for item in overlays if item.destination not in mapped]
    unpinned = [
        item for item in overlays
        if item.destination in mapped and item.source is not None
        and mapped[item.destination] != item.source
    ]
    for item in overlays:
        if item.destination not in mapped:
            status = "MISSING"
        elif item in unpinned:
            status = "UNPINNED"
        else:
            status = "mapped"
        source = f"{item.source:06X}" if item.source is not None else "unknown"
        mapped_source = mapped.get(item.destination)
        actual = (
            f"{mapped_source:06X}" if mapped_source is not None
            else "data-backed"
        )
        size = f"{item.size:04X}" if item.size is not None else "unknown"
        print(
            f"{status:7} {item.destination:06X} <- {source} "
            f"mapped={actual} size={size} {item.name}"
        )
    print(
        f"SUMMARY overlays={len(overlays)} missing={len(missing)} "
        f"unpinned={len(unpinned)}"
    )
    return 1 if missing or unpinned else 0


if __name__ == "__main__":
    raise SystemExit(main())
