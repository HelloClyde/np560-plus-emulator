import socket
import hashlib
import struct
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from serve_np560_npe_codec import OwnedMode5Codec, read_exact, serve_connection


class FakeDecoder:
    frames = []

    def init(self, mode):
        return 0x1000, (mode * 3 + 6) * 8

    def decode(self, frame, context):
        self.frames.append((frame, context))
        return 160, struct.pack("<160h", *([len(self.frames)] * 160))


class CodecTransportTests(unittest.TestCase):
    def setUp(self):
        FakeDecoder.frames = []
        self.trace = []
        self.client, server = socket.socketpair()
        self.worker = threading.Thread(target=serve_connection,
                                       args=(server, FakeDecoder,
                                             lambda mode, frame: self.trace.append(
                                                 (mode, frame))), daemon=True)
        self.worker.start()
        self.server = server

    def tearDown(self):
        self.client.close()
        self.worker.join(timeout=2)
        self.server.close()
        self.assertFalse(self.worker.is_alive())

    def test_mode_five_and_successive_frames(self):
        self.client.sendall(b"I\x05")
        self.assertEqual(read_exact(self.client, 3), b"K\xa8\x00")
        for byte in (0x31, 0x72):
            self.client.sendall(b"D" + struct.pack("<H", 21) + bytes((byte,)) * 21)
            packet = read_exact(self.client, 323)
            self.assertEqual(packet[:3], b"P\xa0\x00")
        self.assertEqual([frame[0][0] for frame in FakeDecoder.frames], [0x31, 0x72])
        self.assertEqual([frame[1] for frame in FakeDecoder.frames], [0x1000, 0x1000])
        self.assertEqual(self.trace, [(5, b"\x31" * 21), (5, b"\x72" * 21)])

    def test_reset_rejects_decode_until_new_init(self):
        self.client.sendall(b"I\x05")
        read_exact(self.client, 3)
        self.client.sendall(b"R")
        self.assertEqual(read_exact(self.client, 1), b"K")
        self.client.sendall(b"D" + struct.pack("<H", 21) + bytes(21))
        self.assertEqual(read_exact(self.client, 1), b"E")
        length = struct.unpack("<H", read_exact(self.client, 2))[0]
        self.assertIn(b"not initialized", read_exact(self.client, length))

    def test_invalid_mode_fails_without_decoding(self):
        self.client.sendall(b"I\x00")
        self.assertEqual(read_exact(self.client, 1), b"E")
        length = struct.unpack("<H", read_exact(self.client, 2))[0]
        self.assertIn(b"1..10", read_exact(self.client, length))
        self.assertEqual(FakeDecoder.frames, [])


class OwnedMode5TransportTests(unittest.TestCase):
    def test_tianjiang_frames_and_decoder_reset_over_socket(self):
        first = bytes.fromhex("488e2b000e1d3579d9a81be12ccb06057dd54c76ec")
        second = bytes.fromhex("3ad5b9064c5c46f98782d5cbe08085ec4ae700560f")
        expected = (
            "7d68146ede3a8706cb01914eecad402abb653c7dbbd8681b0552b7d8d1c34a4f",
            "01e8929f4045949349eb429b3e8af6a807b28c096c39b4d324d2522363782179",
        )
        client, server = socket.socketpair()
        worker = threading.Thread(target=serve_connection,
                                  args=(server, OwnedMode5Codec), daemon=True)
        worker.start()
        try:
            client.sendall(b"I\x05")
            self.assertEqual(read_exact(client, 3), b"K\xa8\x00")
            for frame, digest in zip((first, second), expected):
                client.sendall(b"D" + struct.pack("<H", 21) + frame)
                packet = read_exact(client, 323)
                self.assertEqual(packet[:3], b"P\xa0\x00")
                self.assertEqual(hashlib.sha256(packet[3:]).hexdigest(), digest)
            client.sendall(b"R")
            self.assertEqual(read_exact(client, 1), b"K")
            client.sendall(b"I\x05")
            self.assertEqual(read_exact(client, 3), b"K\xa8\x00")
            client.sendall(b"D" + struct.pack("<H", 21) + first)
            self.assertEqual(hashlib.sha256(read_exact(client, 323)[3:]).hexdigest(),
                             expected[0])
        finally:
            client.close()
            worker.join(timeout=2)
            server.close()
            self.assertFalse(worker.is_alive())

    def test_owned_backend_explicitly_rejects_other_mode(self):
        with self.assertRaisesRegex(ValueError, "mode 5 only"):
            OwnedMode5Codec().init(4)


if __name__ == "__main__":
    unittest.main()
