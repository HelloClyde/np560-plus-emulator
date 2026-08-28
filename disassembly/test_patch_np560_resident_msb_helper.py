from __future__ import annotations

import unittest

try:
    from disassembly import patch_np560_resident_msb_helper as patch
except ModuleNotFoundError:
    import patch_np560_resident_msb_helper as patch


class ResidentMsbHelperTest(unittest.TestCase):
    def make_images(self) -> tuple[bytearray, bytearray, bytes]:
        baseline = bytearray(max(patch.CALL_SITES) + 0x100)
        baseline[patch.RESIDENT_HELPER:patch.RESIDENT_HELPER + patch.HELPER_SIZE] = (
            patch.RESERVED_WORD * (patch.HELPER_SIZE // 2)
        )
        for address in patch.CALL_SITES:
            baseline[address:address + 4] = patch.words_to_bytes(
                patch.ORIGINAL_CALL
            )
        program = bytearray(patch.SOURCE_HELPER - patch.PROGRAM_BASE + 0x100)
        helper = bytearray(patch.HELPER_SIZE)
        helper[:2] = patch.words_to_bytes((0x58F5,))
        helper[-2:] = patch.words_to_bytes((0xC620,))
        source = patch.SOURCE_HELPER - patch.PROGRAM_BASE
        program[source:source + patch.HELPER_SIZE] = helper
        return baseline, program, bytes(helper)

    def test_installs_exact_helper_and_retargets_three_calls(self) -> None:
        baseline, program, helper = self.make_images()
        output, metadata = patch.patch_image(bytes(baseline), bytes(program))
        self.assertEqual(
            output[patch.RESIDENT_HELPER:patch.RESIDENT_HELPER + patch.HELPER_SIZE],
            helper,
        )
        for address in patch.CALL_SITES:
            self.assertEqual(
                output[address:address + 4],
                patch.words_to_bytes(patch.PATCHED_CALL),
            )
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_non_reserved_destination(self) -> None:
        baseline, program, _ = self.make_images()
        baseline[patch.RESIDENT_HELPER] ^= 1
        with self.assertRaisesRegex(ValueError, "no longer an unused"):
            patch.patch_image(bytes(baseline), bytes(program))


if __name__ == "__main__":
    unittest.main()
