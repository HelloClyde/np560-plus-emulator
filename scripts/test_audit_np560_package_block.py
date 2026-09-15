from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audit_np560_package_block import (
    BLOCK, PAGE, HEADER, OOB, BLOCK_PAGES, audit_and_copy, classify_page,
)
from analyze_np560_ecc_checkpoint import ECC_OFFSETS, sector_descriptor
from np560_upd import word_swap


class PackageBlockTests(unittest.TestCase):
    def test_classification(self):
        raw = bytes(range(256)) * 8
        self.assertEqual(classify_page(raw, raw), "raw-package")
        self.assertEqual(classify_page(word_swap(raw), raw), "lane-encoded")
        self.assertEqual(classify_page(bytes(PAGE), bytes(PAGE)), "both")
        with self.assertRaisesRegex(ValueError, "differs"):
            classify_page(bytes(PAGE), raw)
        with self.assertRaisesRegex(ValueError, "size"):
            classify_page(b"short", raw)

    def test_diagnostic_copy_and_guards(self):
        raw = bytes(range(256)) * (BLOCK // 256)
        data = bytearray(raw)
        data[PAGE:PAGE * 2] = word_swap(raw[PAGE:PAGE * 2])
        # Second unrelated block and non-ECC OOB must survive byte-for-byte.
        data.extend(b"\x91" * BLOCK)
        oob = bytearray(b"\x77" * (2 * BLOCK_PAGES * OOB))
        for page in range(BLOCK_PAGES):
            for sector, offset in enumerate(ECC_OFFSETS):
                a = page * OOB + offset
                oob[a:a + 8] = sector_descriptor(data, page * PAGE + sector * 512)
        header = bytearray(HEADER)
        header[:8] = b"NP560N1\0"
        struct.pack_into("<6I2Q2I", header, 8, 1, HEADER, PAGE, OOB,
                         BLOCK_PAGES, 2, len(data), len(oob), 123, 456)
        original = bytes(header + data + oob)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source, target = root / "source.nand", root / "copy.nand"
            source.write_bytes(original)
            with patch("audit_np560_package_block.package_block", return_value=(raw, {})):
                report = audit_and_copy(source, root / "package.upd", 0x120000, 0)
                self.assertEqual(report["changed_pages"], 63)
                self.assertFalse(target.exists())
                audit_and_copy(source, root / "package.upd", 0x120000, 0, target)
                result = target.read_bytes()
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(result[48:56], bytes(8))
                self.assertEqual(result[HEADER:HEADER + BLOCK], word_swap(raw))
                self.assertEqual(result[HEADER + BLOCK:HEADER + len(data)], data[BLOCK:])
                for page in range(BLOCK_PAGES):
                    start = HEADER + len(data) + page * OOB
                    self.assertEqual(result[start:start + 22], oob[page * OOB:page * OOB + 22])
                    for sector, offset in enumerate(ECC_OFFSETS):
                        self.assertEqual(result[start + offset:start + offset + 8],
                                         sector_descriptor(word_swap(raw), page * PAGE + sector * 512))
                for destination in (source, target):
                    with self.assertRaisesRegex(ValueError, "new file"):
                        audit_and_copy(source, root / "package.upd", 0x120000, 0, destination)
                with self.assertRaisesRegex(ValueError, "outside"):
                    audit_and_copy(source, root / "package.upd", 0x120000, 2)
                no_ecc = bytearray(original)
                no_ecc[HEADER + len(data) + ECC_OFFSETS[0] + 6] ^= 1
                source.write_bytes(no_ecc)
                refused = root / "refused.nand"
                with self.assertRaisesRegex(ValueError, "ECC"):
                    audit_and_copy(source, root / "package.upd", 0x120000, 0, refused)
                self.assertFalse(refused.exists())
                # A changed byte must fail preflight, leaving no new output.
                damaged = bytearray(original)
                damaged[HEADER] ^= 0x80
                source.write_bytes(damaged)
                with self.assertRaisesRegex(ValueError, "differs"):
                    audit_and_copy(source, root / "package.upd", 0x120000, 0, refused)
                self.assertFalse(refused.exists())


if __name__ == "__main__":
    unittest.main()
