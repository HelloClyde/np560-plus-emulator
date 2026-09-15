from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest

try:
    from scripts import patch_np560_resident_bad_block_helper as patch
except ModuleNotFoundError:
    import patch_np560_resident_bad_block_helper as patch


class ResidentBadBlockHelperTest(unittest.TestCase):
    def make_images(self) -> tuple[bytearray, bytearray, bytes]:
        baseline = bytearray(max(patch.CALL_SITE, patch.RESIDENT_HELPER) + 0x500)
        baseline[patch.RESIDENT_HELPER:patch.RESIDENT_HELPER + patch.HELPER_SIZE] = (
            patch.RESERVED_WORD * (patch.HELPER_SIZE // 2)
        )
        baseline[patch.CALL_SITE:patch.CALL_SITE + 4] = patch.words_to_bytes(
            patch.ORIGINAL_CALL
        )
        source = patch.SOURCE_HELPER - patch.PROGRAM_BASE
        program = bytearray(source + patch.HELPER_SIZE)
        helper = bytearray(patch.HELPER_SIZE)
        helper[:2] = patch.words_to_bytes((0x2E0C,))
        helper[0x10:0x14] = patch.words_to_bytes((
            0xAC00, (patch.SOURCE_HELPER & 0xFFFF) + 0x20,
        ))
        helper[-4:] = patch.words_to_bytes((0x2F00, 0xC620))
        program[source:source + patch.HELPER_SIZE] = helper
        return baseline, program, bytes(helper)

    def test_installs_exact_helper_and_retargets_caller(self) -> None:
        baseline, program, helper = self.make_images()
        output, metadata = patch.patch_image(bytes(baseline), bytes(program))
        installed = output[
            patch.RESIDENT_HELPER:patch.RESIDENT_HELPER + patch.HELPER_SIZE
        ]
        expected, count = patch.relocate_local_jumps(helper)
        self.assertEqual(installed, expected)
        self.assertEqual(count, 1)
        self.assertEqual(
            installed[0x12:0x14],
            ((patch.RESIDENT_HELPER & 0xFFFF) + 0x20).to_bytes(2, "little"),
        )
        self.assertEqual(
            output[patch.CALL_SITE:patch.CALL_SITE + 4],
            patch.words_to_bytes(patch.PATCHED_CALL),
        )
        self.assertIn("no host HLE", metadata["execution_model"])

    def test_rejects_changed_call_site(self) -> None:
        baseline, program, _ = self.make_images()
        baseline[patch.CALL_SITE] ^= 1
        with self.assertRaisesRegex(ValueError, "not the expected"):
            patch.patch_image(bytes(baseline), bytes(program))


if __name__ == "__main__":
    unittest.main()
