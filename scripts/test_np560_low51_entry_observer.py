from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CPU_HEADER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "cpu.h"
HELPER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "helper.c"
MACHINE = ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"


class Low51EntryObserverTest(unittest.TestCase):
    def test_first_low_51_entry_is_read_only_and_reported(self) -> None:
        header = CPU_HEADER.read_text(encoding="utf-8")
        helper = HELPER.read_text(encoding="utf-8")
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn("bool npe_low51_entry_valid;", header)
        self.assertIn("DMCU_NPE_LOW51_ENTRY_STACK_WORDS 16", header)
        self.assertIn("!env->npe_low51_entry_valid && !env->in_interrupt", helper)
        self.assertIn("dmcu_code_address(0x51, 0x2000)", helper)
        self.assertIn("env->npe_low51_entry_from = from & MASK24;", helper)
        self.assertIn("internal_data_read((sp + index * 2u) & MASK16, 16)", helper)
        self.assertNotIn("internal_data_write", helper[helper.index(
            "Preserve the first foreground edge into the low segment-51 window"
        ):helper.index("Observer-only ABI monitor", helper.index(
            "Preserve the first foreground edge into the low segment-51 window"
        ))])
        self.assertIn("NPE_LOW51_ENTRY=%u FROM:%02x:%04x", machine)


if __name__ == "__main__":
    unittest.main()
