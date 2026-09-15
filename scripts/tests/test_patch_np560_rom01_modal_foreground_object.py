from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest

from scripts import patch_np560_rom01_modal_foreground_object as patch


class ModalForegroundObjectPatchTests(unittest.TestCase):
    def test_extension_is_one_guest_copy_loop_and_rets(self) -> None:
        payload = patch.extension_bytes()
        self.assertEqual(len(payload), 44)
        words = [
            int.from_bytes(payload[index:index + 2], "little")
            for index in range(0, len(payload), 2)
        ]
        self.assertEqual(words[:10], [
            0x6810, 0x005B, 0x6811, 0x0095,
            0x68F1, 0x1DFC, 0x68F3, 0x9DFC,
            0x68F4, 0x01AC,
        ])
        self.assertEqual(words[-5:], [
            0x6810, 0x0000, 0x6811, 0x0001, patch.RETS,
        ])

    def test_patch_replaces_only_legacy_rets_and_reserved_words(self) -> None:
        extension = patch.extension_bytes()
        baseline = bytearray(b"\x00" * 0x200000)
        baseline[patch.EXTENSION_ADDRESS:patch.EXTENSION_ADDRESS + len(extension)] = (
            patch.words_to_bytes((patch.RETS,)) +
            patch.RESERVED_WORD * (len(extension) // 2 - 1)
        )
        program = bytearray(b"\x00" * 0x400000)
        source = patch.SOURCE - patch.PROGRAM_BASE
        program[source:source + patch.SIZE] = (
            patch.PROLOGUE + b"\x00" * (patch.SIZE - 6) + patch.EPILOGUE
        )

        output, metadata = patch.patch_image(bytes(baseline), bytes(program))

        self.assertEqual(
            output[patch.EXTENSION_ADDRESS:patch.EXTENSION_ADDRESS + len(extension)],
            extension,
        )
        self.assertEqual(metadata["exact_bytes"], patch.SIZE)

    def test_patch_accepts_legacy_installer_tail(self) -> None:
        extension = patch.extension_bytes()
        baseline = bytearray(b"\x00" * 0x200000)
        address = patch.LEGACY_EXTENSION_ADDRESS
        baseline[address:address + len(extension)] = (
            patch.words_to_bytes((patch.RETS,)) +
            patch.RESERVED_WORD * (len(extension) // 2 - 1)
        )
        program = bytearray(b"\x00" * 0x400000)
        source = patch.SOURCE - patch.PROGRAM_BASE
        program[source:source + patch.SIZE] = (
            patch.PROLOGUE + b"\x00" * (patch.SIZE - 6) + patch.EPILOGUE
        )

        output, metadata = patch.patch_image(bytes(baseline), bytes(program))

        self.assertEqual(
            output[address:address + len(extension)], extension,
        )
        self.assertEqual(metadata["installer_extension"], "06:3E52")


if __name__ == "__main__":
    unittest.main()
