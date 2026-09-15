from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest

from scripts import patch_np560_menu_hardware_bit_wrappers as patch


class MenuHardwareBitWrappersPatchTests(unittest.TestCase):
    def make_baseline(self) -> bytearray:
        baseline = bytearray(b"\x00" * 0x200000)
        bridge_start = patch.previous.previous.BRIDGE_ADDRESS
        old_region = patch.old_bridge_region_bytes()
        baseline[bridge_start:bridge_start + len(old_region)] = old_region
        call = patch.previous.previous.DIRECT_MANAGER_CALL_ADDRESS
        baseline[call:call + 4] = patch.previous.previous.expected_call(
            bridge_start
        )
        installer = patch.embedded_installer_bytes()
        baseline[
            patch.EMBEDDED_INSTALLER_ADDRESS:
            patch.EMBEDDED_INSTALLER_ADDRESS + len(installer)
        ] = patch.RESERVED_WORD * (len(installer) // 2)
        return baseline

    def test_sources_are_complete_exact_wrappers(self) -> None:
        expected = (
            b"\x00\x2e\x31\xe2\x00\x2f\x20\xc6",
            b"\x00\x2e\x31\xe1\x00\x2f\x20\xc6",
            b"\x00\x2e\x31\xf2\x00\x2f\x20\xc6",
            b"\x00\x2e\x31\xf1\x00\x2f\x20\xc6",
        )
        actual = tuple(
            patch.exact_wrapper_bytes(source, size)
            for _destination, source, size, _purpose in patch.WRAPPERS
        )
        self.assertEqual(actual, expected)

    def test_installs_guest_wrappers_and_extends_bridge(self) -> None:
        baseline = self.make_baseline()
        output, metadata = patch.patch_image(bytes(baseline))
        installer = patch.embedded_installer_bytes()
        start = patch.EMBEDDED_INSTALLER_ADDRESS
        self.assertEqual(output[start:start + len(installer)], installer)
        bridge = patch.replacement_bridge_bytes()
        bridge_start = patch.previous.previous.BRIDGE_ADDRESS
        self.assertEqual(
            output[bridge_start:bridge_start + len(bridge)],
            bridge,
        )
        self.assertEqual(len(metadata["restored_overlays"]), 4)
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_changed_bridge(self) -> None:
        baseline = self.make_baseline()
        baseline[patch.previous.previous.BRIDGE_ADDRESS] ^= 1
        with self.assertRaisesRegex(ValueError, "not exact"):
            patch.patch_image(bytes(baseline))


if __name__ == "__main__":
    unittest.main()
