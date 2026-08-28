#!/usr/bin/env python3
"""Locate and classify MBR/FAT boot sectors in an NP560 NAND checkpoint.

The external 16-bit NAND bus exposes adjacent bytes in the opposite order to
the firmware's byte loads.  This scanner checks both the physical byte order
stored in a checkpoint and the pair-swapped logical order seen by the guest.
It is read-only and reports physical page/sector provenance for every credible
MBR or FAT BPB it finds.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import mmap
from pathlib import Path
import struct


CHECKPOINT_MAGIC = b"NP560N1\0"
CHECKPOINT_HEADER_SIZE = 64
SECTOR_SIZE = 512


@dataclass(frozen=True)
class Geometry:
    data_offset: int
    data_size: int
    page_size: int


def checkpoint_geometry(image: mmap.mmap) -> Geometry:
    if len(image) < CHECKPOINT_HEADER_SIZE or image[:8] != CHECKPOINT_MAGIC:
        raise ValueError("not an NP560N1 NAND checkpoint")
    version, header_size, page_size, _page_oob = struct.unpack_from(
        "<4I", image, 8
    )
    data_size = struct.unpack_from("<Q", image, 32)[0]
    if (
        version != 1
        or header_size != CHECKPOINT_HEADER_SIZE
        or page_size <= 0
        or page_size % SECTOR_SIZE
        or data_size <= 0
        or CHECKPOINT_HEADER_SIZE + data_size > len(image)
    ):
        raise ValueError("unsupported NP560 checkpoint geometry")
    return Geometry(CHECKPOINT_HEADER_SIZE, data_size, page_size)


def swap_adjacent_bytes(data: bytes) -> bytes:
    swapped = bytearray(len(data))
    swapped[0::2] = data[1::2]
    swapped[1::2] = data[0::2]
    return bytes(swapped)


def u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


def u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def fat_bpb(data: bytes) -> dict[str, int] | None:
    if data[510:512] != b"\x55\xAA":
        return None
    bytes_per_sector = u16(data, 0x0B)
    sectors_per_cluster = data[0x0D]
    reserved_sectors = u16(data, 0x0E)
    fat_count = data[0x10]
    root_entries = u16(data, 0x11)
    total_sectors_16 = u16(data, 0x13)
    total_sectors_32 = u32(data, 0x20)
    sectors_per_fat_16 = u16(data, 0x16)
    total_sectors = total_sectors_16 or total_sectors_32
    if (
        bytes_per_sector not in (512, 1024, 2048, 4096)
        or sectors_per_cluster == 0
        or sectors_per_cluster & (sectors_per_cluster - 1)
        or reserved_sectors == 0
        or fat_count not in (1, 2)
        or total_sectors == 0
    ):
        return None
    return {
        "bytes_per_sector": bytes_per_sector,
        "sectors_per_cluster": sectors_per_cluster,
        "reserved_sectors": reserved_sectors,
        "fat_count": fat_count,
        "root_entries": root_entries,
        "total_sectors": total_sectors,
        "sectors_per_fat_16": sectors_per_fat_16,
        "hidden_sectors": u32(data, 0x1C),
    }


def mbr_partitions(data: bytes) -> list[dict[str, int]]:
    if data[510:512] != b"\x55\xAA":
        return []
    partitions: list[dict[str, int]] = []
    for index in range(4):
        offset = 0x1BE + index * 16
        boot = data[offset]
        part_type = data[offset + 4]
        start_lba = u32(data, offset + 8)
        sectors = u32(data, offset + 12)
        if boot in (0x00, 0x80) and part_type and sectors:
            partitions.append({
                "index": index,
                "boot": boot,
                "type": part_type,
                "start_lba": start_lba,
                "sectors": sectors,
            })
    return partitions


def describe_sector(data: bytes) -> tuple[str, str] | None:
    bpb = fat_bpb(data)
    if bpb:
        fields = " ".join(f"{key}={value}" for key, value in bpb.items())
        return "FAT_BPB", fields
    partitions = mbr_partitions(data)
    if partitions:
        fields = ";".join(
            f"p{part['index']} boot={part['boot']:02x} "
            f"type={part['type']:02x} start={part['start_lba']} "
            f"sectors={part['sectors']}"
            for part in partitions
        )
        return "MBR", fields
    return None


def scan_checkpoint(path: Path) -> int:
    matches = 0
    with path.open("rb") as source:
        image = mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            geometry = checkpoint_geometry(image)
            sector_count = geometry.data_size // SECTOR_SIZE
            print(
                f"IMAGE={path} DATA={geometry.data_size} "
                f"PAGE={geometry.page_size} SECTORS={sector_count}"
            )
            for sector_index in range(sector_count):
                offset = geometry.data_offset + sector_index * SECTOR_SIZE
                physical = image[offset:offset + SECTOR_SIZE]
                for byte_order, candidate in (
                    ("physical", physical),
                    ("guest", swap_adjacent_bytes(physical)),
                ):
                    description = describe_sector(candidate)
                    if not description:
                        continue
                    kind, fields = description
                    page = sector_index * SECTOR_SIZE // geometry.page_size
                    in_page = (
                        sector_index * SECTOR_SIZE % geometry.page_size
                    ) // SECTOR_SIZE
                    print(
                        f"{kind} order={byte_order} page=0x{page:x} "
                        f"page_sector={in_page} data_offset=0x{offset:x} "
                        f"bpb_total16={u16(candidate, 0x13)} "
                        f"bpb_total32={u32(candidate, 0x20)} {fields}"
                    )
                    matches += 1
        finally:
            image.close()
    print(f"MATCHES={matches}")
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoints", type=Path, nargs="+")
    args = parser.parse_args()
    for path in args.checkpoints:
        scan_checkpoint(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
