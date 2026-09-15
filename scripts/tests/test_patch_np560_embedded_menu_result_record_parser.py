from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest

from scripts import patch_np560_embedded_menu_result_record_parser as patch


class EmbeddedMenuResultRecordParserPatchTests(unittest.TestCase):
    def make_baseline(self) -> bytearray:
        baseline = bytearray(b"\x00" * 0x200000)
        old_bridge = patch.previous.bridge_bytes()
        start = patch.previous.BRIDGE_ADDRESS
        baseline[start:start + len(old_bridge)] = old_bridge
        call = patch.previous.DIRECT_MANAGER_CALL_ADDRESS
        baseline[call:call + 4] = patch.previous.expected_call(start)
        installer = patch.embedded_installer_bytes()
        baseline[
            patch.EMBEDDED_INSTALLER_ADDRESS:
            patch.EMBEDDED_INSTALLER_ADDRESS + len(installer)
        ] = patch.RESERVED_WORD * (len(installer) // 2)
        return baseline

    def test_embedded_installer_contains_exact_parser_words(self) -> None:
        installer = patch.embedded_installer_bytes()
        exact = patch.exact_parser_bytes()
        self.assertEqual(len(exact), 0x058A)
        self.assertEqual(len(installer), 5678)
        self.assertEqual(exact[:2], b"\x07\x2e")
        self.assertEqual(exact[-4:], b"\x00\x2f\x20\xc6")
        self.assertEqual(
            int.from_bytes(installer[-2:], "little"),
            patch.rom.RETS,
        )

    def test_replaces_copy_bridge_and_installs_guest_words(self) -> None:
        baseline = self.make_baseline()
        output, metadata = patch.patch_image(bytes(baseline))
        installer = patch.embedded_installer_bytes()
        start = patch.EMBEDDED_INSTALLER_ADDRESS
        self.assertEqual(output[start:start + len(installer)], installer)
        bridge_start = patch.previous.BRIDGE_ADDRESS
        bridge = patch.replacement_bridge_bytes()
        self.assertEqual(
            output[bridge_start:bridge_start + len(bridge)],
            bridge,
        )
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_changed_v102_bridge(self) -> None:
        baseline = self.make_baseline()
        baseline[patch.previous.BRIDGE_ADDRESS] ^= 1
        with self.assertRaisesRegex(ValueError, "not exact"):
            patch.patch_image(bytes(baseline))


if __name__ == "__main__":
    unittest.main()
