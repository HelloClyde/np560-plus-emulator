"""Read-only correlation of NPE decoded-frame count and original PRG time.

Bracket each RAM snapshot with two HLE counter reads. Only equal before/after
stream identity and frame counts are treated as a stable observation; a Web
request is not an atomic guest snapshot. No keys or guest memory are changed.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import re
import struct
import time
from urllib.request import urlopen


HLE_RE = re.compile(r"stream-frames=(\d+) calls=(\d+),(\d+),")
RAM_BASE = 0x512828
RAM_SIZE = 0x20


def get_json(url: str) -> dict:
    with urlopen(url, timeout=3) as response:
        return json.load(response)


def parse_hle(state: str) -> tuple[int, int]:
    match = HLE_RE.search(state)
    if match is None:
        raise ValueError(f"missing NPE stream counters: {state}")
    return int(match.group(3)), int(match.group(1))


def parse_prg_time(raw: bytes) -> dict:
    if len(raw) != RAM_SIZE:
        raise ValueError(f"NPE time snapshot is {len(raw)} bytes, expected {RAM_SIZE}")
    words = struct.unpack("<16H", raw)
    at = lambda address: words[(address - 0x2828) // 2]
    total_ms = (at(0x283e) << 16) | at(0x2840)
    current_ms = (at(0x2842) << 16) | at(0x2844)
    return {
        "format": at(0x282a),
        "declared_frames": at(0x282c),
        "bit_rate": at(0x283a),
        "total_ms": total_ms,
        "current_ms": current_ms,
        "remaining_ms": total_ms - current_ms,
    }


def sample(root: str) -> dict:
    before = parse_hle(get_json(root + "/api/npe-hle-state")["state"])
    state = get_json(root + f"/api/state?source=data&base={RAM_BASE}&size={RAM_SIZE}&diagnostics=0")
    prg = parse_prg_time(base64.b64decode(state["frame"], validate=True))
    after = parse_hle(get_json(root + "/api/npe-hle-state")["state"])
    return {
        "wall_time": time.time(),
        "init_calls_before": before[0],
        "stream_frames_before": before[1],
        "init_calls_after": after[0],
        "stream_frames_after": after[1],
        "stable": before == after,
        **prg,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8891")
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--interval", type=float, default=0.02)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.duration <= 0 or args.interval <= 0 or args.output.exists():
        parser.error("duration/interval must be positive and output must not exist")
    root = args.root.rstrip("/")
    rows = []
    deadline = time.monotonic() + args.duration
    while time.monotonic() < deadline:
        rows.append(sample(root))
        time.sleep(args.interval)
    stable = [row for row in rows if row["stable"]]
    boundary = [row for row in stable if row["stream_frames_after"] >= 1980]
    result = {
        "schema": "np560-npe-loop-boundary-v1",
        "root": root,
        "samples": rows,
        "stable_samples": len(stable),
        "near_end_samples": len(boundary),
        "init_calls_range": [rows[0]["init_calls_before"], rows[-1]["init_calls_after"]]
        if rows else None,
        "near_end_range": [min(row["stream_frames_after"] for row in boundary),
                           max(row["stream_frames_after"] for row in boundary)]
        if boundary else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key != "samples"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
