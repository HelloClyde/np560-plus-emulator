#!/usr/bin/env python3
"""Capture raw guest data-bank bytes from an isolated NP560 Web instance.

The Web API is read-only here. Each requested bank is saved separately so
stable-state comparisons can exclude changing audio buffers and clock data.
Do not point this diagnostic at another person's live session.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def get_json(url: str) -> dict:
    with urlopen(url, timeout=15) as response:
        return json.load(response)


def capture(root: str, output: Path, segments: list[int]) -> dict:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    health = get_json(root + "/api/health")
    if not health.get("qemu_alive") or health.get("phase") != "serving":
        raise RuntimeError("target Web/QEMU instance is not serving")
    banks = {}
    for segment in segments:
        state = get_json(
            f"{root}/api/state?source=data&base=0x{segment:02x}0000"
            "&size=65536&diagnostics=0"
        )
        if state.get("source") != "data" or state.get("format") != "packed":
            raise ValueError(f"unexpected data response for segment {segment:02x}")
        raw = base64.b64decode(state["frame"], validate=True)
        if len(raw) != 65536:
            raise ValueError(f"short data response for segment {segment:02x}")
        banks[f"{segment:02x}"] = raw
    output.mkdir(parents=True)
    manifest = {
        "schema": "np560-data-segment-snapshot-v1",
        "root": root,
        "run_id": health["run_id"],
        "bridge_pid": health["bridge_pid"],
        "segments": {},
    }
    for name, raw in banks.items():
        (output / f"{name}.bin").write_bytes(raw)
        manifest["segments"][name] = hashlib.sha256(raw).hexdigest()
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--segment", type=lambda value: int(value, 0),
                        action="append", dest="segments")
    args = parser.parse_args()
    segments = args.segments or [0, 0x50, 0x51, 0x52, 0x53]
    if any(not 0 <= value <= 0xff for value in segments):
        parser.error("segment must fit in one byte")
    if len(set(segments)) != len(segments):
        parser.error("segments must be unique")
    manifest = capture(args.root.rstrip("/"), args.output, segments)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
