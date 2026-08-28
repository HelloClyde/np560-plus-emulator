#!/usr/bin/env python3
"""Install the four exact segment-33 menu hardware-bit wrappers.

The recovered 4D:47EA menu renderer calls 33:6BB2/6BBA and
33:6C2A/6C32.  All four flat destinations are middles of a large framed
segment-33 function, while the same-PC segment-50 words are complete LINK #0
bit-set/bit-clear wrappers.  Segment 50 is mutable at this late lifecycle, so
carry the verified PRG words in a resident guest installer at 1F:F000 and
invoke it from the existing 1F:E000 direct-menu bridge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from disassembly import build_np560_reconstructed_rom as rom
    from disassembly import patch_np560_embedded_menu_result_record_parser as previous
except ModuleNotFoundError:
    import build_np560_reconstructed_rom as rom
    import patch_np560_embedded_menu_result_record_parser as previous


EMBEDDED_INSTALLER_ADDRESS = 0x1FF000
RESERVED_WORD = rom.RESERVED.to_bytes(2, "little")
WRAPPERS = (
    (0x336BB2, 0x506BB2, 0x0008, "set bit 31.2"),
    (0x336BBA, 0x506BBA, 0x0008, "set bit 31.1"),
    (0x336C2A, 0x506C2A, 0x0008, "clear bit 31.2"),
    (0x336C32, 0x506C32, 0x0008, "clear bit 31.1"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words_to_bytes(words: list[int]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def exact_wrapper_bytes(source: int, size: int) -> bytes:
    payload = rom.program_source_bytes(source, size)
    if payload[:2] != b"\x00\x2e" or payload[-4:] != b"\x00\x2f\x20\xc6":
        raise ValueError(f"{source >> 16:02X}:{source & 0xFFFF:04X} boundary changed")
    return payload


def embedded_installer_bytes() -> bytes:
    words: list[int] = []
    for destination, source, size, _purpose in WRAPPERS:
        exact_wrapper_bytes(source, size)
        words.extend(rom.embed_program_overlay_words(destination, source, size))
    words.append(rom.RETS)
    return words_to_bytes(words)


def old_bridge_region_bytes() -> bytes:
    old_size = len(previous.previous.bridge_bytes())
    bridge = previous.replacement_bridge_bytes()
    return bridge + RESERVED_WORD * ((old_size - len(bridge)) // 2)


def replacement_bridge_bytes() -> bytes:
    return words_to_bytes([
        0xBD00 | (previous.previous.menu.RELOCATED_MENU_INSTALLER_ADDRESS >> 16),
        previous.previous.menu.RELOCATED_MENU_INSTALLER_ADDRESS & 0xFFFF,
        0xBD00 | (previous.EMBEDDED_INSTALLER_ADDRESS >> 16),
        previous.EMBEDDED_INSTALLER_ADDRESS & 0xFFFF,
        0xBD00 | (EMBEDDED_INSTALLER_ADDRESS >> 16),
        EMBEDDED_INSTALLER_ADDRESS & 0xFFFF,
        rom.RETS,
    ])


def patch_image(baseline: bytes) -> tuple[bytes, dict[str, object]]:
    bridge_start = previous.previous.BRIDGE_ADDRESS
    old_region = old_bridge_region_bytes()
    bridge_end = bridge_start + len(old_region)
    if baseline[bridge_start:bridge_end] != old_region:
        raise ValueError("1F:E000 v103 bridge region is not exact")
    if baseline[
        previous.previous.DIRECT_MANAGER_CALL_ADDRESS:
        previous.previous.DIRECT_MANAGER_CALL_ADDRESS + 4
    ] != previous.previous.expected_call(bridge_start):
        raise ValueError("06:490C no longer calls 1F:E000")

    installer = embedded_installer_bytes()
    installer_end = EMBEDDED_INSTALLER_ADDRESS + len(installer)
    if installer_end > len(baseline):
        raise ValueError("menu hardware-bit installer is outside ROM")
    if baseline[EMBEDDED_INSTALLER_ADDRESS:installer_end] != (
        RESERVED_WORD * (len(installer) // 2)
    ):
        raise ValueError("1F:F000 installer destination is not reserved ROM")

    new_bridge = replacement_bridge_bytes()
    if len(new_bridge) > len(old_region):
        raise ValueError("replacement bridge no longer fits 1F:E000")
    patched = bytearray(baseline)
    patched[EMBEDDED_INSTALLER_ADDRESS:installer_end] = installer
    patched[bridge_start:bridge_end] = (
        new_bridge + RESERVED_WORD * ((len(old_region) - len(new_bridge)) // 2)
    )
    metadata: dict[str, object] = {
        "bridge": "1F:E000",
        "bridge_sequence": [
            "SCALL relocated menu installer 1F:C000",
            "SCALL embedded exact-parser installer 1F:3000",
            "SCALL embedded hardware-bit wrapper installer 1F:F000",
            "RETS",
        ],
        "embedded_installer": "1F:F000",
        "embedded_installer_bytes": len(installer),
        "restored_overlays": [
            {
                "destination": f"{destination >> 16:02X}:{destination & 0xFFFF:04X}",
                "exact_source": f"PRG {source >> 16:02X}:{source & 0xFFFF:04X}",
                "exact_bytes": size,
                "exact_sha256": sha256(exact_wrapper_bytes(source, size)),
                "purpose": purpose,
            }
            for destination, source, size, purpose in WRAPPERS
        ],
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
        "installed exact guest menu hardware-bit wrappers; "
        f"sha256={sha256(output)}"
    )
    if args.manifest:
        record = {
            "format": "np560-menu-hardware-bit-wrappers-v1",
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
