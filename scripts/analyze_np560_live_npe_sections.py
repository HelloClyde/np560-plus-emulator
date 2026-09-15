#!/usr/bin/env python3
"""Locate live NPE section pointers and their DMCU code consumers.

The probe is observer-only.  It reads the Web/QMP data and code views, finds
the firmware's split-word representation of real NPE section offsets, then
looks for two-word instructions whose 16-bit operand names the matching data
slot.  Candidate references still need surrounding-control-flow validation
because DMCU instructions select the physical data bank through DS registers.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import urlopen

try:
    from analyse_np560_npe import _parse_sections
    from np560_disasm import decode
except ModuleNotFoundError:  # imported as scripts.analyze_...
    from .analyse_np560_npe import _parse_sections
    from .np560_disasm import decode


def fetch_memory(endpoint: str, source: str, address: int, size: int) -> bytes:
    query = urlencode({"source": source, "base": hex(address), "size": hex(size)})
    with urlopen(f"{endpoint.rstrip('/')}?{query}", timeout=30) as response:
        state = json.load(response)
    payload = base64.b64decode(state["frame"], validate=True)
    if len(payload) != size:
        raise ValueError(f"Web endpoint returned {len(payload)} bytes, expected {size}")
    return payload


def split_word_le(value: int) -> bytes:
    """Encode R0:R1-style high/low words in the data dump's byte order."""
    return ((value >> 16) & 0xFFFF).to_bytes(2, "little") + \
           (value & 0xFFFF).to_bytes(2, "little")


def find_all(blob: bytes, needle: bytes) -> list[int]:
    offsets: list[int] = []
    cursor = 0
    while True:
        offset = blob.find(needle, cursor)
        if offset < 0:
            return offsets
        offsets.append(offset)
        cursor = offset + 1


def scan_data_segments(
    segments: dict[int, bytes], sections: list[tuple[int, int]],
    *, first_section: int = 13,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for section_index in range(first_section, len(sections)):
        offset, size = sections[section_index]
        pattern = split_word_le(offset)
        for segment, payload in segments.items():
            for pc in find_all(payload, pattern):
                hits.append({
                    "section": section_index,
                    "section_offset": offset,
                    "section_size": size,
                    "data_address": (segment << 16) | pc,
                    "data_segment": segment,
                    "data_pc": pc,
                    "encoding_hex": pattern.hex(),
                })
    return hits


def scan_code_references(
    segments: dict[int, bytes], data_hits: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    slots: dict[int, list[dict[str, Any]]] = {}
    for hit in data_hits:
        slots.setdefault(int(hit["data_pc"]), []).append(hit)
    references: list[dict[str, Any]] = []
    for segment, payload in segments.items():
        words = [
            int.from_bytes(payload[index:index + 2], "little")
            for index in range(0, len(payload) - 1, 2)
        ]
        for extension_index in range(1, len(words)):
            slot_hits = slots.get(words[extension_index])
            if not slot_hits:
                continue
            instruction_index = extension_index - 1
            instruction = decode(words, instruction_index, segment)
            if instruction.size != 2 or len(instruction.words) != 2:
                continue
            operand = words[extension_index]
            if f"0x{operand:04X}" not in instruction.text:
                continue
            for hit in slot_hits:
                references.append({
                    "section": hit["section"],
                    "section_offset": hit["section_offset"],
                    "data_address": hit["data_address"],
                    "code_address": (segment << 16) | (instruction_index * 2),
                    "code_segment": segment,
                    "code_pc": instruction_index * 2,
                    "instruction": instruction.text,
                    "words": [f"0x{word:04X}" for word in instruction.words],
                })
    return references


def segment_range(value: str) -> tuple[int, int]:
    try:
        first_text, last_text = value.split("-", 1)
        first = int(first_text, 0)
        last = int(last_text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("segment range must be FIRST-LAST") from error
    if not 0 <= first <= last <= 0xFF:
        raise argparse.ArgumentTypeError("segment range is outside 00..FF")
    return first, last


def fetch_segments(
    endpoint: str, source: str, bounds: tuple[int, int],
) -> dict[int, bytes]:
    first, last = bounds
    return {
        segment: fetch_memory(endpoint, source, segment << 16, 0x10000)
        for segment in range(first, last + 1)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("npe", type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8801/api/state")
    parser.add_argument("--data-segments", type=segment_range, default=(0x50, 0x53))
    parser.add_argument("--code-segments", type=segment_range, default=(0x0B, 0x3F))
    parser.add_argument("--first-section", type=int, default=13)
    parser.add_argument("--skip-code", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    blob = args.npe.read_bytes()
    sections = _parse_sections(blob)
    if not 0 <= args.first_section < len(sections):
        parser.error("first section is outside the active descriptor table")
    data = fetch_segments(args.endpoint, "data", args.data_segments)
    hits = scan_data_segments(data, sections, first_section=args.first_section)
    code: dict[int, bytes] = {}
    references: list[dict[str, Any]] = []
    if not args.skip_code and hits:
        code = fetch_segments(args.endpoint, "code", args.code_segments)
        references = scan_code_references(code, hits)
    result = {
        "schema": "np560-live-npe-section-consumers-v1",
        "observer_only": True,
        "npe": str(args.npe.resolve()),
        "active_sections": len(sections),
        "first_section": args.first_section,
        "data_segments": list(args.data_segments),
        "code_segments": None if args.skip_code else list(args.code_segments),
        "data_hits": hits,
        "code_references": references,
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"wrote {args.output}")
    print(json.dumps({
        "data_hits": len(hits),
        "sections_with_hits": sorted({hit["section"] for hit in hits}),
        "code_references": len(references),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
