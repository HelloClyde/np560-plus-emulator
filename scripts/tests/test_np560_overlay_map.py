#!/usr/bin/env python3
"""Tests for the reconstructed/QEMU overlay preflight map."""

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.np560_overlay_map import (  # noqa: E402
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
        self.assertEqual(
            specs["APPLICATION_DESKTOP_CLOCK_FORMAT"].role,
            "data",
        )
        self.assertEqual(
            specs["APPLICATION_FORMAT_PADDING_TABLE"].role,
            "data",
        )
        self.assertNotIn("APPLICATION_FLAG_NUMERIC_CHAIN", specs)

    def test_zero_code_source_means_coherent_data_backing(self) -> None:
        source = r'''
#define COHERENT_BASE 0x003344aeu
#define COHERENT_SIZE 0x1cu
static const NP560ProgramOverlay np560_late_overlays[] = {
    { COHERENT_BASE, COHERENT_SIZE, "data", "code", 0 },
};
'''
        mapping = parse_qemu_mappings(source)[0]
        self.assertTrue(mapping.code)
        self.assertIsNone(mapping.source)

    def test_operation_context_builder_has_coherent_guest_writable_code(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        spec = next(
            item for item in collect_builder_overlays()
            if item.name == "APPLICATION_OPERATION_CONTEXT_BUILD"
        )
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x299746)
        self.assertEqual(mapping.size, 0x02A4)
        self.assertIsNone(mapping.source)
        self.assertIn(
            "overlay->base !=\n"
            "                    "
            "NP560_APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_BASE",
            qemu_source,
        )

    def test_storage_registry_hook_has_coherent_guest_writable_code(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        spec = next(
            item for item in collect_builder_overlays()
            if item.name == "APPLICATION_STORAGE_REGISTRY"
        )
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x255858)
        self.assertEqual(mapping.size, 0x03F6)
        self.assertIsNone(mapping.source)
        self.assertNotIn(
            "NP560_APPLICATION_STORAGE_REGISTRY_OVERLAY_SOURCE",
            qemu_source,
        )

    def test_storage_capacity_retarget_chain_uses_guest_written_code(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}

        for name, base, size in (
            ("STORAGE_RECORD_CAPACITY_SERVICE", 0x5F13F8, 0x0030),
            ("STORAGE_RECORD_CAPACITY_WRAPPER", 0x5F661A, 0x000A),
        ):
            mapping = covering_mapping(specs[name], mappings)
            self.assertIsNotNone(mapping)
            self.assertTrue(mapping.code)
            self.assertEqual(mapping.base, base)
            self.assertEqual(mapping.size, size)
            self.assertIsNone(mapping.source)

        child = covering_mapping(
            specs["STORAGE_RECORD_CAPACITY_CHILD"], mappings
        )
        self.assertIsNotNone(child)
        self.assertTrue(child.code)
        self.assertEqual(child.base, 0x5F6DA0)
        self.assertEqual(child.size, 0x006A)
        self.assertEqual(child.source, 0x4F6B58)

    def test_npe_format_literal_has_data_only_writable_harvard_window(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        exact = [
            item for item in mappings
            if item.base == 0x324956 and item.end == 0x32497C
        ]

        self.assertEqual(len(exact), 1)
        self.assertFalse(exact[0].code)
        self.assertEqual(exact[0].size, 0x26)
        self.assertIsNone(exact[0].source)
        self.assertIn(
            "NP560_APPLICATION_NPE_FORMAT_LITERAL_DATA_BASE", qemu_source
        )
        self.assertIn(
            "np560.data-application-npe-format-literal-overlay-alias",
            qemu_source,
        )
        self.assertFalse(any(
            item.code and item.base == 0x324956 and item.end == 0x32497C
            for item in mappings
        ))
        self.assertNotIn("npe-format-literal-32-alias", qemu_source)

    def test_npe_layout_text_uses_exact_same_linked_data_island(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        exact = [
            item for item in mappings
            if item.base == 0x305862 and item.end == 0x305A6A
        ]

        self.assertEqual(len(exact), 1)
        self.assertFalse(exact[0].code)
        self.assertEqual(exact[0].source, 0x4D5862)
        self.assertEqual(exact[0].size, 0x0208)
        self.assertIn(
            "np560.data-application-layout-text-30-alias", qemu_source
        )
        self.assertFalse(any(
            item.code and item.base == 0x305862 and item.end == 0x305A6A
            for item in mappings
        ))

    def test_npe_list_text_uses_exact_same_linked_data_island(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        exact = [
            item for item in mappings
            if item.base == 0x32613C and item.end == 0x326358
        ]

        self.assertEqual(len(exact), 1)
        self.assertFalse(exact[0].code)
        self.assertEqual(exact[0].source, 0x4F613C)
        self.assertEqual(exact[0].size, 0x021C)
        self.assertIn(
            "np560.data-application-npe-list-text-32-alias", qemu_source
        )
        self.assertFalse(any(
            item.code and item.base == 0x32613C and item.end == 0x326358
            for item in mappings
        ))

    def test_npe_page_text_uses_exact_harvard_data_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        exact = [
            item for item in mappings
            if item.base == 0x31F040 and item.end == 0x31F160
        ]

        self.assertEqual(len(exact), 1)
        self.assertFalse(exact[0].code)
        self.assertEqual(exact[0].source, 0x4EF040)
        self.assertEqual(exact[0].size, 0x0120)
        self.assertIn(
            "np560.data-application-npe-page-text-31-alias", qemu_source
        )
        self.assertFalse(any(
            item.code and item.base == 0x31F040 and item.end == 0x31F160
            for item in mappings
        ))

    def test_npe_loader_slot_write_has_coherent_guest_code_window(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        spec = next(
            item for item in collect_builder_overlays()
            if item.name == "APPLICATION_NPE_LOADER_SLOT_WRITE"
        )
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x5FF38A)
        self.assertEqual(mapping.size, 0x003C)
        self.assertIsNone(mapping.source)

        linked = [
            item for item in mappings
            if item.base == 0x32F38A and item.end == 0x32F3C6
        ]
        self.assertEqual(len(linked), 1)
        self.assertTrue(linked[0].code)
        self.assertEqual(linked[0].size, 0x003C)
        self.assertIsNone(linked[0].source)
        self.assertIn(
            "np560.code-application-npe-loader-slot-write-linked-overlay-alias",
            qemu_source,
        )

        helper = [
            item for item in mappings
            if item.base == 0x263E5E and item.end == 0x2641FE
        ]
        self.assertEqual(len(helper), 1)
        self.assertTrue(helper[0].code)
        self.assertEqual(helper[0].size, 0x03A0)
        self.assertIsNone(helper[0].source)
        self.assertIn(
            "np560.code-application-npe-runtime-helper-overlay-alias",
            qemu_source,
        )

        object_update = [
            item for item in mappings
            if item.base == 0x2DC276 and item.end == 0x2DC41A
        ]
        self.assertEqual(len(object_update), 1)
        self.assertTrue(object_update[0].code)
        self.assertEqual(object_update[0].size, 0x01A4)
        self.assertIsNone(object_update[0].source)
        self.assertIn(
            "np560.code-application-npe-object-update-overlay-alias",
            qemu_source,
        )

        transform = [
            item for item in mappings
            if item.base == 0x3303B2 and item.end == 0x3303E8
        ]
        self.assertEqual(len(transform), 1)
        self.assertTrue(transform[0].code)
        self.assertEqual(transform[0].size, 0x0036)
        self.assertIsNone(transform[0].source)
        self.assertIn(
            "np560.code-application-npe-transform-helper-overlay-alias",
            qemu_source,
        )

    def test_npe_new_journey_closure_has_bounded_code_windows(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        expected = {
            (0x258392, 0x03E8): None,
            (0x236C3C, 0x04A4): None,
            (0x27E84C, 0x0324): None,
            (0x2E79FA, 0x017C): None,
            (0x29BBF2, 0x029A): None,
            (0x2D908E, 0x01B0): None,
            (0x31A3F4, 0x00A4): None,
            (0x5F0248, 0x0248): 0x480248,
        }

        for (base, size), source in expected.items():
            exact = [
                item for item in mappings
                if item.code and item.base == base and item.size == size
            ]
            self.assertEqual(len(exact), 1, f"missing {base:06x}+{size:x}")
            self.assertEqual(exact[0].source, source)

        self.assertIn(
            "NP560_APPLICATION_OPERATION_NEW_JOURNEY_INIT_OVERLAY_BASE",
            qemu_source,
        )
        self.assertIn(
            "np560.code-application-operation-new-journey-draw-overlay-alias",
            qemu_source,
        )
        self.assertIn(
            "np560.code-application-operation-transition-callback-overlay-alias",
            qemu_source,
        )
        helper_source = (
            ROOT / "qemu-dmcu" / "target" / "dmcu" / "helper.c"
        ).read_text(encoding="utf-8")
        self.assertIn("dmcu_code_address(0x1a, 0x77f0)", helper_source)
        self.assertIn("DMCU new-journey closure code sync", helper_source)

    def test_npe_operation7_menu_has_data_only_lifecycle_window(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        exact = [
            item for item in mappings
            if item.base == 0x2FAA00 and item.end == 0x2FAA54
        ]

        self.assertEqual(len(exact), 1)
        self.assertFalse(exact[0].code)
        self.assertEqual(exact[0].size, 0x54)
        self.assertIsNone(exact[0].source)
        self.assertIn(
            "NP560_APPLICATION_NPE_OPERATION7_MENU_DATA_BASE", qemu_source,
        )
        self.assertIn(
            "np560.data-application-npe-operation7-menu-data-alias",
            qemu_source,
        )
        self.assertFalse(any(
            item.code and item.base == 0x2FAA00 and item.end == 0x2FAA54
            for item in mappings
        ))

    def test_resource_open_wrapper_preserves_flat_continuation(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        self.assertFalse(any(
            item.code and item.base <= 0x32B63C < item.end
            for item in mappings
        ))
        relocated = [
            item for item in mappings
            if item.code and item.base == 0x5FB63C and item.end == 0x5FB690
        ]
        self.assertEqual(len(relocated), 1)
        self.assertEqual(relocated[0].source, 0x4FB63C)

    def test_npe_loader_context_init_has_exact_adjacent_coherent_window(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_NPE_LOADER_CONTEXT_INIT"]
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x32CEEE)
        self.assertEqual(mapping.size, 0x004A)
        self.assertIsNone(mapping.source)

        # The context helper still ends exactly where the original flat
        # 32:CF38 continuation begins.  The unrelated framed renderer now
        # lives in collision-free 5F:CF38 and must not create a mapping over
        # that continuation.
        self.assertEqual(mapping.end, 0x32CF38)
        self.assertFalse(any(
            item.base == 0x32CF38 and item.code for item in mappings
        ))
        render = next(
            item for item in mappings
            if item.base == 0x5FCF38 and item.code
        )
        self.assertEqual(render.size, 0x0046)

    def test_npe_bitmap_decoder_has_relocated_coherent_window(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        state_dispatch = covering_mapping(
            specs["APPLICATION_NPE_STATE_DISPATCH"], mappings,
        )
        self.assertIsNotNone(state_dispatch)
        self.assertTrue(state_dispatch.code)
        self.assertEqual(state_dispatch.base, 0x5F0000)
        self.assertEqual(state_dispatch.size, 0x0248)
        self.assertIsNone(state_dispatch.source)

        classifier = covering_mapping(
            specs["APPLICATION_NPE_STREAM_CLASSIFY"], mappings,
        )
        self.assertIsNotNone(classifier)
        self.assertTrue(classifier.code)
        self.assertEqual(classifier.base, 0x5F4E3E)
        self.assertEqual(classifier.size, 0x0234)
        self.assertIsNone(classifier.source)

        spec = specs["APPLICATION_NPE_LOADER_BITMAP_DECODE"]
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x5F716C)
        self.assertEqual(mapping.size, 0x0346)
        self.assertIsNone(mapping.source)

        child = covering_mapping(
            specs["APPLICATION_NPE_BITMAP_CONTEXT"], mappings,
        )
        self.assertIsNotNone(child)
        self.assertTrue(child.code)
        self.assertEqual(child.base, 0x5F8202)
        self.assertEqual(child.size, 0x02AA)
        self.assertIsNone(child.source)

        node_transfer = covering_mapping(
            specs["APPLICATION_NPE_NODE_TRANSFER"], mappings,
        )
        self.assertIsNotNone(node_transfer)
        self.assertTrue(node_transfer.code)
        self.assertEqual(node_transfer.base, 0x5FC5EC)
        self.assertEqual(node_transfer.size, 0x0850)
        self.assertEqual(node_transfer.source, 0x38C5EC)

    def test_npe_post_context_loader_closure_is_guest_written_code(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}

        for name, base, size in (
            ("APPLICATION_NPE_LOADER_PREPARE", 0x24ACBA, 0x0432),
            ("APPLICATION_NPE_LOADER_MODE", 0x3171D2, 0x00B4),
            ("APPLICATION_NPE_OPERATION7", 0x2B0DA2, 0x0242),
            ("APPLICATION_NPE_OPERATION7_DECODE", 0x26A92C, 0x037A),
        ):
            mapping = covering_mapping(specs[name], mappings)
            self.assertIsNotNone(mapping)
            self.assertTrue(mapping.code)
            self.assertEqual(mapping.base, base)
            self.assertEqual(mapping.size, size)
            self.assertIsNone(mapping.source)

    def test_foreground_event_lazy_call_reuses_decoder_code_alias(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        spec = next(
            item for item in collect_builder_overlays()
            if item.name == "APPLICATION_FOREGROUND_EVENT_STATE_LAZY_CALL"
        )
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x2FC216)
        self.assertEqual(mapping.size, 0x012C)
        self.assertIsNone(mapping.source)

    def test_operation_context_child_uses_exact_immutable_code_source(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        spec = next(
            item for item in collect_builder_overlays()
            if item.name == "APPLICATION_OPERATION_CONTEXT_CHILD"
        )
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x27CBE4)
        self.assertEqual(mapping.size, 0x032C)
        self.assertEqual(mapping.source, 0x44CBE4)

    def test_operation_context_casefold_closure_uses_exact_sources(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        expected = {
            "APPLICATION_OPERATION_CONTEXT_CASEFOLD":
                (0x315246, 0x00BA),
            "APPLICATION_OPERATION_CONTEXT_UPPER_PREDICATE":
                (0x33430A, 0x001C),
            "APPLICATION_OPERATION_CONTEXT_TOLOWER":
                (0x3345A2, 0x001A),
            "APPLICATION_NPE_BROWSER_LAZY_CALL":
                (0x333DB8, 0x0004),
        }

        specs = {
            item.name: item for item in collect_builder_overlays()
            if item.name in expected
        }
        self.assertEqual(set(specs), set(expected))
        for name, values in expected.items():
            mapping = covering_mapping(specs[name], mappings)

            self.assertIsNotNone(mapping)
            self.assertTrue(mapping.code)
            self.assertEqual(mapping.base, values[0])
            self.assertEqual(mapping.size, values[1])
            self.assertIsNone(mapping.source)

    def test_operation_context_predicate_uses_exact_source_50_leaf(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        spec = next(
            item for item in collect_builder_overlays()
            if item.name == "APPLICATION_OPERATION_CONTEXT_PREDICATE"
        )
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x336C0A)
        self.assertEqual(mapping.size, 0x0008)
        self.assertEqual(mapping.source, 0x506C0A)

    def test_game_world_browser_confirm_field_uses_exact_source_50_leaf(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        spec = next(
            item for item in collect_builder_overlays()
            if item.name == "APPLICATION_FILE_BROWSER_CONFIRM_FIELD"
        )
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x33384E)
        self.assertEqual(mapping.size, 0x0022)
        self.assertEqual(mapping.source, 0x50384E)

    def test_game_world_browser_path_range_uses_exact_source_42_worker(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        spec = next(
            item for item in collect_builder_overlays()
            if item.name == "APPLICATION_FILE_BROWSER_PATH_RANGE"
        )
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x25F992)
        self.assertEqual(mapping.size, 0x03BA)
        self.assertEqual(mapping.source, 0x42F992)

    def test_game_world_item_callback_closure_is_coherent_guest_code(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        expected = {
            "APPLICATION_MAIN_ITEM_CALLBACK": (0x22147A, 0x051A),
            "APPLICATION_MAIN_ITEM_CALLBACK_RANGE": (0x2E0192, 0x0192),
            "APPLICATION_MAIN_ITEM_CALLBACK_FINALIZE": (0x32F0E0, 0x003E),
        }

        for name, (base, size) in expected.items():
            mapping = covering_mapping(specs[name], mappings)
            self.assertIsNotNone(mapping)
            self.assertTrue(mapping.code)
            self.assertEqual(mapping.base, base)
            self.assertEqual(mapping.size, size)
            self.assertIsNone(mapping.source)

        callback = covering_mapping(
            specs["APPLICATION_MAIN_ITEM_CALLBACK"], mappings,
        )
        self.assertLessEqual(callback.base, 0x22175A)
        self.assertGreaterEqual(callback.base + callback.size, 0x221780)

    def test_file_browser_layout_range_uses_exact_source(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        spec = next(
            item for item in collect_builder_overlays()
            if item.name == "APPLICATION_FILE_BROWSER_LAYOUT_RANGE"
        )
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x2E393A)
        self.assertEqual(mapping.size, 0x0188)
        self.assertEqual(mapping.source, 0x4B393A)

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

    def test_operation_six_input_dispatch_table_has_exact_harvard_view(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        mapping = next(
            item for item in mappings
            if item.base == 0x11B8DA and not item.code
        )
        self.assertEqual(mapping.source, 0x2EB8DA)
        self.assertEqual(mapping.size, 0x10)

    def test_operation_ui_prepare_has_exact_immutable_code_source(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        spec = next(
            item for item in collect_builder_overlays()
            if item.name == "APPLICATION_OPERATION_UI_PREPARE"
        )
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x336610)
        self.assertEqual(mapping.size, 0x000A)
        self.assertEqual(mapping.source, 0x506610)

    def test_application_page_dialog_text_has_exact_harvard_data_view(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        mapping = next(
            item for item in mappings
            if item.base == 0x32E248 and not item.code
        )
        self.assertEqual(mapping.source, 0x4FE248)
        self.assertEqual(mapping.size, 0x84)

    def test_application_file_dialog_text_has_exact_harvard_data_view(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        mapping = next(
            item for item in mappings
            if item.base == 0x27E000 and not item.code
        )
        self.assertEqual(mapping.source, 0x44E000)
        self.assertEqual(mapping.size, 0x7E)

        operation_pool = next(
            item for item in mappings
            if item.base == 0x27E07E and item.code
        )
        self.assertEqual(mapping.base + mapping.size, operation_pool.base)

    def test_wrapped_text_draw_has_guest_writable_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        spec = next(
            item for item in collect_builder_overlays()
            if item.name == "APPLICATION_WRAPPED_TEXT_DRAW"
        )
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x2F0000)
        self.assertEqual(mapping.size, 0x158)

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

    def test_main_action_buffer_prepare_has_exact_harvard_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_MAIN_ACTION_BUFFER_PREPARE"]
        mapping = covering_mapping(spec, mappings)
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x2411BE)
        self.assertEqual(mapping.source, 0x4111BE)
        self.assertEqual(mapping.size, 0x0184)

    def test_main_action_render_helper_has_guest_writable_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        spec = specs["APPLICATION_MAIN_ACTION_RENDER_HELPER"]
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x2E2B6E)
        self.assertEqual(mapping.size, 0x018A)
        self.assertIsNone(mapping.source)

    def test_main_render_finalize_has_guest_writable_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        mapping = covering_mapping(
            specs["APPLICATION_MAIN_RENDER_FINALIZE"], mappings,
        )

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x306082)
        self.assertEqual(mapping.size, 0x0104)
        self.assertIsNone(mapping.source)

    def test_main_render_layout_has_guest_writable_code_view(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        mapping = covering_mapping(
            specs["APPLICATION_MAIN_RENDER_LAYOUT"], mappings,
        )

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x2C8744)
        self.assertEqual(mapping.size, 0x01EE)
        self.assertIsNone(mapping.source)

    def test_game_world_controller_table_has_soc_rom_data_alias(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "NP560_RESIDENT_GAME_WORLD_CONTROLLER_TABLE_BASE 0x000f7e92u",
            qemu_source,
        )
        self.assertIn(
            "NP560_RESIDENT_GAME_WORLD_CONTROLLER_TABLE_SIZE 0x0000001eu",
            qemu_source,
        )
        self.assertIn(
            "np560.data-resident-game-world-controller-table-alias",
            qemu_source,
        )

    def test_game_world_event_dispatch_table_has_soc_rom_data_alias(
            self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "NP560_RESIDENT_GAME_WORLD_EVENT_DISPATCH_TABLE_BASE "
            "0x000db420u",
            qemu_source,
        )
        self.assertIn(
            "NP560_RESIDENT_GAME_WORLD_EVENT_DISPATCH_TABLE_SIZE "
            "0x00000014u",
            qemu_source,
        )
        self.assertIn(
            "np560.data-resident-game-world-event-dispatch-table-alias",
            qemu_source,
        )

    def test_game_world_controller_dependency_code_views(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        expected = {
            "GAME_WORLD_CONTROLLER_DEP_2D622E": (0x2D622E, 0x01BE, None),
            "GAME_WORLD_CONTROLLER_DEP_30A0FC": (0x30A0FC, 0x00EE, None),
            "GAME_WORLD_CONTROLLER_DEP_287408": (0x287408, 0x02FE,
                                                   0x457408),
            "GAME_WORLD_CONTROLLER_DEP_30EE12": (0x30EE12, 0x00DA, None),
            "GAME_WORLD_CONTROLLER_DEP_3150D0": (0x3150D0, 0x00BC, None),
            "GAME_WORLD_CONTROLLER_DEP_323E52": (0x323E52, 0x007A, None),
            "GAME_WORLD_CONTROLLER_DEP_282844": (0x282844, 0x0312,
                                                   0x452844),
            "GAME_WORLD_CONTROLLER_DEP_32E06C": (0x32E06C, 0x0044, None),
            "GAME_WORLD_CONTROLLER_DEP_2BDB86": (0x2BDB86, 0x0218,
                                                   0x48DB86),
        }

        for name, (base, size, source) in expected.items():
            with self.subTest(name=name):
                mapping = covering_mapping(specs[name], mappings)
                self.assertIsNotNone(mapping)
                self.assertTrue(mapping.code)
                self.assertEqual(mapping.base, base)
                self.assertEqual(mapping.size, size)
                self.assertEqual(mapping.source, source)

    def test_operation_browser_chain_has_exact_code_views(self) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        specs = {item.name: item for item in collect_builder_overlays()}
        expected = (
            ("APPLICATION_OPERATION_UI_INIT", 0x29D0BA, 0x0296, 0x46D0BA),
            ("APPLICATION_OPERATION_MODE_ROUTER", 0x2FB644, 0x0130, None),
            ("APPLICATION_OPERATION_ACTION", 0x2370E0, 0x04A4, None),
            ("APPLICATION_OPERATION_ACTION_MODE_PREDICATE",
             0x302966, 0x0112, None),
            ("APPLICATION_OPERATION_RECORD_ACCESSOR",
             0x5F380A, 0x0022, None),
            ("APPLICATION_OPERATION_FRAME_DRAW",
             0x5F6A9C, 0x0102, None),
            ("APPLICATION_OPERATION_NUMBER_DISPATCH", 0x2DF47C, 0x0196, None),
        )

        for name, base, size, source in expected:
            with self.subTest(name=name):
                mapping = covering_mapping(specs[name], mappings)
                self.assertIsNotNone(mapping)
                self.assertTrue(mapping.code)
                self.assertEqual(mapping.base, base)
                self.assertEqual(mapping.size, size)
                self.assertEqual(mapping.source, source)

    def test_resident_operation_dispatch_table_has_soc_rom_data_alias(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "NP560_RESIDENT_OPERATION_DISPATCH_TABLE_BASE 0x001b299cu",
            qemu_source,
        )
        self.assertIn(
            "NP560_RESIDENT_OPERATION_DISPATCH_TABLE_SIZE 0x00000026u",
            qemu_source,
        )
        self.assertRegex(
            qemu_source,
            r"(?s)memory_region_init_alias\(\s*"
            r"&s->data_resident_operation_dispatch_table_alias,\s*NULL,\s*"
            r'"np560\.data-resident-operation-dispatch-table-alias",\s*'
            r"&s->soc_rom_region,\s*"
            r"NP560_RESIDENT_OPERATION_DISPATCH_TABLE_BASE,\s*"
            r"NP560_RESIDENT_OPERATION_DISPATCH_TABLE_SIZE\s*\);\s*"
            r"memory_region_add_subregion_overlap\(\s*"
            r"get_system_memory\(\),\s*"
            r"NP560_RESIDENT_OPERATION_DISPATCH_TABLE_BASE,\s*"
            r"&s->data_resident_operation_dispatch_table_alias,\s*2\s*\);",
        )
        self.assertNotRegex(
            qemu_source,
            r"(?s)memory_region_add_subregion_overlap\(\s*&s->code,\s*"
            r"NP560_RESIDENT_OPERATION_DISPATCH_TABLE_BASE,",
        )

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

    def test_npe_table_mode_initializer_has_coherent_guest_code_window(
        self,
    ) -> None:
        qemu_source = (
            ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
        ).read_text(encoding="utf-8")
        mappings = parse_qemu_mappings(qemu_source)
        spec = next(
            item for item in collect_builder_overlays()
            if item.name == "APPLICATION_NPE_TABLE_MODE_INIT"
        )
        mapping = covering_mapping(spec, mappings)

        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.code)
        self.assertEqual(mapping.base, 0x253082)
        self.assertEqual(mapping.size, 0x0400)
        self.assertIsNone(mapping.source)
        self.assertIn(
            "np560.code-application-npe-table-mode-init-overlay-alias",
            qemu_source,
        )

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
