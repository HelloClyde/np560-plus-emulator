from __future__ import annotations

import unittest

from disassembly import patch_np560_menu_pointer_index_installer as patch


class MenuPointerIndexInstallerPatchTests(unittest.TestCase):
    def make_baseline(self) -> bytearray:
        payload = patch.installer_bytes()
        baseline = bytearray(b"\x00" * 0x200000)
        baseline[
            patch.INSTALLER_ADDRESS:patch.INSTALLER_ADDRESS + len(payload)
        ] = patch.RESERVED_WORD * (len(payload) // 2)
        return baseline

    def test_installer_boundary_is_stable(self) -> None:
        payload = patch.installer_bytes()
        self.assertEqual(len(payload), 326)
        self.assertEqual(payload[:4], b"\x10\x68\xa6\x00")
        self.assertEqual(
            int.from_bytes(payload[-2:], "little"),
            patch.rom.RETS,
        )

    def test_installs_guest_pointer_index(self) -> None:
        baseline = self.make_baseline()
        output, metadata = patch.patch_image(bytes(baseline))
        payload = patch.installer_bytes()
        start = patch.INSTALLER_ADDRESS
        self.assertEqual(output[start:start + len(payload)], payload)
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_non_reserved_destination(self) -> None:
        baseline = self.make_baseline()
        baseline[patch.INSTALLER_ADDRESS] ^= 1
        with self.assertRaisesRegex(ValueError, "not reserved"):
            patch.patch_image(bytes(baseline))


if __name__ == "__main__":
    unittest.main()
