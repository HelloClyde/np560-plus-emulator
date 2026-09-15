
# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import unittest

from scripts import build_np560_reconstructed_rom as rom
from scripts import patch_np560_direct_manager_onto_recovered_rom as patch


class DirectManagerPatchTests(unittest.TestCase):
    def test_direct_menu_range_covers_complete_generated_caller(self) -> None:
        start, end, name = next(
            item for item in patch.RANGES
            if item[2] == "direct_vendor_menu_caller"
        )
        self.assertEqual(start, rom.DIRECT_GENERIC_MENU_PROBE_ADDRESS)
        self.assertEqual(
            end,
            rom.DIRECT_GENERIC_MENU_PROBE_ADDRESS +
            len(rom.direct_generic_menu_probe_words()) * 2,
        )
        self.assertEqual(name, "direct_vendor_menu_caller")

    def test_direct_data_ranges_cover_installer_and_text_stream(self) -> None:
        by_name = {name: (start, end) for start, end, name in patch.RANGES}
        self.assertEqual(
            by_name["direct_menu_pointer_index_installer"],
            (
                rom.MENU_POINTER_INDEX_INSTALLER_ADDRESS,
                rom.MENU_POINTER_INDEX_INSTALLER_ADDRESS +
                len(rom.generic_main_menu_pointer_index_installer_words(
                    direct_text_stream=True,
                )) * 2,
            ),
        )
        self.assertEqual(
            by_name["direct_menu_text_stream"],
            (
                rom.DIRECT_GENERIC_MENU_TEXT_STREAM_ADDRESS,
                rom.DIRECT_GENERIC_MENU_TEXT_STREAM_ADDRESS +
                len(rom.direct_generic_menu_text_stream_words()) * 2,
            ),
        )

    def test_copies_system_main_handoff_with_manager_and_helpers(self) -> None:
        size = max(end for _, end, _ in patch.RANGES) + 2
        natural = bytearray(size)
        direct = bytearray(size)
        for index, (start, end, _name) in enumerate(patch.RANGES, start=1):
            direct[start:end] = bytes([index]) * (end - start)

        output, metadata = patch.patch_image(
            bytes(natural), bytes(natural), bytes(direct)
        )

        copied = {record["name"] for record in metadata["copied_ranges"]}
        self.assertIn("factory_system_main_terminal_handoff", copied)
        for start, end, _name in patch.RANGES:
            self.assertEqual(output[start:end], direct[start:end])
        self.assertEqual(output[0x030318:0x03031C], bytes(4))

    def test_native_hierarchy_keeps_catalogue_index_and_omits_probe_text(self) -> None:
        size = max(end for _, end, _ in patch.RANGES) + 2
        natural = bytearray(size)
        direct = bytearray(size)
        for index, (start, end, _name) in enumerate(patch.RANGES, start=1):
            natural[start:end] = bytes([0x80 + index]) * (end - start)
            direct[start:end] = bytes([index]) * (end - start)

        output, metadata = patch.patch_image(
            bytes(natural), bytes(natural), bytes(direct),
            native_hierarchy=True,
        )

        copied = {record["name"] for record in metadata["copied_ranges"]}
        self.assertTrue(patch.DIRECT_TEXT_RANGE_NAMES.isdisjoint(copied))
        self.assertEqual(
            metadata["menu_source"],
            "invalid_binary_hierarchy_negative_control_1c9748",
        )
        for start, end, name in patch.RANGES:
            expected = natural if name in patch.DIRECT_TEXT_RANGE_NAMES else direct
            self.assertEqual(output[start:end], expected[start:end])


if __name__ == "__main__":
    unittest.main()
