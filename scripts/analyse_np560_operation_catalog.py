#!/usr/bin/env python3
"""Recover the NP560+ file-browser operation catalogue from V3.80.

This pins the original guest-code chain which distinguishes ``游戏世界``
from ``动漫欣赏``:

* catalogue item 0x78 dispatches to the operation-1 wrapper;
* operation 1 scans ``0:\\应用程序`` with ``\\*.npe``;
* catalogue item 0x79 dispatches to the operation-0 wrapper;
* operation 0 scans ``0:\\动漫欣赏`` with ``\\*.nwf``.

The result deliberately does not infer that NPE and NWF have the same file
format.  That relationship must be proven from an original game sample or
from the selected-file launch path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from .analyse_np560_app_catalog import (
        DEFAULT_PROGRAM,
        PROGRAM_BASE,
        catalogue_entries,
        words,
    )
except ImportError:  # Direct execution from scripts/.
    from analyse_np560_app_catalog import (  # type: ignore
        DEFAULT_PROGRAM,
        PROGRAM_BASE,
        catalogue_entries,
        words,
    )


RELOCATION_DELTA = 0x1D0000

OPERATION_TABLE_SOURCE = 0x4D0B0C
OPERATION_TABLE_DESTINATION = 0x300B0C
OPERATION_RECORD_WORDS = 7
OPERATION_RECORD_COUNT = 20

STRING_SOURCE_SEGMENT = 0x44
STRING_RUNTIME_SEGMENT = 0x27
STRING_POOL_FIRST_PC = 0xE07E
STRING_POOL_END_PC = 0xE202

DISPATCH_SOURCE = 0x3F3C2A
DISPATCH_DESTINATION = DISPATCH_SOURCE - RELOCATION_DELTA
DISPATCH_WORDS = (
    0x780B, 0x0006,             # application id argument
    0x76F0, 0x0079,             # 动漫欣赏
    0xAC02, 0x3C3E,
    0xBD33, 0x3CE6,             # operation-0 wrapper
    0xAC00, 0x3D10,
    0x780B, 0x0006,
    0x76F0, 0x0078,             # 游戏世界
    0xAC02, 0x3C52,
    0xBD33, 0x3DA6,             # operation-1 wrapper
    0xAC00, 0x3D10,
)

WRAPPER_RUNTIME_SEGMENT = 0x33
WRAPPER_SOURCE_SEGMENT = 0x50
WRAPPER_SIZE = 0x20
WRAPPERS = (
    {
        "name": "animation-browser",
        "application_id": 0x79,
        "catalogue_index": 47,
        "runtime_pc": 0x3CE6,
        "operation_index": 0,
    },
    {
        "name": "game-world-browser",
        "application_id": 0x78,
        "catalogue_index": 46,
        "runtime_pc": 0x3DA6,
        "operation_index": 1,
    },
)

RESIDENT_BROWSER_SOURCE = 0x3823B8
RESIDENT_BROWSER_DESTINATION = 0x1B23B8
SELECTED_LAUNCH_SOURCE = 0x382A88
SELECTED_LAUNCH_DESTINATION = 0x1B2A88
SELECTED_LAUNCH_WORDS = (
    0x6810, 0x00A4,
    0x88F0, 0x5192,
    0x88F1, 0x5194,
    0x58F1, 0x58F0,
    0xBD2E, 0xD34A,
    0x50F4,
)

LAUNCH_SEQUENCE_SOURCE = 0x4BD34A
LAUNCH_SEQUENCE_DESTINATION = 0x2ED34A
LAUNCH_SEQUENCE_SIZE = 0x0164
LAUNCH_SEQUENCE_PROLOGUE = (
    0x2E00, 0x58F0, 0x58F1,
    0xBD33, 0x5090,
    0xBD33, 0x65D4,
    0xBD33, 0x65FC,
    0xBD33, 0x66E2,
    0xBD32, 0xB8D0,
)
LAUNCH_SEQUENCE_EPILOGUE = (0x381F, 0x380F, 0x2F00, 0xC620)


def address_text(address: int) -> str:
    return f"{address >> 16:02X}:{address & 0xFFFF:04X}"


def _expect_words(
    program: bytes,
    address: int,
    expected: tuple[int, ...] | list[int],
    description: str,
) -> None:
    actual = words(program, address, len(expected))
    if actual != list(expected):
        raise ValueError(
            f"{description} mismatch at {address_text(address)}: "
            f"expected {list(expected)!r}, got {actual!r}"
        )


def decode_operation_string(program: bytes, segment: int, pc: int) -> str:
    """Decode one word-lane GB18030 string referenced by the operation table."""
    if segment != STRING_RUNTIME_SEGMENT:
        raise ValueError(
            f"operation string has unexpected segment {segment:02X}:{pc:04X}"
        )
    if not STRING_POOL_FIRST_PC <= pc < STRING_POOL_END_PC:
        raise ValueError(f"operation string pointer is outside pool: {segment:02X}:{pc:04X}")

    source = (STRING_SOURCE_SEGMENT << 16) | pc
    decoded = bytearray()
    for index in range(0, STRING_POOL_END_PC - pc, 2):
        word = words(program, source + index, 1)[0]
        for value in word.to_bytes(2, "big"):
            if value == 0:
                return decoded.decode("gb18030")
            decoded.append(value)
    raise ValueError(f"unterminated operation string at {segment:02X}:{pc:04X}")


def operation_records(program: bytes) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index in range(OPERATION_RECORD_COUNT):
        source = OPERATION_TABLE_SOURCE + index * OPERATION_RECORD_WORDS * 2
        record = words(program, source, OPERATION_RECORD_WORDS)
        selector = record[0]
        pointers = [
            (record[offset], record[offset + 1])
            for offset in (1, 3, 5)
        ]
        decoded = [
            decode_operation_string(program, segment, pc)
            for segment, pc in pointers
        ]
        result.append({
            "index": index,
            "source": address_text(source),
            "destination": address_text(source - RELOCATION_DELTA),
            "selector": selector,
            "directory": decoded[0],
            "filter": decoded[1],
            "auxiliary": decoded[2],
            "pointers": [f"{segment:02X}:{pc:04X}" for segment, pc in pointers],
        })
    return result


def _wrapper_signature(operation_index: int) -> tuple[int, ...]:
    if not 0 <= operation_index <= 0xF:
        raise ValueError("small-immediate wrapper signature supports operation 0..15")
    return (
        0x2E00, 0x58F0, 0x58F1,
        0x4810, 0x4800, 0x58F1, 0x58F0,
        0x4800 | operation_index, 0x58F0,
        0xBD1B, 0x23B8,
        0x50F6, 0x381F, 0x380F, 0x2F00, 0xC620,
    )


def analyse(program: bytes) -> dict[str, Any]:
    _expect_words(program, DISPATCH_SOURCE, DISPATCH_WORDS, "game/animation dispatcher")
    _expect_words(
        program,
        RESIDENT_BROWSER_SOURCE,
        (0x2EA9, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x780B, 0x0006),
        "resident file-browser prologue",
    )
    _expect_words(
        program,
        SELECTED_LAUNCH_SOURCE,
        SELECTED_LAUNCH_WORDS,
        "selected-file launch handoff",
    )
    _expect_words(
        program,
        LAUNCH_SEQUENCE_SOURCE,
        LAUNCH_SEQUENCE_PROLOGUE,
        "selected-resource launch sequence prologue",
    )
    _expect_words(
        program,
        LAUNCH_SEQUENCE_SOURCE + LAUNCH_SEQUENCE_SIZE - 8,
        LAUNCH_SEQUENCE_EPILOGUE,
        "selected-resource launch sequence epilogue",
    )
    launch_sequence_words = words(
        program, LAUNCH_SEQUENCE_SOURCE, LAUNCH_SEQUENCE_SIZE // 2
    )
    for call, description in (
        ((0xBD30, 0xC370), "file-state constructor"),
        ((0xBD30, 0xC99E), "file wrapper"),
        ((0xBD18, 0x21F4), "application launch manager"),
    ):
        if list(call) not in [
            launch_sequence_words[index:index + 2]
            for index in range(len(launch_sequence_words) - 1)
        ]:
            raise ValueError(
                f"selected-resource launch sequence lacks {description} call"
            )

    records = operation_records(program)
    catalogue = catalogue_entries(program)
    wrapper_results: list[dict[str, Any]] = []
    for wrapper in WRAPPERS:
        runtime = (WRAPPER_RUNTIME_SEGMENT << 16) | int(wrapper["runtime_pc"])
        source = (WRAPPER_SOURCE_SEGMENT << 16) | int(wrapper["runtime_pc"])
        operation_index = int(wrapper["operation_index"])
        _expect_words(
            program,
            source,
            _wrapper_signature(operation_index),
            f"{wrapper['name']} operation wrapper",
        )

        catalogue_entry = catalogue[int(wrapper["catalogue_index"])]
        if catalogue_entry["field4"] != wrapper["application_id"]:
            raise ValueError(
                f"catalogue id mismatch for {wrapper['name']}: "
                f"{catalogue_entry['field4']:04X} != {wrapper['application_id']:04X}"
            )
        operation = records[operation_index]
        wrapper_results.append({
            **wrapper,
            "application_id_hex": f"{int(wrapper['application_id']):04X}",
            "catalogue_name": catalogue_entry["name"],
            "catalogue_source": catalogue_entry["source"],
            "catalogue_destination": catalogue_entry["destination"],
            "dispatcher_source": address_text(DISPATCH_SOURCE),
            "dispatcher_destination": address_text(DISPATCH_DESTINATION),
            "wrapper_source": address_text(source),
            "wrapper_destination": address_text(runtime),
            "resident_browser": "1B:23B8",
            "operation": operation,
        })

    game = next(item for item in wrapper_results if item["name"] == "game-world-browser")
    animation = next(
        item for item in wrapper_results if item["name"] == "animation-browser"
    )
    expected = (
        (game, "游戏世界", r"0:\应用程序", r"\*.npe"),
        (animation, "动漫欣赏", r"0:\动漫欣赏", r"\*.nwf"),
    )
    for item, name, directory, file_filter in expected:
        if item["catalogue_name"] != name:
            raise ValueError(
                f"catalogue name mismatch: {item['catalogue_name']!r} != {name!r}"
            )
        operation = item["operation"]
        if operation["directory"] != directory or operation["filter"] != file_filter:
            raise ValueError(
                f"operation contract mismatch for {name}: "
                f"{operation['directory']!r}, {operation['filter']!r}"
            )

    return {
        "schema": "np560-file-browser-operation-catalog-v1",
        "program_sha256": hashlib.sha256(program).hexdigest(),
        "scope": {
            "claim": "exact V3.80 catalogue-to-file-browser dispatch contract",
            "npe_nwf_same_container_proven": False,
            "selected_file_launch_first_hop_recovered": True,
            "npe_parser_recovered": False,
        },
        "operation_table": {
            "source": address_text(OPERATION_TABLE_SOURCE),
            "destination": address_text(OPERATION_TABLE_DESTINATION),
            "record_words": OPERATION_RECORD_WORDS,
            "record_count": OPERATION_RECORD_COUNT,
            "records": records,
        },
        "dispatch": {
            "source": address_text(DISPATCH_SOURCE),
            "destination": address_text(DISPATCH_DESTINATION),
            "wrappers": wrapper_results,
        },
        "selected_file_launch": {
            "browser_source": address_text(RESIDENT_BROWSER_SOURCE),
            "browser_destination": address_text(RESIDENT_BROWSER_DESTINATION),
            "selected_descriptor_global": "A4:5192/5194",
            "handoff_source": address_text(SELECTED_LAUNCH_SOURCE),
            "handoff_destination": address_text(SELECTED_LAUNCH_DESTINATION),
            "launch_sequence_source": address_text(LAUNCH_SEQUENCE_SOURCE),
            "launch_sequence_destination": address_text(
                LAUNCH_SEQUENCE_DESTINATION
            ),
            "launch_sequence_bytes": LAUNCH_SEQUENCE_SIZE,
            "file_state_constructor": "30:C370",
            "file_wrapper": "30:C99E",
            "application_launch_manager": "18:21F4",
            "claim": (
                "the selected .npe resource descriptor reaches the ordinary "
                "guest launch sequence; the downstream NPE parser is not yet identified"
            ),
        },
        "game_world": game,
        "animation_browser": animation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("program", nargs="?", type=Path, default=DEFAULT_PROGRAM)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = analyse(args.program.read_bytes())
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
