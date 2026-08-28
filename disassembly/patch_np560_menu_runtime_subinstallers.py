#!/usr/bin/env python3
"""Complete the relocated menu chain and avoid the legacy 06:3A00 overlap.

In the incremental direct-manager baseline, 06:3A00 lies inside an older
06:3000 installer body rather than at the current builder's standalone cursor
installer.  Calling it as a subroutine therefore enters mid-function.  Keep
the old body intact, place the exact current cursor installer at 1F:D000,
retarget the one call inside the relocated 1F:C000 menu installer, and restore
the remaining current menu subinstallers in their still-reserved ROM gaps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from disassembly import build_np560_reconstructed_rom as rom
    from disassembly import patch_np560_relocated_menu_runtime_installers as menu
except ModuleNotFoundError:
    import build_np560_reconstructed_rom as rom
    import patch_np560_relocated_menu_runtime_installers as menu


RELOCATED_CURSOR_INSTALLER_ADDRESS = 0x1FD000
RESERVED_WORD = rom.RESERVED.to_bytes(2, "little")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words_to_bytes(words: list[int]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def expected_call(address: int) -> bytes:
    return words_to_bytes([0xBD00 | (address >> 16), address & 0xFFFF])


def generated_payloads() -> tuple[tuple[str, int, bytes], ...]:
    payloads = (
        (
            "application_cursor_refresh_installer_relocated",
            RELOCATED_CURSOR_INSTALLER_ADDRESS,
            words_to_bytes(rom.application_cursor_refresh_installer_words()),
        ),
        (
            "menu_result_table_installer",
            rom.MENU_RESULT_TABLE_INSTALLER_ADDRESS,
            words_to_bytes(rom.menu_result_table_installer_words()),
        ),
        (
            "menu_event_dependency_installer",
            rom.MENU_EVENT_DEPENDENCY_INSTALLER_ADDRESS,
            words_to_bytes(rom.menu_event_dependency_installer_words()),
        ),
        (
            "menu_event_state_installer",
            rom.MENU_EVENT_STATE_INSTALLER_ADDRESS,
            words_to_bytes(rom.menu_event_state_installer_words()),
        ),
        (
            "menu_service_init_installer",
            rom.MENU_SERVICE_INIT_INSTALLER_ADDRESS,
            words_to_bytes(rom.menu_service_init_installer_words()),
        ),
        (
            "menu_decimal_parse_engine_installer",
            rom.MENU_DECIMAL_PARSE_ENGINE_INSTALLER_ADDRESS,
            words_to_bytes(rom.menu_decimal_parse_engine_installer_words()),
        ),
    )
    for name, _address, payload in payloads:
        if not payload or int.from_bytes(payload[-2:], "little") != rom.RETS:
            raise ValueError(f"{name} does not end in RETS")
    return payloads


def cursor_call_address() -> int:
    payload = words_to_bytes(rom.menu_runtime_overlay_installer_words())
    old_call = expected_call(rom.APPLICATION_CURSOR_REFRESH_INSTALLER_ADDRESS)
    offsets = [
        index
        for index in range(0, len(payload) - 3, 2)
        if payload[index:index + 4] == old_call
    ]
    if offsets != [0x07EC]:
        raise ValueError("relocated menu cursor-call signature changed")
    return menu.RELOCATED_MENU_INSTALLER_ADDRESS + offsets[0]


def patch_image(baseline: bytes) -> tuple[bytes, dict[str, object]]:
    menu_payload = words_to_bytes(rom.menu_runtime_overlay_installer_words())
    menu_start = menu.RELOCATED_MENU_INSTALLER_ADDRESS
    if baseline[menu_start:menu_start + len(menu_payload)] != menu_payload:
        raise ValueError("1F:C000 relocated menu installer is not exact")

    call_address = cursor_call_address()
    if baseline[call_address:call_address + 4] != expected_call(
        rom.APPLICATION_CURSOR_REFRESH_INSTALLER_ADDRESS
    ):
        raise ValueError("1F:C7EC no longer calls conflicting 06:3A00")

    payloads = generated_payloads()
    for name, start, payload in payloads:
        end = start + len(payload)
        if end > len(baseline):
            raise ValueError(f"{name} falls outside resident ROM")
        if baseline[start:end] != RESERVED_WORD * (len(payload) // 2):
            raise ValueError(f"{name} destination is not reserved skeleton ROM")

    # The whole current non-reserved legacy span remains byte-identical.  It
    # includes the misleading 06:3A00 mid-function location.
    legacy_start = 0x063000
    legacy_end = 0x06421A
    legacy_before = baseline[legacy_start:legacy_end]

    patched = bytearray(baseline)
    patched[call_address:call_address + 4] = expected_call(
        RELOCATED_CURSOR_INSTALLER_ADDRESS
    )
    for _name, start, payload in payloads:
        patched[start:start + len(payload)] = payload
    if patched[legacy_start:legacy_end] != legacy_before:
        raise AssertionError("legacy 06:3000 installer body was modified")

    entries = [
        {
            "name": name,
            "address": f"{start >> 16:02X}:{start & 0xFFFF:04X}",
            "bytes": len(payload),
        }
        for name, start, payload in payloads
    ]
    metadata: dict[str, object] = {
        "retargeted_internal_call": "1F:C7EC: 06:3A00 -> 1F:D000",
        "installers": entries,
        "preserved_legacy_body": "06:3000..06:4219",
        "preserved_legacy_sha256": sha256(legacy_before),
        "execution_model": (
            "ordinary guest DMCU installers and one guest SCALL retarget; "
            "no host HLE or intercepted ROM service"
        ),
    }
    return bytes(patched), metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    baseline = args.baseline.read_bytes()
    output, patch = patch_image(baseline)
    args.output.write_bytes(output)
    print(
        "installed menu runtime subinstallers and relocated cursor chain; "
        f"sha256={sha256(output)}"
    )
    if args.manifest:
        record = {
            "format": "np560-menu-runtime-subinstallers-v1",
            "baseline": str(args.baseline),
            "baseline_sha256": sha256(baseline),
            "output": str(args.output),
            "output_sha256": sha256(output),
            "patch": patch,
        }
        args.manifest.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
