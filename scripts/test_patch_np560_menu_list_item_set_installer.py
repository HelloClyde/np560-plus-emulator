from __future__ import annotations

import unittest

try:
    from scripts import build_np560_reconstructed_rom as rom
    from scripts import patch_np560_menu_list_item_set_installer as patch
except ModuleNotFoundError:
    import build_np560_reconstructed_rom as rom
    import patch_np560_menu_list_item_set_installer as patch


class MenuListItemSetInstallerPatchTests(unittest.TestCase):
    def make_baseline(self) -> bytes:
        size = max(
            patch.SUBINSTALLER_ADDRESS + len(patch.subinstaller_bytes()),
            patch.previous.EMBEDDED_INSTALLER_ADDRESS +
            len(patch.expanded_main_installer_bytes()),
        ) + 0x20
        baseline = bytearray(patch.RESERVED_WORD * (size // 2))
        old = patch.previous.embedded_installer_bytes()
        start = patch.previous.EMBEDDED_INSTALLER_ADDRESS
        baseline[start:start + len(old)] = old
        return bytes(baseline)

    def test_extends_guest_installer_and_carries_exact_function(self) -> None:
        output, metadata = patch.patch_image(self.make_baseline())
        main = patch.expanded_main_installer_bytes()
        main_start = patch.previous.EMBEDDED_INSTALLER_ADDRESS
        self.assertEqual(output[main_start:main_start + len(main)], main)
        sub = patch.subinstaller_bytes()
        self.assertEqual(
            output[patch.SUBINSTALLER_ADDRESS:patch.SUBINSTALLER_ADDRESS + len(sub)],
            sub,
        )
        self.assertEqual(metadata["main_installer_final_rets"], "1F:F094")
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_source_is_complete_exact_function(self) -> None:
        exact = patch.exact_function_bytes()
        self.assertEqual(len(exact), patch.SIZE)
        self.assertEqual(int.from_bytes(exact[:2], "little"), 0x2E04)
        self.assertEqual(int.from_bytes(exact[-2:], "little"), rom.RETS)

    def test_rejects_changed_existing_installer(self) -> None:
        baseline = bytearray(self.make_baseline())
        baseline[patch.previous.EMBEDDED_INSTALLER_ADDRESS] ^= 1
        with self.assertRaisesRegex(ValueError, "v105 installer is not exact"):
            patch.patch_image(bytes(baseline))


if __name__ == "__main__":
    unittest.main()
