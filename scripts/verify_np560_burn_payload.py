#!/usr/bin/env python3
"""Verify package bytes via finalizer OOB tags, without searching/fitting data.

This is an offline check of the evidenced 2-KiB NAND/256-sector FTL layout.
It does not replace guest FTL readback, or verify the checkpoint's full FNV.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import struct
from pathlib import Path

from analyze_np560_ecc_checkpoint import ECC_OFFSETS, sector_descriptor
from analyze_np560_ftl_map import parse_checkpoint_header
from np560_upd import parse_update


def verify_payload(image, payload: bytes, logical_start: int = 0x110000) -> dict:
    geometry = parse_checkpoint_header(image)
    if (geometry["page_data"], geometry["page_oob"], geometry["pages_per_block"]) != (2048, 64, 64):
        raise ValueError("only the evidenced 2048+64, 64-page geometry is supported")
    if not payload or logical_start < 0 or logical_start % 512:
        raise ValueError("payload must be nonempty and start on a logical sector boundary")
    header = geometry["header_size"]
    oob_base = header + geometry["data_size"]
    block_size = 2048 * 64
    factory = image[header + 63 * 2048:header + 63 * 2048 + 32]
    if factory[:2] != b"\xfe\xca" or factory[6:8] != b"BK":
        raise ValueError("factory partition record signature not found")
    partition_base = struct.unpack_from("<H", factory, 2)[0]
    tags = {}
    for block in range(geometry["blocks"]):
        pos = oob_base + (block * 64 + 63) * 64 + 58
        words = struct.unpack_from("<3H", image, pos)
        if words[0] == words[1] == words[2] and words[0] not in (0, 0xFFFF):
            tags.setdefault(words[0], []).append(block)
    padded = payload + b"\xff" * (-len(payload) % 512)
    errors = []
    mismatches = 0
    ecc_mismatches = 0
    checked = 0
    digest = hashlib.sha256()
    mapping = {}
    for offset in range(0, len(padded), 512):
        logical = logical_start + offset
        tag = partition_base + logical // block_size
        candidates = tags.get(tag, [])
        if len(candidates) != 1:
            if tag not in mapping:
                errors.append({"tag": tag, "physical_blocks": candidates,
                               "error": "missing or ambiguous mapping; no candidate selected"})
                mapping[tag] = None
            continue
        block = candidates[0]
        mapping[tag] = block
        physical = block * block_size + logical % block_size
        data = image[header + physical:header + physical + 512]
        # Inverse of the DMCU byte-bus backing representation. No searching,
        # candidate alignment, header stripping, or image-specific exceptions.
        logical_data = bytearray(512)
        logical_data[0::2] = data[1::2]
        logical_data[1::2] = data[0::2]
        expected = padded[offset:offset + 512]
        bad = sum(a != b for a, b in zip(logical_data, expected))
        if bad and len(errors) < 16:
            errors.append({"payload_offset": offset, "physical": physical,
                           "error": "byte mismatch", "bytes": bad})
        mismatches += bad
        page, sector = divmod(physical, 2048)
        sector //= 512
        ecc_pos = oob_base + page * 64 + ECC_OFFSETS[sector]
        ecc_ok = image[ecc_pos:ecc_pos + 8] == sector_descriptor(data)
        if not ecc_ok and len(errors) < 16:
            errors.append({"payload_offset": offset, "physical": physical,
                           "error": "missing or mismatched sector ECC"})
        ecc_mismatches += not ecc_ok
        digest.update(logical_data[:min(512, max(0, len(payload) - offset))])
        checked += 512
    passed = checked == len(padded) and not mismatches and not ecc_mismatches
    return {"schema": "np560-burn-payload-verify-v1", "passed": passed,
            "scope": "offline factory/OOB mapping, full selected payload and sector ECC",
            "guest_ftl_readback_verified": False, "checkpoint_fnv_verified": False,
            "logical_start": logical_start, "factory_partition_base": partition_base,
            "payload_bytes": len(payload), "padded_bytes": len(padded),
            "checked_bytes": checked, "mismatch_bytes": mismatches,
            "checked_ecc_sectors": checked // 512, "mismatch_ecc_sectors": ecc_mismatches,
            "expected_sha256": hashlib.sha256(payload).hexdigest(),
            "observed_sha256": digest.hexdigest() if checked == len(padded) else None,
            "mapping": [{"tag": tag, "physical_block": block} for tag, block in sorted(mapping.items())],
            "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--limit-bytes", type=lambda value: int(value, 0),
                        help="diagnostic: check only this explicit prefix")
    args = parser.parse_args()
    package = parse_update(args.package)
    block = next(b for b in package.blocks if b.slot == 3 and b.kind == "nand-image")
    size = block.size if args.limit_bytes is None else args.limit_bytes
    if not 0 < size <= block.size:
        parser.error("--limit-bytes must be in 1..slot-3 size")
    with args.package.open("rb") as source:
        source.seek(block.offset)
        payload = source.read(size)
    with args.checkpoint.open("rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as image:
        report = verify_payload(image, payload)
    report.update(checkpoint=str(args.checkpoint.resolve()), package=str(args.package.resolve()),
                  package_slot_sha256=block.sha256, full_package_payload=size == block.size)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps({k: v for k, v in report.items() if k != "mapping"}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
