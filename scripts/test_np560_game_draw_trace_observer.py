from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CPU_HEADER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "cpu.h"
CPU_PARAM = ROOT / "qemu-dmcu" / "target" / "dmcu" / "cpu-param.h"
HELPER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "helper.c"
MACHINE = ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"


class GameDrawTraceObserverTest(unittest.TestCase):
    def test_map_observations_use_loader_map_not_event_range_state(self) -> None:
        helper = HELPER.read_text(encoding="utf-8")
        machine = MACHINE.read_text(encoding="utf-8")
        for text, name in (
            (machine, "game_current_map_index"),
            (helper, "env->npe_game_direction_before_map_index"),
            (helper, "env->npe_game_direction_after_map_index"),
        ):
            start = text.index(name + " = address_space_lduw_le(")
            observer = text[start:text.index(";", start)]
            self.assertIn("0x527a58u", observer)
            self.assertNotIn("0x527a66u", observer)

    def test_latest_draw_trace_is_bounded_read_only_and_reported(self) -> None:
        header = CPU_HEADER.read_text(encoding="utf-8")
        helper = HELPER.read_text(encoding="utf-8")
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn("DMCU_NPE_GAME_DRAW_CHILD_SITES 7", header)
        self.assertIn("DMCU_NPE_GAME_DRAW_TRACE_SLOTS 128", header)
        self.assertIn("bool npe_game_draw_trace_active;", header)
        self.assertIn("0xbc76, 0xbd40, 0xbd4e, 0xbdd2", helper)
        self.assertIn("0xbc7a, 0xbd44, 0xbd52, 0xbdd6", helper)
        self.assertIn(
            "env->npe_game_draw_trace_call = env->npe_game_draw_calls;",
            helper,
        )
        self.assertIn(
            "sequence % DMCU_NPE_GAME_DRAW_TRACE_SLOTS", helper
        )

        start = helper.index(
            "Retain only the most recent exact 29:BBF2 map draw"
        )
        end = helper.index(
            "if (game_target == dmcu_code_address(0x1d, 0x8ef4))", start
        )
        observer = helper[start:end]
        self.assertNotIn("internal_data_write", observer)
        self.assertNotIn("address_space_st", observer)
        self.assertNotIn("env->pc =", observer)

        self.assertIn(
            "NPE_GAME_DRAW_TRACE=ACTIVE:%u CALL:%u EDGES:%u CHILD:%u",
            machine,
        )

    def test_action_low51_execution_preserves_predecessor_trace(self) -> None:
        header = CPU_HEADER.read_text(encoding="utf-8")
        helper = HELPER.read_text(encoding="utf-8")
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn("DMCU_NPE_LOW51_EXEC_HISTORY_WORDS 32", header)
        self.assertIn("bool npe_low51_exec_valid;", header)
        self.assertIn(
            "modal_event == 0x0086u && env->npe_game_draw_calls > 0u",
            helper,
        )
        start = helper.index(
            "The low 51 bank contains the streamed NPE resource window"
        )
        observer = helper[start:start + 1800]
        self.assertIn("env->control_trace_frozen = true;", observer)
        self.assertNotIn("internal_data_write", observer)
        self.assertNotIn("address_space_st", observer)
        self.assertNotIn("env->pc =", observer)
        self.assertIn("NPE_LOW51_EXEC=%u PC:%02x:%04x", machine)

    def test_ui_initializer_reentry_freezes_predecessor_and_stack(self) -> None:
        header = CPU_HEADER.read_text(encoding="utf-8")
        helper = HELPER.read_text(encoding="utf-8")
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn("DMCU_NPE_UI_REENTRY_HISTORY_WORDS 32", header)
        self.assertIn("DMCU_NPE_UI_REENTRY_STACK_WORDS 16", header)
        self.assertIn("bool npe_game_ui_reentry_valid;", header)
        start = helper.index(
            "The first 29:D34E return has already consumed the only observed"
        )
        observer = helper[start:start + 2300]
        self.assertIn(
            "start >= dmcu_code_address(0x29, 0xd0ba)",
            helper[start - 900:start],
        )
        self.assertIn(
            "start < dmcu_code_address(0x29, 0xd34e)",
            helper[start - 700:start],
        )
        self.assertIn("env->control_trace_frozen = true;", observer)
        self.assertNotIn("internal_data_write", observer)
        self.assertNotIn("address_space_st", observer)
        self.assertNotIn("env->pc =", observer)
        self.assertIn("NPE_GAME_UI_REENTRY=%u PC:%02x:%04x", machine)

    def test_linked_loader_alias_escape_is_captured_before_ui_overlap(self) -> None:
        header = CPU_HEADER.read_text(encoding="utf-8")
        helper = HELPER.read_text(encoding="utf-8")
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn("bool npe_game_linked_loader_valid;", header)
        start = helper.index(
            "0C:BDBE owns the immutable loader copy"
        )
        observer = helper[start:start + 2200]
        condition = helper[start - 900:start]
        self.assertIn("env->npe_game_action_trace_armed", condition)
        self.assertIn(
            "start >= dmcu_code_address(0x29, 0xbdbe)", condition
        )
        self.assertIn(
            "start < dmcu_code_address(0x29, 0xd0ba)", condition
        )
        self.assertIn("env->control_trace_frozen = true;", observer)
        self.assertNotIn("internal_data_write", observer)
        self.assertNotIn("address_space_st", observer)
        self.assertNotIn("env->pc =", observer)
        self.assertIn("NPE_GAME_LINKED_LOADER=%u PC:%02x:%04x", machine)

    def test_operation_action_writer_ring_is_read_only_and_syncs_code(self) -> None:
        header = CPU_HEADER.read_text(encoding="utf-8")
        cpu_param = CPU_PARAM.read_text(encoding="utf-8")
        helper = HELPER.read_text(encoding="utf-8")
        machine = MACHINE.read_text(encoding="utf-8")

        self.assertIn(
            "DMCU_NPE_OPERATION_ONE_ACTION_WRITE_SLOTS 16", header
        )
        self.assertIn("#define TARGET_PAGE_BITS 11", cpu_param)
        self.assertIn(
            "#define TARGET_PHYS_ADDR_SPACE_BITS 25", cpu_param
        )
        self.assertIn("npe_operation_one_action_write_count;", header)
        start = helper.index(
            "The operation-one controller calls linked 29:CE22"
        )
        end = helper.index("The original 48:9178 initializer", start)
        observer = helper[start:end]
        self.assertIn("actual_physical < 0x29d0bau", observer)
        self.assertIn("actual_physical + bits / 8u > 0x29ce22u", observer)
        self.assertNotIn("internal_data_write", observer)
        self.assertNotIn("address_space_st", observer)
        self.assertNotIn("env->pc =", observer)
        self.assertIn(
            "NPE_OPERATION_ONE_ACTION_WRITES=COUNT:%u TRACE:", machine
        )
        self.assertIn(
            "NP560_APPLICATION_OPERATION_ONE_ACTION_OVERLAY_BASE "
            "0x0029ce22u",
            machine,
        )
        self.assertIn(
            "np560.code-application-operation-one-action-overlay-alias",
            machine,
        )
        self.assertIn(
            "NP560_APPLICATION_OPERATION_ACTION_UI_OVERLAY_SIZE",
            machine,
        )
        self.assertNotIn(
            "np560.code-application-operation-ui-init-overlay-alias",
            machine,
        )
        self.assertIn(
            "NP560_APPLICATION_EVENT_REGISTRY_OVERLAY_SIZE", machine
        )
        self.assertNotIn(
            "np560.code-application-post-registry-state-overlay-alias",
            machine,
        )
        self.assertIn("NP560_TIMER_IDLE_SET_BITS_OVERLAY_SIZE", machine)
        self.assertIn("NP560_TIMER_IDLE_CLEAR_BITS_OVERLAY_SIZE", machine)
        self.assertNotIn(
            "np560.code-timer-idle-set-bit1-relocated-overlay-alias",
            machine,
        )
        self.assertNotIn(
            "np560.code-timer-idle-clear-bit1-relocated-overlay-alias",
            machine,
        )
        exception = (
            "overlay->base !=\n"
            "                    "
            "NP560_APPLICATION_OPERATION_ONE_ACTION_OVERLAY_BASE"
        )
        self.assertNotIn(exception, machine)
        self.assertIn(
            "np560.application-operation-action-ui-ram", machine
        )
        self.assertIn(
            "NP560_APPLICATION_OPERATION_ACTION_CODE_PAGE_SIZE", machine
        )
        self.assertIn(
            "NP560_APPLICATION_OPERATION_ACTION_CODE_PAGE_BASE +\n"
            "                NP560_APPLICATION_OPERATION_ACTION_CODE_PAGE_OFFSET ==\n"
            "                NP560_APPLICATION_OPERATION_ONE_ACTION_OVERLAY_BASE",
            machine,
        )
        self.assertIn(
            "NP560_APPLICATION_OPERATION_ACTION_UI_TAIL_OFFSET +\n"
            "                NP560_APPLICATION_OPERATION_ACTION_UI_TAIL_SIZE ==\n"
            "                NP560_APPLICATION_OPERATION_ACTION_UI_OVERLAY_SIZE",
            machine,
        )
        self.assertIn(
            "np560.code-application-operation-action-ui-tail-alias",
            machine,
        )
        self.assertIn(
            "actual_physical < 0x29d000u", helper
        )
        self.assertIn(
            "cpu_get_address_space(\n            env_cpu(env), DMCU_AS_CODE)",
            helper,
        )

        sync_start = helper.index(
            "The dedicated 09:E000 operation installer publishes"
        )
        sync = helper[sync_start:sync_start + 1000]
        self.assertIn(
            "start == dmcu_code_address(0x09, 0xf4c0)", sync
        )
        self.assertIn("tb_flush(env_cpu(env));", sync)
        self.assertIn("tlb_flush(env_cpu(env));", sync)


if __name__ == "__main__":
    unittest.main()
