from __future__ import annotations

import unittest

from scripts import patch_np560_rom01_application_result_record_match as patch


class ApplicationResultRecordMatchPatchTests(unittest.TestCase):
    def make_images(self) -> tuple[bytearray, bytearray]:
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
        return baseline, program

    def test_copy_loop_targets_exact_overlay(self) -> None:
        payload = patch.extension_bytes()
        self.assertEqual(len(payload), 44)
        words = [int.from_bytes(payload[i:i + 2], "little")
                 for i in range(0, len(payload), 2)]
        self.assertEqual(words[:10], [
            0x6810, 0x0055, 0x6811, 0x008F,
            0x68F1, 0x00AA, 0x68F3, 0x80AA,
            0x68F4, 0x026C,
        ])
        self.assertEqual(words[-1], patch.RETS)

    def test_installs_exact_guest_copy_extension(self) -> None:
        baseline, program = self.make_images()
        output, metadata = patch.patch_image(bytes(baseline), bytes(program))
        extension = patch.extension_bytes()
        self.assertEqual(
            output[patch.EXTENSION_ADDRESS:patch.EXTENSION_ADDRESS + len(extension)],
            extension,
        )
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_changed_prologue(self) -> None:
        baseline, program = self.make_images()
        program[patch.SOURCE - patch.PROGRAM_BASE] ^= 1
        with self.assertRaisesRegex(ValueError, "LINK #0x0A"):
            patch.patch_image(bytes(baseline), bytes(program))


if __name__ == "__main__":
    unittest.main()
