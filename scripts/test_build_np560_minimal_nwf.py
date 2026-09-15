#!/usr/bin/env python3

from __future__ import annotations

import unittest

from scripts import build_np560_minimal_nwf as nwf


class MinimalNwfTests(unittest.TestCase):
    def test_signed24_round_trip_and_boundaries(self) -> None:
        for value in (-(1 << 23), -1, 0, 1, 0xFE00, (1 << 23) - 1):
            self.assertEqual(nwf.decode_signed24(nwf.encode_signed24(value)), value)
        with self.assertRaises(ValueError):
            nwf.encode_signed24(1 << 23)

    def test_protected_header_round_trip(self) -> None:
        decoded = nwf.decoded_candidate_header()
        encoded = nwf.encode_header(decoded)
        self.assertNotEqual(encoded[0x10:], decoded[0x10:])
        self.assertEqual(nwf.decode_header(encoded), decoded)
        self.assertEqual(len(encoded[0x10:]), 0x1F0)

    def test_candidate_passes_offline_contract(self) -> None:
        image = nwf.build_candidate()
        report = nwf.inspect_candidate(image)
        self.assertTrue(report["valid_offline_candidate"], report["errors"])
        self.assertFalse(report["original_factory_nwf"])
        self.assertEqual(report["file_bytes"], 0x2000)
        self.assertEqual(report["authorization_offset"], -1)
        self.assertEqual(report["record_position"], 0x1F00)
        self.assertEqual(report["application_code"], 0x1203)
        self.assertEqual(report["menu_page"], 0)
        self.assertEqual(report["menu_flags"], 0)

    def test_legacy_full_window_candidate_remains_inspectable(self) -> None:
        image = nwf.build_candidate(
            record_offset=nwf.LEGACY_RECORD_OFFSET,
            record_storage_size=nwf.LEGACY_RECORD_STORAGE_SIZE,
        )
        report = nwf.inspect_candidate(image)
        self.assertTrue(report["valid_offline_candidate"], report["errors"])
        self.assertEqual(report["file_bytes"], 0x10000)

    def test_corrupt_record_is_rejected(self) -> None:
        image = bytearray(nwf.build_candidate())
        image[nwf.RECORD_OFFSET:nwf.RECORD_OFFSET + 2] = b"\x00\x00"
        report = nwf.inspect_candidate(bytes(image))
        self.assertFalse(report["valid_offline_candidate"])
        self.assertIn("application code", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
