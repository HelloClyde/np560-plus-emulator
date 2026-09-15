#!/usr/bin/env python3
"""Install the exact vendor modal callback closure at the ROM-01 boundary.

The resident callback path calls 2B:6CE6, but the flat PRG destination starts
at POP DS0 in the middle of an unrelated function.  The updater's +0x1d
linked banks contain complete framed implementations for that callback and
its directly reached render/layout closure.  Two low resident destinations
are still reserved in the reconstructed ROM, so they are installed through
the same writable-code mechanism as the other recovered mask-ROM modules.

This patch emits ordinary guest DMCU byte-copy loops.  QEMU only supplies
writable/executable aliases for the evidenced destination ranges; it does not
intercept or implement any firmware call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable, Sequence


PROGRAM_BASE = 0x200000
LATE_RESULT_RETS_ADDRESS = 0x0638C8
MODAL_INSTALLER_ADDRESS = 0x063900
RESERVED_WORD = b"\x00\x0f"
RETS = 0xC620
FRAMED_LINK_PREFIXES = frozenset({
    b"\x00\x2e", b"\x01\x2e", b"\x02\x2e", b"\x03\x2e",
    b"\x04\x2e", b"\x05\x2e", b"\x06\x2e", b"\x09\x2e",
    b"\x0a\x2e", b"\x2d\x2e", b"\x39\x2e", b"\x74\x2e",
})

# destination, linked source, exact byte length, descriptive name
OVERLAYS: tuple[tuple[int, int, int, str], ...] = (
    (0x2B6CE6, 0x486CE6, 0x022A, "modal_callback"),
    (0x2603BA, 0x4303BA, 0x03B8, "image_window_tail"),
    # The operation mode router at 2F:B644 calls logical 23:70E0.  Flat bank
    # 23 is resource data; source 40:70E0 is the complete LINK #9 action body
    # through the balanced 40:7582 RETS boundary.
    (0x2370E0, 0x4070E0, 0x04A4, "operation_action"),
    (0x277E84, 0x447E84, 0x0344, "modal_image_render"),
    (0x317772, 0x4E7772, 0x00B2, "modal_layout"),
    (0x2E0AF6, 0x4B0AF6, 0x018E, "modal_compositor"),
    (0x15FF04, 0x32FF04, 0x00FC, "resident_modal_text"),
    (0x0C8622, 0x298622, 0x379C, "resident_modal_document"),
    (0x2F4874, 0x4C4874, 0x0148, "modal_clip"),
    (0x2CF880, 0x49F880, 0x01D8, "modal_clip_step"),
    (0x32F402, 0x4FF402, 0x003C, "modal_release_wrapper"),
    (0x279F0A, 0x449F0A, 0x033A, "modal_release"),
    (0x2717AA, 0x4417AA, 0x035E, "modal_page_scan"),
    (0x271B08, 0x441B08, 0x035E, "modal_page_render"),
    # 32:B304 reaches this low resident entry from the natural storage/media
    # path.  The flat destination is absent from the update image, while the
    # +0x1d linked bank preserves one complete LINK #0x39 function through
    # its balanced 34:D85C UNLINK / 34:D85E RETS boundary.
    (0x17CCD0, 0x34CCD0, 0x0B90, "modal_media_browser"),
    (0x2D3298, 0x4A3298, 0x01C8, "modal_page_state"),
    (0x1B0000, 0x380000, 0x0900, "resident_modal_page"),
    (0x31A204, 0x4EA204, 0x00A6, "modal_layout_update"),
    (0x2FDB9C, 0x4CDB9C, 0x0126, "modal_item_compose"),
    (0x2EF446, 0x4BF446, 0x015C, "modal_item_format"),
    (0x31F1F2, 0x4EF1F2, 0x0090, "modal_worker"),
    (0x29DB0A, 0x46DB0A, 0x0292, "modal_worker_core"),
    (0x2F3CDE, 0x4C3CDE, 0x014A, "modal_buffer_prepare"),
    (0x32BE86, 0x4FBE86, 0x0050, "modal_field_decode"),
    (0x23DEA6, 0x40DEA6, 0x0480, "modal_field_expand"),
    (0x2CE9B0, 0x49E9B0, 0x01DA, "modal_buffer_commit"),
)

# Exact linked tail-dispatch entry.  It is deliberately an SJMP rather than a
# framed function and therefore has its own signature check below.
RAW_OVERLAYS: tuple[tuple[int, int, bytes, str], ...] = (
    (
        0x3213E8,
        0x4F13E8,
        bytes.fromhex("2E AD F6 0A"),
        "modal_compositor_dispatch",
    ),
)

# Segment 50 is mutable data RAM by this late boundary, so the exact linked
# bytes cannot be read back from it by a guest copy loop.  Encode this tiny
# balanced leaf as ordinary immediate stores instead.
EMBEDDED_OVERLAYS: tuple[tuple[int, int, bytes, str], ...] = (
    (
        0x333F5E,
        0x503F5E,
        bytes.fromhex(
            "00 2E F1 58 11 48 10 68 A2 00 F1 B5 4E 2A 11 48 "
            "10 68 A2 00 F1 B4 4C 2A 1F 38 00 2F 20 C6"
        ),
        "modal_flag_clear",
    ),
    (
        0x334476,
        0x504476,
        bytes.fromhex(
            "00 2E 0B 78 06 00 1B 6B 06 00 1B 79 06 00 01 19 "
            "F0 58 32 BD 88 CA F2 50 00 2F 20 C6"
        ),
        "modal_byte_set",
    ),
    (
        0x335AAC,
        0x505AAC,
        bytes.fromhex("10 68 A2 00 F0 88 B0 29 F1 88 B2 29 20 C6"),
        "modal_status_read",
    ),
    (
        0x302966,
        0x4D2966,
        bytes.fromhex(
            "05 2e f1 58 0b 78 06 00 1b 6b 06 00 06 48 f0 58 "
            "00 48 f0 58 1b 08 f1 70 fa ff 00 48 f1 58 f0 58 "
            "33 bd 9e 26 f8 50 1b 79 06 00 01 19 01 56 02 ac "
            "c0 29 f0 68 10 00 f1 68 00 d0 0b 6a f6 ff 1b 6a "
            "f8 ff 10 68 a2 00 f0 88 78 2a f0 74 10 00 00 56 "
            "01 ac 20 2a 00 48 00 ac 72 2a 1b 79 06 00 01 19 "
            "02 56 02 ac f8 29 10 68 a2 00 f0 88 78 2a f0 74 "
            "20 00 00 56 01 ac e4 29 00 48 00 ac 72 2a f0 68 "
            "10 00 f1 68 06 d0 0b 6a f6 ff 1b 6a f8 ff 00 ac "
            "20 2a 10 68 a2 00 f0 88 78 2a f0 74 40 00 00 56 "
            "01 ac 10 2a 00 48 00 ac 72 2a f0 68 10 00 f1 68 "
            "0c d0 0b 6a f6 ff 1b 6a f8 ff 06 48 f0 58 0b 78 "
            "f6 ff 1b 78 f8 ff f1 58 f0 58 1b 08 f1 70 fa ff "
            "00 48 f1 58 f0 58 25 bd 6e 20 fa 50 1b 79 fa ff "
            "01 18 f0 58 33 bd 02 1a f2 50 00 56 02 ac 70 2a "
            "1b 79 fa ff 01 18 f0 58 33 bd 42 43 f2 50 00 56 "
            "02 ac 70 2a 00 48 00 ac 72 2a 01 48 1f 38 00 2f "
            "20 c6"
        ),
        "operation_action_mode_predicate",
    ),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words_to_bytes(words: Sequence[int]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def program_bytes(program: bytes, address: int, size: int) -> bytes:
    offset = address - PROGRAM_BASE
    if offset < 0 or offset + size > len(program):
        raise ValueError(f"PRG source 0x{address:06x}+0x{size:x} is outside image")
    return program[offset:offset + size]


def split_copy_ranges(
    destination: int, source: int, length: int
) -> Iterable[tuple[int, int, int]]:
    """Split at 32-KiB DMCU data-page boundaries."""
    while length:
        destination_page = 0x8000 - (destination & 0x7FFF)
        source_page = 0x8000 - (source & 0x7FFF)
        chunk = min(length, destination_page, source_page)
        yield destination, source, chunk
        destination += chunk
        source += chunk
        length -= chunk


def copy_code_words(destination: int, source: int, length: int) -> list[int]:
    """Copy one page-bounded byte range using normal DMCU data accesses."""
    if not 0 < length <= 0xFFFF:
        raise ValueError("copy length must be between 1 and 65535 bytes")
    if (destination & 0x7FFF) + length > 0x8000:
        raise ValueError("destination copy crosses a 32-KiB data page")
    if (source & 0x7FFF) + length > 0x8000:
        raise ValueError("source copy crosses a 32-KiB data page")
    return [
        0x6810, destination >> 15,              # DS0 destination page
        0x6811, source >> 15,                   # DS1 source page
        0x68F1, destination & 0x7FFF,           # R1 in DS0 low half
        0x68F3, 0x8000 | (source & 0x7FFF),     # R3 in DS1 high half
        0x68F4, length,                         # R4 byte count
        0x5640,                                 # loop: CMP R4,#0
        0xD105,                                 # RJMP Z,+5
        0x2B13,                                 # MOVB [R1],[R3]
        0x5011,                                 # ADD R1,#1
        0x5031,                                 # ADD R3,#1
        0x5241,                                 # SUB R4,#1
        0xD0F9,                                 # RJMP ALWAYS,-7
        0x6810, 0x0000,                         # restore reset DS0
        0x6811, 0x0001,                         # restore reset DS1
    ]


def embedded_write_words(destination: int, payload: bytes) -> list[int]:
    if destination & 1 or len(payload) & 1 or not payload:
        raise ValueError("embedded overlay must contain positive whole words")
    if (destination & 0x7FFF) + len(payload) > 0x8000:
        raise ValueError("embedded overlay crosses a 32-KiB data page")
    words = [0x6810, destination >> 15]
    for index in range(0, len(payload), 2):
        value = int.from_bytes(payload[index:index + 2], "little")
        words.extend((0x68F0, value, 0xA8F0,
                      (destination & 0x7FFF) + index))
    words.extend((0x6810, 0x0000))
    return words


def modal_installer_words() -> list[int]:
    words: list[int] = []
    for destination, source, length, _name in OVERLAYS:
        for chunk_destination, chunk_source, chunk_length in split_copy_ranges(
            destination, source, length
        ):
            words.extend(copy_code_words(
                chunk_destination, chunk_source, chunk_length
            ))
    for destination, source, payload, _name in RAW_OVERLAYS:
        for chunk_destination, chunk_source, chunk_length in split_copy_ranges(
            destination, source, len(payload)
        ):
            words.extend(copy_code_words(
                chunk_destination, chunk_source, chunk_length
            ))
    for destination, _source, payload, _name in EMBEDDED_OVERLAYS:
        words.extend(embedded_write_words(destination, payload))
    words.append(RETS)
    return words


def validate_sources(program: bytes) -> None:
    for destination, source, length, name in OVERLAYS:
        payload = program_bytes(program, source, length)
        if payload[:2] not in FRAMED_LINK_PREFIXES:
            raise ValueError(
                f"{name} linked source 0x{source:06x} lacks a framed LINK"
            )
        if payload[-4:] != b"\x00\x2f\x20\xc6":
            raise ValueError(
                f"{name} linked source 0x{source:06x}+0x{length:x} "
                "lacks a balanced UNLINK/RETS boundary"
            )
        if destination + length > 0x1000000:
            raise ValueError(f"{name} destination exceeds 24-bit address space")
    for _destination, source, payload, name in RAW_OVERLAYS:
        if program_bytes(program, source, len(payload)) != payload:
            raise ValueError(f"{name} raw linked-source signature changed")
    for _destination, source, payload, name in EMBEDDED_OVERLAYS:
        if program_bytes(program, source, len(payload)) != payload:
            raise ValueError(f"{name} embedded linked-source signature changed")
        framed = payload[:2] in FRAMED_LINK_PREFIXES and (
            payload[-4:] == b"\x00\x2f\x20\xc6"
        )
        unframed_leaf = name == "modal_status_read" and payload[-2:] == b"\x20\xc6"
        if not framed and not unframed_leaf:
            raise ValueError(f"{name} is not an evidenced complete leaf")


def format_address(address: int) -> str:
    return f"{address >> 16:02X}:{address & 0xFFFF:04X}"


def patch_image(
    baseline: bytes,
    program: bytes,
    *,
    installer_address: int = MODAL_INSTALLER_ADDRESS,
    late_result_rets_address: int = LATE_RESULT_RETS_ADDRESS,
) -> tuple[bytes, dict[str, object]]:
    validate_sources(program)

    expected_tail = words_to_bytes((RETS,)) + RESERVED_WORD * 2
    if baseline[
        late_result_rets_address:late_result_rets_address + len(expected_tail)
    ] != expected_tail:
        raise ValueError(
            f"{format_address(late_result_rets_address)} is not the expected "
            "late-result RETS/reserved tail"
        )

    installer = words_to_bytes(modal_installer_words())
    installer_end = installer_address + len(installer)
    if installer_end > len(baseline):
        raise ValueError("modal installer falls outside resident ROM image")
    if baseline[installer_address:installer_end] != (
        RESERVED_WORD * (len(installer) // 2)
    ):
        raise ValueError(
            f"{format_address(installer_address)} modal-installer range is "
            "no longer reserved"
        )

    patched = bytearray(baseline)
    patched[
        late_result_rets_address:late_result_rets_address + 6
    ] = words_to_bytes((
        0xBD00 | (installer_address >> 16),
        installer_address & 0xFFFF,
        RETS,
    ))
    patched[installer_address:installer_end] = installer

    chunks = sum(
        1 for destination, source, length, _name in OVERLAYS
        for _chunk in split_copy_ranges(destination, source, length)
    )
    chunks += sum(
        1 for destination, source, payload, _name in RAW_OVERLAYS
        for _chunk in split_copy_ranges(destination, source, len(payload))
    )
    metadata: dict[str, object] = {
        "late_result_tail": (
            f"{format_address(late_result_rets_address)} -> "
            f"SCALL {format_address(installer_address)}; RETS"
        ),
        "modal_installer": format_address(installer_address),
        "modal_installer_bytes": len(installer),
        "copy_chunks": chunks,
        "guest_copies": [
            {
                "name": name,
                "destination": f"{destination >> 16:02X}:{destination & 0xFFFF:04X}",
                "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                "bytes": length,
            }
            for destination, source, length, name in OVERLAYS
        ],
        "guest_embedded_writes": [
            {
                "name": name,
                "destination": f"{destination >> 16:02X}:{destination & 0xFFFF:04X}",
                "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                "bytes": len(payload),
            }
            for destination, source, payload, name in EMBEDDED_OVERLAYS
        ],
        "guest_raw_copies": [
            {
                "name": name,
                "destination": f"{destination >> 16:02X}:{destination & 0xFFFF:04X}",
                "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                "bytes": len(payload),
            }
            for destination, source, payload, name in RAW_OVERLAYS
        ],
    }
    return bytes(patched), metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--installer-address",
        type=lambda value: int(value, 0),
        default=MODAL_INSTALLER_ADDRESS,
    )
    parser.add_argument(
        "--late-result-rets-address",
        type=lambda value: int(value, 0),
        default=LATE_RESULT_RETS_ADDRESS,
    )
    args = parser.parse_args()

    baseline = args.baseline.read_bytes()
    program = args.program.read_bytes()
    output, patch = patch_image(
        baseline,
        program,
        installer_address=args.installer_address,
        late_result_rets_address=args.late_result_rets_address,
    )
    args.output.write_bytes(output)
    print(
        f"installed {patch['modal_installer_bytes']} bytes of guest DMCU code "
        f"at 0x{args.installer_address:06x}; sha256={sha256(output)}"
    )

    if args.manifest:
        record = {
            "format": "np560-rom01-modal-callback-closure-patch-v1",
            "baseline": str(args.baseline),
            "baseline_sha256": sha256(baseline),
            "program": str(args.program),
            "program_sha256": sha256(program),
            "output": str(args.output),
            "output_sha256": sha256(output),
            "patch": patch,
            "execution_model": "ordinary guest DMCU instructions; no host HLE",
        }
        args.manifest.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
