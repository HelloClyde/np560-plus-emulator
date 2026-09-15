from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest

from scripts import analyse_np560_operation_catalog as operation


class OperationCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.program = operation.DEFAULT_PROGRAM.read_bytes()
        cls.result = operation.analyse(cls.program)

    def test_game_world_uses_npe_application_directory(self) -> None:
        game = self.result["game_world"]
        self.assertEqual(game["catalogue_name"], "游戏世界")
        self.assertEqual(game["application_id"], 0x78)
        self.assertEqual(game["wrapper_destination"], "33:3DA6")
        self.assertEqual(game["operation_index"], 1)
        self.assertEqual(game["operation"]["directory"], r"0:\应用程序")
        self.assertEqual(game["operation"]["filter"], r"\*.npe")

    def test_animation_browser_is_separate_nwf_operation(self) -> None:
        animation = self.result["animation_browser"]
        self.assertEqual(animation["catalogue_name"], "动漫欣赏")
        self.assertEqual(animation["application_id"], 0x79)
        self.assertEqual(animation["wrapper_destination"], "33:3CE6")
        self.assertEqual(animation["operation_index"], 0)
        self.assertEqual(animation["operation"]["directory"], r"0:\动漫欣赏")
        self.assertEqual(animation["operation"]["filter"], r"\*.nwf")

    def test_scope_does_not_conflate_npe_and_nwf(self) -> None:
        scope = self.result["scope"]
        self.assertFalse(scope["npe_nwf_same_container_proven"])
        self.assertTrue(scope["selected_file_launch_first_hop_recovered"])
        self.assertFalse(scope["npe_parser_recovered"])

    def test_selected_npe_reaches_guest_launch_sequence(self) -> None:
        launch = self.result["selected_file_launch"]
        self.assertEqual(launch["selected_descriptor_global"], "A4:5192/5194")
        self.assertEqual(launch["handoff_destination"], "1B:2A88")
        self.assertEqual(launch["launch_sequence_destination"], "2E:D34A")
        self.assertEqual(launch["file_state_constructor"], "30:C370")
        self.assertEqual(launch["file_wrapper"], "30:C99E")
        self.assertEqual(launch["application_launch_manager"], "18:21F4")

    def test_dispatch_signature_is_pinned(self) -> None:
        damaged = bytearray(self.program)
        damaged[operation.DISPATCH_SOURCE - operation.PROGRAM_BASE] ^= 1
        with self.assertRaisesRegex(ValueError, "dispatcher mismatch"):
            operation.analyse(bytes(damaged))

    def test_operation_string_pointer_is_bounded(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside pool"):
            operation.decode_operation_string(self.program, 0x27, 0xD000)


if __name__ == "__main__":
    unittest.main()
