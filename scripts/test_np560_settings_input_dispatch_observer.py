from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CPU_HEADER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "cpu.h"
HELPER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "helper.c"
MACHINE = ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"


class SettingsInputDispatchObserverTest(unittest.TestCase):
    def test_e0_input_dispatch_trace_is_scoped_bounded_and_read_only(self) -> None:
        header = CPU_HEADER.read_text(encoding="utf-8")
        helper = HELPER.read_text(encoding="utf-8")
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn("DMCU_SETTINGS_INPUT_TRACE_SLOTS 128", header)
        self.assertIn("bool settings_input_dispatch_active;", header)
        self.assertIn("bool settings_input_region_valid;", header)

        start = helper.index(
            "The restored resident E0 handler calls the exact input dispatcher"
        )
        end = helper.index(
            "Preserve the first foreground edge into the low segment-51", start
        )
        observer = helper[start:end]
        for address in (
            "dmcu_code_address(0x15, 0xf2ca)",
            "dmcu_code_address(0x11, 0x1752)",
            "dmcu_code_address(0x33, 0x52aa)",
            "dmcu_code_address(0x33, 0x5ab8)",
            "dmcu_code_address(0x15, 0xf2ce)",
        ):
            self.assertIn(address, observer)
        self.assertIn(
            "sequence % DMCU_SETTINGS_INPUT_TRACE_SLOTS", observer
        )
        self.assertIn("settings_input_region_gpr[index]", observer)
        self.assertIn("settings_input_region_stack[index]", observer)
        self.assertIn("settings_input_region_frame[index]", observer)
        self.assertNotIn("internal_data_write", observer)
        self.assertNotIn("address_space_st", observer)
        self.assertNotIn("env->pc =", observer)

        self.assertIn(
            "SETTINGS_INPUT=ENTRIES:%u RETURNS:%u ACTIVE:%u EDGES:%u",
            machine,
        )
        self.assertIn("SETTINGS_INPUT_TRACE=", machine)

    def test_e0_action_table_has_a_narrow_harvard_data_alias(self) -> None:
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn(
            "NP560_RESIDENT_EVENT_E0_HANDLER_TABLE_BASE 0x0015f362u",
            machine,
        )
        self.assertIn(
            "NP560_RESIDENT_EVENT_E0_HANDLER_TABLE_SIZE 0x0000000cu",
            machine,
        )
        self.assertIn(
            "np560.data-resident-event-e0-handler-table-alias",
            machine,
        )
        self.assertIn(
            "&s->data_resident_event_e0_handler_table_alias, 2",
            machine,
        )

    def test_resource_kind_table_has_a_narrow_harvard_data_alias(self) -> None:
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn(
            "NP560_RESIDENT_RESOURCE_DISPATCH_KIND_TABLE_BASE 0x0014b932u",
            machine,
        )
        self.assertIn(
            "NP560_RESIDENT_RESOURCE_DISPATCH_KIND_TABLE_SIZE 0x00000010u",
            machine,
        )
        self.assertIn(
            "np560.data-resident-resource-dispatch-kind-table-alias",
            machine,
        )
        self.assertIn(
            "&s->data_resident_resource_dispatch_kind_table_alias, 2",
            machine,
        )

    def test_resource_event_table_has_a_narrow_harvard_data_alias(self) -> None:
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn(
            "NP560_RESIDENT_RESOURCE_DISPATCH_EVENT_TABLE_BASE 0x0014b816u",
            machine,
        )
        self.assertIn(
            "NP560_RESIDENT_RESOURCE_DISPATCH_EVENT_TABLE_SIZE 0x0000000eu",
            machine,
        )
        self.assertIn(
            "np560.data-resident-resource-dispatch-event-table-alias",
            machine,
        )
        self.assertIn(
            "&s->data_resident_resource_dispatch_event_table_alias, 2",
            machine,
        )

        helper = HELPER.read_text(encoding="utf-8")
        self.assertIn(
            "&address_space_memory, 0x14b816u + index * 2u",
            helper,
        )
        self.assertNotIn(
            "&address_space_memory, 0x14b716u + index * 2u",
            helper,
        )

    def test_sound_effect_switch_table_has_a_narrow_harvard_data_alias(
        self,
    ) -> None:
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn(
            "NP560_RESIDENT_SOUND_EFFECT_SWITCH_EVENT_TABLE_BASE "
            "0x001ba6bcu",
            machine,
        )
        self.assertIn(
            "NP560_RESIDENT_SOUND_EFFECT_SWITCH_EVENT_TABLE_SIZE "
            "0x00000022u",
            machine,
        )
        self.assertIn(
            "np560.data-resident-sound-effect-switch-event-table-alias",
            machine,
        )
        self.assertIn(
            "&s->data_resident_sound_effect_switch_event_table_alias, 2",
            machine,
        )

    def test_state_descriptor_uses_exact_adjacent_source_overlay(self) -> None:
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn(
            "NP560_APPLICATION_STATE_DESCRIPTOR_OVERLAY_BASE 0x0031345eu",
            machine,
        )
        self.assertIn(
            "NP560_APPLICATION_STATE_DESCRIPTOR_OVERLAY_SIZE 0x00c4u",
            machine,
        )
        self.assertIn(
            "NP560_APPLICATION_STATE_DESCRIPTOR_OVERLAY_SOURCE 0x004e345eu",
            machine,
        )
        self.assertIn(
            "np560.code-application-state-descriptor-overlay-alias",
            machine,
        )

    def test_one_scan_matrix_pulse_is_consumed_only_by_exact_row_scan(
        self,
    ) -> None:
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn("uint32_t matrix_pulse_index;", machine)
        self.assertIn(
            "qatomic_set(&s->keyboard.matrix_pulse_index, 64);", machine
        )
        self.assertIn(
            "matrix |= 1ull << pulse_index;", machine
        )
        self.assertIn(
            "uint16_t selected = (~s->keyboard.matrix_drive) & 0xc0fc;",
            machine,
        )
        self.assertIn(
            "selected == np560_matrix_row_masks[pulse_index & 7]", machine
        )
        self.assertIn(
            "qatomic_cmpxchg(&s->keyboard.matrix_pulse_index,\n"
            "                                pulse_index, 64);",
            machine,
        )
        self.assertIn(
            "qatomic_read(&s->keyboard.matrix_pulse_index) >= 64", machine
        )
        self.assertIn('"key-matrix-pulse-index", "uint32"', machine)
        setter = machine.split(
            "static void np560_set_key_matrix_pulse_index", 1
        )[1].split("static void np560_load_nand_image", 1)[0]
        self.assertNotIn("address_space_st", setter)
        self.assertNotIn("internal_data_write", setter)
        self.assertNotIn("env->pc", setter)

    def test_key_completion_duplicate_trace_is_bounded_and_read_only(
        self,
    ) -> None:
        header = CPU_HEADER.read_text(encoding="utf-8")
        helper = HELPER.read_text(encoding="utf-8")
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn("DMCU_MATRIX_COMPLETION_TRACE_SLOTS 16", header)
        self.assertIn("matrix_completion_trace_previous_pc", header)
        self.assertIn("matrix_completion_trace_stack", header)
        start = helper.index(
            "A single raw matrix scan has been observed to reach the exact"
        )
        end = helper.index(
            "The exact 32:F3C6 application initializer", start
        )
        observer = helper[start:end]
        self.assertIn("start == 0x3338f8u", observer)
        self.assertIn("start == 0x28f4a4u", observer)
        self.assertIn("env->exec_trace_pc[previous_slot]", observer)
        self.assertIn("0x512a5cu", observer)
        self.assertIn("0x512a8au", observer)
        self.assertIn("0x5128d8u", observer)
        self.assertIn("0x5128dau", observer)
        self.assertIn("DMCU_MATRIX_COMPLETION_TRACE_STACK_WORDS", observer)
        self.assertNotIn("internal_data_write", observer)
        self.assertNotIn("address_space_st", observer)
        self.assertNotIn("env->pc =", observer)
        self.assertIn("KEY_COMPLETION_TRACE=COUNT:%u TRACE:", machine)

    def test_sound_settings_route_trace_is_bounded_and_read_only(
        self,
    ) -> None:
        header = CPU_HEADER.read_text(encoding="utf-8")
        helper = HELPER.read_text(encoding="utf-8")
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn("DMCU_SOUND_SETTINGS_TRACE_SLOTS 64", header)
        self.assertIn("sound_settings_trace_selection", header)
        self.assertIn("sound_settings_trace_switch_state", header)
        start = helper.index(
            "Retain decisive instruction checkpoints for the state-0x55"
        )
        end = helper.index(
            "The exact 32:F3C6 application initializer", start
        )
        observer = helper[start:end]
        for address in (
            "0x1df78au",
            "0x1df816u",
            "0x2fc59au",
            "0x2fc652u",
            "0x2fc698u",
            "0x31345eu",
            "0x3134d8u",
            "0x3134eeu",
            "0x3134f0u",
            "0x313510u",
            "0x2edb9cu",
            "0x0f3906u",
            "0x0f3932u",
            "0x0f3936u",
            "0x15f0eeu",
            "0x15f2ceu",
            "0x15f2d0u",
            "0x15f2d6u",
            "0x15f2dau",
            "0x15f2dcu",
            "0x15f2e0u",
            "0x15f2e6u",
            "0x15f2eau",
            "0x15f2eeu",
            "0x15f2fau",
            "0x15f306u",
            "0x15f30au",
            "0x15f31au",
            "0x15f31eu",
            "0x15f326u",
            "0x15f32cu",
            "0x15f35cu",
            "0x15f360u",
            "0x15fe40u",
            "0x15fe4cu",
            "0x15fe50u",
            "0x15fe54u",
            "0x15fefau",
            "0x15f36eu",
            "0x15f556u",
            "0x15f73au",
            "0x15f8aau",
            "0x15fb8au",
            "0x15fa1au",
            "0x14b768u",
            "0x14b772u",
            "0x14b816u",
            "0x14b868u",
            "0x14b8e0u",
            "0x14b92eu",
            "0x14b930u",
            "0x14b932u",
            "0x14ba5cu",
            "0x14babau",
            "0x14bb28u",
            "0x14bb74u",
            "0x14bd58u",
            "0x14bda4u",
            "0x15fceau",
            "0x32ebaeu",
            "0x19c876u",
            "0x19ca3eu",
            "0x19cc2eu",
            "0x19cc38u",
            "0x19cc3cu",
            "0x19cc54u",
            "0x19cc74u",
            "0x19cc78u",
            "0x19cc94u",
            "0x1ba454u",
            "0x1ba46cu",
            "0x1bac7au",
            "0x1bacbeu",
        ):
            self.assertIn(address, observer)
        for physical in (
            "0x507e38u ^ 1u",
            "0x52573eu ^ 1u",
            "0x525674u ^ 1u",
            "0x5256acu ^ 1u",
            "0x5256c0u ^ 1u",
            "0x52568cu ^ 1u",
            "0x52567eu ^ 1u",
        ):
            self.assertIn(physical, observer)
        self.assertIn(
            "sequence % DMCU_SOUND_SETTINGS_TRACE_SLOTS", observer
        )
        self.assertNotIn("internal_data_write", observer)
        self.assertNotIn("address_space_st", observer)
        self.assertNotIn("env->pc =", observer)

        edge_start = helper.index(
            "Preserve the non-idle control edges through every currently"
        )
        edge_end = helper.index("Source 42:206E is installed", edge_start)
        edge_observer = helper[edge_start:edge_end]
        for edge in (
            "(from & MASK24) == 0x1ef886u",
            "target == 0x15f0eeu",
            "(from & MASK24) == 0x15f360u",
            "(from & MASK24) == 0x14b930u",
            "(from & MASK24) == 0x14babau",
            "(from & MASK24) == 0x14bb74u",
            "(from & MASK24) == 0x14bda4u",
            "(from & MASK24) == 0x15fceau",
            "target == 0x32ebaeu",
            "(from & MASK24) == 0x0f3932u",
            "target == 0x25206eu",
            "(from & MASK24) == 0x2fc652u",
            "target == 0x31345eu",
            "(from & MASK24) == 0x313510u",
            "target == 0x2edb9cu",
            "(from & MASK24) == 0x19cc78u",
            "(from & MASK24) == 0x19cc94u",
            "target == 0x1ba454u",
            "(from & MASK24) == 0x1ba46cu",
            "target == 0x32d016u",
            "(from & MASK24) == 0x1ba6bau",
            "(from & MASK24) == 0x1bacbeu",
        ):
            self.assertIn(edge, edge_observer)
        self.assertIn("sound_settings_trace_target", edge_observer)
        self.assertIn("sound_settings_trace_return_cs", edge_observer)
        self.assertIn("sound_settings_trace_return_pc", edge_observer)
        self.assertNotIn("internal_data_write", edge_observer)
        self.assertNotIn("address_space_st", edge_observer)
        self.assertNotIn("env->pc =", edge_observer)
        self.assertIn("SOUND_SETTINGS_TRACE=COUNT:%u TRACE:", machine)


if __name__ == "__main__":
    unittest.main()
