#!/usr/bin/env python3
"""Measure native NP560+ NPE long-press behavior through the real matrix.

The monitor performs a deterministic Web/QEMU reset, traverses the recovered
main-menu route, holds one direction after its first firmware candidate, and
records every atomic candidate/map/consumer-counter transition.  It does not
write guest RAM or synthesize an application event outside the keyboard GPIO.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any

try:
    from monitor_np560_npe_play_session import (
        PLAY_ACTIONS,
        ROUTE_TO_GAME,
        application_state,
        compact_state,
        decimal_field,
        game_ready,
        wait_for,
        wait_for_key_quiescence,
        write_manifest,
    )
    from probe_np560_matrix_route import (
        RouteStep, WebBridge, diagnostic_failure, replay_step,
    )
except ModuleNotFoundError:  # imported as scripts.monitor_...
    from .monitor_np560_npe_play_session import (
        PLAY_ACTIONS,
        ROUTE_TO_GAME,
        application_state,
        compact_state,
        decimal_field,
        game_ready,
        wait_for,
        wait_for_key_quiescence,
        write_manifest,
    )
    from .probe_np560_matrix_route import (
        RouteStep, WebBridge, diagnostic_failure, replay_step,
    )


DIRECTION_STEPS = {step.label.lower(): step for step in PLAY_ACTIONS}

# Static controller evidence identifies 0x86 as the grid action at 37:141E.
# The remaining entries are kept as separate probes because they enter either
# a different controller branch or the outer modal dispatcher.
INPUT_PROBES = {
    "direction-down": DIRECTION_STEPS["down"],
    "direction-right": DIRECTION_STEPS["right"],
    "direction-up": DIRECTION_STEPS["up"],
    "direction-left": DIRECTION_STEPS["left"],
    "primary-action": RouteStep("PrimaryAction", 53, 0x86),
    "function-90": RouteStep("Function90", 21, 0x90),
    "function-space": RouteStep("FunctionSpace", 54, 0x20),
    "mode-8e": RouteStep("Mode8E", 4, 0x8E),
    "back-84": RouteStep("Back84", 28, 0x84),
    "start-exit": RouteStep("StartExit", 55, 0xB0),
}


def game_input_evidence(registers: str) -> dict[str, int | None]:
    service = re.search(
        r"(?m)^NPE_GAME_SERVICE=.*\bCODE86:(\d+)\b", registers,
    )
    loader = re.search(
        r"(?m)^NPE_GAME_LINKED_LOADER=(\d+)\b", registers,
    )
    action = re.search(
        r"(?m)^NPE_GAME_ACTION=SELECT:(\d+)/(\d+)/R([0-9A-Fa-f]{4}) "
        r"LATE:(\d+)\b",
        registers,
    )
    return {
        "code86": int(service.group(1), 10) if service else None,
        "linked_loader": int(loader.group(1), 10) if loader else None,
        "selector_calls": int(action.group(1), 10) if action else None,
        "selector_returns": int(action.group(2), 10) if action else None,
        "selector_result": int(action.group(3), 16) if action else None,
        "late_paths": int(action.group(4), 10) if action else None,
    }


def capture_completed_checkpoint(
    web: WebBridge, output_dir: Path, prefix: str,
) -> dict[str, Any]:
    """Pair CPU diagnostics with the last complete ST7529 RAM window."""
    state = web.get_json("/api/state")
    registers = str(state.get("registers", ""))
    failure = diagnostic_failure(registers)
    if failure:
        raise RuntimeError(failure)
    completed = web.get_json("/api/frame")
    merged = dict(state)
    for name in ("format", "width", "height", "stride", "frame"):
        merged[name] = completed[name]
    summary, frame = compact_state(merged)
    summary["completed_frame_sequence"] = int(completed["sequence"])
    summary["game_input_evidence"] = game_input_evidence(registers)
    summary["key_status"] = web.get_json("/api/key-status")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{prefix}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / f"{prefix}.gray5").write_bytes(frame)
    return summary


def wait_for_completed_frame(
    web: WebBridge, *, after_sequence: int, advances: int,
    timeout: float, poll_interval: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    target = after_sequence + advances
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = web.get_json("/api/frame")
        if int(last.get("sequence", -1)) >= target:
            return last
        time.sleep(poll_interval)
    raise TimeoutError(
        f"ST7529 complete-frame sequence did not reach {target}"
    )


def repeat_timing(result: dict[str, Any]) -> dict[str, Any]:
    """Summarize candidate edge times without duplicating map/ack updates."""
    edges: list[dict[str, Any]] = []
    previous_delta = 0
    skipped_edges = 0
    for point in result.get("hold_timeline", []):
        delta = int(point.get("candidates_delta", 0))
        if delta <= previous_delta:
            continue
        if previous_delta and delta > previous_delta + 1:
            skipped_edges += delta - previous_delta - 1
        edges.append({
            "edge": delta,
            "elapsed_seconds": float(point["elapsed_seconds"]),
            "event": int(point.get("candidate", -1)),
            "phase": str(point.get("phase", "held")),
            **({
                "matrix_reads": int(point["matrix_reads"]),
                "matrix_reads_delta": int(point["matrix_reads_delta"]),
            } if "matrix_reads" in point else {}),
        })
        previous_delta = delta
    held_edges = [edge for edge in edges if edge["phase"] == "held"]
    repeat_times = [edge["elapsed_seconds"] for edge in held_edges[1:]]
    intervals = [
        round(right - left, 6)
        for left, right in zip(repeat_times, repeat_times[1:])
    ]
    scan_positions = [
        int(edge["matrix_reads_delta"])
        for edge in held_edges if "matrix_reads_delta" in edge
    ]
    first_repeat_reads = (
        scan_positions[1] - scan_positions[0]
        if len(scan_positions) >= 2 else None
    )
    repeat_scan_positions = scan_positions[1:]
    scan_intervals = [
        right - left
        for left, right in zip(
            repeat_scan_positions, repeat_scan_positions[1:],
        )
    ]
    return {
        "candidate_edges": edges,
        "observed_edge_transitions": len(edges),
        "held_edge_transitions": len(held_edges),
        "post_release_edge_transitions": len(edges) - len(held_edges),
        "skipped_edges_between_polls": skipped_edges,
        "first_repeat_seconds": repeat_times[0] if repeat_times else None,
        "repeat_intervals_seconds": intervals,
        "repeat_interval_median_seconds": (
            round(statistics.median(intervals), 6) if intervals else None
        ),
        "repeat_interval_min_seconds": min(intervals) if intervals else None,
        "repeat_interval_max_seconds": max(intervals) if intervals else None,
        "first_repeat_matrix_reads": first_repeat_reads,
        "repeat_intervals_matrix_reads": scan_intervals,
        "repeat_interval_median_matrix_reads": (
            statistics.median(scan_intervals) if scan_intervals else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8801")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--direction", choices=tuple(DIRECTION_STEPS), default="down",
    )
    parser.add_argument(
        "--probe-key", choices=tuple(INPUT_PROBES),
        help="send one isolated non-direction key instead of a long press",
    )
    parser.add_argument("--hold-duration", type=float, default=5.0)
    parser.add_argument(
        "--pulse-duration", type=float, default=0.0,
        help=(
            "release an isolated --probe-key after this fixed physical "
            "pulse instead of waiting for its first candidate"
        ),
    )
    parser.add_argument("--startup-timeout", type=float, default=240.0)
    parser.add_argument("--transition-timeout", type=float, default=120.0)
    parser.add_argument("--request-timeout", type=float, default=10.0)
    parser.add_argument("--press-timeout", type=float, default=5.0)
    parser.add_argument("--release-timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=0.01)
    parser.add_argument("--settle", type=float, default=0.35)
    parser.add_argument("--minimum-matrix-reads", type=int, default=2500)
    parser.add_argument("--skip-reset", action="store_true")
    parser.add_argument(
        "--route-only", action="store_true",
        help="stop after the verified native game loop is ready",
    )
    parser.add_argument(
        "--skip-route", action="store_true",
        help="measure the already-running NPE game without traversing menus",
    )
    args = parser.parse_args()
    if args.hold_duration <= 0:
        parser.error("hold duration must be positive")
    if min(
        args.startup_timeout, args.transition_timeout, args.request_timeout,
        args.press_timeout, args.release_timeout, args.poll_interval,
    ) <= 0 or min(args.settle, args.pulse_duration) < 0 or \
            args.minimum_matrix_reads < 0:
        parser.error("timeouts must be positive and settle/reads non-negative")
    if args.skip_route and not args.skip_reset:
        parser.error("--skip-route requires --skip-reset")

    web = WebBridge(args.root, args.request_timeout)
    manifest: dict[str, Any] = {
        "schema": "np560-npe-input-semantics-v2",
        "root": args.root,
        "direction": args.direction,
        "probe_key": args.probe_key,
        "hold_duration_seconds": args.hold_duration,
        "pulse_duration_seconds": args.pulse_duration,
        "reset_requested": not args.skip_reset,
        "route_requested": not args.skip_route,
        "route_only": bool(args.route_only),
        "route": [],
        "long_press": None,
        "key_probe": None,
        "repeat_timing": None,
        "complete": False,
    }
    write_manifest(args.output_dir, manifest)

    try:
        web.set_matrix(None)
        if not args.skip_reset:
            web.post_json("/api/control", {"action": "reset"})
        if not args.skip_route:
            wait_for(
                web,
                lambda registers: (
                    application_state(registers) == 0x00FF
                    and (decimal_field(registers, "MATRIX_READS") or 0)
                    >= args.minimum_matrix_reads
                ),
                timeout=args.startup_timeout,
                poll_interval=0.25,
                description="deterministic root-menu keyboard scan",
            )
            for step in ROUTE_TO_GAME:
                manifest["route"].append(replay_step(
                    web,
                    step,
                    press_timeout=args.press_timeout,
                    release_timeout=args.release_timeout,
                    poll_interval=args.poll_interval,
                    settle=args.settle,
                    use_bounded_status=False,
                ))
                write_manifest(args.output_dir, manifest)
        wait_for(
            web,
            game_ready,
            timeout=args.transition_timeout,
            poll_interval=0.25,
            description="native NPE game loop",
        )
        wait_for_key_quiescence(
            web,
            quiet_duration=0.25,
            timeout=args.transition_timeout,
            poll_interval=args.poll_interval,
        )
        before = capture_completed_checkpoint(
            web, args.output_dir, "before-input",
        )

        if args.route_only:
            manifest.update({
                "before_frame_sha256": before["frame"]["sha256"],
                "application_state_before": before["application_state"],
                "complete": True,
            })
            write_manifest(args.output_dir, manifest)
            print(json.dumps({
                "complete": True,
                "application_state": before["application_state"],
                "frame_sha256": before["frame"]["sha256"],
            }))
            return 0

        if args.probe_key:
            step = INPUT_PROBES[args.probe_key]
            result = replay_step(
                web,
                step,
                press_timeout=args.press_timeout,
                release_timeout=args.release_timeout,
                poll_interval=args.poll_interval,
                settle=args.settle,
                pulse_duration=args.pulse_duration,
            )
            wait_for_key_quiescence(
                web,
                quiet_duration=0.25,
                timeout=args.transition_timeout,
                poll_interval=args.poll_interval,
            )
            if args.probe_key == "primary-action":
                wait_for_completed_frame(
                    web,
                    after_sequence=int(before["completed_frame_sequence"]),
                    advances=2,
                    timeout=args.transition_timeout,
                    poll_interval=max(args.poll_interval, 0.05),
                )
            after = capture_completed_checkpoint(
                web, args.output_dir, "after-input",
            )
            counts = {
                "candidate": int(result["candidate_writes_total"]),
                "map": int(result["maps_total"]),
                "consumer_ack": int(
                    result["consumer_acknowledgements_total"]
                ),
            }
            if any(value != 1 for value in counts.values()):
                raise RuntimeError(
                    "isolated key did not produce exactly one input edge: "
                    + ", ".join(
                        f"{name}={value}" for name, value in counts.items()
                    )
                )
            firmware_action_evidence = None
            if args.probe_key == "primary-action":
                before_evidence = before["game_input_evidence"]
                after_evidence = after["game_input_evidence"]
                firmware_action_evidence = {
                    name: {
                        "before": before_evidence[name],
                        "after": after_evidence[name],
                        "delta": (
                            int(after_evidence[name]) -
                            int(before_evidence[name])
                            if before_evidence[name] is not None and
                            after_evidence[name] is not None else None
                        ),
                    }
                    for name in (
                        "selector_calls", "selector_returns", "late_paths",
                    )
                }
                firmware_action_evidence["selector_result"] = {
                    "before": before_evidence["selector_result"],
                    "after": after_evidence["selector_result"],
                    "delta": None,
                }
                selector_delta = firmware_action_evidence[
                    "selector_calls"
                ]["delta"]
                selector_return_delta = firmware_action_evidence[
                    "selector_returns"
                ]["delta"]
                late_delta = firmware_action_evidence["late_paths"]["delta"]
                if (selector_delta is None or selector_return_delta is None or
                        late_delta is None or
                        selector_delta + late_delta != 1 or
                        selector_return_delta != selector_delta):
                    raise RuntimeError(
                        "primary action did not traverse exactly one original "
                        "selector or late-state controller path"
                    )
            manifest.update({
                "before_frame_sha256": before["frame"]["sha256"],
                "after_frame_sha256": after["frame"]["sha256"],
                "application_state_before": before["application_state"],
                "application_state_after": after["application_state"],
                "key_probe": result,
                "balanced_counts": counts,
                "firmware_action_evidence": firmware_action_evidence,
                "complete": True,
            })
            write_manifest(args.output_dir, manifest)
            print(json.dumps({
                "complete": True,
                "probe_key": args.probe_key,
                "counts": counts,
                "application_state_before": before["application_state"],
                "application_state_after": after["application_state"],
                "frame_changed": (
                    before["frame"]["sha256"] != after["frame"]["sha256"]
                ),
            }, ensure_ascii=False))
            return 0

        step = DIRECTION_STEPS[args.direction]
        result = replay_step(
            web,
            step,
            press_timeout=args.press_timeout,
            release_timeout=args.release_timeout,
            poll_interval=args.poll_interval,
            settle=args.settle,
            hold_duration=args.hold_duration,
        )
        timing = repeat_timing(result)
        after = capture_completed_checkpoint(
            web, args.output_dir, "after-input",
        )
        status = web.get_json("/api/key-status")
        if int(status.get("application_state", -1)) != 0x0078:
            raise RuntimeError("NPE foreground left application state 0x0078")
        counts = {
            "candidate": int(result["candidate_writes_total"]),
            "map": int(result["maps_total"]),
            "consumer_ack": int(result["consumer_acknowledgements_total"]),
        }
        if len(set(counts.values())) != 1 or counts["candidate"] < 2:
            raise RuntimeError(
                "long press did not produce a balanced repeated input chain: "
                + ", ".join(f"{name}={value}" for name, value in counts.items())
            )
        manifest.update({
            "before_frame_sha256": before["frame"]["sha256"],
            "after_frame_sha256": after["frame"]["sha256"],
            "long_press": result,
            "repeat_timing": timing,
            "balanced_counts": counts,
            "complete": True,
        })
        write_manifest(args.output_dir, manifest)
        print(json.dumps({
            "complete": True,
            "counts": counts,
            "first_repeat_seconds": timing["first_repeat_seconds"],
            "median_repeat_seconds": timing["repeat_interval_median_seconds"],
            "frame_changed": (
                before["frame"]["sha256"] != after["frame"]["sha256"]
            ),
        }, ensure_ascii=False))
        return 0
    except Exception as error:
        manifest["error"] = f"{type(error).__name__}: {error}"
        manifest["failed_at_monotonic"] = round(time.monotonic(), 6)
        try:
            capture_completed_checkpoint(web, args.output_dir, "failure")
        except Exception as capture_error:
            manifest["capture_error"] = (
                f"{type(capture_error).__name__}: {capture_error}"
            )
        write_manifest(args.output_dir, manifest)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
