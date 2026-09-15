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
import watch_np560_code_sources as watcher


class CodeSourceWatcherTests(unittest.TestCase):
    def finding(self, status: str) -> analyzer.Finding:
        return analyzer.Finding(
            0x300000,
            0x7676,
            0x2E00,
            "TEST",
            0x4D0000,
            None,
            ("EXEC_TRACE",),
            status,
        )

    def test_default_ignores_byte_identical_data_backing(self) -> None:
        data_backed = self.finding("data-backed")
        mismatch = self.finding("word-mismatch")
        self.assertEqual(
            watcher.actionable_findings([data_backed, mismatch], False, {}),
            [mismatch],
        )

    def test_diagnostic_mode_retains_data_backing(self) -> None:
        findings = [self.finding("data-backed")]
        self.assertEqual(
            watcher.actionable_findings(findings, True, {}), findings
        )

    def test_accepts_final_guest_installer_word(self) -> None:
        mismatch = self.finding("word-mismatch")
        self.assertEqual(
            watcher.actionable_findings(
                [mismatch], False, {mismatch.address: mismatch.actual_word}
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
