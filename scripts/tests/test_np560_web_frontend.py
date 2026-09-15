#!/usr/bin/env python3
"""Pin the browser keyboard to the recovered NP560+ hardware matrix."""

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import base64
import re
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from web.np560_web import Emulator, KeyInputLease, QMPError, artifact_identity


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "scripts" / "web" / "app.js"
INDEX = ROOT / "scripts" / "web" / "index.html"
KEYBOARD_INPUT = ROOT / "scripts" / "web" / "keyboard_input.js"
FIRMWARE = ROOT / "NP560+V3.80版系统升级程序" / "NP560.PRG"
EVENT_TABLE_OFFSET = 0x2F29B2
EVENT_TABLE_WORDS = 64
EVENT_TABLE_COUNT = 3


class WebKeyboardFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.javascript = APP.read_text(encoding="utf-8")
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.keyboard_input = KEYBOARD_INPUT.read_text(encoding="utf-8")
        cls.firmware = FIRMWARE.read_bytes()

    def test_front_panel_function_keys_use_recovered_matrix_positions(self) -> None:
        mapping = {
            name: int(index)
            for name, index in re.findall(
                r"\b(F[1-4]):\s*(\d+)", self.javascript
            )
        }
        self.assertEqual(mapping, {"F1": 60, "F2": 52, "F3": 44, "F4": 4})

        # Uppercase/shift mode has different meanings at these SAME switches.
        # Do not force normal-mode event values in the host frontend.
        expected_events = {
            "F1": (0xDD, 0xE2, 0xE2), "F2": (0xDC, 0xE1, 0xE1),
            "F3": (0xDF, 0xEA, 0xEA), "F4": (0x8E, 0x8E, 0x8E),
        }
        for table in range(EVENT_TABLE_COUNT):
            base = EVENT_TABLE_OFFSET + table * EVENT_TABLE_WORDS * 2
            for name, index in mapping.items():
                offset = base + index * 2
                event = int.from_bytes(
                    self.firmware[offset:offset + 2], "little"
                )
                self.assertEqual(event, expected_events[name][table])

    def test_function_key_meanings_have_original_player_dispatch_evidence(self) -> None:
        # Matrix tables prove switch -> event, not the printed key name.
        # Pin the separate original app evidence behind the corrected names.
        # VMA03 linked code corresponds to PRG offset address - 0x030000.
        def original_words(address, words):
            expected = b"".join(word.to_bytes(2, "little") for word in words)
            offset = address - 0x030000
            self.assertEqual(self.firmware[offset:offset + len(expected)], expected)

        original_words(0x0EA348, (
            0x780B, 0x000E, 0x76F0, 0x00E1, 0xAC01, 0xA364,
            0x76F0, 0x00E2, 0xAC01, 0xA364,
            0x76F0, 0x00EA, 0xAC02, 0xAB50,
        ))
        # EA takes settings mode 2; E1 takes the track-list branch.
        original_words(0x0EA37E, (0x76F3, 0x00EA, 0xAC02, 0xA3F2))
        original_words(0x0EA3B0, (0x4972,))
        original_words(0x0EA3F6, (0x76F3, 0x00E1, 0xAC02, 0xA7BC))
        # The remaining E2 branch calls the original file picker.
        original_words(0x0EA858, (0xBD0C, 0x0000))
        original_words(0x0EA894, (0xBD0C, 0x0000))
        original_words(0x0D555A, (0x76F0, 0x008E, 0xAC01, 0x558E))

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
                re.sub(r"//[^\n]*", "", block.group("body"))):
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
            "ArrowLeft": 0x80,
            "Escape": 0x84,
            "Backspace": 0x84,
            "ArrowRight": 0x81,
            "Enter": 0x86,
            "StartMenu": 0xB0,
        }.items():
            self.assertEqual(tables[1][mapping[name]], event, name)
            self.assertEqual(tables[2][mapping[name]], event, name)

        self.assertIn('data-key="StartMenu"', self.html)

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

    def test_diagnostic_matrix_pulse_is_one_atomic_qom_write(self) -> None:
        class FakeQMP:
            def __init__(self) -> None:
                self.writes = []

            def execute(self, command: str, arguments: dict) -> None:
                self.writes.append((command, arguments))

        emulator = Emulator.__new__(Emulator)
        emulator.qmp = FakeQMP()
        emulator.pulse_matrix(12)
        self.assertEqual(
            emulator.qmp.writes,
            [("qom-set", {
                "path": "/machine",
                "property": "key-matrix-pulse-index",
                "value": 12,
            })],
        )
        for invalid in (-1, 64):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    emulator.pulse_matrix(invalid)
        server = (ROOT / "scripts" / "web" / "np560_web.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('self.path == "/api/key-pulse"', server)
        self.assertIn("self.emulator.pulse_matrix(matrix_index)", server)

    def test_key_status_reads_one_atomic_bounded_qom_snapshot(self) -> None:
        class FakeProcess:
            returncode = None

            @staticmethod
            def poll():
                return None

        class FakeQMP:
            def __init__(self) -> None:
                self.calls = []

            def execute(self, command: str, arguments: dict):
                self.calls.append((command, arguments))
                if command != "qom-get" or arguments != {
                    "path": "/machine", "property": "key-pipeline-status",
                }:
                    raise AssertionError((command, arguments))
                return json.dumps({
                    "maps": 17,
                    "event": 0xB0,
                    "candidates": 23,
                    "candidate": 0x8C,
                    "acknowledgements": 19,
                    "acknowledgement": 0x97,
                    "modal_acknowledgements": 7,
                    "modal_acknowledgement": 0xEA,
                    "matrix_reads": 0x100000023,
                    "matrix_rearmed": True,
                    "application_state": 0x78,
                    "primary_action_selector_calls": 3,
                    "primary_action_selector_returns": 3,
                    "primary_action_selector_result": 0xFFFF,
                    "primary_action_late_paths": 5,
                    "primary_action_object_guard_checks": 6,
                    "primary_action_object_guard_value": 1,
                    "primary_action_object_guard_passes": 2,
                    "primary_action_object_guard_rejects": 4,
                    "primary_action_object_commits": 2,
                    "primary_action_object_commit_flag": 1,
                    "direction_up_paths": 11,
                    "direction_down_paths": 12,
                    "direction_left_paths": 13,
                    "direction_right_paths": 14,
                    "direction_helper_active": False,
                    "direction_helper_calls": 21,
                    "direction_helper_returns": 20,
                    "direction_helper_result": 3,
                    "direction_code": 2,
                    "direction_before_x": 4,
                    "direction_before_y": 5,
                    "direction_before_offset_x": 6,
                    "direction_before_offset_y": 7,
                    "direction_after_x": 4,
                    "direction_after_y": 4,
                    "direction_after_offset_x": 6,
                    "direction_after_offset_y": 8,
                    "direction_before_map_index": 0x1234,
                    "direction_before_scroll": 0x0020,
                    "direction_after_map_index": 0x1235,
                    "direction_after_scroll": 0x001F,
                    "current_direction": 2,
                    "current_x": 4,
                    "current_y": 4,
                    "current_offset_x": 6,
                    "current_offset_y": 8,
                    "current_map_index": 0x1235,
                    "current_scroll": 0x001F,
                    "current_move_state": 3,
                    "render_calls": 15,
                    "render_callback_dispatches": 16,
                    "render_object_valid": True,
                    "render_object_hi": 0,
                    "render_object_lo": 0x3456,
                    "render_stack_object_hi": 0,
                    "render_stack_object_lo": 0x3456,
                    "render_entry_callback_r0": 0x4D58,
                    "render_entry_callback_r1": 0x0051,
                    "render_callback_object_valid": True,
                    "render_callback_object_hi": 0,
                    "render_callback_object_lo": 0x3456,
                    "render_callback_r0": 0x4D58,
                    "render_callback_r1": 0x0051,
                    "render_callback_target_segment": 0x58,
                    "render_callback_target_pc": 0x0051,
                    "render_callback_field_r0": 0x4D58,
                    "render_callback_field_r1": 0x0051,
                    "faulted": False,
                })

        emulator = Emulator.__new__(Emulator)
        emulator.process = FakeProcess()
        emulator.qmp = FakeQMP()
        self.assertEqual(
            emulator.key_status(),
            {
                "maps": 17,
                "event": 0xB0,
                "candidates": 23,
                "candidate": 0x8C,
                "acknowledgements": 19,
                "acknowledgement": 0x97,
                "modal_acknowledgements": 7,
                "modal_acknowledgement": 0xEA,
                "matrix_reads": 0x100000023,
                "matrix_rearmed": True,
                "application_state": 0x78,
                "primary_action_selector_calls": 3,
                "primary_action_selector_returns": 3,
                "primary_action_selector_result": 0xFFFF,
                "primary_action_late_paths": 5,
                "primary_action_object_guard_checks": 6,
                "primary_action_object_guard_value": 1,
                "primary_action_object_guard_passes": 2,
                "primary_action_object_guard_rejects": 4,
                "primary_action_object_commits": 2,
                "primary_action_object_commit_flag": 1,
                "direction_up_paths": 11,
                "direction_down_paths": 12,
                "direction_left_paths": 13,
                "direction_right_paths": 14,
                "direction_helper_active": False,
                "direction_helper_calls": 21,
                "direction_helper_returns": 20,
                "direction_helper_result": 3,
                "direction_code": 2,
                "direction_before_x": 4,
                "direction_before_y": 5,
                "direction_before_offset_x": 6,
                "direction_before_offset_y": 7,
                "direction_after_x": 4,
                "direction_after_y": 4,
                "direction_after_offset_x": 6,
                "direction_after_offset_y": 8,
                "direction_before_map_index": 0x1234,
                "direction_before_scroll": 0x0020,
                "direction_after_map_index": 0x1235,
                "direction_after_scroll": 0x001F,
                "current_direction": 2,
                "current_x": 4,
                "current_y": 4,
                "current_offset_x": 6,
                "current_offset_y": 8,
                "current_map_index": 0x1235,
                "current_scroll": 0x001F,
                "current_move_state": 3,
                "render_calls": 15,
                "render_callback_dispatches": 16,
                "render_object_valid": True,
                "render_object_hi": 0,
                "render_object_lo": 0x3456,
                "render_stack_object_hi": 0,
                "render_stack_object_lo": 0x3456,
                "render_entry_callback_r0": 0x4D58,
                "render_entry_callback_r1": 0x0051,
                "render_callback_object_valid": True,
                "render_callback_object_hi": 0,
                "render_callback_object_lo": 0x3456,
                "render_callback_r0": 0x4D58,
                "render_callback_r1": 0x0051,
                "render_callback_target_segment": 0x58,
                "render_callback_target_pc": 0x0051,
                "render_callback_field_r0": 0x4D58,
                "render_callback_field_r1": 0x0051,
                "faulted": False,
            },
        )
        self.assertEqual(
            emulator.qmp.calls,
            [
                ("qom-get", {
                    "path": "/machine", "property": "key-pipeline-status",
                }),
            ],
        )

    def test_completed_frame_uses_only_complete_lcd_qom_properties(self) -> None:
        class FakeProcess:
            returncode = None

            @staticmethod
            def poll():
                return None

        class FakeQMP:
            def __init__(self) -> None:
                self.calls = []

            def execute(self, command: str, arguments: dict):
                self.calls.append((command, arguments))
                values = {
                    "lcd-completed-frame": base64.b64encode(
                        bytes(240 * 120)
                    ).decode("ascii"),
                    "lcd-completed-frame-sequence": "37",
                }
                return values[arguments["property"]]

        emulator = Emulator.__new__(Emulator)
        emulator.process = FakeProcess()
        emulator.qmp = FakeQMP()
        frame = emulator.completed_frame()
        self.assertEqual(frame["sequence"], 37)
        self.assertEqual(frame["format"], "gray5")
        self.assertEqual(
            base64.b64decode(frame["frame"]), bytes(240 * 120),
        )
        self.assertEqual(
            [call[1]["property"] for call in emulator.qmp.calls],
            ["lcd-completed-frame", "lcd-completed-frame-sequence"],
        )

    def test_code_snapshot_uses_the_separate_dmcu_code_bus(self) -> None:
        payload = bytes.fromhex("172e40152f92")

        class FakeProcess:
            returncode = None

            @staticmethod
            def poll():
                return None

        class FakeQMP:
            def __init__(self) -> None:
                self.calls = []

            def execute(self, command: str, arguments: dict | None = None):
                arguments = arguments or {}
                self.calls.append((command, arguments))
                if command == "qom-set":
                    self.assert_code_save(arguments)
                    Path(arguments["value"].split("@", 1)[1]).write_bytes(
                        payload
                    )
                    return None
                if command == "query-status":
                    return {"running": True, "status": "running"}
                values = {
                    "lcd-annunciators": "none",
                    "cpu-state": "PC=00:56c0",
                    "nand-state": "ready",
                    "soc-rom": "reconstructed.bin",
                }
                return values[arguments["property"]]

            @staticmethod
            def assert_code_save(arguments: dict) -> None:
                if arguments != {
                    "path": "/machine",
                    "property": "debug-code-save",
                    "value": arguments["value"],
                }:
                    raise AssertionError(arguments)
                if not arguments["value"].startswith("0x56c0:0x6@"):
                    raise AssertionError(arguments["value"])

        with tempfile.TemporaryDirectory() as directory:
            emulator = Emulator.__new__(Emulator)
            emulator.process = FakeProcess()
            emulator.qmp = FakeQMP()
            emulator.frame_path = Path(directory) / "snapshot.bin"
            emulator.nand_save_on_exit = None
            emulator.soc_rom_size = len(payload)
            emulator.soc_rom_sha256 = hashlib.sha256(payload).hexdigest()

            state = emulator.snapshot("code", 0x56C0, len(payload))

        self.assertEqual(base64.b64decode(state["frame"]), payload)
        self.assertEqual(state["source"], "code")
        self.assertEqual(
            state["lcd_state"], "Raw NP560 DMCU code-bus diagnostic view"
        )
        self.assertEqual(emulator.qmp.calls[0][0], "qom-set")

    def test_pointer_click_is_long_enough_and_qmp_writes_are_ordered(self) -> None:
        hold = re.search(
            r"const\s+minimumPointerHoldMs\s*=\s*(\d+)", self.javascript
        )
        self.assertIsNotNone(hold)
        # Two original keyboard scans can span 125 ms. Pointer taps include
        # margin; this does not change PC key-up or guest repeat semantics.
        self.assertEqual(int(hold.group(1)), 150)
        self.assertIn(
            "const request = keyRequestQueue.catch(() => {}).then(",
            self.javascript,
        )
        self.assertIn("setTimeout(() => finishRelease(sourceName), remaining)", self.javascript)
        self.assertIn("button.setPointerCapture(event.pointerId)", self.javascript)
        self.assertNotIn('button.addEventListener("pointerleave"', self.javascript)

    def test_rapid_pointer_repress_recaptures_before_deduplicating_make(
            self) -> None:
        bind = re.search(
            r"function bindKeyButton\(button\) \{(?P<body>.*?)\n\}",
            self.javascript,
            re.DOTALL,
        )
        self.assertIsNotNone(bind)
        body = bind.group("body")
        press = re.search(
            r"const press = event => \{(?P<body>.*?)\n  \};",
            body,
            re.DOTALL,
        )
        self.assertIsNotNone(press)
        press_body = press.group("body")
        capture = 'button.setPointerCapture(event.pointerId)'
        refresh = 'pointerPressedAt.set(sourceName, performance.now())'
        deduplicate = 'if (!keyboardInput.hasSource(sourceName)) keyboardInput.press'
        self.assertLess(press_body.index(capture),
                        press_body.index(deduplicate))
        self.assertLess(press_body.index(refresh),
                        press_body.index(deduplicate))
        self.assertIn("pointerButtonId", body)
        self.assertIn(
            "`pointer:${pointerButtonId}:${code}:${event.pointerId}`",
            body,
        )

    def test_pointer_transport_timing_and_cancellation(self) -> None:
        subprocess.run(
            ["node", str(ROOT / "scripts" / "tests" / "test_np560_pointer_input.js")],
            check=True, cwd=ROOT, capture_output=True, text=True,
        )

    def test_keyboard_controller_preserves_physical_hold_and_deduplicates_make(
            self) -> None:
        script = f"""
const assert = require("assert");
const {{ KeyboardMatrixController }} = require({json.dumps(str(KEYBOARD_INPUT))});
const sent = [];
const input = new KeyboardMatrixController({{
  matrixIndexes: {{ A: 10, Escape: 28, ArrowLeft: 28, Enter: 53, StartMenu: 55 }},
  keyBits: {{ Escape: 5, ArrowLeft: 2, Enter: 4, StartMenu: 15 }},
  sendPayload: payload => sent.push(payload),
}});
assert.strictEqual(input.press("keyboard:KeyA", "A"), true);
assert.strictEqual(input.press("keyboard:KeyA", "A"), false);
assert.strictEqual(sent.length, 1, "browser repeat emitted a second make");
assert.strictEqual(sent[0].matrix_low >>> 0, (1 << 10) >>> 0);
assert.strictEqual(input.press("pointer:A:1", "A"), false);
assert.strictEqual(input.release("keyboard:KeyA"), false);
assert.strictEqual(sent.length, 1, "one source released a still-held switch");
assert.strictEqual(input.release("pointer:A:1"), true);
assert.deepStrictEqual(sent.at(-1), {{
  state: 0, code: 0, matrix_low: 0, matrix_high: 0,
}});

assert.strictEqual(input.press("keyboard:Escape", "Escape"), true);
assert.strictEqual(input.press("pointer:ArrowLeft:2", "ArrowLeft"), false);
assert.strictEqual(input.release("keyboard:Escape"), false);
assert.strictEqual(input.release("pointer:ArrowLeft:2"), true);

assert.strictEqual(input.press("keyboard:Enter", "Enter"), true);
const beforeResend = sent.length;
assert.strictEqual(input.resendHeld(), true);
assert.strictEqual(sent.length, beforeResend + 1);
assert.strictEqual(input.press("keyboard:Home", "StartMenu"), true);
assert.strictEqual(sent.at(-1).matrix_high >>> 0,
  ((1 << (53 - 32)) | (1 << (55 - 32))) >>> 0);
assert.strictEqual(input.press("keyboard:Unknown", "Unknown"), false);
const beforeReleaseAll = sent.length;
assert.strictEqual(input.releaseAll(), true);
assert.strictEqual(sent.length, beforeReleaseAll + 1);
assert.strictEqual(input.releaseAll(), false);
assert.strictEqual(input.releaseAll(true), true);
"""
        subprocess.run(
            ["node", "-e", script], check=True, cwd=ROOT,
            capture_output=True, text=True,
        )

    def test_real_frontend_function_keys_emit_correct_physical_switches(self) -> None:
        script = f"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {{ KeyboardMatrixController, normalizeKeyboardEvent }} =
  require({json.dumps(str(KEYBOARD_INPUT))});
const source = fs.readFileSync({json.dumps(str(APP))}, "utf8");
const declarations = ["keyBits", "matrixIndexes"].map(name => {{
  const start = source.indexOf(`const ${{name}} = {{`);
  assert.ok(start >= 0);
  const end = source.indexOf("\\n}};", start);
  assert.ok(end > start);
  return source.slice(start, end + 3);
}}).join("\\n");
const mapping = vm.runInNewContext(declarations + "\\n({{ keyBits, matrixIndexes }})");
const sent = [];
const input = new KeyboardMatrixController({{
  ...mapping, sendPayload: payload => sent.push(payload),
}});
for (const [key, index] of Object.entries({{ F1: 60, F2: 52, F3: 44, F4: 4 }})) {{
  const normalized = normalizeKeyboardEvent({{ code: key, key }});
  assert.equal(normalized, key);
  input.press(`keyboard:${{key}}`, normalized);
  const payload = sent.at(-1);
  assert.equal(payload.matrix_low >>> 0, index < 32 ? (1 << index) >>> 0 : 0);
  assert.equal(payload.matrix_high >>> 0, index >= 32 ? (1 << (index - 32)) >>> 0 : 0);
  const count = sent.length;
  input.press(`keyboard:${{key}}`, normalized);
  assert.equal(sent.length, count, "held F key must not inject another make");
  input.release(`keyboard:${{key}}`);
  assert.equal(sent.at(-1).matrix_low, 0);
  assert.equal(sent.at(-1).matrix_high, 0);
}}
"""
        subprocess.run(
            ["node", "-e", script], check=True, cwd=ROOT,
            capture_output=True, text=True,
        )

    def test_pc_key_normalizer_accepts_only_evidenced_frontend_keys(self) -> None:
        script = f"""
const assert = require("assert");
const {{ normalizeKeyboardEvent }} = require({json.dumps(str(KEYBOARD_INPUT))});
assert.strictEqual(normalizeKeyboardEvent({{ code: "KeyQ", key: "q" }}), "Q");
assert.strictEqual(normalizeKeyboardEvent({{ code: "Digit1", key: "!" }}), "1");
assert.strictEqual(normalizeKeyboardEvent({{ code: "Home", key: "Home" }}), "StartMenu");
assert.strictEqual(normalizeKeyboardEvent({{ code: "ArrowDown", key: "ArrowDown" }}), "ArrowDown");
assert.strictEqual(normalizeKeyboardEvent({{ code: "Slash", key: "/" }}), null);
assert.strictEqual(normalizeKeyboardEvent({{ code: "Delete", key: "Delete" }}), null);
"""
        subprocess.run(
            ["node", "-e", script], check=True, cwd=ROOT,
            capture_output=True, text=True,
        )

    def test_focus_disconnect_and_page_exit_release_every_matrix_bit(self) -> None:
        self.assertIn('window.addEventListener("blur"', self.javascript)
        self.assertIn('document.addEventListener("visibilitychange"', self.javascript)
        self.assertIn('window.addEventListener("pagehide", sendEmergencyRelease)', self.javascript)
        self.assertIn('window.addEventListener("beforeunload", sendEmergencyRelease)', self.javascript)
        self.assertIn("navigator.sendBeacon(", self.javascript)
        self.assertIn("if (keyboardInput.hasHeldKeys()) releaseAllKeys(true)", self.javascript)
        self.assertIn("synchronizeReleasedBackend();", self.javascript)
        self.assertIn('api("/api/key-heartbeat"', self.javascript)
        self.assertIn("lease_id: keyLeaseId", self.javascript)
        self.assertIn("keyboardInput.resendHeld();", self.javascript)
        self.assertIn(
            "state: 0, code: 0, matrix_low: 0, matrix_high: 0",
            self.javascript,
        )

    def test_visible_keyboard_identifies_confirmed_and_unmapped_hardware(self) -> None:
        self.assertLess(
            self.html.index('src="keyboard_input.js"'),
            self.html.index('src="app.js"'),
        )
        self.assertIn("实体按键（已恢复映射）", self.html)
        self.assertIn("其余侧键仍标记为未映射", self.html)
        self.assertIn("button.dataset.matrixIndex", self.javascript)
        self.assertIn('content: "M" attr(data-matrix-index)',
                      (ROOT / "scripts" / "web" / "styles.css").read_text(
                          encoding="utf-8"))

    def test_server_key_lease_releases_disconnect_without_repeating_make(
            self) -> None:
        class FakeEmulator:
            def __init__(self) -> None:
                self.keys = []

            def set_key(self, state, code, matrix_low=0, matrix_high=0):
                self.keys.append((state, code, matrix_low, matrix_high))

        now = [100.0]
        emulator = FakeEmulator()
        lease = KeyInputLease(
            emulator, clock=lambda: now[0], start_worker=False,
        )
        try:
            self.assertTrue(lease.apply(0, 0, 1 << 10, 0, "page-a", 1000))
            self.assertEqual(emulator.keys, [(0, 0, 1 << 10, 0)])
            now[0] = 100.7
            self.assertTrue(lease.heartbeat("page-a"))
            self.assertFalse(lease.expire_due(101.1))
            self.assertEqual(len(emulator.keys), 1)
            self.assertTrue(lease.expire_due(101.8))
            self.assertEqual(emulator.keys[-1], (0, 0, 0, 0))

            self.assertTrue(lease.apply(0, 0, 0, 1 << 21,
                                        "page-b", 1000))
            before_stale_release = list(emulator.keys)
            self.assertFalse(lease.apply(0, 0, 0, 0, "page-a", 1000))
            self.assertEqual(emulator.keys, before_stale_release)
            self.assertFalse(lease.apply(0, 0, 1 << 7, 0,
                                         "page-a", 1000))
            self.assertEqual(emulator.keys, before_stale_release)
            self.assertFalse(lease.heartbeat("page-a"))
            self.assertTrue(lease.apply(0, 0, 0, 0, "page-b", 1000))

            # Existing probe/API clients omit lease_id and retain their old
            # behavior; no watchdog is armed for them.
            self.assertTrue(lease.apply(0, 0, 1 << 2, 0))
            self.assertFalse(lease.expire_due(1000.0))
        finally:
            lease.close()

    def test_new_key_lease_retries_only_after_live_owner_expires(self) -> None:
        class FakeEmulator:
            def __init__(self) -> None:
                self.keys = []

            def set_key(self, state, code, matrix_low=0, matrix_high=0):
                self.keys.append((state, code, matrix_low, matrix_high))

        now = [200.0]
        emulator = FakeEmulator()
        lease = KeyInputLease(
            emulator, clock=lambda: now[0], start_worker=False,
        )
        try:
            self.assertTrue(lease.apply(0, 0, 1 << 3, 0,
                                        "old-page", 1000))
            old_level = list(emulator.keys)
            self.assertFalse(lease.apply(0, 0, 1 << 8, 0,
                                         "new-page", 1000))
            self.assertFalse(lease.apply(0, 0, 0, 0,
                                         "new-page", 1000))
            self.assertEqual(emulator.keys, old_level)
            self.assertFalse(lease.heartbeat("new-page"))

            now[0] = 201.01
            self.assertTrue(lease.expire_due())
            self.assertEqual(emulator.keys[-1], (0, 0, 0, 0))
            self.assertTrue(lease.apply(0, 0, 1 << 8, 0,
                                        "new-page", 1000))
            self.assertTrue(lease.heartbeat("new-page"))
            self.assertEqual(emulator.keys[-1], (0, 0, 1 << 8, 0))
        finally:
            lease.close()

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

    def test_web_reset_is_not_converted_into_process_exit(self) -> None:
        backend = (ROOT / "scripts" / "web" / "np560_web.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"reset": "system_reset"', backend)
        self.assertNotIn('"-no-reboot"', backend)

        machine = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        self.assertIn("mc->reset = np560_machine_reset;", machine)
        reset = machine.split(
            "static void np560_machine_reset", 1
        )[1].split("static bool np560_get_hle_ui", 1)[0]
        self.assertIn("s->reset_data_snapshot", reset)
        self.assertIn("NP560_APPLICATION_OPERATION_ACTION_UI_OVERLAY_SIZE",
                      reset)
        self.assertIn("NP560_APPLICATION_OPERATION_ACTION_CODE_PAGE_SIZE",
                      reset)
        self.assertIn("qemu_devices_reset(reason);", reset)
        self.assertIn("cpu_reset(CPU(s->cpu));", reset)
        self.assertNotIn("np560_load_nand_image", reset)
        self.assertLess(reset.index("cpu_reset(CPU(s->cpu));"),
                        reset.index("qemu_devices_reset(reason);"))
        # A checkpoint seeds nonvolatile storage at machine creation, not at
        # every reset. Rewinding it discards native settings and game saves.
        self.assertEqual(machine.count("np560_load_nand_image(s);"), 1)
        self.assertIn("qemu_register_reset(np560_nand_reset, s);", machine)

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

    def test_audio_snapshot_is_read_only_and_validated(self) -> None:
        class FakeProcess:
            @staticmethod
            def poll():
                return None

        class FakeQMP:
            def __init__(self):
                self.calls = []
                self.response = None

            def execute(self, command, arguments):
                self.calls.append((command, arguments))
                return self.response

        emulator = Emulator.__new__(Emulator)
        emulator.process = FakeProcess()
        emulator.qmp = FakeQMP()
        emulator.audio_stream_id = "isolated-test-process"
        packet = {"format": "s16le", "sample_rate": 48000, "channels": 2,
                  "generation": 2, "first_frame": 100, "next_frame": 101,
                  "pcm": base64.b64encode(b"\x34\x12\xff\xff").decode("ascii")}
        emulator.qmp.response = json.dumps(packet)
        first = emulator.audio()
        self.assertEqual(first, {**packet, "stream_id": emulator.audio_stream_id})
        self.assertEqual(first, emulator.audio(), "reading must not dequeue PCM")
        self.assertEqual(emulator.qmp.calls, [
            ("qom-get", {"path": "/machine", "property": "audio-pcm"})] * 2)
        for bad in (None, False, -1, 2**53):
            emulator.qmp.response = json.dumps({**packet, "generation": bad})
            with self.assertRaises(QMPError):
                emulator.audio()
        for bad in (None, "not JSON", "[]",
                    json.dumps({**packet, "next_frame": 2**53}),
                    json.dumps({**packet, "pcm": "AA=="})):
            emulator.qmp.response = bad
            with self.assertRaises(QMPError):
                emulator.audio()


if __name__ == "__main__":
    unittest.main()
