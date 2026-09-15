#!/usr/bin/env python3
"""Seed an evidence-driven NP560 mask-ROM resource path experiment.

The real firmware reads a one-byte enable flag from ``10:D03F`` and a
50-byte NUL-terminated path from ``10:D040``.  No factory mask-ROM dump is
available, so this tool patches a *copy* of a reconstructed image and labels
the result as an experiment.  It does not alter QEMU or intercept filesystem
calls; the unmodified guest reader, stat, open, and header validation code all
remain in control.
"""

from __future__ import annotations

import argparse
from pathlib import Path


LOGICAL_BASE = 0x10D03E
RESOURCE_FLAG_ADDRESS = 0x10D03F
RESOURCE_PATH_ADDRESS = 0x10D040
RESOURCE_PATH_SIZE = 0x32
LOGICAL_END = RESOURCE_PATH_ADDRESS + RESOURCE_PATH_SIZE


def external_lane_storage(data: bytes) -> bytes:
    """Map even-aligned logical bytes to the DMCU external byte lane."""
    if len(data) & 1:
        raise ValueError("external-lane patch must contain whole words")
    stored = bytearray(data)
    for offset in range(0, len(stored), 2):
        stored[offset], stored[offset + 1] = stored[offset + 1], stored[offset]
    return bytes(stored)


def patch_image(image: bytes, path: str, encoding: str) -> tuple[bytes, bytes]:
    encoded = path.encode(encoding)
    if b"\0" in encoded:
        raise ValueError("resource path contains an embedded NUL")
    if len(encoded) >= RESOURCE_PATH_SIZE:
        raise ValueError(
            f"encoded path needs {len(encoded) + 1} bytes including NUL; "
            f"field holds {RESOURCE_PATH_SIZE}"
        )
    if len(image) < LOGICAL_END:
        raise ValueError(
            f"image is only 0x{len(image):x} bytes; patch ends at "
            f"0x{LOGICAL_END:x}"
        )

    logical = bytearray(LOGICAL_END - LOGICAL_BASE)
    logical[RESOURCE_FLAG_ADDRESS - LOGICAL_BASE] = 1
    path_offset = RESOURCE_PATH_ADDRESS - LOGICAL_BASE
    logical[path_offset:path_offset + len(encoded)] = encoded
    logical[path_offset + len(encoded)] = 0

    result = bytearray(image)
    result[LOGICAL_BASE:LOGICAL_END] = external_lane_storage(logical)
    return bytes(result), encoded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--path", required=True)
    parser.add_argument("--encoding", default="gb18030")
    args = parser.parse_args()

    if args.input.resolve() == args.output.resolve():
        parser.error("input and output must differ; keep the baseline image intact")
    patched, encoded = patch_image(
        args.input.read_bytes(), args.path, args.encoding
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    print(
        f"wrote {args.output} with experimental 10:D03F=1, "
        f"10:D040={encoded!r} ({len(encoded)} bytes)"
    )


if __name__ == "__main__":
    main()
