from __future__ import annotations

import unittest

try:
    from scripts import patch_np560_resident_event_e0_handler as patch
except ModuleNotFoundError:
    import patch_np560_resident_event_e0_handler as patch


class ResidentEventE0HandlerTest(unittest.TestCase):
    def make_images(self) -> tuple[bytearray, bytearray, bytes, bytes]:
        baseline = bytearray(patch.DESTINATION + patch.SIZE)
        baseline[patch.DESTINATION:patch.DESTINATION + patch.SIZE] = (
            patch.RESERVED_WORD * (patch.SIZE // 2)
        )
        baseline[
            patch.CALLBACK_DESTINATION:
            patch.CALLBACK_DESTINATION + patch.CALLBACK_SIZE
        ] = patch.RESERVED_WORD * (patch.CALLBACK_SIZE // 2)
        source_offset = patch.SOURCE - patch.PROGRAM_BASE
        callback_offset = patch.CALLBACK_SOURCE - patch.PROGRAM_BASE
        program = bytearray(max(
            source_offset + patch.SIZE,
            callback_offset + patch.CALLBACK_SIZE,
        ))
        body = bytearray(patch.SIZE)
        body[:2] = patch.words_to_bytes(patch.PROLOGUE)
        body[-4:] = patch.words_to_bytes(patch.EPILOGUE)
        pointer_offset = patch.CALLBACK_POINTER_SOURCE - patch.SOURCE
        body[pointer_offset:pointer_offset + 8] = patch.words_to_bytes((
            0x68F1, patch.CALLBACK_LINKED_ADDRESS & 0xFFFF,
            0x68F0, patch.CALLBACK_LINKED_ADDRESS >> 16,
        ))
        program[source_offset:source_offset + patch.SIZE] = body
        callback = bytearray(patch.CALLBACK_SIZE)
        callback[:2] = patch.words_to_bytes(patch.CALLBACK_PROLOGUE)
        callback[-4:] = patch.words_to_bytes(patch.CALLBACK_EPILOGUE)
        program[
            callback_offset:callback_offset + patch.CALLBACK_SIZE
        ] = callback
        return baseline, program, bytes(body), bytes(callback)

    def test_installs_handler_and_relocated_exact_callback(self) -> None:
        baseline, program, body, callback = self.make_images()
        output, metadata = patch.patch_image(bytes(baseline), bytes(program))
        expected = bytearray(body)
        pointer_offset = patch.CALLBACK_POINTER_SOURCE - patch.SOURCE
        expected[pointer_offset:pointer_offset + 8] = patch.words_to_bytes((
            0x68F1, patch.CALLBACK_DESTINATION & 0xFFFF,
            0x68F0, patch.CALLBACK_DESTINATION >> 16,
        ))
        self.assertEqual(
            output[patch.DESTINATION:patch.DESTINATION + patch.SIZE], expected
        )
        self.assertEqual(
            output[
                patch.CALLBACK_DESTINATION:
                patch.CALLBACK_DESTINATION + patch.CALLBACK_SIZE
            ],
            callback,
        )
        self.assertEqual(metadata["bytes"], patch.SIZE)
        self.assertEqual(
            metadata["callback"]["pointer_patch"],
            "15:F26C: 33:5896 -> 06:1E30",
        )
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_nonreserved_destination(self) -> None:
        baseline, program, _, _ = self.make_images()
        baseline[patch.DESTINATION + 2] ^= 1
        with self.assertRaisesRegex(ValueError, "no longer reserved"):
            patch.patch_image(bytes(baseline), bytes(program))

    def test_rejects_changed_source_epilogue(self) -> None:
        baseline, program, _, _ = self.make_images()
        source_offset = patch.SOURCE - patch.PROGRAM_BASE
        program[source_offset + patch.SIZE - 1] ^= 1
        with self.assertRaisesRegex(ValueError, "UNLINK/RETS"):
            patch.patch_image(bytes(baseline), bytes(program))

    def test_rejects_changed_callback_pointer_signature(self) -> None:
        baseline, program, _, _ = self.make_images()
        source_offset = patch.CALLBACK_POINTER_SOURCE - patch.PROGRAM_BASE
        program[source_offset + 2] ^= 1
        with self.assertRaisesRegex(ValueError, "pointer signature"):
            patch.patch_image(bytes(baseline), bytes(program))


if __name__ == "__main__":
    unittest.main()
