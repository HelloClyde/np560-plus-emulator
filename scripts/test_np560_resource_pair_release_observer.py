from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "helper.c"
CPU_HEADER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "cpu.h"
MACHINE = ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"


class ResourcePairReleaseObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = HELPER.read_text(encoding="utf-8")
        cls.cpu_header = CPU_HEADER.read_text(encoding="utf-8")
        cls.machine = MACHINE.read_text(encoding="utf-8")

    def test_exact_footer_and_clock_callers_arm_the_observer(self):
        arm_start = self.helper.index(
            "/* Arm the exact adjacent resource pair only:"
        )
        arm_end = self.helper.index(
            "if (env->clock_resource_release_active)", arm_start
        )
        arm = self.helper[arm_start:arm_end]

        self.assertIn("dmcu_code_address(0x27, 0x58e4)", arm)
        self.assertIn("dmcu_code_address(0x31, 0x590e)", arm)
        self.assertIn("dmcu_code_address(0x2e, 0x0af6)", arm)
        self.assertIn("!env->in_interrupt", arm)

    def test_trace_capacity_covers_initial_clock_and_thirty_pairs(self):
        self.assertIn(
            "#define DMCU_CLOCK_RESOURCE_RELEASE_TRACE_SLOTS 64",
            self.cpu_header,
        )

    def test_all_handle_release_boundaries_are_observed(self):
        for address in (
            "dmcu_code_address(0x2e, 0x0c64)",
            "dmcu_code_address(0x2e, 0x0c6a)",
            "dmcu_code_address(0x30, 0x8b26)",
            "dmcu_code_address(0x30, 0x8c1a)",
            "dmcu_code_address(0x2e, 0x0c76)",
            "dmcu_code_address(0x30, 0x3a56)",
            "dmcu_code_address(0x30, 0x3b60)",
            "dmcu_code_address(0x31, 0x8abc)",
            "dmcu_code_address(0x31, 0x8b68)",
            "dmcu_code_address(0x2e, 0x0c7c)",
        ):
            self.assertIn(address, self.helper)

        self.assertIn("(resource_fp - 6u) & MASK16", self.helper)
        self.assertIn("internal_data_read(sp, 16)", self.helper)
        self.assertIn("internal_data_read((old_sp + 4u) & MASK16, 16)",
                      self.helper)

    def test_registry_and_bitmap_snapshot_is_read_only(self):
        snapshot_start = self.helper.index(
            "static void snapshot_clock_resource_release"
        )
        snapshot_end = self.helper.index(
            "/* Observer-only watch for the low word", snapshot_start
        )
        snapshot = self.helper[snapshot_start:snapshot_end]

        self.assertIn("address_space_lduw_le", snapshot)
        self.assertIn("internal_data_read", snapshot)
        for mutator in (
            "address_space_st",
            "address_space_write",
            "internal_data_write",
            "cpu_physical_memory_write",
        ):
            self.assertNotIn(mutator, snapshot)

    def test_diagnostics_expose_pair_identity_and_release_evidence(self):
        self.assertIn("RESOURCE_PAIR_RELEASE=CALLS:%u ACTIVE:%u TRACE:",
                      self.machine)
        self.assertIn("clock_resource_release_caller", self.machine)
        self.assertIn("clock_resource_release_stage_argument", self.machine)
        self.assertIn("clock_resource_release_stage_node_word", self.machine)
        self.assertIn("clock_resource_release_stage_bitmap_word", self.machine)
        self.assertIn("clock_resource_release_mask_bitmap_before", self.machine)
        self.assertIn("clock_resource_release_mask_bitmap_after", self.machine)
        self.assertIn("no field below is consumed by guest execution",
                      self.cpu_header)


if __name__ == "__main__":
    unittest.main()
