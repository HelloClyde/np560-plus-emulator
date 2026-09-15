#!/usr/bin/env python3

from __future__ import annotations

import unittest

from scripts import analyse_np560_nwf_format as nwf


class NwfFormatAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.program = nwf.DEFAULT_PROGRAM.read_bytes()

    def test_extracts_exact_format_and_menu_contract(self) -> None:
        result = nwf.analyse(self.program)
        resource = result["resource_open"]
        loader = result["record_loader"]
        launch = result["menu_launch"]

        self.assertEqual(resource["minimum_file_bytes"], 0x5F)
        self.assertEqual(resource["header_read_bytes"], 0x200)
        self.assertEqual(resource["protected_header_blocks"], 0x3E)
        self.assertEqual(resource["des_block_bytes"], 8)
        self.assertEqual(resource["protected_header_bytes"], 0x1F0)
        self.assertEqual(
            [entry["text"] for entry in resource["accepted_versions"]],
            ["NEPLAYERV0.98", "NEPLAYERV0.99"],
        )
        self.assertEqual(resource["player_magic"]["text"], "NEPLAYER")
        self.assertEqual(
            resource["authorization_magic"]["text"], "NOAHAUTH"
        )
        self.assertEqual(loader["direct_window_threshold"], 0xFE00)
        self.assertEqual(loader["record_window_bytes"], 0x200)
        self.assertEqual(launch["application_code"], 0x1203)
        self.assertEqual(launch["registry_entry"]["entry_point"], "2C:C9E8")
        self.assertFalse(result["scope"]["original_factory_nwf_recovered"])
        table = resource["header_table"]
        self.assertEqual(table["offset"], 0x40)
        self.assertEqual(table["authorization_disabled_value"], -1)
        self.assertEqual(
            [field["relative_offset"] for field in
             table["signed_little_endian_24_bit_fields"]],
            [0x01, 0x04, 0x07, 0x0A, 0x0D,
             0x10, 0x13, 0x16, 0x19, 0x1C],
        )

    def test_logical_bytes_exchange_each_word(self) -> None:
        self.assertEqual(
            nwf.logical_bytes(self.program, 0x48FFD8, 13),
            b"NEPLAYERV0.99",
        )
        self.assertEqual(
            nwf.logical_bytes(self.program, 0x48FFE6, 13),
            b"NEPLAYERV0.98",
        )

    def test_fails_when_an_instruction_anchor_changes(self) -> None:
        damaged = bytearray(self.program)
        offset = 0x3A66F4 - nwf.PROGRAM_BASE
        damaged[offset:offset + 2] = (0).to_bytes(2, "little")
        with self.assertRaisesRegex(ValueError, "minimum resource size check"):
            nwf.analyse(bytes(damaged))

    def test_fails_when_a_format_constant_changes(self) -> None:
        damaged = bytearray(self.program)
        offset = 0x48FFA8 - nwf.PROGRAM_BASE
        damaged[offset] ^= 1
        with self.assertRaisesRegex(ValueError, "authorization_magic mismatch"):
            nwf.analyse(bytes(damaged))


if __name__ == "__main__":
    unittest.main()
