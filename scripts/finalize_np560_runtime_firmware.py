#!/usr/bin/env python3
"""Remove one-shot NAND provisioning triggers from NP560 runtime firmware.

The provisioning image is intentionally used only to create a NAND
checkpoint.  Normal emulation must restore the vendor call at the selected
trigger site before using that checkpoint, otherwise every cold boot rewrites
the provisioned file and consumes application RAM as file-I/O scratch space.
The compiled shim may remain in its erased-bank allocation because it is
unreachable after the call site is restored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_np560_lirt_provision_firmware as provision  # noqa: E402


def restore_trigger(program: bytes, trigger: str) -> tuple[bytes, dict]:
    if len(program) != provision.PROGRAM_SIZE:
        raise ValueError(
            f"NP560 PRG must be {provision.PROGRAM_SIZE} bytes, "
            f"got {len(program)}"
        )
    if trigger not in provision.TRIGGERS:
        raise ValueError(f"unknown provision trigger: {trigger}")

    call, original_words, original_target, _forward_far_args = (
        provision.TRIGGERS[trigger]
    )
    provision_words = (
        0xBD00 | (provision.PROVISION_WRAPPER >> 16),
        provision.PROVISION_WRAPPER & 0xFFFF,
    )
    current_words = provision.read_words(program, call, 2)
    if current_words == original_words:
        output = program
        changed = False
    elif current_words == provision_words:
        image = bytearray(program)
        provision.put_words(image, call, list(original_words))
        output = bytes(image)
        changed = True
    else:
        raise ValueError(
            f"provision trigger signature changed at {call:06X}: "
            f"{current_words!r}"
        )

    manifest = {
        "format": "np560-runtime-firmware-finalization-v1",
        "hardware_rom_service": False,
        "host_filesystem_service": False,
        "trigger": trigger,
        "trigger_address": f"{call >> 16:02X}:{call & 0xFFFF:04X}",
        "provision_call": [f"{word:04X}" for word in provision_words],
        "restored_call": [f"{word:04X}" for word in original_words],
        "restored_target": (
            f"{original_target >> 16:02X}:{original_target & 0xFFFF:04X}"
        ),
        "changed": changed,
        "inactive_provision_code_retained": True,
        "input_sha256": hashlib.sha256(program).hexdigest(),
        "output_sha256": hashlib.sha256(output).hexdigest(),
    }
    return output, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("program", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--trigger", choices=tuple(provision.TRIGGERS),
        default="main-resource",
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output, manifest = restore_trigger(
        args.program.read_bytes(), args.trigger
    )
    document = {
        **manifest,
        "input": str(args.program.resolve()),
        "output": str(args.output.resolve()),
    }
    print(json.dumps(document, ensure_ascii=False, indent=2))
    if not args.dry_run:
        args.output.write_bytes(output)
        manifest_path = args.manifest or args.output.with_suffix(".json")
        manifest_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
