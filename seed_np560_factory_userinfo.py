#!/usr/bin/env python3
"""Seed a complete factory-compatible USERINFO.SYS in an NP560 checkpoint.

The recovered factory filesystem has a FAT-compatible root directory in
physical NAND page ``0x20037``.  Its first entry is ``TRASH.CAN`` and the next
slot is the zero end marker.  During first boot the application tries to
create ``LIRT.NWF`` and recursively opens ``USERINFO.SYS`` while committing
metadata.  With no factory USERINFO entry, that recursion exhausts the five
temporary file-root objects and returns FFF6 before any file data is written.

The exact guest validator consumes 0x444 data bytes followed by a little-endian
CRC16-CCITT word.  The factory FAT16 volume uses 8-KiB clusters; TRASH.CAN owns
cluster 2 and cluster 3 is free in the recovered image.  This utility installs
the USERINFO short entry, marks cluster 3 EOC in both FAT copies, writes a
minimal valid V1.0 record, refreshes every affected NAND-sector ECC descriptor,
and invalidates the checkpoint hashes.  Run ``np560_checkpoint_rehash`` on the
output before booting it.
"""

from __future__ import annotations

import argparse
import mmap
import shutil
import struct
from pathlib import Path

from analyze_np560_ecc_checkpoint import ECC_OFFSETS, sector_descriptor
from seed_np560_factory_selector import (
    HEADER_SIZE,
    PAGE_DATA,
    PAGE_OOB,
    PROGRAMMED_PAGE_MARKER_OFFSET,
    _validate_geometry,
)


FAT_PHYSICAL_BLOCK = 0xC00
FAT1_PHYSICAL_PAGE = FAT_PHYSICAL_BLOCK * 64 + 0x08
FAT2_PHYSICAL_PAGE = FAT_PHYSICAL_BLOCK * 64 + 0x3F
FAT1_ENTRY_OFFSET = 0x206
FAT2_ENTRY_OFFSET = 0x606
ROOT_PHYSICAL_PAGE = 0x20037
ROOT_DIRECTORY_OFFSET = 0x200
USERINFO_ENTRY_OFFSET = ROOT_DIRECTORY_OFFSET + 0x20
USERINFO_DATA_PHYSICAL_PAGE = 0x10003
USERINFO_DATA_OFFSET = 0x200
USERINFO_CLUSTER = 3
USERINFO_SHORT_NAME = b"USERINFOSYS"
USERINFO_ATTRIBUTE = 0x20
DIRECTORY_ENTRY_SIZE = 0x20
USERINFO_DATA_SIZE = 0x444
USERINFO_FILE_SIZE = USERINFO_DATA_SIZE + 2
USERINFO_VERSION = b"V1.0  \x00"
FAT16_EOC = 0xFFFF


def pair_swap(data: bytes) -> bytes:
    """Translate between physical NAND bytes and guest logical byte order."""
    if len(data) & 1:
        raise ValueError("pair-swapped data must have even length")
    swapped = bytearray(data)
    swapped[0::2] = data[1::2]
    swapped[1::2] = data[0::2]
    return bytes(swapped)


def crc16_ccitt(data: bytes, initial: int = 0) -> int:
    """Match exact guest helpers 32:5ACC and 31:F162 (poly 0x1021)."""
    crc = initial & 0xFFFF
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (
                crc << 1
            ) & 0xFFFF
    return crc


def factory_userinfo_payload() -> bytes:
    """Return a minimal record accepted by the original USERINFO validator."""
    data = bytearray(USERINFO_DATA_SIZE)
    data[:len(USERINFO_VERSION)] = USERINFO_VERSION
    checksum = crc16_ccitt(data)
    return bytes(data) + struct.pack("<H", checksum)


def userinfo_directory_entry() -> bytes:
    """Return the FAT16 short-name entry for the complete seeded file."""
    entry = bytearray(DIRECTORY_ENTRY_SIZE)
    entry[:11] = USERINFO_SHORT_NAME
    entry[11] = USERINFO_ATTRIBUTE
    struct.pack_into("<H", entry, 26, USERINFO_CLUSTER)
    struct.pack_into("<I", entry, 28, USERINFO_FILE_SIZE)
    return bytes(entry)


def page_offsets(page: int, data_size: int) -> tuple[int, int]:
    return (
        HEADER_SIZE + page * PAGE_DATA,
        HEADER_SIZE + data_size + page * PAGE_OOB,
    )


def update_page_sectors(
    image: mmap.mmap, data_size: int, page: int, sectors: set[int],
) -> None:
    data_offset, oob_offset = page_offsets(page, data_size)
    for sector in sorted(sectors):
        descriptor_offset = ECC_OFFSETS[sector]
        sector_offset = data_offset + sector * 512
        image[
            oob_offset + descriptor_offset : oob_offset + descriptor_offset + 8
        ] = sector_descriptor(image, sector_offset)
    image[oob_offset + PROGRAMMED_PAGE_MARKER_OFFSET] = 0x00


