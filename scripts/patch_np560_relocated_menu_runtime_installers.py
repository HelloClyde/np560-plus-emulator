#!/usr/bin/env python3
"""Restore the menu-runtime guest installers without clobbering 06:3000.

The incremental direct-manager image retains an earlier guest dependency
installer at 06:3000.  The current clean-room menu installer normally spans
06:2900..06:3191, so placing it at its current builder address would destroy
that still-addressable entry.  Relocate the position-independent generated
installer to reserved 1F:C000 ROM, retarget the evidenced 06:490C call, and
materialize its three missing guest installer dependencies at their standard
reserved addresses.  All installed code executes inside the DMCU guest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from scripts import build_np560_reconstructed_rom as rom
except ModuleNotFoundError:
    import build_np560_reconstructed_rom as rom


CALL_ADDRESS = 0x06490C
OLD_MENU_INSTALLER_ADDRESS = rom.MENU_RUNTIME_OVERLAY_INSTALLER_ADDRESS
RELOCATED_MENU_INSTALLER_ADDRESS = 0x1FC000
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
            "menu_runtime_overlay_installer_relocated",
            RELOCATED_MENU_INSTALLER_ADDRESS,
            words_to_bytes(rom.menu_runtime_overlay_installer_words()),
        ),
        (
            "menu_arithmetic_wrapper_installer",
            rom.MENU_ARITHMETIC_WRAPPER_INSTALLER_ADDRESS,
            words_to_bytes(rom.menu_arithmetic_wrapper_installer_words()),
        ),
        (
            "application_menu_resource_decoder_installer",
            rom.APPLICATION_MENU_RESOURCE_DECODER_INSTALLER_ADDRESS,
            words_to_bytes(
                rom.application_menu_resource_decoder_installer_words()
            ),
        ),
        (
            "application_menu_text_stream_installer",
            rom.APPLICATION_MENU_TEXT_STREAM_INSTALLER_ADDRESS,
            words_to_bytes(rom.application_menu_text_stream_installer_words()),
        ),
    )
    for name, _address, payload in payloads:
        if not payload or int.from_bytes(payload[-2:], "little") != rom.RETS:
            raise ValueError(f"{name} does not end in RETS")
    return payloads


def patch_image(baseline: bytes) -> tuple[bytes, dict[str, object]]:
    if baseline[CALL_ADDRESS:CALL_ADDRESS + 4] != expected_call(
        OLD_MENU_INSTALLER_ADDRESS
    ):
        raise ValueError("06:490C no longer calls 06:2900")

    des = words_to_bytes(rom.des_table_initializer_words())
    des_start = rom.DES_TABLE_INITIALIZER_ADDRESS
    if baseline[des_start:des_start + len(des)] != des:
        raise ValueError("06:C000 DES initializer dependency is not exact")

    payloads = generated_payloads()
    for name, start, payload in payloads:
        end = start + len(payload)
        if end > len(baseline):
            raise ValueError(f"{name} falls outside resident ROM")
        if baseline[start:end] != RESERVED_WORD * (len(payload) // 2):
            raise ValueError(f"{name} destination is not reserved skeleton ROM")

    # This old entry is intentionally outside every destination above.  Keep
    # a digest in the manifest so the non-overlap is independently auditable.
    legacy_start = 0x063000
    legacy_end = 0x063192
    legacy_before = baseline[legacy_start:legacy_end]

    patched = bytearray(baseline)
    patched[CALL_ADDRESS:CALL_ADDRESS + 4] = expected_call(
        RELOCATED_MENU_INSTALLER_ADDRESS
    )
    for _name, start, payload in payloads:
        patched[start:start + len(payload)] = payload
    if patched[legacy_start:legacy_end] != legacy_before:
        raise AssertionError("legacy 06:3000 dependency installer was modified")

    entries = [
        {
            "name": name,
            "address": f"{start >> 16:02X}:{start & 0xFFFF:04X}",
            "bytes": len(payload),
        }
        for name, start, payload in payloads
    ]
    metadata: dict[str, object] = {
        "retargeted_call": "06:490C: 06:2900 -> 1F:C000",
        "installers": entries,
        "preserved_legacy_installer": "06:3000..06:3191",
        "preserved_legacy_sha256": sha256(legacy_before),
        "verified_dependency": "exact guest DES initializer at 06:C000",
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
        "installed relocated guest menu-runtime chain; "
        f"sha256={sha256(output)}"
    )
    if args.manifest:
        record = {
            "format": "np560-relocated-menu-runtime-installers-v1",
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
