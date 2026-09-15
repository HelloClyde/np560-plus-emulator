from __future__ import annotations

import unittest

from scripts import patch_np560_rom01_application_result_scan_chain as patch


class ApplicationResultScanChainPatchTests(unittest.TestCase):
    def make_images(self) -> tuple[bytearray, bytearray]:
        extension = patch.extension_bytes()
        baseline = bytearray(b"\x00" * 0x200000)
        baseline[patch.EXTENSION_ADDRESS:patch.EXTENSION_ADDRESS + len(extension)] = (
            patch.words_to_bytes((patch.RETS,)) +
            patch.RESERVED_WORD * (len(extension) // 2 - 1)
        )
        program = bytearray(b"\x00" * 0x400000)
        for _destination, source, size, head, _name in patch.OVERLAYS:
            offset = source - patch.PROGRAM_BASE
            program[offset:offset + size] = (
                head + b"\x00" * (size - 6) + patch.EPILOGUE
            )
        return baseline, program

    def test_extension_contains_fifteen_copy_loops(self) -> None:
        payload = patch.extension_bytes()
        self.assertEqual(len(patch.OVERLAYS), 15)
        self.assertEqual(len(payload), 15 * 42 + 2)
        words = [int.from_bytes(payload[i:i + 2], "little")
                 for i in range(0, len(payload), 2)]
        self.assertEqual(words[:10], [
            0x6810, 0x0057, 0x6811, 0x0091,
            0x68F1, 0x5756, 0x68F3, 0xD756,
            0x68F4, 0x0218,
        ])
        self.assertEqual(words[-1], patch.RETS)

    def test_installs_and_reports_all_selected_overlays(self) -> None:
        baseline, program = self.make_images()
        output, metadata = patch.patch_image(bytes(baseline), bytes(program))
        extension = patch.extension_bytes()
        self.assertEqual(
            output[patch.EXTENSION_ADDRESS:patch.EXTENSION_ADDRESS + len(extension)],
            extension,
        )
        self.assertEqual(len(metadata["overlays"]), 15)
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_changed_source_epilogue(self) -> None:
        baseline, program = self.make_images()
        _destination, source, size, _head, _name = patch.OVERLAYS[8]
        program[source - patch.PROGRAM_BASE + size - 2] ^= 1
        with self.assertRaisesRegex(ValueError, "epilogue changed"):
            patch.patch_image(bytes(baseline), bytes(program))


if __name__ == "__main__":
    unittest.main()
