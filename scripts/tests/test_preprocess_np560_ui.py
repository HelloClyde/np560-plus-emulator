from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent))
import preprocess_np560_ui as preprocess


class PreprocessUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.image = (
            Path(__file__).resolve().parents[2]
            / "tmp"
            / "NP560-lirt-provision-root-v323.PRG"
        ).read_bytes()

    def test_dispatch_table_captures_state_progression(self) -> None:
        manifest = preprocess.dispatch_manifest(self.image)
        records = manifest["records"]
        self.assertEqual(manifest["source"], "3E:AA46")
        self.assertEqual(manifest["data_view"], "21:AA46")
        self.assertEqual(manifest["zero_boundary"], "3E:AF5A")
        self.assertEqual(records[0], {
            "index": 0,
            "source": "3E:AA46",
            "event": 0x0200,
            "action": 1,
            "argument_segment": 0x52,
            "argument_offset": 0x50EC,
            "next_state": 1,
        })
        self.assertEqual(records[1]["event"], 0x0201)
        self.assertEqual(records[1]["next_state"], 2)
        self.assertEqual(records[2]["event"], 0x0202)
        self.assertEqual(records[2]["next_state"], 3)

    def test_new_failure_chain_is_in_preprocessing_set(self) -> None:
        names = {name for name, _, _ in preprocess.FUNCTIONS}
        self.assertTrue({
            "application-main-loop",
            "application-resource-driver",
            "resident-resource-init",
            "foreground-state-dispatch",
            "startup-default-selector",
            "startup-default-manager",
            "clock-validator",
            "modal-event-loop",
            "modal-event-ready",
            "menu-catalog",
            "menu-event-wrapper",
            "menu-event-dispatch",
            "menu-event-state",
            "resident-main-menu",
            "file-root-pool",
            "file-root-release",
            "file-record-scan",
            "storage-driver-resolve",
            "file-driver-dynamic-wrapper",
            "file-driver-dynamic-child",
        }.issubset(names))

    def test_startup_selector_maps_factory_value_six_to_date_state(self) -> None:
        manifest = preprocess.startup_selector_manifest(self.image)
        mappings = {
            record["selector"]: record["initial_state"]
            for record in manifest["mappings"]
        }
        self.assertEqual(manifest["persistent_byte"], "10:D072")
        self.assertEqual(mappings[6], 1)
        self.assertEqual(mappings[8], 0x4E)

    def test_foreground_control_events_include_idle_and_main_menu(self) -> None:
        manifest = preprocess.foreground_control_manifest(self.image)
        events = {
            record["event"]: record for record in manifest["events"]
        }
        self.assertEqual(events[0x008F]["new_state"], 0x00FE)
        self.assertEqual(events[0x00B0]["new_state"], 0x00FF)
        self.assertEqual(events[0x00B0]["state_write"], "3D:311E")


if __name__ == "__main__":
    unittest.main()
