from __future__ import annotations

import unittest

from disassembly import patch_np560_rom01_application_result_list_create as patch


class ApplicationResultListCreatePatchTests(unittest.TestCase):
    def test_extension_is_one_guest_copy_loop_and_rets(self) -> None:
        payload = patch.extension_bytes()
        self.assertEqual(len(payload), 44)
        words = [
            int.from_bytes(payload[index:index + 2], "little")
            for index in range(0, len(payload), 2)
        ]
        self.assertEqual(words[:10], [
            0x6810, 0x0063, 0x6811, 0x009D,
            0x68F1, 0x1E18, 0x68F3, 0x9E18,
            0x68F4, 0x00A8,
        ])
        self.assertEqual(words[-5:], [
            0x6810, 0x0000, 0x6811, 0x0001, patch.RETS,
        ])

    def test_patch_replaces_only_previous_rets_and_reserved_words(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
