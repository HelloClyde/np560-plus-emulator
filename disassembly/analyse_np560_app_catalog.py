#!/usr/bin/env python3
"""Recover the NP560+ V3.80 resident menu catalogue and event dispatcher.

The update program contains several unused ``+0x1d`` segment copies of code
and data linked for lower run-time addresses.  This module verifies three
related artefacts without guessing their semantics:

* the complete 20:0B82 helper and the 124 five-word records which follow it;
* the complete resident 18:9A58 event routine and its 0x80..0x8e jump table;
* the 31:138C wrapper which initializes buffers and enters 18:9A58.

Strings referenced by the records live in the source copy of segment 33 at
50:xxxx and are stored with the two bytes of every DMCU word exchanged.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROGRAM = ROOT / "NP560+V3.80版系统升级程序" / "NP560.PRG"

PROGRAM_BASE = 0x200000
RELOCATION_DELTA = 0x1D0000

CATALOG_HELPER_DESTINATION = 0x200B82
CATALOG_HELPER_SOURCE = CATALOG_HELPER_DESTINATION + RELOCATION_DELTA
CATALOG_HELPER_SIZE = 0x05C0
CATALOG_DESTINATION = 0x201142
CATALOG_SOURCE = CATALOG_DESTINATION + RELOCATION_DELTA
CATALOG_ENTRY_WORDS = 5
CATALOG_ENTRY_SIZE = CATALOG_ENTRY_WORDS * 2
CATALOG_ENTRY_COUNT = 124
CATALOG_END = CATALOG_SOURCE + CATALOG_ENTRY_COUNT * CATALOG_ENTRY_SIZE

EVENT_DISPATCH_DESTINATION = 0x189A58
EVENT_DISPATCH_SOURCE = EVENT_DISPATCH_DESTINATION + RELOCATION_DELTA
EVENT_DISPATCH_SIZE = 0x0AB8
EVENT_JUMP_TABLE_SOURCE = 0x359BDA
EVENT_FIRST = 0x80
EVENT_LAST = 0x8E

EVENT_WRAPPER_DESTINATION = 0x31138C
EVENT_WRAPPER_SOURCE = EVENT_WRAPPER_DESTINATION + RELOCATION_DELTA
EVENT_WRAPPER_SIZE = 0x00CE

APPLICATION_REGISTRY_DESTINATION = 0x2A0514
APPLICATION_REGISTRY_SOURCE = APPLICATION_REGISTRY_DESTINATION + RELOCATION_DELTA
APPLICATION_REGISTRY_ENTRY_WORDS = 4
APPLICATION_REGISTRY_ENTRY_SIZE = APPLICATION_REGISTRY_ENTRY_WORDS * 2
APPLICATION_REGISTRY_ENTRY_COUNT = 81
APPLICATION_REGISTRY_SIZE = (
    APPLICATION_REGISTRY_ENTRY_SIZE * APPLICATION_REGISTRY_ENTRY_COUNT
)

APPLICATION_REGISTRY_LOOKUP_DESTINATION = 0x2FE4C8
APPLICATION_REGISTRY_LOOKUP_SOURCE = (
    APPLICATION_REGISTRY_LOOKUP_DESTINATION + RELOCATION_DELTA
)
APPLICATION_REGISTRY_LOOKUP_SIZE = 0x0124
APPLICATION_REGISTRY_CALL_SOURCE = 0x3524A6
APPLICATION_LAUNCH_MANAGER_DESTINATION = 0x1821F4
APPLICATION_LAUNCH_MANAGER_SOURCE = (
    APPLICATION_LAUNCH_MANAGER_DESTINATION + RELOCATION_DELTA
)
APPLICATION_LAUNCH_MANAGER_SIZE = 0x0B2E

MENU_PAGE_TABLE_DESTINATION = 0x1C9748
MENU_PAGE_TABLE_SOURCE = MENU_PAGE_TABLE_DESTINATION + RELOCATION_DELTA
MENU_PAGE_RECORD_SIZE = 0x42
MENU_PAGE_RECORD_WORDS = MENU_PAGE_RECORD_SIZE // 2
MENU_PAGE_COUNT = 25
MENU_PAGE_TABLE_SIZE = MENU_PAGE_RECORD_SIZE * MENU_PAGE_COUNT
MENU_PAGE_POINTER_CAPACITY = 14

STRING_RUNTIME_SEGMENT = 0x33
STRING_SOURCE_SEGMENT = STRING_RUNTIME_SEGMENT + 0x1D


def address_text(address: int) -> str:
    return f"{address >> 16:02X}:{address & 0xFFFF:04X}"


def program_offset(address: int) -> int:
    offset = address - PROGRAM_BASE
    if offset < 0:
        raise ValueError(f"{address_text(address)} is below the PRG mapping")
    return offset


def u16(program: bytes, address: int) -> int:
    offset = program_offset(address)
    if offset + 2 > len(program):
        raise ValueError(f"{address_text(address)} is outside NP560.PRG")
    return int.from_bytes(program[offset:offset + 2], "little")


def words(program: bytes, address: int, count: int) -> list[int]:
    return [u16(program, address + index * 2) for index in range(count)]


def decode_runtime_string(
    program: bytes,
    segment: int,
    pc: int,
    *,
    maximum_bytes: int = 96,
) -> str:
    """Decode a word-swapped GB18030 string through its run-time pointer."""
    if segment != STRING_RUNTIME_SEGMENT:
        raise ValueError(f"unsupported string segment {segment:04X}")
    source_address = ((segment + 0x1D) << 16) | pc
    offset = program_offset(source_address)
    decoded = bytearray()
    for index in range(0, maximum_bytes, 2):
        pair = program[offset + index:offset + index + 2]
        if len(pair) != 2:
            raise ValueError("unterminated string outside NP560.PRG")
        for value in (pair[1], pair[0]):
            if value == 0:
                return decoded.decode("gb18030")
            decoded.append(value)
    raise ValueError(
        f"unterminated string at {segment:02X}:{pc:04X}"
    )


def catalogue_entries(program: bytes) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index in range(CATALOG_ENTRY_COUNT):
        source = CATALOG_SOURCE + index * CATALOG_ENTRY_SIZE
        pointer_segment, pointer_pc, field2, field3, field4 = words(
            program, source, CATALOG_ENTRY_WORDS
        )
        name = decode_runtime_string(program, pointer_segment, pointer_pc)
        result.append({
            "index": index,
            "source": address_text(source),
            "destination": address_text(
                source - RELOCATION_DELTA
            ),
            "name_pointer": f"{pointer_segment:02X}:{pointer_pc:04X}",
            "name": name,
            "field2": field2,
            "field3": field3,
            "field4": field4,
            "submenu_flag": bool(field2 & 0x8000),
        })
    return result


def _candidate_entry(program: bytes, offset: int) -> bool:
    if offset < 0 or offset + CATALOG_ENTRY_SIZE > len(program):
        return False
    if int.from_bytes(program[offset:offset + 2], "little") != 0x0033:
        return False
    pointer_pc = int.from_bytes(program[offset + 2:offset + 4], "little")
    try:
        name = decode_runtime_string(
            program, STRING_RUNTIME_SEGMENT, pointer_pc, maximum_bytes=64
        )
    except (UnicodeDecodeError, ValueError, IndexError):
        return False
    return bool(name) and len(name) <= 24 and all(
        character.isprintable() for character in name
    )


def descriptor_runs(program: bytes, minimum_count: int = 2) -> list[dict[str, Any]]:
    """Find maximal ten-byte record runs whose first field is a valid name."""
    candidates = {
        offset for offset in range(0, len(program) - CATALOG_ENTRY_SIZE + 1, 2)
        if _candidate_entry(program, offset)
    }
    runs: list[dict[str, Any]] = []
    for start in sorted(candidates):
        if start - CATALOG_ENTRY_SIZE in candidates:
            continue
        count = 1
        while start + count * CATALOG_ENTRY_SIZE in candidates:
            count += 1
        if count < minimum_count:
            continue
        names = []
        for index in range(count):
            offset = start + index * CATALOG_ENTRY_SIZE
            pointer_pc = int.from_bytes(
                program[offset + 2:offset + 4], "little"
            )
            names.append(decode_runtime_string(
                program, STRING_RUNTIME_SEGMENT, pointer_pc
            ))
        source = PROGRAM_BASE + start
        runs.append({
            "source": address_text(source),
            "file_offset": f"0x{start:X}",
            "count": count,
            "names": names,
        })
    return runs


def menu_pages(
    program: bytes,
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entry_by_destination = {
        int(entry["destination"].replace(":", ""), 16): entry
        for entry in entries
    }
    pages: list[dict[str, Any]] = []
    for index in range(MENU_PAGE_COUNT):
        source = MENU_PAGE_TABLE_SOURCE + index * MENU_PAGE_RECORD_SIZE
        record = words(program, source, MENU_PAGE_RECORD_WORDS)
        count = record[4]
        if count > MENU_PAGE_POINTER_CAPACITY:
            raise ValueError(
                f"menu page {index} has invalid item count {count}"
            )
        pointers = []
        trailing_pointers = []
        for item_index in range(MENU_PAGE_POINTER_CAPACITY):
            segment = record[5 + item_index * 2]
            pc = record[6 + item_index * 2]
            if segment == 0 and pc == 0:
                continue
            if segment == 0 or pc == 0:
                raise ValueError(
                    f"menu page {index} has a partial pointer in slot "
                    f"{item_index}"
                )
            address = (segment << 16) | pc
            entry = entry_by_destination.get(address)
            if entry is None:
                raise ValueError(
                    f"menu page {index} points outside the catalogue: "
                    f"{segment:02X}:{pc:04X}"
                )
            decoded_pointer = {
                "pointer": f"{segment:02X}:{pc:04X}",
                "catalogue_index": entry["index"],
                "name": entry["name"],
            }
            if item_index < count:
                pointers.append(decoded_pointer)
            else:
                trailing_pointers.append(decoded_pointer)
        if len(pointers) != count:
            raise ValueError(
                f"menu page {index} has {len(pointers)} active pointers, "
                f"expected {count}"
            )
        pages.append({
            "index": index,
            "source": address_text(source),
            "destination": address_text(source - RELOCATION_DELTA),
            "header_fields": record[:4],
            "item_count": count,
            "items": pointers,
            # Two shipped records retain the first pointer of the following
            # page in an otherwise unused slot.  Preserve this exact data but
            # do not count it as an active item.
            "trailing_pointers": trailing_pointers,
        })
    return pages


def application_registry(program: bytes) -> list[dict[str, Any]]:
    """Decode the sorted application-code to entry-point registry."""
    result: list[dict[str, Any]] = []
    for index in range(APPLICATION_REGISTRY_ENTRY_COUNT):
        source = (
            APPLICATION_REGISTRY_SOURCE
            + index * APPLICATION_REGISTRY_ENTRY_SIZE
        )
        application_code, flags, entry_segment, entry_pc = words(
            program, source, APPLICATION_REGISTRY_ENTRY_WORDS
        )
        result.append({
            "index": index,
            "source": address_text(source),
            "destination": address_text(source - RELOCATION_DELTA),
            "application_code": application_code,
            "application_code_hex": f"{application_code:04X}",
            "flags": flags,
            "entry_point": f"{entry_segment:02X}:{entry_pc:04X}",
        })
    return result


def _expect_words(
    program: bytes,
    address: int,
    expected: list[int],
    description: str,
) -> None:
    actual = words(program, address, len(expected))
    if actual != expected:
        raise ValueError(
            f"{description} mismatch at {address_text(address)}: "
            f"expected {expected!r}, got {actual!r}"
        )


def analyse(program: bytes) -> dict[str, Any]:
    entries = catalogue_entries(program)
    pages = menu_pages(program, entries)
    registry = application_registry(program)
    jump_pcs = words(
        program,
        EVENT_JUMP_TABLE_SOURCE,
        EVENT_LAST - EVENT_FIRST + 1,
    )

    # Pin complete function boundaries and the literal cross-module calls.
    _expect_words(program, CATALOG_HELPER_SOURCE, [0x2E25, 0x58F2],
                  "catalogue helper prologue")
    _expect_words(program, CATALOG_SOURCE - 0x0C,
                  [0x385F, 0x384F, 0x383F, 0x382F, 0x2F00, 0xC620],
                  "catalogue helper epilogue")
    _expect_words(program, EVENT_DISPATCH_SOURCE,
                  [0x2E20, 0x58F0, 0x58F1],
                  "event dispatcher prologue")
    _expect_words(program, EVENT_DISPATCH_SOURCE + EVENT_DISPATCH_SIZE - 0x0C,
                  [0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, 0xC620],
                  "event dispatcher epilogue")
    _expect_words(program, 0x359EDE, [0xBD20, 0x0B82],
                  "event 82 helper call")
    _expect_words(program, 0x359F6C, [0xBD20, 0x0B82],
                  "event 84 type-8 helper call")
    _expect_words(program, 0x359F8E, [0xBD20, 0x0B82],
                  "event 84 type-6 helper call")
    _expect_words(program, EVENT_WRAPPER_SOURCE, [0x2E00, 0x58F0, 0x58F1],
                  "event wrapper prologue")
    _expect_words(program, 0x4E142A, [0xBD18, 0x9A58],
                  "event wrapper resident call")
    _expect_words(program, EVENT_WRAPPER_SOURCE + EVENT_WRAPPER_SIZE - 0x08,
                  [0x381F, 0x380F, 0x2F00, 0xC620],
                  "event wrapper epilogue")
    _expect_words(program, APPLICATION_REGISTRY_LOOKUP_SOURCE,
                  [0x2E07, 0x58F1, 0x58F2, 0x58F3],
                  "application registry lookup prologue")
    _expect_words(
        program,
        APPLICATION_REGISTRY_LOOKUP_SOURCE + 0x54,
        [0x68F5, 0x0514, 0x68F4, 0x002A],
        "application registry table base",
    )
    _expect_words(
        program,
        APPLICATION_REGISTRY_LOOKUP_SOURCE + 0x12,
        [0x68F1, 0x0051],
        "application registry entry count",
    )
    _expect_words(
        program,
        APPLICATION_REGISTRY_LOOKUP_SOURCE + APPLICATION_REGISTRY_LOOKUP_SIZE - 0x0E,
        [0x385F, 0x384F, 0x383F, 0x382F, 0x381F, 0x2F00, 0xC620],
        "application registry lookup epilogue",
    )
    _expect_words(program, APPLICATION_REGISTRY_CALL_SOURCE,
                  [0xBD2F, 0xE4C8],
                  "application registry caller")
    _expect_words(program, APPLICATION_LAUNCH_MANAGER_SOURCE,
                  [0x2E0F, 0x58F1, 0x58F2, 0x58F3],
                  "application launch manager prologue")
    _expect_words(
        program,
        APPLICATION_LAUNCH_MANAGER_SOURCE + APPLICATION_LAUNCH_MANAGER_SIZE - 0x0E,
        [0x385F, 0x384F, 0x383F, 0x382F, 0x381F, 0x2F00, 0xC620],
        "application launch manager epilogue",
    )

    expected_jump_pcs = [
        0x9D7C, 0x9D7C, 0x9EBA, 0x9FB0, 0x9F00,
        0xA020, 0x9C8C, 0xA4F8, 0x9D50, 0x9D66,
        0xA4F8, 0xA4F8, 0xA4F8, 0x9C78, 0xA4FC,
    ]
    if jump_pcs != expected_jump_pcs:
        raise ValueError("event jump table does not match V3.80")

    if CATALOG_END != 0x3D161A:
        raise AssertionError("catalogue boundary constant is inconsistent")
    if [entry["name"] for entry in entries[:5]] != [
        "娱乐", "时间", "计算", "翻译", "资料",
    ]:
        raise ValueError("catalogue prefix does not match V3.80")
    if words(program, CATALOG_END, 2) != [0, 0]:
        raise ValueError("catalogue is not followed by its zero terminator")

    application_codes = [
        entry["application_code"] for entry in registry
    ]
    if application_codes != sorted(application_codes):
        raise ValueError("application registry is not sorted by application code")
    if len(set(application_codes)) != APPLICATION_REGISTRY_ENTRY_COUNT:
        raise ValueError("application registry contains duplicate application codes")
    if registry[0] != {
        "index": 0,
        "source": "47:0514",
        "destination": "2A:0514",
        "application_code": 0x0100,
        "application_code_hex": "0100",
        "flags": 0xFF00,
        "entry_point": "28:EEE8",
    }:
        raise ValueError("application registry prefix does not match V3.80")
    if registry[-1]["application_code"] != 0x2000:
        raise ValueError("application registry terminator does not match V3.80")

    # Every explicit subgroup descriptor names the page which contains its
    # children.  Pages 0..5 are the six root category pages; subgroup pages
    # therefore begin at six and continue without holes through 24.
    subgroup_pages = {
        entry["field3"] for entry in entries if entry["submenu_flag"]
    }
    if subgroup_pages != set(range(6, MENU_PAGE_COUNT)):
        raise ValueError(
            "catalogue subgroup page IDs are not the contiguous range 6..24"
        )
    if [item["name"] for item in pages[0]["items"]] != [
        "娱乐", "时间", "计算", "翻译", "资料",
    ]:
        raise ValueError("root menu page zero does not match V3.80")
    zero_record = words(
        program,
        MENU_PAGE_TABLE_SOURCE + MENU_PAGE_TABLE_SIZE,
        MENU_PAGE_RECORD_WORDS,
    )
    if any(zero_record):
        raise ValueError("active menu page table is not followed by a zero record")

    return {
        "schema": "np560-app-catalog-v1",
        "catalogue_helper": {
            "source": (
                f"{address_text(CATALOG_HELPER_SOURCE)}.."
                f"{address_text(CATALOG_SOURCE)}"
            ),
            "destination": (
                f"{address_text(CATALOG_HELPER_DESTINATION)}.."
                f"{address_text(CATALOG_DESTINATION)}"
            ),
            "bytes": CATALOG_HELPER_SIZE,
            "exact_guest_words_recovered": True,
        },
        "catalogue": {
            "source": (
                f"{address_text(CATALOG_SOURCE)}.."
                f"{address_text(CATALOG_END)}"
            ),
            "destination": (
                f"{address_text(CATALOG_DESTINATION)}.."
                f"{address_text(CATALOG_END - RELOCATION_DELTA)}"
            ),
            "entry_words": CATALOG_ENTRY_WORDS,
            "entry_count": len(entries),
            "entries": entries,
        },
        "descriptor_runs": descriptor_runs(program),
        "menu_pages": {
            "source": (
                f"{address_text(MENU_PAGE_TABLE_SOURCE)}.."
                f"{address_text(MENU_PAGE_TABLE_SOURCE + MENU_PAGE_TABLE_SIZE)}"
            ),
            "destination": (
                f"{address_text(MENU_PAGE_TABLE_DESTINATION)}.."
                f"{address_text(MENU_PAGE_TABLE_DESTINATION + MENU_PAGE_TABLE_SIZE)}"
            ),
            "record_bytes": MENU_PAGE_RECORD_SIZE,
            "page_count": len(pages),
            "pages": pages,
            "exact_guest_words_recovered": True,
        },
        "event_dispatcher": {
            "source": (
                f"{address_text(EVENT_DISPATCH_SOURCE)}.."
                f"{address_text(EVENT_DISPATCH_SOURCE + EVENT_DISPATCH_SIZE)}"
            ),
            "destination": (
                f"{address_text(EVENT_DISPATCH_DESTINATION)}.."
                f"{address_text(EVENT_DISPATCH_DESTINATION + EVENT_DISPATCH_SIZE)}"
            ),
            "jump_table_source": address_text(EVENT_JUMP_TABLE_SOURCE),
            "jump_table": {
                f"{EVENT_FIRST + index:02X}": f"18:{pc:04X}"
                for index, pc in enumerate(jump_pcs)
            },
            "catalogue_helper_actions": {
                "82": [1],
                "84 when item type is 8": [7],
                "84 when item type is 6": [9],
            },
            "exact_guest_words_recovered": True,
        },
        "event_wrapper": {
            "source": (
                f"{address_text(EVENT_WRAPPER_SOURCE)}.."
                f"{address_text(EVENT_WRAPPER_SOURCE + EVENT_WRAPPER_SIZE)}"
            ),
            "destination": (
                f"{address_text(EVENT_WRAPPER_DESTINATION)}.."
                f"{address_text(EVENT_WRAPPER_DESTINATION + EVENT_WRAPPER_SIZE)}"
            ),
            "resident_call": "18:9A58",
            "exact_guest_words_recovered": True,
        },
        "application_registry": {
            "source": (
                f"{address_text(APPLICATION_REGISTRY_SOURCE)}.."
                f"{address_text(APPLICATION_REGISTRY_SOURCE + APPLICATION_REGISTRY_SIZE)}"
            ),
            "destination": (
                f"{address_text(APPLICATION_REGISTRY_DESTINATION)}.."
                f"{address_text(APPLICATION_REGISTRY_DESTINATION + APPLICATION_REGISTRY_SIZE)}"
            ),
            "entry_words": APPLICATION_REGISTRY_ENTRY_WORDS,
            "entry_count": len(registry),
            "entries": registry,
            "lookup": {
                "source": (
                    f"{address_text(APPLICATION_REGISTRY_LOOKUP_SOURCE)}.."
                    f"{address_text(APPLICATION_REGISTRY_LOOKUP_SOURCE + APPLICATION_REGISTRY_LOOKUP_SIZE)}"
                ),
                "destination": (
                    f"{address_text(APPLICATION_REGISTRY_LOOKUP_DESTINATION)}.."
                    f"{address_text(APPLICATION_REGISTRY_LOOKUP_DESTINATION + APPLICATION_REGISTRY_LOOKUP_SIZE)}"
                ),
                "algorithm": "binary search",
                "direct_caller_source": address_text(APPLICATION_REGISTRY_CALL_SOURCE),
            },
            "launch_manager": {
                "source": (
                    f"{address_text(APPLICATION_LAUNCH_MANAGER_SOURCE)}.."
                    f"{address_text(APPLICATION_LAUNCH_MANAGER_SOURCE + APPLICATION_LAUNCH_MANAGER_SIZE)}"
                ),
                "destination": (
                    f"{address_text(APPLICATION_LAUNCH_MANAGER_DESTINATION)}.."
                    f"{address_text(APPLICATION_LAUNCH_MANAGER_DESTINATION + APPLICATION_LAUNCH_MANAGER_SIZE)}"
                ),
                "registry_call": "18:24A6 -> 2F:E4C8",
            },
            "exact_guest_words_recovered": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("program", nargs="?", type=Path,
                        default=DEFAULT_PROGRAM)
    parser.add_argument("--output", type=Path,
                        help="optional JSON output path")
    args = parser.parse_args()

    result = analyse(args.program.read_bytes())
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
