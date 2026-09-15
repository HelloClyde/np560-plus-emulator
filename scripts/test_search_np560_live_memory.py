#!/usr/bin/env python3
"""Unit tests for exact live-memory search helpers."""

from __future__ import annotations

import unittest

try:
    from search_np560_live_memory import find_offsets
except ModuleNotFoundError:
    from .search_np560_live_memory import find_offsets


class LiveMemorySearchTests(unittest.TestCase):
    def test_overlapping_hits(self) -> None:
        self.assertEqual(find_offsets(b"AAAA", b"AA"), [0, 1, 2])

    def test_absent_and_exact_hits(self) -> None:
        self.assertEqual(find_offsets(b"0123450123", b"0123"), [0, 6])
        self.assertEqual(find_offsets(b"0123", b"xx"), [])


if __name__ == "__main__":
    unittest.main()
