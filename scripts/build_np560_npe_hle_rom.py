"""Add return instructions behind verified experimental NPE ROM HLE gates.

This is a copy of an existing strict-skeleton resident image, not a recovered
factory ROM.  The entry marker remains strict and is handled only when the
QEMU NPE codec socket option is enabled.  All other unknown ROM stays strict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ENTRY_OFFSETS = (0x02ACD8, 0x01B6DE, 0x01B7AA, 0x01B816, 0x01B84E,
                 0x02AD92)
STRICT = bytes.fromhex("000f")
RETS = bytes.fromhex("20c6")


def patch_image(raw: bytes) -> bytes:
    """Install only the six reviewed HLE returns in a strict ROM image."""
    patched = bytearray(raw)
    for offset in ENTRY_OFFSETS:
        if offset + 4 > len(raw) or raw[offset:offset + 4] != STRICT * 2:
            raise ValueError(f"strict two-word ROM hole not found at {offset:06x}")
        patched[offset + 2:offset + 4] = RETS
    return bytes(patched)


def build(source: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    raw = source.read_bytes()
    patched = patch_image(raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    report = {
        "schema": "np560-experimental-npe-hle-gates-v1",
        "source": str(source.resolve()),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "output": str(output.resolve()),
        "output_sha256": hashlib.sha256(patched).hexdigest(),
        "entry_offsets": [f"{offset:06x}" for offset in ENTRY_OFFSETS],
        "patched_word": "c620 RETS at entry+2",
        "ad92_implemented": True,
        "ad92_scope": "observed NPE 0:1000 PCM transfer only",
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.source, args.output)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
