#!/usr/bin/env python3
"""Restore a real gzip NAND seed in QEMU and compare its raw export."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.web.np560_web import Emulator


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--soc-rom", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--gzip", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="np560-nand-gzip-") as directory:
        exported = Path(directory) / "exported.nand"
        emulator = Emulator(
            qemu=args.qemu.resolve(), firmware=args.firmware.resolve(),
            soc_rom=args.soc_rom.resolve(), soc_rom_skeleton=True,
            nand_checkpoint=args.gzip.resolve(), boot_mode="firmware-vma03",
            start_paused=True,
        )
        try:
            state = emulator.qmp.execute(
                "qom-get", {"path": "/machine", "property": "nand-state"}
            )
            if "CHECKPOINT=restored" not in state:
                raise AssertionError(f"Compressed seed was not restored: {state}")
            emulator.save_nand(exported, timeout=120)
        finally:
            emulator.close()
        if sha256(args.raw) != sha256(exported):
            raise AssertionError("QEMU gzip restore changed the checkpoint bytes")
    print("NP560+ gzip checkpoint restore and raw export matched")


if __name__ == "__main__":
    main()