def logical_page(image: mmap.mmap, data_size: int, page: int) -> bytearray:
    data_offset, _ = page_offsets(page, data_size)
    return bytearray(pair_swap(bytes(image[data_offset:data_offset + PAGE_DATA])))


def store_logical_page(
    image: mmap.mmap, data_size: int, page: int, content: bytearray,
) -> None:
    data_offset, _ = page_offsets(page, data_size)
    image[data_offset:data_offset + PAGE_DATA] = pair_swap(bytes(content))


def seed_factory_userinfo(image: mmap.mmap, *, force: bool = False) -> None:
    """Install a valid single-cluster USERINFO.SYS and its FAT metadata."""
    data_size, _ = _validate_geometry(image)
    root = logical_page(image, data_size, ROOT_PHYSICAL_PAGE)

    existing = bytes(
        root[
            USERINFO_ENTRY_OFFSET : USERINFO_ENTRY_OFFSET + DIRECTORY_ENTRY_SIZE
        ]
    )
    expected = userinfo_directory_entry()
    if existing != expected:
        zero_seed = bytearray(DIRECTORY_ENTRY_SIZE)
        zero_seed[:11] = USERINFO_SHORT_NAME
        zero_seed[11] = USERINFO_ATTRIBUTE
        if not force and existing not in (
            b"\x00" * DIRECTORY_ENTRY_SIZE, bytes(zero_seed),
        ):
            raise ValueError(
                "factory USERINFO directory slot is occupied; use --force"
            )
        root[
            USERINFO_ENTRY_OFFSET : USERINFO_ENTRY_OFFSET + DIRECTORY_ENTRY_SIZE
        ] = expected
    store_logical_page(image, data_size, ROOT_PHYSICAL_PAGE, root)
    update_page_sectors(
        image, data_size, ROOT_PHYSICAL_PAGE,
        {USERINFO_ENTRY_OFFSET // 512},
    )

    for page, offset in (
        (FAT1_PHYSICAL_PAGE, FAT1_ENTRY_OFFSET),
        (FAT2_PHYSICAL_PAGE, FAT2_ENTRY_OFFSET),
    ):
        fat = logical_page(image, data_size, page)
        existing_fat = struct.unpack_from("<H", fat, offset)[0]
        if not force and existing_fat not in (0, FAT16_EOC):
            raise ValueError(
                f"FAT cluster {USERINFO_CLUSTER} is 0x{existing_fat:04X}; "
                "use --force"
            )
        struct.pack_into("<H", fat, offset, FAT16_EOC)
        store_logical_page(image, data_size, page, fat)
        update_page_sectors(image, data_size, page, {offset // 512})

    payload = factory_userinfo_payload()
    data = logical_page(image, data_size, USERINFO_DATA_PHYSICAL_PAGE)
    existing_data = bytes(
        data[USERINFO_DATA_OFFSET:USERINFO_DATA_OFFSET + len(payload)]
    )
    if not force and existing_data not in (b"\x00" * len(payload), payload):
        raise ValueError("USERINFO cluster data is occupied; use --force")
    data[
        USERINFO_DATA_OFFSET:USERINFO_DATA_OFFSET + len(payload)
    ] = payload
    store_logical_page(image, data_size, USERINFO_DATA_PHYSICAL_PAGE, data)
    first_sector = USERINFO_DATA_OFFSET // 512
    final_sector = (USERINFO_DATA_OFFSET + len(payload) - 1) // 512
    update_page_sectors(
        image, data_size, USERINFO_DATA_PHYSICAL_PAGE,
        set(range(first_sector, final_sector + 1)),
    )

    # Prevent a partially patched file from passing checkpoint validation.
    image[48:56] = b"\x00" * 8
    image.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace a non-empty directory slot",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    destination = args.destination.resolve()
    if source != destination:
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    elif not destination.exists():
        raise FileNotFoundError(destination)

    with destination.open("r+b") as target:
        image = mmap.mmap(target.fileno(), 0)
        try:
            seed_factory_userinfo(image, force=args.force)
        finally:
            image.close()

    print(
        f"USERINFO=SEEDED SHORT={USERINFO_SHORT_NAME.decode('ascii')} "
        f"PHYSICAL_PAGE=0x{ROOT_PHYSICAL_PAGE:X} "
        f"LOGICAL_OFFSET=0x{USERINFO_ENTRY_OFFSET:X} "
        f"CLUSTER={USERINFO_CLUSTER} SIZE=0x{USERINFO_FILE_SIZE:X} "
        f"OUTPUT={destination} REHASH_REQUIRED=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
