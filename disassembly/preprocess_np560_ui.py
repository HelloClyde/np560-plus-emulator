#!/usr/bin/env python3
"""Preprocess the exact NP560 foreground/UI reverse-engineering slice.

The full PRG is mostly unrelated code and resource data.  This command emits
small recursive disassemblies for the foreground call chain and a manifest of
the signature-bounded 39:974E layout catalogue used through data 1C:974E.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


FUNCTIONS = (
    ("storage", 0x4C, 0x5CDC),
    ("file-open-inner", 0x40, 0x7584),
    ("clock-validator", 0x4C, 0x4D94),
    ("time-3212", 0x4E, 0x3212),
    ("time-6010", 0x4E, 0x6010),
    ("time-7b9e", 0x4E, 0x7B9E),
    ("main-resource", 0x50, 0x17AE),
    ("foreground-loop", 0x3D, 0x2DE0),
    ("foreground-callback", 0x41, 0x162C),
    ("foreground-layout-consumer", 0x4A, 0x9DFC),
    ("application-pending-reader", 0x50, 0x5D76),
    ("power-worker", 0x3F, 0xF40C),
    ("application-tick", 0x4C, 0xFA32),
    ("tick-sample", 0x4F, 0x1EF2),
    ("tick-commit", 0x4D, 0xC61A),
    ("tick-commit-worker", 0x49, 0x528A),
    ("foreground-parent", 0x4C, 0xC59A),
    ("foreground-status", 0x50, 0x16F6),
    ("foreground-state-dispatch", 0x3F, 0x381E),
    ("foreground-state1-handler", 0x50, 0x3E86),
    ("startup-default-selector", 0x4A, 0x7F88),
    ("startup-default-manager", 0x47, 0xA952),
    ("application-main-loop", 0x3F, 0x515E),
    ("application-resource-driver", 0x4F, 0x512C),
    ("resident-resource-init", 0x38, 0xCE3C),
    ("file-open-public", 0x3C, 0x1F1A),
    ("file-root-pool", 0x4C, 0x37B0),
    ("file-root-lookup", 0x4E, 0xB83C),
    ("file-root-release", 0x4F, 0x5592),
    ("file-record-scan", 0x4A, 0xD93C),
    ("storage-driver-resolve", 0x4A, 0x3460),
    ("file-driver-dynamic-wrapper", 0x50, 0x6624),
    ("file-driver-dynamic-child", 0x50, 0x244A),
    ("modal-event-loop", 0x4E, 0xF282),
    ("modal-event-ready", 0x4F, 0x4C34),
    ("menu-catalog", 0x3D, 0x0B82),
    ("menu-event-wrapper", 0x4E, 0x138C),
    ("menu-event-dispatch", 0x35, 0x9A58),
    ("menu-event-state", 0x50, 0x0EDC),
    ("resident-main-menu", 0x32, 0xD474),
    ("invalid-clock-handler-a", 0x4F, 0xB2F4),
    ("invalid-clock-handler-b", 0x4E, 0x3FC0),
)

PROGRAM_BASE_SEGMENT = 0x20
LAYOUT_SOURCE_SEGMENT = 0x39
LAYOUT_SOURCE_OFFSET = 0x974E
LAYOUT_RECORD_SIZE = 0x42
LAYOUT_RECORD_COUNT = 25
DISPATCH_SOURCE_SEGMENT = 0x3E
DISPATCH_SOURCE_OFFSET = 0xAA46
DISPATCH_DATA_SEGMENT = 0x21
DISPATCH_RECORD_WORDS = 5
DISPATCH_RECORD_COUNT = 130


def word_at(image: bytes, segment: int, offset: int) -> int:
    start = file_offset(segment, offset)
    if start + 2 > len(image):
        raise ValueError(
            f"firmware is too short for word {segment:02X}:{offset:04X}"
        )
    return int.from_bytes(image[start:start + 2], "little")


def require_words(
    image: bytes, segment: int, offset: int, expected: tuple[int, ...],
) -> None:
    actual = tuple(
        word_at(image, segment, offset + index * 2)
        for index in range(len(expected))
    )
    if actual != expected:
        raise ValueError(
            f"unexpected startup/UI signature at {segment:02X}:{offset:04X}: "
            f"{actual!r} != {expected!r}"
        )


def startup_selector_manifest(image: bytes) -> dict[str, object]:
    """Describe the persistent product selector decoded at 4A:7F88."""
    require_words(
        image, 0x4A, 0x7F90,
        (0x68F0, 0x0010, 0x68F1, 0xD072),
    )
    mappings = (
        (4, 0x13, 0x7FB4, 0x7FBA),
        (5, 0x04, 0x7FC8, 0x7FCE),
        (6, 0x01, 0x7FDA, 0x7FE0),
        (7, 0x02, 0x7FEC, 0x7FF2),
        (8, 0x4E, 0x7FFE, 0x8004),
        (9, 0x31, 0x8012, 0x8018),
        (10, 0x20, 0x8026, 0x802C),
        (11, 0x50, 0x803A, 0x8040),
    )
    expected_compare_words = {
        0x7FB4: 0x5604,
        0x7FC8: 0x5605,
        0x7FDA: 0x5606,
        0x7FEC: 0x5607,
        0x7FFE: 0x5608,
        0x8012: 0x5609,
        0x8026: 0x560A,
        0x803A: 0x560B,
    }
    for compare, expected in expected_compare_words.items():
        require_words(image, 0x4A, compare, (expected,))
    return {
        "entry": "4A:7F88",
        "persistent_byte": "10:D072",
        "mappings": [
            {
                "selector": selector,
                "initial_state": state,
                "compare": f"4A:{compare:04X}",
                "result": f"4A:{result:04X}",
            }
            for selector, state, compare, result in mappings
        ],
        "special_selectors": {
            "1": "launch-via-2E:D34A",
            "3": "call-2C:E064",
            "default": "manager-2A:A952",
        },
    }


def foreground_control_manifest(image: bytes) -> dict[str, object]:
    """Validate the two control events currently relevant to menu bring-up."""
    require_words(
        image, 0x3D, 0x2F52,
        (0x76F0, 0x008F, 0xAC01, 0x2FA2),
    )
    require_words(
        image, 0x3D, 0x2FA2,
        (0x68F1, 0x00FE, 0x6810, 0x00A2, 0xC700, 0xA8F1, 0x2AAA),
    )
    require_words(
        image, 0x3D, 0x2F62,
        (0x76F0, 0x00B0, 0xAC01, 0x3102),
    )
    require_words(
        image, 0x3D, 0x3114,
        (0x68F0, 0x00FF, 0x6810, 0x00A2, 0xC700, 0xA8F0, 0x2AAA),
    )
    return {
        "source": "3D:2DE0",
        "events": [
            {
                "event": 0x008F,
                "new_state": 0x00FE,
                "compare": "3D:2F52",
                "state_write": "3D:2FAC",
                "meaning": "firmware-generated idle transition",
            },
            {
                "event": 0x00B0,
                "new_state": 0x00FF,
                "compare": "3D:2F62",
                "state_write": "3D:311E",
                "meaning": "enter main menu",
            },
        ],
    }


def file_offset(segment: int, offset: int = 0) -> int:
    if segment < PROGRAM_BASE_SEGMENT:
        raise ValueError(f"segment {segment:02X} precedes PRG base")
    return ((segment - PROGRAM_BASE_SEGMENT) << 16) + offset


def layout_manifest(image: bytes) -> dict[str, object]:
    start = file_offset(LAYOUT_SOURCE_SEGMENT, LAYOUT_SOURCE_OFFSET)
    size = LAYOUT_RECORD_COUNT * LAYOUT_RECORD_SIZE
    table = image[start:start + size]
    boundary = image[start + size:start + size + LAYOUT_RECORD_SIZE]
    if len(table) != size or len(boundary) != LAYOUT_RECORD_SIZE:
        raise ValueError("firmware is too short for the layout catalogue")
    if any(boundary):
        raise ValueError(
            "record 25 is not the expected all-zero table boundary"
        )

    records = []
    for index in range(LAYOUT_RECORD_COUNT):
        record = table[index * LAYOUT_RECORD_SIZE:
                       (index + 1) * LAYOUT_RECORD_SIZE]
        words = [
            int.from_bytes(record[offset:offset + 2], "little")
            for offset in range(0, len(record), 2)
        ]
        records.append({
            "index": index,
            "source": f"39:{LAYOUT_SOURCE_OFFSET + index * LAYOUT_RECORD_SIZE:04X}",
            "word0": words[0],
            "word1": words[1],
            "nonzero_words": sum(word != 0 for word in words),
        })
    return {
        "source": "39:974E",
        "data_view": "1C:974E",
        "record_size": LAYOUT_RECORD_SIZE,
        "record_count": LAYOUT_RECORD_COUNT,
        "size": size,
        "sha256": hashlib.sha256(table).hexdigest(),
        "zero_boundary": "39:9DC0",
        "records": records,
    }


def dispatch_manifest(image: bytes) -> dict[str, object]:
    record_size = DISPATCH_RECORD_WORDS * 2
    start = file_offset(DISPATCH_SOURCE_SEGMENT, DISPATCH_SOURCE_OFFSET)
    size = DISPATCH_RECORD_COUNT * record_size
    table = image[start:start + size]
    boundary = image[start + size:start + size + record_size]
    if len(table) != size or len(boundary) != record_size:
        raise ValueError("firmware is too short for the foreground dispatch table")
    if any(boundary):
        raise ValueError(
            "record 130 is not the expected all-zero dispatch-table boundary"
        )

    records = []
    for index in range(DISPATCH_RECORD_COUNT):
        record = table[index * record_size:(index + 1) * record_size]
        words = [
            int.from_bytes(record[offset:offset + 2], "little")
            for offset in range(0, record_size, 2)
        ]
        records.append({
            "index": index,
            "source": (
                f"{DISPATCH_SOURCE_SEGMENT:02X}:"
                f"{DISPATCH_SOURCE_OFFSET + index * record_size:04X}"
            ),
            "event": words[0],
            "action": words[1],
            "argument_segment": words[2],
            "argument_offset": words[3],
            "next_state": words[4],
        })
    return {
        "source": f"{DISPATCH_SOURCE_SEGMENT:02X}:{DISPATCH_SOURCE_OFFSET:04X}",
        "data_view": f"{DISPATCH_DATA_SEGMENT:02X}:{DISPATCH_SOURCE_OFFSET:04X}",
        "record_words": DISPATCH_RECORD_WORDS,
        "record_count": DISPATCH_RECORD_COUNT,
        "size": size,
        "sha256": hashlib.sha256(table).hexdigest(),
        "zero_boundary": (
            f"{DISPATCH_SOURCE_SEGMENT:02X}:"
            f"{DISPATCH_SOURCE_OFFSET + size:04X}"
        ),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("tmp") / "np560-ui-preprocessed",
    )
    args = parser.parse_args()
    image_path = args.image.resolve()
    output_dir = args.output_dir.resolve()
    if not image_path.is_file():
        parser.error(f"firmware not found: {image_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    disassembler = Path(__file__).with_name("np560_aux_disasm.py")
    for name, segment, entry in FUNCTIONS:
        command = (
            sys.executable, str(disassembler), str(image_path),
            "--base", f"{segment:02X}:0000",
            "--entry", f"{segment:02X}:{entry:04X}",
            "--endian", "little",
            "--offset", hex(file_offset(segment)),
            "--length", "0x10000",
            "--name", name,
            "--output-dir", str(output_dir),
        )
        subprocess.run(command, check=True)

    image = image_path.read_bytes()
    manifest = {
        "firmware": str(image_path),
        "firmware_sha256": hashlib.sha256(image).hexdigest(),
        "functions": [
            {"name": name, "entry": f"{segment:02X}:{entry:04X}"}
            for name, segment, entry in FUNCTIONS
        ],
        "foreground_layout": layout_manifest(image),
        "foreground_dispatch": dispatch_manifest(image),
        "startup_selector": startup_selector_manifest(image),
        "foreground_controls": foreground_control_manifest(image),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
