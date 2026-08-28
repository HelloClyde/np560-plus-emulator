#!/usr/bin/env python3
"""Materialize the guest menu pointer-index installer at 06:1600."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from disassembly import build_np560_reconstructed_rom as rom
except ModuleNotFoundError:
    import build_np560_reconstructed_rom as rom


INSTALLER_ADDRESS = rom.MENU_POINTER_INDEX_INSTALLER_ADDRESS
RESERVED_WORD = rom.RESERVED.to_bytes(2, "little")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def installer_bytes() -> bytes:
    words = rom.generic_main_menu_pointer_index_installer_words()
    if not words or words[-1] != rom.RETS:
        raise ValueError("menu pointer-index installer does not end in RETS")
    return b"".join(word.to_bytes(2, "little") for word in words)


def patch_image(baseline: bytes) -> tuple[bytes, dict[str, object]]:
    payload = installer_bytes()
    end = INSTALLER_ADDRESS + len(payload)
    if end > len(baseline):
        raise ValueError("menu pointer-index installer is outside ROM")
    if baseline[INSTALLER_ADDRESS:end] != (
        RESERVED_WORD * (len(payload) // 2)
    ):
        raise ValueError("06:1600 destination is not reserved skeleton ROM")

    patched = bytearray(baseline)
    patched[INSTALLER_ADDRESS:end] = payload
    metadata: dict[str, object] = {
        "installer": "06:1600",
        "installer_end_exclusive": "06:1746",
        "installer_bytes": len(payload),
        "purpose": "publish exact guest menu pointer-index words",
        "execution_model": (
            "ordinary guest DMCU immediate stores; no host HLE or "
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
        "installed guest menu pointer-index installer; "
        f"sha256={sha256(output)}"
    )
    if args.manifest:
        record = {
            "format": "np560-menu-pointer-index-installer-v1",
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
