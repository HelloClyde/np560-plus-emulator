from __future__ import annotations

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
import analyse_np560_resident_context as context


def ins(address: int, text: str) -> context.Instruction:
    return context.Instruction(address, address >> 16, address & 0xFFFF, text)


class ResidentContextAnalysisTests(unittest.TestCase):
    def test_extracts_word_read_from_r0_r1_context_pair(self) -> None:
        code = [
            ins(0x334510, "MOV R0, [R11+0xFFFC]"),
            ins(0x334514, "MOV R1, [R11+0xFFFE]"),
            ins(0x334518, "ADD REG[0xF1], #0x0024"),
            ins(0x33451C, "ADDC R0, #0x0"),
            ins(0x334520, "SL R1, #0x1"),
            ins(0x334522, "SLOSB R0, #0x1"),
            ins(0x334524, "MOV R0, [R1]"),
        ]
        uses = context.extract_outer_uses(code, 0x334510, 0x3352A8)
        self.assertEqual(len(uses), 1)
        self.assertEqual(uses[0].offset, 0x24)
        self.assertEqual((uses[0].operation, uses[0].width_bits), ("read", 16))

    def test_extracts_copied_r2_r3_far_pointer_write(self) -> None:
        code = [
            ins(0x334510, "MOV R0, [R11+0xFFFC]"),
            ins(0x334514, "MOV R1, [R11+0xFFFE]"),
            ins(0x334518, "MOV R2, R0"),
            ins(0x33451A, "MOV R3, R1"),
            ins(0x33451C, "ADD REG[0xF3], #0x0030"),
            ins(0x334520, "ADDC R2, #0x0"),
            ins(0x334524, "MOV [R3++], R0"),
        ]
        uses = context.extract_outer_uses(code, 0x334510, 0x3352A8)
        self.assertEqual(len(uses), 1)
        self.assertEqual(uses[0].offset, 0x30)
        self.assertEqual((uses[0].operation, uses[0].width_bits), ("write", 32))


if __name__ == "__main__":
    unittest.main()
