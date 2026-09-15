#!/usr/bin/env python3
"""Create a diagnostic minimal ``nminbox.pim`` in an NP560 checkpoint.

The resident 1E:6444 routine constructs and validates a 0x40-byte NOAHPIM
header.  Its mode-4 creation arm then writes a two-byte count and an eight-byte
first-record descriptor, producing a 0x4A-byte empty file.  This tool reproduces
that byte-exact *empty-file* layout in a copy of a checkpoint so stale startup
modal contamination can be isolated.

It remains a diagnostic provisioning aid rather than a recovered factory
workflow.  The startup caller uses resident ``fopen(mode=1)``, which requires
the file object to be recognized by the resident catalogue, so every directory
record field is kept explicit and covered by tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import shutil
import struct
from pathlib import Path
from typing import Any

try:
    from .ensure_np560_fat16_directories import ensure_directories
    from .inject_np560_npe_fat16 import (
        CHECKPOINT_MAGIC,
        FAT16_EOC,
        SECTOR_SIZE,
        CheckpointFat16,
        _find_entry,
        _free_clusters,
        _free_entry,
        _read_file_chain,
        cluster_lba,
        directory_entry,
        dot_entry,
        encode_short_name,
    )
except ImportError:  # Direct execution from scripts/.
    from ensure_np560_fat16_directories import ensure_directories  # type: ignore
    from inject_np560_npe_fat16 import (  # type: ignore
        CHECKPOINT_MAGIC,
        FAT16_EOC,
        SECTOR_SIZE,
        CheckpointFat16,
        _find_entry,
        _free_clusters,
        _free_entry,
        _read_file_chain,
        cluster_lba,
        directory_entry,
        dot_entry,
        encode_short_name,
    )


# The exact startup path captured at resident fopen is
# ``30 3A 5C CE D2 B5 C4 D3 CA BC FE 5C 6E 6D 69 6E 62 6F 78 2E 70 69 6D``.
# GBK ``CE D2 B5 C4 D3 CA BC FE`` is “我的邮件”; an earlier diagnostic
# incorrectly labelled it “同步学习” (whose distinct GBK bytes are
# ``CD AC B2 BD D1 A7 CF B0``).
DEFAULT_DIRECTORY = "我的邮件"
DEFAULT_STEM = "nminbox"

# Captured read-only at 1E:6594 after the exact resident allocator constructed
# the header for category 08/mode 01.  Word-valued fields retain the guest's
# logical byte order: the 0x0040 header size is therefore bytes 00 40.
MINIMAL_PIM_HEADER = bytes.fromhex(
    "4e4f414850494d00"
    "56312e3000000000"
    "0040000000000000"
    "0000000000000000"
    "0000000000000000"
    "0000000000000000"
    "0000000000000000"
    "0000000055aa55aa"
)

# The mode-4 arm at 1E:660C..66B0 writes a zero record count followed by an
# eight-byte descriptor whose final guest-order word is 0x004A.
MINIMAL_PIM_TRAILER = b"\0" * 9 + b"\x4A"
MINIMAL_PIM = MINIMAL_PIM_HEADER + MINIMAL_PIM_TRAILER


def _read_cluster(volume: CheckpointFat16, cluster: int) -> bytes:
    lba = cluster_lba(volume.layout, cluster)
    return b"".join(
        volume.read_sector(lba + index)
        for index in range(volume.layout["sectors_per_cluster"])
    )


def _write_cluster(
        volume: CheckpointFat16, cluster: int, payload: bytes,
) -> None:
    cluster_bytes = volume.layout["cluster_bytes"]
    if len(payload) != cluster_bytes:
        raise ValueError("cluster payload size changed")
    lba = cluster_lba(volume.layout, cluster)
    for index in range(volume.layout["sectors_per_cluster"]):
        offset = index * SECTOR_SIZE
        volume.write_sector(lba + index, payload[offset:offset + SECTOR_SIZE])


def inject_minimal_pim(
        volume: CheckpointFat16, *, directory: str = DEFAULT_DIRECTORY,
        stem: str = DEFAULT_STEM, lowercase_extension: bool = False,
        omit_dot_entries: bool = False,
) -> dict[str, Any]:
    """Insert or verify the recovered minimal PIM and return an audit report."""
    root_name = encode_short_name(directory)
    # The exact path parser at 28:D7E2 normalises ASCII components to upper
    # case before 2D:D93C compares the resulting 8.3 selector byte-for-byte.
    # FAT short-name lookup is therefore case-sensitive here: a literal
    # ``nminbox`` directory entry differs from ``NMINBOX`` by 0x20 and is not
    # found even though the caller's source path is lower-case.
    file_name = encode_short_name(stem.upper(), "PIM")
    if lowercase_extension:
        file_name = file_name[:8] + b"pim"
    root = volume.root_bytes()
    root_offset = _find_entry(root, root_name)
    if root_offset is None:
        raise ValueError(f"root directory {directory!r} is absent")
    root_entry = root[root_offset:root_offset + 32]
    if not root_entry[11] & 0x10:
        raise ValueError(f"root entry {directory!r} is not a directory")
    directory_cluster = struct.unpack_from("<H", root_entry, 26)[0]

    fat = volume.read_fat(0)
    for copy_index in range(1, volume.layout["fat_count"]):
        if volume.read_fat(copy_index) != fat:
            raise ValueError("FAT16 copies differ before PIM import")
    if struct.unpack_from("<H", fat, directory_cluster * 2)[0] < 0xFFF8:
        raise ValueError("multi-cluster target directory is not supported")

    directory_data = bytearray(_read_cluster(volume, directory_cluster))
    if omit_dot_entries:
        expected_dots = (
            dot_entry(".", directory_cluster) + dot_entry("..", 0)
        )
        if directory_data[:64] == expected_dots:
            directory_data[:64] = b"\0" * 64
        elif any(directory_data[:64]):
            raise ValueError(
                "cannot omit dot entries from a non-empty target directory"
            )
    existing_offset = _find_entry(directory_data, file_name)
    if existing_offset is not None:
        entry = directory_data[existing_offset:existing_offset + 32]
        if entry[11] & 0x10:
            raise ValueError(f"{stem}.PIM exists but is a directory")
        first_cluster = struct.unpack_from("<H", entry, 26)[0]
        size = struct.unpack_from("<I", entry, 28)[0]
        existing, clusters = _read_file_chain(
            volume, fat, first_cluster, size,
        )
        if existing != MINIMAL_PIM:
            raise ValueError(
                f"{stem}.PIM exists with non-minimal content; refusing overwrite"
            )
        return {
            "created": False,
            "directory": directory,
            "directory_cluster": directory_cluster,
            "file": f"{stem}.PIM",
            "extension_case": "lower" if lowercase_extension else "upper",
            "directory_layout": (
                "diagnostic-file-first" if omit_dot_entries
                else "guest-dot-records"
            ),
            "file_short_name_hex": file_name.hex(" ").upper(),
            "file_size": size,
            "file_first_cluster": first_cluster,
            "file_cluster_count": len(clusters),
            "file_sha256": hashlib.sha256(existing).hexdigest().upper(),
            "byte_exact": True,
        }

    cluster_count = (
        len(MINIMAL_PIM) + volume.layout["cluster_bytes"] - 1
    ) // volume.layout["cluster_bytes"]
    clusters = _free_clusters(fat, cluster_count, minimum=2)
    for current, following in zip(clusters, clusters[1:]):
        struct.pack_into("<H", fat, current * 2, following)
    struct.pack_into("<H", fat, clusters[-1] * 2, FAT16_EOC)
    for copy_index in range(volume.layout["fat_count"]):
        volume.write_fat(fat, copy_index)

    entry_offset = _free_entry(directory_data)
    directory_data[entry_offset:entry_offset + 32] = directory_entry(
        file_name, 0x20, clusters[0], len(MINIMAL_PIM),
    )
    _write_cluster(volume, directory_cluster, bytes(directory_data))

    padded = MINIMAL_PIM.ljust(
        len(clusters) * volume.layout["cluster_bytes"], b"\0",
    )
    for index, cluster in enumerate(clusters):
        offset = index * volume.layout["cluster_bytes"]
        _write_cluster(
            volume,
            cluster,
            padded[offset:offset + volume.layout["cluster_bytes"]],
        )
    volume.finalize_allocations()

    reconstructed, readback_clusters = _read_file_chain(
        volume, volume.read_fat(0), clusters[0], len(MINIMAL_PIM),
    )
    if reconstructed != MINIMAL_PIM or readback_clusters != clusters:
        raise ValueError("minimal PIM readback mismatch")
    return {
        "created": True,
        "directory": directory,
        "directory_cluster": directory_cluster,
        "file": f"{stem}.PIM",
        "extension_case": "lower" if lowercase_extension else "upper",
        "directory_layout": (
            "diagnostic-file-first" if omit_dot_entries
            else "guest-dot-records"
        ),
        "file_short_name_hex": file_name.hex(" ").upper(),
        "file_size": len(MINIMAL_PIM),
        "file_first_cluster": clusters[0],
        "file_cluster_count": len(clusters),
        "file_sha256": hashlib.sha256(MINIMAL_PIM).hexdigest().upper(),
        "byte_exact": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_checkpoint", type=Path)
    parser.add_argument("destination_checkpoint", type=Path)
    parser.add_argument("--directory", default=DEFAULT_DIRECTORY)
    parser.add_argument("--stem", default=DEFAULT_STEM)
    parser.add_argument(
        "--lowercase-extension", action="store_true",
        help="diagnostic A/B: store the FAT extension as literal lowercase pim",
    )
    parser.add_argument(
        "--omit-dot-entries", action="store_true",
        help="diagnostic A/B: place nminbox.pim in the first directory slot",
    )
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    source = args.source_checkpoint.resolve()
    destination = args.destination_checkpoint.resolve()
    if source == destination:
        raise ValueError("PIM A/B requires a distinct destination checkpoint")
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
                directory_report = ensure_directories(
                    volume, [args.directory],
                )
                pim_report = inject_minimal_pim(
                    volume,
                    directory=args.directory,
                    stem=args.stem,
                    lowercase_extension=args.lowercase_extension,
                    omit_dot_entries=args.omit_dot_entries,
                )
                image[48:56] = b"\0" * 8
                image.flush()
            finally:
                image.close()
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    result = {
        "schema": "np560-minimal-pim-diagnostic-v1",
        "scope": {
            "diagnostic_only": True,
            "normal_boot_compatible": True,
            "factory_provisioning_recovered": False,
            "live_guest_memory_modified": False,
            "guest_menu_or_framebuffer_modified": False,
            "checkpoint_rehash_required": True,
        },
        "source_checkpoint": str(source),
        "destination_checkpoint": str(destination),
        "directory": directory_report[0],
        "pim": pim_report,
        "evidence": {
            "allocator": "1E:6444 <- 3B:6444",
            "header_snapshot_pc": "1E:6594",
            "creation_arm": "1E:65A8..66B0",
            "resident_selector_short_name_hex": (
                "4E 4D 49 4E 42 4F 58 20 50 49 4D"
            ),
            "case_sensitive_control": (
                "literal lowercase nminbox differs by 0x20 and does not match"
            ),
            "startup_open": (
                "v729 resolves uppercase NMINBOX PIM in mode 1 and returns "
                "error 0000"
            ),
        },
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    print("REHASH_REQUIRED=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
