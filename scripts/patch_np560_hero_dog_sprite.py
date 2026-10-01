#!/usr/bin/env python3
"""Create an opt-in, two-byte repair of the known Hero Legend NPE sample.

The source file is never modified. This is a game-data compatibility repair,
not an emulated CPU/LCD/ROM behavior. Refuse unknown revisions or layouts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .analyse_np560_npe import _parse_sections
except ImportError:
    from analyse_np560_npe import _parse_sections  # type: ignore


SOURCE_SHA256 = "adea7c7442cefaea1c21ab7442cdd10d7796e7fc1dd3a5b98fd3c1c61dfa8c19"
DOG_RECORD_OFFSET = 0x098B91
DOG_RESOURCE_WORD_OFFSET = DOG_RECORD_OFFSET + 12
DOG_SPRITE_INDEX = 0x571  # game's resource base 0x570 + enemy image number 1
DOG_SPRITE_SHA256 = "189fe95da3d40daea485075f101a4870296bc104b1a3b633a95175e8fddeb180"


def repair_blob(source: bytes) -> bytes:
    actual_sha256 = hashlib.sha256(source).hexdigest()
    if actual_sha256 != SOURCE_SHA256:
        raise ValueError(f"unsupported NPE revision: {actual_sha256}")

    sections = _parse_sections(source)
    index_start, index_size = sections[0]
    bitmap_start, bitmap_size = sections[1]
    enemy_start, enemy_size = sections[4]
    if not (
        enemy_start == 0x9899D
        and enemy_start + 0x1F4 == DOG_RECORD_OFFSET
        and DOG_RECORD_OFFSET + 39 <= enemy_start + enemy_size
        and source[DOG_RECORD_OFFSET:DOG_RECORD_OFFSET + 7]
        == b"\xB4\xF3\xCD\xB7\xC8\xAE\x00"  # 大头犬 + NUL
        and source[DOG_RESOURCE_WORD_OFFSET:DOG_RESOURCE_WORD_OFFSET + 2]
        == b"\xCC\xCC"
        and source[DOG_RECORD_OFFSET + 39 + 12:DOG_RECORD_OFFSET + 39 + 14]
        == b"\x00\x02"
    ):
        raise ValueError("enemy record does not match the verified sample")

    entry = index_start + DOG_SPRITE_INDEX * 8
    if entry + 8 > index_start + index_size:
        raise ValueError("dog sprite index lies outside the resource table")
    bitmap_offset = int.from_bytes(source[entry:entry + 4], "big")
    bitmap_length = int.from_bytes(source[entry + 4:entry + 8], "big")
    if bitmap_offset + bitmap_length > bitmap_size:
        raise ValueError("dog sprite entry lies outside the bitmap section")
    sprite = source[bitmap_start + bitmap_offset:bitmap_start + bitmap_offset + bitmap_length]
    if (
        bitmap_length != 0x3F2
        or sprite[:10] != b"\x01\x10\x00\x00\x00\x00\x28\x00\x32\x00"
        or hashlib.sha256(sprite).hexdigest() != DOG_SPRITE_SHA256
    ):
        raise ValueError("resource 0x571 is not the verified 40x50 dog bitmap")

    repaired = bytearray(source)
    repaired[DOG_RESOURCE_WORD_OFFSET:DOG_RESOURCE_WORD_OFFSET + 2] = b"\x00\x01"
    return bytes(repaired)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    if source == destination:
        raise ValueError("source and destination must differ")
    patched = repair_blob(source.read_bytes())
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        output.write(patched)
    print(json.dumps({
        "source": str(source),
        "destination": str(destination),
        "source_sha256": SOURCE_SHA256,
        "repaired_sha256": hashlib.sha256(patched).hexdigest(),
        "changed_offset": f"0x{DOG_RESOURCE_WORD_OFFSET:X}",
        "from_hex": "cccc",
        "to_hex": "0001",
        "source_unmodified": True,
        "live_emulator_unmodified": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
