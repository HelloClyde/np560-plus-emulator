#!/usr/bin/env python3

import hashlib
import unittest

from scripts import publish_np560_resource_persistence_writer as publish


class PersistenceWriterPublicationTests(unittest.TestCase):
    def test_exact_source_modules_are_published_idempotently(self) -> None:
        size = max(
            source - publish.PROGRAM_BASE + length
            for _name, _destination, source, length in
            publish.PERSISTENCE_WRITER_MODULES
        )
        image = bytearray(b"\xA5" * size)
        expected: dict[int, bytes] = {}
        for index, (_name, destination, source, length) in enumerate(
                publish.PERSISTENCE_WRITER_MODULES):
            body = bytes((offset * 17 + index * 29) & 0xFF
                         for offset in range(length))
            source_offset = source - publish.PROGRAM_BASE
            image[source_offset:source_offset + length] = body
            expected[destination] = body

        output, manifest = publish.publish_persistence_writer(bytes(image))
        for destination, body in expected.items():
            target_offset = destination - publish.PROGRAM_BASE
            self.assertEqual(output[target_offset:target_offset + len(body)], body)
        self.assertEqual(len(manifest["modules"]), 3)
        self.assertTrue(all(item["changed"] for item in manifest["modules"]))
        self.assertFalse(manifest["hardware_rom_service"])
        self.assertFalse(manifest["host_storage_service"])
        self.assertEqual(manifest["output_sha256"], hashlib.sha256(output).hexdigest())

        repeated, second = publish.publish_persistence_writer(output)
        self.assertEqual(repeated, output)
        self.assertTrue(all(not item["changed"] for item in second["modules"]))

    def test_rejects_truncated_program(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the PRG"):
            publish.publish_persistence_writer(bytes(0x1000))


if __name__ == "__main__":
    unittest.main()
