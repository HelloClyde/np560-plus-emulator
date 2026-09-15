#!/usr/bin/env python3


# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_np560_runtime_code_sources as analyzer
from scripts.np560_overlay_map import OverlaySpec, QemuMapping


class RuntimeCodeSourceAnalyzerTests(unittest.TestCase):
    def test_parses_foreground_and_control_words(self) -> None:
        registers = """\
FOREGROUND_TRACE=2e:2e92/7676@0b68,2e:2e96/a6a7@0b68
CONTROL_TRACE=2e:2e92/7676>2e:2e96@0b68/0bb6
EXEC_TRACE=2e:2e96/a6a7
NPE_CONTROL_TRACE=COUNT:2 TRACE:#1/1e:fd7a>2f:c23a/wc620/sp0e02/fp0e1c,#2/2c:d38e>03:4050/wbd03/sp0e02/fp0e1c
"""
        words = analyzer.executed_words(registers)
        self.assertEqual(words[0x2E2E92][0], 0x7676)
        self.assertEqual(
            words[0x2E2E92][1], {"FOREGROUND_TRACE", "CONTROL_TRACE"}
        )
        self.assertEqual(
            words[0x2E2E96][1], {"FOREGROUND_TRACE", "EXEC_TRACE"}
        )
        self.assertEqual(words[0x1EFD7A][0], 0xC620)
        self.assertEqual(words[0x2CD38E][0], 0xBD03)
        self.assertEqual(
            words[0x2CD38E][1], {"NPE_CONTROL_TRACE"}
        )

    def test_reports_word_mismatch_before_mapping_status(self) -> None:
        spec = OverlaySpec(
            0x2E0000, 2, "TEST", analyzer.PROGRAM_BASE + 0x10, "code"
        )
        firmware = bytearray(0x20)
        firmware[0x10:0x12] = (0x1234).to_bytes(2, "little")
        findings = analyzer.diagnose(
            {0x2E0000: (0x7676, {"EXEC_TRACE"})},
            [spec],
            [QemuMapping(0x2E0000, 2, "TEST_BASE", True)],
            bytes(firmware),
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].status, "word-mismatch")
        self.assertEqual(findings[0].expected_word, 0x1234)

    def test_clean_source_mapping_is_suppressed(self) -> None:
        source = analyzer.PROGRAM_BASE + 0x10
        spec = OverlaySpec(0x2E0000, 2, "TEST", source, "code")
        firmware = bytearray(0x20)
        firmware[0x10:0x12] = (0x1234).to_bytes(2, "little")
        findings = analyzer.diagnose(
            {0x2E0000: (0x1234, {"EXEC_TRACE"})},
            [spec],
            [QemuMapping(0x2E0000, 2, "TEST_BASE", True, source)],
            bytes(firmware),
        )
        self.assertEqual(findings, [])

    def test_reports_qemu_only_source_mapping_mismatch(self) -> None:
        source = analyzer.PROGRAM_BASE + 0x10
        firmware = bytearray(0x20)
        firmware[0x10:0x12] = (0x2E00).to_bytes(2, "little")
        findings = analyzer.diagnose(
            {0x330000: (0x7676, {"EXEC_TRACE"})},
            [],
            [QemuMapping(0x330000, 8, "LEAF_BASE", True, source)],
            bytes(firmware),
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].status, "word-mismatch")
        self.assertEqual(findings[0].expected_source, source)

    def test_reports_changed_source_less_code_window(self) -> None:
        address = analyzer.PROGRAM_BASE + 0x10
        firmware = bytearray(0x20)
        firmware[0x10:0x12] = (0x58F0).to_bytes(2, "little")
        findings = analyzer.diagnose(
            {address: (0x7676, {"CONTROL_TRACE"})},
            [],
            [QemuMapping(address, 8, "WRITABLE_BASE", True)],
            bytes(firmware),
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].status, "data-backed-mismatch")
        self.assertIsNone(findings[0].mapped_source)


if __name__ == "__main__":
    unittest.main()
