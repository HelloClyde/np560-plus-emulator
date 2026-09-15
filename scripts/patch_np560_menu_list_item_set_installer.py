#!/usr/bin/env python3
"""Install the exact 30:3A56 menu list-item setter as guest code.

The already restored 33:4D2A wrapper calls 30:3A56.  Flat 30:3A56 is the
middle of an unrelated function and reaches 30:3892's unmatched epilogue;
the complete same-PC implementation is present in NP560.PRG at 4D:3A56.
Extend the resident 1F:F000 guest installer with a 1F:A000 sub-installer that
writes the exact vendor words into code RAM before the menu runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from scripts import build_np560_reconstructed_rom as rom
    from scripts import patch_np560_menu_hardware_bit_wrappers as previous
except ModuleNotFoundError:
    import build_np560_reconstructed_rom as rom
    import patch_np560_menu_hardware_bit_wrappers as previous


SUBINSTALLER_ADDRESS = 0x1FA000
DESTINATION = 0x303A56
SOURCE = 0x4D3A56
SIZE = 0x010C
RESERVED_WORD = rom.RESERVED.to_bytes(2, "little")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words_to_bytes(words: list[int]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def exact_function_bytes() -> bytes:
    payload = rom.program_source_bytes(SOURCE, SIZE)
    if payload[:2] != b"\x04\x2e":
        raise ValueError("4D:3A56 no longer starts with LINK #4")
    if payload[-16:] != words_to_bytes([
        0x50F2, 0xBD27, 0x6100, 0x383F,
        0x381F, 0x380F, 0x2F00, rom.RETS,
    ]):
        raise ValueError("4D:3A56 no longer has its evidenced epilogue")
    return payload


def subinstaller_bytes() -> bytes:
    exact_function_bytes()
    words = rom.embed_program_overlay_words(DESTINATION, SOURCE, SIZE)
    words.append(rom.RETS)
    return words_to_bytes(words)


def expanded_main_installer_bytes() -> bytes:
    old = previous.embedded_installer_bytes()
    if old[-2:] != words_to_bytes([rom.RETS]):
        raise ValueError("1F:F000 v105 installer no longer ends in RETS")
    return old[:-2] + words_to_bytes([
        0xBD00 | (SUBINSTALLER_ADDRESS >> 16),
        SUBINSTALLER_ADDRESS & 0xFFFF,
        rom.RETS,
    ])


def patch_image(baseline: bytes) -> tuple[bytes, dict[str, object]]:
    old_main = previous.embedded_installer_bytes()
    old_end = previous.EMBEDDED_INSTALLER_ADDRESS + len(old_main)
    if baseline[previous.EMBEDDED_INSTALLER_ADDRESS:old_end] != old_main:
        raise ValueError("1F:F000 v105 installer is not exact")

    new_main = expanded_main_installer_bytes()
    new_main_end = previous.EMBEDDED_INSTALLER_ADDRESS + len(new_main)
    if baseline[old_end:new_main_end] != (
        RESERVED_WORD * ((new_main_end - old_end) // 2)
    ):
        raise ValueError("1F:F000 expansion bytes are not reserved ROM")

    subinstaller = subinstaller_bytes()
    subinstaller_end = SUBINSTALLER_ADDRESS + len(subinstaller)
    if subinstaller_end > len(baseline):
        raise ValueError("1F:A000 sub-installer falls outside the SoC ROM")
    if baseline[SUBINSTALLER_ADDRESS:subinstaller_end] != (
        RESERVED_WORD * (len(subinstaller) // 2)
    ):
        raise ValueError("1F:A000 sub-installer destination is not reserved ROM")

    patched = bytearray(baseline)
    patched[previous.EMBEDDED_INSTALLER_ADDRESS:new_main_end] = new_main
    patched[SUBINSTALLER_ADDRESS:subinstaller_end] = subinstaller
    metadata: dict[str, object] = {
        "main_installer": "1F:F000",
        "main_installer_final_rets": "1F:F094",
        "subinstaller": "1F:A000",
        "subinstaller_bytes": len(subinstaller),
        "restored_overlay": {
            "destination": "30:3A56",
            "exact_source": "PRG 4D:3A56",
            "exact_bytes": SIZE,
            "exact_sha256": sha256(exact_function_bytes()),
            "boundary": "LINK #4 through balanced UNLINK/RETS",
        },
        "execution_model": (
            "ordinary guest DMCU immediate stores and SCALL; no host HLE "
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
        "installed exact guest 30:3A56 list-item setter; "
        f"sha256={sha256(output)}"
    )
    if args.manifest:
        record = {
            "format": "np560-menu-list-item-set-installer-v1",
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
