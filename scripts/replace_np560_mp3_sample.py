#!/usr/bin/env python3
"""Replace the two diagnostic MP3 samples in an offline NP560 checkpoint.

The new track must already have been imported into /MP3 through the offline
file manager. Work on a copy and atomically replace the staged checkpoint only
after FAT, playlist CRC, and track bytes have been verified.
"""

from __future__ import annotations

import argparse
import binascii
from pathlib import Path
import shutil

from web.nand_files import rehash_checkpoint, with_volume


def update(files, track: str, expected: bytes) -> None:
    path = f"/MP3/{track}"
    if files.read_file(path) != expected:
        raise ValueError("导入的歌曲与源文件不一致")
    old = files.read_file("/MP3/PLAYLIST.LST")
    if len(old) != 3074 or old[:6] != b"\0\0\0\0\1\2":
        raise ValueError("未知的 MP3 播放列表格式")
    if binascii.crc_hqx(old[:-2], 0) != int.from_bytes(old[-2:], "big"):
        raise ValueError("原播放列表 CRC 校验失败")
    if not old[6:-2].startswith(b"0:\\MP3\\SAMPLE15.MP3\0"):
        raise ValueError("播放列表已不是预期的测试曲")
    if any(old[25:-2]):
        raise ValueError("播放列表含其他项目，不覆盖用户歌曲")
    new_path = b"0:\\MP3\\" + track.encode("gb18030")
    payload = bytearray(old)
    payload[6:-2] = new_path.ljust(len(payload) - 8, b"\0")
    payload[-2:] = binascii.crc_hqx(payload[:-2], 0).to_bytes(2, "big")
    files.delete_file("/MP3/PLAYLIST.LST")
    files.import_file("/MP3", "PLAYLIST.LST", bytes(payload))
    files.delete_file("/MP3/SAMPLE15.MP3")
    files.delete_file("/TONE440.MP3")
    if files.read_file("/MP3/PLAYLIST.LST") != payload:
        raise ValueError("播放列表回读不一致")
    if files.read_file(path) != expected:
        raise ValueError("歌曲回读不一致")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    checkpoint = args.checkpoint.resolve(strict=True)
    source = args.source.resolve(strict=True)
    track = "伏魔战歌.MP3"
    if source.name.casefold() != track.casefold():
        parser.error(f"源文件必须命名为 {track}")
    temporary = checkpoint.with_name(checkpoint.name + ".music.tmp")
    if temporary.exists():
        parser.error(f"暂存文件已存在：{temporary}")
    try:
        shutil.copyfile(checkpoint, temporary)
        expected = source.read_bytes()
        with_volume(temporary, True, lambda files: update(files, track, expected))
        rehash_checkpoint(temporary)
        temporary.replace(checkpoint)
        print(f"已替换测试曲并更新播放列表：{checkpoint}")
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
