#!/usr/bin/env python3
"""Source contracts for the bounded v752 NPE format-dispatch observer."""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import build_np560_reconstructed_rom as rom  # noqa: E402


HELPER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "helper.c"
CPU_HEADER = ROOT / "qemu-dmcu" / "target" / "dmcu" / "cpu.h"
MACHINE = ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"


class NpeFormatDispatchObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.helper = HELPER.read_text(encoding="utf-8")
        cls.cpu_header = CPU_HEADER.read_text(encoding="utf-8")
        cls.machine = MACHINE.read_text(encoding="utf-8")
        observer_start = cls.helper.index(
            "static void trace_npe_format_dispatch"
        )
        observer_end = cls.helper.index(
            "static void trace_control_transfer", observer_start
        )
        cls.observer = cls.helper[observer_start:observer_end]
        literal_start = cls.helper.index(
            "static inline void trace_npe_literal_data_access"
        )
        literal_end = cls.helper.index(
            "static inline uint32_t translated_data_read", literal_start
        )
        cls.literal_observer = cls.helper[literal_start:literal_end]
        memory_start = cls.helper.index(
            "static void trace_npe_loader_memory_call"
        )
        memory_end = cls.helper.index("\nenum {", memory_start)
        cls.memory_observer = cls.helper[memory_start:memory_end]

    def test_observer_is_fixed_size_and_time_bounds_the_followup(self) -> None:
        self.assertIn("#define DMCU_NPE_FORMAT_MEMCMP_SLOTS 3",
                      self.cpu_header)
        self.assertIn("#define DMCU_NPE_FORMAT_SAMPLE_BYTES 16",
                      self.cpu_header)
        self.assertIn(
            "#define DMCU_NPE_FORMAT_FOLLOWUP_MAX_STEPS 256",
            self.cpu_header,
        )
        self.assertNotIn("g_malloc", self.observer)
        self.assertNotIn("g_realloc", self.observer)
        self.assertNotIn("qemu_log", self.observer)
        self.assertIn("--env->npe_format_dispatch_followup_steps",
                      self.observer)

    def test_observer_covers_every_exact_v752_checkpoint(self) -> None:
        for address in (
            "0x1b7a20u",  # dispatcher entry
            "0x1b7aa2u",  # record-accessor call
            "0x5f380au",  # relocated accessor entry
            "0x5f382au",  # relocated accessor RETS
            "0x1b7aa6u",  # accessor return continuation
            "0x1b7b2au",  # first memcmp return
            "0x1b7b56u",  # second memcmp return
            "0x1b7b82u",  # third/7B7E memcmp return
            "0x066b4cu",  # first memcmp tail after literal installation
            "0x1b7b52u",  # second memcmp call
            "0x1b7b7eu",  # third memcmp call
            "0x2cc07eu",  # exact compare target
            "0x1b7baeu",  # status = 2 site
            "0x1b8294u",  # dispatcher RETS
            "0x2fb6deu",  # router continuation
            "0x2fb726u",  # mode-2 call site
            "0x1fd1a6u",  # exact mode-2 controller
            "0x530020u",
            "0x530024u",
            "0x530028u",
            "0x1b7e8au",
            "0x1b7ea2u",
        ):
            self.assertIn(address, self.observer)

        self.assertIn("env->npe_format_status_value == 2u", self.observer)
        self.assertIn("env->npe_format_memcmp_result[slot]", self.observer)
        self.assertIn("env->gpr[DMCU_SP] + 4u", self.observer)
        self.assertIn("trace_userinfo_descriptor_byte(", self.observer)

    def test_observer_never_mutates_guest_architectural_state(self) -> None:
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

    def test_observer_is_called_once_from_post_instruction_transfer_trace(
        self,
    ) -> None:
        self.assertEqual(
            self.helper.count(
                "trace_npe_format_dispatch(env, from, target, sequential);"
            ),
            1,
        )
        call = self.helper.index(
            "trace_npe_format_dispatch(env, from, target, sequential);"
        )
        transfer = self.helper.rfind(
            "static void trace_control_transfer", 0, call
        )
        self.assertNotEqual(transfer, -1)
        self.assertLess(
            self.helper.index("uint32_t target = env->pc & MASK24;", transfer),
            call,
        )

    def test_diagnostics_expose_results_and_hero_legacy_zero_contract(
        self,
    ) -> None:
        for label in (
            "NPE_FORMAT_DISPATCH=ACTIVE:%u",
            "FIELD_7AA2_380A_7AA6:%u/%u/r%04x",
            "MEMCMP:7B2A=%u/r%04x,7B56=%u/r%04x,7B82=%u/r%04x",
            "STATUS_7BAE:%u/is2:%u/r%04x",
            "RETURN_8294:%u/r%04x/to%02x:%04x",
            "B6DE:%u/r%04x B726_D1A6:%u",
            "LEGACY_53:%u/%u/%u LEGACY_1B:%u/%u",
            " NPE_FORMAT_ARGS=",
            "/%c",
        ):
            self.assertIn(label, self.machine)

        # Each new invocation clears the five legacy counters, so a Hero
        # dispatch can be asserted as 0/0/0 and 0/0 without stale history.
        self.assertIn(
            "memset(env->npe_format_legacy_service_calls, 0,", self.observer
        )
        self.assertIn(
            "memset(env->npe_format_legacy_path_calls, 0,", self.observer
        )

    def test_v752_installed_words_match_the_observed_edges(self) -> None:
        words = rom.resident_operation_1b7a20_words()

        def installed(live_address: int, count: int = 1) -> list[int]:
            offset = (
                live_address - rom.RESIDENT_OPERATION_1B7A20_ADDRESS
            ) // 2
            return words[offset:offset + count]

        self.assertEqual(installed(0x1B7A20), [0x2E21])
        self.assertEqual(installed(0x1B7AA2, 2), [0xBD5F, 0x380A])
        self.assertEqual(installed(0x1B7E8A, 2), [0xBD5F, 0x6A9C])
        self.assertEqual(installed(0x1B7EA2, 2), [0xBD5F, 0x1BBA])
        self.assertEqual(installed(0x1B7BAE), [0x4802])
        self.assertEqual(installed(0x1B8294), [rom.RETS])

        for source in (0x387B26, 0x387B52, 0x387B7E):
            self.assertEqual(
                rom.program_source_words(source, 4), [0xBD2C, 0xC07E]
            )
        self.assertEqual(
            rom.program_source_words(0x50382A, 2), [rom.RETS]
        )
        self.assertEqual(
            rom.program_source_words(0x4CB6DA, 4), [0xBD1B, 0x7A20]
        )
        self.assertEqual(rom.program_source_words(0x4CB6DE, 2), [0x50F4])
        self.assertEqual(
            rom.program_source_words(0x4CB726, 4), [0xBD1F, 0xD1A6]
        )

    def test_format_literal_source_matches_observed_arguments_and_data_window(
        self,
    ) -> None:
        words = rom.program_source_words(
            rom.APPLICATION_NPE_FORMAT_LITERAL_DATA_SOURCE,
            rom.APPLICATION_NPE_FORMAT_LITERAL_DATA_SIZE,
        )
        logical = b"".join(word.to_bytes(2, "big") for word in words)

        self.assertEqual(logical[0x00:0x09], b"NP560 RPG")
        self.assertEqual(logical[0x0A:0x16], b"NP580 Ver1.0")
        self.assertEqual(logical[0x18:0x24], b"NP560 Ver1.0")
        self.assertEqual(
            rom.APPLICATION_NPE_FORMAT_LITERAL_DATA_DESTINATION,
            0x324956,
        )
        self.assertIn(
            "NP560_APPLICATION_NPE_FORMAT_LITERAL_DATA_BASE", self.machine
        )
        self.assertIn(
            "np560.data-application-npe-format-literal-overlay-alias",
            self.machine,
        )
        self.assertIn(
            '"np560.data-application-npe-format-literal-overlay-alias",\n'
            "        NULL,",
            self.machine,
        )
        self.assertNotIn("np560.data-npe-format-literal-32-alias", self.machine)

    def test_literal_lifecycle_observer_is_bounded_and_read_only(self) -> None:
        self.assertIn(
            "#define DMCU_NPE_LITERAL_DATA_TRACE_SLOTS 64", self.cpu_header
        )
        self.assertIn("physical >= 0x32497cu", self.literal_observer)
        self.assertIn("physical + width <= 0x324956u", self.literal_observer)
        self.assertEqual(
            self.helper.count(
                "trace_npe_literal_data_access(env, addr, "
            ),
            2,
        )
        for mutator in (
            "internal_data_write",
            "address_space_st",
            "address_space_write",
            "cpu_physical_memory_write",
            "reg_write",
            "set_flag",
            "tlb_flush",
        ):
            self.assertNotIn(mutator, self.literal_observer)
        self.assertIn(
            "NPE_LITERAL_DATA=READS:%u WRITES:%u DISPATCH_DELTA:%u/%u",
            self.machine,
        )
        self.assertIn("LITERAL_WRAP:%u/%u/%u/%u", self.machine)

    def test_npe_loader_memory_observer_has_independent_bounded_rings(
        self,
    ) -> None:
        for declaration in (
            "#define DMCU_NPE_FILE_READ_TRACE_SLOTS 64",
            "#define DMCU_NPE_FAR_COPY_TRACE_SLOTS 64",
        ):
            self.assertIn(declaration, self.cpu_header)
        self.assertIn("!env->npe_modal_control_trace_pending", self.memory_observer)
        self.assertIn("!env->npe_glyph_trace_armed", self.memory_observer)
        self.assertIn("dmcu_code_address(0x2d, 0x261c)", self.memory_observer)
        self.assertIn("dmcu_code_address(0x2e, 0x4572)", self.memory_observer)
        self.assertNotIn("resource_io_trace_frozen", self.memory_observer)
        self.assertIn("env->npe_far_copy_trace_count = 0;", self.helper)
        self.assertIn("NPE_FILE_READ=COUNT:%u TRACE:", self.machine)
        self.assertIn("NPE_FAR_COPY=COUNT:%u TRACE:", self.machine)

    def test_npe_loader_memory_observer_is_read_only(self) -> None:
        for mutator in (
            "internal_data_write",
            "address_space_st",
            "address_space_write",
            "cpu_physical_memory_write",
            "reg_write",
            "set_flag",
            "tlb_flush",
        ):
            self.assertNotIn(mutator, self.memory_observer)
        self.assertNotIn("env->pc =", self.memory_observer)
        self.assertNotIn("env->psw =", self.memory_observer)
        self.assertNotIn("env->gpr[", self.memory_observer.split("=", 1)[0])


if __name__ == "__main__":
    unittest.main()
