from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import burn_np560_stream as burn
from np560_usb_transport import (
    USB_RECEIVE_STORE_PC, USB_RECEIVE_STORE_WORD, usb_data_to_physical_ram,
)


class FakeBurner:
    def __init__(self, ack):
        self.ack = ack
        self.data = {}
        self.qmp = self
        self.process = self
        self.staged = b""

    def execute(self, command, arguments=None):
        if command == "cont":
            self.data[burn.STREAM_FLAG] = struct.pack("<HH", 0, self.ack)
            self.data[burn.STREAM_PROBE] = self.staged[:2]
            self.data[burn.COMMAND_RESULT] = bytes(2)

    def load_data(self, address, path):
        assert address == burn.SOURCE
        self.staged = path.read_bytes()

    def write_data(self, address, data):
        self.data[address] = data

    def read(self, address, size):
        if burn.SOURCE <= address < burn.SOURCE + len(self.staged):
            start = address - burn.SOURCE
            return self.staged[start:start + size]
        return self.data[address][:size]

    def poll(self):
        return None


class UsbTransportTests(unittest.TestCase):
    def test_loader_store_is_exact_source_word(self):
        path = (Path(__file__).resolve().parents[1]
                / "NP560+V3.80版系统升级程序/USB_Loader_Noah.bin")
        if not path.exists():
            self.skipTest("original USB loader unavailable")
        data = path.read_bytes()
        offset = USB_RECEIVE_STORE_PC - 0x1000
        self.assertEqual(int.from_bytes(data[offset:offset + 2], "big"),
                         USB_RECEIVE_STORE_WORD)
        self.assertEqual(data[offset - 4:offset], bytes.fromhex("88f0f230"))

    def test_all_byte_values_and_bounds(self):
        data = bytes(range(256)) * 2
        encoded = usb_data_to_physical_ram(data)
        self.assertEqual(encoded[0::2], data[1::2])
        self.assertEqual(encoded[1::2], data[0::2])
        self.assertEqual(bytes(encoded[i ^ 1] for i in range(len(data))), data)
        for invalid in (b"", b"a", b"abc"):
            with self.assertRaises(ValueError):
                usb_data_to_physical_ram(invalid)

    def test_command13_uses_encoded_staging_and_numeric_probe(self):
        # Includes odd final payload size, exact page and the official max chunk.
        with tempfile.TemporaryDirectory() as name:
            for size in (1, 511, 512, 513, burn.OFFICIAL_CHUNK_SIZE):
                with self.subTest(size=size):
                    payload = bytes(i % 256 for i in range(size))
                    padded = payload + b"\xff" * (-size % burn.PAGE_SIZE)
                    fake = FakeBurner(0x1234)
                    with patch.object(burn, "memory", side_effect=lambda _e, a, s: fake.read(a, s)):
                        pages = burn.send_chunk(fake, Path(name) / "chunk.bin", payload,
                                                0x880, fake.ack, 1.0)
                    self.assertEqual(pages, len(padded) // 512)
                    self.assertEqual(fake.staged, usb_data_to_physical_ram(padded))
                    self.assertNotEqual(fake.staged, padded)
                    self.assertEqual(fake.data[burn.TARGET_PAGE], struct.pack("<HH", 0, 0x880))
                    self.assertEqual(fake.data[burn.CHUNK_LENGTH],
                                     struct.pack("<HH", 0, pages))
                    self.assertEqual(fake.data[burn.SOURCE_POINTER],
                                     struct.pack("<HH", burn.SOURCE >> 16, burn.SOURCE & 0xFFFF))

    def test_command13_rejects_invalid_length_before_transport(self):
        for invalid in (b"", bytes(burn.OFFICIAL_CHUNK_SIZE + 1)):
            with self.assertRaises(ValueError):
                burn.send_chunk(None, Path("unused.bin"), invalid, 0x880, 1, 1.0)

    def test_command13_rejects_corrupted_staging(self):
        with tempfile.TemporaryDirectory() as name:
            for offset in (0, 511):
                with self.subTest(offset=offset):
                    fake = FakeBurner(1)
                    original_load = fake.load_data

                    def corrupt_load(address, path):
                        original_load(address, path)
                        data = bytearray(fake.staged)
                        data[offset] ^= 1
                        fake.staged = bytes(data)

                    fake.load_data = corrupt_load
                    with patch.object(burn, "memory", side_effect=lambda _e, a, s: fake.read(a, s)):
                        with self.assertRaisesRegex(RuntimeError, "did not reach.*staging RAM"):
                            burn.send_chunk(fake, Path(name) / "chunk.bin",
                                            bytes(range(256)) * 2, 0x880, 1, 1.0)
                    self.assertNotIn(burn.STREAM_FLAG, fake.data)


if __name__ == "__main__":
    unittest.main()
