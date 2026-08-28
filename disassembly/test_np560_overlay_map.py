#!/usr/bin/env python3
"""Tests for the reconstructed/QEMU overlay preflight map."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from disassembly.np560_overlay_map import (  # noqa: E402
    QemuMapping,
    OverlaySpec,
    collect_builder_overlays,
    covering_mapping,
    missing_mappings,
    parse_defines,
    parse_qemu_mappings,
    overlapping_overlays,
    resolve_address,
)


SAMPLE = r'''
#define CODE_BASE 0x00201234u
#define CODE_SIZE 0x20u
#define DATA_BASE 0x00305678u
#define DATA_SIZE (2u * 8u)
static const NP560ProgramOverlay np560_late_overlays[] = {
    { CODE_BASE, CODE_SIZE, "data-code", "code-code" },
    { DATA_BASE, DATA_SIZE, "data-only", NULL },
};
static const NP560FixedDataAlias fixed_data[] = {
    { 0x002bff80u, 0x0048ff80u, 0x80u, "nwf-format" },
};
'''


class OverlayMapTests(unittest.TestCase):
    def test_parses_integer_macros_and_code_role(self) -> None:
        self.assertEqual(parse_defines(SAMPLE)["DATA_SIZE"], 16)
        mappings = parse_qemu_mappings(SAMPLE)
        self.assertEqual(len(mappings), 3)
        self.assertTrue(next(item for item in mappings
                             if item.base == 0x201234).code)
        self.assertFalse(next(item for item in mappings
                              if item.base == 0x305678).code)
        self.assertFalse(next(item for item in mappings
                              if item.base == 0x2BFF80).code)

    def test_fixed_data_alias_satisfies_only_data_overlay(self) -> None:
        mappings = parse_qemu_mappings(SAMPLE)
        data = OverlaySpec(0x2BFF80, 0x80, "NWF_DATA", 0x48FF80, "data")
        code = OverlaySpec(0x2BFF80, 0x80, "NWF_CODE", 0x48FF80, "code")
        self.assertEqual(missing_mappings([data], mappings), [])
        self.assertEqual(missing_mappings([code], mappings), [code])

    def test_data_alias_does_not_satisfy_code_overlay(self) -> None:
        mappings = parse_qemu_mappings(SAMPLE)
        code = OverlaySpec(0x305678, 16, "MISTAKEN_CODE", 0x405678, "code")
        data = OverlaySpec(0x305678, 16, "REAL_DATA", 0x405678, "data")
        self.assertEqual(missing_mappings([code], mappings), [code])
        self.assertEqual(missing_mappings([data], mappings), [])

    def test_legacy_guest_copied_tables_are_data_only(self) -> None:
        specs = {item.name: item for item in collect_builder_overlays()}
        self.assertEqual(specs["APPLICATION_USERINFO_LITERAL"].role, "data")
        self.assertEqual(
            specs["APPLICATION_BYTE_CLASSIFY_TABLE"].role,
            "data",
        )

    def test_harvard_and_same_source_nested_overlays_do_not_collide(self) -> None:
        overlays = [
            OverlaySpec(0x330000, 0x100, "CODE", 0x500000, "code"),
            OverlaySpec(0x330020, 0x20, "DATA", 0x500020, "data"),
            OverlaySpec(0x340000, 0x20, "PREFIX", 0x510000, "code"),
            OverlaySpec(0x340000, 0x80, "SUPERSET", 0x510000, "code"),
        ]
        self.assertEqual(overlapping_overlays(overlays), [])

    def test_runtime_pc_resolves_to_linked_source(self) -> None:
        overlay = OverlaySpec(0x5F1A5A, 0x2C, "WIDE", 0x501A5A, "code")
        result = resolve_address(0x5F1A84, [overlay])
        self.assertEqual(result[0]["source"], "0x501a84")
        self.assertEqual(result[0]["offset"], "0x2a")

    def test_covering_mapping_prefers_exact_nested_harvard_window(self) -> None:
        spec = OverlaySpec(0x333D46, 0x20, "LEAF", 0x503D46, "code")
        broad = QemuMapping(0x333C86, 0x260, "BROAD", True, None)
        exact = QemuMapping(0x333D46, 0x20, "EXACT", True, 0x503D46)
        self.assertEqual(covering_mapping(spec, [broad, exact]), exact)

    def test_parses_direct_program_backed_code_alias(self) -> None:
        source = r'''
#define DIRECT_BASE 0x003307b0u
#define DIRECT_SOURCE 0x005007b0u
#define DIRECT_SIZE 0x34u
memory_region_init_alias(&s->code_direct_alias, NULL, "code-direct",
                         &s->program,
                         DIRECT_SOURCE - DMCU_PROGRAM_BASE,
                         DIRECT_SIZE);
memory_region_add_subregion_overlap(
    &s->code, DIRECT_BASE, &s->code_direct_alias, 2);
'''
        self.assertIn(
            QemuMapping(0x3307B0, 0x34, "DIRECT_BASE", True, 0x5007B0),
            parse_qemu_mappings(source),
        )

    def test_parses_complete_writable_data_bus(self) -> None:
        source = r'''
memory_region_init_ram(&s->data, NULL, "np560.data",
                       DMCU_DATA_SIZE, &error_fatal);
memory_region_add_subregion(get_system_memory(), 0, &s->data);
'''
        self.assertIn(
            QemuMapping(0, 1 << 24, "DMCU_DATA_SIZE", False, None),
            parse_qemu_mappings(source),
        )

    def test_copy_overlay_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        code = next(
            item for item in mappings
            if item.base == 0x32F786 and item.code
        )
        self.assertEqual(code.source, 0x4FF786)
        self.assertEqual(code.size, 0x3C)
        self.assertIn(
            '"np560.data-copy-overlay-alias", &s->data,\n'
            '                             NP560_COPY_OVERLAY_BASE,',
            qemu_source,
        )

    def test_result_object_jump_table_has_exact_harvard_data_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        spec = next(
            item for item in collect_builder_overlays()
            if item.name ==
            "APPLICATION_RESULT_OBJECT_INIT_JUMP_TABLE_DATA"
        )
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertFalse(mapping.code)
        self.assertEqual(mapping.base, 0x268346)
        self.assertEqual(mapping.source, 0x438346)
        self.assertEqual(mapping.size, 0x28)

    def test_result_memory_fill_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_RESULT_MEMORY_FILL"]
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x33269E)
        self.assertEqual(mapping.source, 0x50269E)
        self.assertEqual(mapping.size, 0x04)

    def test_storage_record_callback_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        callback = covering_mapping(
            specs["STORAGE_RECORD_CALLBACK"], mappings,
        )
        service = covering_mapping(
            specs["STORAGE_RECORD_CALLBACK_SERVICE"], mappings,
        )
        self.assertIsNotNone(callback)
        self.assertTrue(callback.code)
        self.assertEqual(callback.base, 0x33091C)
        self.assertEqual(callback.source, 0x50091C)
        self.assertEqual(callback.size, 0x34)
        self.assertIsNotNone(service)
        self.assertTrue(service.code)
        self.assertEqual(service.base, 0x336E5E)
        self.assertEqual(service.source, 0x506E5E)
        self.assertEqual(service.size, 0x06)

    def test_storage_record_drivers_have_exact_harvard_code_views(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        for name, base, source, size in (
            ("APPLICATION_STORAGE_UNIT_OPEN", 0x30A3C2, 0x4DA3C2, 0xEC),
            ("RESIDENT_STORAGE_UNIT_INIT", 0x18F97C, 0x35F97C, 0x67E),
            ("STORAGE_UNIT_WORKER", 0x2CFE08, 0x49FE08, 0x1D8),
            ("STORAGE_PACKED_FIELD", 0x31CBE8, 0x4ECBE8, 0x9C),
            ("STORAGE_SECONDARY_DRIVER", 0x326EA8, 0x4F6EA8, 0x6A),
            ("STORAGE_PRIMARY_READER", 0x326F12, 0x4F6F12, 0x6A),
            ("STORAGE_TRANSFER_WORKER", 0x2EBF9A, 0x4BBF9A, 0x16A),
            ("STORAGE_PRIMARY_TRANSFER", 0x2EC104, 0x4BC104, 0x16A),
            ("STORAGE_BLOCK_TRANSFER", 0x2905B0, 0x4605B0, 0x2D6),
            ("STORAGE_RECORD_POST_LOOKUP", 0x330070, 0x500070, 0x38),
            ("STORAGE_ASYNC_RANGE", 0x2CF6A6, 0x49F6A6, 0x1DA),
            ("STORAGE_RANGE_DISPATCH", 0x32EC6E, 0x4FEC6E, 0x40),
            ("STORAGE_FIELD_PARSE", 0x2C38C0, 0x4938C0, 0x200),
            ("STORAGE_BUFFER_DECODE", 0x30DA48, 0x4DDA48, 0xDE),
            ("STORAGE_EVENT_POLL", 0x320B6A, 0x4F0B6A, 0x8A),
            ("APPLICATION_TIMER_CALLBACK", 0x27E528, 0x44E528, 0x324),
            ("APPLICATION_STORAGE_CAPACITY", 0x2902D8, 0x4602D8, 0x2D8),
            ("APPLICATION_STORAGE_RECORD_LOOKUP", 0x2AD374, 0x47D374, 0x252),
            ("APPLICATION_STORAGE_DRIVER_RESOLVE", 0x2D3460, 0x4A3460, 0x1C8),
            ("APPLICATION_ADDRESS_RESOLVE", 0x30C8C0, 0x4DC8C0, 0xDE),
            ("APPLICATION_FILE_ATTACH_COMPARE_WRAPPERS", 0x332652, 0x502652, 0x4C),
        ):
            mapping = next(
                item for item in mappings
                if item.base == base and item.code and item.source == source
            )
            self.assertTrue(mapping.code)
            self.assertEqual(mapping.base, base)
            self.assertEqual(mapping.source, source)
            self.assertEqual(mapping.size, size)

    def test_modal_validation_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_MODAL_VALIDATION"]
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x322728)
        self.assertEqual(mapping.source, 0x4F2728)
        self.assertEqual(mapping.size, 0x82)

    def test_modal_foreground_object_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_MODAL_FOREGROUND_OBJECT"]
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x2D9DFC)
        self.assertEqual(mapping.source, 0x4A9DFC)
        self.assertEqual(mapping.size, 0x01AC)

    def test_buffer_copy_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_BUFFER_COPY"]
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x322520)
        self.assertEqual(mapping.source, 0x4F2520)
        self.assertEqual(mapping.size, 0x82)

    def test_foreground_loop_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_FOREGROUND_LOOP"]
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x202DE0)
        self.assertEqual(mapping.source, 0x3D2DE0)
        self.assertEqual(mapping.size, 0x05B0)

    def test_state_classify_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_STATE_CLASSIFY"]
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x319C1E)
        self.assertEqual(mapping.source, 0x4E9C1E)
        self.assertEqual(mapping.size, 0x00AA)

    def test_state_service_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_STATE_SERVICE"]
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x2F3A48)
        self.assertEqual(mapping.source, 0x4C3A48)
        self.assertEqual(mapping.size, 0x014C)

    def test_key_gpio_scan_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_KEY_GPIO_SCAN"]
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x31D9AA)
        self.assertEqual(mapping.source, 0x4ED9AA)
        self.assertEqual(mapping.size, 0x0098)

    def test_key_activity_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_KEY_ACTIVITY"]
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x2D2D40)
        self.assertEqual(mapping.source, 0x4A2D40)
        self.assertEqual(mapping.size, 0x01C8)

    def test_menu_power_state_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_MENU_POWER_STATE"]
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x2FFA32)
        self.assertEqual(mapping.source, 0x4CFA32)
        self.assertEqual(mapping.size, 0x011E)

    def test_state_ui_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_STATE_UI"]
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x22F40C)
        self.assertEqual(mapping.source, 0x3FF40C)
        self.assertEqual(mapping.size, 0x04CA)

    def test_dispatch_poll_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_DISPATCH_POLL"]
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x324C34)
        self.assertEqual(mapping.source, 0x4F4C34)
        self.assertEqual(mapping.size, 0x0074)

    def test_bitwise_helpers_have_exact_harvard_code_views(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        for name, base, source in (
            ("APPLICATION_BIT_OR", 0x314D24, 0x4E4D24),
            ("APPLICATION_BIT_AND", 0x315014, 0x4E5014),
        ):
            with self.subTest(name=name):
                mapping = covering_mapping(specs[name], mappings)
                self.assertIsNotNone(mapping)
                self.assertTrue(mapping.code)
                self.assertEqual(mapping.base, base)
                self.assertEqual(mapping.source, source)
                self.assertEqual(mapping.size, 0x00BC)

    def test_state_mode_duplicates_have_exact_harvard_code_views(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        for name in ("APPLICATION_STATE_MODE", "APPLICATION_MAIN_STATUS_GET"):
            with self.subTest(name=name):
                mapping = covering_mapping(specs[name], mappings)
                self.assertIsNotNone(mapping)
                self.assertTrue(mapping.code)
                self.assertEqual(mapping.base, 0x335D76)
                self.assertEqual(mapping.source, 0x505D76)
                self.assertEqual(mapping.size, 0x000E)

    def test_main_conditional_closure_has_exact_harvard_code_views(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        for name, base, source, size in (
            ("APPLICATION_MAIN_CONDITIONAL", 0x32F65A, 0x4FF65A, 0x003C),
            ("APPLICATION_MAIN_CONDITIONAL_WORKER", 0x2C7BA8, 0x497BA8, 0x01F0),
            ("APPLICATION_MAIN_FLAG_CLEAR", 0x334C7A, 0x504C7A, 0x0016),
        ):
            with self.subTest(name=name):
                mapping = covering_mapping(specs[name], mappings)
                self.assertIsNotNone(mapping)
                self.assertTrue(mapping.code)
                self.assertEqual(mapping.base, base)
                self.assertEqual(mapping.source, source)
                self.assertEqual(mapping.size, size)

    def test_main_service_closure_has_exact_harvard_code_views(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        for name, base, source, size in (
            ("APPLICATION_MAIN_SERVICES", 0x335090, 0x505090, 0x0014),
            ("APPLICATION_MAIN_INPUT_STATE", 0x31DF8C, 0x4EDF8C, 0x0096),
            ("APPLICATION_MAIN_STATUS_SCAN", 0x2F5024, 0x4C5024, 0x0148),
            ("APPLICATION_MAIN_STATE_TICK", 0x301EAA, 0x4D1EAA, 0x0114),
            ("APPLICATION_MAIN_STATE_CLEAR", 0x334EF8, 0x504EF8, 0x0016),
            ("APPLICATION_MAIN_STATE_SYNC", 0x322930, 0x4F2930, 0x0082),
        ):
            with self.subTest(name=name):
                mapping = covering_mapping(specs[name], mappings)
                self.assertIsNotNone(mapping)
                self.assertTrue(mapping.code)
                self.assertEqual(mapping.base, base)
                self.assertEqual(mapping.source, source)
                self.assertEqual(mapping.size, size)

    def test_system_mode_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        mapping = covering_mapping(specs["SYSTEM_MODE"], mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x335CB2)
        self.assertEqual(mapping.source, 0x505CB2)
        self.assertEqual(mapping.size, 0x000E)

    def test_memory_mode_pair_has_exact_harvard_code_views(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        for name, base, source in (
            ("MEMORY_RESET", 0x31AF72, 0x4EAF72),
            ("MEMORY_MODE", 0x31B014, 0x4EB014),
        ):
            with self.subTest(name=name):
                mapping = covering_mapping(specs[name], mappings)
                self.assertIsNotNone(mapping)
                self.assertTrue(mapping.code)
                self.assertEqual(mapping.base, base)
                self.assertEqual(mapping.source, source)
                self.assertEqual(mapping.size, 0x00A2)

    def test_activation_dispatch_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        mapping = covering_mapping(specs["ACTIVATION_DISPATCH"], mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x27507C)
        self.assertEqual(mapping.source, 0x44507C)
        self.assertEqual(mapping.size, 0x0350)

    def test_adjacent_wide_helpers_have_exact_harvard_code_views(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        for name, base, source in (
            ("WIDE_FROM_INT16", 0x3286B4, 0x4F86B4),
            ("WIDE_COMPARE", 0x328716, 0x4F8716),
        ):
            with self.subTest(name=name):
                mapping = covering_mapping(specs[name], mappings)
                self.assertIsNotNone(mapping)
                self.assertTrue(mapping.code)
                self.assertEqual(mapping.base, base)
                self.assertEqual(mapping.source, source)
                self.assertEqual(mapping.size, 0x0062)

    def test_display_state_pair_has_exact_harvard_code_views(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        for name, base, source, size in (
            ("APPLICATION_DISPLAY_STATE", 0x308C1C, 0x4D8C1C, 0x00F6),
            ("APPLICATION_DISPLAY_RESET", 0x328E5C, 0x4F8E5C, 0x0062),
        ):
            with self.subTest(name=name):
                mapping = covering_mapping(specs[name], mappings)
                self.assertIsNotNone(mapping)
                self.assertTrue(mapping.code)
                self.assertEqual(mapping.base, base)
                self.assertEqual(mapping.source, source)
                self.assertEqual(mapping.size, size)

    def test_foreground_parent_pair_has_exact_harvard_code_views(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        for name, base, source, size in (
            ("APPLICATION_FOREGROUND_PARENT", 0x2FC59A, 0x4CC59A, 0x012C),
            ("APPLICATION_FOREGROUND_DISPATCH_PREPARE", 0x32FE0A, 0x4FFE0A, 0x0038),
        ):
            with self.subTest(name=name):
                mapping = covering_mapping(specs[name], mappings)
                self.assertIsNotNone(mapping)
                self.assertTrue(mapping.code)
                self.assertEqual(mapping.base, base)
                self.assertEqual(mapping.source, source)
                self.assertEqual(mapping.size, size)

    def test_application_main_result_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        mapping = covering_mapping(specs["APPLICATION_MAIN_RESULT"], mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x3343CE)
        self.assertEqual(mapping.source, 0x5043CE)
        self.assertEqual(mapping.size, 0x001C)

    def test_application_top_level_pair_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        mapping = covering_mapping(specs["APPLICATION_TOP_LEVEL"], mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x2D7DD2)
        self.assertEqual(mapping.source, 0x4A7DD2)
        self.assertEqual(mapping.size, 0x036C)


if __name__ == "__main__":
    unittest.main()
