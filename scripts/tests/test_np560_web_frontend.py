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
    def test_home_tabs_keep_device_primary_and_move_short_tap_to_settings(self) -> None:
        self.assertNotIn("<h1>网络学习机</h1>", self.html)
        self.assertLess(self.html.index('class="audio-controls"'), self.html.index('class="run-state"'))
        self.assertIn('role="tablist" aria-label="首页页面"', self.html)
        for name in ("device", "settings", "files", "about"):
            with self.subTest(name=name):
                self.assertIn(f'id="tab-{name}" role="tab" aria-controls="panel-{name}"', self.html)
                self.assertIn(f'id="panel-{name}" role="tabpanel"', self.html)
        self.assertNotIn('id="tab-input"', self.html)
        self.assertNotIn('id="panel-input"', self.html)
        self.assertNotIn('class="touch-keyboard-panel"', self.html)
        self.assertNotIn('id="keyboard" class="keyboard"', self.html)
        self.assertIn('id="keyboard-short-tap"', self.html)
        self.assertIn('id="panel-settings" role="tabpanel" aria-labelledby="tab-settings" hidden', self.html)
        settings = self.html.split('id="panel-settings"', 1)[1].split('id="panel-files"', 1)[0]
        for first, second in ((">LCD</summary>", ">按键</summary>"),
                              (">按键</summary>", ">日志</summary>")):
            self.assertLess(settings.index(first), settings.index(second))
        self.assertLess(settings.index('>按键</summary>'), settings.index('id="keyboard-short-tap"'))
        self.assertLess(settings.index('>日志</summary>'), settings.index('id="registers"'))
        self.assertIn('<details class="input-deck" id="raw-matrix-panel">', self.html)
        self.assertIn('id="raw-matrix-panel"', self.html)
        self.assertNotIn('id="tab-debug"', self.html)
        self.assertNotIn('id="panel-debug"', self.html)
        self.assertNotIn('按键说明与原始矩阵', self.html)
        self.assertIn('event.stopPropagation();\n    void changeHomeTab(homeTabs[next]);', self.javascript)
        self.assertIn('id="panel-files" role="tabpanel" aria-labelledby="tab-files" hidden', self.html)

    def test_register_dump_has_bounded_scrollable_viewport(self) -> None:
        self.assertIn('id="registers" aria-label="DMCU 寄存器" tabindex="0"', self.html)
        styles = (ROOT / "scripts" / "web" / "styles.css").read_text(encoding="utf-8")
        rule = styles.split("#registers {", 1)[1].split("}", 1)[0]
        self.assertIn("height: min(34rem, 60vh)", rule)
        self.assertIn("overflow: auto", rule)

    def test_user_run_starts_audio_before_control_request(self) -> None:
        self.assertIn('button.addEventListener("click", enableAudioOnFirstGesture);',
                      self.javascript)
        self.assertIn('async function resumeFromFiles() {\n  if (!filesOffline) return true;\n  enableAudioOnFirstGesture();',
                      self.javascript)
        self.assertIn('if (event.repeat) return;\n  enableAudioOnFirstGesture();',
                      self.javascript)
        script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync(process.argv[1], 'utf8');
const start = app.indexOf('document.querySelectorAll("[data-action]").forEach');
const end = app.indexOf('document.getElementById("backlight")', start);
assert.ok(start >= 0 && end > start);
const order = [], handlers = {};
const buttons = ['resume', 'pause'].map(action => ({dataset: {action},
  addEventListener: (name, handler) => {handlers[action] = handler;}}));
const context = {document: {querySelectorAll: () => buttons},
  enableAudioOnFirstGesture: () => order.push('audio'),
  api: () => {order.push('api'); return Promise.resolve();},
  statusText: {textContent: ''}};
vm.runInNewContext(app.slice(start, end), context);
Promise.resolve().then(() => handlers.resume()).then(() => {
  assert.deepEqual(order, ['audio', 'api']);
  order.length = 0;
  return handlers.pause();
}).then(() => assert.deepEqual(order, ['api']))
  .catch(error => {console.error(error); process.exitCode = 1;});
