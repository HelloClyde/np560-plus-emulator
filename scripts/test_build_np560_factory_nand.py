import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_np560_factory_nand as factory


class FactoryWriterTests(unittest.TestCase):
    def test_streaming_writer_is_byte_identical_to_reference(self):
        geometry = dict(BLOCKS=2, PAGES=128, DATA_SIZE=128 * 2048, OOB_SIZE=128 * 64)
        with patch.multiple(factory, **geometry), tempfile.TemporaryDirectory() as name:
            root = Path(name)
            output = root / "factory.nand"
            native = root / "rehash"
            native.touch()

            def rehash(command, check):
                self.assertTrue(check)
                self.assertEqual(Path(command[0]), native.resolve())
                target = Path(command[1])
                data = target.read_bytes()
                with target.open("r+b") as stream:
                    stream.seek(48)
                    stream.write(struct.pack("<2I",
                        factory.fnv1a(data[64:64 + factory.DATA_SIZE]),
                        factory.fnv1a(data[64 + factory.DATA_SIZE:])))

            with patch.object(factory.subprocess, "run", side_effect=rehash):
                factory.write_erased_checkpoint(output, native)
                self.assertEqual(output.read_bytes(), factory.build_checkpoint())
                factory.validate_checkpoint(output.read_bytes(), expect_erased=True)
                before = output.read_bytes()
                with self.assertRaises(FileExistsError):
                    factory.write_erased_checkpoint(output, native)
                self.assertEqual(output.read_bytes(), before)

    def test_missing_native_tool_creates_nothing(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with self.assertRaises(ValueError):
                factory.write_erased_checkpoint(root / "new.nand", root / "missing")
            self.assertFalse((root / "new.nand").exists())


if __name__ == "__main__":
    unittest.main()
