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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_np560_overlay_mappings as audit


class OverlayAuditTests(unittest.TestCase):
    def test_matches_builder_destination_to_listed_qemu_base(self) -> None:
        builder = """\
FILE_OVERLAY_DESTINATION = 0x5D1234
FILE_OVERLAY_SOURCE = 0x4C1234
FILE_OVERLAY_SIZE = 0x80
LOW_OVERLAY_DESTINATION = 0x301234
"""
        qemu = """\
#define NP560_FILE_OVERLAY_BASE 0x005d1234u
#define NP560_FILE_OVERLAY_SOURCE 0x004c1234u
static const NP560ProgramOverlay np560_late_overlays[] = {
    { NP560_FILE_OVERLAY_BASE, 0x80u, "data", "code",
      NP560_FILE_OVERLAY_SOURCE },
};
"""
        self.assertEqual(audit.builder_overlays(builder, 0x5C0000), [
            audit.Overlay("FILE_OVERLAY_DESTINATION", 0x5D1234,
                          0x4C1234, 0x80)
        ])
        self.assertEqual(audit.qemu_late_overlay_bases(qemu), {0x5D1234})
        self.assertEqual(
            audit.qemu_late_overlay_sources(qemu), {0x5D1234: 0x4C1234}
        )

    def test_reports_data_backed_high_bank_mapping(self) -> None:
        qemu = """\
#define NP560_FILE_OVERLAY_BASE 0x005d1234u
static const NP560ProgramOverlay np560_late_overlays[] = {
    { NP560_FILE_OVERLAY_BASE, 0x80u, "data", "code" },
};
"""
        self.assertEqual(
            audit.qemu_late_overlay_sources(qemu), {0x5D1234: None}
        )

    def test_defined_but_unlisted_base_is_not_mapped(self) -> None:
        qemu = """\
#define NP560_FILE_OVERLAY_BASE 0x005d1234u
static const NP560ProgramOverlay np560_late_overlays[] = {
    { NP560_OTHER_OVERLAY_BASE, 4u, "data", "code" },
};
"""
        self.assertEqual(audit.qemu_late_overlay_bases(qemu), set())

    def test_real_state4e_harvard_windows_are_exact(self) -> None:
        root = Path(__file__).resolve().parents[2]
        qemu = (root / "qemu-dmcu" / "hw" / "dmcu" / "np560.c").read_text(
            encoding="utf-8"
        )
        mappings = {
            (mapping.base, mapping.size): mapping.source
            for mapping in audit.parse_qemu_mappings(qemu)
            if mapping.code
        }
        self.assertEqual(mappings[(0x3344AE, 0x001C)], None)
        self.assertEqual(mappings[(0x0D2F30, 0x2E6C)], None)
        self.assertNotIn((0x336BE2, 0x0008), mappings)
        self.assertEqual(mappings[(0x5F6BE2, 0x0008)], 0x506BE2)
        self.assertEqual(mappings[(0x33197A, 0x002E)], 0x50197A)
        self.assertEqual(mappings[(0x224C58, 0x0506)], None)
        self.assertEqual(mappings[(0x22D700, 0x04E0)], None)
        self.assertEqual(mappings[(0x330070, 0x0070)], None)
        self.assertEqual(mappings[(0x23DA24, 0x0902)], None)
        self.assertEqual(mappings[(0x3338D6, 0x00CC)], None)
        self.assertIn(
            "NP560_APPLICATION_OPERATION_GRID_REPOSITION_CODE_BASE",
            qemu,
        )
        self.assertIn(
            "NP560_APPLICATION_OPERATION_SCROLL_RENDERER_CODE_BASE",
            qemu,
        )

    def test_resource_persistence_writer_windows_keep_writable_data_views(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[2]
        qemu = (root / "qemu-dmcu" / "hw" / "dmcu" / "np560.c").read_text(
            encoding="utf-8"
        )
        mappings = audit.parse_qemu_mappings(qemu)
        for base, size in (
            (0x32EBAE, 0x0040),
            (0x330D7E, 0x0032),
            (0x280F92, 0x0312),
        ):
            mapping = min(
                (
                    item for item in mappings
                    if item.base <= base and item.base + item.size >= base + size
                ),
                key=lambda item: item.size,
            )
            self.assertFalse(mapping.code)
        existing = next(
            item for item in mappings
            if item.code and item.base == 0x330D4C and item.size == 0x0032
        )
        self.assertEqual(existing.source, 0x500D4C)

    def test_adjacent_overlay_unions_preserve_every_original_window(self) -> None:
        root = Path(__file__).resolve().parents[2]
        qemu = (root / "qemu-dmcu" / "hw" / "dmcu" / "np560.c").read_text(
            encoding="utf-8"
        )
        mappings = [
            mapping for mapping in audit.parse_qemu_mappings(qemu)
            if mapping.code
        ]
        for base, size in (
            (0x270000, 0x0362), (0x270362, 0x0362),
            (0x284CEA, 0x0306), (0x284FF0, 0x0306),
            (0x2913DC, 0x02D4), (0x2916B0, 0x02D4),
            (0x31F162, 0x0090), (0x31F1F2, 0x0090),
            (0x32AF98, 0x0056), (0x32AFEE, 0x0056),
            (0x32B922, 0x0052), (0x32B974, 0x0052),
            (0x32E560, 0x0042), (0x32E5A2, 0x0042),
            (0x334D14, 0x0016), (0x334D2A, 0x0016),
        ):
            self.assertTrue(
                any(
                    item.base <= base and
                    item.base + item.size >= base + size
                    for item in mappings
                ),
                f"missing union coverage for {base:06X}+{size:04X}",
            )


if __name__ == "__main__":
    unittest.main()
