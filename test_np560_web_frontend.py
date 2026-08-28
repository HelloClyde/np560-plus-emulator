#!/usr/bin/env python3
"""Pin the browser keyboard to the recovered NP560+ hardware matrix."""

from __future__ import annotations

import re
import hashlib
import tempfile
import unittest
from pathlib import Path

from web.np560_web import Emulator, artifact_identity


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "qemu-dmcu" / "web" / "app.js"
INDEX = ROOT / "qemu-dmcu" / "web" / "index.html"
FIRMWARE = ROOT / "NP560+V3.80版系统升级程序" / "NP560.PRG"
EVENT_TABLE_OFFSET = 0x2F29B2
EVENT_TABLE_WORDS = 64
EVENT_TABLE_COUNT = 3


class WebKeyboardFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.javascript = APP.read_text(encoding="utf-8")
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.firmware = FIRMWARE.read_bytes()

    def test_front_panel_function_keys_use_recovered_matrix_positions(self) -> None:
        mapping = {
            name: int(index)
            for name, index in re.findall(
                r"\b(F[1-4]):\s*(\d+)", self.javascript
            )
        }
        self.assertEqual(mapping, {"F1": 23, "F2": 26, "F3": 15, "F4": 4})

        expected_events = {"F1": 0x8B, "F2": 0x8C, "F3": 0x8D, "F4": 0x8E}
        for table in range(EVENT_TABLE_COUNT):
            base = EVENT_TABLE_OFFSET + table * EVENT_TABLE_WORDS * 2
            for name, index in mapping.items():
                offset = base + index * 2
                event = int.from_bytes(
                    self.firmware[offset:offset + 2], "little"
                )
                self.assertEqual(event, expected_events[name])

    def test_browser_matrix_matches_all_recovered_alphanumeric_and_navigation_keys(
            self) -> None:
        block = re.search(
            r"const\s+matrixIndexes\s*=\s*\{(?P<body>.*?)\n\};",
            self.javascript,
            re.DOTALL,
        )
        self.assertIsNotNone(block)
        mapping = {}
        for match in re.finditer(
                r'(?:"(?P<quoted>[^"]+)"|(?P<bare>[A-Za-z][A-Za-z0-9]*))'
                r"\s*:\s*(?P<index>\d+)",
                block.group("body")):
            name = match.group("quoted") or match.group("bare")
            mapping[name] = int(match.group("index"))

        tables = []
        for table in range(EVENT_TABLE_COUNT):
            base = EVENT_TABLE_OFFSET + table * EVENT_TABLE_WORDS * 2
            tables.append([
                int.from_bytes(
                    self.firmware[base + index * 2:base + index * 2 + 2],
                    "little",
                )
                for index in range(EVENT_TABLE_WORDS)
            ])

        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            self.assertEqual(
                tables[0][mapping[letter]],
                ord(letter),
                f"uppercase matrix position for {letter}",
            )
            self.assertEqual(
                tables[2][mapping[letter]],
                ord(letter.lower()),
                f"lowercase matrix position for {letter}",
            )
        for digit in "0123456789":
            self.assertEqual(
                tables[1][mapping[digit]],
                ord(digit),
                f"numeric matrix position for {digit}",
            )

        for name, event in {
            "ArrowUp": 0x82,
            "PageUp": 0x82,
            "ArrowDown": 0x83,
            "PageDown": 0x83,
            "Tab": 0x83,
            "ArrowLeft": 0x84,
            "Escape": 0x84,
            "Backspace": 0x84,
            "ArrowRight": 0x85,
            "Enter": 0x85,
        }.items():
            self.assertEqual(tables[1][mapping[name]], event, name)
            self.assertEqual(tables[2][mapping[name]], event, name)

        self.assertEqual(tables[0][mapping[","]], ord(","))
        self.assertEqual(tables[0][mapping["."]], ord("."))
        self.assertEqual(tables[1][mapping[" "]], ord(" "))
        self.assertEqual(tables[2][mapping[" "]], ord(" "))

    def test_strict_web_input_uses_only_physical_matrix_or_gpio_state(self) -> None:
        class FakeQMP:
            def __init__(self) -> None:
                self.writes = []

            def execute(self, command: str, arguments: dict) -> None:
                self.writes.append((command, arguments))

        emulator = Emulator.__new__(Emulator)
        emulator.legacy_key_latch = False
        emulator.qmp = FakeQMP()
        emulator.set_key(
            state=1 << 1,
            code=0x101,
            matrix_low=0x10000000,
            matrix_high=0,
        )
        self.assertEqual(
            emulator.qmp.writes,
            [
                ("qom-set", {
                    "path": "/machine", "property": "key-code", "value": 0,
                }),
                ("qom-set", {
                    "path": "/machine", "property": "key-matrix-low",
                    "value": 0x10000000,
                }),
                ("qom-set", {
                    "path": "/machine", "property": "key-matrix-high",
                    "value": 0,
                }),
                ("qom-set", {
                    "path": "/machine", "property": "key-state", "value": 0,
                }),
            ],
        )

        emulator.qmp.writes.clear()
        emulator.set_key(state=1 << 1, code=0x101)
        written = {
            arguments["property"]: arguments["value"]
            for command, arguments in emulator.qmp.writes
            if command == "qom-set"
        }
        self.assertEqual(written["key-code"], 0)
        self.assertEqual(written["key-state"], 1 << 1)
        self.assertEqual(written["key-matrix-low"], 0)
        self.assertEqual(written["key-matrix-high"], 0)

    def test_pointer_click_is_long_enough_and_qmp_writes_are_ordered(self) -> None:
        hold = re.search(
            r"const\s+minimumPointerHoldMs\s*=\s*(\d+)", self.javascript
        )
        self.assertIsNotNone(hold)
        self.assertGreaterEqual(int(hold.group(1)), 100)
        self.assertIn(
            "keyRequestQueue = keyRequestQueue.catch(() => {}).then(",
            self.javascript,
        )
        self.assertIn("setTimeout(finishRelease, remaining)", self.javascript)

    def test_artifact_identity_binds_diagnostics_to_exact_rom_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "soc-rom.bin"
            payload = b"np560-v109\0\x07\xbd\x00\x45"
            path.write_bytes(payload)
            size, digest = artifact_identity(path)
        self.assertEqual(size, len(payload))
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())

    def test_loaded_soc_rom_identity_is_visible_in_the_frontend(self) -> None:
        self.assertIn('id="rom-identity"', self.html)
        self.assertIn("state.soc_rom_configured", self.javascript)
        self.assertIn("state.soc_rom_size", self.javascript)
        self.assertIn("state.soc_rom_sha256", self.javascript)
        self.assertIn("SHA-256 ${digestText}", self.javascript)

    def test_custom_glass_status_is_driven_from_guest_lcd_segments(self) -> None:
        self.assertRegex(
            self.html,
            r'<canvas id="lcd" width="240" height="132"',
        )
        self.assertIn("state.lcd_annunciators", self.javascript)
        self.assertIn("annunciatorActive(bytes, 1, 228)", self.javascript)
        self.assertIn("annunciatorActive(bytes, 1, 235)", self.javascript)
        self.assertIn("drawBatteryAnnunciator(bytes, color)", self.javascript)
        self.assertNotIn("state.adc_level", self.javascript)
        self.assertNotIn("state.external_power", self.javascript)

    def test_lightweight_diagnostics_skip_frame_and_nand_queries(self) -> None:
        class FakeProcess:
            returncode = None

            @staticmethod
            def poll():
                return None

        class FakeQMP:
            def __init__(self) -> None:
                self.calls = []

            def execute(self, command: str, arguments: dict | None = None):
                self.calls.append((command, arguments))
                if command == "query-status":
                    return {"running": True, "status": "running"}
                if command == "qom-get":
                    self.assert_cpu_state(arguments)
                    return "PC=20:2DE0\nAPPLICATION_STATE=STATE:0001"
                raise AssertionError(command)

            @staticmethod
            def assert_cpu_state(arguments: dict | None) -> None:
                if arguments != {
                    "path": "/machine", "property": "cpu-state",
                }:
                    raise AssertionError(arguments)

        emulator = Emulator.__new__(Emulator)
        emulator.process = FakeProcess()
        emulator.qmp = FakeQMP()
        result = emulator.diagnostics()
        self.assertEqual(result["status"], "running")
        self.assertIn("APPLICATION_STATE", result["registers"])
        self.assertEqual(
            emulator.qmp.calls,
            [
                ("query-status", None),
                ("qom-get", {
                    "path": "/machine", "property": "cpu-state",
                }),
            ],
        )


if __name__ == "__main__":
    unittest.main()
