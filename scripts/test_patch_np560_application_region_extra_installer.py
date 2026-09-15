from __future__ import annotations

import unittest

from scripts import patch_np560_application_region_extra_installer as patch


class ApplicationRegionExtraInstallerPatchTests(unittest.TestCase):
    def make_baseline(self) -> bytearray:
        payload = patch.installer_bytes()
        baseline = bytearray(b"\x00" * 0x200000)
        start = patch.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS
        baseline[start:start + len(payload)] = (
            patch.RESERVED.to_bytes(2, "little") * (len(payload) // 2)
        )
        return baseline

    def test_generated_installer_has_expected_boundary(self) -> None:
        payload = patch.installer_bytes()
        self.assertEqual(len(payload), 16930)
        self.assertEqual(payload[:4], b"\x10\x68\x66\x00")
        self.assertEqual(
            int.from_bytes(payload[-2:], "little"),
            patch.RETS,
        )

    def test_installs_guest_code_and_reports_no_host_hle(self) -> None:
        baseline = self.make_baseline()
        output, metadata = patch.patch_image(bytes(baseline))
        payload = patch.installer_bytes()
        start = patch.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS
        self.assertEqual(output[start:start + len(payload)], payload)
        self.assertEqual(metadata["installer"], "0A:0000")
        self.assertEqual(metadata["installer_end_exclusive"], "0A:4222")
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_non_reserved_destination(self) -> None:
        baseline = self.make_baseline()
        start = patch.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS
        baseline[start] ^= 1
        with self.assertRaisesRegex(ValueError, "not reserved skeleton ROM"):
            patch.patch_image(bytes(baseline))


if __name__ == "__main__":
    unittest.main()
