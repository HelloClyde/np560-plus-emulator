#!/usr/bin/env python3

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = (Path(__file__).resolve().parent.parent / 'patch_np560_words.py')
SPEC = importlib.util.spec_from_file_location("patch_np560_words", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PatchWordsTests(unittest.TestCase):
    def test_verified_patch(self) -> None:
        payload = bytes.fromhex("01 48 34 12")
        patch = MODULE.WordPatch(MODULE.PROGRAM_BASE, 0x4801, 0x4800)
        self.assertEqual(
            MODULE.apply_patches(payload, [patch]), bytes.fromhex("00 48 34 12")
        )

    def test_mismatch_is_rejected(self) -> None:
        patch = MODULE.WordPatch(MODULE.PROGRAM_BASE, 0x4802, 0x4800)
        with self.assertRaisesRegex(ValueError, "word mismatch"):
            MODULE.apply_patches(bytes.fromhex("01 48"), [patch])

    def test_duplicate_is_rejected(self) -> None:
        patch = MODULE.WordPatch(MODULE.PROGRAM_BASE, 0x4801, 0x4800)
        with self.assertRaisesRegex(ValueError, "duplicate patch"):
            MODULE.apply_patches(bytes.fromhex("01 48"), [patch, patch])


if __name__ == "__main__":
    unittest.main()
