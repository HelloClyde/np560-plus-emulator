#!/usr/bin/env python3
"""Tests for guest runtime-patch mirroring into source-pinned PRG copies."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qemu-dmcu"))

import mirror_np560_runtime_patches as mirror  # noqa: E402
from disassembly.np560_overlay_map import QemuMapping  # noqa: E402


class MirrorRuntimePatchesTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
