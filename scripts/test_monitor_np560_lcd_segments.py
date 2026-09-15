#!/usr/bin/env python3
"""Unit tests for the read-only NP560 LCD annunciator monitor."""

from __future__ import annotations

import unittest

from monitor_np560_lcd_segments import (
    PLANE_BYTES, STATUS_BYTES, StatusPlanes, bit_delta,
)


class LCDSegmentMonitorTests(unittest.TestCase):
    def test_two_planes_use_firmware_little_endian_bit_order(self) -> None:
        payload = bytearray(STATUS_BYTES)
        payload[0] = 0x81
        payload[PLANE_BYTES + 16] = 0x26
        status = StatusPlanes(bytes(payload))
        self.assertEqual(status.bits[0], (0, 7))
        self.assertEqual(status.bits[1], (129, 130, 133))

    def test_delta_separates_enabled_and_disabled_electrodes(self) -> None:
        self.assertEqual(bit_delta((1, 3, 7), (3, 4, 7)), ((4,), (1,)))


if __name__ == "__main__":
    unittest.main()
