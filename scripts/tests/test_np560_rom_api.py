
# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import np560_rom_api as api


SAMPLE = """\
entry:
50:6000  2E02       LINK #0x02
50:6002  4801       MOV R0, #0x1
50:6004  58F0       MOV [--R15], R0
50:6006  BD02 BBF6  SCALL 02:BBF6
50:600A  50F2       ADD R15, #0x2
50:600C  BD51 0000  SCALL 51:0000
sub_51_0000:
51:0000  4802       MOV R0, #0x2
51:0002  BD02 C04C  SCALL 02:C04C
51:0006  C620       RETS
"""


class ResidentRomApiTests(unittest.TestCase):
    def test_filters_and_groups_resident_segment_calls(self):
        instructions, calls = api.parse_listing(SAMPLE)
        self.assertEqual(len(instructions), 9)
        self.assertEqual(
            [(call.address, call.target, call.function) for call in calls],
            [
                ("50:6006", "02:BBF6", "entry"),
                ("51:0002", "02:C04C", "sub_51_0000"),
            ],
        )

    def test_report_marks_call_and_keeps_function_context(self):
        instructions, calls = api.parse_listing(SAMPLE)
        report = api.render_report(Path("sample.asm"), instructions, calls, 8, 1)
        self.assertIn("Direct calls into code segment 02: 2", report)
        self.assertIn("| `02:BBF6` | 1 | 1 | `0x2` (1 words) |", report)
        self.assertIn("> 50:6006  BD02 BBF6  SCALL 02:BBF6", report)
        c04c = report.index("### `51:0002` in `sub_51_0000`")
        self.assertNotIn("50:600C", report[c04c : c04c + 300])


if __name__ == "__main__":
    unittest.main()
