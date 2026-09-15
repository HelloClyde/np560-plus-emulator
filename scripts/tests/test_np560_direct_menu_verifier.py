from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import struct
import hashlib
import re
import unittest

from verify_np560_direct_menu_web import (
    MENU_PAGE_PREFIX_SIZE,
    MINIMUM_DIRECT_MENU_FONT_BLITS,
    RESOURCE_DIAGNOSTIC_OFFSET,
    RESOURCE_WINDOW_SIZE,
    ROOT_MENU_LABELS,
    ROOT_PAGE_ADDRESS,
    font_copy_records,
    glyph_draw_codes,
    rendered_root_menu_labels,
    root_menu_glyph_codes,
    validate_direct_menu_snapshot,
)


def valid_state() -> str:
    entries = (
        "MENU:1@06:4900/sp9000/r0000:0000:0000/a0000,0000,0000,0000",
        "MENUPAGE:1@2c:c9e8/sp9000/r0000:0000:0000/a0000,0000,0000,0000",
        "MENUBUILDRET:1@2a:34a4/sp9000/r0001:0000:0000/a0000,0000,0000,0000",
        "PAGEBUILD:1@2c:cb2e/sp9000/r0000:0000:0000/a0000,0000,0000,0000",
        "MENUOK:1@2c:cb80/sp9000/r0000:0000:0000/a0000,0000,0000,0000",
    )
    return (
        "ROM_HLE=off ROM_MISSING=none INVALID_CONTROL=none UNSUPPORTED=none "
        "FIRST_LOW_FP=none FIRST_LOW_SP=none NAND=EC:DC:10:95 ERROR=0\n"
        f"APPLICATION_TRACE={','.join(entries)}\n"
        f"NATIVE_FONT_BLIT=CALLS:{MINIMUM_DIRECT_MENU_FONT_BLITS} PTR:00000000\n"
        "GLYPH_DRAW_TRACE="
        "43:4868@8,12/d3e9,43:48ec@20,12/c0d6,"
        "43:4868@8,32/cab1,43:48ec@20,32/bce4,"
        "43:4868@8,52/bcc6,43:48ec@20,52/cbe3,"
        "43:4868@8,72/b7ad,43:48ec@20,72/d2eb,"
        "43:4868@8,92/d7ca,43:48ec@20,92/c1cf\n"
        "FONT_COPY_TRACE="
        "d3e9>350100/24/15/00000001,c0d6>350120/24/16/00000002,"
        "cab1>350140/24/17/00000003,bce4>350160/24/18/00000004,"
        "bcc6>350180/24/19/00000005,cbe3>3501a0/24/20/00000006,"
        "b7ad>3501c0/24/21/00000007,d2eb>3501e0/24/22/00000008,"
        "d7ca>350200/24/14/00000009,c1cf>350220/24/13/0000000a"
    )


