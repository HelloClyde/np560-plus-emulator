#!/usr/bin/env python3
"""Prove the native one-shot NPE object action at a recovered target.

The probe starts with the running avatar already facing the target.  It takes
one stable pre-action checkpoint, sends two real M53/0x86 matrix edges, and
proves that original guest code commits the first edge and rejects the second
through its completion flag.  It never writes guest RAM or redirects control.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import time
from typing import Any

try:
    from explore_np560_npe_map import (
        explorer_state,
        faces_world_target,
        wait_for_stable_frame,
    )
    from monitor_np560_npe_input_semantics import (
        capture_completed_checkpoint,
    )
    from monitor_np560_npe_play_session import run_step, write_manifest
    from probe_np560_matrix_route import (
        RouteStep,
        WebBridge,
        raise_if_key_status_faulted,
    )
    from probe_np560_npe_unbanked_sfr import (
        parse_stream_position_inventory,
        stream_position_delta,
    )
except ModuleNotFoundError:  # imported as scripts.probe_...
    from .explore_np560_npe_map import (
        explorer_state,
        faces_world_target,
        wait_for_stable_frame,
    )
    from .monitor_np560_npe_input_semantics import (
        capture_completed_checkpoint,
    )
    from .monitor_np560_npe_play_session import run_step, write_manifest
    from .probe_np560_matrix_route import (
        RouteStep,
        WebBridge,
        raise_if_key_status_faulted,
    )
    from .probe_np560_npe_unbanked_sfr import (
        parse_stream_position_inventory,
        stream_position_delta,
    )


ACTION_STEP = RouteStep("ObjectAction", 53, 0x86)
COUNTERS = (
    "primary_action_selector_calls",
    "primary_action_selector_returns",
    "primary_action_object_guard_checks",
    "primary_action_object_guard_passes",
    "primary_action_object_guard_rejects",
    "primary_action_object_commits",
)
MEMORY_RANGES = (
    ("52", 0x520000, 0x10000),
    ("53", 0x530000, 0x10000),
)


def action_deltas(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, int]:
    return {
        name: int(after[name]) - int(before[name])
        for name in COUNTERS
    }


def capture_stream_position(web: WebBridge) -> dict[str, Any]:
    state = web.get_json("/api/state")
    return parse_stream_position_inventory(str(state.get("registers", "")))


def require_delta(
    deltas: dict[str, int],
    name: str,
    expected: int,
) -> None:
    actual = deltas[name]
    if actual != expected:
        raise RuntimeError(f"{name} delta is {actual}, expected {expected}")


def capture_memory_ranges(
    web: WebBridge,
    output_dir: Path,
    prefix: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
    summaries: dict[str, dict[str, Any]] = {}
    captures: dict[str, bytes] = {}
    output_dir.mkdir(parents=True, exist_ok=True)
    for label, base, size in MEMORY_RANGES:
        payload = web.get_json(
            f"/api/state?source=memory&base=0x{base:x}&size=0x{size:x}"
        )
        data = base64.b64decode(str(payload.get("frame", "")), validate=True)
        if len(data) != size:
            raise ValueError(
                f"memory range {label} returned {len(data)} bytes, "
                f"expected {size}"
            )
        path = output_dir / f"{prefix}-{label}.bin"
        path.write_bytes(data)
        summaries[label] = {
            "base": base,
            "bytes": size,
            "sha256": hashlib.sha256(data).hexdigest(),
            "file": path.name,
        }
        captures[label] = data
    return summaries, captures


def changed_offsets(before: bytes, after: bytes) -> list[int]:
    if len(before) != len(after):
        raise ValueError("memory snapshots have different sizes")
    return [
        offset
        for offset, (old, new) in enumerate(zip(before, after))
        if old != new
    ]


def contiguous_runs(offsets: list[int]) -> list[tuple[int, int]]:
    if not offsets:
        return []
    runs: list[tuple[int, int]] = []
    start = previous = offsets[0]
    for offset in offsets[1:]:
        if offset != previous + 1:
            runs.append((start, previous + 1))
            start = offset
        previous = offset
    runs.append((start, previous + 1))
    return runs


def memory_diff_summary(
    before: dict[str, bytes],
    after_first: dict[str, bytes],
    before_second: dict[str, bytes],
    after_second: dict[str, bytes],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    bases = {label: base for label, base, _ in MEMORY_RANGES}
    for label in before:
        first = changed_offsets(before[label], after_first[label])
        delay = changed_offsets(after_first[label], before_second[label])
        second = changed_offsets(before_second[label], after_second[label])
        second_set = set(second)
        first_only = [offset for offset in first if offset not in second_set]
        result[label] = {
            "first_action_changed_bytes": len(first),
            "second_action_changed_bytes": len(second),
            "post_first_action_delay_changed_bytes": len(delay),
            "first_action_only_changed_bytes": len(first_only),
            "first_action_runs": [list(run) for run in contiguous_runs(first)],
            "second_action_runs": [list(run) for run in contiguous_runs(second)],
            "post_first_action_delay_runs": [
                list(run) for run in contiguous_runs(delay)
            ],
            "first_action_only_sample": [
                {
                    "physical": bases[label] + offset,
                    "logical_byte": (bases[label] + offset) ^ 1,
                    "before": before[label][offset],
                    "after": after_first[label][offset],
                }
                for offset in first_only[:1024]
            ],
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8801")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target-world-x", type=int, default=1)
    parser.add_argument("--target-world-y", type=int, default=6)
    parser.add_argument("--request-timeout", type=float, default=30.0)
    parser.add_argument("--transition-timeout", type=float, default=90.0)
    parser.add_argument("--press-timeout", type=float, default=15.0)
    parser.add_argument("--release-timeout", type=float, default=20.0)
    parser.add_argument("--poll-interval", type=float, default=0.03)
    parser.add_argument("--settle", type=float, default=0.20)
    parser.add_argument("--pulse-duration", type=float, default=0.20)
    parser.add_argument("--stable-duration", type=float, default=1.0)
    parser.add_argument(
        "--post-action-delay", type=float, default=5.5,
        help=(
            "minimum delay before the repeat action, covering the guest's "
            "0x1388/5000 ms item UI state (default: 5.5s)"
        ),
    )
    args = parser.parse_args()
    if min(
        args.request_timeout,
        args.transition_timeout,
        args.press_timeout,
        args.release_timeout,
        args.poll_interval,
        args.pulse_duration,
        args.stable_duration,
        args.post_action_delay,
    ) <= 0 or args.settle < 0:
        parser.error("timeouts, pulse and stable duration must be positive")

    web = WebBridge(args.root, args.request_timeout)
    target = (args.target_world_x, args.target_world_y)
    manifest: dict[str, Any] = {
        "schema": "np560-npe-object-action-v1",
        "root": args.root,
        "target_world": {"x": target[0], "y": target[1]},
        "complete": False,
        "actions": [],
        "checkpoints": [],
    }
    write_manifest(args.output_dir, manifest)

    try:
        web.set_matrix(None)
        before = web.get_json("/api/key-status")
        raise_if_key_status_faulted(web, before)
        position = explorer_state(before)
        if not faces_world_target(position, target):
            raise RuntimeError(
                f"avatar state {position!r} does not face world target {target}"
            )
        if int(before["primary_action_object_commits"]) != 0:
            raise RuntimeError("object action was already committed")

        wait_for_stable_frame(
            web,
            stable_duration=args.stable_duration,
            timeout=args.transition_timeout,
            poll_interval=max(args.poll_interval, 0.05),
        )
        pre = capture_completed_checkpoint(
            web, args.output_dir, "00-before-action",
        )
        pre_stream = capture_stream_position(web)
        pre_memory_summary, pre_memory = capture_memory_ranges(
            web, args.output_dir, "00-before-action",
        )
        manifest["before_status"] = before
        manifest["position"] = {
            "x": position[0],
            "y": position[1],
            "map_index": position[2],
            "offset_x": position[3],
            "offset_y": position[4],
            "direction": position[5],
        }
        manifest["checkpoints"].append({
            "label": "before-action",
            "frame_sha256": pre["frame"]["sha256"],
        })
        manifest["memory_checkpoints"] = [{
            "label": "before-action",
            "ranges": pre_memory_summary,
        }]
        manifest["stream_position_checkpoints"] = [{
            "label": "before-action",
            "inventory": pre_stream,
        }]
        manifest["stream_position_deltas"] = []
        write_manifest(args.output_dir, manifest)

        first_edge = run_step(
            web,
            ACTION_STEP,
            press_timeout=args.press_timeout,
            release_timeout=args.release_timeout,
            poll_interval=args.poll_interval,
            settle=args.settle,
            use_bounded_status=True,
            pulse_duration=args.pulse_duration,
        )
        first_status = web.get_json("/api/key-status")
        raise_if_key_status_faulted(web, first_status)
        first_delta = action_deltas(before, first_status)
        for name in (
            "primary_action_selector_calls",
            "primary_action_selector_returns",
            "primary_action_object_guard_checks",
            "primary_action_object_guard_passes",
            "primary_action_object_commits",
        ):
            require_delta(first_delta, name, 1)
        require_delta(
            first_delta, "primary_action_object_guard_rejects", 0,
        )
        if int(first_status["primary_action_selector_result"]) != 0:
            raise RuntimeError("first action did not select object 0")
        if int(first_status["primary_action_object_guard_value"]) != 0:
            raise RuntimeError("first action did not observe guard value 0")
        if int(first_status["primary_action_object_commit_flag"]) != 1:
            raise RuntimeError("first action did not commit flag value 1")

        first_checkpoint = capture_completed_checkpoint(
            web, args.output_dir, "01-after-first-action-immediate",
        )
        first_memory_summary, first_memory = capture_memory_ranges(
            web, args.output_dir, "01-after-first-action-immediate",
        )
        first_stream = capture_stream_position(web)
        manifest["actions"].append({
            "label": "first-action",
            "edge": first_edge,
            "deltas": first_delta,
            "status": first_status,
        })
        manifest["checkpoints"].append({
            "label": "after-first-action",
            "frame_sha256": first_checkpoint["frame"]["sha256"],
        })
        manifest["memory_checkpoints"].append({
            "label": "after-first-action",
            "ranges": first_memory_summary,
        })
        manifest["stream_position_checkpoints"].append({
            "label": "after-first-action-immediate",
            "inventory": first_stream,
        })
        manifest["stream_position_deltas"].append({
            "from": "before-action",
            "to": "after-first-action-immediate",
            "delta": stream_position_delta(
                {"stream_position": pre_stream},
                {"stream_position": first_stream},
            ),
        })
        write_manifest(args.output_dir, manifest)

        # Object type 1 sets a 0x1388/5000 ms guest UI state.  Do not let its
        # delayed callback contaminate the repeat-action comparison.
        time.sleep(args.post_action_delay)
        wait_for_stable_frame(
            web,
            stable_duration=args.stable_duration,
            timeout=args.transition_timeout,
            poll_interval=max(args.poll_interval, 0.05),
        )
        settled_checkpoint = capture_completed_checkpoint(
            web, args.output_dir, "02-before-second-action-settled",
        )
        settled_memory_summary, settled_memory = capture_memory_ranges(
            web, args.output_dir, "02-before-second-action-settled",
        )
        settled_stream = capture_stream_position(web)
        manifest["checkpoints"].append({
            "label": "before-second-action-settled",
            "frame_sha256": settled_checkpoint["frame"]["sha256"],
        })
        manifest["memory_checkpoints"].append({
            "label": "before-second-action-settled",
            "ranges": settled_memory_summary,
        })
        manifest["stream_position_checkpoints"].append({
            "label": "before-second-action-settled",
            "inventory": settled_stream,
        })
        manifest["stream_position_deltas"].append({
            "from": "after-first-action-immediate",
            "to": "before-second-action-settled",
            "delta": stream_position_delta(
                {"stream_position": first_stream},
                {"stream_position": settled_stream},
            ),
        })
        write_manifest(args.output_dir, manifest)

        second_edge = run_step(
            web,
            ACTION_STEP,
            press_timeout=args.press_timeout,
            release_timeout=args.release_timeout,
            poll_interval=args.poll_interval,
            settle=args.settle,
            use_bounded_status=True,
            pulse_duration=args.pulse_duration,
        )
        second_status = web.get_json("/api/key-status")
        raise_if_key_status_faulted(web, second_status)
        second_delta = action_deltas(first_status, second_status)
        for name in (
            "primary_action_selector_calls",
            "primary_action_selector_returns",
            "primary_action_object_guard_checks",
            "primary_action_object_guard_rejects",
        ):
            require_delta(second_delta, name, 1)
        require_delta(
            second_delta, "primary_action_object_guard_passes", 0,
        )
        require_delta(second_delta, "primary_action_object_commits", 0)
        if int(second_status["primary_action_selector_result"]) != 0:
            raise RuntimeError("second action did not select object 0")
        if int(second_status["primary_action_object_guard_value"]) != 1:
            raise RuntimeError("second action did not observe guard value 1")

        wait_for_stable_frame(
            web,
            stable_duration=args.stable_duration,
            timeout=args.transition_timeout,
            poll_interval=max(args.poll_interval, 0.05),
        )
        second_checkpoint = capture_completed_checkpoint(
            web, args.output_dir, "03-after-second-action",
        )
        second_memory_summary, second_memory = capture_memory_ranges(
            web, args.output_dir, "03-after-second-action",
        )
        second_stream = capture_stream_position(web)
        manifest["actions"].append({
            "label": "second-action",
            "edge": second_edge,
            "deltas": second_delta,
            "status": second_status,
        })
        manifest["checkpoints"].append({
            "label": "after-second-action",
            "frame_sha256": second_checkpoint["frame"]["sha256"],
        })
        manifest["memory_checkpoints"].append({
            "label": "after-second-action",
            "ranges": second_memory_summary,
        })
        manifest["stream_position_checkpoints"].append({
            "label": "after-second-action",
            "inventory": second_stream,
        })
        manifest["stream_position_deltas"].append({
            "from": "before-second-action-settled",
            "to": "after-second-action",
            "delta": stream_position_delta(
                {"stream_position": settled_stream},
                {"stream_position": second_stream},
            ),
        })
        manifest["memory_diff"] = memory_diff_summary(
            pre_memory, first_memory, settled_memory, second_memory,
        )
        manifest["complete"] = True
        manifest["faulted"] = False
        write_manifest(args.output_dir, manifest)
        print(json.dumps({
            "complete": True,
            "position": manifest["position"],
            "checkpoints": manifest["checkpoints"],
            "first_deltas": first_delta,
            "second_deltas": second_delta,
            "stream_position_deltas": manifest["stream_position_deltas"],
        }))
        return 0
    except Exception as exc:
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        try:
            manifest["failure_status"] = web.get_json("/api/key-status")
        except Exception as status_exc:
            manifest["failure_status_error"] = (
                f"{type(status_exc).__name__}: {status_exc}"
            )
        write_manifest(args.output_dir, manifest)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
