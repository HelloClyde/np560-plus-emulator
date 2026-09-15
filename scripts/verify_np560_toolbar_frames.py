#!/usr/bin/env python3
"""Exact top-toolbar regression against the original, checksummed UPD bytes.

No captured LCD is used as a golden and no shift/permutation is fitted.
The expected selected category is an explicit test input, not inferred by
choosing whichever image happens to resemble the observed frame most closely.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from np560_upd import parse_update

WIDTH, HEIGHT = 240, 22
HEADER_SIZE = 10
RESOURCE_BYTES = HEADER_SIZE + WIDTH * HEIGHT // 2
# Source 3A:F3DA dispatch table / resident 1D:F3F6..F4CE resource trace.
POINTERS = {1: 0x24715A1, 2: 0x2470B47, 3: 0x2471FFB,
            4: 0x2472A55, 5: 0x24734AF}
LABELS = {1: "学习", 2: "辞典", 3: "网络", 4: "记事", 5: "系统"}


def decode_expected(resource: bytes) -> bytes:
    if len(resource) != RESOURCE_BYTES:
        raise ValueError("wrong toolbar resource length")
    if resource[:10] != bytes.fromhex("010400000000f0001600"):
        raise ValueError("unsupported toolbar header; refusing to guess")
    # Original flush sends nibble << 4, i.e. RAM code 2*nibble. With A7 the
    # positive glass exports that as darkness (0=light, 31=dark), not 31-code.
    return bytes(2 * value for byte in resource[HEADER_SIZE:]
                 for value in (byte >> 4, byte & 15))


def expected_from_package(package: Path) -> tuple[dict[int, bytes], dict]:
    parsed = parse_update(package)
    block, = [b for b in parsed.blocks if b.kind == "nand-image"]
    raw = package.read_bytes()
    expected = {}
    for index, pointer in POINTERS.items():
        offset = block.offset + pointer - HEADER_SIZE - 0x110000
        expected[index] = decode_expected(raw[offset:offset + RESOURCE_BYTES])
    return expected, {"package": str(package.resolve()),
                      "nand_package_sha256": block.sha256,
                      "pixel_mapping": "2 * packed_gray4; gray5-darkness; no alignment fitting"}


def compare(frame: bytes, expected: bytes) -> dict:
    if len(frame) != WIDTH * 120 or len(expected) != WIDTH * HEIGHT:
        raise ValueError("frame dimensions must be 240x120 / 240x22")
    observed = frame[:WIDTH * HEIGHT]
    different = [i for i, (a, b) in enumerate(zip(observed, expected)) if a != b]
    return {"passed": not different, "mismatch_pixels": len(different),
            "compared_pixels": len(expected),
            "first_mismatch_xy": [different[0] % WIDTH, different[0] // WIDTH]
            if different else None,
            "expected_sha256": hashlib.sha256(expected).hexdigest(),
            "observed_sha256": hashlib.sha256(observed).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--frame", action="append", required=True,
                        help="EXPECTED_CATEGORY:RAW_GRAY5_PATH (index 1..5)")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    expected, provenance = expected_from_package(args.package)
    reports = []
    for specification in args.frame:
        index_text, path_text = specification.split(":", 1)
        index = int(index_text)
        if index not in expected:
            parser.error("category must be 1..5")
        path = Path(path_text)
        reports.append({"category": index, "label": LABELS[index],
                        "path": str(path.resolve()),
                        **compare(path.read_bytes(), expected[index])})
    result = {"schema": "np560-package-toolbar-pixel-regression-v1",
              **provenance, "passed": all(r["passed"] for r in reports),
              "frames": reports}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    for report in reports:
        print(f"{report['category']} {report['label']}: "
              f"{report['mismatch_pixels']}/{WIDTH * HEIGHT} mismatches")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
