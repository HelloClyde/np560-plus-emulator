from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import struct
import tempfile
import unittest
from pathlib import Path

from scripts.np560_upd import (
    HEADER_SIZE,
    UpdateFormatError,
    extract_update,
    parse_update,
    verify_program_block,
    word_swap,
)


ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = ROOT / "NP560+V3.80版系统升级程序"


def make_update(blocks: list[bytes]) -> bytes:
    if len(blocks) > 4:
        raise ValueError("too many blocks")
    blocks += [b""] * (4 - len(blocks))
    header = bytearray(HEADER_SIZE)
    header[:10] = b"NP560+V1.0"
    struct.pack_into("<4I", header, 0x24, *(len(block) for block in blocks))
    payload = b"".join(blocks)
    checksum = (sum(header[:0x20]) + sum(payload)) & 0xFFFFFFFF
    struct.pack_into("<I", header, 0x20, checksum)
    return bytes(header) + payload


class UpdateParserTests(unittest.TestCase):
    def test_parse_layout_and_maskrom(self) -> None:
        maskrom = bytearray(0x240)
        maskrom[:17] = b"MASKROM TEST V1.0"
        struct.pack_into("<III", maskrom, 0x20, 2, 11, len(maskrom))
        package = make_update([b"loader", bytes(maskrom)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.upd"
            path.write_bytes(package)
            image = parse_update(path)

        self.assertTrue(image.checksum_valid)
        self.assertEqual([block.offset for block in image.blocks], [0x40, 0x46])
        self.assertEqual(image.blocks[1].kind, "nand-image")
        self.assertEqual(image.blocks[1].maskrom.page_count, 2)
        self.assertEqual(image.blocks[1].maskrom.declared_block_size, 0x240)

    def test_reject_bad_checksum(self) -> None:
        package = bytearray(make_update([b"payload"]))
        package[-1] ^= 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.upd"
            path.write_bytes(package)
            with self.assertRaisesRegex(UpdateFormatError, "checksum mismatch"):
                parse_update(path)

    def test_word_swap(self) -> None:
        self.assertEqual(word_swap(bytes.fromhex("bd030030")), bytes.fromhex("03bd3000"))
        with self.assertRaises(UpdateFormatError):
            word_swap(b"odd")

    @unittest.skipUnless((FIRMWARE / "NP560+.upd").is_file(), "firmware is absent")
    def test_release_package(self) -> None:
        update = FIRMWARE / "NP560+.upd"
        program = FIRMWARE / "NP560.PRG"
        image = parse_update(update)

        self.assertEqual(image.size, 48_332_640)
        self.assertEqual(
            [block.size for block in image.blocks],
            [0x17C88, 0x12EE4, 0x400000, 0x29ED3B4],
        )
        self.assertEqual(
            [block.kind for block in image.blocks],
            ["burner-code", "driver-code", "program-word-image", "nand-image"],
        )
        self.assertEqual(image.blocks[0].offset, 0x40)
        self.assertEqual(image.blocks[1].offset, 0x17CC8)
        self.assertEqual(image.blocks[2].offset, 0x2ABAC)
        self.assertEqual(image.blocks[3].offset, 0x42ABAC)
        self.assertEqual(image.blocks[3].maskrom.page_count, 85_866)
        self.assertEqual(verify_program_block(update, program), 2)

        with tempfile.TemporaryDirectory() as directory:
            extracted = extract_update(update, Path(directory), slots={0, 1})
            burner = extracted[0].read_bytes()
            driver = extracted[1].read_bytes()
            self.assertEqual(len(burner), 0x17C88)
            self.assertEqual(burner[:4], bytes.fromhex("ad51dc1c"))
            self.assertEqual(len(driver), 0x12EE4)
            self.assertEqual(driver[:4], bytes.fromhex("ad532e8e"))

    @unittest.skipUnless((FIRMWARE / "NP560PRG.upd").is_file(), "firmware is absent")
    def test_program_only_package(self) -> None:
        update = FIRMWARE / "NP560PRG.upd"
        program = FIRMWARE / "NP560.PRG"
        image = parse_update(update)

        self.assertEqual([block.slot for block in image.blocks], [0, 1])
        self.assertEqual(verify_program_block(update, program), 1)


if __name__ == "__main__":
    unittest.main()
