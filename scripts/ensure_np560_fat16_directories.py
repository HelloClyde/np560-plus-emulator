#!/usr/bin/env python3
"""Add missing diagnostic FAT16 directories to an NP560 NAND checkpoint.

The guest normally obtains its application directories through the factory
provisioning/transfer workflow.  Until that workflow is fully recovered this
tool creates a disposable A/B checkpoint so a missing default directory does
not leave an old error dialog on the modal stack and contaminate later menu
tests.  It edits only a copied checkpoint and never writes live guest state.
"""

from __future__ import annotations

import argparse
import json
import mmap
import shutil
import struct
from pathlib import Path
from typing import Any, Protocol

try:
    from .inject_np560_npe_fat16 import (
        CHECKPOINT_MAGIC,
        FAT16_EOC,
        SECTOR_SIZE,
        CheckpointFat16,
        _find_entry,
        _free_clusters,
        _free_entry,
        cluster_lba,
        directory_entry,
        dot_entry,
        encode_short_name,
    )
except ImportError:  # Direct execution from scripts/.
    from inject_np560_npe_fat16 import (  # type: ignore
        CHECKPOINT_MAGIC,
        FAT16_EOC,
        SECTOR_SIZE,
        CheckpointFat16,
        _find_entry,
        _free_clusters,
        _free_entry,
        cluster_lba,
        directory_entry,
        dot_entry,
        encode_short_name,
    )


class Fat16Volume(Protocol):
    layout: dict[str, int]

    def root_bytes(self) -> bytearray: ...
    def write_root_bytes(self, root: bytes) -> None: ...
    def read_fat(self, copy_index: int = 0) -> bytearray: ...
    def write_fat(self, fat: bytes, copy_index: int) -> None: ...
    def write_sector(self, lba: int, logical: bytes) -> None: ...
    def finalize_allocations(self) -> None: ...


def ensure_directories(
        volume: Fat16Volume, directories: list[str],
) -> list[dict[str, Any]]:
    """Create empty guest-format directories and return an audit report."""
    if not directories:
        raise ValueError("at least one directory is required")
    if len(set(directories)) != len(directories):
        raise ValueError("directory list contains duplicates")

    root = volume.root_bytes()
    fat = volume.read_fat(0)
    for copy_index in range(1, volume.layout["fat_count"]):
        if volume.read_fat(copy_index) != fat:
            raise ValueError("FAT16 copies differ before directory update")

    report: list[dict[str, Any]] = []
    pending_clusters: list[tuple[str, bytes, int]] = []
    for name in directories:
        short_name = encode_short_name(name)
        existing_offset = _find_entry(root, short_name)
        if existing_offset is not None:
            entry = root[existing_offset:existing_offset + 32]
            if not entry[11] & 0x10:
                raise ValueError(
                    f"root entry {name!r} exists but is not a directory"
                )
            report.append({
                "directory": name,
                "short_name_hex": short_name.hex(" ").upper(),
                "cluster": struct.unpack_from("<H", entry, 26)[0],
                "created": False,
            })
            continue

        cluster = _free_clusters(fat, 1, minimum=2)[0]
        struct.pack_into("<H", fat, cluster * 2, FAT16_EOC)
        root_offset = _free_entry(root)
        root[root_offset:root_offset + 32] = directory_entry(
            short_name, 0x10, cluster,
        )
        pending_clusters.append((name, short_name, cluster))
        report.append({
            "directory": name,
            "short_name_hex": short_name.hex(" ").upper(),
            "cluster": cluster,
            "created": True,
        })

    for copy_index in range(volume.layout["fat_count"]):
        volume.write_fat(fat, copy_index)
    volume.write_root_bytes(root)

    for _name, _short_name, cluster in pending_clusters:
        directory_data = bytearray(volume.layout["cluster_bytes"])
        directory_data[0:32] = dot_entry(".", cluster)
        directory_data[32:64] = dot_entry("..", 0)
        lba = cluster_lba(volume.layout, cluster)
        for sector_index in range(volume.layout["sectors_per_cluster"]):
            offset = sector_index * SECTOR_SIZE
            volume.write_sector(
                lba + sector_index,
                directory_data[offset:offset + SECTOR_SIZE],
            )
    volume.finalize_allocations()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_checkpoint", type=Path)
    parser.add_argument("destination_checkpoint", type=Path)
    parser.add_argument(
        "--directory", action="append", required=True,
        help="root directory to ensure; may be supplied more than once",
    )
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    source = args.source_checkpoint.resolve()
    destination = args.destination_checkpoint.resolve()
    if source == destination:
        raise ValueError("directory A/B requires a distinct destination")
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    try:
        with destination.open("r+b") as target:
            image = mmap.mmap(target.fileno(), 0)
            try:
                if image[:8] != CHECKPOINT_MAGIC:
                    raise ValueError("not an NP560N1 checkpoint")
                volume = CheckpointFat16(image)
                directories = ensure_directories(volume, args.directory)
                # Invalidate both payload hashes.  QEMU rejects this image until
                # np560_checkpoint_rehash has recomputed them.
                image[48:56] = b"\0" * 8
                image.flush()
            finally:
                image.close()
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    result = {
        "schema": "np560-fat16-directory-diagnostic-v1",
        "scope": {
            "diagnostic_only": True,
            "factory_provisioning_recovered": False,
            "live_guest_memory_modified": False,
            "guest_menu_or_framebuffer_modified": False,
            "checkpoint_rehash_required": True,
        },
        "source_checkpoint": str(source),
        "destination_checkpoint": str(destination),
        "directories": directories,
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
