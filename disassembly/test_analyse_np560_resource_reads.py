import tempfile
import unittest
from pathlib import Path

import analyse_np560_resource_reads as reads


class ResourceReadAnalysisTests(unittest.TestCase):
    def test_extracts_fixed_five_word_call(self) -> None:
        assembly = """\
38:CF08  68F0 0032  MOV REG[0xF0], #0x0032
38:CF0C  58F0       MOV [--R15], R0
38:CF0E  68F0 0010  MOV REG[0xF0], #0x0010
38:CF12  68F1 D040  MOV REG[0xF1], #0xD040
38:CF16  58F1       MOV [--R15], R1
38:CF18  58F0       MOV [--R15], R0
38:CF1A  68F1 4F36  MOV REG[0xF1], #0x4F36
38:CF1E  68F0 0052  MOV REG[0xF0], #0x0052
38:CF22  58F1       MOV [--R15], R1
38:CF24  58F0       MOV [--R15], R0
38:CF26  BD25 206E  SCALL 25:206E
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "fixture.asm")
            path.write_text(assembly, encoding="utf-8")
            calls = reads.classify(reads.parse_assembly(path), 48)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["length"], 0x32)
        self.assertEqual(calls[0]["source"], 0x10D040)
        self.assertEqual(calls[0]["output"], 0x524F36)


if __name__ == "__main__":
    unittest.main()
