import struct
import sys
import unittest
from pathlib import Path
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extract_np560_mobivoice_codec_candidate import FIRST_MEMBER, wise_members


class WiseMemberTests(unittest.TestCase):
    def test_crc_checked_member(self):
        original = b"decoder evidence"
        compressor = zlib.compressobj(wbits=-15)
        packed = compressor.compress(original) + compressor.flush()
        installer = b"\x00" * FIRST_MEMBER + packed + struct.pack(
            "<I", zlib.crc32(original))
        self.assertEqual(next(wise_members(installer))[2], original)

    def test_bad_crc_rejected(self):
        compressor = zlib.compressobj(wbits=-15)
        packed = compressor.compress(b"x") + compressor.flush()
        installer = b"\x00" * FIRST_MEMBER + packed + b"\x00\x00\x00\x00"
        with self.assertRaisesRegex(ValueError, "CRC mismatch"):
            next(wise_members(installer))


if __name__ == "__main__":
    unittest.main()
