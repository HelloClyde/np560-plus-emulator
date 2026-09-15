#!/usr/bin/env python3
"""Index direct DMCU calls in an NP560 program image.

The upgrade PRG is mapped at source address 20:0000.  A direct SCALL is two
little-endian words: ``BDss pppp`` for target ``ss:pppp``.  This tool keeps
the scan deliberately structural; it does not pretend that every BD-looking
word in resource data is executable.  Its main purpose is to make candidate
discovery fast and reproducible, after which callers are verified with the
recursive disassembler.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_BASE_ADDRESS = 0x200000
SCALL_OPCODE_MASK = 0xFF00
SCALL_OPCODE = 0xBD00
LINK_OPCODE_MASK = 0xFF00
LINK_OPCODE = 0x2E00
RETS_WORD = 0xC620


def format_address(address: int) -> str:
    return f"{address >> 16:02X}:{address & 0xFFFF:04X}"


def parse_address(text: str) -> int:
    if ":" in text:
        segment, offset = text.split(":", 1)
        return (int(segment, 16) << 16) | int(offset, 16)
    return int(text, 0)


def words_from_bytes(data: bytes) -> list[int]:
    usable = len(data) & ~1
    return [int.from_bytes(data[i : i + 2], "little")
            for i in range(0, usable, 2)]


@dataclass(frozen=True)
class DirectCall:
    source_address: int
    target_address: int
    file_offset: int
    next_word: int | None
    cleanup_bytes: int | None

    def json_record(self) -> dict[str, int | str | None]:
        record = asdict(self)
        record["source"] = format_address(self.source_address)
        record["target"] = format_address(self.target_address)
        return record


def decode_stack_cleanup(word: int | None) -> int | None:
    """Decode the common ``ADD R15, #imm4`` word after a call."""
    if word is None or (word & 0xFFF0) != 0x50F0:
        return None
    return word & 0xF


def scan_direct_calls(
    data: bytes, base_address: int = DEFAULT_BASE_ADDRESS
) -> list[DirectCall]:
    words = words_from_bytes(data)
    calls: list[DirectCall] = []
    for index in range(len(words) - 1):
        first = words[index]
        if first & SCALL_OPCODE_MASK != SCALL_OPCODE:
            continue
        file_offset = index * 2
        target = ((first & 0xFF) << 16) | words[index + 1]
        following = words[index + 2] if index + 2 < len(words) else None
        calls.append(
            DirectCall(
                source_address=base_address + file_offset,
                target_address=target,
                file_offset=file_offset,
                next_word=following,
                cleanup_bytes=decode_stack_cleanup(following),
            )
        )
    return calls


def likely_function_starts(
    data: bytes,
    start_address: int,
    end_address: int,
    base_address: int = DEFAULT_BASE_ADDRESS,
) -> list[dict[str, int | str]]:
    """List LINK prologues in a source-address interval.

    These are candidates rather than proven code boundaries.  Keeping that
    distinction in the output prevents resource bytes from silently becoming
    invented functions.
    """
    words = words_from_bytes(data)
    first_offset = max(0, start_address - base_address) & ~1
    last_offset = min(len(data), end_address - base_address) & ~1
    result: list[dict[str, int | str]] = []
    for file_offset in range(first_offset, last_offset, 2):
        word = words[file_offset // 2]
        if word & LINK_OPCODE_MASK == LINK_OPCODE:
            address = base_address + file_offset
            result.append(
                {
                    "address": format_address(address),
                    "source_address": address,
                    "file_offset": file_offset,
                    "frame_words": word & 0xFF,
                }
            )
    return result


def build_report(
    data: bytes,
    *,
    base_address: int = DEFAULT_BASE_ADDRESS,
    target: int | None = None,
    target_segment: int | None = None,
    source_start: int | None = None,
    source_end: int | None = None,
    context_bytes: int = 0,
) -> dict[str, object]:
    all_calls = scan_direct_calls(data, base_address)
    calls: Iterable[DirectCall] = all_calls
    if target is not None:
        calls = (call for call in calls if call.target_address == target)
    if target_segment is not None:
        calls = (call for call in calls
                 if call.target_address >> 16 == target_segment)
    selected = list(calls)

    counts = Counter(call.target_address for call in selected)
    cleanups: dict[int, Counter[int | None]] = defaultdict(Counter)
    for call in selected:
        cleanups[call.target_address][call.cleanup_bytes] += 1

    call_records: list[dict[str, object]] = []
    for call in selected:
        record: dict[str, object] = call.json_record()
        if context_bytes:
            window_start = max(base_address, call.source_address - context_bytes)
            record["preceding_calls"] = [
                prior.json_record()
                for prior in all_calls
                if window_start <= prior.source_address < call.source_address
            ]
        call_records.append(record)

    report: dict[str, object] = {
        "image_bytes": len(data),
        "base_address": base_address,
        "structural_warning": (
            "Candidates are found by word pattern; verify every caller with "
            "the recursive disassembler before assigning semantics."
        ),
        "all_direct_call_candidates": len(all_calls),
        "selected_call_candidates": len(selected),
        "targets": [
            {
                "target": format_address(address),
                "target_address": address,
                "count": count,
                "cleanup_bytes": {
                    ("none" if cleanup is None else str(cleanup)): amount
                    for cleanup, amount in sorted(
                        cleanups[address].items(),
                        key=lambda item: (-1 if item[0] is None else item[0]),
                    )
                },
            }
            for address, count in sorted(counts.items())
        ],
        "context_bytes": context_bytes,
        "calls": call_records,
    }
    if source_start is not None and source_end is not None:
        report["likely_function_starts"] = likely_function_starts(
            data, source_start, source_end, base_address
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--base", type=parse_address,
                        default=DEFAULT_BASE_ADDRESS)
    parser.add_argument("--target", type=parse_address)
    parser.add_argument("--target-segment", type=lambda value: int(value, 16))
    parser.add_argument("--source-range", nargs=2, type=parse_address,
                        metavar=("START", "END"))
    parser.add_argument(
        "--context-bytes", type=lambda value: int(value, 0), default=0,
        help="include structural direct calls in this many bytes before each match",
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    data = args.image.read_bytes()
    source_start = source_end = None
    if args.source_range:
        source_start, source_end = args.source_range
    report = build_report(
        data,
        base_address=args.base,
        target=args.target,
        target_segment=args.target_segment,
        source_start=source_start,
        source_end=source_end,
        context_bytes=args.context_bytes,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json:
        args.json.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
