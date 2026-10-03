"""Small deterministic transport tests for compressed NAND checkpoints."""

from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from scripts import compress_np560_checkpoint as checkpoint


class CompressedCheckpointTests(unittest.TestCase):
    def test_round_trip_and_reject_wrong_source_identity(self):
        data = b"\xff" * 4096
        oob = bytes(range(64)) * 2
        header = bytearray(64)
        struct.pack_into("<8s6I2Q", header, 0, b"NP560N1\0",
                         1, 64, 2048, 64, 64, 4096, len(data), len(oob))
        original = bytes(header) + data + oob

        with tempfile.TemporaryDirectory() as directory, \
                patch.object(checkpoint, "DATA_SIZE", len(data)), \
                patch.object(checkpoint, "OOB_SIZE", len(oob)), \
                patch.object(checkpoint, "CHECKPOINT_SIZE", len(original)):
            source = Path(directory) / "system.nand"
            source.write_bytes(original)
            first = Path(directory) / "first.nand.gz"
            second = Path(directory) / "second.nand.gz"
            digest = hashlib.sha256(original).hexdigest()
            report = checkpoint.compress(source, first, digest)
            checkpoint.compress(source, second, digest)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(gzip.decompress(first.read_bytes()), original)
            self.assertEqual(report["source_sha256"], digest)
            self.assertLess(report["compressed_bytes"], len(original))

            rejected = Path(directory) / "rejected.nand.gz"
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                checkpoint.compress(source, rejected, "0" * 64)
            self.assertFalse(rejected.exists())
