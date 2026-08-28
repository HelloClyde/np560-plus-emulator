#!/usr/bin/env python3
"""Recover and verify the NP560+ V3.80 NEPLAYER/NWF file contract.

This is deliberately a static preflight tool.  It extracts only facts pinned
by the shipped PRG and fails when any instruction or data anchor changes.  It
does not pretend that an original factory ``.nwf`` file has been recovered.

The DMCU stores bytes inside each 16-bit PRG word in the opposite order from
the logical byte-addressed memory seen by MOVB.  The fixed strings therefore
need word-byte exchange before they are readable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from disassembly.analyse_np560_app_catalog import (  # noqa: E402
    DEFAULT_PROGRAM,
    PROGRAM_BASE,
    address_text,
    application_registry,
    words,
)


RESOURCE_OPEN_SOURCE = 0x3A668A
RESOURCE_OPEN_DESTINATION = 0x1D668A
RESOURCE_OPEN_SIZE = 0x0730
RECORD_LOADER_SOURCE = 0x3A0EEA
RECORD_LOADER_DESTINATION = 0x1D0EEA
RECORD_LOADER_SIZE = 0x0770

DES_BLOCK_BYTES = 8
PROTECTED_HEADER_BLOCKS = 0x3E
PROTECTED_HEADER_BYTES = PROTECTED_HEADER_BLOCKS * DES_BLOCK_BYTES

HEADER_TABLE_OFFSET = 0x40
HEADER_TABLE_BYTE_FIELD_OFFSET = 0x00
HEADER_TABLE_SIGNED24_FIELDS = (
    (0x01, "field_7c92_7c94", "A0:7C92/A0:7C94"),
    (0x04, "field_7c96_7c98", "A0:7C96/A0:7C98"),
    (0x07, "field_7c9a_7c9c", "A0:7C9A/A0:7C9C"),
    (0x0A, "authorization_offset", "A0:7C9E/A0:7CA0"),
    (0x0D, "record_position_base", "A0:7CA2/A0:7CA4"),
    (0x10, "field_7ca6_7ca8", "A0:7CA6/A0:7CA8"),
    (0x13, "field_7caa_7cac", "A0:7CAA/A0:7CAC"),
    (0x16, "field_7cae_7cb0", "A0:7CAE/A0:7CB0"),
    (0x19, "field_7cb2_7cb4", "A0:7CB2/A0:7CB4"),
    (0x1C, "field_7cb6_7cb8", "A0:7CB6/A0:7CB8"),
)

CONSTANT_SOURCE_SEGMENT = 0x48
CONSTANT_RUNTIME_SEGMENT = 0x2B
CONSTANTS = (
    (0xFFE6, 13, "accepted_version_0", "NEPLAYERV0.98"),
    (0xFFD8, 13, "accepted_version_1", "NEPLAYERV0.99"),
    (0xFFC0, 8, "player_magic", "NEPLAYER"),
    (0xFFA8, 8, "authorization_magic", "NOAHAUTH"),
)


def program_offset(address: int) -> int:
    offset = address - PROGRAM_BASE
    if offset < 0:
        raise ValueError(f"{address_text(address)} is below the PRG mapping")
    return offset


def logical_bytes(program: bytes, source_address: int, length: int) -> bytes:
    """Read logical MOVB order from a word-exchanged PRG data island."""
    if source_address & 1:
        raise ValueError("logical byte extraction must begin on a word boundary")
    offset = program_offset(source_address)
    end = offset + ((length + 1) & ~1)
    raw = program[offset:end]
    if len(raw) != end - offset:
        raise ValueError(f"{address_text(source_address)} is outside NP560.PRG")
    exchanged = bytearray()
    for index in range(0, len(raw), 2):
        exchanged.extend((raw[index + 1], raw[index]))
    return bytes(exchanged[:length])


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


def _verify_code_contract(program: bytes) -> None:
    anchors = (
        (RESOURCE_OPEN_SOURCE, [0x2E18, 0x58F1, 0x58F2, 0x58F3],
         "resource-open prologue"),
        (0x3A66F4, [0x72F1, 0x005F, 0x5300, 0xAC06, 0x671C],
         "minimum resource size check"),
        (0x3A6742, [0x68F0, 0x0200], "header read size"),
        (0x3A6764, [0xBD33, 0x048A], "header file read"),
        (0x3A678E, [0x481D, 0x4800], "version length"),
        (0x3A6796, [0x68F1, 0xFFE6, 0x68F0, 0x002B],
         "first version constant"),
        (0x3A67D2, [0x68F1, 0xFFD8, 0x68F0, 0x002B],
         "second version constant"),
        (0x3A6862, [0x70F1, 0x0010], "protected header offset"),
        (0x3A6848, [0x68F0, 0x003E], "protected header DES block count"),
        (0x3A68DA, [0x70F3, 0x001C], "header XOR byte 0"),
        (0x3A68EE, [0x70F1, 0x001D], "header XOR byte 1"),
        (0x3A6902, [0x1720], "header XOR operation"),
        (0x3A690E, [0x4818, 0x4800], "player magic length"),
        (0x3A6916, [0x68F1, 0xFFC0, 0x68F0, 0x002B],
         "player magic constant"),
        (0x3A6960, [0x70F1, 0x0040], "header index field offset"),
        (0x3A6A42, [0x4818, 0x4800], "authorization magic length"),
        (0x3A6A4A, [0x68F1, 0xFFA8, 0x68F0, 0x002B],
         "authorization magic constant"),
        (0x3A6B0C, [0x68F0, 0x005F], "header decode start"),
        (0x3A6BFE, [0x76F2, 0x0200], "header page boundary"),
        (RESOURCE_OPEN_SOURCE + RESOURCE_OPEN_SIZE - 0x0A,
         [0x383F, 0x382F, 0x381F, 0x2F00, 0xC620],
         "resource-open epilogue"),
        (RECORD_LOADER_SOURCE, [0x2E15, 0x58F1, 0x58F2, 0x58F3],
         "record-loader prologue"),
        (0x3A0F3E, [0x88F0, 0x7DF6, 0x88F1, 0x7DF8],
         "record base position"),
        (0x3A0F4A, [0x90F1, 0x7CA4, 0x91F0, 0x7CA2],
         "record relative position"),
        (0x3A0F62, [0x72F1, 0xFE00, 0x5300, 0xAC06, 0x14F8],
         "direct record threshold"),
        (0x3A1500, [0x5417, 0x5400], "record alignment mask"),
        (0x3A152E, [0x68F1, 0x7778, 0x68F0, 0x0050],
         "record window destination"),
        (0x3A1572, [0x68F0, 0x0200], "record window read size"),
        (0x3A1594, [0xBD33, 0x048A], "record window file read"),
        (0x3A1632, [0x4800, 0x6810, 0x00A0],
         "record index reset"),
        (RECORD_LOADER_SOURCE + RECORD_LOADER_SIZE - 0x0E,
         [0x385F, 0x384F, 0x383F, 0x382F, 0x381F, 0x2F00, 0xC620],
         "record-loader epilogue"),
    )
    for address, expected, description in anchors:
        _expect_words(program, address, expected, description)


def analyse(program: bytes) -> dict[str, Any]:
    _verify_code_contract(program)

    constants: dict[str, dict[str, Any]] = {}
    for pc, length, name, expected_text in CONSTANTS:
        source_address = (CONSTANT_SOURCE_SEGMENT << 16) | pc
        value = logical_bytes(program, source_address, length)
        text = value.decode("ascii")
        if text != expected_text:
            raise ValueError(
                f"{name} mismatch at {address_text(source_address)}: "
                f"expected {expected_text!r}, got {text!r}"
            )
        constants[name] = {
            "text": text,
            "bytes_hex": value.hex(),
            "length": length,
            "source": address_text(source_address),
            "destination": f"{CONSTANT_RUNTIME_SEGMENT:02X}:{pc:04X}",
        }

    registry = application_registry(program)
    menu_entries = [
        entry for entry in registry if entry["application_code"] == 0x1203
    ]
    if menu_entries != [{
        "index": 59,
        "source": "47:06EC",
        "destination": "2A:06EC",
        "application_code": 0x1203,
        "application_code_hex": "1203",
        "flags": 0xFF00,
        "entry_point": "2C:C9E8",
    }]:
        raise ValueError(
            "application registry does not contain the expected generic-menu "
            "mapping 0x1203 -> 2C:C9E8"
        )

    return {
        "schema": "np560-nwf-contract-v1",
        "scope": {
            "claim": "static V3.80 format and launch contract",
            "original_factory_nwf_recovered": False,
        },
        "resource_open": {
            "source": address_text(RESOURCE_OPEN_SOURCE),
            "destination": address_text(RESOURCE_OPEN_DESTINATION),
            "minimum_file_bytes": 0x5F,
            "header_buffer": "53:0000",
            "header_read_bytes": 0x200,
            "accepted_versions": [
                constants["accepted_version_0"],
                constants["accepted_version_1"],
            ],
            "player_magic": constants["player_magic"],
            "authorization_magic": constants["authorization_magic"],
            "protected_header_offset": 0x10,
            "protected_header_blocks": PROTECTED_HEADER_BLOCKS,
            "des_block_bytes": DES_BLOCK_BYTES,
            "protected_header_bytes": PROTECTED_HEADER_BYTES,
            "guest_transformation": "DES-E(K1), DES-D(K2), DES-E(K1)",
            "disk_inverse_transformation": "DES-D(K1), DES-E(K2), DES-D(K1)",
            "key_1_source": "raw header bytes 0x00..0x07",
            "key_2_source": "raw header bytes 0x08..0x0F",
            "xor_seed_header_offsets": [0x1C, 0x1D],
            "index_field_offset": HEADER_TABLE_OFFSET,
            "header_table": {
                "offset": HEADER_TABLE_OFFSET,
                "byte_field": {
                    "relative_offset": HEADER_TABLE_BYTE_FIELD_OFFSET,
                    "global": "A0:7C90",
                },
                "signed_little_endian_24_bit_fields": [
                    {
                        "relative_offset": offset,
                        "name": name,
                        "global": global_address,
                    }
                    for offset, name, global_address
                    in HEADER_TABLE_SIGNED24_FIELDS
                ],
                "parser_source": "4A:D79E",
                "parser_destination": "2D:D79E",
                "signed24_reader_source": "4E:3A72",
                "signed24_reader_destination": "31:3A72",
                "authorization_disabled_value": -1,
            },
            "decoded_header_start": 0x5F,
            "first_page_bytes": 0x200,
            "authorization_offset": "runtime-computed",
            "exact_guest_words_recovered": True,
        },
        "record_loader": {
            "source": address_text(RECORD_LOADER_SOURCE),
            "destination": address_text(RECORD_LOADER_DESTINATION),
            "current_position": "A0:7DF6/7DF8 + A0:7CA2/7CA4",
            "direct_window_threshold": 0xFE00,
            "window_alignment_bytes": 8,
            "record_index_global": "A0:7086",
            "record_window": "50:7778 - A0:7086",
            "record_window_bytes": 0x200,
            "exact_guest_words_recovered": True,
        },
        "menu_launch": {
            "application_code": 0x1203,
            "application_code_hex": "1203",
            "registry_entry": menu_entries[0],
            "record_source": "mutable 50:7778 window populated by 1D:0EEA",
            "factory_resource_required": True,
        },
        "constants": constants,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("program", nargs="?", type=Path, default=DEFAULT_PROGRAM)
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    args = parser.parse_args()

    result = analyse(args.program.read_bytes())
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
