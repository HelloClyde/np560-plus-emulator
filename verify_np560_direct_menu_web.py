#!/usr/bin/env python3
"""Verify the recovered NP560+ direct menu through an existing Web instance.

This verifier never starts or mutates QEMU.  It polls the read-only ``/api/state``
endpoint of the isolated Web frontend and proves the guest-side resource read,
menu construction, native font rendering, and ST7529 row order together.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import struct
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from test_np560_system_boot import (
    application_calls,
    require_bottom_up_lcd_rows,
    require_clean_state,
    trace_r0,
)


RESOURCE_WINDOW_ADDRESS = 0x530400
RESOURCE_WINDOW_SIZE = 0x0220
RESOURCE_SECTOR_SIZE = 0x0200
RESOURCE_DIAGNOSTIC_OFFSET = 0x0200
RESOURCE_DIAGNOSTIC_SIZE = 0x0016
MENU_PAGE_WORK_ADDRESS = 0x514A46
MENU_PAGE_PREFIX_SIZE = 0x0010
MENU_ITEM_COUNT_ADDRESS = 0xA453A2
ROOT_PAGE_ADDRESS = 0x1C9748
ROOT_PAGE_ITEM_COUNT = 5
MINIMUM_DIRECT_MENU_FONT_BLITS = 1465
ROOT_MENU_LABELS = ("娱乐", "时间", "计算", "翻译", "资料")


def fetch_state(
    base_url: str, source: str = "lcd", base: int = 0, size: int = 0x3600,
) -> dict:
    query = urlencode({"source": source, "base": hex(base), "size": hex(size)})
    url = f"{base_url.rstrip('/')}/api/state?{query}"
    with urlopen(url, timeout=10) as response:
        payload = json.load(response)
    if "error" in payload:
        raise AssertionError(f"Web diagnostic request failed: {payload['error']}")
    return payload


def decoded_frame(snapshot: dict, expected_size: int) -> bytes:
    frame = base64.b64decode(snapshot["frame"], validate=True)
    if len(frame) != expected_size:
        raise AssertionError(
            f"snapshot returned {len(frame)} bytes, expected {expected_size}"
        )
    return frame


def native_font_blits(state: str) -> int:
    match = re.search(r"\bNATIVE_FONT_BLIT=CALLS:(\d+)", state)
    return int(match.group(1)) if match else 0


def root_menu_glyph_codes() -> tuple[tuple[int, ...], ...]:
    """Return the exact V3.80 menu-label codes consumed by guest 32:7B42."""
    result = []
    for label in ROOT_MENU_LABELS:
        encoded = label.encode("gb18030")
        if len(encoded) & 1:
            raise AssertionError(f"root menu label has an odd encoding: {label}")
        result.append(tuple(
            int.from_bytes(encoded[offset:offset + 2], "big")
            for offset in range(0, len(encoded), 2)
        ))
    return tuple(result)


def glyph_draw_codes(state: str) -> list[int]:
    """Parse the bounded guest glyph-code trace from a QEMU state dump."""
    match = re.search(r"(?m)^GLYPH_DRAW_TRACE=([^\r\n]+)$", state)
    if not match or match.group(1) == "none":
        return []
    codes = []
    for entry in match.group(1).split(","):
        code = re.search(r"/([0-9a-fA-F]{2,4})$", entry)
        if code:
            codes.append(int(code.group(1), 16))
    return codes


def font_copy_records(state: str) -> list[tuple[int, int, int, int, int]]:
    """Parse character, source, length, density and hash for copied glyphs."""
    match = re.search(r"(?m)^FONT_COPY_TRACE=([^\r\n]+)$", state)
    if not match or match.group(1) == "none":
        return []
    records = []
    for entry in match.group(1).split(","):
        record = re.fullmatch(
            r"([0-9a-fA-F]{4})>([0-9a-fA-F]{6})/"
            r"(\d+)/(\d+)/([0-9a-fA-F]{8})",
            entry,
        )
        if record:
            records.append((
                int(record.group(1), 16), int(record.group(2), 16),
                int(record.group(3)), int(record.group(4)),
                int(record.group(5), 16),
            ))
    return records


def rendered_root_menu_labels(state: str) -> tuple[str, ...]:
    """Return labels whose complete character sequence reached guest drawing."""
    codes = glyph_draw_codes(state)
    rendered = []
    for label, expected in zip(ROOT_MENU_LABELS, root_menu_glyph_codes()):
        width = len(expected)
        if any(tuple(codes[index:index + width]) == expected
               for index in range(len(codes) - width + 1)):
            rendered.append(label)
    return tuple(rendered)


def validate_direct_menu_snapshot(
    *,
    state: str,
    soc_rom: bytes,
    lcd_frame: bytes,
    native_framebuffer: bytes,
    resource_window: bytes,
    page_work: bytes,
    item_count_data: bytes,
    reported_soc_rom_size: int,
    reported_soc_rom_sha256: str,
) -> dict[str, int | str]:
    """Validate one coherent-enough read-only snapshot of the menu state."""
    expected_sha256 = hashlib.sha256(soc_rom).hexdigest()
    if reported_soc_rom_size != len(soc_rom):
        raise AssertionError(
            "Web instance loaded a different-sized SoC ROM: "
            f"reported={reported_soc_rom_size} expected={len(soc_rom)}"
        )
    if reported_soc_rom_sha256.lower() != expected_sha256:
        raise AssertionError(
            "Web instance is not bound to the requested SoC ROM: "
            f"reported={reported_soc_rom_sha256} expected={expected_sha256}"
        )
    require_clean_state(state)
    for name in ("MENU", "MENUPAGE", "MENUBUILDRET", "PAGEBUILD", "MENUOK"):
        if application_calls(state, name) < 1:
            raise AssertionError(f"guest has not reached {name}:\n{state}")
    if trace_r0(state, "MENUBUILDRET") != 1:
        raise AssertionError("resident menu table builder did not return one")

    font_blits = native_font_blits(state)
    if font_blits < MINIMUM_DIRECT_MENU_FONT_BLITS:
        raise AssertionError(
            "direct menu did not add native text blits: "
            f"calls={font_blits} minimum={MINIMUM_DIRECT_MENU_FONT_BLITS}"
        )

    rendered_labels = rendered_root_menu_labels(state)
    if rendered_labels != ROOT_MENU_LABELS:
        missing = [label for label in ROOT_MENU_LABELS
                   if label not in rendered_labels]
        raise AssertionError(
            "guest did not draw the recovered V3.80 root-menu labels: "
            f"missing={','.join(missing)} "
            f"glyph_codes={','.join(f'{code:04x}' for code in glyph_draw_codes(state))}"
        )

    expected_glyphs = tuple(
        code for label_codes in root_menu_glyph_codes() for code in label_codes
    )
    records = font_copy_records(state)
    glyph_hashes: dict[int, set[int]] = {}
    for character, source, length, nonzero, glyph_hash in records:
        if (source and length and 0 < nonzero <= length and glyph_hash):
            glyph_hashes.setdefault(character, set()).add(glyph_hash)
    missing_bitmaps = [code for code in expected_glyphs if code not in glyph_hashes]
    if missing_bitmaps:
        raise AssertionError(
            "guest font lookup did not copy non-empty bitmaps for root menu: "
            f"missing={','.join(f'{code:04x}' for code in missing_bitmaps)}"
        )
    signatures = [tuple(sorted(glyph_hashes[code])) for code in expected_glyphs]
    if len(set(signatures)) != len(expected_glyphs):
        raise AssertionError(
            "different root-menu characters reused a placeholder glyph bitmap"
        )

    if len(resource_window) != RESOURCE_WINDOW_SIZE:
        raise AssertionError("invalid direct-resource diagnostic window size")
    if len(page_work) != MENU_PAGE_PREFIX_SIZE:
        raise AssertionError("invalid menu page-work snapshot size")
    if len(item_count_data) != 1:
        raise AssertionError("invalid menu item-count snapshot size")
    if len(soc_rom) < ROOT_PAGE_ADDRESS + MENU_PAGE_PREFIX_SIZE:
        raise AssertionError("SoC ROM image does not contain the resident root page")

    diagnostic = resource_window[
        RESOURCE_DIAGNOSTIC_OFFSET:
        RESOURCE_DIAGNOSTIC_OFFSET + RESOURCE_DIAGNOSTIC_SIZE
    ]
    words = struct.unpack("<11H", diagnostic)
    if words[0] != 0x6840:
        raise AssertionError(
            f"direct resource callback did not run: marker={words[0]:04x}"
        )
    if words[5:7] != (ROOT_PAGE_ADDRESS >> 16, ROOT_PAGE_ADDRESS & 0xFFFF):
        raise AssertionError(
            "resource callback saw the wrong linked FILE position: "
            f"{words[5]:04x}:{words[6]:04x}"
        )

    sector_address = ROOT_PAGE_ADDRESS & ~(RESOURCE_SECTOR_SIZE - 1)
    expected_sector_prefix = soc_rom[sector_address:sector_address + 8]
    actual_sector_prefix = resource_window[:8]
    diagnostic_sector_prefix = diagnostic[0x0E:0x16]
    if actual_sector_prefix != expected_sector_prefix:
        raise AssertionError(
            "resource sector buffer does not match resident ROM: "
            f"expected={expected_sector_prefix.hex()} "
            f"actual={actual_sector_prefix.hex()}"
        )
    if diagnostic_sector_prefix != expected_sector_prefix:
        raise AssertionError(
            "resource callback copied-word snapshot is inconsistent: "
            f"expected={expected_sector_prefix.hex()} "
            f"actual={diagnostic_sector_prefix.hex()}"
        )

    expected_page_prefix = soc_rom[
        ROOT_PAGE_ADDRESS:ROOT_PAGE_ADDRESS + MENU_PAGE_PREFIX_SIZE
    ]
    if page_work != expected_page_prefix:
        raise AssertionError(
            "menu page-work buffer does not contain the resident root page: "
            f"expected={expected_page_prefix.hex()} actual={page_work.hex()}"
        )
    # A4:53A2 is a byte count.  A4:53A3 is the independent page-flags byte
    # initialized from descriptor +6 and must not be folded into this value.
    item_count = item_count_data[0]
    if item_count != ROOT_PAGE_ITEM_COUNT:
        raise AssertionError(
            f"menu item count is {item_count}, expected {ROOT_PAGE_ITEM_COUNT}"
        )

    if len(set(lcd_frame)) < 2:
        raise AssertionError("completed LCD frame is uniform")
    require_bottom_up_lcd_rows(lcd_frame, native_framebuffer)
    return {
        "menu_calls": application_calls(state, "MENU"),
        "page_build_calls": application_calls(state, "PAGEBUILD"),
        "font_blits": font_blits,
        "root_labels": len(rendered_labels),
        "root_glyphs": len(expected_glyphs),
        "item_count": item_count,
        "resource_position": f"{words[5]:02x}:{words[6]:04x}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8775")
    parser.add_argument("--soc-rom", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    args = parser.parse_args()
    if args.timeout <= 0 or args.poll_interval <= 0:
        parser.error("timeout and poll interval must be positive")

    soc_rom = args.soc_rom.read_bytes()
    deadline = time.monotonic() + args.timeout
    last_error = "no snapshot collected"
    while time.monotonic() < deadline:
        try:
            lcd = fetch_state(args.url)
            state = str(lcd["registers"])
            resource = fetch_state(
                args.url, "memory", RESOURCE_WINDOW_ADDRESS,
                RESOURCE_WINDOW_SIZE,
            )
            page = fetch_state(
                args.url, "memory", MENU_PAGE_WORK_ADDRESS,
                MENU_PAGE_PREFIX_SIZE,
            )
            count = fetch_state(
                args.url, "memory", MENU_ITEM_COUNT_ADDRESS, 1,
            )
            framebuffer = fetch_state(
                args.url, "memory", 0x503840, 0x3840,
            )
            result = validate_direct_menu_snapshot(
                state=state,
                soc_rom=soc_rom,
                lcd_frame=decoded_frame(lcd, 240 * 120),
                native_framebuffer=decoded_frame(framebuffer, 0x3840),
                resource_window=decoded_frame(resource, RESOURCE_WINDOW_SIZE),
                page_work=decoded_frame(page, MENU_PAGE_PREFIX_SIZE),
                item_count_data=decoded_frame(count, 1),
                reported_soc_rom_size=int(lcd.get("soc_rom_size", -1)),
                reported_soc_rom_sha256=str(lcd.get("soc_rom_sha256", "")),
            )
            print("NP560+ recovered direct menu passed")
            print(" ".join(f"{key.upper()}={value}" for key, value in result.items()))
            return 0
        except (AssertionError, KeyError, OSError, ValueError) as exc:
            last_error = str(exc)
            time.sleep(args.poll_interval)
    raise AssertionError(
        f"direct menu did not pass within {args.timeout:g}s: {last_error}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
