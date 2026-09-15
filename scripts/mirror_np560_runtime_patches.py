#!/usr/bin/env python3
"""Mirror guest-installed NP560 code patches into source-pinned PRG copies.

The reconstructed resident ROM installs application overlays and then patches
some call sites in their writable destinations.  A Harvard QEMU mapping may
source an overlay's instruction view from its immutable linked PRG copy to
protect it from unrelated NAND-buffer writes.  In that case the later guest
patch would otherwise be hidden.  This preflight extracts immediate program
writes from the actual guest installer routines, reports every conflict, and
mirrors only those evidenced words into a derived PRG image.

This is firmware preprocessing, not a host ROM service: the output contains
the same final instruction words that the reconstructed guest installer writes
to its destination code RAM.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_np560_reconstructed_rom as rom  # noqa: E402
from scripts.np560_overlay_map import (  # noqa: E402
    DEFAULT_QEMU_SOURCE,
    QemuMapping,
    parse_qemu_mappings,
)


PROGRAM_BASE = 0x200000


def parse_program_address(value: str) -> int:
    """Parse an exact byte address written as ``BB:OOOO`` or hexadecimal."""
    text = value.strip()
    if ":" in text:
        bank, offset = text.split(":", 1)
        address = (int(bank, 16) << 16) | int(offset, 16)
    else:
        address = int(text, 0)
    if not 0 <= address <= 0xFFFFFF:
        raise argparse.ArgumentTypeError(
            f"program address is outside the 24-bit address space: {value}"
        )
    return address


def current_resident_routines() -> dict[int, tuple[str, list[int]]]:
    """Build the v416 resident-ROM routine set used by the active emulator."""
    return rom.make_routines(
        initializer_overlay_probe=True,
        probe_rom_08_return=True,
        probe_rom_01_return=True,
        probe_system_main=True,
        probe_storage_global_templates=True,
        factory_linked_startup=True,
    )


def static_program_writes(
    routines: dict[int, tuple[str, Sequence[int]]],
) -> tuple[dict[int, list[int]], dict[int, set[str]]]:
    """Recover immediate DS0/MOV/store writes emitted by guest installers."""
    # Keep write order.  Several installers first copy an original call word
    # and then retarget that same word later in the same guest routine.  A set
    # makes preprocessing alternate between the two values on each run;
    # retaining the sequence makes the final guest-visible write idempotent.
    values: dict[int, list[int]] = defaultdict(list)
    origins: dict[int, set[str]] = defaultdict(set)
    for _base, (name, words) in routines.items():
        ds0: int | None = None
        index = 0
        while index < len(words):
            if words[index] == 0x6810 and index + 1 < len(words):
                ds0 = words[index + 1]
                index += 2
                continue
            if (
                ds0 is not None
                and words[index] == 0x68F0
                and index + 3 < len(words)
                and words[index + 2] == 0xA8F0
            ):
                address = (ds0 << 15) | (words[index + 3] & 0x7FFF)
                values[address].append(words[index + 1])
                origins[address].add(name)
                index += 4
                continue
            index += 1
    return dict(values), dict(origins)


def narrowest_source_mapping(
    address: int,
    mappings: Iterable[QemuMapping],
) -> QemuMapping | None:
    matches = [
        mapping for mapping in mappings
        if mapping.code and mapping.source is not None
        and mapping.base <= address and address + 2 <= mapping.end
    ]
    return min(matches, key=lambda mapping: mapping.size, default=None)


def firmware_word(firmware: bytes, address: int) -> int:
    offset = address - PROGRAM_BASE
    if offset < 0 or offset + 2 > len(firmware):
        raise ValueError(f"source address {address:06X} is outside the PRG")
    return int.from_bytes(firmware[offset:offset + 2], "little")


def planned_source_patches(
    firmware: bytes,
    mappings: Sequence[QemuMapping],
    writes: dict[int, Sequence[int]],
    origins: dict[int, set[str]],
) -> list[dict]:
    patches: dict[int, dict] = {}
    for destination, candidates in sorted(writes.items()):
        mapping = narrowest_source_mapping(destination, mappings)
        if mapping is None:
            continue
        source = mapping.source + destination - mapping.base
        # A code mapping with source=0 denotes a guest-generated/embedded
        # overlay rather than a byte range backed by NP560.PRG.  There is no
        # immutable PRG source to mirror in that case; the guest installer is
        # already the authoritative instruction producer.  Likewise, ignore
        # any mapping whose translated source falls outside this exact PRG
        # image instead of treating it as a corrupt firmware address.
        if not PROGRAM_BASE <= source or source + 2 > PROGRAM_BASE + len(
            firmware
        ):
            continue
        old_word = firmware_word(firmware, source)
        if not candidates:
            continue
        new_word = candidates[-1]
        if new_word == old_word:
            continue
        previous = patches.get(source)
        if previous is not None and previous["new_word"] != new_word:
            raise ValueError(
                f"conflicting mirrored values for source {source:06X}"
            )
        patches[source] = {
            "destination": destination,
            "source": source,
            "old_word": old_word,
            "new_word": new_word,
            "mapping": mapping.symbol,
            "origins": sorted(origins.get(destination, ())),
        }
    return [patches[address] for address in sorted(patches)]


def apply_source_patches(firmware: bytes, patches: Sequence[dict]) -> bytes:
    image = bytearray(firmware)
    for patch in patches:
        offset = patch["source"] - PROGRAM_BASE
        image[offset:offset + 2] = patch["new_word"].to_bytes(2, "little")
    return bytes(image)


def planned_resource_page_reader_relocations(firmware: bytes) -> list[dict]:
    """Retarget every source-proven 2D:261C call to relocated 5F:261C.

    Only three of these calls sit in QEMU source-pinned overlay mappings; the
    other eleven are copied later by application modules.  Preprocessing the
    exact shipped call words ensures every later guest copy inherits the same
    relocation that the reconstructed ROM installer writes to its linked
    destination.  Accepting the new first word makes repeated preprocessing
    idempotent, while the unchanged second word remains part of the signature.
    """
    old_first = 0xBD00 | (
        rom.APPLICATION_RESOURCE_PAGE_READ_LINKED_DESTINATION >> 16
    )
    new_first = 0xBD00 | (
        rom.APPLICATION_RESOURCE_PAGE_READ_OVERLAY_DESTINATION >> 16
    )
    target_pc = rom.APPLICATION_RESOURCE_PAGE_READ_LINKED_DESTINATION & 0xFFFF
    patches: list[dict] = []
    for source in rom.APPLICATION_RESOURCE_PAGE_READ_CALL_SOURCES:
        first = firmware_word(firmware, source)
        second = firmware_word(firmware, source + 2)
        if second != target_pc or first not in (old_first, new_first):
            raise ValueError(
                "resource page-reader call signature changed at "
                f"{source:06X}: {first:04X} {second:04X}"
            )
        if first == new_first:
            continue
        patches.append({
            "destination": source - 0x1D0000,
            "source": source,
            "old_word": first,
            "new_word": new_first,
            "mapping": "source-proven-resource-page-reader-call",
            "origins": [
                "application_resource_page_read_call_retarget_words"
            ],
        })
    return patches


def planned_system_flag_query_relocations(firmware: bytes) -> list[dict]:
    """Retarget every proven 33:58A6/B6/C6 query to resident 06:1E00.

    The three linked targets are interior instructions of the active flat
    segment-33 worker.  All listed source sites have been verified as direct
    SCALL instructions in complete functions; patch both far-call words
    because the collision-free resident family uses different PCs.
    """
    patches: list[dict] = []
    for source, linked_target, resident_target in (
            rom.SYSTEM_FLAG_QUERY_CALL_RELOCATIONS):
        destination = source - 0x1D0000
        old_words = (
            0xBD00 | (linked_target >> 16),
            linked_target & 0xFFFF,
        )
        new_words = (
            0xBD00 | (resident_target >> 16),
            resident_target & 0xFFFF,
        )
        current = (
            firmware_word(firmware, source),
            firmware_word(firmware, source + 2),
        )
        if current not in (old_words, new_words):
            raise ValueError(
                "system-flag query call signature changed at "
                f"{source:06X}: {current[0]:04X} {current[1]:04X}"
            )
        for index, (old_word, new_word) in enumerate(zip(current, new_words)):
            if old_word == new_word:
                continue
            patches.append({
                "destination": destination + index * 2,
                "source": source + index * 2,
                "old_word": old_word,
                "new_word": new_word,
                "mapping": "source-proven-system-flag-query-call",
                "origins": ["system_flag_query_call_relocation"],
            })
    return patches


def planned_render_line_relocations(firmware: bytes) -> list[dict]:
    """Retarget drawing calls while preserving flat 32:CF38 continuation.

    The shipped 32:5F94 call is intentionally absent from the source list: it
    enters the original flat 32:CF38 continuation with an inherited frame.
    Every listed call is a signature-checked framed-renderer call, either in
    the live 20..33 image or in its +0x1D application-bank source copy.
    """
    old_first = 0xBD00 | (
        rom.APPLICATION_MAIN_ACTION_RENDER_LINE_LINKED_DESTINATION >> 16
    )
    new_first = 0xBD00 | (
        rom.APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_DESTINATION >> 16
    )
    target_pc = (
        rom.APPLICATION_MAIN_ACTION_RENDER_LINE_LINKED_DESTINATION & 0xFFFF
    )
    patches: list[dict] = []
    for source, destination in zip(
            rom.APPLICATION_MAIN_ACTION_RENDER_LINE_CALL_SOURCES,
            rom.APPLICATION_MAIN_ACTION_RENDER_LINE_CALL_DESTINATIONS,
            strict=True):
        first = firmware_word(firmware, source)
        second = firmware_word(firmware, source + 2)
        if second != target_pc or first not in (old_first, new_first):
            raise ValueError(
                "render-line call signature changed at "
                f"{source:06X}: {first:04X} {second:04X}"
            )
        if first == new_first:
            continue
        patches.append({
            "destination": destination,
            "source": source,
            "old_word": first,
            "new_word": new_first,
            "mapping": "source-proven-render-line-call",
            "origins": ["application_main_action_render_line_relocation"],
        })
    return patches


def planned_resource_open_wrapper_relocations(firmware: bytes) -> list[dict]:
    """Retarget true SCALLs while preserving flat 32:B63C fallthrough.

    Live NPE launch reaches 32:B63C sequentially from 32:B638 as part of the
    large flat decoder.  Only the signature-checked call sites receive the
    collision-free 5F:B63C wrapper; preprocessing never changes the flat
    continuation itself.
    """
    old_first = 0xBD00 | (
        rom.APPLICATION_RESOURCE_OPEN_WRAPPER_LINKED_DESTINATION >> 16
    )
    new_first = 0xBD00 | (
        rom.APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_DESTINATION >> 16
    )
    target_pc = (
        rom.APPLICATION_RESOURCE_OPEN_WRAPPER_LINKED_DESTINATION & 0xFFFF
    )
    patches: list[dict] = []
    for source, destination in zip(
            rom.APPLICATION_RESOURCE_OPEN_WRAPPER_CALL_SOURCES,
            rom.APPLICATION_RESOURCE_OPEN_WRAPPER_CALL_DESTINATIONS,
            strict=True):
        first = firmware_word(firmware, source)
        second = firmware_word(firmware, source + 2)
        if second != target_pc or first not in (old_first, new_first):
            raise ValueError(
                "resource-open wrapper call signature changed at "
                f"{source:06X}: {first:04X} {second:04X}"
            )
        if first == new_first:
            continue
        patches.append({
            "destination": destination,
            "source": source,
            "old_word": first,
            "new_word": new_first,
            "mapping": "source-proven-resource-open-wrapper-call",
            "origins": ["application_resource_open_wrapper_relocation"],
        })
    return patches


def planned_npe_bitmap_decode_relocations(firmware: bytes) -> list[dict]:
    """Retarget the six live callers away from flat 27:716C.

    The resident 1F:1464 caller is patched while its source-3C body is embedded
    in reconstructed ROM.  These six segment-2B callers remain in the runtime
    PRG and therefore require the same signature-checked segment relocation.
    """
    old_first = 0xBD00 | (
        rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_LINKED_DESTINATION >> 16
    )
    new_first = 0xBD00 | (
        rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_OVERLAY_DESTINATION >> 16
    )
    target_pc = (
        rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_LINKED_DESTINATION & 0xFFFF
    )
    patches: list[dict] = []
    for source in rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_CALL_SOURCES:
        first = firmware_word(firmware, source)
        second = firmware_word(firmware, source + 2)
        if second != target_pc or first not in (old_first, new_first):
            raise ValueError(
                "NPE bitmap-decode call signature changed at "
                f"{source:06X}: {first:04X} {second:04X}"
            )
        if first == new_first:
            continue
        patches.append({
            "destination": source,
            "source": source,
            "old_word": first,
            "new_word": new_first,
            "mapping": "source-proven-npe-bitmap-decode-call",
            "origins": ["application_npe_bitmap_decode_relocation"],
        })
    return patches


def planned_npe_stream_classify_relocations(firmware: bytes) -> list[dict]:
    """Retarget the two live calls away from flat-midword 2B:4E3E."""
    old_first = 0xBD00 | (
        rom.APPLICATION_NPE_STREAM_CLASSIFY_LINKED_DESTINATION >> 16
    )
    new_first = 0xBD00 | (
        rom.APPLICATION_NPE_STREAM_CLASSIFY_OVERLAY_DESTINATION >> 16
    )
    target_pc = (
        rom.APPLICATION_NPE_STREAM_CLASSIFY_LINKED_DESTINATION & 0xFFFF
    )
    patches: list[dict] = []
    for source in rom.APPLICATION_NPE_STREAM_CLASSIFY_CALL_SOURCES:
        first = firmware_word(firmware, source)
        second = firmware_word(firmware, source + 2)
        if second != target_pc or first not in (old_first, new_first):
            raise ValueError(
                "NPE stream-classify call signature changed at "
                f"{source:06X}: {first:04X} {second:04X}"
            )
        if first == new_first:
            continue
        patches.append({
            "destination": source,
            "source": source,
            "old_word": first,
            "new_word": new_first,
            "mapping": "source-proven-npe-stream-classify-call",
            "origins": ["application_npe_stream_classify_relocation"],
        })
    return patches


def planned_npe_state_dispatch_relocations(firmware: bytes) -> list[dict]:
    """Retarget dynamically proven application calls from flat 2B:0000."""
    old_first = 0xBD00 | (
        rom.APPLICATION_NPE_STATE_DISPATCH_LINKED_DESTINATION >> 16
    )
    new_first = 0xBD00 | (
        rom.APPLICATION_NPE_STATE_DISPATCH_OVERLAY_DESTINATION >> 16
    )
    target_pc = rom.APPLICATION_NPE_STATE_DISPATCH_LINKED_DESTINATION & 0xFFFF
    patches: list[dict] = []
    for source, destination in zip(
            rom.APPLICATION_NPE_STATE_DISPATCH_CALL_SOURCES,
            rom.APPLICATION_NPE_STATE_DISPATCH_CALL_DESTINATIONS,
            strict=True):
        first = firmware_word(firmware, source)
        second = firmware_word(firmware, source + 2)
        if second != target_pc or first not in (old_first, new_first):
            raise ValueError(
                "NPE state-dispatch call signature changed at "
                f"{source:06X}: {first:04X} {second:04X}"
            )
        if first == new_first:
            continue
        patches.append({
            "destination": destination,
            "source": source,
            "old_word": first,
            "new_word": new_first,
            "mapping": "source-proven-npe-state-dispatch-call",
            "origins": ["application_npe_state_dispatch_relocation"],
        })
    return patches


def planned_npe_bitmap_context_relocations(firmware: bytes) -> list[dict]:
    """Retarget source-proven calls away from flat 29:8202."""
    old_first = 0xBD00 | (
        rom.APPLICATION_NPE_BITMAP_CONTEXT_LINKED_DESTINATION >> 16
    )
    new_first = 0xBD00 | (
        rom.APPLICATION_NPE_BITMAP_CONTEXT_OVERLAY_DESTINATION >> 16
    )
    target_pc = rom.APPLICATION_NPE_BITMAP_CONTEXT_LINKED_DESTINATION & 0xFFFF
    patches: list[dict] = []
    for source, destination in zip(
            rom.APPLICATION_NPE_BITMAP_CONTEXT_CALL_SOURCES,
            rom.APPLICATION_NPE_BITMAP_CONTEXT_CALL_DESTINATIONS,
            strict=True):
        first = firmware_word(firmware, source)
        second = firmware_word(firmware, source + 2)
        if second != target_pc or first not in (old_first, new_first):
            raise ValueError(
                "NPE bitmap-context call signature changed at "
                f"{source:06X}: {first:04X} {second:04X}"
            )
        if first == new_first:
            continue
        patches.append({
            "destination": destination,
            "source": source,
            "old_word": first,
            "new_word": new_first,
            "mapping": "source-proven-npe-bitmap-context-call",
            "origins": ["application_npe_bitmap_context_relocation"],
        })
    return patches


def planned_npe_node_transfer_relocations(firmware: bytes) -> list[dict]:
    """Retarget the node-transfer entry and its relocated sector probe.

    The node body is source-pinned from 38:C5EC after its writable logical
    5F:C5EC window is populated with transfer data.  Mirror the resident
    installer's internal 5F:CD04 call rewrite into that immutable source too;
    otherwise instruction fetch sees the shipped ``BD20 F928`` and enters the
    collision which the recovered 5F:F928 sector probe was created to avoid.
    """
    old_first = 0xBD00 | (
        rom.APPLICATION_NPE_NODE_TRANSFER_LINKED_DESTINATION >> 16
    )
    new_first = 0xBD00 | (
        rom.APPLICATION_NPE_NODE_TRANSFER_OVERLAY_DESTINATION >> 16
    )
    target_pc = rom.APPLICATION_NPE_NODE_TRANSFER_LINKED_DESTINATION & 0xFFFF
    patches: list[dict] = []
    for source, destination in zip(
            rom.APPLICATION_NPE_NODE_TRANSFER_CALL_SOURCES,
            rom.APPLICATION_NPE_NODE_TRANSFER_CALL_DESTINATIONS,
            strict=True):
        first = firmware_word(firmware, source)
        second = firmware_word(firmware, source + 2)
        if second != target_pc or first not in (old_first, new_first):
            raise ValueError(
                "NPE node-transfer call signature changed at "
                f"{source:06X}: {first:04X} {second:04X}"
            )
        if first == new_first:
            continue
        patches.append({
            "destination": destination,
            "source": source,
            "old_word": first,
            "new_word": new_first,
            "mapping": "source-proven-npe-node-transfer-call",
            "origins": ["application_npe_node_transfer_relocation"],
        })

    dependency_source = rom.RESIDENT_TRANSFORM_1B_SECTOR_PROBE_CALL_SOURCE
    dependency_destination = (
        rom.APPLICATION_NPE_NODE_TRANSFER_OVERLAY_DESTINATION
        + dependency_source
        - rom.APPLICATION_NPE_NODE_TRANSFER_OVERLAY_SOURCE
    )
    dependency_old_first = 0xBD00 | (
        rom.APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION >> 16
    )
    dependency_new_first = 0xBD00 | (
        rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION >> 16
    )
    dependency_pc = (
        rom.APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION & 0xFFFF
    )
    first = firmware_word(firmware, dependency_source)
    second = firmware_word(firmware, dependency_source + 2)
    if second != dependency_pc or first not in (
            dependency_old_first, dependency_new_first):
        raise ValueError(
            "NPE node-transfer sector-probe call signature changed at "
            f"{dependency_source:06X}: {first:04X} {second:04X}"
        )
    if first != dependency_new_first:
        patches.append({
            "destination": dependency_destination,
            "source": dependency_source,
            "old_word": first,
            "new_word": dependency_new_first,
            "mapping": "source-pinned-npe-node-transfer-dependency",
            "origins": ["resident_transform_1b_sector_probe_relocation"],
        })
    return patches


def merge_source_patches(*groups: Sequence[dict]) -> list[dict]:
    """Merge independently evidenced PRG patches by source address."""
    merged: dict[int, dict] = {}
    for group in groups:
        for patch in group:
            previous = merged.get(patch["source"])
            if previous is None:
                merged[patch["source"]] = patch
                continue
            if previous["new_word"] != patch["new_word"]:
                raise ValueError(
                    "conflicting mirrored values for source "
                    f"{patch['source']:06X}"
                )
            previous["origins"] = sorted(set(previous["origins"]) | set(
                patch["origins"]
            ))
    return [merged[address] for address in sorted(merged)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--qemu-source", type=Path, default=DEFAULT_QEMU_SOURCE)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--only-destination",
        type=parse_program_address,
        action="append",
        default=[],
        metavar="BB:OOOO",
        help=(
            "mirror only this exact destination word; repeat for a "
            "controlled experiment"
        ),
    )
    args = parser.parse_args()

    firmware = args.firmware.read_bytes()
    mappings = parse_qemu_mappings(
        args.qemu_source.read_text(encoding="utf-8")
    )
    writes, origins = static_program_writes(current_resident_routines())
    patches = merge_source_patches(
        planned_source_patches(firmware, mappings, writes, origins),
        planned_resource_page_reader_relocations(firmware),
        planned_system_flag_query_relocations(firmware),
        planned_render_line_relocations(firmware),
        planned_resource_open_wrapper_relocations(firmware),
        planned_npe_state_dispatch_relocations(firmware),
        planned_npe_stream_classify_relocations(firmware),
        planned_npe_bitmap_decode_relocations(firmware),
        planned_npe_bitmap_context_relocations(firmware),
        planned_npe_node_transfer_relocations(firmware),
    )
    if args.only_destination:
        allowed = set(args.only_destination)
        patches = [
            patch for patch in patches
            if patch["destination"] in allowed
        ]
        found = {patch["destination"] for patch in patches}
        missing = allowed - found
        if missing:
            parser.error(
                "requested destination word is not an evidenced pending "
                "source patch: "
                + ", ".join(
                    f"{address >> 16:02X}:{address & 0xFFFF:04X}"
                    for address in sorted(missing)
                )
            )
    output = apply_source_patches(firmware, patches)
    document = {
        "format": "np560-source-pinned-runtime-patches-v1",
        "hardware_rom_service": False,
        "input": str(args.firmware.resolve()),
        "input_sha256": hashlib.sha256(firmware).hexdigest(),
        "output": str(args.output.resolve()),
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "patch_words": len(patches),
        "only_destinations": [
            f"{address >> 16:02X}:{address & 0xFFFF:04X}"
            for address in sorted(set(args.only_destination))
        ],
        "patches": [
            {
                **patch,
                "destination": f"{patch['destination'] >> 16:02X}:"
                               f"{patch['destination'] & 0xFFFF:04X}",
                "source": f"{patch['source'] >> 16:02X}:"
                          f"{patch['source'] & 0xFFFF:04X}",
                "old_word": f"{patch['old_word']:04X}",
                "new_word": f"{patch['new_word']:04X}",
            }
            for patch in patches
        ],
    }
    print(json.dumps(document, ensure_ascii=False, indent=2))
    if not args.dry_run:
        args.output.write_bytes(output)
        manifest = args.manifest or args.output.with_suffix(".json")
        manifest.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
