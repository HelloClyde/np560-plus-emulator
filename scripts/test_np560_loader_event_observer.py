#!/usr/bin/env python3
"""Source contracts for the status-2 NPE loader event observer."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "helper.c"
CPU_HEADER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "cpu.h"
MACHINE = ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"


class NpeLoaderEventObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.helper = HELPER.read_text(encoding="utf-8")
        cls.cpu_header = CPU_HEADER.read_text(encoding="utf-8")
        cls.machine = MACHINE.read_text(encoding="utf-8")
        start = cls.helper.index(
            "/* Observe the exact event boundary inside the status-2"
        )
        end = cls.helper.index(
            "/* After modal event 0x86 enters the exact 1E:F734 worker",
            start,
        )
        cls.observer = cls.helper[start:end]

    def test_exact_loader_event_and_branch_boundaries_are_observed(self) -> None:
        for address in (
            "dmcu_code_address(0x1f, 0xd5b2)",
            "dmcu_code_address(0x03, 0x4158)",
            "dmcu_code_address(0x1e, 0xfd7a)",
            "dmcu_code_address(0x1f, 0xd5b6)",
            "dmcu_code_address(0x1f, 0xd5ba)",
            "dmcu_code_address(0x1f, 0xd5c4)",
            "dmcu_code_address(0x1f, 0xd5d2)",
            "dmcu_code_address(0x1f, 0xd5e0)",
            "dmcu_code_address(0x1f, 0xd5e4)",
            "dmcu_code_address(0x1d, 0x5820)",
            "dmcu_code_address(0x1f, 0xd5e8)",
            "dmcu_code_address(0x25, 0x8392)",
            "dmcu_code_address(0x1f, 0xd5ec)",
            "dmcu_code_address(0x1f, 0xd71e)",
            "dmcu_code_address(0x1f, 0xd760)",
            "dmcu_code_address(0x2d, 0xf47c)",
            "dmcu_code_address(0x1f, 0xd772)",
        ):
            self.assertIn(address, self.observer)

    def test_snapshot_reads_the_two_caller_outputs_and_exact_globals(self) -> None:
        for expression in (
            "(fp - 8u) & MASK16",
            "(fp - 0x14u) & MASK16",
            "0x527934u",
            "0x527ac4u ^ 1u",
            "0x527a32u ^ 1u",
            "0x527a76u",
            "0x527a3cu",
            "0x512ae0u",
        ):
            self.assertIn(expression, self.observer)
        self.assertIn("bool key86 = env->npe_modal_control_trace_pending", self.observer)
        self.assertIn("if (result != 0u)", self.observer)
        self.assertIn("if (key86)", self.observer)
        self.assertIn("npe_loader_event_follow_active = true", self.observer)

    def test_observer_never_changes_guest_architectural_state(self) -> None:
        for mutator in (
            "internal_data_write",
            "address_space_st",
            "address_space_write",
            "cpu_physical_memory_write",
            "reg_write",
            "set_flag",
            "tlb_flush",
        ):
            self.assertNotIn(mutator, self.observer)
        for architectural_field in ("pc", "psw", "repeat_count"):
            self.assertIsNone(
                re.search(
                    rf"env->{architectural_field}\s*(?:\[[^]]+\])?\s*=",
                    self.observer,
                )
            )
        self.assertIsNone(
            re.search(r"env->(?:gpr|sfr)\s*\[[^]]+\]\s*=", self.observer)
        )
        self.assertIn(
            "no field below is consumed by guest execution", self.cpu_header
        )

    def test_loader_caller_does_not_replace_phase_two_with_modal_trace(self) -> None:
        self.assertIn(
            "target == dmcu_code_address(0x1f, 0xd5b6)", self.helper
        )
        self.assertIn(
            "env->npe_modal_control_trace_active = !loader_event_return",
            self.helper,
        )
        self.assertIn("if (!loader_event_return) {", self.helper)
        self.assertIn(
            "if (!env->npe_loader_event_watch_active) {", self.helper
        )

    def test_diagnostics_expose_event_snapshot_and_branch_milestones(self) -> None:
        for label in (
            "NPE_LOADER_EVENT=ACTIVE:%u FOLLOW:%u",
            "CALLS:%u RETURNS:%u/NZ:%u/K86:%u",
            "EVENT:r%04x/t%04x/c%04x",
            "GLOBAL:m%04x/f%02x/i%02x/s%04x",
            "PATH:z%u/t4%u/to%u/m1%u/mo%u/f0%u/fn%u",
            "PREP:%u INIT:%u/%u PROGRESS:%u SERVICE:%u EXIT:%u",
        ):
            self.assertIn(label, self.machine)

    def test_game_service_and_first_draw_closure_are_observed(self) -> None:
        for address in (
            "dmcu_code_address(0x2d, 0xf52a)",
            "dmcu_code_address(0x1d, 0x8a3a)",
            "dmcu_code_address(0x1d, 0x8eb6)",
            "dmcu_code_address(0x1d, 0x8ed4)",
            "dmcu_code_address(0x1d, 0x8ee2)",
            "dmcu_code_address(0x31, 0xb0b4)",
            "dmcu_code_address(0x29, 0xd0ba)",
            "dmcu_code_address(0x29, 0xd34e)",
            "dmcu_code_address(0x31, 0x4c66)",
            "dmcu_code_address(0x33, 0x2216)",
            "dmcu_code_address(0x2d, 0xf610)",
            "dmcu_code_address(0x1d, 0x5f56)",
            "dmcu_code_address(0x25, 0x8778)",
            "dmcu_code_address(0x23, 0x6c3c)",
            "dmcu_code_address(0x27, 0xe84c)",
            "dmcu_code_address(0x2e, 0x79fa)",
            "dmcu_code_address(0x29, 0xbbf2)",
            "dmcu_code_address(0x29, 0xbe8a)",
            "dmcu_code_address(0x2d, 0x908e)",
            "dmcu_code_address(0x5f, 0x0000)",
        ):
            self.assertIn(address, self.observer)
        for flag in ("0x527a7au ^ 1u", "0x527a7cu ^ 1u", "0x527a7eu ^ 1u"):
            self.assertIn(flag, self.observer)

    def test_game_frame_snapshots_are_read_only_and_bounded(self) -> None:
        snapshot_start = self.helper.index("static void snapshot_npe_game_frame")
        snapshot_end = self.helper.index("enum {\n    CLOCK_RESOURCE_RELEASE", snapshot_start)
        snapshot = self.helper[snapshot_start:snapshot_end]
        self.assertIn("DMCU_NATIVE_FRAMEBUFFER_BYTES", snapshot)
        self.assertIn("address_space_ldub", snapshot)
        self.assertIn("DMCU_NPE_GAME_FRAME_STAGES 12", self.cpu_header)
        for mutator in (
            "internal_data_write",
            "address_space_st",
            "address_space_write",
            "cpu_physical_memory_write",
        ):
            self.assertNotIn(mutator, snapshot)

    def test_diagnostics_expose_game_service_loop_and_frame_stages(self) -> None:
        for label in (
            "NPE_GAME_SERVICE=ARMED:%u DISPATCH:%u HANDLER:%u/%u",
            "MEM:%u/%u UIINIT:%u/%u SYNC:%u/%u STATE:%u/%u",
            "NPE_GAME_LOOP=GRID:%u/%u INIT:%u/%u RANGE:%u RAND:%u",
            "CMP:%u DRAW:%u/%u ITEM:%u STATEDISP:%u",
            "NPE_GAME_FRAME=VALID:%03x",
            "NPE_GAME_BRANCH=COUNT:%u TRACE:",
            "NPE_GAME_DATA=COUNT:%u TRACE:",
            "NPE_GAME_STATE=LIVE:%02x WRITES:%u/C%u/NZ%u",
            "CALLBACK:%u/Z%u/O%u/X%u/S%02x",
        ):
            self.assertIn(label, self.machine)

    def test_game_ui_initializer_return_abi_is_observed_only(self) -> None:
        self.assertIn("npe_game_ui_init_rets_target", self.cpu_header)
        observer_start = self.observer.index(
            "game_pc == dmcu_code_address(0x1d, 0x8ef0)"
        )
        observer = self.observer[observer_start:]
        for evidence in (
            "dmcu_code_address(0x29, 0xd34e)",
            "npe_game_ui_init_rets_target = game_target",
            "dmcu_code_address(0x1d, 0x8ef4)",
            "npe_game_ui_init_continuation_from = game_pc",
            "internal_data_read((post_sp + index * 2u) & MASK16, 16)",
            "internal_data_read((sp + index * 2u) & MASK16, 16)",
        ):
            self.assertIn(evidence, observer)
        for mutator in (
            "internal_data_write",
            "address_space_st",
            "address_space_write",
            "cpu_physical_memory_write",
        ):
            self.assertNotIn(mutator, observer)
        self.assertIn("NPE_GAME_UI_RETURN=CALL:%u", self.machine)

    def test_game_ui_overlay_lifecycle_is_monotonic_and_observer_only(self) -> None:
        for field in (
            "npe_game_ui_lifecycle_sequence",
            "npe_game_ui_wrapper_8a5c_sequence",
            "npe_game_ui_wrapper_9140_sequence",
            "npe_game_ui_publisher_return_sequence",
            "npe_game_ui_init_call_sequence",
            "npe_game_ui_e15a_call_sequence",
            "npe_game_ui_e15a_return_sequence",
            "npe_game_ui_6ab8_call_sequence",
            "npe_game_ui_6ab8_return_sequence",
            "npe_game_ui_5c22_call_sequence",
            "npe_game_ui_5c22_return_sequence",
        ):
            self.assertIn(field, self.cpu_header)
        for edge in (
            "dmcu_code_address(0x1d, 0x8a5c)",
            "dmcu_code_address(0x1d, 0x9140)",
            "dmcu_code_address(0x06, 0x6b80)",
            "dmcu_code_address(0x06, 0x6fb2)",
            "dmcu_code_address(0x1a, 0x7600)",
            "dmcu_code_address(0x1a, 0x78ec)",
            "dmcu_code_address(0x06, 0x6fb6)",
            "dmcu_code_address(0x06, 0x6fee)",
            "dmcu_code_address(0x2b, 0x0da2)",
            "dmcu_code_address(0x29, 0xd2d8)",
            "dmcu_code_address(0x2f, 0xe15a)",
            "dmcu_code_address(0x2f, 0xe27e)",
            "dmcu_code_address(0x29, 0xd2dc)",
            "dmcu_code_address(0x29, 0xd2f4)",
            "dmcu_code_address(0x2f, 0x6ab8)",
            "dmcu_code_address(0x2f, 0x6bf8)",
            "dmcu_code_address(0x29, 0xd2f8)",
            "dmcu_code_address(0x2f, 0x6ac2)",
            "dmcu_code_address(0x29, 0x5c22)",
            "dmcu_code_address(0x29, 0x5edc)",
            "dmcu_code_address(0x2f, 0x6ac6)",
        ):
            self.assertIn(edge, self.observer)
        lifecycle_start = self.observer.index(
            "A compact closure monitor for the exact 46:5C22"
        )
        lifecycle_end = self.observer.index(
            "Operation one is the post-0x86 transition", lifecycle_start
        )
        lifecycle = self.observer[lifecycle_start:lifecycle_end]
        for mutator in (
            "internal_data_write",
            "address_space_st",
            "address_space_write",
            "cpu_physical_memory_write",
            "tlb_flush",
            "tb_flush",
        ):
            self.assertNotIn(mutator, lifecycle)
        self.assertIn("NPE_GAME_UI_LIFECYCLE=SEQ:%u", self.machine)
        for field in (
            "npe_game_frame_clear_child_calls",
            "npe_game_frame_clear_child_targets",
            "npe_game_frame_clear_child_continuations",
            "npe_game_frame_clear_child_continuation_from",
        ):
            self.assertIn(field, self.cpu_header)
        for pc in (
            "0x5c78", "0x5c92", "0x5d4a", "0x5d84",
            "0x5db6", "0x5e58", "0x5eb4", "0x5ec4",
            "0x5c7c", "0x5c96", "0x5d4e", "0x5d88",
            "0x5dba", "0x5e5c", "0x5eb8", "0x5ec8",
        ):
            self.assertIn(pc, self.observer)
        self.assertIn("NPE_GAME_FRAME_CLEAR=", self.machine)
        self.assertIn(
            "NP560_APPLICATION_OPERATION_NEW_JOURNEY_FRAME_INIT_OVERLAY_BASE",
            self.machine,
        )
        self.assertIn("0x002f6ab8u", self.machine)
        self.assertIn("0x0142u", self.machine)
        self.assertIn(
            "np560.code-application-operation-new-journey-frame-init-overlay-alias",
            self.machine,
        )
        self.assertIn("NP560_APPLICATION_OPERATION_FRAME_CLEAR_OVERLAY_BASE", self.machine)
        self.assertIn("0x00295c22u", self.machine)
        self.assertIn("0x02bcu", self.machine)
        self.assertIn(
            "np560.code-application-operation-frame-clear-overlay-alias",
            self.machine,
        )
        self.assertIn(
            "NP560_APPLICATION_OPERATION_FRAME_CLEAR_DRAW_HELPER_OVERLAY_BASE",
            self.machine,
        )
        self.assertIn("0x00307b8cu", self.machine)
        self.assertIn("0x00fcu", self.machine)
        self.assertIn(
            "np560.code-application-operation-frame-clear-draw-helper-overlay-alias",
            self.machine,
        )
        for field in (
            "npe_game_transition_service_calls",
            "npe_game_transition_service_entries",
            "npe_game_transition_service_returns",
            "npe_game_transition_service_continuation_from",
            "npe_game_transition_service_child_calls",
            "npe_game_transition_service_child_returns",
            "npe_game_transition_service_leaf_calls",
            "npe_game_transition_service_leaf_returns",
        ):
            self.assertIn(field, self.cpu_header)
        for edge in (
            "dmcu_code_address(0x31, 0xa480)",
            "dmcu_code_address(0x03, 0x438c)",
            "dmcu_code_address(0x32, 0x5f86)",
            "dmcu_code_address(0x32, 0x5ff2)",
            "dmcu_code_address(0x31, 0xa484)",
            "dmcu_code_address(0x32, 0x5fe6)",
            "dmcu_code_address(0x32, 0xb974)",
            "dmcu_code_address(0x32, 0xb9c4)",
            "dmcu_code_address(0x32, 0x5fea)",
            "dmcu_code_address(0x32, 0xb9b8)",
            "dmcu_code_address(0x25, 0x0000)",
            "dmcu_code_address(0x25, 0x0410)",
            "dmcu_code_address(0x32, 0xb9bc)",
        ):
            self.assertIn(edge, self.observer)
        self.assertIn("NPE_GAME_TRANSITION_SERVICE=CALL:%u", self.machine)
        self.assertIn(
            "NP560_APPLICATION_OPERATION_TRANSITION_SERVICE_OVERLAY_BASE",
            self.machine,
        )
        self.assertIn("0x00325f86u", self.machine)
        self.assertIn("0x006eu", self.machine)
        self.assertIn(
            "np560.code-application-operation-transition-service-overlay-alias",
            self.machine,
        )
        self.assertIn(
            "NP560_APPLICATION_OPERATION_TRANSITION_SERVICE_CHILD_OVERLAY_BASE",
            self.machine,
        )
        self.assertIn("0x0032b974u", self.machine)
        self.assertIn("0x0052u", self.machine)
        self.assertIn(
            "np560.code-application-operation-transition-service-child-overlay-alias",
            self.machine,
        )
        self.assertIn(
            "NP560_APPLICATION_OPERATION_TRANSITION_SERVICE_LEAF_OVERLAY_BASE",
            self.machine,
        )
        self.assertIn("0x00250000u", self.machine)
        self.assertIn("0x0412u", self.machine)
        self.assertIn(
            "np560.code-application-operation-transition-service-leaf-overlay-alias",
            self.machine,
        )

    def test_game_state_writer_and_dynamic_callback_are_observed_only(self) -> None:
        state_start = self.helper.index(
            "static inline void trace_npe_game_state_write"
        )
        state_end = self.helper.index(
            "/* Observe every write to the seven-word game grid/state block",
            state_start,
        )
        state_observer = self.helper[state_start:state_end]
        self.assertIn("0x527a3eu", state_observer)
        self.assertIn("physical + width <= state_start", state_observer)
        self.assertIn("npe_game_state_first_nonzero_pc", state_observer)
        self.assertIn("trace_npe_game_state_write(env, addr", self.helper)
        for mutator in (
            "internal_data_write",
            "address_space_st",
            "address_space_write",
            "cpu_physical_memory_write",
        ):
            self.assertNotIn(mutator, state_observer)
        for edge in (
            "dmcu_code_address(0x2d, 0x2dc0)",
            "dmcu_code_address(0x00, 0x1002)",
            "dmcu_code_address(0x00, 0x100c)",
            "dmcu_code_address(0x00, 0x56fa)",
            "dmcu_code_address(0x00, 0x1010)",
        ):
            self.assertIn(edge, self.observer)

    def test_operation_one_gate_and_boot_writes_are_observed_only(self) -> None:
        control_start = self.helper.index(
            "static inline void trace_npe_game_control_write"
        )
        control_end = self.helper.index(
            "/* Observe every write to the seven-word game grid/state block",
            control_start,
        )
        control_observer = self.helper[control_start:control_end]
        for address in ("0x527934u", "0x527a50u", "0x527ab4u"):
            self.assertIn(address, control_observer)
        self.assertIn(
            "DMCU_NPE_GAME_CONTROL_WRITE_SLOTS 64", self.cpu_header
        )
        self.assertIn(
            "trace_npe_game_control_write(env, addr", self.helper
        )
        self.assertNotIn(
            "npe_game_control_write_count = 0", self.helper
        )
        for mutator in (
            "internal_data_write",
            "address_space_st",
            "address_space_write",
            "cpu_physical_memory_write",
        ):
            self.assertNotIn(mutator, control_observer)
        for edge in (
            "dmcu_code_address(0x2d, 0xf4c8)",
            "dmcu_code_address(0x2d, 0xf4fa)",
            "dmcu_code_address(0x1a, 0x1312)",
            "dmcu_code_address(0x1a, 0x1340)",
            "dmcu_code_address(0x31, 0xa3f4)",
            "dmcu_code_address(0x31, 0xa742)",
            "dmcu_code_address(0x1a, 0x1366)",
            "dmcu_code_address(0x2f, 0x6ab8)",
            "dmcu_code_address(0x1a, 0x1c90)",
        ):
            self.assertIn(edge, self.observer)
        for label in (
            "NPE_GAME_CONTROL=LIVE:m%04x/g%04x/t%04x",
            "OP1:%u/%u/F%u/R%u/N%u/I%u/X%u WRITES:%u TRACE:",
        ):
            self.assertIn(label, self.machine)

    def test_game_draw_boundary_and_dynamic_data_reads_are_read_only(self) -> None:
        self.assertIn("DMCU_NPE_GAME_BRANCH_TRACE_SLOTS 16", self.cpu_header)
        self.assertIn("DMCU_NPE_GAME_DATA_TRACE_SLOTS 64", self.cpu_header)
        self.assertIn(
            "DMCU_NPE_GAME_DATA_WRITE_TRACE_SLOTS 128", self.cpu_header
        )
        self.assertIn("dmcu_code_address(0x1f, 0xd674)", self.observer)
        self.assertIn("(fp - 9u) & MASK16", self.observer)
        self.assertIn("0x526ca2u + record * 14u", self.observer)
        self.assertIn("0x52783au + record * 2u", self.observer)
        read_start = self.helper.index(
            "static inline void trace_npe_game_data_read"
        )
        read_end = self.helper.index(
            "static inline uint32_t translated_data_read", read_start
        )
        read_trace = self.helper[read_start:read_end]
        for address in ("0x334874u", "0x3355beu", "0x31f122u"):
            self.assertIn(address, read_trace)
        for mutator in (
            "internal_data_write",
            "address_space_st",
            "address_space_write",
            "cpu_physical_memory_write",
        ):
            self.assertNotIn(mutator, read_trace)

        write_start = self.helper.index(
            "static inline int trace_npe_game_data_write_begin"
        )
        write_end = self.helper.index(
            "static inline uint32_t translated_data_read", write_start
        )
        write_trace = self.helper[write_start:write_end]
        for address in (
            "0x334874u",
            "0x334884u",
            "0x3355beu",
            "0x335625u",
            "0x31f122u",
            "0x31f12au",
        ):
            self.assertIn(address, write_trace)
        for mutator in (
            "internal_data_write",
            "address_space_st",
            "address_space_write",
            "cpu_physical_memory_write",
            "cpu_stb_data",
            "cpu_stw_data",
        ):
            self.assertNotIn(mutator, write_trace)
        self.assertIn("address_space_ldub", write_trace)
        self.assertIn("address_space_lduw_le", write_trace)
        begin_call = self.helper.index(
            "npe_game_data_write_slot = trace_npe_game_data_write_begin("
        )
        store = self.helper.index("cpu_stb_data(env, backing_addr, value)")
        end_call = self.helper.index(
            "trace_npe_game_data_write_end(env, npe_game_data_write_slot"
        )
        self.assertLess(begin_call, store)
        self.assertLess(store, end_call)
        self.assertIn("NPE_GAME_DATA_WRITE=COUNT:%u TRACE:", self.machine)

    def test_game_table_loader_and_stream_io_are_read_only_observers(self) -> None:
        for address in (
            "dmcu_code_address(0x29, 0xd284)",
            "dmcu_code_address(0x0c, 0xbdbe)",
            "dmcu_code_address(0x0c, 0xf256)",
            "dmcu_code_address(0x29, 0xd288)",
            "dmcu_code_address(0x03, 0x401c)",
            "dmcu_code_address(0x30, 0xc99c)",
            "dmcu_code_address(0x03, 0x4010)",
            "dmcu_code_address(0x33, 0x04b2)",
            "dmcu_code_address(0x1c, 0xccd4)",
            "dmcu_code_address(0x33, 0x04b6)",
            "dmcu_code_address(0x33, 0x04be)",
        ):
            self.assertIn(address, self.observer)
        self.assertIn("game_pc >= dmcu_code_address(0x0c, 0xbdbe)", self.observer)
        self.assertIn("game_pc <= dmcu_code_address(0x0c, 0xf256)", self.observer)
        self.assertIn("0x526ca2u", self.helper)
        self.assertIn("20u * 14u", self.helper)
        self.assertIn("DMCU_NPE_GAME_TABLE_IO_SLOTS 16", self.cpu_header)
        self.assertIn("DMCU_NPE_GAME_TABLE_COPY_SLOTS 256", self.cpu_header)
        self.assertIn(
            "DMCU_NPE_GAME_TABLE_COPY_SAMPLE_BYTES 8", self.cpu_header
        )
        self.assertIn("DMCU_NPE_GAME_GRID_WRITE_SLOTS 32", self.cpu_header)
        self.assertIn("DMCU_NPE_GAME_LOADER_EDGE_SLOTS 64", self.cpu_header)
        self.assertIn("no field below is consumed by guest", self.cpu_header)
        table_trace_start = self.helper.index(
            "static inline void trace_npe_game_table_write"
        )
        table_trace_end = self.helper.index(
            "static inline uint32_t translated_data_read", table_trace_start
        )
        table_trace = self.helper[table_trace_start:table_trace_end]
        for mutator in (
            "internal_data_write",
            "address_space_st",
            "address_space_write",
            "cpu_physical_memory_write",
        ):
            self.assertNotIn(mutator, table_trace)

        memory_trace_start = self.helper.index(
            "static void trace_npe_loader_memory_call"
        )
        memory_trace_end = self.helper.index(
            "enum {\n    USERINFO_FLOW_FALLBACK_ENTRY", memory_trace_start
        )
        memory_trace = self.helper[memory_trace_start:memory_trace_end]
        self.assertIn("npe_game_table_copy_count++", memory_trace)
        self.assertIn("destination + length > table_start", memory_trace)
        self.assertIn("const uint32_t grid_start = 0x52783au", memory_trace)
        self.assertIn("destination + length > grid_start", memory_trace)
        self.assertIn("npe_game_table_copy_stream_position", memory_trace)
        self.assertIn("npe_game_table_copy_cache_position", memory_trace)
        self.assertIn("address_space_ldub", memory_trace)
        self.assertIn("((source + sample) & MASK24) ^ 1u", memory_trace)
        for mutator in (
            "internal_data_write",
            "address_space_st",
            "address_space_write",
            "cpu_physical_memory_write",
        ):
            self.assertNotIn(mutator, memory_trace)
        self.assertIn(
            "game_pc == dmcu_code_address(0x0c, 0xd06a)", self.observer
        )
        self.assertIn("npe_game_grid_count_io_position", self.observer)
        self.assertIn("npe_game_grid_count_io_value", self.observer)

    def test_diagnostics_expose_game_table_live_state_and_io_trace(self) -> None:
        for label in (
            "NPE_GAME_TABLE=LIVE:%u/%08x LOADER:%u/%u/A%u/",
            "STREAM:%u/%u/A%u/M%u:%u/T%u WRITES:%u/C%u/NZ%u",
            "FIRST:%u@%02x:%04x/a%06x/%04x>%04x/b%u",
            "FIRSTNZ:%u@%02x:%04x/a%06x/%04x>%04x/b%u",
            "m%02x:%04x/r%04x:%04x/e%04x/w%u%s",
            "NPE_GAME_TABLE_COPY=COUNT:%u TRACE:",
            "NPE_GAME_GRID_WRITE=COUNT:%u TRACE:",
            "NPE_GAME_GRID_COUNT=CALLS:%u/%u/A%u/",
            "#%u/%02x:%04x/d%06x/s%06x/n%08x/",
            "p%08x/c%08x/",
            "NPE_GAME_LOADER_FLOW=LAST:%02x:%04x>%02x:%04x/",
            "RESOLVE:%u/%u/A%u/",
            "EDGES:%u TRACE:",
            "#%u/%02x:%04x>%02x:%04x/w%04x/sp%04x/fp%04x%s",
        ):
            self.assertIn(label, self.machine)


if __name__ == "__main__":
    unittest.main()
