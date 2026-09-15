from __future__ import annotations

import re
import unittest
from pathlib import Path

from test_np560_direct_menu_verifier import valid_inputs
from verify_np560_natural_menu_web import (
    MINIMUM_NATURAL_MENU_FONT_BLITS,
    trace_from,
    validate_natural_menu_snapshot,
)


def natural_inputs() -> dict:
    direct = valid_inputs()
    native_entries = (
        "BOOT33:1@20:0004/sp1000/r0000:0000:0000/a0000,0000,0000,0000",
        "STACK33:1@33:4f60/sp1000/r0000:0000:0000/a0000,0000,0000,0000",
        "INIT261:1@33:6044/sp1000/r0000:0000:0000/a0000,0000,0000,0000",
        "INIT9:1@11:5c0e/sp1000/r0000:0000:0000/a0000,0000,0000,0000",
        "SYSMAIN:1@05:3ffe/sp1000/r0000:0000:0000/a0000,0000,0000,0000",
        "TOP:1@20:031c/sp9000/r0000:0000:0000/a0000,0000,0000,0000",
        "RESINIT:1@32:512c/sp9000/r0000:0000:0000/a0000,0000,0000,0000",
        "SELECTOR:1@1b:d48e/sp8f00/r0000:0000:0000/a0000,0000,0000,0000",
        "SELRET:1@23:a81e/sp8f00/r0001:0000:0000/a0000,0000,0000,0000",
        "MANAGER:1@23:a574/sp8e00/r0000:0000:0000/a0000,0000,0000,0000",
        "REGLOOK:1@18:24a6/sp8d00/r1203:0000:0000/a0000,0000,0000,0000",
        "REGRET:1@2f:e5ea/sp8d00/r0001:0000:0000/a0000,0000,0000,0000",
        "MANRET:1@2c:c9e8/sp8e00/r0001:0000:0000/a0000,0000,0000,0000",
    )
    state = direct["state"].replace(
        "APPLICATION_TRACE=",
        f"APPLICATION_TRACE={','.join(native_entries)},",
    )
    state = re.sub(
        r"NATIVE_FONT_BLIT=CALLS:\d+",
        f"NATIVE_FONT_BLIT=CALLS:{MINIMUM_NATURAL_MENU_FONT_BLITS}",
        state,
    )
    return {
        "state": state,
        "soc_rom": direct["soc_rom"],
        "lcd_frame": direct["lcd_frame"],
        "native_framebuffer": direct["native_framebuffer"],
        "reported_soc_rom_size": direct["reported_soc_rom_size"],
        "reported_soc_rom_sha256": direct["reported_soc_rom_sha256"],
    }


class NaturalMenuVerifierTests(unittest.TestCase):
    def test_accepts_exact_native_selector_chain(self) -> None:
        inputs = natural_inputs()
        result = validate_natural_menu_snapshot(**inputs)

        self.assertEqual(result["selector_calls"], 1)
        self.assertEqual(result["factory_stages"], 5)
        self.assertEqual(result["selector_result"], 1)
        self.assertEqual(result["manager_calls"], 1)
        self.assertEqual(result["root_labels"], 5)
        self.assertEqual(trace_from(inputs["state"], "SELECTOR"), "1b:d48e")

    def test_rejects_direct_menu_probe_without_selector(self) -> None:
        direct = valid_inputs()
        inputs = natural_inputs()
        inputs["state"] = direct["state"]
        with self.assertRaisesRegex(AssertionError, "stage BOOT33"):
            validate_natural_menu_snapshot(**inputs)

    def test_rejects_wrong_factory_linked_order(self) -> None:
        inputs = natural_inputs()
        inputs["state"] = inputs["state"].replace(
            "INIT9:1@11:5c0e", "INIT9:1@24:80aa"
        )
        with self.assertRaisesRegex(AssertionError, "INIT9 has wrong caller"):
            validate_natural_menu_snapshot(**inputs)

    def test_rejects_wrong_selector_caller(self) -> None:
        inputs = natural_inputs()
        inputs["state"] = inputs["state"].replace(
            "SELECTOR:1@1b:d48e", "SELECTOR:1@03:0080"
        )
        with self.assertRaisesRegex(AssertionError, "exact resident call"):
            validate_natural_menu_snapshot(**inputs)

    def test_rejects_selector_without_balanced_epilogue(self) -> None:
        inputs = natural_inputs()
        inputs["state"] = inputs["state"].replace(
            "SELRET:1@23:a81e", "SELRET:1@23:a600"
        )
        with self.assertRaisesRegex(AssertionError, "balanced"):
            validate_natural_menu_snapshot(**inputs)

    def test_rejects_invalid_selector_result(self) -> None:
        inputs = natural_inputs()
        inputs["state"] = inputs["state"].replace(
            "SELRET:1@23:a81e/sp8f00/r0001:",
            "SELRET:1@23:a81e/sp8f00/rffff:",
        )
        with self.assertRaisesRegex(AssertionError, "invalid result"):
            validate_natural_menu_snapshot(**inputs)

    def test_application_trace_target_and_name_arrays_stay_aligned(self) -> None:
        qemu_root = Path(__file__).resolve().parents[1] / "qemu-dmcu"
        helper = (qemu_root / "target/dmcu/helper.c").read_text(encoding="utf-8")
        machine = (qemu_root / "hw/dmcu/np560.c").read_text(encoding="utf-8")
        cpu_header = (qemu_root / "target/dmcu/cpu.h").read_text(
            encoding="utf-8"
        )
        targets_block = helper.split("application_targets[", 1)[1].split(
            "};", 1
        )[0]
        names_block = machine.split(
            "static const char *const names[", 1
        )[1].split("};", 1)[0]
        targets = re.findall(r"0x[0-9a-fA-F]+u", targets_block)
        names = re.findall(r'"([A-Z][A-Z0-9]*)"', names_block)
        declared_match = re.search(
            r"#define\s+DMCU_APPLICATION_TRACE_ENTRIES\s+(\d+)",
            cpu_header,
        )
        self.assertIsNotNone(declared_match)
        declared_entries = int(declared_match.group(1))

        self.assertEqual(declared_entries, 181)
        self.assertEqual(len(targets), declared_entries)
        self.assertEqual(len(names), declared_entries)
        selector = names.index("RESINIT")
        self.assertEqual(
            list(zip(targets[selector:selector + 3],
                     names[selector:selector + 3])),
            [
                ("0x1bce3cu", "RESINIT"),
                ("0x23a38cu", "SELECTOR"),
                ("0x1bd492u", "SELRET"),
            ],
        )
        factory = names.index("BOOT33")
        self.assertEqual(
            list(zip(targets[factory:factory + 5],
                     names[factory:factory + 5])),
            [
                ("0x334f50u", "BOOT33"),
                ("0x33603cu", "STACK33"),
                ("0x114560u", "INIT261"),
                ("0x077fe4u", "INIT9"),
                ("0x03026au", "SYSMAIN"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
