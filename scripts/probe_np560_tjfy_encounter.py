#!/usr/bin/env python3
"""Walk the original Tianjiang map until its guest enters a random battle.

Only physical matrix contacts are sent.  Read-only guest mode snapshots stop
the walk before a subsequent direction could be interpreted as a battle key.
This is a bounded diagnostic for an isolated Web instance, not a game patch.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

try:
    from .probe_np560_matrix_route import RouteStep, WebBridge, replay_step
except ImportError:  # Direct scripts/ execution.
    from probe_np560_matrix_route import RouteStep, WebBridge, replay_step


def guest_mode(snapshot: dict) -> int:
    if snapshot.get("format") != "packed" or snapshot.get("source") != "data":
        raise ValueError("expected a raw guest data snapshot")
    raw = base64.b64decode(snapshot["frame"], validate=True)
    if len(raw) != 0x36:
        raise ValueError("unexpected game-state snapshot length")
    return int.from_bytes(raw[0x34:0x36], "little")


def read_mode(web: WebBridge) -> int:
    return guest_mode(web.get_json(
        "/api/state?source=data&base=0x527900&size=0x36&diagnostics=0"))


def read_map(web: WebBridge) -> int:
    return int(web.get_json("/api/key-status")["current_map_index"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8781")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-steps", type=int, default=160)
    parser.add_argument("--settle", type=float, default=0.35)
    parser.add_argument("--expected-map", type=int,
                        help="reject a stale load or unintended map before walking")
    args = parser.parse_args()
    if args.max_steps < 1 or args.settle < 0:
        parser.error("--max-steps must be positive and --settle nonnegative")
    if args.output.exists():
        parser.error(f"report already exists: {args.output}")

    web = WebBridge(args.root, 5.0)
    web.set_matrix(None)
    before = read_mode(web)
    if before != 1:
        parser.error(f"expected map mode 1 before walking; observed {before}")
    initial_map = read_map(web)
    if args.expected_map is not None and initial_map != args.expected_map:
        parser.error(f"expected map {args.expected_map} before walking; "
                     f"observed {initial_map}")
    report = {"schema": "np560-tjfy-encounter-v1", "root": args.root,
              "initial_mode": before, "initial_map": initial_map, "steps": []}
    result_code = 2
    try:
        for index in range(args.max_steps):
            before_step = read_mode(web)
            if before_step == 3:
                # A random encounter may finish its transition after the
                # preceding key's guest acknowledgement and settle window.
                # No further direction must be delivered in battle mode.
                report["outcome"] = "battle_after_settle"
                result_code = 0
                break
            if before_step != 1:
                report["outcome"] = "other_mode_before_step"
                break
            left = index % 2 == 0
            step = RouteStep(f"{'left' if left else 'right'}-{index + 1}",
                             45 if left else 29, 0x80 if left else 0x81)
            result = replay_step(web, step, press_timeout=3.0,
                                 release_timeout=3.0, poll_interval=0.01,
                                 settle=args.settle)
            mode = read_mode(web)
            report["steps"].append({"step": index + 1,
                                    "matrix_index": step.matrix_index,
                                    "event": step.expected_event,
                                    "maps_before": result["maps_before"],
                                    "maps_after": result["maps_after"],
                                    "mode_after": mode})
            print(f"{index + 1}: M{step.matrix_index} mode={mode}", flush=True)
            if mode == 3:
                report["outcome"] = "battle"
                result_code = 0
                break
            if mode != 1:
                report["outcome"] = "other_mode"
                break
        else:
            report["outcome"] = "step_limit"
    except Exception as error:
        report["outcome"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["final_mode"] = read_mode(web)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
