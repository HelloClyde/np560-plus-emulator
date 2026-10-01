import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_np560_nand_journals import compare


DATA, OOB, PAGES, BLOCK = 4, 2, 4, 2


def fixture(directory: Path, name: str, records: list[tuple[int, int, int, bytes]],
            *, data_size: int = DATA, oob_size: int = OOB,
            seed_first_byte: int = 0x0F
            ) -> tuple[Path, Path]:
    data = bytearray(b"\xff" * (data_size * PAGES))
    data[0] = seed_first_byte
    payload = bytes(data) + b"\xff" * (oob_size * PAGES)
    base = directory / "base.nand"
    base.write_bytes(b"NP560N1\0" + b"\0" * 56 + payload)
    header = (b"NP560J1\0" + struct.pack("<6I", 1, data_size, oob_size,
                                          PAGES, BLOCK, 0) +
              hashlib.sha256(payload).digest())
    journal = directory / name
    body = b"".join(
        struct.pack("<4sIQIIII", b"NJR1", op, sequence, page, column,
                    len(raw), 0) + raw
        for sequence, (op, page, column, raw) in enumerate(records, 1)
    )
    journal.write_bytes(header + body)
    return base, journal


class JournalCompareTests(unittest.TestCase):
    def test_erase_then_program_and_anded_program_differ(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, first = fixture(root, "first.npj", [(1, 0, 0, b"\x03")])
            _, second = fixture(root, "second.npj",
                                [(3, 0, 0, b""), (1, 0, 0, b"\xf0")])
            report = compare(base, first, second)
            self.assertEqual(report["different_pages"], 1)
            self.assertEqual(report["differences"][0]["page"], 0)
            self.assertEqual(report["differences"][0]["first_values"], [3, 240])

    def test_oob_write_crossing_page_is_compared(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, first = fixture(root, "first.npj", [(2, 0, 5, b"\x00\x01")])
            _, second = fixture(root, "second.npj", [])
            report = compare(base, first, second)
            self.assertEqual(report["selected_pages"], 2)
            self.assertEqual([item["page"] for item in report["differences"]],
                             [0, 1])

    def test_wrong_seed_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, first = fixture(root, "first.npj", [(1, 0, 0, b"\x03")])
            _, second = fixture(root, "second.npj", [])
            raw = bytearray(base.read_bytes())
            raw[-1] ^= 1
            base.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "base SHA-256"):
                compare(base, first, second)

    def test_tag_alignment_ignores_physical_block_relocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tail = struct.pack("<H", 0x0E9B) * 3
            base, first = fixture(root, "first.npj",
                                  [(1, 0, 1, b"\x07"), (2, 1, 4 + 58, tail)],
                                  oob_size=64, seed_first_byte=0xFF)
            _, second = fixture(root, "second.npj",
                                [(1, 2, 1, b"\x00"), (2, 3, 4 + 58, tail)],
                                oob_size=64, seed_first_byte=0xFF)
            report = compare(base, first, second, tag=0x0E9B)
            self.assertEqual(report["tag_alignment"], {
                "tag": 0x0E9B,
                "physical_blocks": [0, 1],
                "data_differences": [
                    {"page_in_block": 0, "column": 1, "first": 7, "second": 0}
                ],
            })


if __name__ == "__main__":
    unittest.main()
