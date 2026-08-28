from __future__ import annotations

import unittest

try:
    from disassembly import patch_np560_resident_menu_record_decoder as patch
except ModuleNotFoundError:
    import patch_np560_resident_menu_record_decoder as patch


class ResidentMenuRecordDecoderPatchTests(unittest.TestCase):
    def make_images(self) -> tuple[bytearray, bytearray, bytes]:
        baseline = bytearray(patch.DESTINATION + patch.SIZE + 0x20)
        baseline[patch.DESTINATION:patch.DESTINATION + patch.SIZE] = (
            patch.RESERVED_WORD * (patch.SIZE // 2)
        )

        program_size = patch.SOURCE - patch.PROGRAM_BASE + patch.SIZE
        program = bytearray(program_size)
        exact = bytearray((index * 31 + 9) & 0xFF for index in range(patch.SIZE))
        exact[:2] = patch.words_to_bytes((patch.LINK_39,))
        exact[-16:] = patch.words_to_bytes((
            0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, patch.UNLINK, patch.RETS,
        ))
        for offset in (0x100, 0x400, 0x800, 0xC00):
            exact[offset:offset + 4] = patch.MEMORY_FILL_CALL
        source_offset = patch.SOURCE - patch.PROGRAM_BASE
        program[source_offset:source_offset + patch.SIZE] = exact
        return baseline, program, bytes(exact)

    def test_restores_exact_original_decoder(self) -> None:
        baseline, program, exact = self.make_images()
        output, metadata = patch.patch_image(bytes(baseline), bytes(program))
        self.assertEqual(
            output[patch.DESTINATION:patch.DESTINATION + patch.SIZE],
            exact,
        )
        self.assertEqual(metadata["exact_source"], "2E:5C12")
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_non_reserved_destination(self) -> None:
        baseline, program, _ = self.make_images()
        baseline[patch.DESTINATION + 2] ^= 1
        with self.assertRaisesRegex(ValueError, "no longer entirely reserved"):
            patch.patch_image(bytes(baseline), bytes(program))

    def test_rejects_changed_dependency_count(self) -> None:
        baseline, program, _ = self.make_images()
        source_offset = patch.SOURCE - patch.PROGRAM_BASE
        program[source_offset + 0x100] ^= 1
        with self.assertRaisesRegex(ValueError, "four SCALL"):
            patch.patch_image(bytes(baseline), bytes(program))

    def test_rejects_incomplete_epilogue(self) -> None:
        baseline, program, _ = self.make_images()
        source_offset = patch.SOURCE - patch.PROGRAM_BASE
        program[source_offset + patch.SIZE - 2] ^= 1
        with self.assertRaisesRegex(ValueError, "balanced epilogue"):
            patch.patch_image(bytes(baseline), bytes(program))


if __name__ == "__main__":
    unittest.main()
