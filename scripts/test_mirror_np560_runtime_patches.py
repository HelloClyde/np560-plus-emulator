#!/usr/bin/env python3
"""Tests for guest runtime-patch mirroring into source-pinned PRG copies."""

from __future__ import annotations

import unittest

from scripts import mirror_np560_runtime_patches as mirror
from scripts.np560_overlay_map import QemuMapping


class MirrorRuntimePatchesTests(unittest.TestCase):
    def test_parses_exact_destination_addresses(self) -> None:
        self.assertEqual(mirror.parse_program_address("5F:FA1E"), 0x5FFA1E)
        self.assertEqual(mirror.parse_program_address("0x5ffb44"), 0x5FFB44)

    def test_extracts_immediate_guest_program_write(self) -> None:
        routines = {
            0x100: ("installer", [
                0x6810, 0x0064,
                0x68F0, 0xBD5F, 0xA8F0, 0x2F20,
            ]),
        }
        values, origins = mirror.static_program_writes(routines)
        self.assertEqual(values, {0x322F20: [0xBD5F]})
        self.assertEqual(origins, {0x322F20: {"installer"}})

    def test_mirrors_only_changed_word_to_linked_source(self) -> None:
        firmware = bytearray(0x200000)
        source = 0x302000
        offset = source - mirror.PROGRAM_BASE
        firmware[offset:offset + 2] = (0xBD33).to_bytes(2, "little")
        mapping = QemuMapping(0x202000, 0x40, "CODE", True, source)
        patches = mirror.planned_source_patches(
            bytes(firmware), [mapping], {0x202000: [0xBD5F]},
            {0x202000: {"installer"}},
        )
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]["source"], source)
        output = mirror.apply_source_patches(bytes(firmware), patches)
        self.assertEqual(mirror.firmware_word(output, source), 0xBD5F)

    def test_last_guest_write_wins_and_preprocessing_is_idempotent(self) -> None:
        firmware = bytearray(0x200000)
        source = 0x302000
        offset = source - mirror.PROGRAM_BASE
        mapping = QemuMapping(0x202000, 0x40, "CODE", True, source)
        writes = {0x202000: [0xBD33, 0xBD5F]}
        origins = {0x202000: {"installer"}}

        firmware[offset:offset + 2] = (0xBD33).to_bytes(2, "little")
        first = mirror.planned_source_patches(
            bytes(firmware), [mapping], writes, origins,
        )
        self.assertEqual([item["new_word"] for item in first], [0xBD5F])
        output = mirror.apply_source_patches(bytes(firmware), first)
        self.assertEqual(
            mirror.planned_source_patches(output, [mapping], writes, origins),
            [],
        )

    def test_ignores_embedded_mapping_without_prg_source(self) -> None:
        firmware = bytes(0x200000)
        mapping = QemuMapping(0x306490, 0x40, "EMBEDDED", True, 0)
        self.assertEqual(
            mirror.planned_source_patches(
                firmware,
                [mapping],
                {0x306490: [0x2E00]},
                {0x306490: {"installer"}},
            ),
            [],
        )

    def test_retargets_all_source_proven_resource_page_reader_calls(
            self) -> None:
        firmware = bytearray(0x300000)
        for source in mirror.rom.APPLICATION_RESOURCE_PAGE_READ_CALL_SOURCES:
            offset = source - mirror.PROGRAM_BASE
            firmware[offset:offset + 4] = bytes.fromhex("2dbd1c26")

        patches = mirror.planned_resource_page_reader_relocations(
            bytes(firmware)
        )
        self.assertEqual(len(patches), 14)
        self.assertEqual(
            [patch["source"] for patch in patches],
            list(mirror.rom.APPLICATION_RESOURCE_PAGE_READ_CALL_SOURCES),
        )
        output = mirror.apply_source_patches(bytes(firmware), patches)
        for source in mirror.rom.APPLICATION_RESOURCE_PAGE_READ_CALL_SOURCES:
            self.assertEqual(mirror.firmware_word(output, source), 0xBD5F)
            self.assertEqual(mirror.firmware_word(output, source + 2), 0x261C)
        self.assertEqual(
            mirror.planned_resource_page_reader_relocations(output),
            [],
        )

    def test_resource_page_reader_relocation_rejects_changed_signature(
            self) -> None:
        firmware = bytearray(0x300000)
        for source in mirror.rom.APPLICATION_RESOURCE_PAGE_READ_CALL_SOURCES:
            offset = source - mirror.PROGRAM_BASE
            firmware[offset:offset + 4] = bytes.fromhex("2dbd1c26")
        first = mirror.rom.APPLICATION_RESOURCE_PAGE_READ_CALL_SOURCES[0]
        offset = first - mirror.PROGRAM_BASE
        firmware[offset + 2:offset + 4] = (0x261E).to_bytes(2, "little")
        with self.assertRaisesRegex(ValueError, "signature changed"):
            mirror.planned_resource_page_reader_relocations(bytes(firmware))

    def test_retargets_all_source_proven_system_flag_query_calls(self) -> None:
        firmware = bytearray(0x300000)
        for source, linked_target, _resident_target in (
                mirror.rom.SYSTEM_FLAG_QUERY_CALL_RELOCATIONS):
            offset = source - mirror.PROGRAM_BASE
            words = (
                0xBD00 | (linked_target >> 16),
                linked_target & 0xFFFF,
            )
            firmware[offset:offset + 4] = b"".join(
                word.to_bytes(2, "little") for word in words
            )

        patches = mirror.planned_system_flag_query_relocations(bytes(firmware))
        self.assertEqual(len(patches), 20)
        output = mirror.apply_source_patches(bytes(firmware), patches)
        for source, _linked_target, resident_target in (
                mirror.rom.SYSTEM_FLAG_QUERY_CALL_RELOCATIONS):
            self.assertEqual(
                mirror.firmware_word(output, source),
                0xBD00 | (resident_target >> 16),
            )
            self.assertEqual(
                mirror.firmware_word(output, source + 2),
                resident_target & 0xFFFF,
            )
        self.assertEqual(
            mirror.planned_system_flag_query_relocations(output),
            [],
        )

    def test_system_flag_query_relocation_rejects_changed_signature(
            self) -> None:
        firmware = bytearray(0x300000)
        for source, linked_target, _resident_target in (
                mirror.rom.SYSTEM_FLAG_QUERY_CALL_RELOCATIONS):
            offset = source - mirror.PROGRAM_BASE
            firmware[offset:offset + 4] = b"".join(
                word.to_bytes(2, "little")
                for word in (
                    0xBD00 | (linked_target >> 16),
                    linked_target & 0xFFFF,
                )
            )
        first = mirror.rom.SYSTEM_FLAG_QUERY_CALL_RELOCATIONS[0][0]
        offset = first - mirror.PROGRAM_BASE
        firmware[offset + 2:offset + 4] = (0x1234).to_bytes(2, "little")
        with self.assertRaisesRegex(ValueError, "signature changed"):
            mirror.planned_system_flag_query_relocations(bytes(firmware))

    def test_retargets_render_line_calls_but_preserves_flat_continuation(
            self) -> None:
        firmware = bytearray(0x300000)
        old_first = 0xBD00 | (
            mirror.rom.APPLICATION_MAIN_ACTION_RENDER_LINE_LINKED_DESTINATION
            >> 16
        )
        target_pc = (
            mirror.rom.APPLICATION_MAIN_ACTION_RENDER_LINE_LINKED_DESTINATION
            & 0xFFFF
        )
        for source in (
                mirror.rom.APPLICATION_MAIN_ACTION_RENDER_LINE_CALL_SOURCES):
            offset = source - mirror.PROGRAM_BASE
            firmware[offset:offset + 2] = old_first.to_bytes(2, "little")
            firmware[offset + 2:offset + 4] = target_pc.to_bytes(2, "little")
        continuation = 0x325F94
        continuation_offset = continuation - mirror.PROGRAM_BASE
        firmware[continuation_offset:continuation_offset + 2] = (
            old_first.to_bytes(2, "little")
        )
        firmware[continuation_offset + 2:continuation_offset + 4] = (
            target_pc.to_bytes(2, "little")
        )

        patches = mirror.planned_render_line_relocations(bytes(firmware))
        self.assertEqual(
            [patch["source"] for patch in patches],
            list(mirror.rom.APPLICATION_MAIN_ACTION_RENDER_LINE_CALL_SOURCES),
        )
        output = mirror.apply_source_patches(bytes(firmware), patches)
        for source in (
                mirror.rom.APPLICATION_MAIN_ACTION_RENDER_LINE_CALL_SOURCES):
            self.assertEqual(mirror.firmware_word(output, source), 0xBD5F)
            self.assertEqual(mirror.firmware_word(output, source + 2), 0xCF38)
        self.assertEqual(
            mirror.firmware_word(output, continuation), old_first,
        )
        self.assertEqual(
            mirror.planned_render_line_relocations(output), [],
        )

    def test_retargets_resource_open_calls_but_preserves_flat_continuation(
            self) -> None:
        firmware = bytearray(0x300000)
        for source in (
                mirror.rom.APPLICATION_RESOURCE_OPEN_WRAPPER_CALL_SOURCES):
            offset = source - mirror.PROGRAM_BASE
            firmware[offset:offset + 4] = bytes.fromhex("32bd3cb6")
        continuation = (
            mirror.rom.APPLICATION_RESOURCE_OPEN_WRAPPER_LINKED_DESTINATION
        )
        continuation_offset = continuation - mirror.PROGRAM_BASE
        continuation_words = bytes.fromhex("f16800f1")
        firmware[
            continuation_offset:continuation_offset + 4
        ] = continuation_words

        patches = mirror.planned_resource_open_wrapper_relocations(
            bytes(firmware)
        )
        self.assertEqual(
            [patch["source"] for patch in patches],
            list(
                mirror.rom.APPLICATION_RESOURCE_OPEN_WRAPPER_CALL_SOURCES
            ),
        )
        output = mirror.apply_source_patches(bytes(firmware), patches)
        for source in (
                mirror.rom.APPLICATION_RESOURCE_OPEN_WRAPPER_CALL_SOURCES):
            self.assertEqual(mirror.firmware_word(output, source), 0xBD5F)
            self.assertEqual(
                mirror.firmware_word(output, source + 2), 0xB63C,
            )
        self.assertEqual(
            output[
                continuation_offset:continuation_offset + 4
            ],
            continuation_words,
        )
        self.assertEqual(
            mirror.planned_resource_open_wrapper_relocations(output), [],
        )

    def test_retargets_npe_bitmap_decode_runtime_calls(self) -> None:
        firmware = bytearray(0x300000)
        old_first = 0xBD00 | (
            mirror.rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_LINKED_DESTINATION
            >> 16
        )
        target_pc = (
            mirror.rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_LINKED_DESTINATION
            & 0xFFFF
        )
        for source in (
                mirror.rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_CALL_SOURCES):
            offset = source - mirror.PROGRAM_BASE
            firmware[offset:offset + 2] = old_first.to_bytes(2, "little")
            firmware[offset + 2:offset + 4] = target_pc.to_bytes(2, "little")

        patches = mirror.planned_npe_bitmap_decode_relocations(bytes(firmware))
        self.assertEqual(
            [patch["source"] for patch in patches],
            list(mirror.rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_CALL_SOURCES),
        )
        output = mirror.apply_source_patches(bytes(firmware), patches)
        for source in (
                mirror.rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_CALL_SOURCES):
            self.assertEqual(mirror.firmware_word(output, source), 0xBD5F)
            self.assertEqual(mirror.firmware_word(output, source + 2), 0x716C)
        self.assertEqual(
            mirror.planned_npe_bitmap_decode_relocations(output), [],
        )

    def test_retargets_npe_stream_classify_runtime_calls(self) -> None:
        firmware = bytearray(0x300000)
        old_first = 0xBD00 | (
            mirror.rom.APPLICATION_NPE_STREAM_CLASSIFY_LINKED_DESTINATION
            >> 16
        )
        target_pc = (
            mirror.rom.APPLICATION_NPE_STREAM_CLASSIFY_LINKED_DESTINATION
            & 0xFFFF
        )
        for source in (
                mirror.rom.APPLICATION_NPE_STREAM_CLASSIFY_CALL_SOURCES):
            offset = source - mirror.PROGRAM_BASE
            firmware[offset:offset + 2] = old_first.to_bytes(2, "little")
            firmware[offset + 2:offset + 4] = target_pc.to_bytes(2, "little")

        patches = mirror.planned_npe_stream_classify_relocations(
            bytes(firmware)
        )
        self.assertEqual(
            [patch["source"] for patch in patches],
            list(mirror.rom.APPLICATION_NPE_STREAM_CLASSIFY_CALL_SOURCES),
        )
        output = mirror.apply_source_patches(bytes(firmware), patches)
        for source in (
                mirror.rom.APPLICATION_NPE_STREAM_CLASSIFY_CALL_SOURCES):
            self.assertEqual(mirror.firmware_word(output, source), 0xBD5F)
            self.assertEqual(mirror.firmware_word(output, source + 2), 0x4E3E)
        self.assertEqual(
            mirror.planned_npe_stream_classify_relocations(output), [],
        )

    def test_retargets_dynamically_proven_npe_state_dispatch_call(self) -> None:
        firmware = bytearray(0x300000)
        old_first = 0xBD00 | (
            mirror.rom.APPLICATION_NPE_STATE_DISPATCH_LINKED_DESTINATION
            >> 16
        )
        target_pc = (
            mirror.rom.APPLICATION_NPE_STATE_DISPATCH_LINKED_DESTINATION
            & 0xFFFF
        )
        for source in mirror.rom.APPLICATION_NPE_STATE_DISPATCH_CALL_SOURCES:
            offset = source - mirror.PROGRAM_BASE
            firmware[offset:offset + 2] = old_first.to_bytes(2, "little")
            firmware[offset + 2:offset + 4] = target_pc.to_bytes(2, "little")

        patches = mirror.planned_npe_state_dispatch_relocations(
            bytes(firmware)
        )
        self.assertEqual(
            [patch["source"] for patch in patches],
            list(mirror.rom.APPLICATION_NPE_STATE_DISPATCH_CALL_SOURCES),
        )
        self.assertEqual(
            [patch["destination"] for patch in patches],
            list(mirror.rom.APPLICATION_NPE_STATE_DISPATCH_CALL_DESTINATIONS),
        )
        output = mirror.apply_source_patches(bytes(firmware), patches)
        for source in mirror.rom.APPLICATION_NPE_STATE_DISPATCH_CALL_SOURCES:
            self.assertEqual(mirror.firmware_word(output, source), 0xBD5F)
            self.assertEqual(mirror.firmware_word(output, source + 2), 0x0000)
        self.assertEqual(
            mirror.planned_npe_state_dispatch_relocations(output), [],
        )

    def test_retargets_npe_bitmap_context_calls(self) -> None:
        firmware = bytearray(0x300000)
        old_first = 0xBD00 | (
            mirror.rom.APPLICATION_NPE_BITMAP_CONTEXT_LINKED_DESTINATION >> 16
        )
        target_pc = (
            mirror.rom.APPLICATION_NPE_BITMAP_CONTEXT_LINKED_DESTINATION
            & 0xFFFF
        )
        for source in mirror.rom.APPLICATION_NPE_BITMAP_CONTEXT_CALL_SOURCES:
            offset = source - mirror.PROGRAM_BASE
            firmware[offset:offset + 2] = old_first.to_bytes(2, "little")
            firmware[offset + 2:offset + 4] = target_pc.to_bytes(2, "little")

        patches = mirror.planned_npe_bitmap_context_relocations(bytes(firmware))
        self.assertEqual(
            [patch["source"] for patch in patches],
            list(mirror.rom.APPLICATION_NPE_BITMAP_CONTEXT_CALL_SOURCES),
        )
        output = mirror.apply_source_patches(bytes(firmware), patches)
        for source in mirror.rom.APPLICATION_NPE_BITMAP_CONTEXT_CALL_SOURCES:
            self.assertEqual(mirror.firmware_word(output, source), 0xBD5F)
            self.assertEqual(mirror.firmware_word(output, source + 2), 0x8202)
        self.assertEqual(
            mirror.planned_npe_bitmap_context_relocations(output), [],
        )

    def test_retargets_npe_node_transfer_calls(self) -> None:
        firmware = bytearray(0x300000)
        old_first = 0xBD00 | (
            mirror.rom.APPLICATION_NPE_NODE_TRANSFER_LINKED_DESTINATION >> 16
        )
        target_pc = (
            mirror.rom.APPLICATION_NPE_NODE_TRANSFER_LINKED_DESTINATION
            & 0xFFFF
        )
        for source in mirror.rom.APPLICATION_NPE_NODE_TRANSFER_CALL_SOURCES:
            offset = source - mirror.PROGRAM_BASE
            firmware[offset:offset + 2] = old_first.to_bytes(2, "little")
            firmware[offset + 2:offset + 4] = target_pc.to_bytes(2, "little")

        dependency_source = (
            mirror.rom.RESIDENT_TRANSFORM_1B_SECTOR_PROBE_CALL_SOURCE
        )
        dependency_offset = dependency_source - mirror.PROGRAM_BASE
        firmware[dependency_offset:dependency_offset + 2] = (
            0xBD20
        ).to_bytes(2, "little")
        firmware[dependency_offset + 2:dependency_offset + 4] = (
            0xF928
        ).to_bytes(2, "little")

        patches = mirror.planned_npe_node_transfer_relocations(bytes(firmware))
        self.assertEqual(
            [patch["source"] for patch in patches],
            [
                *mirror.rom.APPLICATION_NPE_NODE_TRANSFER_CALL_SOURCES,
                dependency_source,
            ],
        )
        output = mirror.apply_source_patches(bytes(firmware), patches)
        for source in mirror.rom.APPLICATION_NPE_NODE_TRANSFER_CALL_SOURCES:
            self.assertEqual(mirror.firmware_word(output, source), 0xBD5F)
            self.assertEqual(mirror.firmware_word(output, source + 2), 0xC5EC)
        self.assertEqual(
            mirror.firmware_word(output, dependency_source), 0xBD5F,
        )
        self.assertEqual(
            mirror.firmware_word(output, dependency_source + 2), 0xF928,
        )
        dependency_patch = next(
            patch for patch in patches
            if patch["source"] == dependency_source
        )
        self.assertEqual(dependency_patch["destination"], 0x5FCD04)
        self.assertEqual(
            mirror.planned_npe_node_transfer_relocations(output), [],
        )


if __name__ == "__main__":
    unittest.main()
