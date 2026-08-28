from __future__ import annotations

import unittest

try:
    from disassembly import patch_np560_resident_result_object_alloc as patch
except ModuleNotFoundError:
    import patch_np560_resident_result_object_alloc as patch


class ResidentResultObjectAllocPatchTests(unittest.TestCase):
    def make_images(self) -> tuple[bytearray, bytearray, bytes]:
        baseline = bytearray(patch.DESTINATION + patch.SIZE + 0x20)
        baseline[patch.DESTINATION:patch.DESTINATION + patch.SIZE] = (
            patch.RESERVED_WORD * (patch.SIZE // 2)
        )

        program_size = patch.SOURCE - patch.PROGRAM_BASE + patch.SIZE
        program = bytearray(program_size)
        exact = bytearray((index * 29 + 7) & 0xFF for index in range(patch.SIZE))
        exact[:2] = patch.words_to_bytes((patch.LINK_6B,))
        exact[-4:] = patch.words_to_bytes((patch.UNLINK, patch.RETS))
        source_offset = patch.SOURCE - patch.PROGRAM_BASE
        program[source_offset:source_offset + patch.SIZE] = exact
        return baseline, program, bytes(exact)

    def test_restores_exact_original_function(self) -> None:
        baseline, program, exact = self.make_images()
        output, metadata = patch.patch_image(bytes(baseline), bytes(program))
        self.assertEqual(
            output[patch.DESTINATION:patch.DESTINATION + patch.SIZE],
            exact,
        )
        self.assertEqual(metadata["exact_source"], "3B:6444")
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_non_reserved_destination(self) -> None:
        baseline, program, _ = self.make_images()
        baseline[patch.DESTINATION + 2] ^= 1
        with self.assertRaisesRegex(ValueError, "no longer entirely reserved"):
            patch.patch_image(bytes(baseline), bytes(program))

    def test_rejects_incomplete_source_body(self) -> None:
        baseline, program, _ = self.make_images()
        source_offset = patch.SOURCE - patch.PROGRAM_BASE
        program[source_offset + patch.SIZE - 2] ^= 1
        with self.assertRaisesRegex(ValueError, "UNLINK/RETS"):
            patch.patch_image(bytes(baseline), bytes(program))


if __name__ == "__main__":
    unittest.main()
