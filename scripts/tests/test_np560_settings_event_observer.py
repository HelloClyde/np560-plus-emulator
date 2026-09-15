
# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
CPU_HEADER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "cpu.h"
HELPER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "helper.c"
MACHINE = ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"


class SettingsEventObserverTest(unittest.TestCase):
    def test_settings_event_lifecycle_is_exact_and_read_only(self) -> None:
        header = CPU_HEADER.read_text(encoding="utf-8")
        helper = HELPER.read_text(encoding="utf-8")
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn("settings_event_poll_calls;", header)
        self.assertIn("settings_event_callback_target;", header)
        start = helper.index(
            "The settings child at 1E:F820 obtains its event"
        )
        end = helper.index(
            "Source 42:206E is installed at runtime 25:206E", start
        )
        observer = helper[start:end]
        for address in (
            "dmcu_code_address(0x1e, 0xf82e)",
            "dmcu_code_address(0x33, 0x38f8)",
            "dmcu_code_address(0x33, 0x3918)",
            "dmcu_code_address(0x33, 0x591e)",
            "dmcu_code_address(0x1e, 0xf886)",
            "dmcu_code_address(0x15, 0xf0ee)",
        ):
            self.assertIn(address, observer)
        self.assertIn("(fp + 0x0012u)", observer)
        self.assertIn("(fp + 0x0014u)", observer)
        self.assertNotIn("internal_data_write", observer)
        self.assertNotIn("address_space_st", observer)
        self.assertNotIn("env->pc =", observer)
        self.assertIn("SETTINGS_EVENT=POLL:%u/%u/A%u", machine)

    def test_invalid_control_freezes_register_stack_and_frame_context(self) -> None:
        header = CPU_HEADER.read_text(encoding="utf-8")
        helper = HELPER.read_text(encoding="utf-8")
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn("DMCU_INVALID_CONTROL_GPR_WORDS 16", header)
        self.assertIn("DMCU_INVALID_CONTROL_STACK_WORDS 16", header)
        self.assertIn("DMCU_INVALID_CONTROL_FRAME_WORDS 16", header)
        start = helper.index(
            "Every DMCU instruction word is two-byte aligned"
        )
        end = helper.index(
            "if ((env->pc & MASK24) == 0x1cf28au", start
        )
        observer = helper[start:end]
        self.assertIn("env->invalid_control_sequential", observer)
        self.assertIn("env->invalid_control_post_sp", observer)
        self.assertIn("env->invalid_control_gpr[index]", observer)
        self.assertIn("env->invalid_control_stack[index]", observer)
        self.assertIn("env->invalid_control_frame[index]", observer)
        self.assertNotIn("internal_data_write", observer)
        self.assertNotIn("address_space_st", observer)
        self.assertNotIn("env->pc =", observer)
        self.assertIn("INVALID_CONTROL_CONTEXT=SEQ:%02x:%04x", machine)


if __name__ == "__main__":
    unittest.main()
