#!/usr/bin/env python3

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


if __name__ == "__main__":
    unittest.main()
