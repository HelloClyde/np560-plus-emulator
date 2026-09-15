#!/usr/bin/env python3
"""Unit tests for the read-only NP560 QEMU bus dump utility."""

from __future__ import annotations

import unittest

from scripts import dump_np560_qemu_bus as dump


class DumpQemuBusTests(unittest.TestCase):
    def test_parses_segmented_and_flat_ranges(self) -> None:
        self.assertEqual(dump.parse_range("1B:CD04+0x4"), (0x1BCD04, 4))
        self.assertEqual(dump.parse_range("0xD20+16"), (0xD20, 16))

    def test_code_expression_selects_harvard_address_space(self) -> None:
        expression = dump.code_expression(0x5FFA1E)
        self.assertIn("cpu_ases[1].as", expression)
        self.assertIn("0x5ffa1e", expression)

    def test_internal_expression_does_not_call_tls_read_helper(self) -> None:
        expression = dump.internal_expression(0xD20)
        self.assertIn("->internal_data", expression)
        self.assertNotIn("internal_data_read", expression)

    def test_internal_expression_reads_only_requested_bytes(self) -> None:
        expression = dump.internal_expression(0xD20)
        self.assertIn("+ 0xd20", expression)
        self.assertIn("+ 0xd21", expression)
        self.assertEqual(expression.count("unsigned char"), 2)

    def test_word_addresses_are_exact_and_bounded(self) -> None:
        self.assertEqual(
            list(dump.word_addresses([(0x10, 6)], 0x100)),
            [0x10, 0x12, 0x14],
        )
        with self.assertRaises(ValueError):
            list(dump.word_addresses([(0xFE, 4)], 0x100))

    def test_gdb_commands_are_streamable_and_detach(self) -> None:
        commands = dump.gdb_commands([(0x1BCD04, 2)], [(0xD20, 2)])
        self.assertEqual(commands[0], "set pagination off")
        self.assertIn("C 1BCD04", commands[2])
        self.assertIn("I 0D20", commands[3])
        self.assertEqual(commands[-1], "detach")

    def test_translates_windows_path_for_wsl(self) -> None:
        self.assertEqual(
            dump.windows_to_wsl_path(r"C:\Temp\np560.gdb"),
            "/mnt/c/Temp/np560.gdb",
        )


if __name__ == "__main__":
    unittest.main()
