#!/usr/bin/env python3
"""Restore the exact result-record parser before direct menu execution.

The menu foreground reaches 33:218E, which calls linked 20:81E0.  Flat
20:81E0 is only a suffix of an unrelated segment-20 worker and ends in an
unmatched UNLINK/RETS; exact PRG source 3D:81E0 is the complete LINK #7 body.
Route the direct manager through a tiny guest installer bridge that first
runs the relocated menu installer and then copies this exact parser overlay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from scripts import build_np560_reconstructed_rom as rom
    from scripts import patch_np560_menu_runtime_subinstallers as sub
    from scripts import patch_np560_relocated_menu_runtime_installers as menu
except ModuleNotFoundError:
    import build_np560_reconstructed_rom as rom
    import patch_np560_menu_runtime_subinstallers as sub
    import patch_np560_relocated_menu_runtime_installers as menu


BRIDGE_ADDRESS = 0x1FE000
DIRECT_MANAGER_CALL_ADDRESS = 0x06490C
RESERVED_WORD = rom.RESERVED.to_bytes(2, "little")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words_to_bytes(words: list[int]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def expected_call(address: int) -> bytes:
    return words_to_bytes([0xBD00 | (address >> 16), address & 0xFFFF])


def expected_relocated_menu_bytes() -> bytes:
    payload = bytearray(words_to_bytes(rom.menu_runtime_overlay_installer_words()))
    offset = sub.cursor_call_address() - menu.RELOCATED_MENU_INSTALLER_ADDRESS
    old = expected_call(rom.APPLICATION_CURSOR_REFRESH_INSTALLER_ADDRESS)
    if payload[offset:offset + 4] != old:
        raise ValueError("generated menu cursor call signature changed")
    payload[offset:offset + 4] = expected_call(
        sub.RELOCATED_CURSOR_INSTALLER_ADDRESS
    )
    return bytes(payload)


def bridge_bytes() -> bytes:
    words = [
        0xBD00 | (menu.RELOCATED_MENU_INSTALLER_ADDRESS >> 16),
        menu.RELOCATED_MENU_INSTALLER_ADDRESS & 0xFFFF,
    ]
    words.extend(rom.copy_code_to_overlay_words(
        rom.APPLICATION_RESULT_RECORD_PARSE_OVERLAY_DESTINATION,
        rom.APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SOURCE,
        rom.APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SIZE,
    ))
    words.append(rom.RETS)
    return words_to_bytes(words)


def patch_image(baseline: bytes) -> tuple[bytes, dict[str, object]]:
    if baseline[DIRECT_MANAGER_CALL_ADDRESS:DIRECT_MANAGER_CALL_ADDRESS + 4] != (
        expected_call(menu.RELOCATED_MENU_INSTALLER_ADDRESS)
    ):
        raise ValueError("06:490C no longer calls relocated menu installer")

    expected_menu = expected_relocated_menu_bytes()
    menu_start = menu.RELOCATED_MENU_INSTALLER_ADDRESS
    if baseline[menu_start:menu_start + len(expected_menu)] != expected_menu:
        raise ValueError("1F:C000 relocated menu installer is not exact v101 code")

    source = rom.program_source_bytes(
        rom.APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SOURCE,
        rom.APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SIZE,
    )
    if source[:2] != b"\x07\x2e" or source[-4:] != b"\x00\x2f\x20\xc6":
        raise ValueError("3D:81E0 result-record parser boundary changed")

    bridge = bridge_bytes()
    end = BRIDGE_ADDRESS + len(bridge)
    if end > len(baseline):
        raise ValueError("result-record parser bridge falls outside ROM")
    if baseline[BRIDGE_ADDRESS:end] != RESERVED_WORD * (len(bridge) // 2):
        raise ValueError("1F:E000 bridge destination is not reserved skeleton ROM")

    patched = bytearray(baseline)
    patched[BRIDGE_ADDRESS:end] = bridge
    patched[DIRECT_MANAGER_CALL_ADDRESS:DIRECT_MANAGER_CALL_ADDRESS + 4] = (
        expected_call(BRIDGE_ADDRESS)
    )
    metadata: dict[str, object] = {
        "retargeted_call": "06:490C: 1F:C000 -> 1F:E000",
        "bridge": "1F:E000",
        "bridge_bytes": len(bridge),
        "bridge_sequence": [
            "SCALL relocated menu installer 1F:C000",
            "copy exact 3D:81E0+0x58A to linked 20:81E0",
            "RETS",
        ],
        "restored_overlay": {
            "destination": "20:81E0",
            "exact_source": "3D:81E0",
            "bytes": rom.APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SIZE,
            "boundary": "LINK #7 through UNLINK/RETS",
        },
        "execution_model": (
            "ordinary guest DMCU SCALL and byte-copy loop; no host HLE or "
            "intercepted ROM service"
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
        "installed guest result-record parser bridge; "
        f"sha256={sha256(output)}"
    )
    if args.manifest:
        record = {
            "format": "np560-menu-result-record-parser-v1",
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
