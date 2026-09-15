from __future__ import annotations

import unittest

from scripts import patch_np560_menu_result_record_parser as patch


class MenuResultRecordParserPatchTests(unittest.TestCase):
    def make_baseline(self) -> bytearray:
        baseline = bytearray(b"\x00" * 0x200000)
        baseline[
            patch.DIRECT_MANAGER_CALL_ADDRESS:
            patch.DIRECT_MANAGER_CALL_ADDRESS + 4
        ] = patch.expected_call(patch.menu.RELOCATED_MENU_INSTALLER_ADDRESS)
        menu_payload = patch.expected_relocated_menu_bytes()
        menu_start = patch.menu.RELOCATED_MENU_INSTALLER_ADDRESS
        baseline[menu_start:menu_start + len(menu_payload)] = menu_payload
        bridge = patch.bridge_bytes()
        baseline[patch.BRIDGE_ADDRESS:patch.BRIDGE_ADDRESS + len(bridge)] = (
            patch.RESERVED_WORD * (len(bridge) // 2)
        )
        return baseline

    def test_bridge_has_one_exact_copy_loop(self) -> None:
        bridge = patch.bridge_bytes()
        self.assertEqual(len(bridge), 48)
        words = [
            int.from_bytes(bridge[index:index + 2], "little")
            for index in range(0, len(bridge), 2)
        ]
        self.assertEqual(words[:2], [0xBD1F, 0xC000])
        self.assertEqual(words[2:12], [
            0x6810, 0x0041, 0x6811, 0x007B,
            0x68F1, 0x01E0, 0x68F3, 0x81E0,
            0x68F4, 0x058A,
        ])
        self.assertEqual(words[-1], patch.rom.RETS)

    def test_installs_bridge_and_retargets_direct_manager(self) -> None:
        baseline = self.make_baseline()
        output, metadata = patch.patch_image(bytes(baseline))
        bridge = patch.bridge_bytes()
        self.assertEqual(
            output[patch.BRIDGE_ADDRESS:patch.BRIDGE_ADDRESS + len(bridge)],
            bridge,
        )
        self.assertEqual(
            output[
                patch.DIRECT_MANAGER_CALL_ADDRESS:
                patch.DIRECT_MANAGER_CALL_ADDRESS + 4
            ],
            patch.expected_call(patch.BRIDGE_ADDRESS),
        )
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_changed_menu_installer(self) -> None:
        baseline = self.make_baseline()
        baseline[patch.menu.RELOCATED_MENU_INSTALLER_ADDRESS] ^= 1
        with self.assertRaisesRegex(ValueError, "not exact"):
            patch.patch_image(bytes(baseline))


if __name__ == "__main__":
    unittest.main()
