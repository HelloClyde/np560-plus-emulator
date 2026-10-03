"""Offline FAT16 file access for a complete NP560N1 NAND checkpoint.

This is a diagnostic file bridge, not an implementation of the factory USB
transfer protocol. Callers must stop QEMU before opening a writable image.
"""

from __future__ import annotations

import hashlib
import mmap
from pathlib import Path
import struct
import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from inject_np560_npe_fat16 import (
    CheckpointFat16, FAT16_EOC, SECTOR_SIZE, _free_clusters,
    cluster_lba, directory_entry, encode_short_name,
)


MAX_IMPORT_BYTES = 64 * 1024 * 1024


def _components(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/") or "\\" in path:
        raise ValueError("NAND 路径必须从 / 开始")
    parts = path.split("/")[1:]
    if parts == [""]:
        return []
    if any(not part or part in (".", "..") or "\x00" in part for part in parts):
        raise ValueError("NAND 路径含有无效目录名")
    return parts


def _display_name(short: bytes) -> str:
    stem = short[:8].rstrip(b" ").decode("gb18030", errors="replace")
    extension = short[8:11].rstrip(b" \x00").decode("ascii", errors="replace")
    return stem + ("." + extension if extension else "")


class FatFiles:
    def __init__(self, volume: CheckpointFat16):
        self.volume = volume
        self.fat = volume.read_fat(0)

    def _chain(self, first: int) -> list[int]:
        if first < 2:
            raise ValueError("FAT 目录或文件的起始簇无效")
        result = []
        seen = set()
        cluster = first
        maximum = min(len(self.fat) // 2, 2 +
                      (self.volume.layout["total_sectors"] -
                       self.volume.layout["data_start"]) //
                      self.volume.layout["sectors_per_cluster"])
        while True:
            if cluster < 2 or cluster >= maximum or cluster in seen:
                raise ValueError("FAT 簇链越界或循环")
            result.append(cluster)
            seen.add(cluster)
            following = struct.unpack_from("<H", self.fat, cluster * 2)[0]
            if following >= 0xFFF8:
                return result
            if following == 0 or following == 0xFFF7:
                raise ValueError("FAT 簇链中断或指向坏簇")
            cluster = following

    def _directory(self, first: int | None) -> tuple[bytearray, list[int]]:
        layout = self.volume.layout
        if first is None:
            lbas = list(range(layout["root_start"],
                              layout["root_start"] + layout["root_sectors"]))
        else:
            lbas = [cluster_lba(layout, cluster) + sector
                    for cluster in self._chain(first)
                    for sector in range(layout["sectors_per_cluster"])]
        return bytearray(b"".join(self.volume.read_sector(lba) for lba in lbas)), lbas

    @staticmethod
    def _entries(raw: bytes):
        for offset in range(0, len(raw), 32):
            entry = raw[offset:offset + 32]
            if entry[0] == 0:
                break
            if entry[0] in (0xE5, 0x2E) or entry[11] in (0x0F, 0x08):
                continue
            yield offset, entry

    def _resolve_dir(self, path: str) -> tuple[bytearray, list[int]]:
        raw, lbas = self._directory(None)
        for part in _components(path):
            found = next((entry for _, entry in self._entries(raw)
                          if _display_name(entry[:11]).casefold() == part.casefold()), None)
            if found is None or not found[11] & 0x10:
                raise FileNotFoundError(f"NAND 目录不存在：{path}")
            raw, lbas = self._directory(struct.unpack_from("<H", found, 26)[0])
        return raw, lbas

    def list_dir(self, path: str) -> list[dict]:
        raw, _ = self._resolve_dir(path)
        return [{"name": _display_name(entry[:11]),
                 "directory": bool(entry[11] & 0x10),
                 "size": struct.unpack_from("<I", entry, 28)[0]}
                for _, entry in self._entries(raw)]

    def read_file(self, path: str) -> bytes:
        parts = _components(path)
        if not parts:
            raise ValueError("请选择文件")
        parent = "/" + "/".join(parts[:-1])
        raw, _ = self._resolve_dir(parent)
        found = next((entry for _, entry in self._entries(raw)
                      if _display_name(entry[:11]).casefold() == parts[-1].casefold()), None)
        if found is None or found[11] & 0x10:
            raise FileNotFoundError(f"NAND 文件不存在：{path}")
        size = struct.unpack_from("<I", found, 28)[0]
        if size == 0:
            return b""
        if size > 128 * 1024 * 1024:
            raise ValueError("文件超过 Web 下载上限 128 MiB")
        first = struct.unpack_from("<H", found, 26)[0]
        clusters = self._chain(first)
        cluster_bytes = self.volume.layout["cluster_bytes"]
        if len(clusters) != (size + cluster_bytes - 1) // cluster_bytes:
            raise ValueError("文件大小与 FAT 簇链不一致")
        return b"".join(self.volume.read_sector(cluster_lba(self.volume.layout, cluster) + sector)
                        for cluster in clusters
                        for sector in range(self.volume.layout["sectors_per_cluster"]))[:size]

    def import_file(self, directory: str, filename: str, payload: bytes) -> dict:
        if len(payload) > MAX_IMPORT_BYTES:
            raise ValueError("导入文件超过 64 MiB")
        if not filename or filename in (".", "..") or "/" in filename or "\\" in filename:
            raise ValueError("文件名无效")
        stem, dot, extension = filename.rpartition(".")
        if not dot:
            stem, extension = filename, ""
        short = encode_short_name(stem.upper(), extension)
        raw, lbas = self._resolve_dir(directory)
        if any(entry[:11].upper() == short.upper() for _, entry in self._entries(raw)):
            raise FileExistsError("同名文件已存在；首版不覆盖原文件")
        slot = next((offset for offset in range(0, len(raw), 32)
                     if raw[offset] in (0, 0xE5)), None)
        if slot is None:
            raise ValueError("目录已满；首版不扩容目录")
        if self.volume.layout["fat_count"] > 1 and self.fat != self.volume.read_fat(1):
            raise ValueError("FAT 副本不一致，拒绝写入")
        cluster_bytes = self.volume.layout["cluster_bytes"]
        needed = (len(payload) + cluster_bytes - 1) // cluster_bytes
        clusters = _free_clusters(self.fat, needed) if needed else []
        for index, cluster in enumerate(clusters):
            struct.pack_into("<H", self.fat, cluster * 2,
                             clusters[index + 1] if index + 1 < needed else FAT16_EOC)
        for copy in range(self.volume.layout["fat_count"]):
            self.volume.write_fat(self.fat, copy)
        for index, cluster in enumerate(clusters):
            chunk = payload[index * cluster_bytes:(index + 1) * cluster_bytes].ljust(cluster_bytes, b"\0")
            start = cluster_lba(self.volume.layout, cluster)
            for sector in range(self.volume.layout["sectors_per_cluster"]):
                pos = sector * SECTOR_SIZE
                self.volume.write_sector(start + sector, chunk[pos:pos + SECTOR_SIZE])
        raw[slot:slot + 32] = directory_entry(short, 0x20, clusters[0] if clusters else 0,
                                               len(payload))
        sector_index = slot // SECTOR_SIZE
        start = sector_index * SECTOR_SIZE
        self.volume.write_sector(lbas[sector_index], raw[start:start + SECTOR_SIZE])
        self.volume.finalize_allocations()
        name = _display_name(short)
        path = directory.rstrip("/") + "/" + name
        if self.read_file(path) != payload:
            raise ValueError("NAND 导入后逐字节校验失败")
        return {"path": path, "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest()}

    def delete_file(self, path: str) -> None:
        parts = _components(path)
        if not parts:
            raise ValueError("请选择文件")
        parent = "/" + "/".join(parts[:-1])
        raw, lbas = self._resolve_dir(parent)
        found = next(((offset, entry) for offset, entry in self._entries(raw)
                      if _display_name(entry[:11]).casefold() == parts[-1].casefold()), None)
        if found is None or found[1][11] & 0x10:
            raise FileNotFoundError(f"NAND 文件不存在：{path}")
        if self.volume.layout["fat_count"] > 1 and self.fat != self.volume.read_fat(1):
            raise ValueError("FAT 副本不一致，拒绝写入")
        offset, entry = found
        size = struct.unpack_from("<I", entry, 28)[0]
        first = struct.unpack_from("<H", entry, 26)[0]
        clusters = self._chain(first) if size else []
        cluster_bytes = self.volume.layout["cluster_bytes"]
        if len(clusters) != (size + cluster_bytes - 1) // cluster_bytes:
            raise ValueError("文件大小与 FAT 簇链不一致")
        for cluster in clusters:
            struct.pack_into("<H", self.fat, cluster * 2, 0)
        for copy in range(self.volume.layout["fat_count"]):
            self.volume.write_fat(self.fat, copy)
        raw[offset] = 0xE5
        sector_index = offset // SECTOR_SIZE
        start = sector_index * SECTOR_SIZE
        self.volume.write_sector(lbas[sector_index], raw[start:start + SECTOR_SIZE])
        self.volume.finalize_allocations()


def with_volume(path: Path, writable: bool, action):
    with path.open("r+b" if writable else "rb") as stream:
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_WRITE if writable else mmap.ACCESS_READ) as image:
            volume = CheckpointFat16(image)
            result = action(FatFiles(volume))
            if writable:
                image.flush()
            return result


def rehash_checkpoint(path: Path) -> None:
    """Streaming FNV-1a fallback; no compiler or external package required."""
    with path.open("r+b") as stream:
        header = stream.read(64)
        if header[:8] != b"NP560N1\0" or len(header) != 64:
            raise ValueError("不是 NP560 NAND 检查点")
        data_size, oob_size = struct.unpack_from("<2Q", header, 32)
        if path.stat().st_size != 64 + data_size + oob_size:
            raise ValueError("NAND 检查点长度错误")
        hashes = []
        for length in (data_size, oob_size):
            value = 2166136261
            remaining = length
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("NAND 检查点被截断")
                for byte in chunk:
                    value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
                remaining -= len(chunk)
            hashes.append(value)
        stream.seek(48)
        stream.write(struct.pack("<2I", *hashes))
        stream.flush()
