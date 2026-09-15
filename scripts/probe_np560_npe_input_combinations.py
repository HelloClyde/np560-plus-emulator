#!/usr/bin/env python3
"""Prove native NP560+ NPE direction/action matrix-combination semantics.

Two physical sequences are measured without writing guest RAM or injecting an
application event:

1. press one direction, add and remove the action switch while the direction
   remains held, then release the complete matrix;
2. press the direction and action switches simultaneously from a fully
   released matrix.

The first sequence proves whether the original scanner rearms on a level
change without a full release.  The second proves the original multi-key
priority.  All assertions use the atomic QEMU observer counters only.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable

try:
    from monitor_np560_npe_play_session import (
        PLAY_ACTIONS,
        wait_for_key_quiescence,
        write_manifest,
    )
    from probe_np560_matrix_route import (
        WebBridge,
        matrix_masks,
        raise_if_key_status_faulted,
    )
except ModuleNotFoundError:  # imported as scripts.probe_...
    from .monitor_np560_npe_play_session import (
        PLAY_ACTIONS,
        wait_for_key_quiescence,
        write_manifest,
    )
    from .probe_np560_matrix_route import (
        WebBridge,
        matrix_masks,
        raise_if_key_status_faulted,
    )


DIRECTIONS = {step.label.lower(): step for step in PLAY_ACTIONS}
ACTION_MATRIX_INDEX = 53
ACTION_EVENT = 0x86
COUNTERS = (
    "candidates",
    "maps",
    "acknowledgements",
    "modal_acknowledgements",
    "primary_action_selector_calls",
    "primary_action_selector_returns",
    "primary_action_late_paths",
    "direction_up_paths",
    "direction_down_paths",
    "direction_left_paths",
    "direction_right_paths",
)


def combined_masks(*indexes: int) -> tuple[int, int]:
    low = high = 0
    for index in indexes:
        index_low, index_high = matrix_masks(index)
        low |= index_low
        high |= index_high
    return low, high


def simultaneous_winner(direction_name: str) -> tuple[int, int, str]:
    """Return the observed descending-index matrix scan winner."""
    direction = DIRECTIONS[direction_name]
    if direction.matrix_index > ACTION_MATRIX_INDEX:
        return (
            direction.matrix_index,
            direction.expected_event,
            f"direction_{direction_name}_paths",
        )
    return ACTION_MATRIX_INDEX, ACTION_EVENT, "primary-action"


def counter_deltas(
    before: dict[str, Any], after: dict[str, Any],
) -> dict[str, int]:
    return {
        name: int(after.get(name, 0)) - int(before.get(name, 0))
        for name in COUNTERS
    }


def consumer_delta(deltas: dict[str, int]) -> int:
    return deltas["acknowledgements"] + deltas["modal_acknowledgements"]


def wait_status(
    web: WebBridge,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    timeout: float,
    poll_interval: float,
    description: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = web.get_json("/api/key-status")
        raise_if_key_status_faulted(web, last)
        if predicate(last):
            return last
        time.sleep(poll_interval)
    raise TimeoutError(f"timed out waiting for {description}: {last!r}")


def set_masks(web: WebBridge, low: int, high: int) -> None:
    web.post_json("/api/key", {
        "state": 0,
        "code": 0,
        "matrix_low": low,
        "matrix_high": high,
    })


def require_single_event(
    deltas: dict[str, int], *, label: str,
) -> None:
    actual = {
        "candidate": deltas["candidates"],
        "map": deltas["maps"],
        "consumer": consumer_delta(deltas),
    }
    if any(value != 1 for value in actual.values()):
        raise RuntimeError(
            f"{label} was not one balanced guest event: "
            + ", ".join(f"{name}={value}" for name, value in actual.items())
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8801")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--direction", choices=tuple(DIRECTIONS), default="down")
    parser.add_argument("--transition-hold", type=float, default=0.08)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=0.01)
    parser.add_argument("--settle", type=float, default=0.25)
    args = parser.parse_args()
    if min(args.transition_hold, args.timeout, args.poll_interval) <= 0 or \
            args.settle < 0:
        parser.error("hold/timeouts must be positive and settle non-negative")

    web = WebBridge(args.root, args.timeout)
    direction = DIRECTIONS[args.direction]
    winner_index, simultaneous_event, simultaneous_path = \
        simultaneous_winner(args.direction)
    direction_masks = combined_masks(direction.matrix_index)
    both_masks = combined_masks(direction.matrix_index, ACTION_MATRIX_INDEX)
    manifest: dict[str, Any] = {
        "schema": "np560-npe-input-combinations-v1",
        "root": args.root,
        "direction": args.direction,
        "direction_matrix_index": direction.matrix_index,
        "direction_event": direction.expected_event,
        "action_matrix_index": ACTION_MATRIX_INDEX,
        "action_event": ACTION_EVENT,
        "simultaneous_winner_matrix_index": winner_index,
        "simultaneous_expected_event": simultaneous_event,
        "simultaneous_expected_path": simultaneous_path,
        "transition_hold_seconds": args.transition_hold,
        "phases": [],
        "complete": False,
    }
    write_manifest(args.output_dir, manifest)

    try:
        set_masks(web, 0, 0)
        wait_for_key_quiescence(
            web,
            quiet_duration=0.25,
            timeout=args.timeout,
            poll_interval=args.poll_interval,
        )
        wait_status(
            web,
            lambda status: (
                not bool(status.get("direction_helper_active", False))
                and int(status.get("direction_helper_calls", 0)) ==
                int(status.get("direction_helper_returns", 0))
            ),
            timeout=args.timeout,
            poll_interval=args.poll_interval,
            description="initial direction-helper quiescence",
        )

        # A level change while any matrix switch remains held must not create
        # a second make: the recovered guest worker rearms only after all keys
        # are released.
        before_staged = web.get_json("/api/key-status")
        raise_if_key_status_faulted(web, before_staged)
        if int(before_staged.get("application_state", -1)) != 0x78:
            raise RuntimeError("NPE foreground is not application state 0x0078")
        set_masks(web, *direction_masks)
        first_direction = wait_status(
            web,
            lambda status: (
                int(status.get("candidates", 0)) >
                int(before_staged.get("candidates", 0))
                and int(status.get("candidate", -1)) ==
                direction.expected_event
                and int(status.get("maps", 0)) >
                int(before_staged.get("maps", 0))
                and (
                    int(status.get("acknowledgements", 0)) -
                    int(before_staged.get("acknowledgements", 0)) +
                    int(status.get("modal_acknowledgements", 0)) -
                    int(before_staged.get("modal_acknowledgements", 0))
                ) > 0
            ),
            timeout=args.timeout,
            poll_interval=args.poll_interval,
            description="first held direction event",
        )
        set_masks(web, *both_masks)
        time.sleep(args.transition_hold)
        after_add = web.get_json("/api/key-status")
        raise_if_key_status_faulted(web, after_add)
        set_masks(web, *direction_masks)
        time.sleep(args.transition_hold)
        after_remove = web.get_json("/api/key-status")
        raise_if_key_status_faulted(web, after_remove)
        set_masks(web, 0, 0)
        after_staged = wait_status(
            web,
            lambda status: (
                bool(status.get("matrix_rearmed", False))
                and not bool(status.get("direction_helper_active", False))
                and int(status.get("direction_helper_calls", 0)) ==
                int(status.get("direction_helper_returns", 0))
            ),
            timeout=args.timeout,
            poll_interval=args.poll_interval,
            description=(
                "matrix rearm and direction-helper return after staged "
                "combination"
            ),
        )
        if args.settle:
            time.sleep(args.settle)
            after_staged = web.get_json("/api/key-status")
        staged_deltas = counter_deltas(before_staged, after_staged)
        require_single_event(staged_deltas, label="staged direction/action")
        if int(after_staged.get("candidate", -1)) != direction.expected_event:
            raise RuntimeError("staged combination changed the direction event")
        if counter_deltas(first_direction, after_add)["candidates"] != 0 or \
                counter_deltas(first_direction, after_remove)["candidates"] != 0:
            raise RuntimeError(
                "adding/removing action while direction remained held "
                "created a second make before full release"
            )
        manifest["phases"].append({
            "label": "direction-held-add-action",
            "deltas": staged_deltas,
            "candidate": int(after_staged["candidate"]),
            "matrix_rearmed": bool(after_staged["matrix_rearmed"]),
        })
        write_manifest(args.output_dir, manifest)

        # From a fully released matrix, the original descending-index scan
        # priority selects exactly one switch from the simultaneous level.
        # M61/Up therefore wins over M53/Action; Action wins over M45/M37/M29.
        before_simultaneous = after_staged
        set_masks(web, *both_masks)
        simultaneous_status = wait_status(
            web,
            lambda status: (
                int(status.get("candidates", 0)) >
                int(before_simultaneous.get("candidates", 0))
                and int(status.get("candidate", -1)) == simultaneous_event
            ),
            timeout=args.timeout,
            poll_interval=args.poll_interval,
            description="simultaneous combination winner event",
        )
        set_masks(web, 0, 0)
        after_simultaneous = wait_status(
            web,
            lambda status: (
                bool(status.get("matrix_rearmed", False))
                and int(status.get("maps", 0)) >
                int(before_simultaneous.get("maps", 0))
                and (
                    int(status.get("acknowledgements", 0)) -
                    int(before_simultaneous.get("acknowledgements", 0)) +
                    int(status.get("modal_acknowledgements", 0)) -
                    int(before_simultaneous.get("modal_acknowledgements", 0))
                ) > 0
                and (
                    (
                        simultaneous_path == "primary-action"
                        and (
                            int(status.get(
                                "primary_action_selector_calls", 0,
                            )) - int(before_simultaneous.get(
                                "primary_action_selector_calls", 0,
                            )) + int(status.get(
                                "primary_action_late_paths", 0,
                            )) - int(before_simultaneous.get(
                                "primary_action_late_paths", 0,
                            ))
                        ) > 0
                    )
                    or (
                        simultaneous_path != "primary-action"
                        and int(status.get(simultaneous_path, 0)) >
                        int(before_simultaneous.get(simultaneous_path, 0))
                        and not bool(status.get(
                            "direction_helper_active", False,
                        ))
                        and int(status.get("direction_helper_calls", 0)) ==
                        int(status.get("direction_helper_returns", 0))
                    )
                )
            ),
            timeout=args.timeout,
            poll_interval=args.poll_interval,
            description="simultaneous combination delivery and rearm",
        )
        if args.settle:
            time.sleep(args.settle)
            after_simultaneous = web.get_json("/api/key-status")
        simultaneous_deltas = counter_deltas(
            before_simultaneous, after_simultaneous,
        )
        require_single_event(
            simultaneous_deltas, label="simultaneous direction/action",
        )
        action_paths = (
            simultaneous_deltas["primary_action_selector_calls"] +
            simultaneous_deltas["primary_action_late_paths"]
        )
        if simultaneous_path == "primary-action":
            if action_paths != 1:
                raise RuntimeError(
                    "simultaneous combination did not traverse exactly one "
                    f"native action path: {action_paths}"
                )
            if simultaneous_deltas["primary_action_selector_returns"] != \
                    simultaneous_deltas["primary_action_selector_calls"]:
                raise RuntimeError(
                    "native action selector did not return cleanly"
                )
        else:
            if action_paths != 0 or simultaneous_deltas[simultaneous_path] != 1:
                raise RuntimeError(
                    "simultaneous combination did not traverse exactly one "
                    f"native {simultaneous_path}: action={action_paths}, "
                    f"direction={simultaneous_deltas[simultaneous_path]}"
                )
        manifest["phases"].append({
            "label": "simultaneous-direction-action",
            "deltas": simultaneous_deltas,
            "candidate": int(simultaneous_status["candidate"]),
            "winner_matrix_index": winner_index,
            "winner_path": simultaneous_path,
            "selector_result": int(
                after_simultaneous.get("primary_action_selector_result", -1)
            ),
            "matrix_rearmed": bool(after_simultaneous["matrix_rearmed"]),
        })
        manifest.update({
            "complete": True,
            "faulted": False,
            "application_state": int(after_simultaneous["application_state"]),
        })
        write_manifest(args.output_dir, manifest)
        print(json.dumps({
            "complete": True,
            "direction": args.direction,
            "staged_event": int(after_staged["candidate"]),
            "simultaneous_event": int(simultaneous_status["candidate"]),
            "simultaneous_winner_matrix_index": winner_index,
            "simultaneous_winner_path": simultaneous_path,
            "staged_deltas": staged_deltas,
            "simultaneous_deltas": simultaneous_deltas,
        }, ensure_ascii=False))
        return 0
    except Exception as exc:
        try:
            set_masks(web, 0, 0)
        finally:
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
