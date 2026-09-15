
# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import tempfile
import unittest
from pathlib import Path

from build_np560_stream_burn_harness import build_file_program, STREAM_FILES_PROTOCOL
from import_np560_vendor_file import encode_path, transfer_file, VendorFiles


class FakeFiles:
    require_success = staticmethod(VendorFiles.require_success)

    def __init__(self, *, existing=False, short_write=False, corrupt=False):
        self.calls = []
        self.data = bytearray()
        self.existing = existing
        self.short_write = short_write
        self.corrupt = corrupt
        self.offset = 0

    def command(self, code, *, pathname=None, payload=None):
        self.calls.append(code)
        result = {"result": 0, "detail": 0, "handle": 1, "count": 0}
        if code == 5 and not self.existing and not self.data:
            result.update(result=-10, detail=-7, handle=0)
        if code == 8:
            self.data.extend(payload)
            result["count"] = len(payload) - self.short_write
        return result

    def read_chunk(self):
        chunk = bytes(self.data[self.offset:self.offset + 8192])
        self.offset += len(chunk)
        if self.corrupt and chunk:
            chunk = bytes([chunk[0] ^ 1]) + chunk[1:]
        return chunk


class VendorFileTests(unittest.TestCase):
    def test_guest_paths_and_file_harness_bounds(self):
        self.assertEqual(encode_path("0:\\应用程序\\英雄传奇.npe").hex(),
                         "303a5cd3a6d3c3b3ccd0f25cd3a2d0dbb4abc6e62e6e7065")
        for path in ("file.npe", "1:\\A.NPE", "0:\\..\\A.NPE", "0:\\A\0.NPE", "0:\\" + "a" * 256):
            with self.assertRaises(ValueError):
                encode_path(path)
        image, labels = build_file_program()
        words = [int.from_bytes(image[i:i + 2], "little") for i in range(0, labels["stop"] + 2, 2)]
        self.assertIn(STREAM_FILES_PROTOCOL, words)
        start = labels["pathname"] // 2
        self.assertEqual(words[start:start + 8], [0x6810, 0, 0x6811, 0xA4, 0x68F0, 0x0FF0, 0x68F1, 0xE000])
        autonomous = [words[i + 1] for i in range(len(words) - 3)
                      if words[i] == 0x68F0 and words[i + 2:i + 4] == [0xA8F0, 8]]
        self.assertEqual(autonomous, [23])
        for command in (2, 11, 13, 18, 25, 27):
            with self.assertRaises(ValueError):
                VendorFiles(None, None, None, 1).command(command)

    def test_odd_tail_roundtrip_and_refuse_overwrite_or_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.npe"
            source.write_bytes(bytes(range(256)) * 33 + b"x")
            client = FakeFiles()
            report = transfer_file(client, source, "0:\\SAMPLE.NPE")
            self.assertEqual(report["read_bytes"], source.stat().st_size)
            self.assertEqual(client.calls, [5, 4, 8, 8, 10, 5, 10])
            existing = FakeFiles(existing=True)
            with self.assertRaises(FileExistsError):
                transfer_file(existing, source, "0:\\SAMPLE.NPE")
            self.assertEqual(existing.calls, [5, 10])
            for client in (FakeFiles(short_write=True), FakeFiles(corrupt=True)):
                with self.assertRaises(RuntimeError):
                    transfer_file(client, source, "0:\\SAMPLE.NPE")


if __name__ == "__main__":
    unittest.main()
