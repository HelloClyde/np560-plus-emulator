#!/usr/bin/env python3
"""Create a diagnostic NP560 NAND checkpoint containing one real NPE game.

This tool operates on a *copy* of an NP560N1 checkpoint.  It follows the FAT16
geometry recovered from the guest-created volume, resolves logical 128-KiB
blocks through the triplicated final-page OOB tag, and updates FAT, directory,
data, sector ECC, programmed-page markers, and tags.  It never writes live
guest RAM or draws a menu.

The importer is deliberately a diagnostic bridge to reach the original NPE
loader sooner.  It is not evidence that the factory PC transfer/USB workflow
has been recovered, and it must not replace that workflow in the final
canonical emulator path.
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
    from .analyse_np560_npe import analyse_blob
    from .analyze_np560_ecc_checkpoint import ECC_OFFSETS, sector_descriptor
except ImportError:  # Direct execution from scripts/.
    from analyse_np560_npe import analyse_blob  # type: ignore
    from analyze_np560_ecc_checkpoint import (  # type: ignore
        ECC_OFFSETS,
        sector_descriptor,
    )


CHECKPOINT_MAGIC = b"NP560N1\0"
HEADER_SIZE = 64
PAGE_DATA = 2048
PAGE_OOB = 64
PAGES_PER_BLOCK = 64
BLOCKS = 4096
SECTOR_SIZE = 512
SECTORS_PER_BLOCK = PAGE_DATA * PAGES_PER_BLOCK // SECTOR_SIZE
DATA_SIZE = PAGE_DATA * PAGES_PER_BLOCK * BLOCKS
OOB_SIZE = PAGE_OOB * PAGES_PER_BLOCK * BLOCKS

TAIL_OFFSET = 58
TAIL_BYTES = 6
PROGRAMMED_PAGE_MARKER_OFFSET = 55
FINAL_PAGE_METADATA = bytes((0x55, 0x00, 0x55, 0x55))

FTL_LBA_BIAS = 0x20
FTL_LANES = (0xC00, 0x800, 0x400, 0x000)
FAT16_EOC = 0xFFFF

DEFAULT_DIRECTORY = "应用程序"
DEFAULT_NPE = Path(r"D:\Downloads\NP560plus游戏全集\英雄传奇.npe")


def pair_swap(data: bytes) -> bytes:
    if len(data) & 1:
        raise ValueError("pair-swapped data must contain complete words")
    result = bytearray(data)
    result[0::2] = data[1::2]
    result[1::2] = data[0::2]
    return bytes(result)


def logical_block_and_sector(lba: int) -> tuple[int, int]:
    if lba < 0:
        raise ValueError("negative logical sector")
    biased = lba + FTL_LBA_BIAS
    return biased // SECTORS_PER_BLOCK, biased % SECTORS_PER_BLOCK


def encode_short_name(stem: str, extension: str = "") -> bytes:
    stem_bytes = stem.encode("gb18030")
    extension_bytes = extension.upper().encode("ascii")
    if not stem_bytes or len(stem_bytes) > 8:
        raise ValueError(
            f"FAT short-name stem {stem!r} needs {len(stem_bytes)} bytes; limit is 8"
        )
    if len(extension_bytes) > 3:
        raise ValueError("FAT short-name extension exceeds three ASCII bytes")
    if any(value in b'\"*+,./:;<=>?[\\]|' for value in stem_bytes):
        raise ValueError("FAT short-name stem contains a reserved byte")
    return stem_bytes.ljust(8, b" ") + extension_bytes.ljust(3, b" ")


def directory_entry(
        short_name: bytes, attribute: int, cluster: int, size: int = 0,
) -> bytes:
    if len(short_name) != 11:
        raise ValueError("FAT short name must be exactly 11 bytes")
    if not 0 <= attribute <= 0xFF:
        raise ValueError("FAT attribute does not fit one byte")
    if not 0 <= cluster <= 0xFFFF:
        raise ValueError("FAT16 cluster does not fit one word")
    if not 0 <= size <= 0xFFFFFFFF:
        raise ValueError("FAT file size does not fit one dword")
    entry = bytearray(32)
    entry[:11] = short_name
    entry[11] = attribute
    struct.pack_into("<H", entry, 26, cluster)
    struct.pack_into("<I", entry, 28, size)
    return bytes(entry)


def dot_entry(name: str, cluster: int) -> bytes:
    if name not in (".", ".."):
        raise ValueError("dot entry name must be '.' or '..'")
    # Match the directory records created by the NP560 guest itself.  The
    # recovered TRASH.CAN cluster uses an eight-byte, space-padded stem, a
    # three-byte NUL extension, and marks both dot records directory + hidden
    # + system.  A conventional 0x10/space-padded FAT entry is not equivalent
    # here: the resident enumerator exposes it as an ordinary first result and
    # never reaches the following NPE record.
    short = name.encode("ascii").ljust(8, b" ") + b"\x00\x00\x00"
    return directory_entry(short, 0x16, cluster)


def parse_bpb(sector: bytes) -> dict[str, int]:
    if len(sector) != SECTOR_SIZE or sector[510:512] != b"\x55\xAA":
        raise ValueError("logical sector 0 is not a signed FAT boot sector")
    values = {
        "bytes_per_sector": struct.unpack_from("<H", sector, 0x0B)[0],
        "sectors_per_cluster": sector[0x0D],
        "reserved_sectors": struct.unpack_from("<H", sector, 0x0E)[0],
        "fat_count": sector[0x10],
        "root_entries": struct.unpack_from("<H", sector, 0x11)[0],
        "total_sectors_16": struct.unpack_from("<H", sector, 0x13)[0],
        "sectors_per_fat": struct.unpack_from("<H", sector, 0x16)[0],
        "total_sectors_32": struct.unpack_from("<I", sector, 0x20)[0],
    }
    total = values["total_sectors_16"] or values["total_sectors_32"]
    sectors_per_cluster = values["sectors_per_cluster"]
    if (
        values["bytes_per_sector"] != SECTOR_SIZE
        or sectors_per_cluster == 0
        or sectors_per_cluster & (sectors_per_cluster - 1)
        or values["reserved_sectors"] == 0
        or values["fat_count"] not in (1, 2)
        or values["root_entries"] == 0
        or values["sectors_per_fat"] == 0
        or total == 0
    ):
        raise ValueError(f"unsupported FAT16 BPB: {values}")
    root_sectors = (
        values["root_entries"] * 32 + SECTOR_SIZE - 1
    ) // SECTOR_SIZE
    root_start = (
        values["reserved_sectors"]
        + values["fat_count"] * values["sectors_per_fat"]
    )
    values.update({
        "total_sectors": total,
        "root_sectors": root_sectors,
        "root_start": root_start,
        "data_start": root_start + root_sectors,
        "cluster_bytes": sectors_per_cluster * SECTOR_SIZE,
    })
    return values


def cluster_lba(layout: dict[str, int], cluster: int) -> int:
    if cluster < 2:
        raise ValueError("FAT16 data clusters start at 2")
    return layout["data_start"] + (
        cluster - 2
    ) * layout["sectors_per_cluster"]


class CheckpointFat16:
    def __init__(self, image: mmap.mmap) -> None:
        self.image = image
        self._validate_geometry()
        self.oob_base = HEADER_SIZE + DATA_SIZE
        self.tag_candidates = self._scan_tags()
        self.mapping: dict[int, int] = {}
        self.allocated_blocks: dict[int, int] = {}
        self._select_boot_mapping()
        self.layout = parse_bpb(self.read_sector(0))

    def _validate_geometry(self) -> None:
        if len(self.image) < HEADER_SIZE or self.image[:8] != CHECKPOINT_MAGIC:
            raise ValueError("not an NP560N1 checkpoint")
        fields = struct.unpack_from("<6I2Q", self.image, 8)
        expected = (
            1, HEADER_SIZE, PAGE_DATA, PAGE_OOB,
            PAGES_PER_BLOCK, BLOCKS, DATA_SIZE, OOB_SIZE,
        )
        if fields != expected or len(self.image) != HEADER_SIZE + DATA_SIZE + OOB_SIZE:
            raise ValueError(f"unsupported NP560 checkpoint geometry: {fields}")

    def _scan_tags(self) -> dict[int, list[int]]:
        result: dict[int, list[int]] = {}
        for block in range(BLOCKS):
            page = block * PAGES_PER_BLOCK + PAGES_PER_BLOCK - 1
            offset = self.oob_base + page * PAGE_OOB + TAIL_OFFSET
            tail = bytes(self.image[offset:offset + TAIL_BYTES])
            if tail == b"\xFF" * TAIL_BYTES:
                continue
            values = struct.unpack("<3H", tail)
            if values[0] != values[1] or values[1] != values[2]:
                raise ValueError(
                    f"physical block 0x{block:03X} has a non-triplicated FTL tail"
                )
            result.setdefault(values[0], []).append(block)
        return result

    def _physical_sector(self, block: int, sector: int) -> bytes:
        offset = (
            HEADER_SIZE + block * PAGES_PER_BLOCK * PAGE_DATA
            + sector * SECTOR_SIZE
        )
        return pair_swap(bytes(self.image[offset:offset + SECTOR_SIZE]))

    def _select_boot_mapping(self) -> None:
        candidates = self.tag_candidates.get(0, [])
        selected: list[int] = []
        for block in candidates:
            try:
                parse_bpb(self._physical_sector(block, FTL_LBA_BIAS))
            except ValueError:
                continue
            selected.append(block)
        if len(selected) != 1:
            raise ValueError(
                f"expected one tag-0 block containing the FAT BPB, got {selected}"
            )
        self.mapping[0] = selected[0]
        for tag, blocks in self.tag_candidates.items():
            if tag == 0:
                continue
            if len(blocks) != 1:
                raise ValueError(f"FTL tag 0x{tag:04X} has duplicate blocks {blocks}")
            self.mapping[tag] = blocks[0]

    def read_sector(self, lba: int) -> bytes:
        tag, sector = logical_block_and_sector(lba)
        block = self.mapping.get(tag)
        if block is None:
            return b"\xFF" * SECTOR_SIZE
        return self._physical_sector(block, sector)

    def _block_is_erased(self, block: int) -> bool:
        data_start = HEADER_SIZE + block * PAGES_PER_BLOCK * PAGE_DATA
        data_end = data_start + PAGES_PER_BLOCK * PAGE_DATA
        oob_start = self.oob_base + block * PAGES_PER_BLOCK * PAGE_OOB
        oob_end = oob_start + PAGES_PER_BLOCK * PAGE_OOB
        return (
            self.image[data_start:data_end] == b"\xFF" * (data_end - data_start)
            and self.image[oob_start:oob_end] == b"\xFF" * (oob_end - oob_start)
        )

    def _allocate_block(self, tag: int) -> int:
        lane = FTL_LANES[tag & 3]
        used = set(self.mapping.values())
        # The first block of each lane is factory/format-reserved even when a
        # particular checkpoint currently leaves it erased.
        for block in range(lane + 1, lane + 0x400):
            if block in used or not self._block_is_erased(block):
                continue
            self.mapping[tag] = block
            self.allocated_blocks[tag] = block
            return block
        raise ValueError(f"no erased physical block remains in lane 0x{lane:03X}")

    def write_sector(self, lba: int, logical: bytes) -> None:
        if len(logical) != SECTOR_SIZE:
            raise ValueError("logical FAT sector must be exactly 512 bytes")
        tag, sector = logical_block_and_sector(lba)
        block = self.mapping.get(tag)
        if block is None:
            block = self._allocate_block(tag)
        page_in_block, sector_in_page = divmod(sector, PAGE_DATA // SECTOR_SIZE)
        page = block * PAGES_PER_BLOCK + page_in_block
        data_offset = (
            HEADER_SIZE + page * PAGE_DATA + sector_in_page * SECTOR_SIZE
        )
        self.image[data_offset:data_offset + SECTOR_SIZE] = pair_swap(logical)
        oob_offset = self.oob_base + page * PAGE_OOB
        descriptor_offset = ECC_OFFSETS[sector_in_page]
        self.image[
            oob_offset + descriptor_offset:oob_offset + descriptor_offset + 8
        ] = sector_descriptor(self.image, data_offset)
        self.image[oob_offset + PROGRAMMED_PAGE_MARKER_OFFSET] = 0

    def finalize_allocations(self) -> None:
        for tag, block in self.allocated_blocks.items():
            page = block * PAGES_PER_BLOCK + PAGES_PER_BLOCK - 1
            oob_offset = self.oob_base + page * PAGE_OOB
            self.image[oob_offset + 54:oob_offset + 58] = FINAL_PAGE_METADATA
            self.image[oob_offset + TAIL_OFFSET:oob_offset + TAIL_OFFSET + 6] = (
                struct.pack("<3H", tag, tag, tag)
            )

    def root_bytes(self) -> bytearray:
        return bytearray(b"".join(
            self.read_sector(self.layout["root_start"] + index)
            for index in range(self.layout["root_sectors"])
        ))

    def write_root_bytes(self, root: bytes) -> None:
        expected = self.layout["root_sectors"] * SECTOR_SIZE
        if len(root) != expected:
            raise ValueError("root directory byte count changed")
        for index in range(self.layout["root_sectors"]):
            start = index * SECTOR_SIZE
            self.write_sector(
                self.layout["root_start"] + index,
                root[start:start + SECTOR_SIZE],
            )

    def read_fat(self, copy_index: int = 0) -> bytearray:
        if not 0 <= copy_index < self.layout["fat_count"]:
            raise ValueError("FAT copy index is out of range")
        start = (
            self.layout["reserved_sectors"]
            + copy_index * self.layout["sectors_per_fat"]
        )
        return bytearray(b"".join(
            self.read_sector(start + index)
            for index in range(self.layout["sectors_per_fat"])
        ))

    def write_fat(self, fat: bytes, copy_index: int) -> None:
        expected = self.layout["sectors_per_fat"] * SECTOR_SIZE
        if len(fat) != expected:
            raise ValueError("FAT byte count changed")
        start = (
            self.layout["reserved_sectors"]
            + copy_index * self.layout["sectors_per_fat"]
        )
        for index in range(self.layout["sectors_per_fat"]):
            offset = index * SECTOR_SIZE
            original = self.read_sector(start + index)
            updated = fat[offset:offset + SECTOR_SIZE]
            if updated != original:
                self.write_sector(start + index, updated)


def _find_entry(directory: bytes, short_name: bytes) -> int | None:
    for offset in range(0, len(directory), 32):
        entry = directory[offset:offset + 32]
        if entry[0] == 0:
            return None
        if entry[0] != 0xE5 and entry[11] != 0x0F and entry[:11] == short_name:
            return offset
    return None


def _free_entry(directory: bytes) -> int:
    for offset in range(0, len(directory), 32):
        if directory[offset] in (0x00, 0xE5):
            return offset
    raise ValueError("FAT directory has no free entry")


def _free_clusters(fat: bytes, count: int, *, minimum: int = 2) -> list[int]:
    result: list[int] = []
    for cluster in range(minimum, len(fat) // 2):
        if struct.unpack_from("<H", fat, cluster * 2)[0] == 0:
            result.append(cluster)
            if len(result) == count:
                return result
    raise ValueError(f"FAT contains fewer than {count} free clusters")


def _read_cluster(volume: CheckpointFat16, cluster: int) -> bytes:
    lba = cluster_lba(volume.layout, cluster)
    return b"".join(
        volume.read_sector(lba + index)
        for index in range(volume.layout["sectors_per_cluster"])
    )


def _read_file_chain(
        volume: CheckpointFat16, fat: bytes, first_cluster: int, size: int,
) -> tuple[bytes, list[int]]:
    if size < 0:
        raise ValueError("negative FAT file size")
    if size == 0:
        return b"", []
    cluster = first_cluster
    visited: list[int] = []
    seen: set[int] = set()
    payload = bytearray()
    while len(payload) < size:
        if cluster < 2 or cluster >= len(fat) // 2:
            raise ValueError(f"FAT chain references invalid cluster {cluster}")
        if cluster in seen:
            raise ValueError(f"FAT chain loops at cluster {cluster}")
        seen.add(cluster)
        visited.append(cluster)
        payload.extend(_read_cluster(volume, cluster))
        following = struct.unpack_from("<H", fat, cluster * 2)[0]
        if len(payload) >= size:
            if following < 0xFFF8:
                raise ValueError(
                    f"FAT chain continues to {following} after declared file size"
                )
            break
        if following >= 0xFFF8:
            raise ValueError("FAT chain ends before the declared file size")
        if following == 0:
            raise ValueError("FAT chain enters a free cluster")
        cluster = following
    return bytes(payload[:size]), visited


def verify_game(
        volume: CheckpointFat16, *, directory: str, game_stem: str,
        expected_blob: bytes,
) -> dict[str, Any]:
    root_name = encode_short_name(directory)
    game_name = encode_short_name(game_stem, "NPE")
    root = volume.root_bytes()
    root_offset = _find_entry(root, root_name)
    if root_offset is None:
        raise ValueError("imported application directory is absent on readback")
    root_entry = root[root_offset:root_offset + 32]
    if not root_entry[11] & 0x10:
        raise ValueError("imported application entry is not marked as a directory")
    directory_cluster = struct.unpack_from("<H", root_entry, 26)[0]
    directory_blob = _read_cluster(volume, directory_cluster)
    game_offset = _find_entry(directory_blob, game_name)
    if game_offset is None:
        raise ValueError("imported NPE entry is absent on readback")
    game_entry = directory_blob[game_offset:game_offset + 32]
    if game_entry[11] & 0x10:
        raise ValueError("imported NPE entry is marked as a directory")
    first_cluster = struct.unpack_from("<H", game_entry, 26)[0]
    size = struct.unpack_from("<I", game_entry, 28)[0]
    fat = volume.read_fat(0)
    reconstructed, clusters = _read_file_chain(
        volume, fat, first_cluster, size,
    )
    expected_sha256 = hashlib.sha256(expected_blob).hexdigest().upper()
    actual_sha256 = hashlib.sha256(reconstructed).hexdigest().upper()
    if reconstructed != expected_blob:
        raise ValueError(
            f"NPE readback mismatch: {actual_sha256} != {expected_sha256}"
        )
    return {
        "directory_cluster": directory_cluster,
        "game_first_cluster": first_cluster,
        "game_cluster_count": len(clusters),
        "game_final_cluster": clusters[-1],
        "game_size": size,
        "game_sha256": actual_sha256,
        "byte_exact": True,
    }


def inject_game(
        volume: CheckpointFat16, npe_blob: bytes, *, directory: str, game_stem: str,
        include_dot_entries: bool = True,
) -> dict[str, Any]:
    root_name = encode_short_name(directory)
    game_name = encode_short_name(game_stem, "NPE")
    root = volume.root_bytes()
    if _find_entry(root, root_name) is not None:
        raise ValueError(f"root directory already contains {directory!r}")

    fat = volume.read_fat(0)
    other_fat = volume.read_fat(1) if volume.layout["fat_count"] > 1 else fat
    if fat != other_fat:
        raise ValueError("the two FAT16 copies differ before import")

    file_clusters_needed = (
        len(npe_blob) + volume.layout["cluster_bytes"] - 1
    ) // volume.layout["cluster_bytes"]
    allocated = _free_clusters(fat, 1 + file_clusters_needed, minimum=2)
    directory_cluster = allocated[0]
    file_clusters = allocated[1:]

    struct.pack_into("<H", fat, directory_cluster * 2, FAT16_EOC)
    for current, following in zip(file_clusters, file_clusters[1:]):
        struct.pack_into("<H", fat, current * 2, following)
    struct.pack_into("<H", fat, file_clusters[-1] * 2, FAT16_EOC)
    for copy_index in range(volume.layout["fat_count"]):
        volume.write_fat(fat, copy_index)

    root_offset = _free_entry(root)
    root[root_offset:root_offset + 32] = directory_entry(
        root_name, 0x10, directory_cluster,
    )
    volume.write_root_bytes(root)

    directory_data = bytearray(volume.layout["cluster_bytes"])
    game_offset = 0
    if include_dot_entries:
        directory_data[0:32] = dot_entry(".", directory_cluster)
        directory_data[32:64] = dot_entry("..", 0)
        game_offset = 64
    directory_data[game_offset:game_offset + 32] = directory_entry(
        game_name, 0x20, file_clusters[0], len(npe_blob),
    )
    directory_lba = cluster_lba(volume.layout, directory_cluster)
    for index in range(volume.layout["sectors_per_cluster"]):
        start = index * SECTOR_SIZE
        volume.write_sector(
            directory_lba + index,
            directory_data[start:start + SECTOR_SIZE],
        )

    padded = npe_blob.ljust(
        len(file_clusters) * volume.layout["cluster_bytes"], b"\0",
    )
    for cluster_index, cluster in enumerate(file_clusters):
        source = cluster_index * volume.layout["cluster_bytes"]
        lba = cluster_lba(volume.layout, cluster)
        for sector_index in range(volume.layout["sectors_per_cluster"]):
            offset = source + sector_index * SECTOR_SIZE
            volume.write_sector(
                lba + sector_index,
                padded[offset:offset + SECTOR_SIZE],
            )
    volume.finalize_allocations()

    return {
        "directory": directory,
        "directory_short_name_hex": root_name.hex(" ").upper(),
        "directory_cluster": directory_cluster,
        "game_stem": game_stem,
        "game_short_name_hex": game_name.hex(" ").upper(),
        "game_size": len(npe_blob),
        "game_sha256": hashlib.sha256(npe_blob).hexdigest().upper(),
        "game_first_cluster": file_clusters[0],
        "game_cluster_count": len(file_clusters),
        "game_final_cluster": file_clusters[-1],
        "directory_layout": (
            "guest-dot-records" if include_dot_entries else "diagnostic-game-only"
        ),
        "allocated_ftl_blocks": {
            f"0x{tag:04X}": f"0x{block:04X}"
            for tag, block in sorted(volume.allocated_blocks.items())
        },
        "fat16": volume.layout,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_checkpoint", type=Path)
    parser.add_argument("destination_checkpoint", type=Path)
    parser.add_argument("--npe", type=Path, default=DEFAULT_NPE)
    parser.add_argument("--directory", default=DEFAULT_DIRECTORY)
    parser.add_argument("--game-name", help="8-byte GB18030 FAT stem; defaults to file stem")
    parser.add_argument(
        "--omit-dot-entries",
        action="store_true",
        help=(
            "diagnostic A/B only: put the NPE record first so resident "
            "enumeration can be isolated from dot-record handling"
        ),
    )
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    source = args.source_checkpoint.resolve()
    destination = args.destination_checkpoint.resolve()
    if source == destination:
        raise ValueError("diagnostic importer requires a distinct destination checkpoint")
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(destination)
    npe_blob = args.npe.read_bytes()
    npe_report = analyse_blob(npe_blob, name=args.npe.name)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    try:
        with destination.open("r+b") as target:
            image = mmap.mmap(target.fileno(), 0)
            try:
                volume = CheckpointFat16(image)
                report = inject_game(
                    volume,
                    npe_blob,
                    directory=args.directory,
                    game_stem=args.game_name or args.npe.stem,
                    include_dot_entries=not args.omit_dot_entries,
                )
                report["readback"] = verify_game(
                    volume,
                    directory=args.directory,
                    game_stem=args.game_name or args.npe.stem,
                    expected_blob=npe_blob,
                )
                image[48:56] = b"\0" * 8
                image.flush()
            finally:
                image.close()
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    result = {
        "schema": "np560-npe-fat16-diagnostic-import-v1",
        "scope": {
            "diagnostic_only": True,
            "factory_usb_import_recovered": False,
            "live_guest_memory_modified": False,
            "guest_menu_or_framebuffer_modified": False,
            "checkpoint_rehash_required": True,
        },
        "source_checkpoint": str(source),
        "destination_checkpoint": str(destination),
        "npe": {
            "path": str(args.npe.resolve()),
            "title": npe_report["title"],
            "container_magic": npe_report["magic"],
            "active_sections": npe_report["layout"]["active_sections"],
        },
        "import": report,
    }
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("REHASH_REQUIRED=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
