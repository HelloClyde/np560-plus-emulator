from __future__ import annotations

import unittest

from scripts import build_np560_nand_rw_harness as harness


class NandRwHarnessTests(unittest.TestCase):
    @staticmethod
    def calls(image: bytes, loop: int) -> list[int]:
        words = [
            int.from_bytes(image[offset : offset + 2], "little")
            for offset in range(0, loop + 2, 2)
        ]
        return [
            words[index + 1]
            for index, word in enumerate(words[:-1])
            if word == 0xBD02
        ]

    def test_calls_program_read_erase_read(self) -> None:
        image, loop = harness.build_program()
        words = [
            int.from_bytes(image[offset : offset + 2], "little")
            for offset in range(0, loop + 2, 2)
        ]
        calls = [
            words[index + 1]
            for index, word in enumerate(words[:-1])
            if word == 0xBD02
        ]

        self.assertEqual(
            calls,
            [
                0xBCC6, 0xBBF6, 0xBDD6, 0xBBF6, 0xBBF6,
                0xBCC6, 0xBBF6, 0xBBF6,
            ],
        )
        self.assertEqual(words[-1], 0xD0FF)
        source_offset = harness.SOURCE - harness.PROGRAM_BASE
        self.assertEqual(
            image[source_offset : source_offset + len(harness.PATTERN)],
            harness.PATTERN,
        )
        oob_source_offset = harness.OOB_SOURCE - harness.PROGRAM_BASE
        self.assertEqual(
            image[
                oob_source_offset : oob_source_offset + len(harness.OOB_PATTERN)
            ],
            harness.OOB_PATTERN,
        )
        self.assertEqual(harness.SOURCE >> 16, 0x20)
        self.assertEqual(harness.READBACK >> 16, 0x50)
        self.assertEqual(harness.ERASED_READBACK >> 16, 0x50)
        self.assertEqual(harness.OOB_READBACK >> 16, 0x50)
        self.assertEqual(harness.OOB_PROBE_READBACK >> 16, 0x50)
        self.assertEqual(harness.OOB_PROBE_COLUMN, 2102)

    def test_persistence_writer_erases_then_programs_data_and_oob(self) -> None:
        image, loop = harness.build_program("persist-write")

        self.assertEqual(
            self.calls(image, loop),
            [0xBDD6, 0xBDD6, 0xBCC6, 0xBCC6],
        )

    def test_persistence_reader_does_not_modify_nand(self) -> None:
        image, loop = harness.build_program("persist-read")

        self.assertEqual(
            self.calls(image, loop),
            [0xBBF6, 0xBBF6, 0xBBF6],
        )


if __name__ == "__main__":
    unittest.main()
