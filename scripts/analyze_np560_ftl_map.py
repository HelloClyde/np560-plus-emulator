#!/usr/bin/env python3
"""Build a repeatable NP560 NAND FTL-tail and logical-image correlation map.

The vendor finalizer writes three copies of a 16-bit tag to bytes 58..63 of
the final OOB page in each active physical block.  This tool reports that
evidence without assuming the tag's full wear-leveling semantics.  When the
slot-3 logical NAND image is supplied, unique 2-KiB pages are correlated back
to their source offsets, making physical/logical placement regressions cheap
to check after each burner or ROM change.  When two or more tagged blocks
correlate, the report also proves or rejects the observed affine relation
between the OOB tag and raw logical-image byte offset.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import mmap
from pathlib import Path
import struct
from typing import Any


MAGIC = b"NP560N1\0"
MASKROM_MAGIC = b"MASKROM"
HEADER_SIZE = 64
MASKROM_HEADER_SIZE = 0x200
TAIL_OFFSET = 58
TAIL_SIZE = 6


def logical_payload(image: bytes) -> tuple[bytes, dict[str, Any]]:
    """Return QEMU-visible logical bytes and describe package-header removal."""
    if not image.startswith(MASKROM_MAGIC):
        return image, {"format": "raw-logical-stream", "header_stripped": 0}
    if len(image) < MASKROM_HEADER_SIZE:
        raise ValueError("truncated NP560 MASKROM image")
    declared_pages, field_24, declared_size = struct.unpack_from("<III", image, 0x20)
    if declared_size != len(image):
        raise ValueError(
            f"MASKROM size {declared_size} != logical image size {len(image)}"
        )
    expected_pages = (len(image) + 0x1ff) // 0x200
    if declared_pages != expected_pages:
        raise ValueError(
            f"MASKROM page count {declared_pages} != expected {expected_pages}"
        )
    return image[MASKROM_HEADER_SIZE:], {
        "format": "maskrom-logical-stream",
        "header_stripped": MASKROM_HEADER_SIZE,
        "signature": image[:0x20].split(b"\0", 1)[0].decode(
            "ascii", errors="replace",
        ),
        "declared_512_byte_pages": declared_pages,
        "field_24": field_24,
        "declared_size": declared_size,
    }


def parse_checkpoint_header(image: bytes | mmap.mmap) -> dict[str, int]:
    if len(image) < HEADER_SIZE or image[:8] != MAGIC:
        raise ValueError("not an NP560 NAND checkpoint")
    (
        version,
        header_size,
        page_data,
        page_oob,
        pages_per_block,
        blocks,
        data_size,
        oob_size,
        data_hash,
        oob_hash,
    ) = struct.unpack_from("<6I2Q2I", image, 8)
    if version != 1 or header_size != HEADER_SIZE:
        raise ValueError(f"unsupported checkpoint version/header {version}/{header_size}")
    pages = pages_per_block * blocks
    expected = header_size + data_size + oob_size
    if (
        page_data <= 0
        or page_oob < TAIL_OFFSET + TAIL_SIZE
        or pages_per_block <= 0
        or blocks <= 0
        or data_size != pages * page_data
        or oob_size != pages * page_oob
        or len(image) != expected
    ):
        raise ValueError("incompatible checkpoint geometry or file length")
    return {
        "version": version,
        "header_size": header_size,
        "page_data": page_data,
        "page_oob": page_oob,
        "pages_per_block": pages_per_block,
        "blocks": blocks,
        "pages": pages,
        "data_size": data_size,
        "oob_size": oob_size,
        "data_hash": data_hash,
        "oob_hash": oob_hash,
    }


def _digest(page: bytes) -> bytes:
    return hashlib.blake2s(page, digest_size=16).digest()


def logical_page_index(logical: bytes, page_size: int) -> dict[bytes, int]:
    """Return only uniquely occurring complete logical pages."""
    positions: dict[bytes, list[int]] = defaultdict(list)
    for offset in range(0, len(logical) - page_size + 1, page_size):
        page = logical[offset:offset + page_size]
        positions[_digest(page)].append(offset)
    return {
        digest: offsets[0]
        for digest, offsets in positions.items()
        if len(offsets) == 1
    }


def correlate_block(
    block_data: bytes,
    logical: bytes,
    unique_pages: dict[bytes, int],
    page_size: int,
) -> dict[str, Any] | None:
    candidate_bases: Counter[int] = Counter()
    exact_matches: list[tuple[int, int]] = []
    pages_per_block = len(block_data) // page_size
    for page_index in range(pages_per_block):
        start = page_index * page_size
        page = block_data[start:start + page_size]
        logical_offset = unique_pages.get(_digest(page))
        if logical_offset is None:
            continue
        # Defend against digest collisions and make the result an exact-byte
        # statement rather than a probabilistic hash claim.
        if logical[logical_offset:logical_offset + page_size] != page:
            continue
        exact_matches.append((page_index, logical_offset))
        candidate_bases[logical_offset - start] += 1
    if not candidate_bases:
        return None

    source_base, support = candidate_bases.most_common(1)[0]
    matched_indexes = [
        page_index
        for page_index, logical_offset in exact_matches
        if logical_offset - page_index * page_size == source_base
    ]
    exact_indexes = []
    for page_index in range(pages_per_block):
        logical_offset = source_base + page_index * page_size
        if logical_offset < 0 or logical_offset + page_size > len(logical):
            continue
        start = page_index * page_size
        if block_data[start:start + page_size] == logical[
            logical_offset:logical_offset + page_size
        ]:
            exact_indexes.append(page_index)
    return {
        "inferred_source_base": source_base,
        "inferred_source_base_hex": f"0x{source_base:X}",
        "unique_page_support": support,
        "unique_matched_pages": matched_indexes,
        "exact_matched_pages": exact_indexes,
        "exact_matched_bytes": len(exact_indexes) * page_size,
    }


def infer_tag_source_relation(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Describe an exact affine tag/source relation, if the evidence has one.

    The relation is deliberately expressed in raw image bytes.  It does not
    rename the vendor tag as a logical block number or infer wear-level policy.
    """
    pairs = sorted(
        (
            entry["tail_tag"],
            entry["logical_image_correlation"]["inferred_source_base"],
            entry["physical_block"],
        )
        for entry in entries
        if entry.get("logical_image_correlation") is not None
    )
    if len(pairs) < 2:
        return None

    anchor_tag, anchor_source, _ = pairs[0]
    strides = {
        (source - anchor_source) // (tag - anchor_tag)
        for tag, source, _ in pairs[1:]
        if tag != anchor_tag and
        (source - anchor_source) % (tag - anchor_tag) == 0
    }
    stride = next(iter(strides)) if len(strides) == 1 else None
    mismatches: list[dict[str, int | str]] = []
    if stride is not None:
        for tag, source, physical_block in pairs:
            expected = anchor_source + (tag - anchor_tag) * stride
            if source != expected:
                mismatches.append({
                    "tail_tag": tag,
                    "tail_tag_hex": f"0x{tag:04X}",
                    "physical_block": physical_block,
                    "observed_source_base": source,
                    "expected_source_base": expected,
                })

    tags = [tag for tag, _, _ in pairs]
    unique_tags = sorted(set(tags))
    tag_set = set(unique_tags)
    missing_tags = [
        tag for tag in range(unique_tags[0], unique_tags[-1] + 1)
        if tag not in tag_set
    ]
    return {
        "evidence_pairs": len(pairs),
        "unique_tags": len(unique_tags),
        "duplicate_correlated_tags": len(tags) - len(unique_tags),
        "tag_min": unique_tags[0],
        "tag_min_hex": f"0x{unique_tags[0]:04X}",
        "tag_max": unique_tags[-1],
        "tag_max_hex": f"0x{unique_tags[-1]:04X}",
        "missing_tags": missing_tags,
        "anchor_tag": anchor_tag,
        "anchor_tag_hex": f"0x{anchor_tag:04X}",
        "anchor_source_base": anchor_source,
        "anchor_source_base_hex": f"0x{anchor_source:X}",
        "source_bytes_per_tag": stride,
        "source_bytes_per_tag_hex": (
            f"0x{stride:X}" if stride is not None else None
        ),
        "exact_affine_relation": stride is not None and not mismatches,
        "mismatches": mismatches,
    }


