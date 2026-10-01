"""Opt-in NPE decoder launch arguments must not change the default path."""

import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.web import np560_web as web


class OwnedNPECodecTests(unittest.TestCase):
    def test_default_has_no_owned_decoder(self):
        args = web.parse_args([])
        self.assertIsNone(args.rom_npe_codec_dll)
        self.assertIsNone(args.rom_npe_codec_socket)
        self.assertFalse(args.rom_npe_codec_owned)

    def test_independent_decoder_is_explicit_and_needs_no_dll(self):
        args = web.parse_args(["--rom-npe-codec-owned"])
        self.assertTrue(args.rom_npe_codec_owned)
        self.assertIsNone(args.rom_npe_codec_dll)
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                web.parse_args(["--rom-npe-codec-owned",
                                "--rom-npe-codec-socket", "/tmp/external.sock"])

    def test_owned_decoder_requires_existing_local_dll(self):
        with tempfile.TemporaryDirectory() as directory:
            dll = Path(directory) / "mv_sp.dll"
            dll.write_bytes(b"fixture")
            args = web.parse_args(["--rom-npe-codec-dll", str(dll)])
            self.assertEqual(args.rom_npe_codec_dll, dll)
            with redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit):
                    web.parse_args(["--rom-npe-codec-dll", str(dll),
                                    "--rom-npe-codec-socket", "/tmp/external.sock"])
                with self.assertRaises(SystemExit):
                    web.parse_args(["--rom-npe-codec-pythonpath", directory])
                with self.assertRaises(SystemExit):
                    web.parse_args(["--rom-npe-codec-owned",
                                    "--rom-npe-codec-dll", str(dll)])


if __name__ == "__main__":
    unittest.main()
