#!/usr/bin/env python3
"""Regression tests for the NP560+ ST7529 visible-row contract."""

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest

from test_np560_system_boot import require_bottom_up_lcd_rows


WIDTH = 240
HEIGHT = 120


def packed_framebuffer(row_counts: list[int]) -> bytes:
    """Encode per-row foreground counts as the guest's packed 4-bpp page."""
    data = bytearray(WIDTH * HEIGHT // 2)
    for y, count in enumerate(row_counts):
        for x in range(count):
            index = y * (WIDTH // 2) + x // 2
            data[index] |= 0x10 if x % 2 == 0 else 0x01
    return bytes(data)


def lcd_frame(row_counts: list[int]) -> bytes:
    """Encode per-row foreground counts as the Web/QMP 5-bit LCD frame."""
    data = bytearray(WIDTH * HEIGHT)
    for y, count in enumerate(row_counts):
        start = y * WIDTH
        data[start:start + count] = b"\x1f" * count
    return bytes(data)


class NP560LCDRowMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        # Unique counts make every row distinguishable without OCR or glyph
        # assumptions.  Keep them below half the panel width so zero remains
        # the unambiguous background selected by the production checker.
        self.guest_counts = list(range(1, HEIGHT + 1))
        self.framebuffer = packed_framebuffer(self.guest_counts)

    def test_global_bottom_up_mapping_is_accepted(self) -> None:
        require_bottom_up_lcd_rows(
            lcd_frame(self.guest_counts[::-1]), self.framebuffer
        )

    def test_old_upper_half_mirror_is_rejected(self) -> None:
        visible = self.guest_counts[::-1]
        visible[:HEIGHT // 2] = visible[:HEIGHT // 2][::-1]
        with self.assertRaisesRegex(
                AssertionError, "visible rows do not match"):
            require_bottom_up_lcd_rows(lcd_frame(visible), self.framebuffer)

    def test_top_down_mapping_is_rejected(self) -> None:
        with self.assertRaisesRegex(
                AssertionError, "visible rows do not match"):
            require_bottom_up_lcd_rows(
                lcd_frame(self.guest_counts), self.framebuffer
            )


if __name__ == "__main__":
    unittest.main()
