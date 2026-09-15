from __future__ import annotations

import unittest

from scripts import patch_np560_relocated_menu_runtime_installers as patch


class RelocatedMenuRuntimeInstallerPatchTests(unittest.TestCase):
    def make_baseline(self) -> bytearray:
        baseline = bytearray(b"\x00" * 0x200000)
        baseline[patch.CALL_ADDRESS:patch.CALL_ADDRESS + 4] = (
            patch.expected_call(patch.OLD_MENU_INSTALLER_ADDRESS)
        )
        des = patch.words_to_bytes(patch.rom.des_table_initializer_words())
        des_start = patch.rom.DES_TABLE_INITIALIZER_ADDRESS
        baseline[des_start:des_start + len(des)] = des
        for _name, start, payload in patch.generated_payloads():
            baseline[start:start + len(payload)] = (
                patch.RESERVED_WORD * (len(payload) // 2)
            )
        baseline[0x063000:0x063192] = bytes(
            (index * 37 + 11) & 0xFF for index in range(0x192)
        )
        return baseline

    def test_payload_boundaries_are_stable(self) -> None:
        payloads = patch.generated_payloads()
        self.assertEqual(
            [(address, len(payload)) for _name, address, payload in payloads],
            [
                (0x1FC000, 2320),
                (0x065D00, 1450),
                (0x1A8000, 15486),
                (0x09C800, 3710),
            ],
        )

    def test_installs_all_guest_code_and_preserves_legacy_entry(self) -> None:
        baseline = self.make_baseline()
        legacy = bytes(baseline[0x063000:0x063192])
        output, metadata = patch.patch_image(bytes(baseline))
        self.assertEqual(
            output[patch.CALL_ADDRESS:patch.CALL_ADDRESS + 4],
            patch.expected_call(patch.RELOCATED_MENU_INSTALLER_ADDRESS),
        )
        for _name, start, payload in patch.generated_payloads():
            self.assertEqual(output[start:start + len(payload)], payload)
        self.assertEqual(output[0x063000:0x063192], legacy)
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_changed_des_dependency(self) -> None:
        baseline = self.make_baseline()
        baseline[patch.rom.DES_TABLE_INITIALIZER_ADDRESS] ^= 1
        with self.assertRaisesRegex(ValueError, "DES initializer"):
            patch.patch_image(bytes(baseline))


if __name__ == "__main__":
    unittest.main()
