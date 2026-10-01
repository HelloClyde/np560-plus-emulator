#!/usr/bin/env python3
"""Find stable guest bytes distinguishing two NPE audio states.

All six captures must come from one isolated QEMU run. This is a correlation
filter, not proof that a returned address causes or saves the audio choice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def read_capture(path: Path) -> tuple[dict, dict[str, bytes]]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "np560-data-segment-snapshot-v1":
        raise ValueError(f"{path}: unexpected snapshot schema")
    banks = {}
    for name, digest in manifest["segments"].items():
        raw = (path / f"{name}.bin").read_bytes()
        if len(raw) != 65536 or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"{path}: corrupt segment {name}")
        banks[name] = raw
    return manifest, banks


def classify(cold1: bytes, cold2: bytes, on1: bytes, on2: bytes,
             off1: bytes, off2: bytes) -> list[dict]:
    if len({len(item) for item in (cold1, cold2, on1, on2, off1, off2)}) != 1:
        raise ValueError("snapshot banks have different sizes")
    candidates = []
    for offset, (c1, c2, a1, a2, b1, b2) in enumerate(zip(
            cold1, cold2, on1, on2, off1, off2)):
        if a1 != a2 or b1 != b2 or a1 == b1:
            continue
        candidates.append({
            "offset": offset,
            "on": a1,
            "off": b1,
            "cold_stable": c1 == c2,
            "cold": c1 if c1 == c2 else None,
            "cold_matches_off": c1 == c2 == b1,
            "cold_matches_on": c1 == c2 == a1,
        })
    return candidates


def compare(paths: list[Path]) -> dict:
    captures = [read_capture(path) for path in paths]
    run_ids = {manifest["run_id"] for manifest, _ in captures}
    segment_sets = {tuple(sorted(banks)) for _, banks in captures}
    if len(run_ids) != 1 or len(segment_sets) != 1:
        raise ValueError("captures must share one QEMU run and segment set")
    result = {
        "schema": "np560-stable-data-state-compare-v1",
        "scope": "stable on/off correlation across sequential non-atomic reads",
        "run_id": run_ids.pop(),
        "captures": [str(path) for path in paths],
        "segments": {},
    }
    for name in sorted(captures[0][1]):
        candidates = classify(*(banks[name] for _, banks in captures))
        result["segments"][name] = {
            "stable_on_off": len(candidates),
            "cold_matches_off": sum(item["cold_matches_off"] for item in candidates),
            "cold_matches_on": sum(item["cold_matches_on"] for item in candidates),
            "candidates": candidates,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cold1", type=Path)
    parser.add_argument("cold2", type=Path)
    parser.add_argument("on1", type=Path)
    parser.add_argument("on2", type=Path)
    parser.add_argument("off1", type=Path)
    parser.add_argument("off2", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite output")
    result = compare([args.cold1, args.cold2, args.on1, args.on2,
                      args.off1, args.off2])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {key: value for key, value in data.items()
                             if key != "candidates"}
                      for name, data in result["segments"].items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
