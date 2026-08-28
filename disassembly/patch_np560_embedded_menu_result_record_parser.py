#!/usr/bin/env python3
"""Embed the exact result-record parser after its source bank is mutable.

Runtime evidence at the late direct-menu boundary shows the data-bus view of
3D:81E0 is all zero, so the v102 guest copy loop cannot recover the exact PRG
body.  Encode those already verified PRG words in a resident guest installer
at 1F:3000 and have the 1F:E000 bridge SCALL it after the menu installer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from disassembly import build_np560_reconstructed_rom as rom
    from disassembly import patch_np560_menu_result_record_parser as previous
except ModuleNotFoundError:
    import build_np560_reconstructed_rom as rom
    import patch_np560_menu_result_record_parser as previous


EMBEDDED_INSTALLER_ADDRESS = 0x1F3000
RESERVED_WORD = rom.RESERVED.to_bytes(2, "little")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words_to_bytes(words: list[int]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def exact_parser_bytes() -> bytes:
    source = rom.program_source_bytes(
        rom.APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SOURCE,
        rom.APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SIZE,
    )
    if source[:2] != b"\x07\x2e" or source[-4:] != b"\x00\x2f\x20\xc6":
        raise ValueError("3D:81E0 result-record parser boundary changed")
    return source


def embedded_installer_bytes() -> bytes:
    words = rom.embed_program_overlay_words(
        rom.APPLICATION_RESULT_RECORD_PARSE_OVERLAY_DESTINATION,
        rom.APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SOURCE,
        rom.APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SIZE,
    )
    words.append(rom.RETS)
    return words_to_bytes(words)


def replacement_bridge_bytes() -> bytes:
    return words_to_bytes([
        0xBD00 | (previous.menu.RELOCATED_MENU_INSTALLER_ADDRESS >> 16),
        previous.menu.RELOCATED_MENU_INSTALLER_ADDRESS & 0xFFFF,
        0xBD00 | (EMBEDDED_INSTALLER_ADDRESS >> 16),
        EMBEDDED_INSTALLER_ADDRESS & 0xFFFF,
        rom.RETS,
    ])


def patch_image(baseline: bytes) -> tuple[bytes, dict[str, object]]:
    old_bridge = previous.bridge_bytes()
    old_start = previous.BRIDGE_ADDRESS
    old_end = old_start + len(old_bridge)
    if baseline[old_start:old_end] != old_bridge:
        raise ValueError("1F:E000 v102 copy bridge is not exact")
    if baseline[
        previous.DIRECT_MANAGER_CALL_ADDRESS:
        previous.DIRECT_MANAGER_CALL_ADDRESS + 4
    ] != previous.expected_call(previous.BRIDGE_ADDRESS):
        raise ValueError("06:490C no longer calls 1F:E000")

    exact = exact_parser_bytes()
    installer = embedded_installer_bytes()
    installer_end = EMBEDDED_INSTALLER_ADDRESS + len(installer)
    if installer_end > len(baseline):
        raise ValueError("embedded result-record installer is outside ROM")
    if baseline[EMBEDDED_INSTALLER_ADDRESS:installer_end] != (
        RESERVED_WORD * (len(installer) // 2)
    ):
        raise ValueError("1F:3000 installer destination is not reserved ROM")

    new_bridge = replacement_bridge_bytes()
    patched = bytearray(baseline)
    patched[EMBEDDED_INSTALLER_ADDRESS:installer_end] = installer
    patched[old_start:old_end] = (
        new_bridge + RESERVED_WORD * ((len(old_bridge) - len(new_bridge)) // 2)
    )
    metadata: dict[str, object] = {
        "bridge": "1F:E000",
        "bridge_sequence": [
            "SCALL relocated menu installer 1F:C000",
            "SCALL embedded exact-parser installer 1F:3000",
            "RETS",
        ],
        "embedded_installer": "1F:3000",
        "embedded_installer_bytes": len(installer),
        "restored_overlay": {
            "destination": "20:81E0",
            "exact_source": "PRG 3D:81E0",
            "exact_bytes": len(exact),
            "exact_sha256": sha256(exact),
            "boundary": "LINK #7 through UNLINK/RETS",
        },
        "late_source_state": (
            "3D:81E0 data-bus source is mutable/zero at this lifecycle; "
            "installer therefore carries verified PRG words"
        ),
        "execution_model": (
            "ordinary guest DMCU immediate stores and SCALLs; no host HLE "
            "or intercepted ROM service"
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
        "installed embedded guest result-record parser; "
        f"sha256={sha256(output)}"
    )
    if args.manifest:
        record = {
            "format": "np560-embedded-menu-result-record-parser-v1",
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
