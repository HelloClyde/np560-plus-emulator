#!/usr/bin/env python3
"""Install the exact 18:F97C function after executable RAM is created.

The successful storage-unit path at 30:A490 calls resident 18:F97C.  Its
complete same-PC implementation is present at 35:F97C in NP560.PRG.  A static
SoC-ROM copy is insufficient: the application-region installer creates and
clears a higher-priority executable-RAM mapping over segment 18.

Patch both evidenced overlay-lifetime boundaries through resident wrappers.
The cold-boot wrapper runs after the existing 06:3830 late-result repair; the
direct-menu wrapper runs after the relocated 0A:0000 application-region
installer.  Each then invokes a guest DMCU installer which writes the exact
vendor function into executable RAM.  QEMU does not supply a ROM service or a
result value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

try:
    from scripts.build_np560_reconstructed_rom import (
        APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS,
    )
except ModuleNotFoundError:
    from build_np560_reconstructed_rom import (
        APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS,
    )


PROGRAM_BASE = 0x200000
SOURCE = 0x35F97C
DESTINATION = 0x18F97C
SIZE = 0x067E

ROM01_LATE_CALL = 0x011598
EXISTING_LATE_INSTALLER = 0x063830
DIRECT_MANAGER_CALL = 0x064900
COLD_BOOT_WRAPPER = 0x065100
DIRECT_MANAGER_WRAPPER = 0x065110
GUEST_INSTALLER = 0x073810
RESERVED_WORD = b"\x00\x0f"
RETS = 0xC620


def words_to_bytes(words: Sequence[int]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def program_bytes(program: bytes, address: int, size: int) -> bytes:
    offset = address - PROGRAM_BASE
    if offset < 0 or offset + size > len(program):
        raise ValueError(f"program range 0x{address:06X}+0x{size:X} is absent")
    return program[offset:offset + size]


def embedded_installer_words(payload: bytes) -> list[int]:
    """Return guest MOV-immediate stores for one same-bank program overlay."""
    if len(payload) != SIZE or len(payload) & 1:
        raise ValueError("storage-unit initializer payload size changed")
    logical = DESTINATION & 0x7FFF
    if logical + len(payload) > 0x8000:
        raise ValueError("18:F97C overlay unexpectedly crosses a data bank")

    words = [0x6810, DESTINATION >> 15]
    for offset in range(0, len(payload), 2):
        value = int.from_bytes(payload[offset:offset + 2], "little")
        words.extend((0x68F0, value, 0xA8F0, logical + offset))
    # Match the reset bank selectors expected by the following vendor calls.
    words.extend((0x6810, 0x0000, 0x6811, 0x0001, RETS))
    return words


def wrapper_words(preceding_installer: int) -> list[int]:
    return [
        0xBD00 | (preceding_installer >> 16), preceding_installer & 0xFFFF,
        0xBD00 | (GUEST_INSTALLER >> 16), GUEST_INSTALLER & 0xFFFF,
        RETS,
    ]


def patch_image(baseline: bytes, program: bytes) -> tuple[bytes, dict[str, object]]:
    exact = program_bytes(program, SOURCE, SIZE)
    if exact[:2] != words_to_bytes((0x2E09,)):
        raise ValueError("35:F97C no longer starts with LINK #9")
    if exact[-4:] != words_to_bytes((0x2F00, RETS)):
        raise ValueError("35:F97C no longer ends with UNLINK/RETS")

    expected_rom01_call = words_to_bytes((
        0xBD00 | (EXISTING_LATE_INSTALLER >> 16),
        EXISTING_LATE_INSTALLER & 0xFFFF,
    ))
    if baseline[ROM01_LATE_CALL:ROM01_LATE_CALL + 4] != expected_rom01_call:
        raise ValueError("01:1598 no longer calls the existing 06:3830 installer")

    expected_direct_call = words_to_bytes((
        0xBD00 | (APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS >> 16),
        APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS & 0xFFFF,
    ))
    if baseline[DIRECT_MANAGER_CALL:DIRECT_MANAGER_CALL + 4] != expected_direct_call:
        installer_address = (
            f"{APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS >> 16:02X}:"
            f"{APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS & 0xFFFF:04X}"
        )
        raise ValueError(
            f"06:4900 no longer calls the {installer_address} installer"
        )

    cold_wrapper = words_to_bytes(wrapper_words(EXISTING_LATE_INSTALLER))
    direct_wrapper = words_to_bytes(wrapper_words(
        APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS
    ))
    installer = words_to_bytes(embedded_installer_words(exact))
    for address, payload, name in (
        (COLD_BOOT_WRAPPER, cold_wrapper, "06:5100 cold-boot wrapper"),
        (DIRECT_MANAGER_WRAPPER, direct_wrapper, "06:5110 direct wrapper"),
        (GUEST_INSTALLER, installer, "07:3810 installer"),
    ):
        end = address + len(payload)
        if end > len(baseline):
            raise ValueError(f"{name} falls outside the SoC ROM image")
        if baseline[address:end] != RESERVED_WORD * (len(payload) // 2):
            raise ValueError(f"{name} range is no longer reserved")

    patched = bytearray(baseline)
    patched[ROM01_LATE_CALL:ROM01_LATE_CALL + 4] = words_to_bytes((
        0xBD00 | (COLD_BOOT_WRAPPER >> 16), COLD_BOOT_WRAPPER & 0xFFFF,
    ))
    patched[DIRECT_MANAGER_CALL:DIRECT_MANAGER_CALL + 4] = words_to_bytes((
        0xBD00 | (DIRECT_MANAGER_WRAPPER >> 16),
        DIRECT_MANAGER_WRAPPER & 0xFFFF,
    ))
    patched[COLD_BOOT_WRAPPER:COLD_BOOT_WRAPPER + len(cold_wrapper)] = cold_wrapper
    patched[DIRECT_MANAGER_WRAPPER:
            DIRECT_MANAGER_WRAPPER + len(direct_wrapper)] = direct_wrapper
    patched[GUEST_INSTALLER:GUEST_INSTALLER + len(installer)] = installer

    metadata: dict[str, object] = {
        "cold_boot_call": "01:1598 -> 06:5100",
        "cold_boot_wrapper": "SCALL 06:3830; SCALL 07:3810; RETS",
        "direct_manager_call": "06:4900 -> 06:5110",
        "direct_manager_wrapper": (
            "SCALL "
            f"{APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS >> 16:02X}:"
            f"{APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS & 0xFFFF:04X}; "
            "SCALL 07:3810; RETS"
        ),
        "guest_installer": "07:3810",
        "guest_installer_bytes": len(installer),
        "destination": "18:F97C executable RAM",
        "exact_source": "35:F97C",
        "exact_bytes": SIZE,
        "relocation": "none (same PC)",
        "lifetime": (
            "after cold-boot foreground loading and after direct-menu "
            "application-region loading"
        ),
        "execution_model": "ordinary guest DMCU instructions; no host HLE",
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
    print(f"installed guest storage-unit initializer; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-resident-storage-unit-init-v2",
            "baseline": str(args.baseline),
            "baseline_sha256": sha256(baseline),
            "program": str(args.program),
            "program_sha256": sha256(program),
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
