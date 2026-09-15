import struct
import unittest

from analyze_np560_ecc_checkpoint import ECC_OFFSETS, sector_descriptor
from verify_np560_burn_payload import verify_payload


class BurnPayloadTests(unittest.TestCase):
    def fixture(self):
        data_size, oob_size = 4 * 64 * 2048, 4 * 64 * 64
        image = bytearray(b"\xff" * (64 + data_size + oob_size))
        image[:64] = bytes(64)
        image[:8] = b"NP560N1\0"
        struct.pack_into("<6I2Q2I", image, 8, 1, 64, 2048, 64, 64, 4,
                         data_size, oob_size, 0, 0)
        factory = 64 + 63 * 2048
        image[factory:factory + 8] = bytes.fromhex("feca01000300424b")
        self.oob_base = 64 + data_size
        struct.pack_into("<3H", image, self.oob_base + 127 * 64 + 58, 9, 9, 9)
        payload = bytes(range(256)) * 2 + b"end!?"
        padded = payload + b"\xff" * (-len(payload) % 512)
        self.physical = 0x20000 + 0x10000
        physical_data = bytearray(len(padded))
        physical_data[1::2] = padded[0::2]
        physical_data[0::2] = padded[1::2]
        pos = 64 + self.physical
        image[pos:pos + len(padded)] = physical_data
        for offset in (0, 512):
            page, column = divmod(self.physical + offset, 2048)
            ecc_pos = self.oob_base + page * 64 + ECC_OFFSETS[column // 512]
            image[ecc_pos:ecc_pos + 8] = sector_descriptor(physical_data[offset:offset + 512])
        return image, payload

    def test_exact_mapping_padding_and_ecc(self):
        image, payload = self.fixture()
        result = verify_payload(image, payload)
        self.assertTrue(result["passed"])
        self.assertEqual(result["checked_bytes"], 1024)
        self.assertEqual(result["expected_sha256"], result["observed_sha256"])
        self.assertEqual(result["mapping"], [{"tag": 9, "physical_block": 1}])
        self.assertFalse(result["guest_ftl_readback_verified"])

    def test_bad_payload_and_bad_ecc_are_not_accepted(self):
        image, payload = self.fixture()
        image[64 + self.physical + 11] ^= 1
        result = verify_payload(image, payload)
        self.assertFalse(result["passed"])
        self.assertEqual(result["mismatch_bytes"], 1)
        self.assertEqual(result["mismatch_ecc_sectors"], 1)
        image, payload = self.fixture()
        image[self.oob_base + (self.physical // 2048) * 64 + 22] ^= 1
        self.assertFalse(verify_payload(image, payload)["passed"])

    def test_no_fitting_to_another_block_or_lane_order(self):
        image, payload = self.fixture()
        struct.pack_into("<3H", image, self.oob_base + 191 * 64 + 58, 9, 9, 9)
        result = verify_payload(image, payload)
        self.assertFalse(result["passed"])
        self.assertEqual(result["checked_bytes"], 0)
        image, payload = self.fixture()
        image[64 + self.physical:64 + self.physical + 512] = payload[:512]
        self.assertFalse(verify_payload(image, payload)["passed"])

    def test_missing_tag_and_invalid_factory_fail(self):
        image, payload = self.fixture()
        image[self.oob_base + 127 * 64 + 58:self.oob_base + 128 * 64] = b"\xff" * 6
        self.assertFalse(verify_payload(image, payload)["passed"])
        image[64 + 63 * 2048] = 0
        with self.assertRaises(ValueError):
            verify_payload(image, payload)


if __name__ == "__main__":
    unittest.main()
