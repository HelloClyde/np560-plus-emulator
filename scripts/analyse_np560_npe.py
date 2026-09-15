#!/usr/bin/env python3
"""Inspect real NP560 ``NP560 RPG2.1`` game containers.

The parser records only structure demonstrated by the current sample set and
the original guest consumers.  It does not assign meanings to the nine 16-bit
container-header values.  Two payload layouts are now recognised
conservatively: repeated full-screen packed-4bpp candidates and indexed
GB18030 question records.  The stable container facts currently enforced are:

* bytes 0x00..0x0B contain ``NP560 RPG2.1``;
* bytes 0x0C..0x17 are a NUL-terminated, 12-byte GB18030 title field;
* nine big-endian 16-bit values occupy 0x18..0x29;
* a 100-slot big-endian ``{offset, size}`` table starts at 0x3A;
* active descriptors stop at the first zero offset and describe contiguous
  sections which cover the complete file.

This is an offline, read-only analyser.  It never imports a game into guest
storage and does not imply that NPE and NWF share a runtime or container.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


MAGIC = b"NP560 RPG2.1"
TITLE_OFFSET = 0x0C
TITLE_SIZE = 0x0C
VECTOR_OFFSET = 0x18
VECTOR_COUNT = 9
RESERVED_OFFSET = 0x2A
RESERVED_SIZE = 0x0E
FIRST_SECTION_END_OFFSET = 0x38
SECTION_TABLE_OFFSET = 0x3A
SECTION_RECORD_SIZE = 8
SECTION_RECORD_COUNT = 100
SECTION_TABLE_END = SECTION_TABLE_OFFSET + SECTION_RECORD_SIZE * SECTION_RECORD_COUNT
BITMAP_HEADER_SIZE = 10
LCD_WIDTH = 240
LCD_HEIGHT = 120
PACKED4_PAYLOAD_SIZE = LCD_WIDTH * LCD_HEIGHT // 2
PACKED4_RECORD_SIZE = BITMAP_HEADER_SIZE + PACKED4_PAYLOAD_SIZE

DEFAULT_SAMPLE_DIRECTORY = Path(r"D:\Downloads\NP560plus游戏全集")

SIGNATURES: tuple[tuple[str, bytes], ...] = (
    ("NEPLAYER", b"NEPLAYER"),
    ("NOAHAUTH", b"NOAHAUTH"),
    ("NWF-extension", b".nwf"),
    ("ZIP-local-header", b"PK\x03\x04"),
    ("GZIP", b"\x1f\x8b\x08"),
    ("PNG", b"\x89PNG\r\n\x1a\n"),
    ("RIFF", b"RIFF"),
    ("OGG", b"OggS"),
    ("MIDI", b"MThd"),
)


def _u16be(blob: bytes, offset: int) -> int:
    return int.from_bytes(blob[offset:offset + 2], "big")


def _u32be(blob: bytes, offset: int) -> int:
    return int.from_bytes(blob[offset:offset + 4], "big")


def _entropy(blob: bytes) -> float:
    if not blob:
        return 0.0
    counts = [0] * 256
    for value in blob:
        counts[value] += 1
    length = len(blob)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts if count
    )


def _all_offsets(blob: bytes, needle: bytes, limit: int = 32) -> list[int]:
    offsets: list[int] = []
    start = 0
    while len(offsets) < limit:
        offset = blob.find(needle, start)
        if offset < 0:
            break
        offsets.append(offset)
        start = offset + 1
    return offsets


def _packed4_fullscreen_array(payload: bytes) -> dict[str, Any] | None:
    """Recognise the repeated 10-byte + 240x120/2 structural pattern.

    The runtime consumer still decides the final semantics.  This detector only
    reports a layout when every record has the same observed little-endian
    ``{kind, x, y, width, height}`` header and an exactly sized 4-bit payload.
    """
    if not payload or len(payload) % PACKED4_RECORD_SIZE:
        return None
    count = len(payload) // PACKED4_RECORD_SIZE
    headers = [
        payload[index * PACKED4_RECORD_SIZE:
                index * PACKED4_RECORD_SIZE + BITMAP_HEADER_SIZE]
        for index in range(count)
    ]
    fields = [
        tuple(int.from_bytes(header[offset:offset + 2], "little")
              for offset in range(0, BITMAP_HEADER_SIZE, 2))
        for header in headers
    ]
    if any(field != (0x1001, 0, 0, LCD_WIDTH, LCD_HEIGHT)
           for field in fields):
        return None
    return {
        "record_count": count,
        "record_size": PACKED4_RECORD_SIZE,
        "header_size": BITMAP_HEADER_SIZE,
        "payload_size": PACKED4_PAYLOAD_SIZE,
        "kind_u16le": fields[0][0],
        "x": fields[0][1],
        "y": fields[0][2],
        "width": fields[0][3],
        "height": fields[0][4],
        "classification": "structural-packed-4bpp-fullscreen-candidate",
    }


def _indexed_question_records(payload: bytes) -> dict[str, Any] | None:
    """Recognise the category-count + u32-offset quiz database layout."""
    header_size = 2 + 10 * 2
    if len(payload) < header_size + 8:
        return None
    total = _u16be(payload, 0)
    category_counts = [
        _u16be(payload, 2 + index * 2) for index in range(10)
    ]
    if total == 0 or sum(category_counts) != total:
        return None
    table_end = header_size + total * 4
    if table_end + 4 > len(payload):
        return None
    offsets = [
        _u32be(payload, header_size + index * 4) for index in range(total)
    ]
    if (payload[table_end:table_end + 4] != b"\xFF" * 4 or
            offsets[0] != table_end + 4 or offsets[-1] >= len(payload) or
            any(left >= right for left, right in zip(offsets, offsets[1:]))):
        return None
    sample_count = min(total, 32)
    for index in range(sample_count):
        end = offsets[index + 1] if index + 1 < total else len(payload)
        record = payload[offsets[index]:end]
        # Some factory records omit the literal ``A.`` prefix while retaining
        # the first answer directly after the question terminator.  B/C/D are
        # stable across the validated sample records.
        if not all(marker in record for marker in (b"\0B.", b"\0C.", b"\0D.")):
            return None
        text_end = record.find(b"\0", record.find(b"\0D.") + 1)
        if text_end < 0:
            return None
        try:
            record[:text_end].decode("gb18030")
        except UnicodeDecodeError:
            return None
    return {
        "record_count": total,
        "category_counts": category_counts,
        "offset_table_start": header_size,
        "offset_table_end": table_end,
        "sentinel_u32be": 0xFFFFFFFF,
        "first_record_offset": offsets[0],
        "last_record_offset": offsets[-1],
        "sample_records_validated": sample_count,
        "classification": "indexed-gb18030-question-records",
    }


def decode_title(raw: bytes) -> str:
    """Decode the meaningful prefix of the fixed-width NPE title field."""
    encoded = raw.split(b"\0", 1)[0]
    try:
        return encoded.decode("gb18030")
    except UnicodeDecodeError as error:
        raise ValueError(f"invalid GB18030 NPE title: {error}") from error


def _parse_sections(blob: bytes) -> list[tuple[int, int]]:
    sections: list[tuple[int, int]] = []
    saw_unused = False
    for index in range(SECTION_RECORD_COUNT):
        record = SECTION_TABLE_OFFSET + index * SECTION_RECORD_SIZE
        offset = _u32be(blob, record)
        size = _u32be(blob, record + 4)
        if offset == 0:
            saw_unused = True
            continue
        if saw_unused:
            raise ValueError(
                f"active section descriptor {index} follows a zero-offset slot"
            )
        if size == 0:
            raise ValueError(f"active section descriptor {index} has zero size")
        if offset > len(blob) or size > len(blob) - offset:
            raise ValueError(
                f"section {index} range 0x{offset:X}+0x{size:X} exceeds "
                f"file size 0x{len(blob):X}"
            )
        sections.append((offset, size))
    if not sections:
        raise ValueError("NPE section table has no active descriptors")
    return sections


def analyse_blob(blob: bytes, *, name: str = "<memory>") -> dict[str, Any]:
    if len(blob) < SECTION_TABLE_END:
        raise ValueError(
            f"{name}: file is smaller than the 0x{SECTION_TABLE_END:X}-byte header"
        )
    if blob[:len(MAGIC)] != MAGIC:
        raise ValueError(
            f"{name}: magic mismatch: {blob[:len(MAGIC)]!r} != {MAGIC!r}"
        )

    title_raw = blob[TITLE_OFFSET:TITLE_OFFSET + TITLE_SIZE]
    title = decode_title(title_raw)
    vectors = [
        _u16be(blob, VECTOR_OFFSET + index * 2)
        for index in range(VECTOR_COUNT)
    ]
    sections = _parse_sections(blob)

    contiguous = all(
        offset + size == next_offset
        for (offset, size), (next_offset, _next_size)
        in zip(sections, sections[1:])
    )
    covers_file = sections[-1][0] + sections[-1][1] == len(blob)
    begins_after_table = sections[0][0] == SECTION_TABLE_END
    first_section_end = sections[0][0] + sections[0][1]
    end_marker = _u16be(blob, FIRST_SECTION_END_OFFSET)
    marker_matches = first_section_end <= 0xFFFF and end_marker == first_section_end
    vectors_bounded = all(value == 0 or value < first_section_end for value in vectors)

    invariant_errors: list[str] = []
    if not begins_after_table:
        invariant_errors.append(
            f"first section starts at 0x{sections[0][0]:X}, expected 0x{SECTION_TABLE_END:X}"
        )
    if not contiguous:
        invariant_errors.append("active section descriptors are not contiguous")
    if not covers_file:
        invariant_errors.append("active section descriptors do not cover the file")
    if not marker_matches:
        invariant_errors.append(
            f"0x38 marker 0x{end_marker:X} does not match first end 0x{first_section_end:X}"
        )
    if not vectors_bounded:
        invariant_errors.append("one or more header vectors exceed the first section")
    if invariant_errors:
        raise ValueError(f"{name}: " + "; ".join(invariant_errors))

    section_reports: list[dict[str, Any]] = []
    for index, (offset, size) in enumerate(sections):
        payload = blob[offset:offset + size]
        report = {
            "index": index,
            "offset": offset,
            "offset_hex": f"0x{offset:08X}",
            "size": size,
            "size_hex": f"0x{size:08X}",
            "end": offset + size,
            "end_hex": f"0x{offset + size:08X}",
            "sha256": hashlib.sha256(payload).hexdigest().upper(),
            "entropy_bits_per_byte": round(_entropy(payload), 6),
            "prefix_hex": payload[:16].hex(" ").upper(),
        }
        packed4 = _packed4_fullscreen_array(payload)
        if packed4 is not None:
            report["packed4_fullscreen_array"] = packed4
        questions = _indexed_question_records(payload)
        if questions is not None:
            report["indexed_question_records"] = questions
        section_reports.append(report)

    signature_hits = {
        label: [f"0x{offset:08X}" for offset in _all_offsets(blob, signature)]
        for label, signature in SIGNATURES
        if signature in blob
    }
    reserved = blob[RESERVED_OFFSET:RESERVED_OFFSET + RESERVED_SIZE]
    return {
        "name": name,
        "size": len(blob),
        "size_hex": f"0x{len(blob):X}",
        "sha256": hashlib.sha256(blob).hexdigest().upper(),
        "magic": MAGIC.decode("ascii"),
        "title": title,
        "title_raw_hex": title_raw.hex(" ").upper(),
        "header": {
            "title_offset": TITLE_OFFSET,
            "title_bytes": TITLE_SIZE,
            "vectors_u16be": vectors,
            "vectors_hex": [f"0x{value:04X}" for value in vectors],
            "reserved_hex": reserved.hex(" ").upper(),
            "reserved_all_zero": not any(reserved),
            "first_section_end_marker_u16be": end_marker,
            "section_table_offset": SECTION_TABLE_OFFSET,
            "section_record_bytes": SECTION_RECORD_SIZE,
            "section_record_capacity": SECTION_RECORD_COUNT,
            "header_bytes": SECTION_TABLE_END,
        },
        "layout": {
            "active_sections": len(sections),
            "first_section_offset": sections[0][0],
            "first_section_end": first_section_end,
            "begins_immediately_after_descriptor_table": begins_after_table,
            "sections_are_contiguous": contiguous,
            "sections_cover_file": covers_file,
            "first_section_end_marker_matches": marker_matches,
            "header_vectors_are_bounded_by_first_section": vectors_bounded,
        },
        "sections": section_reports,
        "signature_hits": signature_hits,
        "scope": {
            "container_layout_semantics_recovered": False,
            "npe_nwf_relationship_proven": False,
            "guest_loader_abi_recovered": False,
        },
    }


def analyse_file(path: Path) -> dict[str, Any]:
    result = analyse_blob(path.read_bytes(), name=path.name)
    result["path"] = str(path.resolve())
    return result


def _layout_cluster_key(sample: dict[str, Any]) -> tuple[Any, ...]:
    header = sample["header"]
    layout = sample["layout"]
    return (
        tuple(header["vectors_u16be"]),
        layout["active_sections"],
        layout["first_section_offset"],
        layout["first_section_end"],
    )


def analyse_files(paths: Iterable[Path]) -> dict[str, Any]:
    samples = [analyse_file(path) for path in paths]
    if not samples:
        raise ValueError("no .npe input files found")

    layout_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    hash_groups: dict[str, list[str]] = defaultdict(list)
    for sample in samples:
        layout_groups[_layout_cluster_key(sample)].append(sample)
        hash_groups[sample["sha256"]].append(sample["name"])

    clusters: list[dict[str, Any]] = []
    for index, (key, members) in enumerate(
            sorted(layout_groups.items(), key=lambda item: (-len(item[1]), item[0]))):
        vectors, section_count, first_offset, first_end = key
        clusters.append({
            "cluster": index,
            "sample_count": len(members),
            "members": [sample["name"] for sample in members],
            "vectors_u16be": list(vectors),
            "active_sections": section_count,
            "first_section_offset": first_offset,
            "first_section_end": first_end,
        })

    return {
        "schema": "np560-npe-sample-analysis-v1",
        "scope": {
            "claim": "observed structural invariants of supplied NP560 RPG2.1 files",
            "field_semantics_claimed": False,
            "guest_loader_abi_recovered": False,
            "npe_nwf_relationship_proven": False,
        },
        "sample_count": len(samples),
        "unique_file_count": len(hash_groups),
        "layout_cluster_count": len(clusters),
        "layout_clusters": clusters,
        "duplicate_files": [
            {"sha256": digest, "members": members}
            for digest, members in sorted(hash_groups.items())
            if len(members) > 1
        ],
        "samples": samples,
    }


def discover_inputs(inputs: Iterable[Path]) -> list[Path]:
    discovered: list[Path] = []
    for path in inputs:
        if path.is_dir():
            discovered.extend(sorted(path.glob("*.npe"), key=lambda item: item.name))
        elif path.is_file():
            discovered.append(path)
        else:
            raise ValueError(f"input does not exist: {path}")
    unique: dict[str, Path] = {}
    for path in discovered:
        unique[str(path.resolve()).casefold()] = path
    return sorted(unique.values(), key=lambda item: (item.stat().st_size, item.name))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs", nargs="*", type=Path,
        help=".npe files or directories (defaults to the local NP560plus collection)",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    inputs = args.inputs or [DEFAULT_SAMPLE_DIRECTORY]
    result = analyse_files(discover_inputs(inputs))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
