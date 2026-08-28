from __future__ import annotations

import unittest

try:
    from disassembly import patch_np560_resident_event_e0_handler as patch
except ModuleNotFoundError:
    import patch_np560_resident_event_e0_handler as patch


class ResidentEventE0HandlerTest(unittest.TestCase):
    def make_images(self) -> tuple[bytearray, bytearray, bytes]:
        baseline = bytearray(patch.DESTINATION + patch.SIZE)
        baseline[patch.DESTINATION:patch.DESTINATION + patch.SIZE] = (
            patch.RESERVED_WORD * (patch.SIZE // 2)
        )
        source_offset = patch.SOURCE - patch.PROGRAM_BASE
        program = bytearray(source_offset + patch.SIZE)
        body = bytearray(patch.SIZE)
        body[:2] = patch.words_to_bytes(patch.PROLOGUE)
        body[-4:] = patch.words_to_bytes(patch.EPILOGUE)
        program[source_offset:source_offset + patch.SIZE] = body
        return baseline, program, bytes(body)

    def test_installs_exact_same_pc_function(self) -> None:
        baseline, program, body = self.make_images()
        output, metadata = patch.patch_image(bytes(baseline), bytes(program))
        self.assertEqual(
            output[patch.DESTINATION:patch.DESTINATION + patch.SIZE], body
        )
        self.assertEqual(metadata["bytes"], patch.SIZE)
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_nonreserved_destination(self) -> None:
        baseline, program, _ = self.make_images()
        baseline[patch.DESTINATION + 2] ^= 1
        with self.assertRaisesRegex(ValueError, "no longer reserved"):
            patch.patch_image(bytes(baseline), bytes(program))

    def test_rejects_changed_source_epilogue(self) -> None:
        baseline, program, _ = self.make_images()
        program[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "UNLINK/RETS"):
            patch.patch_image(bytes(baseline), bytes(program))


if __name__ == "__main__":
    unittest.main()
