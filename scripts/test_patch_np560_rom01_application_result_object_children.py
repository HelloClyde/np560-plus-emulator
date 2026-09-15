from __future__ import annotations

import unittest

from scripts import patch_np560_rom01_application_result_object_children as patch


class ApplicationResultObjectChildrenPatchTests(unittest.TestCase):
    def make_images(self) -> tuple[bytearray, bytearray]:
        extension = patch.extension_bytes()
        baseline = bytearray(b"\x00" * 0x200000)
        baseline[patch.EXTENSION_ADDRESS:patch.EXTENSION_ADDRESS + len(extension)] = (
            patch.words_to_bytes((patch.RETS,)) +
            patch.RESERVED_WORD * (len(extension) // 2 - 1)
        )
        program = bytearray(b"\x00" * 0x400000)
        for _destination, source, size, head, tail, _name in patch.OVERLAYS:
            offset = source - patch.PROGRAM_BASE
            program[offset:offset + size] = (
                head + b"\x00" * (size - len(head) - len(tail)) + tail
            )
        return baseline, program

    def test_extension_contains_three_guest_copy_loops(self) -> None:
        payload = patch.extension_bytes()
        self.assertEqual(len(payload), 128)
        words = [
            int.from_bytes(payload[index:index + 2], "little")
            for index in range(0, len(payload), 2)
        ]
        self.assertEqual(words[:10], [
            0x6810, 0x0061, 0x6811, 0x009B,
            0x68F1, 0x026A, 0x68F3, 0x826A,
            0x68F4, 0x00FA,
        ])
        self.assertEqual(words[-1], patch.RETS)

    def test_installs_and_reports_all_three_overlays(self) -> None:
        baseline, program = self.make_images()
        output, metadata = patch.patch_image(bytes(baseline), bytes(program))
        extension = patch.extension_bytes()
        self.assertEqual(
            output[patch.EXTENSION_ADDRESS:patch.EXTENSION_ADDRESS + len(extension)],
            extension,
        )
        self.assertEqual(len(metadata["overlays"]), 3)
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_changed_epilogue(self) -> None:
        baseline, program = self.make_images()
        _destination, source, size, _head, _tail, _name = patch.OVERLAYS[1]
        program[source - patch.PROGRAM_BASE + size - 2] ^= 1
        with self.assertRaisesRegex(ValueError, "epilogue changed"):
            patch.patch_image(bytes(baseline), bytes(program))


if __name__ == "__main__":
    unittest.main()
