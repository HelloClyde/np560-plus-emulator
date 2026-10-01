#!/usr/bin/env python3
"""Compare final programmed NP560 NAND pages from two journals of one seed.

This is a read-only forensic aid. QEMU remains the integrity authority: this
script checks record structure and the common base identity, but not CRC32C.
Only pages programmed by at least one journal are materialized, so widespread
boot-time erases do not allocate another full NAND image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import struct
from collections import Counter
from pathlib import Path


RECORD = struct.Struct("<4sIQIIII")
HEADER_SIZE = 64
ERASE = 3
PROGRAM = 1
OOB = 2


def parse_journal(path: Path) -> tuple[bytes, list[tuple[int, int, int, bytes]]]:
    raw = path.read_bytes()
    if len(raw) < HEADER_SIZE or raw[:8] != b"NP560J1\0":
        raise ValueError(f"{path}: invalid NP560 journal header")
    geometry = struct.unpack_from("<5I", raw, 8)
    version, data_size, oob_size, pages, block_pages = geometry
    if version != 1 or not all((data_size, oob_size, pages, block_pages)):
        raise ValueError(f"{path}: invalid journal geometry")
    records = []
    offset = HEADER_SIZE
    expected_sequence = 1
    while offset < len(raw):
        if len(raw) - offset < RECORD.size:
            raise ValueError(f"{path}: torn record header at {offset}")
        magic, op, sequence, page, column, length, _crc = RECORD.unpack_from(
            raw, offset
        )
        offset += RECORD.size
        if (magic != b"NJR1" or sequence != expected_sequence or
                op not in (PROGRAM, OOB, ERASE) or page >= pages or
                length > data_size + oob_size or
                offset + length > len(raw)):
            raise ValueError(f"{path}: invalid record {expected_sequence}")
        if op == ERASE and (length or column or page % block_pages):
            raise ValueError(f"{path}: invalid erase {expected_sequence}")
        if op == PROGRAM and column + length > data_size + oob_size:
            raise ValueError(f"{path}: invalid program {expected_sequence}")
        if op == OOB and (column < data_size or
                          column - data_size + length > 4 * oob_size or
                          page * oob_size + column - data_size + length >
                          pages * oob_size):
            raise ValueError(f"{path}: invalid OOB {expected_sequence}")
        records.append((op, page, column, raw[offset:offset + length]))
        offset += length
        expected_sequence += 1
    return raw[:HEADER_SIZE], records


def candidate_pages(
    records: list[tuple[int, int, int, bytes]], data_size: int,
    oob_size: int,
) -> set[int]:
    result = set()
    for op, page, column, payload in records:
        if op == PROGRAM:
            result.add(page)
        elif op == OOB and payload:
            first = page + (column - data_size) // oob_size
            last = page + (column - data_size + len(payload) - 1) // oob_size
            result.update(range(first, last + 1))
    return result


def replay_selected(
    base: mmap.mmap, records: list[tuple[int, int, int, bytes]],
    selected: set[int], data_size: int, oob_size: int, pages: int,
    block_pages: int,
) -> dict[int, bytearray]:
    plane = pages * data_size
    result = {
        page: bytearray(base[HEADER_SIZE + page * data_size:
                             HEADER_SIZE + (page + 1) * data_size] +
                        base[HEADER_SIZE + plane + page * oob_size:
                             HEADER_SIZE + plane + (page + 1) * oob_size])
        for page in selected
    }
    selected_blocks: dict[int, list[int]] = {}
    for page in selected:
        selected_blocks.setdefault(page // block_pages, []).append(page)
    for op, page, column, payload in records:
        if op == ERASE:
            for target in selected_blocks.get(page // block_pages, ()):
                result[target][:] = b"\xff" * (data_size + oob_size)
        elif op == PROGRAM and page in result:
            target = result[page]
            for i, value in enumerate(payload):
                target[column + i] &= value
        elif op == OOB:
            start = page * oob_size + column - data_size
            for i, value in enumerate(payload):
                target_page, target_column = divmod(start + i, oob_size)
                if target_page in result:
                    result[target_page][data_size + target_column] &= value
    return result


def compare_tagged_block(
    base: mmap.mmap, first_records: list[tuple[int, int, int, bytes]],
    second_records: list[tuple[int, int, int, bytes]], data_size: int,
    oob_size: int, pages: int, block_pages: int, tag: int,
) -> dict:
    """Align one unique FTL tail tag across physical block relocation."""
    if not 0 <= tag <= 0xffff or oob_size < 64:
        raise ValueError("FTL tag must fit 16 bits and OOB must have 64 bytes")
    last_pages = {block * block_pages + block_pages - 1
                  for block in range(pages // block_pages)}
    tail = struct.pack("<H", tag) * 3
    matches = []
    for records in (first_records, second_records):
        endings = replay_selected(base, records, last_pages, data_size,
                                  oob_size, pages, block_pages)
        matches.append(sorted(page // block_pages for page, raw in endings.items()
                              if raw[data_size + 58:data_size + 64] == tail))
    if any(len(found) != 1 for found in matches):
        raise ValueError(f"FTL tag 0x{tag:04x} is not unique: {matches}")
    selected = {block * block_pages + index for found in matches
                for block in found for index in range(block_pages)}
    first = replay_selected(base, first_records, selected, data_size,
                            oob_size, pages, block_pages)
    second = replay_selected(base, second_records, selected, data_size,
                             oob_size, pages, block_pages)
    differences = []
    for index in range(block_pages):
        left = first[matches[0][0] * block_pages + index]
        right = second[matches[1][0] * block_pages + index]
        for column, (a, b) in enumerate(zip(left[:data_size], right[:data_size])):
            if a != b:
                differences.append({"page_in_block": index, "column": column,
                                    "first": a, "second": b})
    return {"tag": tag, "physical_blocks": [found[0] for found in matches],
            "data_differences": differences}


def compare(base_path: Path, first_path: Path, second_path: Path,
            *, tag: int | None = None) -> dict:
    first_header, first_records = parse_journal(first_path)
    second_header, second_records = parse_journal(second_path)
    if first_header != second_header:
        raise ValueError("journals have different NAND geometry or base SHA-256")
    _version, data_size, oob_size, pages, block_pages = struct.unpack_from(
        "<5I", first_header, 8
    )
    selected = (candidate_pages(first_records, data_size, oob_size) |
                candidate_pages(second_records, data_size, oob_size))
    with base_path.open("rb") as stream:
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as base:
            expected = HEADER_SIZE + pages * (data_size + oob_size)
            if len(base) != expected or base[:8] != b"NP560N1\0":
                raise ValueError("base is not a matching-sized NP560 checkpoint")
            if hashlib.sha256(memoryview(base)[HEADER_SIZE:]).digest() != \
                    first_header[32:64]:
                raise ValueError("checkpoint content does not match journal base SHA-256")
            first = replay_selected(base, first_records, selected, data_size,
                                    oob_size, pages, block_pages)
            second = replay_selected(base, second_records, selected, data_size,
                                     oob_size, pages, block_pages)
            tagged = (compare_tagged_block(base, first_records, second_records,
                                          data_size, oob_size, pages,
                                          block_pages, tag)
                      if tag is not None else None)
    differences = []
    for page in sorted(selected):
        left, right = first[page], second[page]
        if left == right:
            continue
        positions = [i for i, (a, b) in enumerate(zip(left, right)) if a != b]
        differences.append({
            "page": page,
            "block": page // block_pages,
            "different_bytes": len(positions),
            "first_column": positions[0],
            "first_values": [left[positions[0]], right[positions[0]]],
            "first_sha256": hashlib.sha256(left).hexdigest(),
            "second_sha256": hashlib.sha256(right).hexdigest(),
        })
    report = {
        "schema": "np560-journal-programmed-page-compare-v1",
        "scope": "union of programmed/OOB pages only; CRC32C not rechecked",
        "base": str(base_path),
        "first": str(first_path),
        "second": str(second_path),
        "base_sha256_from_journals": first_header[32:64].hex(),
        "records": [len(first_records), len(second_records)],
        "operations": [dict(Counter(r[0] for r in records))
                       for records in (first_records, second_records)],
        "selected_pages": len(selected),
        "different_pages": len(differences),
        "differences": differences,
    }
    if tagged is not None:
        report["tag_alignment"] = tagged
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tag", type=lambda value: int(value, 0),
                        help="align a unique 16-bit FTL tail tag across journals")
    args = parser.parse_args()
    report = compare(args.base, args.first, args.second, tag=args.tag)
    if args.output:
        if args.output.exists():
            parser.error("refusing to overwrite existing report")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items()
                      if key != "differences"}, ensure_ascii=False, indent=2))
    print("first differing pages:", [
        (item["page"], item["different_bytes"], item["first_column"])
        for item in report["differences"][:20]
    ])


if __name__ == "__main__":
    main()
