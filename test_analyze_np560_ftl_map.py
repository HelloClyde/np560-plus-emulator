#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import unittest


MODULE_PATH = Path(__file__).with_name("analyze_np560_ftl_map.py")
SPEC = importlib.util.spec_from_file_location("analyze_np560_ftl_map", MODULE_PATH)
assert SPEC and SPEC.loader
ftl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ftl)


def checkpoint(data_blocks: list[bytes], oob_blocks: list[bytes]) -> bytes:
    page_data = 16
    page_oob = 64
    pages_per_block = 2
    blocks = len(data_blocks)
    data = b"".join(data_blocks)
    oob = b"".join(oob_blocks)
    header = bytearray(64)
    header[:8] = ftl.MAGIC
    struct.pack_into(
        "<6I2Q2I", header, 8,
        1, 64, page_data, page_oob, pages_per_block, blocks,
        len(data), len(oob), 0, 0,
    )
    return bytes(header) + data + oob


def oob_block(tag: int) -> bytes:
    first = bytes([0xFF]) * 64
    final = bytearray([0xFF]) * 64
    final[58:64] = struct.pack("<3H", tag, tag, tag)
    return first + bytes(final)


class FtlMapTests(unittest.TestCase):
    def test_reports_tags_and_correlates_unique_pages(self) -> None:
        pages = [bytes([value]) * 16 for value in range(1, 7)]
        logical = b"".join(pages)
        image = checkpoint(
            [pages[2] + pages[3], pages[4] + pages[5]],
            [oob_block(0x1234), oob_block(0x1238)],
        )
        report = ftl.analyse(image, logical)
        self.assertEqual(report["tagged_blocks"], 2)
        self.assertEqual(report["duplicate_tags"], {})
        self.assertEqual(report["logical_image"]["correlated_blocks"], 2)
        first = report["entries"][0]["logical_image_correlation"]
        self.assertEqual(first["inferred_source_base"], 32)
        self.assertEqual(first["exact_matched_pages"], [0, 1])
        relation = report["tag_source_relation"]
        self.assertTrue(relation["exact_affine_relation"])
        self.assertEqual(relation["source_bytes_per_tag"], 8)
        self.assertEqual(
            relation["missing_tags"], list(range(0x1235, 0x1238))
        )

    def test_reports_duplicate_and_invalid_tails(self) -> None:
        data = bytes(32)
        bad = bytearray(oob_block(0x1111))
        bad[-6:] = struct.pack("<3H", 1, 2, 3)
        image = checkpoint(
            [data, data, data],
            [oob_block(0x2222), oob_block(0x2222), bytes(bad)],
        )
        report = ftl.analyse(image)
        self.assertEqual(report["duplicate_tags"], {"0x2222": [0, 1]})
        self.assertEqual(len(report["invalid_triplicated_tails"]), 1)

    def test_rejects_non_affine_correlations(self) -> None:
        entries = [
            {
                "tail_tag": tag,
                "physical_block": index,
                "logical_image_correlation": {"inferred_source_base": source},
            }
            for index, (tag, source) in enumerate((
                (0x1000, 0x0000),
                (0x1001, 0x2000),
                (0x1002, 0x5000),
            ))
        ]
        relation = ftl.infer_tag_source_relation(entries)
        self.assertIsNotNone(relation)
        self.assertFalse(relation["exact_affine_relation"])
        self.assertIsNone(relation["source_bytes_per_tag"])


if __name__ == "__main__":
    unittest.main()
