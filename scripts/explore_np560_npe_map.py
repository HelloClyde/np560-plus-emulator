#!/usr/bin/env python3
"""Explore the running native NPE map using original movement feedback.

Unlike a blind geometric spiral, this probe treats the guest's source-exact
movement helper result and current viewport/map globals as the state graph.
It builds a directed state graph, issues one real 0x86 matrix action at every
newly discovered state, follows known directed edges toward unexplored states,
and normally stops on either a non-FFFF selector result or the first guest
fault.  Optional continuation and NPE stream-page watching support longer
event discovery without changing guest memory or control flow.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

try:
    from monitor_np560_npe_input_semantics import (
        INPUT_PROBES,
        capture_completed_checkpoint,
    )
    from monitor_np560_npe_play_session import (
        ROUTE_TO_GAME,
        application_state,
        decimal_field,
        game_ready,
        run_step,
        single_edge_violation,
        wait_for,
        wait_for_key_quiescence,
        write_manifest,
    )
    from probe_np560_matrix_route import (
        WebBridge,
        raise_if_key_status_faulted,
        replay_step,
    )
    from probe_np560_npe_action_target import (
        movement_state,
        position_state,
        wait_for_action_path,
        wait_for_direction_path,
        wait_for_render_cooldown,
    )
    from probe_np560_npe_unbanked_sfr import (
        parse_stream_position_inventory,
        stream_position_delta,
    )
except ModuleNotFoundError:  # imported as scripts.explore_...
    from .monitor_np560_npe_input_semantics import (
        INPUT_PROBES,
        capture_completed_checkpoint,
    )
    from .monitor_np560_npe_play_session import (
        ROUTE_TO_GAME,
        application_state,
        decimal_field,
        game_ready,
        run_step,
        single_edge_violation,
        wait_for,
        wait_for_key_quiescence,
        write_manifest,
    )
    from .probe_np560_matrix_route import (
        WebBridge,
        raise_if_key_status_faulted,
        replay_step,
    )
    from .probe_np560_npe_action_target import (
        movement_state,
        position_state,
        wait_for_action_path,
        wait_for_direction_path,
        wait_for_render_cooldown,
    )
    from .probe_np560_npe_unbanked_sfr import (
        parse_stream_position_inventory,
        stream_position_delta,
    )


DIRECTIONS = ("up", "right", "down", "left")
OPPOSITE = {
    "up": "down",
    "right": "left",
    "down": "up",
    "left": "right",
}


GameState = tuple[int, int, int, int, int, int]


def position_record(position: GameState) -> dict[str, int]:
    x, y, map_index, offset_x, offset_y, direction = position
    return {
        "x": x,
        "y": y,
        "map_index": map_index,
        "offset_x": offset_x,
        "offset_y": offset_y,
        "direction": direction,
    }


def position_tuple(record: dict[str, Any]) -> GameState:
    return (
        int(record["x"]),
        int(record["y"]),
        int(record["map_index"]),
        int(record["offset_x"]),
        int(record["offset_y"]),
        int(record["direction"]),
    )


def explorer_state(status: dict[str, Any]) -> GameState:
    """Return every guest field that changes movement/action semantics."""
    x, y, map_index, offset_x, offset_y = position_state(status)
    return (
        x, y, map_index, offset_x, offset_y,
        int(status["current_direction"]),
    )


def route_to_unexplored(
    start: GameState,
    graph: dict[GameState, dict[str, GameState]],
    attempted_directions: dict[GameState, set[str]],
    target_world: tuple[int, int] | None = None,
) -> list[str] | None:
    """Return a known directed route to a state with an untried edge.

    With a target, prefer the reachable frontier whose world coordinate is
    closest to it.  This changes only navigation through already known edges;
    every state still tries all four directions in the stable schema order.
    """
    queue: list[tuple[GameState, list[str]]] = [(start, [])]
    seen = {start}
    candidates: list[tuple[int, int, list[str]]] = []
    while queue:
        state, path = queue.pop(0)
        if len(attempted_directions.get(state, set())) < len(DIRECTIONS):
            if target_world is None:
                return path
            x, y, _, offset_x, offset_y, _ = state
            distance = (
                abs((x + offset_x) - target_world[0])
                + abs((y + offset_y) - target_world[1])
            )
            candidates.append((distance, len(path), path))
        for direction, target in graph.get(state, {}).items():
            if target in seen:
                continue
            seen.add(target)
            queue.append((target, path + [direction]))
    if candidates:
        return min(candidates, key=lambda item: (item[0], item[1]))[2]
    return None


def direction_order(
    state: GameState,
    target_world: tuple[int, int] | None,
) -> tuple[str, ...]:
    """Return a stable exhaustive order, biased toward a known world target."""
    if target_world is None:
        return DIRECTIONS
    x, y, _, offset_x, offset_y, _ = state
    world_x = x + offset_x
    world_y = y + offset_y
    delta = {
        "up": (0, -1),
        "right": (1, 0),
        "down": (0, 1),
        "left": (-1, 0),
    }
    return tuple(sorted(
        DIRECTIONS,
        key=lambda direction: (
            abs(world_x + delta[direction][0] - target_world[0])
            + abs(world_y + delta[direction][1] - target_world[1]),
            DIRECTIONS.index(direction),
        ),
    ))


def faces_world_target(
    state: GameState,
    target_world: tuple[int, int],
) -> bool:
    """Return whether the avatar's adjacent facing cell is the target."""
    x, y, _, offset_x, offset_y, direction = state
    delta = {
        0: (0, 1),
        1: (1, 0),
        2: (0, -1),
        3: (-1, 0),
    }
    dx, dy = delta[direction]
    return (
        x + offset_x + dx,
        y + offset_y + dy,
    ) == target_world


