#!/usr/bin/env python3
"""Tests for NPE fixed-record extraction used by the codec probe."""

from __future__ import annotations

import unittest

try:
    from probe_np560_npe_speex import framed_section
    from test_analyse_np560_npe import sample_blob
except ModuleNotFoundError:
    from .probe_np560_npe_speex import framed_section
    from .test_analyse_np560_npe import sample_blob


class SpeexProbeStructureTests(unittest.TestCase):
    def test_extracts_21_byte_records_and_pad(self) -> None:
        payload = b"\x20\x0d\x00\x02" + b"A" * 21 + b"B" * 21 + b"\0"
        blob = sample_blob(second_payload=payload)
        count, records, padding = framed_section(blob, 1)
        self.assertEqual(count, 2)
        self.assertEqual(records, [b"A" * 21, b"B" * 21])
        self.assertEqual(padding, b"\0")

    def test_rejects_nonframed_section(self) -> None:
        with self.assertRaisesRegex(ValueError, "20 0D"):
            framed_section(sample_blob(second_payload=b"not framed"), 1)


if __name__ == "__main__":
    unittest.main()
