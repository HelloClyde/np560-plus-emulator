from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import hashlib
import unittest

from scripts import patch_np560_rom01_modal_callback_closure as patch


class ModalCallbackClosurePatchTests(unittest.TestCase):
    def test_image_render_copy_splits_at_32k_boundary(self) -> None:
        self.assertEqual(
            list(patch.split_copy_ranges(0x277E84, 0x447E84, 0x0344)),
            [
                (0x277E84, 0x447E84, 0x017C),
                (0x278000, 0x448000, 0x01C8),
            ],
        )

    def test_installer_has_one_copy_loop_per_page_chunk(self) -> None:
        chunks = sum(
            len(list(patch.split_copy_ranges(destination, source, length)))
            for destination, source, length, _name in patch.OVERLAYS
        )
        chunks += sum(
            len(list(patch.split_copy_ranges(
                destination, source, len(payload)
            )))
            for destination, source, payload, _name in patch.RAW_OVERLAYS
        )
        words = patch.modal_installer_words()
        self.assertEqual(chunks, 28)
        self.assertGreater(len(words), chunks * 21 + 1)
        self.assertEqual(words[-1], patch.RETS)

    def test_copy_loop_restores_data_pages(self) -> None:
        words = patch.copy_code_words(0x2B6CE6, 0x486CE6, 0x022A)
        self.assertEqual(words[:10], [
            0x6810, 0x56, 0x6811, 0x90,
            0x68F1, 0x6CE6, 0x68F3, 0xECE6,
            0x68F4, 0x022A,
        ])
        self.assertEqual(words[-4:], [0x6810, 0x0000, 0x6811, 0x0001])

    def test_embedded_leaf_restores_ds0(self) -> None:
        destination, _source, payload, _name = patch.EMBEDDED_OVERLAYS[0]
        words = patch.embedded_write_words(destination, payload)
        self.assertEqual(words[:2], [0x6810, destination >> 15])
        self.assertEqual(words[-2:], [0x6810, 0x0000])

    def test_operation_action_mode_predicate_is_exact_embedded_payload(
        self,
    ) -> None:
        destination, source, payload, _name = next(
            item for item in patch.EMBEDDED_OVERLAYS
            if item[3] == "operation_action_mode_predicate"
        )
        write = patch.embedded_write_words(destination, payload)
        installer = patch.modal_installer_words()

        self.assertEqual((destination, source, len(payload)),
                         (0x302966, 0x4D2966, 0x0112))
        self.assertEqual(payload[:8], bytes.fromhex("05 2e f1 58 0b 78 06 00"))
        self.assertEqual(payload[-8:],
                         bytes.fromhex("01 48 1f 38 00 2f 20 c6"))
        self.assertEqual(
            hashlib.sha256(payload).hexdigest(),
            "90fa4f93d78d136425d780ede43be2719201cd0a4590f04d8175027ab7474aa2",
        )
        self.assertIn(
            write,
            [installer[index:index + len(write)]
             for index in range(len(installer) - len(write) + 1)],
        )
        self.assertFalse(any(name == "operation_action_mode_predicate"
                             for *_range, name in patch.OVERLAYS))


if __name__ == "__main__":
    unittest.main()