def analyse(
    image: bytes | mmap.mmap,
    logical: bytes | None = None,
) -> dict[str, Any]:
    geometry = parse_checkpoint_header(image)
    header_size = geometry["header_size"]
    page_data = geometry["page_data"]
    page_oob = geometry["page_oob"]
    pages_per_block = geometry["pages_per_block"]
    data_size = geometry["data_size"]
    oob_base = header_size + data_size
    block_data_size = pages_per_block * page_data

    unique_pages = (
        logical_page_index(logical, page_data) if logical is not None else {}
    )
    entries: list[dict[str, Any]] = []
    invalid_tails: list[dict[str, Any]] = []
    tags: dict[int, list[int]] = defaultdict(list)
    correlated_blocks = 0
    correlated_bytes = 0

    for block in range(geometry["blocks"]):
        final_page = block * pages_per_block + pages_per_block - 1
        oob_offset = oob_base + final_page * page_oob
        final_oob = image[oob_offset:oob_offset + page_oob]
        tail = bytes(final_oob[TAIL_OFFSET:TAIL_OFFSET + TAIL_SIZE])
        values = struct.unpack("<3H", tail)
        if tail == b"\xff" * TAIL_SIZE:
            continue
        if values[0] != values[1] or values[1] != values[2]:
            invalid_tails.append({
                "physical_block": block,
                "physical_block_hex": f"0x{block:04X}",
                "tail_hex": tail.hex(),
                "tail_words": list(values),
            })
            continue

        tag = values[0]
        tags[tag].append(block)
        entry: dict[str, Any] = {
            "physical_block": block,
            "physical_block_hex": f"0x{block:04X}",
            "tail_tag": tag,
            "tail_tag_hex": f"0x{tag:04X}",
            "final_oob_prefix_hex": bytes(final_oob[:TAIL_OFFSET]).hex(),
        }
        if logical is not None:
            block_offset = header_size + block * block_data_size
            block_bytes = bytes(image[block_offset:block_offset + block_data_size])
            correlation = correlate_block(
                block_bytes, logical, unique_pages, page_data
            )
            entry["logical_image_correlation"] = correlation
            if correlation is not None:
                correlated_blocks += 1
                correlated_bytes += correlation["exact_matched_bytes"]
        entries.append(entry)

    duplicate_tags = {
        f"0x{tag:04X}": blocks
        for tag, blocks in sorted(tags.items())
        if len(blocks) > 1
    }
    nonzero_entries = [entry for entry in entries if entry["tail_tag"] != 0]
    result: dict[str, Any] = {
        "schema": "np560-ftl-tail-map-v1",
        "claim": (
            "observed triplicated final-page OOB tags; full NFTL generation "
            "and wear-level semantics are not inferred"
        ),
        "geometry": geometry,
        "tagged_blocks": len(entries),
        "nonzero_tagged_blocks": len(nonzero_entries),
        "invalid_triplicated_tails": invalid_tails,
        "duplicate_tags": duplicate_tags,
        "entries": entries,
    }
    if logical is not None:
        result["logical_image"] = {
            "bytes": len(logical),
            "sha256": hashlib.sha256(logical).hexdigest(),
            "complete_pages": len(logical) // page_data,
            "unique_page_digests": len(unique_pages),
            "correlated_blocks": correlated_blocks,
            "correlated_exact_bytes": correlated_bytes,
        }
        result["tag_source_relation"] = infer_tag_source_relation(entries)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--logical-image", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    logical = None
    logical_metadata = None
    if args.logical_image:
        logical, logical_metadata = logical_payload(args.logical_image.read_bytes())
    with args.checkpoint.open("rb") as source:
        image = mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            result = analyse(image, logical)
        finally:
            image.close()
    if logical_metadata is not None:
        result["logical_image"].update(logical_metadata)

    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    summary = {
        "schema": result["schema"],
        "tagged_blocks": result["tagged_blocks"],
        "nonzero_tagged_blocks": result["nonzero_tagged_blocks"],
        "invalid_triplicated_tails": len(result["invalid_triplicated_tails"]),
        "duplicate_tags": len(result["duplicate_tags"]),
    }
    if "logical_image" in result:
        summary["logical_image"] = result["logical_image"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
