#!/usr/bin/env python3
"""Verify NP560+ reaches its root menu through the native application chain.

The verifier is read-only and attaches to an already-running Web frontend.  It
distinguishes a natural launch from the direct-menu exploration probe by
requiring the exact resident resource/selector/launch-manager trace before the
generic menu entry, then validates native glyph copies and ST7529 row order.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import time
from pathlib import Path

from test_np560_system_boot import (
    application_calls,
    require_bottom_up_lcd_rows,
    require_clean_state,
    trace_r0,
)
from verify_np560_direct_menu_web import (
    ROOT_MENU_LABELS,
    decoded_frame,
    fetch_state,
    font_copy_records,
    glyph_draw_codes,
    native_font_blits,
    rendered_root_menu_labels,
    root_menu_glyph_codes,
)


NATIVE_FRAMEBUFFER_ADDRESS = 0x503840
NATIVE_FRAMEBUFFER_SIZE = 240 * 120 // 2
MINIMUM_NATURAL_MENU_FONT_BLITS = sum(
    len(codes) for codes in root_menu_glyph_codes()
)
NATIVE_CHAIN = (
    "BOOT33", "STACK33", "INIT261", "INIT9", "SYSMAIN",
    "TOP", "RESINIT", "SELECTOR", "SELRET", "MANAGER",
    "REGLOOK", "REGRET", "MANRET", "MENU", "MENUPAGE",
    "MENUBUILDRET", "PAGEBUILD", "MENUOK",
)


def trace_from(state: str, name: str) -> str:
    match = re.search(
        rf"(?:APPLICATION_TRACE=|,){re.escape(name)}:\d+@"
        rf"([0-9A-Fa-f]{{2}}:[0-9A-Fa-f]{{4}})/",
        state,
    )
    return match.group(1).lower() if match else "none"


def validate_natural_menu_snapshot(
    *,
    state: str,
    soc_rom: bytes,
    lcd_frame: bytes,
    native_framebuffer: bytes,
    reported_soc_rom_size: int,
    reported_soc_rom_sha256: str,
) -> dict[str, int | str]:
    """Validate a native selector-to-root-menu snapshot."""
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
    for name in NATIVE_CHAIN:
        if application_calls(state, name) < 1:
            raise AssertionError(
                f"guest has not completed native chain stage {name}:\n{state}"
            )
    expected_factory_callers = {
        "BOOT33": "20:0004",
        "STACK33": "33:4f60",
        "INIT261": "33:6044",
        "INIT9": "11:5c0e",
    }
    for name, expected in expected_factory_callers.items():
        if trace_from(state, name) != expected:
            raise AssertionError(
                f"factory linked stage {name} has wrong caller: "
                f"from={trace_from(state, name)} expected={expected}"
            )
    if trace_from(state, "SELECTOR") != "1b:d48e":
        raise AssertionError(
            "23:A38C was not entered from exact resident call 1B:D48E: "
            f"from={trace_from(state, 'SELECTOR')}"
        )
    if trace_from(state, "SELRET") != "23:a81e":
        raise AssertionError(
            "selector did not return through its balanced 23:A81E epilogue: "
            f"from={trace_from(state, 'SELRET')}"
        )
    selector_result = trace_r0(state, "SELRET")
    if selector_result not in (0, 1, 2):
        raise AssertionError(
            f"selector returned an invalid result {selector_result:04x}"
        )
    if trace_r0(state, "MENUBUILDRET") != 1:
        raise AssertionError("resident menu table builder did not return one")

    font_blits = native_font_blits(state)
    if font_blits < MINIMUM_NATURAL_MENU_FONT_BLITS:
        raise AssertionError(
            "natural menu did not draw enough native glyphs: "
            f"calls={font_blits} minimum={MINIMUM_NATURAL_MENU_FONT_BLITS}"
        )
    rendered_labels = rendered_root_menu_labels(state)
    if rendered_labels != ROOT_MENU_LABELS:
        missing = [label for label in ROOT_MENU_LABELS
                   if label not in rendered_labels]
        raise AssertionError(
            "native chain did not draw the recovered root-menu labels: "
            f"missing={','.join(missing)} "
            f"glyph_codes={','.join(f'{code:04x}' for code in glyph_draw_codes(state))}"
        )

    expected_glyphs = tuple(
        code for label_codes in root_menu_glyph_codes() for code in label_codes
    )
    glyph_hashes: dict[int, set[int]] = {}
    for character, source, length, nonzero, glyph_hash in font_copy_records(state):
        if source and length and 0 < nonzero <= length and glyph_hash:
            glyph_hashes.setdefault(character, set()).add(glyph_hash)
    missing_bitmaps = [code for code in expected_glyphs if code not in glyph_hashes]
    if missing_bitmaps:
        raise AssertionError(
            "native font lookup did not copy root-menu bitmaps: "
            f"missing={','.join(f'{code:04x}' for code in missing_bitmaps)}"
        )
    signatures = [tuple(sorted(glyph_hashes[code])) for code in expected_glyphs]
    if len(set(signatures)) != len(expected_glyphs):
        raise AssertionError(
            "different root-menu characters reused a placeholder glyph bitmap"
        )

    if len(set(lcd_frame)) < 2:
        raise AssertionError("completed natural-menu LCD frame is uniform")
    require_bottom_up_lcd_rows(lcd_frame, native_framebuffer)
    return {
        "factory_stages": 5,
        "selector_calls": application_calls(state, "SELECTOR"),
        "selector_result": selector_result,
        "manager_calls": application_calls(state, "MANAGER"),
        "menu_calls": application_calls(state, "MENU"),
        "font_blits": font_blits,
        "root_labels": len(rendered_labels),
        "root_glyphs": len(expected_glyphs),
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
            framebuffer = fetch_state(
                args.url, "memory", NATIVE_FRAMEBUFFER_ADDRESS,
                NATIVE_FRAMEBUFFER_SIZE,
            )
            result = validate_natural_menu_snapshot(
                state=str(lcd["registers"]),
                soc_rom=soc_rom,
                lcd_frame=decoded_frame(lcd, 240 * 120),
                native_framebuffer=decoded_frame(
                    framebuffer, NATIVE_FRAMEBUFFER_SIZE
                ),
                reported_soc_rom_size=int(lcd.get("soc_rom_size", -1)),
                reported_soc_rom_sha256=str(lcd.get("soc_rom_sha256", "")),
            )
            print("NP560+ recovered natural menu passed")
            print(" ".join(
                f"{key.upper()}={value}" for key, value in result.items()
            ))
            return 0
        except (AssertionError, KeyError, OSError, ValueError) as exc:
            last_error = str(exc)
            time.sleep(args.poll_interval)
    raise AssertionError(
        f"natural menu did not pass within {args.timeout:g}s: {last_error}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
