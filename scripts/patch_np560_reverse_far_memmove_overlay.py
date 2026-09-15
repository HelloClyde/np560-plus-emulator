#!/usr/bin/env python3
"""Install the reconstructed 31:7824 descending far-memory move.

The current system ROM lineage contains several exact post-builder patches.
Rebuilding from the base image alone would discard those recovered routines,
so this patch extends the already-executed ROM-01 foreground-object installer
with one call to an otherwise-reserved 09:C000 helper.  That helper writes the
clean-room DMCU routine to executable RAM; QEMU supplies only the Harvard code
alias for the guest-written range.
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


HOOK_ADDRESS = 0x064536
HELPER_ADDRESS = 0x09C000
RESERVED_WORD = 0x0F00


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words_to_bytes(words: list[int]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def patch_image(baseline: bytes) -> tuple[bytes, dict[str, object]]:
    reverse_words = rom.reverse_far_memmove_words()
    helper_words = [
        0x58F0,                       # preserve R0
        0x1F10,                       # preserve DS0
        *rom.write_program_words(
            rom.REVERSE_FAR_MEMMOVE_OVERLAY_DESTINATION,
            reverse_words,
        ),
        0x1F90,                       # restore DS0
        0x380F,                       # restore R0
        rom.RETS,
    ]
    helper = words_to_bytes(helper_words)
    helper_end = HELPER_ADDRESS + len(helper)
    if helper_end > rom.APPLICATION_MENU_TEXT_STREAM_INSTALLER_ADDRESS:
        raise ValueError("09:C000 helper overlaps the 09:C800 text installer")
    hook_words = [0xBD09, HELPER_ADDRESS & 0xFFFF, rom.RETS]
    hook = words_to_bytes(hook_words)

    expected_hook = words_to_bytes(
        [rom.RETS, RESERVED_WORD, RESERVED_WORD]
    )
    if baseline[HOOK_ADDRESS:HOOK_ADDRESS + len(hook)] != expected_hook:
        raise ValueError("06:4536 is not the exact RETS/reserved extension tail")
    expected_helper = words_to_bytes([RESERVED_WORD] * len(helper_words))
    if baseline[HELPER_ADDRESS:helper_end] != expected_helper:
        raise ValueError("09:C000 helper range is not fully reserved")

    patched = bytearray(baseline)
    patched[HOOK_ADDRESS:HOOK_ADDRESS + len(hook)] = hook
    patched[HELPER_ADDRESS:helper_end] = helper
    metadata: dict[str, object] = {
        "installer_hook": "06:4536 SCALL 09:C000; RETS",
        "installer_helper": (
            f"09:C000..09:{helper_end & 0xFFFF:04X}"
        ),
        "installer_helper_bytes": len(helper),
        "destination": "31:7824..31:78C3 executable overlay RAM",
        "guest_body_bytes": len(reverse_words) * 2,
        "abi": "memmove_reverse(dest_end_far, source_end_far, u16 bytes)",
        "callers": ["26:39B4 manager-table insertion", "26:A530 buffer compaction"],
        "execution_model": (
            "ordinary guest DMCU writes plus writable Harvard code alias; "
            "no host ROM service or SCALL interception"
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
    print(f"installed reverse far memmove; sha256={sha256(output)}")
    if args.manifest:
        record = {
            "format": "np560-reverse-far-memmove-overlay-v1",
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