def valid_inputs() -> dict:
    soc_rom = bytearray(ROOT_PAGE_ADDRESS + 0x200)
    sector = ROOT_PAGE_ADDRESS & ~0x1FF
    soc_rom[sector:sector + 8] = bytes.fromhex("1122334455667788")
    page_prefix = bytes.fromhex("040023001e00620003004e009e000000")
    soc_rom[ROOT_PAGE_ADDRESS:ROOT_PAGE_ADDRESS + len(page_prefix)] = page_prefix

    resource = bytearray(RESOURCE_WINDOW_SIZE)
    resource[:8] = soc_rom[sector:sector + 8]
    diagnostic = struct.pack(
        "<11H", 0x6840, 0, 0, 0, 0,
        ROOT_PAGE_ADDRESS >> 16, ROOT_PAGE_ADDRESS & 0xFFFF,
        *struct.unpack("<4H", resource[:8]),
    )
    resource[
        RESOURCE_DIAGNOSTIC_OFFSET:
        RESOURCE_DIAGNOSTIC_OFFSET + len(diagnostic)
    ] = diagnostic

    framebuffer = bytearray(240 * 120 // 2)
    framebuffer[0:2] = b"\x11\x10"
    lcd = bytearray(240 * 120)
    lcd[(119 * 240):(119 * 240) + 3] = b"\x01\x01\x01"
    soc_rom_bytes = bytes(soc_rom)
    return {
        "state": valid_state(),
        "soc_rom": soc_rom_bytes,
        "lcd_frame": bytes(lcd),
        "native_framebuffer": bytes(framebuffer),
        "resource_window": bytes(resource),
        "page_work": page_prefix[:MENU_PAGE_PREFIX_SIZE],
        "item_count_data": bytes([5]),
        "reported_soc_rom_size": len(soc_rom_bytes),
        "reported_soc_rom_sha256": hashlib.sha256(soc_rom_bytes).hexdigest(),
    }


class DirectMenuVerifierTests(unittest.TestCase):
    def test_accepts_complete_guest_menu_path(self) -> None:
        result = validate_direct_menu_snapshot(**valid_inputs())
        self.assertEqual(result["item_count"], 5)
        self.assertEqual(result["resource_position"], "1c:9748")
        self.assertEqual(result["root_labels"], 5)
        self.assertEqual(result["root_glyphs"], 10)

    def test_parses_exact_root_menu_glyph_codes(self) -> None:
        state = valid_state()
        self.assertEqual(
            root_menu_glyph_codes(),
            ((0xD3E9, 0xC0D6), (0xCAB1, 0xBCE4),
             (0xBCC6, 0xCBE3), (0xB7AD, 0xD2EB),
             (0xD7CA, 0xC1CF)),
        )
        self.assertEqual(rendered_root_menu_labels(state), ROOT_MENU_LABELS)
        self.assertEqual(glyph_draw_codes(state)[:2], [0xD3E9, 0xC0D6])
        self.assertEqual(
            font_copy_records(state)[0],
            (0xD3E9, 0x350100, 24, 15, 1),
        )

    def test_rejects_old_zero_page_work_regression(self) -> None:
        inputs = valid_inputs()
        inputs["page_work"] = bytes(MENU_PAGE_PREFIX_SIZE)
        with self.assertRaisesRegex(AssertionError, "page-work buffer"):
            validate_direct_menu_snapshot(**inputs)

    def test_rejects_stale_resource_callback(self) -> None:
        inputs = valid_inputs()
        resource = bytearray(inputs["resource_window"])
        resource[RESOURCE_DIAGNOSTIC_OFFSET:RESOURCE_DIAGNOSTIC_OFFSET + 2] = b"\0\0"
        inputs["resource_window"] = bytes(resource)
        with self.assertRaisesRegex(AssertionError, "callback did not run"):
            validate_direct_menu_snapshot(**inputs)

    def test_rejects_pre_menu_font_blit_count(self) -> None:
        inputs = valid_inputs()
        inputs["state"] = inputs["state"].replace(
            f"CALLS:{MINIMUM_DIRECT_MENU_FONT_BLITS}", "CALLS:1464"
        )
        with self.assertRaisesRegex(AssertionError, "did not add native text"):
            validate_direct_menu_snapshot(**inputs)

    def test_rejects_garbage_instead_of_root_menu_labels(self) -> None:
        inputs = valid_inputs()
        inputs["state"] = re.sub(
            r"(?m)^GLYPH_DRAW_TRACE=.*$",
            "GLYPH_DRAW_TRACE=43:4868@8,12/ffff,43:48ec@20,12/1234",
            inputs["state"],
        )
        with self.assertRaisesRegex(AssertionError, "root-menu labels"):
            validate_direct_menu_snapshot(**inputs)

    def test_rejects_one_placeholder_bitmap_for_all_chinese(self) -> None:
        inputs = valid_inputs()
        inputs["state"] = re.sub(
            r"(?m)^(FONT_COPY_TRACE=.*)$",
            lambda match: re.sub(
                r"/[0-9a-fA-F]{8}(?=,|$)", "/deadbeef", match.group(1)
            ),
            inputs["state"],
        )
        with self.assertRaisesRegex(AssertionError, "placeholder glyph"):
            validate_direct_menu_snapshot(**inputs)

    def test_rejects_empty_glyph_copy(self) -> None:
        inputs = valid_inputs()
        inputs["state"] = inputs["state"].replace(
            "d3e9>350100/24/15/00000001",
            "d3e9>350100/24/0/00000001",
        )
        with self.assertRaisesRegex(AssertionError, "non-empty bitmaps"):
            validate_direct_menu_snapshot(**inputs)

    def test_rejects_a_different_loaded_soc_rom(self) -> None:
        inputs = valid_inputs()
        inputs["reported_soc_rom_sha256"] = "0" * 64
        with self.assertRaisesRegex(AssertionError, "not bound"):
            validate_direct_menu_snapshot(**inputs)


if __name__ == "__main__":
    unittest.main()
