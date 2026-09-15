
# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import np560_disasm as d


class DecoderTests(unittest.TestCase):
    def decode(self, *words: int, index: int = 0) -> d.Instruction:
        return d.decode(list(words), index, 0x20)

    def test_reset_stub(self):
        call = self.decode(0xBD03, 0x0030)
        self.assertEqual(call.text, "SCALL 03:0030")
        self.assertEqual(call.size, 2)
        self.assertEqual(call.flow, "call")

        jump = self.decode(0xAD33, 0x4F50)
        self.assertEqual(jump.text, "SJMP 33:4F50")
        self.assertEqual(jump.flow, "jump")

    def test_multiply_pdf_correction(self):
        self.assertEqual(self.decode(0xC061).text, "MUL R6, R1")
        self.assertEqual(self.decode(0xC101).text, "UMUL R0, R1")

    def test_software_reset_is_not_a_fallthrough_instruction(self):
        reset = self.decode(0x3FFF)
        self.assertEqual(reset.text, "RESET")
        self.assertEqual(reset.size, 1)
        self.assertEqual(reset.flow, "stop")

    def test_common_move_forms(self):
        self.assertEqual(self.decode(0x2831).text, "MOV R3, [R1]")
        self.assertEqual(self.decode(0x6810, 0x00A2).text, "MOV REG[0x10], #0x00A2")
        self.assertEqual(self.decode(0x780B, 0xFFFC).text, "MOV R0, [R11+0xFFFC]")

    def test_mac_forms_are_selected_by_configuration_not_zero_operands(self):
        self.assertEqual(self.decode(0xBEF0, 0x0700).text, "MULS.ss.r.s R7, R0")
        self.assertEqual(self.decode(0xBED0, 0x0100).text, "MAC.ss.r.s R1, R0")
        self.assertEqual(self.decode(0xBE10, 0).text, "MAC.ss R0, R0")
        self.assertEqual(self.decode(0xBEA0, 0).text, "RNDST.r")
        self.assertEqual(self.decode(0xBE68, 0).text, "RNDST.s")
        self.assertEqual(self.decode(0xBE03, 0x040D).text, "MAC.ss.m.- [X0++], [Y1+YC1]")
        for opcode, operands in ((0xBEF0, 0x1000), (0xBE20, 1), (0xBE32, 0),
                                 (0xBE12, 0), (0xBE00, 0x0300), (0xBE6A, 0x59F9)):
            instruction = self.decode(opcode, operands)
            self.assertEqual(instruction.flow, "stop")
            self.assertEqual(instruction.size, 2)

    def test_relative_branch_scales_word_displacement_to_bytes(self):
        ins = self.decode(0xD0FE)
        self.assertEqual(ins.targets, (d.Address(0x20, 0xFFFE),))
        self.assertEqual(ins.flow, "jump")

    def test_program_addresses_are_byte_addressed(self):
        self.assertEqual(d.address_for_index(2, 0x20), d.Address(0x20, 0x0004))
        self.assertEqual(
            d.index_for_address(d.Address(0x33, 0x4F50), 0x20, 0x200000),
            0x9A7A8,
        )


if __name__ == "__main__":
    unittest.main()
