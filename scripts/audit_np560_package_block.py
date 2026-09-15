#!/usr/bin/env python3
"""Audit an explicit package-backed NAND block's byte lanes.

Default is read-only. An optional destination creates a diagnostic COPY with
one complete block reserialized from the checksummed official package, never
from rendered pixels. This is not a replacement for recovering USB/burn import.
Each existing page must match either original bytes or their word-lane encoding;
unknown/user-modified data is rejected before creating the destination.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import shutil
import struct
from pathlib import Path

from analyze_np560_ecc_checkpoint import ECC_OFFSETS, ECC_SIGNATURE, sector_descriptor
from np560_upd import parse_update, word_swap

HEADER = 64
PAGE = 2048
OOB = 64
BLOCK_PAGES = 64
BLOCK = PAGE * BLOCK_PAGES
PACKAGE_LOGICAL_START = 0x110000


def classify_page(current: bytes, serialized: bytes) -> str:
    if len(current) != PAGE or len(serialized) != PAGE:
        raise ValueError("page size must be 2048")
    encoded = word_swap(serialized)
    if current == serialized == encoded:
        return "both"
    if current == encoded:
        return "lane-encoded"
    if current == serialized:
        return "raw-package"
    raise ValueError("page differs from both package encodings; refusing overwrite")


def geometry(image: mmap.mmap) -> tuple[int, int]:
    if len(image) < HEADER or image[:8] != b"NP560N1\0":
        raise ValueError("not an NP560 checkpoint")
    version, header, page, oob, pages, blocks = struct.unpack_from("<6I", image, 8)
    data_size, oob_size = struct.unpack_from("<2Q", image, 32)
    if ((version, header, page, oob, pages) != (1, HEADER, PAGE, OOB, BLOCK_PAGES)
            or blocks <= 0 or data_size != blocks * BLOCK
            or oob_size != blocks * BLOCK_PAGES * OOB
            or len(image) != HEADER + data_size + oob_size):
        raise ValueError("incompatible checkpoint geometry")
    return blocks, data_size


def package_block(package: Path, logical_start: int) -> tuple[bytes, dict]:
    if logical_start % BLOCK or logical_start < PACKAGE_LOGICAL_START:
        raise ValueError("logical start must be a package-backed block boundary")
    parsed = parse_update(package)  # Includes vendor checksum verification.
    blocks = [b for b in parsed.blocks if b.kind == "nand-image"]
    if len(blocks) != 1:
        raise ValueError("expected exactly one NAND package block")
    block = blocks[0]
    offset = logical_start - PACKAGE_LOGICAL_START
    if offset + BLOCK > block.size:
        raise ValueError("requested block is not fully covered by package")
    with package.open("rb") as stream:
        stream.seek(block.offset + offset)
        data = stream.read(BLOCK)
    if len(data) != BLOCK:
        raise ValueError("short package read")
    return data, {
        "package": str(package.resolve()), "package_block_sha256": block.sha256,
        "package_slot": block.slot, "slot_offset": offset,
        "file_offset": block.offset + offset, "logical_start": logical_start,
        "logical_block_sha256": hashlib.sha256(data).hexdigest(),
    }


def audit_and_copy(source: Path, package: Path, logical_start: int,
                   physical_block: int, destination: Path | None = None) -> dict:
    if destination is not None and (
            destination.resolve() == source.resolve() or destination.exists()):
        raise ValueError("destination must be a new file, distinct from source")
    serialized, provenance = package_block(package, logical_start)
    expected = word_swap(serialized)
    with source.open("rb") as stream, mmap.mmap(
            stream.fileno(), 0, access=mmap.ACCESS_READ) as image:
        blocks, data_size = geometry(image)
        if not 0 <= physical_block < blocks:
            raise ValueError("physical block outside checkpoint")
        offset = HEADER + physical_block * BLOCK
        before = image[offset:offset + BLOCK]
        page_states = [classify_page(before[i:i + PAGE], serialized[i:i + PAGE])
                       for i in range(0, BLOCK, PAGE)]
        # Preserve the original signed ECC policy; unknown descriptors cannot
        # silently become valid merely because data bytes were replaced.
        ecc_updates = []
        for page in range(BLOCK_PAGES):
            if page_states[page] != "raw-package":
                continue
            for sector, ecc in enumerate(ECC_OFFSETS):
                a = (HEADER + data_size
                     + (physical_block * BLOCK_PAGES + page) * OOB + ecc)
                if struct.unpack_from("<H", image, a + 6)[0] != ECC_SIGNATURE:
                    raise ValueError("changed page lacks signed ECC descriptor")
                data_offset = page * PAGE + sector * 512
                ecc_updates.append((a, sector_descriptor(expected, data_offset)))
        report = {
            "schema": "np560-package-block-lanes-v1", "diagnostic_only": True,
            "source": str(source.resolve()), "physical_block": physical_block,
            **provenance, "page_states": page_states,
            "before_sha256": hashlib.sha256(before).hexdigest(),
            "expected_sha256": hashlib.sha256(expected).hexdigest(),
            "changed_bytes": sum(a != b for a, b in zip(before, expected)),
            "changed_pages": page_states.count("raw-package"),
            "destination": str(destination.resolve()) if destination else None,
            "checkpoint_rehash_required": destination is not None,
        }
        if destination is not None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            stream.seek(0)
            with destination.open("xb") as target:
                shutil.copyfileobj(stream, target, 1024 * 1024)
            with destination.open("r+b") as target, mmap.mmap(target.fileno(), 0) as out:
                # Also leave failed post-copy validation unmistakably invalid.
                out[48:56] = bytes(8)
                if out[offset:offset + BLOCK] != before:
                    raise ValueError("source changed during copy; output not accepted")
                # Invalidate before any mutation; only the native rehasher may
                # declare the completed data/OOB planes valid for boot.
                out[offset:offset + BLOCK] = expected
                for a, descriptor in ecc_updates:
                    out[a:a + 8] = descriptor
                out.flush()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--logical-start", type=lambda s: int(s, 0), required=True)
    parser.add_argument("--physical-block", type=lambda s: int(s, 0), required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = audit_and_copy(args.source, args.package, args.logical_start,
                            args.physical_block, args.destination)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "page_states"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
