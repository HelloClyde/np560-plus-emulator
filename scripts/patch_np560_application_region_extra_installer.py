#!/usr/bin/env python3
"""Install the late application-region guest DMCU overlay installer.

The v98 execution path reaches the already reconstructed resident wrapper at
06:5110 and calls the relocated installer at 0A:0000.  That range is entirely
skeleton-ROM 0x0F00,
while the clean-room ROM builder already defines the bounded guest DMCU
installer expected at this address.  Materialize that exact generated code;
QEMU does not intercept the call and no host ROM service is introduced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from scripts.build_np560_reconstructed_rom import (
        APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS,
        RESERVED,
        RETS,
        application_region_extra_installer_words,
    )
except ModuleNotFoundError:
    from build_np560_reconstructed_rom import (
        APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS,
        RESERVED,
        RETS,
        application_region_extra_installer_words,
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words_to_bytes(words: list[int]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def installer_bytes() -> bytes:
    words = application_region_extra_installer_words()
    if not words or words[-1] != RETS:
        raise ValueError("application-region installer does not end in RETS")
    return words_to_bytes(words)


def patch_image(baseline: bytes) -> tuple[bytes, dict[str, object]]:
    payload = installer_bytes()
    start = APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS
    end = start + len(payload)
    if end > len(baseline):
        raise ValueError("application-region installer is outside ROM")
    expected = RESERVED.to_bytes(2, "little") * (len(payload) // 2)
    if baseline[start:end] != expected:
        address = f"{start >> 16:02X}:{start & 0xFFFF:04X}"
        raise ValueError(
            f"{address} installer range is not reserved skeleton ROM"
        )

    patched = bytearray(baseline)
    patched[start:end] = payload
    metadata: dict[str, object] = {
        "installer": f"{start >> 16:02X}:{start & 0xFFFF:04X}",
        "installer_end_exclusive": (
            f"{end >> 16:02X}:{end & 0xFFFF:04X}"
        ),
        "installer_bytes": len(payload),
        "installer_words": len(payload) // 2,
        "terminator": "RETS",
        "execution_model": (
            "ordinary clean-room guest DMCU overlay installer; no host HLE "
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
        "installed guest application-region overlay installer; "
        f"sha256={sha256(output)}"
    )
    if args.manifest:
        record = {
            "format": "np560-application-region-extra-installer-v1",
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
