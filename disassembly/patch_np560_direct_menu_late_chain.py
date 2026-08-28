#!/usr/bin/env python3
"""Chain the exact late-result installer before the direct-menu probe.

The exploration ROM uses ``03:0080 -> 06:4900`` as its guest-side selector,
so it does not retain the factory ``01:1598 -> 06:3000`` call patched by
``patch_np560_rom01_late_result_table.py``.  Install the same exact guest
result-table repair in the reserved ROM-06 gap and route the existing
selector through a two-instruction bridge.  QEMU does not service either
operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import patch_np560_rom01_late_result_table as late


SELECTOR_ADDRESS = 0x030080
BRIDGE_ADDRESS = 0x063820
DIRECT_MENU_ADDRESS = 0x064900
RESERVED_WORD = b"\x00\x0f"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_image(baseline: bytes, program: bytes) -> tuple[bytes, dict[str, object]]:
    expected_selector = late.words_to_bytes((0xAD06, 0x4900))
    if baseline[SELECTOR_ADDRESS:SELECTOR_ADDRESS + 4] != expected_selector:
        raise ValueError("03:0080 is not the expected direct-menu selector")

    alloc = late.program_bytes(program, late.ALLOC_SOURCE, late.WRAPPER_SIZE)
    pointer = late.program_bytes(program, late.POINTER_SOURCE, late.WRAPPER_SIZE)
    if alloc != late.EXPECTED_ALLOC_BYTES:
        raise ValueError("50:51E0 exact allocation-wrapper signature changed")
    if pointer != late.EXPECTED_POINTER_BYTES:
        raise ValueError("50:51F2 exact pointer-wrapper signature changed")

    installer = late.words_to_bytes(late.late_installer_words(alloc, pointer))
    installer_end = late.LATE_INSTALLER_ADDRESS + len(installer)
    bridge = late.words_to_bytes((
        0xBD06, late.LATE_INSTALLER_ADDRESS & 0xFFFF,
        0xAD06, DIRECT_MENU_ADDRESS & 0xFFFF,
    ))
    reserved_start = BRIDGE_ADDRESS
    reserved_end = installer_end
    if reserved_end > len(baseline):
        raise ValueError("direct-menu late chain falls outside resident ROM")
    if baseline[reserved_start:reserved_end] != (
        RESERVED_WORD * ((reserved_end - reserved_start) // 2)
    ):
        raise ValueError("06:3820 late-chain range is no longer reserved")

    patched = bytearray(baseline)
    patched[SELECTOR_ADDRESS:SELECTOR_ADDRESS + 4] = late.words_to_bytes((
        0xAD06, BRIDGE_ADDRESS & 0xFFFF,
    ))
    patched[BRIDGE_ADDRESS:BRIDGE_ADDRESS + len(bridge)] = bridge
    patched[late.LATE_INSTALLER_ADDRESS:installer_end] = installer
    metadata: dict[str, object] = {
        "selector": "03:0080 -> 06:3820",
        "bridge": "06:3820: SCALL 06:3830; SJMP 06:4900",
        "late_installer": "06:3830",
        "late_installer_bytes": len(installer),
        "original_dependency_installer": "06:3000",
        "guest_writes": [
            {"destination": "33:51E0", "source": "50:51E0", "bytes": 18},
            {"destination": "33:51F2", "source": "50:51F2", "bytes": 18},
        ],
    }
    return bytes(patched), metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    baseline = args.baseline.read_bytes()
    program = args.program.read_bytes()
    output, patch = patch_image(baseline, program)
    args.output.write_bytes(output)
    print(
        f"installed direct-menu late chain; sha256={sha256(output)}"
    )
    if args.manifest:
        record = {
            "format": "np560-direct-menu-late-result-chain-v1",
            "baseline": str(args.baseline),
            "baseline_sha256": sha256(baseline),
            "program": str(args.program),
            "program_sha256": sha256(program),
            "output": str(args.output),
            "output_sha256": sha256(output),
            "patch": patch,
            "execution_model": "ordinary guest DMCU instructions; no host HLE",
        }
        args.manifest.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