def wait_for_stable_frame(
    web: WebBridge,
    *,
    stable_duration: float,
    timeout: float,
    poll_interval: float,
) -> None:
    """Wait until completed LCD content remains identical for a duration."""
    deadline = time.monotonic() + timeout
    stable_since = time.monotonic()
    last_frame: str | None = None
    while time.monotonic() < deadline:
        payload = web.get_json("/api/frame")
        frame = str(payload.get("frame", ""))
        if not frame:
            raise ValueError("completed LCD frame is empty")
        now = time.monotonic()
        if frame != last_frame:
            last_frame = frame
            stable_since = now
        elif now - stable_since >= stable_duration:
            return
        time.sleep(poll_interval)
    raise TimeoutError("timed out waiting for stable target frame")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8801")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--resume-manifest", type=Path, action="append", default=[],
        help=(
            "seed the directed graph and tested-action set from a manifest "
            "created earlier in the same live game session"
        ),
    )
    parser.add_argument(
        "--route-to-game", action="store_true",
        help=(
            "if the native game is not already running, wait for the cold-boot "
            "desktop and traverse the seven recovered physical menu edges"
        ),
    )
    parser.add_argument("--minimum-matrix-reads", type=int, default=2500)
    parser.add_argument("--target-world-x", type=int)
    parser.add_argument("--target-world-y", type=int)
    parser.add_argument(
        "--stop-before-target-action", action="store_true",
        help=(
            "stop and capture a stable frame when the avatar first faces the "
            "specified world target, before issuing the 0x86 action"
        ),
    )
    parser.add_argument("--target-stable-duration", type=float, default=1.0)
    parser.add_argument(
        "--continue-after-found", action="store_true",
        help=(
            "record non-FFFF action selectors and continue exploring instead "
            "of stopping at the first object"
        ),
    )
    parser.add_argument(
        "--watch-new-stream-pages", action="store_true",
        help=(
            "capture NPE stream inventories after each accepted edge and "
            "stop at the first 4 KiB file page absent from the baseline"
        ),
    )
    parser.add_argument(
        "--stream-stop-min-position", type=lambda value: int(value, 0),
        help=(
            "with stream watching, ignore new pages below this file offset "
            "and stop only when an observed read extends beyond it"
        ),
    )
    parser.add_argument("--max-states", type=int, default=256)
    parser.add_argument("--max-edges", type=int, default=2048)
    parser.add_argument("--request-timeout", type=float, default=20.0)
    parser.add_argument("--transition-timeout", type=float, default=120.0)
    parser.add_argument("--press-timeout", type=float, default=10.0)
    parser.add_argument("--release-timeout", type=float, default=20.0)
    parser.add_argument("--controller-timeout", type=float, default=2.0)
    parser.add_argument("--max-edge-retries", type=int, default=5)
    parser.add_argument("--frame-advances", type=int, default=2)
    parser.add_argument("--pulse-duration", type=float, default=0.2)
    parser.add_argument("--poll-interval", type=float, default=0.03)
    parser.add_argument("--settle", type=float, default=0.04)
    parser.add_argument(
        "--route-settle", type=float, default=0.35,
        help="settle time between cold-boot menu edges (default: 0.35s)",
    )
    args = parser.parse_args()
    if (args.target_world_x is None) != (args.target_world_y is None):
        parser.error("target world X and Y must be supplied together")
    if args.stop_before_target_action and args.target_world_x is None:
        parser.error("stop-before-target-action requires a world target")
    if (
        args.stream_stop_min_position is not None
        and not 0 <= args.stream_stop_min_position < (1 << 24)
    ):
        parser.error("stream stop position must fit the 24-bit file range")
    if min(
        args.max_states, args.max_edges, args.max_edge_retries,
        args.frame_advances, args.minimum_matrix_reads,
    ) <= 0:
        parser.error("state, edge, retry and frame limits must be positive")
    if min(
        args.request_timeout, args.transition_timeout, args.press_timeout,
        args.release_timeout, args.controller_timeout, args.pulse_duration,
        args.poll_interval, args.target_stable_duration,
    ) <= 0 or min(args.settle, args.route_settle) < 0:
        parser.error("timeouts/pulse must be positive and settle non-negative")

    web = WebBridge(args.root, args.request_timeout)
    manifest: dict[str, Any] = {
        "schema": "np560-npe-map-explorer-v3",
        "root": args.root,
        "max_states": args.max_states,
        "max_edges": args.max_edges,
        "pulse_duration_seconds": args.pulse_duration,
        "resume_manifests": [str(path) for path in args.resume_manifest],
        "route_to_game_requested": bool(args.route_to_game),
        "route": [],
        "target_world": (
            None if args.target_world_x is None else {
                "x": args.target_world_x,
                "y": args.target_world_y,
            }
        ),
        "stop_before_target_action": bool(args.stop_before_target_action),
        "continue_after_found": bool(args.continue_after_found),
        "watch_new_stream_pages": bool(args.watch_new_stream_pages),
        "stream_stop_min_position": args.stream_stop_min_position,
        "states": [],
        "transitions": [],
        "actions": [],
        "findings": [],
        "stream_checkpoints": [],
        "found": False,
        "complete": False,
    }
    edge_count = 0
    stream_previous: dict[str, Any] | None = None
    stream_baseline_pages: set[str] = set()
    stream_stop_record: dict[str, Any] | None = None

    def persist() -> None:
        manifest["physical_edges"] = edge_count
        write_manifest(args.output_dir, manifest)

    def watch_stream(label: str) -> None:
        nonlocal stream_previous, stream_baseline_pages, stream_stop_record
        if not args.watch_new_stream_pages:
            return
        state = web.get_json("/api/state")
        inventory = parse_stream_position_inventory(
            str(state.get("registers", ""))
        )
        compact = {
            name: inventory[name]
            for name in (
                "calls", "returns", "changed", "reverse", "range_start",
                "range_end", "requested_bytes", "advanced_bytes",
                "pages_touched", "page_calls",
            )
        }
        if stream_previous is None:
            stream_previous = inventory
            stream_baseline_pages = set(inventory["page_calls"])
            manifest["stream_baseline"] = compact
            manifest["stream_baseline_pages"] = sorted(stream_baseline_pages)
            persist()
            return

        delta = stream_position_delta(
            {"stream_position": stream_previous},
            {"stream_position": inventory},
        )
        new_pages = sorted(
            page for page, count in inventory["page_calls"].items()
            if count and page not in stream_baseline_pages
        )
        if args.stream_stop_min_position is None:
            trigger_pages = new_pages
            extends_stop_position = False
        else:
            trigger_pages = [
                page for page in new_pages
                if ((int(page, 16) + 1) << 12) >
                   args.stream_stop_min_position
            ]
            extends_stop_position = (
                inventory["range_end"] > args.stream_stop_min_position
            )
        if delta["calls"] or new_pages:
            record = {
                "label": label,
                "edge_count": edge_count,
                "delta": delta,
                "new_pages": new_pages,
                "trigger_pages": trigger_pages,
                "extends_stop_position": extends_stop_position,
                "inventory": compact,
            }
            manifest["stream_checkpoints"].append(record)
            if (
                (trigger_pages or extends_stop_position)
                and stream_stop_record is None
            ):
                stream_stop_record = record
        stream_previous = inventory
        persist()

    def finish_stream_stop(position: GameState) -> bool:
        if stream_stop_record is None:
            return False
        checkpoint = capture_completed_checkpoint(
            web, args.output_dir, "new-stream-page",
        )
        manifest.update({
            "complete": True,
            "completion_reason": "new NPE stream page observed",
            "new_stream_page_position": position_record(position),
            "new_stream_page_frame_sha256": checkpoint["frame"]["sha256"],
            "new_stream_page_record": stream_stop_record,
        })
        persist()
        print(json.dumps({
            "new_stream_pages": stream_stop_record["trigger_pages"],
            "range_end": stream_stop_record["inventory"]["range_end"],
            "position": position_record(position),
            "edge_count": edge_count,
        }))
        return True

    def perform_move(
        direction: str, reason: str,
    ) -> tuple[GameState, dict[str, Any]]:
        nonlocal edge_count
        move = INPUT_PROBES[f"direction-{direction}"]
        retries: list[dict[str, Any]] = []
        for retry in range(1, args.max_edge_retries + 1):
            if edge_count >= args.max_edges:
                raise RuntimeError("physical edge budget exhausted")
            frame_sequence = int(web.get_json("/api/frame")["sequence"])
            before = web.get_json("/api/key-status")
            before_position = explorer_state(before)
            result = replay_step(
                web,
                move,
                press_timeout=args.press_timeout,
                release_timeout=args.release_timeout,
                poll_interval=args.poll_interval,
                settle=args.settle,
                pulse_duration=args.pulse_duration,
            )
            edge_count += 1
            violation = single_edge_violation(result)
            if violation:
                raise RuntimeError(
                    f"move {direction} was not one physical edge: {violation}"
                )
            try:
                _, path_delta = wait_for_direction_path(
                    web,
                    before,
                    direction,
                    timeout=args.controller_timeout,
                    poll_interval=args.poll_interval,
                    helper_timeout=args.transition_timeout,
                )
            except TimeoutError:
                retries.append({
                    "retry": retry,
                    "accepted_by_game": False,
                    "edge": result,
                })
                wait_for_render_cooldown(
                    web,
                    after_sequence=frame_sequence,
                    advances=args.frame_advances,
                    timeout=args.transition_timeout,
                    poll_interval=args.poll_interval,
                    allow_unchanged=True,
                )
                persist()
                continue

            wait_for_render_cooldown(
                web,
                after_sequence=frame_sequence,
                advances=args.frame_advances,
                timeout=args.transition_timeout,
                poll_interval=args.poll_interval,
                allow_unchanged=True,
            )
            after = web.get_json("/api/key-status")
            raise_if_key_status_faulted(web, after)
            after_position = explorer_state(after)
            retries.append({
                "retry": retry,
                "accepted_by_game": True,
                "controller_path_delta": path_delta,
                "movement": movement_state(after),
                "edge": result,
            })
            transition = {
                "index": len(manifest["transitions"]) + 1,
                "reason": reason,
                "direction": direction,
                "before": position_record(before_position),
                "after": position_record(after_position),
                "changed": after_position != before_position,
                "retries": retries,
            }
            manifest["transitions"].append(transition)
            persist()
            return after_position, transition
        raise TimeoutError(
            f"{direction} was not accepted after "
            f"{args.max_edge_retries} physical edges"
        )

    def perform_action(
        position: GameState, state_id: int,
    ) -> tuple[bool, int]:
        nonlocal edge_count
        action = INPUT_PROBES["primary-action"]
        retries: list[dict[str, Any]] = []
        for retry in range(1, args.max_edge_retries + 1):
            if edge_count >= args.max_edges:
                raise RuntimeError("physical edge budget exhausted")
            frame_sequence = int(web.get_json("/api/frame")["sequence"])
            before = web.get_json("/api/key-status")
            result = replay_step(
                web,
                action,
                press_timeout=args.press_timeout,
                release_timeout=args.release_timeout,
                poll_interval=args.poll_interval,
                settle=args.settle,
                pulse_duration=args.pulse_duration,
            )
            edge_count += 1
            violation = single_edge_violation(result)
            if violation:
                raise RuntimeError(
                    f"action at state {state_id} was not one physical edge: "
                    f"{violation}"
                )
            try:
                after, selector_delta, selector_return_delta, late_delta = (
                    wait_for_action_path(
                        web,
                        before,
                        timeout=args.controller_timeout,
                        poll_interval=args.poll_interval,
                    )
                )
            except TimeoutError:
                retries.append({
                    "retry": retry,
                    "accepted_by_game": False,
                    "edge": result,
                })
                wait_for_render_cooldown(
                    web,
                    after_sequence=frame_sequence,
                    advances=args.frame_advances,
                    timeout=args.transition_timeout,
                    poll_interval=args.poll_interval,
                    allow_unchanged=True,
                )
                persist()
                continue

            result_value = int(after["primary_action_selector_result"])
            retries.append({
                "retry": retry,
                "accepted_by_game": True,
                "selector_delta": selector_delta,
                "selector_return_delta": selector_return_delta,
                "late_path_delta": late_delta,
                "selector_result": result_value,
                "edge": result,
            })
            action_record = {
                "state_id": state_id,
                "position": position_record(position),
                "selector_delta": selector_delta,
                "selector_return_delta": selector_return_delta,
                "late_path_delta": late_delta,
                "selector_result": result_value,
                "retries": retries,
            }
            manifest["actions"].append(action_record)
            persist()
            return selector_delta == 1 and result_value != 0xFFFF, result_value
        raise TimeoutError(
            f"action at state {state_id} was not accepted after "
            f"{args.max_edge_retries} physical edges"
        )

    persist()
    try:
        web.set_matrix(None)
        current_state = web.get_json("/api/state")
        current_registers = str(current_state.get("registers", ""))
        if args.route_to_game and not game_ready(current_registers):
            wait_for(
                web,
                lambda registers: (
                    (decimal_field(registers, "MATRIX_READS") or 0)
                    >= args.minimum_matrix_reads
                    and application_state(registers) != 0x0078
                ),
                timeout=args.transition_timeout,
                poll_interval=0.5,
                description="stable desktop matrix scanning",
            )
            for step in ROUTE_TO_GAME:
                result = run_step(
                    web,
                    step,
                    press_timeout=args.press_timeout,
                    release_timeout=args.release_timeout,
                    poll_interval=args.poll_interval,
                    settle=args.route_settle,
                    use_bounded_status=False,
                )
                manifest["route"].append(result)
                persist()
        wait_for(
            web,
            game_ready,
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
        initial_status = web.get_json("/api/key-status")
        raise_if_key_status_faulted(web, initial_status)
        initial = explorer_state(initial_status)
        watch_stream("game-ready-baseline")
        manifest["initial_position"] = position_record(initial)
        visited: dict[GameState, int] = {}
        graph: dict[GameState, dict[str, GameState]] = {}
        attempted_directions: dict[GameState, set[str]] = {}
        state_paths: dict[GameState, list[str]] = {}
        action_tested: set[GameState] = set()
        resumed_edges = 0

        def register_position(
            position: GameState, path: list[str],
            resumed_from: str | None = None,
        ) -> int:
            existing = visited.get(position)
            if existing is not None:
                return existing
            state_id = len(visited)
            visited[position] = state_id
            state_paths[position] = list(path)
            attempted_directions[position] = set()
            graph[position] = {}
            record: dict[str, Any] = {
                "id": state_id,
                "position": position_record(position),
                "path": list(path),
            }
            if resumed_from is not None:
                record["resumed_from"] = resumed_from
            manifest["states"].append(record)
            return state_id

        for resume_path in args.resume_manifest:
            resume_name = str(resume_path)
            resumed = json.loads(resume_path.read_text(encoding="utf-8"))
            resumed_edges += int(resumed.get("physical_edges", 0))
            for state in resumed.get("states", []):
                register_position(
                    position_tuple(state["position"]),
                    [str(item) for item in state.get("path", [])],
                    resume_name,
                )
            for transition in resumed.get("transitions", []):
                before_position = position_tuple(transition["before"])
                after_position = position_tuple(transition["after"])
                direction = str(transition["direction"])
                register_position(before_position, [], resume_name)
                register_position(
                    after_position,
                    state_paths[before_position] + [direction],
                    resume_name,
                )
                graph[before_position][direction] = after_position
                if str(transition.get("reason", "")).endswith("explore"):
                    attempted_directions[before_position].add(direction)
                copied_transition = dict(transition)
                copied_transition["resumed_from"] = resume_name
                manifest["transitions"].append(copied_transition)
            for action_record in resumed.get("actions", []):
                position = position_tuple(action_record["position"])
                state_id = register_position(position, [], resume_name)
                action_tested.add(position)
                copied_action = dict(action_record)
                copied_action["state_id"] = state_id
                copied_action["resumed_from"] = resume_name
                manifest["actions"].append(copied_action)

        initial_id = register_position(initial, [])
        manifest["resumed_physical_edges"] = resumed_edges
        persist()

        target_world = (
            None if args.target_world_x is None else
            (args.target_world_x, args.target_world_y)
        )

        def stop_before_target_action(
            position: GameState,
            state_id: int,
        ) -> bool:
            if (
                not args.stop_before_target_action
                or target_world is None
                or not faces_world_target(position, target_world)
            ):
                return False
            wait_for_stable_frame(
                web,
                stable_duration=args.target_stable_duration,
                timeout=args.transition_timeout,
                poll_interval=max(args.poll_interval, 0.05),
            )
            checkpoint = capture_completed_checkpoint(
                web, args.output_dir, "target-before-action",
            )
            status = web.get_json("/api/key-status")
            manifest.update({
                "complete": True,
                "completion_reason": "stopped before target action",
                "stopped_before_target_action": True,
                "target_state_id": state_id,
                "target_position": position_record(position),
                "target_path": state_paths[position],
                "target_before_action_frame_sha256": (
                    checkpoint["frame"]["sha256"]
                ),
                "target_before_action_key_status": status,
            })
            persist()
            print(json.dumps({
                "stopped_before_target_action": True,
                "state_id": state_id,
                "position": position_record(position),
                "frame_sha256": checkpoint["frame"]["sha256"],
            }))
            return True

        if initial not in action_tested:
            if stop_before_target_action(initial, initial_id):
                return 0
            found, selector_result = perform_action(initial, initial_id)
            action_tested.add(initial)
            watch_stream(f"action-state-{initial_id}")
            if finish_stream_stop(initial):
                return 0
            if found and args.continue_after_found:
                manifest["found"] = True
                manifest["findings"].append({
                    "state_id": initial_id,
                    "position": position_record(initial),
                    "selector_result": selector_result,
                })
                persist()
            elif found:
                checkpoint = capture_completed_checkpoint(
                    web, args.output_dir, "target-found",
                )
                manifest.update({
                    "found": True,
                    "found_state_id": initial_id,
                    "selector_result": selector_result,
                    "frame_sha256": checkpoint["frame"]["sha256"],
                    "complete": True,
                })
                persist()
                print(json.dumps({
                    "found": True, "state_id": initial_id,
                }))
                return 0

        current = initial
        completion_reason = "reachable directed feedback graph exhausted"
        while edge_count < args.max_edges:
            remaining = [
                direction
                for direction in direction_order(current, target_world)
                if direction not in attempted_directions[current]
            ]
            if remaining:
                direction = remaining[0]
                attempted_directions[current].add(direction)
                reason = "graph-explore"
            else:
                route = route_to_unexplored(
                    current, graph, attempted_directions, target_world,
                )
                if route is None:
                    break
                if not route:
                    continue
                direction = route[0]
                reason = "graph-navigate"

            source = current
            next_position, _ = perform_move(direction, reason)
            watch_stream(
                f"move-{direction}-{len(manifest['transitions'])}"
            )
            if finish_stream_stop(next_position):
                return 0
            graph.setdefault(source, {})[direction] = next_position
            graph.setdefault(next_position, {})

            if next_position not in visited:
                if len(visited) >= args.max_states:
                    completion_reason = "state limit reached"
                    current = next_position
                    break
                path = list(state_paths[source]) + [direction]
                state_id = register_position(next_position, path)
                persist()

            if next_position not in action_tested:
                state_id = visited[next_position]
                if stop_before_target_action(next_position, state_id):
                    return 0
                found, selector_result = perform_action(
                    next_position, state_id,
                )
                action_tested.add(next_position)
                watch_stream(f"action-state-{state_id}")
                if finish_stream_stop(next_position):
                    return 0
                if found and args.continue_after_found:
                    manifest["found"] = True
                    manifest["findings"].append({
                        "state_id": state_id,
                        "position": position_record(next_position),
                        "path": state_paths[next_position],
                        "selector_result": selector_result,
                    })
                    persist()
                elif found:
                    checkpoint = capture_completed_checkpoint(
                        web, args.output_dir, "target-found",
                    )
                    manifest.update({
                        "found": True,
                        "found_state_id": state_id,
                        "found_position": position_record(next_position),
                        "found_path": state_paths[next_position],
                        "selector_result": selector_result,
                        "frame_sha256": checkpoint["frame"]["sha256"],
                        "complete": True,
                    })
                    persist()
                    print(json.dumps({
                        "found": True,
                        "state_id": state_id,
                        "position": position_record(next_position),
                        "selector_result": selector_result,
                    }))
                    return 0
            current = next_position

        if edge_count >= args.max_edges:
            completion_reason = "physical edge limit reached"

        manifest.update({
            "complete": True,
            "found": bool(manifest["findings"]),
            "states_explored": len(visited),
            "completion_reason": completion_reason,
        })
        persist()
        print(json.dumps({
            "found": bool(manifest["findings"]),
            "states": len(visited),
            "physical_edges": edge_count,
        }))
        return 0
    except Exception as exc:
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        manifest["failed_at_monotonic"] = time.monotonic()
        try:
            status = web.get_json("/api/key-status")
            manifest["failure_key_status"] = status
        except Exception as status_exc:  # retain the primary failure
            manifest["failure_status_error"] = (
                f"{type(status_exc).__name__}: {status_exc}"
            )
        persist()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
