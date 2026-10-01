#!/usr/bin/env python3
"""Find a native NPE action target using only real matrix edges.

Starting in the running game, walk an expanding square spiral and issue one
0x86 action after each move.  The bounded QOM status reports whether original
guest code used the 29:CE22 selector or the later 1A:19C4 state branch.  The
probe stops only when the selector returns a value other than 0xFFFF.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Iterator

try:
    from monitor_np560_npe_input_semantics import (
        INPUT_PROBES,
        capture_completed_checkpoint,
        wait_for_completed_frame,
    )
    from monitor_np560_npe_play_session import (
        application_state,
        game_ready,
        single_edge_violation,
        wait_for,
        wait_for_key_quiescence,
        write_manifest,
    )
    from probe_np560_matrix_route import (
        WebBridge, raise_if_key_status_faulted, replay_step,
    )
except ModuleNotFoundError:  # imported as scripts.probe_...
    from .monitor_np560_npe_input_semantics import (
        INPUT_PROBES,
        capture_completed_checkpoint,
        wait_for_completed_frame,
    )
    from .monitor_np560_npe_play_session import (
        application_state,
        game_ready,
        single_edge_violation,
        wait_for,
        wait_for_key_quiescence,
        write_manifest,
    )
    from .probe_np560_matrix_route import (
        WebBridge, raise_if_key_status_faulted, replay_step,
    )


def spiral_directions(limit: int) -> Iterator[str]:
    directions = ("right", "down", "left", "up")
    emitted = 0
    leg = 1
    direction = 0
    while emitted < limit:
        for _ in range(2):
            for _ in range(leg):
                if emitted >= limit:
                    return
                yield directions[direction % 4]
                emitted += 1
            direction += 1
        leg += 1


DIRECTION_COUNTER_FIELDS = {
    "up": "direction_up_paths",
    "down": "direction_down_paths",
    "left": "direction_left_paths",
    "right": "direction_right_paths",
}

MOVEMENT_STATE_FIELDS = (
    "direction_helper_result", "direction_code",
    "direction_before_x", "direction_before_y",
    "direction_before_offset_x", "direction_before_offset_y",
    "direction_after_x", "direction_after_y",
    "direction_after_offset_x", "direction_after_offset_y",
    "direction_before_map_index", "direction_before_scroll",
    "direction_after_map_index", "direction_after_scroll",
)

POSITION_STATE_FIELDS = (
    "current_x", "current_y", "current_map_index",
    "current_offset_x", "current_offset_y",
)


def movement_state(status: dict) -> dict | None:
    if status.get("full_control_observers") is False:
        return None
    if not all(field in status for field in MOVEMENT_STATE_FIELDS):
        return None
    return {field: int(status[field]) for field in MOVEMENT_STATE_FIELDS}


def position_state(status: dict) -> tuple[int, int, int, int, int]:
    missing = [field for field in POSITION_STATE_FIELDS if field not in status]
    if missing:
        raise RuntimeError(
            "key status is missing movement position fields: " +
            ", ".join(missing)
        )
    return tuple(int(status[field]) for field in POSITION_STATE_FIELDS)


def wait_for_direction_path(
    web: WebBridge, before: dict, direction: str, *, timeout: float,
    poll_interval: float, helper_timeout: float | None = None,
) -> tuple[dict, int]:
    """Wait until the original game controller accepts one direction."""
    if before.get("full_control_observers") is False:
        raise RuntimeError("direction tracing requires --full-control-observers")
    field = DIRECTION_COUNTER_FIELDS[direction]
    deadline = time.monotonic() + timeout
    helper_wait_extended = False
    after = before
    while time.monotonic() < deadline:
        after = web.get_json("/api/key-status")
        if after.get("full_control_observers") is False:
            raise RuntimeError("direction tracing was disabled during observation")
        raise_if_key_status_faulted(web, after)
        delta = int(after[field]) - int(before[field])
        if delta == 1:
            if "direction_helper_returns" not in before:
                return after, delta
            if not helper_wait_extended:
                deadline = max(
                    deadline,
                    time.monotonic() + (
                        helper_timeout if helper_timeout is not None else timeout
                    ),
                )
                helper_wait_extended = True
            call_delta = (
                int(after["direction_helper_calls"]) -
                int(before["direction_helper_calls"])
            )
            return_delta = (
                int(after["direction_helper_returns"]) -
                int(before["direction_helper_returns"])
            )
            if call_delta > 1 or return_delta > 1:
                raise RuntimeError(
                    f"one {direction} edge traversed helper "
                    f"calls={call_delta}, returns={return_delta}"
                )
            if call_delta == 1 and return_delta == 1 and not bool(
                    after["direction_helper_active"]):
                return after, delta
        if delta > 1:
            raise RuntimeError(
                f"one {direction} edge traversed {delta} controller paths"
            )
        time.sleep(poll_interval)
    raise TimeoutError(
        f"{direction} did not reach the original controller path"
    )


def wait_for_render_cooldown(
    web: WebBridge, *, after_sequence: int, advances: int, timeout: float,
    poll_interval: float, allow_unchanged: bool = False,
) -> None:
    """Let the native renderer finish before emitting the next matrix edge."""
    try:
        wait_for_completed_frame(
            web,
            after_sequence=after_sequence,
            advances=advances,
            timeout=min(timeout, 0.75) if allow_unchanged else timeout,
            poll_interval=max(poll_interval, 0.05),
        )
    except TimeoutError:
        if not allow_unchanged:
            raise
        # A rejected move or action legitimately commits no LCD frame.  The
        # source-exact controller/helper return plus the quiet keyboard gate
        # below are sufficient in that case; do not invent a display update.
    wait_for_key_quiescence(
        web,
        quiet_duration=0.20,
        timeout=timeout,
        poll_interval=poll_interval,
    )


def wait_for_action_path(
    web: WebBridge, before: dict, *, timeout: float, poll_interval: float,
) -> tuple[dict, int, int, int]:
    """Wait past modal acknowledgement for the controller's own branch."""
    deadline = time.monotonic() + timeout
    after = before
    while time.monotonic() < deadline:
        after = web.get_json("/api/key-status")
        raise_if_key_status_faulted(web, after)
        selector_delta = (
            int(after["primary_action_selector_calls"]) -
            int(before["primary_action_selector_calls"])
        )
        selector_return_delta = (
            int(after["primary_action_selector_returns"]) -
            int(before["primary_action_selector_returns"])
        )
        late_delta = (
            int(after["primary_action_late_paths"]) -
            int(before["primary_action_late_paths"])
        )
        if (selector_delta + late_delta == 1 and
                selector_return_delta == selector_delta):
            return after, selector_delta, selector_return_delta, late_delta
        if selector_delta + late_delta > 1:
            raise RuntimeError("one action traversed multiple controller paths")
        time.sleep(poll_interval)
    raise TimeoutError("action did not reach an original controller path")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8801")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-steps", type=int, default=64)
    parser.add_argument("--request-timeout", type=float, default=10.0)
    parser.add_argument("--transition-timeout", type=float, default=120.0)
    parser.add_argument("--press-timeout", type=float, default=5.0)
    parser.add_argument("--release-timeout", type=float, default=30.0)
    parser.add_argument("--controller-timeout", type=float, default=1.0)
    parser.add_argument("--max-edge-retries", type=int, default=8)
    parser.add_argument("--frame-advances", type=int, default=2)
    parser.add_argument("--pulse-duration", type=float, default=0.2)
    parser.add_argument("--poll-interval", type=float, default=0.01)
    parser.add_argument("--settle", type=float, default=0.08)
    args = parser.parse_args()
    if args.max_steps <= 0 or args.max_edge_retries <= 0:
        parser.error("steps and edge retries must be positive")
    if args.frame_advances <= 0:
        parser.error("frame advances must be positive")
    if min(
        args.request_timeout, args.transition_timeout, args.press_timeout,
        args.release_timeout, args.controller_timeout, args.poll_interval,
        args.pulse_duration,
    ) <= 0 or args.settle < 0:
        parser.error("timeouts must be positive and settle non-negative")

    web = WebBridge(args.root, args.request_timeout)
    manifest = {
        "schema": "np560-npe-action-target-v2",
        "root": args.root,
        "max_steps": args.max_steps,
        "pulse_duration_seconds": args.pulse_duration,
        "attempts": [],
        "found": False,
        "complete": False,
    }
    write_manifest(args.output_dir, manifest)
    web.set_matrix(None)
    wait_for(
        web, game_ready,
        timeout=args.transition_timeout,
        poll_interval=0.25,
        description="running native NPE game",
    )
    wait_for_key_quiescence(
        web,
        quiet_duration=0.25,
        timeout=args.transition_timeout,
        poll_interval=args.poll_interval,
    )
    capture_completed_checkpoint(web, args.output_dir, "before-search")

    action = INPUT_PROBES["primary-action"]
    for index, direction in enumerate(spiral_directions(args.max_steps), 1):
        move = INPUT_PROBES[f"direction-{direction}"]
        move_attempts = []
        manifest["pending_attempt"] = {
            "index": index,
            "direction": direction,
            "stage": "move",
            "move_attempts": move_attempts,
            "action_attempts": [],
        }
        write_manifest(args.output_dir, manifest)
        for retry in range(1, args.max_edge_retries + 1):
            frame_sequence = int(web.get_json("/api/frame")["sequence"])
            move_before = web.get_json("/api/key-status")
            move_result = replay_step(
                web, move,
                press_timeout=args.press_timeout,
                release_timeout=args.release_timeout,
                poll_interval=args.poll_interval,
                settle=args.settle,
                pulse_duration=args.pulse_duration,
            )
            violation = single_edge_violation(move_result)
            if violation:
                raise RuntimeError(
                    f"move {index}.{retry} was not single: {violation}"
                )
            try:
                move_after, move_path_delta = wait_for_direction_path(
                    web, move_before, direction,
                    timeout=args.controller_timeout,
                    poll_interval=args.poll_interval,
                    helper_timeout=args.transition_timeout,
                )
            except TimeoutError:
                move_attempts.append({
                    "retry": retry,
                    "accepted_by_game": False,
                    "edge": move_result,
                })
                write_manifest(args.output_dir, manifest)
                wait_for_render_cooldown(
                    web,
                    after_sequence=frame_sequence,
                    advances=args.frame_advances,
                    timeout=args.transition_timeout,
                    poll_interval=args.poll_interval,
                    allow_unchanged=True,
                )
                continue
            move_attempts.append({
                "retry": retry,
                "accepted_by_game": True,
                "controller_path_delta": move_path_delta,
                "edge": move_result,
            })
            manifest["pending_attempt"]["stage"] = "move-accepted"
            write_manifest(args.output_dir, manifest)
            break
        else:
            raise TimeoutError(
                f"move {index} was not accepted after "
                f"{args.max_edge_retries} physical edges"
            )

        wait_for_render_cooldown(
            web,
            after_sequence=frame_sequence,
            advances=args.frame_advances,
            timeout=args.transition_timeout,
            poll_interval=args.poll_interval,
            allow_unchanged=True,
        )
        move_completed = web.get_json("/api/key-status")
        raise_if_key_status_faulted(web, move_completed)
        manifest["pending_attempt"]["movement_state"] = movement_state(
            move_completed
        )
        write_manifest(args.output_dir, manifest)

        action_attempts = []
        manifest["pending_attempt"]["stage"] = "action"
        manifest["pending_attempt"]["action_attempts"] = action_attempts
        write_manifest(args.output_dir, manifest)
        for retry in range(1, args.max_edge_retries + 1):
            frame_sequence = int(web.get_json("/api/frame")["sequence"])
            before = web.get_json("/api/key-status")
            action_result = replay_step(
                web, action,
                press_timeout=args.press_timeout,
                release_timeout=args.release_timeout,
                poll_interval=args.poll_interval,
                settle=args.settle,
                pulse_duration=args.pulse_duration,
            )
            violation = single_edge_violation(action_result)
            if violation:
                raise RuntimeError(
                    f"action {index}.{retry} was not single: {violation}"
                )
            try:
                after, selector_delta, selector_return_delta, late_delta = (
                    wait_for_action_path(
                        web, before,
                        timeout=args.controller_timeout,
                        poll_interval=args.poll_interval,
                    )
                )
            except TimeoutError:
                action_attempts.append({
                    "retry": retry,
                    "accepted_by_game": False,
                    "edge": action_result,
                })
                write_manifest(args.output_dir, manifest)
                wait_for_render_cooldown(
                    web,
                    after_sequence=frame_sequence,
                    advances=args.frame_advances,
                    timeout=args.transition_timeout,
                    poll_interval=args.poll_interval,
                    allow_unchanged=True,
                )
                continue
            action_attempts.append({
                "retry": retry,
                "accepted_by_game": True,
                "selector_delta": selector_delta,
                "selector_return_delta": selector_return_delta,
                "late_path_delta": late_delta,
                "edge": action_result,
            })
            manifest["pending_attempt"]["stage"] = "action-accepted"
            write_manifest(args.output_dir, manifest)
            break
        else:
            raise TimeoutError(
                f"action {index} was not accepted after "
                f"{args.max_edge_retries} physical edges"
            )

        if int(after["application_state"]) != 0x0078:
            raise RuntimeError("NPE foreground left application state 0x0078")

        if selector_delta + late_delta != 1:
            raise RuntimeError(
                f"action {index} traversed selector={selector_delta}, "
                f"late={late_delta} controller paths"
            )
        if selector_return_delta != selector_delta:
            raise RuntimeError(
                f"action {index} selector call/return mismatch"
            )
        result = int(after["primary_action_selector_result"])
        attempt = {
            "index": index,
            "direction": direction,
            "move_attempts": move_attempts,
            "movement_state": movement_state(move_completed),
            "action_attempts": action_attempts,
            "selector_delta": selector_delta,
            "selector_return_delta": selector_return_delta,
            "selector_result": result,
            "late_path_delta": late_delta,
        }
        manifest["attempts"].append(attempt)
        manifest.pop("pending_attempt", None)
        found = selector_delta == 1 and result != 0xFFFF
        if found or index % 4 == 0:
            write_manifest(args.output_dir, manifest)
        if found:
            checkpoint = capture_completed_checkpoint(
                web, args.output_dir, "target-found",
            )
            manifest.update({
                "found": True,
                "found_at_step": index,
                "found_after_direction": direction,
                "selector_result": result,
                "application_state": checkpoint["application_state"],
                "frame_sha256": checkpoint["frame"]["sha256"],
                "complete": True,
            })
            write_manifest(args.output_dir, manifest)
            print(json.dumps({
                "found": True,
                "step": index,
                "direction": direction,
                "selector_result": result,
            }))
            return 0

    manifest["error"] = "no non-FFFF selector result within max steps"
    write_manifest(args.output_dir, manifest)
    raise RuntimeError(manifest["error"])


if __name__ == "__main__":
    raise SystemExit(main())