'''
        result = subprocess.run(
            ["node", "-e", script, str(APP)], capture_output=True, text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_nand_entry_uses_html_dialog_and_cancel_does_not_stop_guest(self) -> None:
        self.assertIn('<dialog id="files-confirm-dialog"', self.html)
        self.assertIn('form method="dialog"', self.html)
        self.assertIn('filesConfirmDialog.showModal()', self.javascript)
        self.assertNotIn('confirm("进入 NAND 文件管理', self.javascript)
        script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync(process.argv[1], 'utf8');
const start = app.indexOf('async function openFilesTab()');
const end = app.indexOf('async function resumeFromFiles()', start);
assert.ok(start >= 0 && end > start);
const calls = [];
const context = {
  filesOffline: false, filesBusy: false,
  confirmFilesShutdown: async () => false,
  listNandFiles: async () => calls.push('list'),
  setFileMessage: () => calls.push('message'),
  releaseAllKeys: () => calls.push('release'),
  keyRequestQueue: Promise.resolve(),
  audioOutput: {stop: () => calls.push('audio-stop')},
  setFilesOffline: () => calls.push('power-off'),
  api: async () => calls.push('api'),
};
vm.runInNewContext(app.slice(start, end) + '; globalThis.openFilesTab = openFilesTab;', context);
context.openFilesTab().then(result => {
  assert.equal(result, false);
  assert.equal(context.filesBusy, false);
  assert.deepEqual(calls, []);
}).catch(error => { console.error(error); process.exitCode = 1; });
'''
        result = subprocess.run(
            ["node", "-e", script, str(APP)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_about_tab_embeds_original_manual_and_credits(self) -> None:
        manual = ROOT / "scripts" / "web" / "assets" / "np560plus-manual.pdf"
        self.assertTrue(manual.is_file())
        with manual.open("rb") as stream:
            self.assertEqual(stream.read(5), b"%PDF-")
        self.assertIn('id="panel-about" role="tabpanel" aria-labelledby="tab-about" hidden', self.html)
        self.assertIn("模拟器作者：HelloClyde", self.html)
        self.assertIn("Thanks：步步高电子词典游戏群（830340878）", self.html)
        self.assertIn('src="assets/np560plus-manual.pdf"', self.html)

    def test_additional_skin_keys_use_verified_matrix_contacts(self) -> None:
        contacts = (
            ("左侧翻页盘上", 11, (0xC1, 0x94, 0x94), 117, 465),
            ("左侧翻页盘中／确认", 19, (0x92, 0x92, 0x92), 117, 505),
            ("左侧翻页盘下", 27, (0xC2, 0x95, 0x95), 117, 555),
            ("设置", 12, (0xE0, 0xE0, 0xE0), 88, 634),
            ("生词／@", 57, (0x40, 0xE3, 0xE3), 1000, 927),
            ("音标／?", 62, (0x3F, 0xE7, 0xE7), 1000, 1003),
            ("英汉词典／朗文双解", 42, (0xB8, 0xB8, 0xB8), 154, 1069),
            ("简明汉英／现代汉语", 50, (0xEE, 0xEE, 0xEE), 248, 1069),
            ("屏幕取词", 7, (0xC0, 0xC0, 0xC0), 342, 1069),
            ("输入法", 58, (0xED, 0x7B, 0x7B), 530, 1069),
            ("删除", 47, (0x89, 0x89, 0x89), 624, 1069),
            ("查找", 23, (0x8B, 0x8B, 0x8B), 718, 1069),
            ("添加", 31, (0x88, 0x88, 0x88), 812, 1069),
            ("修改／*", 39, (0x2A, 0x8A, 0x8A), 906, 1069),
        )
        for label, index, events, x, y in contacts:
            with self.subTest(label=label):
                self.assertIn(
                    f'add("Matrix{index:02d}", "{label}", {x}, {y},',
                    self.javascript,
                )
                for table, event in enumerate(events):
                    offset = EVENT_TABLE_OFFSET + (table * 64 + index) * 2
                    self.assertEqual(
                        int.from_bytes(self.firmware[offset:offset + 2], "little"),
                        event,
                    )

    def test_right_side_shortcuts_have_physical_skin_hotspots(self) -> None:
        for label, index, event, y in (
            ("同步学习", 59, 0xB4, 198),
            ("多科助考", 51, 0xB7, 258),
            ("我的硬盘", 43, 0xBF, 318),
            ("MP3", 35, 0x97, 377),
        ):
            with self.subTest(label=label):
                self.assertIn(
                    f'add("Matrix{index}", "{label}", 1038, {y}, 129, 37)',
                    self.javascript,
                )
                for table in range(3):
                    offset = EVENT_TABLE_OFFSET + (table * 64 + index) * 2
                    self.assertEqual(
                        int.from_bytes(self.firmware[offset:offset + 2], "little"),
                        event,
                    )

    def test_side_power_uses_guest_m63_not_host_shutdown(self) -> None:
        self.assertIn('add("Matrix63", "电源／休眠", 1019, 1195, 56, 56)', self.javascript)
        self.assertIn('power.classList.add("skin-side-power")', self.javascript)
        self.assertIn('class="skin-power-icon"', self.javascript)
        self.assertRegex(self.html, r'data-key="Matrix63"[^>]*>电源／休眠</button>')
        for table in range(EVENT_TABLE_COUNT):
            offset = EVENT_TABLE_OFFSET + (table * 64 + 63) * 2
            self.assertEqual(self.firmware[offset:offset + 2], b'\x8f\x00')

    def test_six_status_electrodes_are_drawn_individually(self) -> None:
        self.assertNotIn("annunciatorGroupActive", self.javascript)
        for bit, x in ((133, 92), (150, 110), (163, 128),
                       (179, 146), (196, 164), (211, 182)):
            with self.subTest(bit=bit):
                self.assertIn(f"{{ bit: {bit}, x: {x}, pixels:", self.javascript)
        self.assertIn("annunciatorActive(bytes, 1, artwork.bit)", self.javascript)
        self.assertIn("drawBatteryAnnunciator(bytes, color)", self.javascript)

    def test_directory_key_is_on_physical_skin_not_a_start_shortcut(self) -> None:
        self.assertRegex(
            self.javascript,
            r'add\("StartMenu", "目录（返回总目录）", 1000, 1069, 94, 65\)',
        )
        self.assertNotIn('class="skin-quick-controls"', self.html)
        self.assertNotIn('开始／主界面', self.html)
        self.assertIn('add("StartMenu", "目录（返回总目录）"', self.javascript)

    def test_mp3_shortcut_reuses_original_matrix_contact(self) -> None:
        self.assertIn('add("Matrix35", "MP3"', self.javascript)
        for table in range(3):
            offset = EVENT_TABLE_OFFSET + (table * 64 + 35) * 2
            self.assertEqual(self.firmware[offset:offset + 2], b'\x97\x00')

    def test_mode_switch_uses_raw_matrix_and_factory_table_selection(self) -> None:
        # Expose the existing contact, not a host-side Shift/character injector.
        self.assertIn('add("Matrix26", "SHIFT／符号模式（候选映射）"', self.javascript)
        for table in range(3):
            offset = EVENT_TABLE_OFFSET + (table * 64 + 26) * 2
            self.assertEqual(self.firmware[offset:offset + 2], b'\x8c\x00')
        # Source worker 45:F4A4: bit 2 overrides bit 0; bit 0 selects
        # 32:29B2. M26 clears/sets bit 0 in the ORIGINAL worker.
        for offset, words in {
            0x25F4EC: (0x6810, 0x00A2, 0x99F0, 0x28D3, 0x5404, 0x5600),
            0x25F538: (0x6810, 0x00A2, 0x99F0, 0x28D3, 0x5401, 0x5600, 0xAC01, 0xF584),
            0x25F55E: (0x68F3, 0x29B2, 0x68F2, 0x0032),
            0x25F628: (0x6810, 0x00A2, 0x99F0, 0x28D3, 0x74F0, 0xFFFE),
            0x25F65C: (0x6810, 0x00A2, 0x99F0, 0x28D3, 0x5501),
        }.items():
            expected = b''.join(word.to_bytes(2, 'little') for word in words)
            self.assertEqual(self.firmware[offset:offset + len(expected)], expected)

    def test_game_speech_key_is_available_on_skin_without_expanding_keyboard(self) -> None:
        self.assertIn('add(" ", "发音／空格"', self.javascript)

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
            "Escape": 0x8E,
            "Backspace": 0x84,
            "ArrowRight": 0x81,
            "Enter": 0x86,
            "StartMenu": 0xB0,
        }.items():
            self.assertEqual(tables[1][mapping[name]], event, name)
            self.assertEqual(tables[2][mapping[name]], event, name)

        self.assertIn('add("StartMenu", "目录（返回总目录）"', self.javascript)

        self.assertEqual(tables[0][mapping[","]], ord(","))
        self.assertEqual(tables[0][mapping["."]], ord("."))
        self.assertEqual(mapping["Escape"], 4)
        self.assertEqual(mapping["'"], 28)
        self.assertIn('add("Escape", "返回"', self.javascript)
        self.assertIn('data-key="Escape">返回', self.html)
        self.assertEqual([table[mapping["'"]] for table in tables],
                         [ord("'"), 0x84, 0x84])
        self.assertEqual(tables[1][mapping[" "]], ord(" "))
        self.assertEqual(tables[2][mapping[" "]], ord(" "))

    def test_core_legacy_navigation_agrees_with_web_matrix(self) -> None:
        from test_np560_system_boot import matrix_key

        for raw, expected in {
                0x102: (1 << 2, 45, 0x80),
                0x103: (1 << 3, 29, 0x81),
                0x104: (1 << 4, 53, 0x86),
                0x105: (1 << 5, 4, 0x8E),
                0x106: (1 << 6, 28, 0x84)}.items():
            self.assertEqual(matrix_key(raw), expected)
        core = (ROOT / "qemu-dmcu/hw/dmcu/np560.c").read_text(encoding="utf-8")
        table = re.search(r"legacy_matrix_indexes\[16\]\s*=\s*\{([^}]+)\}", core)
        self.assertIsNotNone(table)
        indexes = [int(value) for value in re.findall(r"\d+", table.group(1))]
        names = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Enter",
                 "Escape", "Backspace", "Tab", "F1", "F2", "F3", "F4",
                 "PageUp", "PageDown", " ", "StartMenu"]
        block = re.search(r"const matrixIndexes = \{(.*?)\n\};",
                          self.javascript, re.DOTALL).group(1)
        block = re.sub(r"//[^\n]*", "", block)
        for bit, name in enumerate(names):
            with self.subTest(key=name, bit=bit):
                pattern = (r'" "' if name == " " else rf"\b{re.escape(name)}")
                index = int(re.search(pattern + r"\s*:\s*(\d+)", block).group(1))
                self.assertEqual(indexes[bit], index)

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

    def test_atomic_key_snapshot_has_no_intermediate_matrix_or_error_fallback(self) -> None:
        class FakeQMP:
            def __init__(self):
                self.writes = []
                self.fail = False

            def execute(self, command, arguments):
                self.writes.append((command, arguments))
                if self.fail:
                    raise QMPError("transport lost")

        emulator = Emulator.__new__(Emulator)
        emulator.qmp = FakeQMP()
        emulator.atomic_key_input = True
        emulator.legacy_key_latch = False
        for low, high in ((0x80000000, 0), (0, 0x80000000),
                          (0xFFFFFFFF, 0xFFFFFFFF), (0, 0)):
            emulator.set_key(0, 0x101, low, high)
            self.assertEqual(emulator.qmp.writes[-1], ("qom-set", {
                "path": "/machine", "property": "key-input-snapshot",
                "value": f"00000000:00000000:{low:08x}:{high:08x}",
            }))
        self.assertEqual(len(emulator.qmp.writes), 4)
        emulator.set_key(2, 0x101, 0, 1)
        self.assertEqual(emulator.qmp.writes[-1][1]["value"],
                         "00000000:00000000:00000000:00000001")
        emulator.legacy_key_latch = True
        emulator.set_key(2, 0x101, 0, 1)
        self.assertEqual(emulator.qmp.writes[-1][1]["value"],
                         "00000002:00000101:00000000:00000001")
        emulator.qmp.fail = True
        count = len(emulator.qmp.writes)
        with self.assertRaises(QMPError):
            emulator.set_key(0, 0)
        self.assertEqual(len(emulator.qmp.writes), count + 1)

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

    def test_optional_keyboard_contact(self) -> None:
        subprocess.run(
            ["node", str(ROOT / "scripts/tests/test_np560_keyboard_contact.js")],
            check=True, capture_output=True, text=True,
        )

    def test_keyboard_event_filtering_and_release(self) -> None:
        subprocess.run(
            ["node", str(ROOT / "scripts" / "tests" / "test_np560_keyboard_events.js")],
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

    def test_raw_matrix_buttons_cover_all_switches_and_share_alias_levels(self) -> None:
        script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync(process.argv[1], 'utf8');
const {KeyboardMatrixController} = require(process.argv[2]);
const buttons = [];
const document = {
  getElementById(id) {
    assert.equal(id, 'matrix-keyboard');
    return {appendChild(button) {buttons.push(button);}};
  },
  createElement(tag) {
    assert.equal(tag, 'button');
    return {dataset: {}, attrs: {},
      classList: {toggle(name, value) {this[name] = value;}},
      setAttribute(name, value) {this.attrs[name] = value;}};
  },
  querySelectorAll() {return buttons;},
};
const context = vm.createContext({document});
const mapping = app.slice(app.indexOf('const matrixIndexes ='),
                          app.indexOf('// Original TBC='));
function actualFunction(name) {
  const match = app.match(new RegExp('^function ' + name + '\\([^]*?^}', 'm'));
  assert.ok(match, name);
  return match[0];
}
vm.runInContext(mapping + '\n' + actualFunction('buildRawMatrixKeyboard') +
  '\n' + actualFunction('updatePressedButtons') +
  '\nbuildRawMatrixKeyboard(); globalThis.mapping = matrixIndexes;', context);
assert.equal(buttons.length, 64);
assert.equal(new Set(buttons.map(button => button.dataset.key)).size, 64);
const payloads = [];
const controller = new KeyboardMatrixController({matrixIndexes: context.mapping,
  keyBits: {}, sendPayload: payload => payloads.push(payload),
  onHeldChange: held => context.updatePressedButtons(held)});
for (let index = 0; index < 64; index++) {
  const button = buttons[index];
  assert.equal(button.textContent, `M${String(index).padStart(2, '0')}`);
  assert.equal(button.type, 'button');
  assert.equal(controller.press('raw', button.dataset.key), true);
  assert.equal(payloads.at(-1).matrix_low, index < 32 ? (2 ** index) >>> 0 : 0);
  assert.equal(payloads.at(-1).matrix_high, index >= 32 ? (2 ** (index-32)) >>> 0 : 0);
  assert.equal(button.attrs['aria-pressed'], 'true');
  assert.equal(buttons.filter(b => b.classList['is-pressed']).length, 1);
  controller.release('raw');
  assert.equal(payloads.at(-1).matrix_low, 0);
  assert.equal(payloads.at(-1).matrix_high, 0);
  assert.equal(button.attrs['aria-pressed'], 'false');
}
controller.press('pc', 'ArrowDown');
assert.equal(buttons[37].attrs['aria-pressed'], 'true');
const count = payloads.length;
controller.press('touch', 'Matrix37');
controller.release('pc');
assert.equal(payloads.length, count); // no duplicate make or premature break
assert.equal(buttons[37].attrs['aria-pressed'], 'true');
controller.release('touch');
assert.equal(payloads.length, count + 1);
assert.equal(buttons[37].attrs['aria-pressed'], 'false');
'''
        result = subprocess.run(
            ["node", "-e", script, str(APP), str(KEYBOARD_INPUT)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_raw_matrix_remains_available_without_verbose_key_explanations(self) -> None:
        self.assertLess(
            self.html.index('src="keyboard_input.js"'),
            self.html.index('src="app.js'),
        )
        self.assertIn('原始矩阵 M00–M63（高级）', self.html)
        self.assertIn('仅供按键排查；编号不是原机键名', self.html)
        self.assertNotIn('实体按键（已恢复映射）', self.html)
        self.assertIn('add("Matrix15", "帮助"', self.javascript)
        self.assertIn('ArrowDown: 37, PageDown: 37, Tab: 37', self.javascript)
        self.assertIn('ArrowUp: 61, PageUp: 61', self.javascript)
        self.assertNotIn('Tab: "切换"', self.javascript)
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

    def test_opcode_profile_is_opt_in_and_resumes_after_read_failure(self) -> None:
        class FakeProcess:
            @staticmethod
            def poll():
                return None

        class FakeQMP:
            def __init__(self):
                self.calls = []
                self.fail_read = False

            def execute(self, command, arguments=None):
                self.calls.append((command, arguments))
                if command == "query-status":
                    return {"running": True}
                if command == "qom-get":
                    if self.fail_read:
                        raise QMPError("profile read failed")
                    return '{"enabled":true,"executed":{"9a":3}}'
                if command in ("stop", "cont"):
                    return {}
                raise AssertionError(command)

        emulator = Emulator.__new__(Emulator)
        emulator.process = FakeProcess()
        emulator.qmp = FakeQMP()
        emulator.opcode_profile_enabled = False
        with self.assertRaises(ValueError):
            emulator.opcode_profile()
        self.assertEqual(emulator.qmp.calls, [])
        emulator.opcode_profile_enabled = True
        self.assertEqual(emulator.opcode_profile()["executed"], {"9a": 3})
        self.assertEqual([call[0] for call in emulator.qmp.calls],
                         ["query-status", "stop", "qom-get", "cont"])
        emulator.qmp.calls.clear()
        emulator.qmp.fail_read = True
        with self.assertRaises(QMPError):
            emulator.opcode_profile()
        self.assertEqual([call[0] for call in emulator.qmp.calls],
                         ["query-status", "stop", "qom-get", "cont"])

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
