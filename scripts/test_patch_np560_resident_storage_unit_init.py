import unittest

try:
    from scripts import patch_np560_resident_storage_unit_init as patch
except ImportError:
    import patch_np560_resident_storage_unit_init as patch


class ResidentStorageUnitInitPatchTests(unittest.TestCase):
    def make_program(self) -> bytearray:
        size = patch.SOURCE - patch.PROGRAM_BASE + patch.SIZE
        program = bytearray(size)
        start = patch.SOURCE - patch.PROGRAM_BASE
        body = bytearray((index * 17 + 3) & 0xFF for index in range(patch.SIZE))
        body[:2] = patch.words_to_bytes((0x2E09,))
        body[-4:] = patch.words_to_bytes((0x2F00, patch.RETS))
        program[start:start + patch.SIZE] = body
        return program

    def make_baseline(self, installer_size: int) -> bytearray:
        size = max(
            patch.ROM01_LATE_CALL + 4,
            patch.DIRECT_MANAGER_CALL + 4,
            patch.COLD_BOOT_WRAPPER + len(patch.words_to_bytes(
                patch.wrapper_words(patch.EXISTING_LATE_INSTALLER)
            )),
            patch.DIRECT_MANAGER_WRAPPER + len(patch.words_to_bytes(
                patch.wrapper_words(
                    patch.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS
                )
            )),
            patch.GUEST_INSTALLER + installer_size,
        )
        baseline = bytearray(size)
        for address, length in (
            (patch.COLD_BOOT_WRAPPER, len(patch.words_to_bytes(
                patch.wrapper_words(patch.EXISTING_LATE_INSTALLER)
            ))),
            (patch.DIRECT_MANAGER_WRAPPER, len(patch.words_to_bytes(
                patch.wrapper_words(
                    patch.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS
                )
            ))),
            (patch.GUEST_INSTALLER, installer_size),
        ):
            baseline[address:address + length] = patch.RESERVED_WORD * (length // 2)
        baseline[patch.ROM01_LATE_CALL:patch.ROM01_LATE_CALL + 4] = (
            patch.words_to_bytes((0xBD06, 0x3830))
        )
        baseline[patch.DIRECT_MANAGER_CALL:patch.DIRECT_MANAGER_CALL + 4] = (
            patch.words_to_bytes((
                0xBD00
                | (patch.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS >> 16),
                patch.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS & 0xFFFF,
            ))
        )
        return baseline

    def test_installs_exact_function_after_original_region_installer(self) -> None:
        program = self.make_program()
        exact = patch.program_bytes(bytes(program), patch.SOURCE, patch.SIZE)
        installer_words = patch.embedded_installer_words(exact)
        installer = patch.words_to_bytes(installer_words)
        baseline = self.make_baseline(len(installer))

        output, metadata = patch.patch_image(bytes(baseline), bytes(program))
        self.assertEqual(
            output[patch.ROM01_LATE_CALL:patch.ROM01_LATE_CALL + 4],
            patch.words_to_bytes((0xBD06, 0x5100)),
        )
        self.assertEqual(
            output[patch.DIRECT_MANAGER_CALL:patch.DIRECT_MANAGER_CALL + 4],
            patch.words_to_bytes((0xBD06, 0x5110)),
        )
        self.assertEqual(
            output[patch.COLD_BOOT_WRAPPER:patch.COLD_BOOT_WRAPPER + 10],
            patch.words_to_bytes((0xBD06, 0x3830, 0xBD07, 0x3810, patch.RETS)),
        )
        self.assertEqual(
            output[patch.DIRECT_MANAGER_WRAPPER:
                   patch.DIRECT_MANAGER_WRAPPER + 10],
            patch.words_to_bytes((
                0xBD00
                | (patch.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS >> 16),
                patch.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS & 0xFFFF,
                0xBD07,
                0x3810,
                patch.RETS,
            )),
        )
        self.assertEqual(
            output[patch.GUEST_INSTALLER:patch.GUEST_INSTALLER + len(installer)],
            installer,
        )
        # First and last exact words are carried as MOV/store immediates.
        self.assertEqual(installer_words[2:6], [
            0x68F0, 0x2E09, 0xA8F0, patch.DESTINATION & 0x7FFF,
        ])
        self.assertEqual(installer_words[-9:-5], [
            0x68F0, patch.RETS, 0xA8F0,
            (patch.DESTINATION & 0x7FFF) + patch.SIZE - 2,
        ])
        self.assertEqual(installer_words[-5:], [
            0x6810, 0x0000, 0x6811, 0x0001, patch.RETS,
        ])
        self.assertEqual(
            metadata["direct_manager_wrapper"],
            "SCALL 0A:0000; SCALL 07:3810; RETS",
        )
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_refuses_to_overwrite_non_reserved_installer_range(self) -> None:
        program = self.make_program()
        exact = patch.program_bytes(bytes(program), patch.SOURCE, patch.SIZE)
        installer_size = len(patch.words_to_bytes(
            patch.embedded_installer_words(exact)
        ))
        baseline = self.make_baseline(installer_size)
        baseline[patch.GUEST_INSTALLER + 2] ^= 1
        with self.assertRaisesRegex(ValueError, "no longer reserved"):
            patch.patch_image(bytes(baseline), bytes(program))


if __name__ == "__main__":
    unittest.main()
