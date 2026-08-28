from __future__ import annotations

import unittest

from disassembly import patch_np560_menu_runtime_subinstallers as patch


class MenuRuntimeSubinstallerPatchTests(unittest.TestCase):
    def make_baseline(self) -> bytearray:
        baseline = bytearray(b"\x00" * 0x200000)
        menu_payload = patch.words_to_bytes(
            patch.rom.menu_runtime_overlay_installer_words()
        )
        menu_start = patch.menu.RELOCATED_MENU_INSTALLER_ADDRESS
        baseline[menu_start:menu_start + len(menu_payload)] = menu_payload
        for _name, start, payload in patch.generated_payloads():
            baseline[start:start + len(payload)] = (
                patch.RESERVED_WORD * (len(payload) // 2)
            )
        baseline[0x063000:0x06421A] = bytes(
            (index * 19 + 7) & 0xFF for index in range(0x121A)
        )
        return baseline

    def test_generated_payload_boundaries_are_stable(self) -> None:
        self.assertEqual(
            [(address, len(payload))
             for _name, address, payload in patch.generated_payloads()],
            [
                (0x1FD000, 2830),
                (0x061750, 932),
                (0x061C40, 128),
                (0x065B00, 508),
                (0x066300, 44),
                (0x067000, 4494),
            ],
        )
        self.assertEqual(patch.cursor_call_address(), 0x1FC7EC)

    def test_installs_and_preserves_legacy_mid_function_body(self) -> None:
        baseline = self.make_baseline()
        legacy = bytes(baseline[0x063000:0x06421A])
        output, metadata = patch.patch_image(bytes(baseline))
        call = patch.cursor_call_address()
        self.assertEqual(
            output[call:call + 4],
            patch.expected_call(patch.RELOCATED_CURSOR_INSTALLER_ADDRESS),
        )
        for _name, start, payload in patch.generated_payloads():
            self.assertEqual(output[start:start + len(payload)], payload)
        self.assertEqual(output[0x063000:0x06421A], legacy)
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_changed_relocated_menu_installer(self) -> None:
        baseline = self.make_baseline()
        baseline[patch.menu.RELOCATED_MENU_INSTALLER_ADDRESS] ^= 1
        with self.assertRaisesRegex(ValueError, "not exact"):
            patch.patch_image(bytes(baseline))


if __name__ == "__main__":
    unittest.main()
