#!/usr/bin/env python3

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest

from scripts import patch_np560_rom01_late_result_table as patch


class LateResultTablePatchTests(unittest.TestCase):
    def make_images(self) -> tuple[bytes, bytes]:
        baseline = bytearray(patch.LATE_INSTALLER_ADDRESS + 0x200)
        baseline[:] = patch.RESERVED_WORD * (len(baseline) // 2)
        baseline[
            patch.ROM01_CALL_ADDRESS:patch.ROM01_CALL_ADDRESS + 4
        ] = patch.words_to_bytes(patch.EXPECTED_CALL_WORDS)

        program_size = patch.POINTER_SOURCE - patch.PROGRAM_BASE + 0x100
        program = bytearray(program_size)
        alloc_offset = patch.ALLOC_SOURCE - patch.PROGRAM_BASE
        pointer_offset = patch.POINTER_SOURCE - patch.PROGRAM_BASE
        program[alloc_offset:alloc_offset + patch.WRAPPER_SIZE] = (
            patch.EXPECTED_ALLOC_BYTES
        )
        program[pointer_offset:pointer_offset + patch.WRAPPER_SIZE] = (
            patch.EXPECTED_POINTER_BYTES
        )
        return bytes(baseline), bytes(program)

    def test_installer_calls_original_then_writes_exact_wrappers(self) -> None:
        words = patch.late_installer_words(
            patch.EXPECTED_ALLOC_BYTES,
            patch.EXPECTED_POINTER_BYTES,
        )
        self.assertEqual(words[:4], [0xBD06, 0x3000, 0x6810, 0x0066])
        self.assertEqual(words[-1], patch.RETS)
        self.assertEqual(len(words) * 2, 0x9A)
        self.assertEqual(words.count(0x6810), 1)

    def test_patch_changes_only_call_and_reserved_installer_gap(self) -> None:
        baseline, program = self.make_images()
        output, metadata = patch.patch_image(baseline, program)
        installer_size = int(metadata["late_installer_bytes"])
        changed = {
            index for index, (old, new) in enumerate(zip(baseline, output))
            if old != new
        }
        allowed = set(range(patch.ROM01_CALL_ADDRESS,
                            patch.ROM01_CALL_ADDRESS + 4))
        allowed.update(range(patch.LATE_INSTALLER_ADDRESS,
                             patch.LATE_INSTALLER_ADDRESS + installer_size))
        self.assertLessEqual(changed, allowed)
        self.assertEqual(
            output[patch.ROM01_CALL_ADDRESS:patch.ROM01_CALL_ADDRESS + 4],
            patch.words_to_bytes((0xBD06, 0x3830)),
        )

    def test_rejects_non_reserved_gap(self) -> None:
        baseline, program = self.make_images()
        damaged = bytearray(baseline)
        damaged[patch.LATE_INSTALLER_ADDRESS] = 0xAA
        with self.assertRaisesRegex(ValueError, "no longer reserved"):
            patch.patch_image(bytes(damaged), program)


if __name__ == "__main__":
    unittest.main()
