#!/usr/bin/env python3
"""Run a bounded native NPE play session and prove the guest exit path.

The monitor only presses recovered 8x8 matrix positions through the Web/QOM
hardware bridge.  It does not write guest RAM, select menus in the host, or
alter an LCD frame.  A successful run proves all of the following:

* the normal physical route reaches the native NPE game controller;
* repeated direction events are mapped and consumed by original guest code;
* no missing-ROM, unsupported-instruction, or invalid-control diagnostic is
  raised for the requested wall-clock duration; and
* physical Start key M55/event 0xB0 changes application state 0x0078 to
  0x00FF; and
* when the first event is consumed by the modal game controller, a second
  physical Start edge reaches the root foreground and runs the native desktop
  renderer.  Merely observing state 0x00FF or a footer blit is not accepted as
  a successful return to the menu.

The default duration is ten minutes.  ``--action-count`` selects an exact
edge-count run instead, which is useful for repeatable input stress tests.
Checkpoints contain one 28,800-byte gray5 frame and compact JSON rather than
the multi-hundred-KiB full diagnostic payload, which keeps long-running
regression artifacts bounded.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

try:
    from probe_np560_matrix_route import (
        RouteStep,
        WebBridge,
        diagnostic_failure,
        raise_if_key_status_faulted,
        replay_step,
    )
except ModuleNotFoundError:  # imported as scripts.monitor_np560_npe_play_session
    from .probe_np560_matrix_route import (
        RouteStep,
        WebBridge,
        diagnostic_failure,
        raise_if_key_status_faulted,
        replay_step,
    )


ROUTE_TO_GAME = (
    RouteStep("Start", 55, 0xB0),
    RouteStep("Entertainment", 53, 0x86),
    RouteStep("GameWorld", 37, 0x83),
    RouteStep("NPEList", 53, 0x86),
    RouteStep("Hero", 53, 0x86),
    RouteStep("NewJourney", 53, 0x86),
    RouteStep("StartGame", 53, 0x86),
)

# Current recovered ROMs can finish cold boot with the lower-left Start menu
# already expanded.  In that state another M55 closes the menu and shifts the
# entire route into the Study page.  Keep the historical closed-menu route
# above, but omit its first toggle when the LCD proves the menu is expanded.
ROUTE_FROM_EXPANDED_START_MENU = ROUTE_TO_GAME[1:]

BOOT_START_STEP = RouteStep("BootStart", 55, 0xB0)

# These four physical positions and events were independently observed in the
# live 37:1312 controller and its exact direction helper.  A closed loop keeps
# the player near its starting area while still exercising all four paths.
PLAY_ACTIONS = (
    RouteStep("Down", 37, 0x83),
    RouteStep("Right", 29, 0x81),
    RouteStep("Up", 61, 0x82),
    RouteStep("Left", 45, 0x80),
)

EXIT_STEP = RouteStep("StartExit", 55, 0xB0)

# Deterministic raw gray5 frame emitted after the Hero splash has completely
# faded and the original "新的征程 / 再续前缘 / 退出游戏" menu is ready.
HERO_JOURNEY_MENU_SHA256 = (
    "5e5577bdeba08bc5b6d147270ac7ebbf0fb5983f3ae13b3a6b4cdd7bd9498947"
)


def decimal_field(registers: str, name: str) -> int | None:
    match = re.search(rf"\b{re.escape(name)}:(\d+)\b", registers)
    return int(match.group(1), 10) if match else None


def application_state(registers: str) -> int | None:
    match = re.search(r"(?m)^APPLICATION_STATE=STATE:([0-9A-Fa-f]{4})\b",
                      registers)
    return int(match.group(1), 16) if match else None


def desktop_blit_count(registers: str) -> int | None:
    match = re.search(r"(?m)^DESKTOP_BLIT_TRACE=COUNT:(\d+)\b", registers)
    return int(match.group(1), 10) if match else None


def root_render_count(registers: str) -> int | None:
    match = re.search(r"(?m)^ROOT_RENDER_FLAGS=COUNT:(\d+)\b", registers)
    return int(match.group(1), 10) if match else None


def desktop_menu_ready(registers: str, render_count_before: int) -> bool:
    return bool(
        application_state(registers) == 0x00FF
        and (root_render_count(registers) or 0) > render_count_before
    )


def start_menu_expanded(state: dict[str, Any]) -> bool:
    """Recognize the cold-boot Start list without reading guest RAM.

    The expanded list begins below y=35, leaving the 0..149,25..34 strip
    blank.  A closed Start list exposes the active top-category submenu in
    that strip.  This LCD-only gate is intentionally used only after the
    native root renderer has reached application state 0x00FF.
    """
    if state.get("format") != "gray5":
        return False
    width = int(state.get("width", 0))
    height = int(state.get("height", 0))
    if width < 150 or height < 35:
        return False
    try:
        frame = base64.b64decode(str(state.get("frame", "")), validate=True)
    except (ValueError, TypeError):
        return False
    if len(frame) != width * height:
        return False
    dark = sum(
        frame[y * width + x] < 16
        for y in range(25, 35)
        for x in range(150)
    )
    return dark < 50


def lcd_frame_sha256(state: dict[str, Any]) -> str | None:
    """Return the raw gray5 frame hash, or ``None`` for an invalid frame."""
    if state.get("format") != "gray5":
        return None
    width = int(state.get("width", 0))
    height = int(state.get("height", 0))
    try:
        frame = base64.b64decode(str(state.get("frame", "")), validate=True)
    except (ValueError, TypeError):
        return None
    if width <= 0 or height <= 0 or len(frame) != width * height:
        return None
    return hashlib.sha256(frame).hexdigest()


def hero_journey_menu_ready(state: dict[str, Any]) -> bool:
    """Recognize the deterministic post-splash Hero journey menu."""
    return lcd_frame_sha256(state) == HERO_JOURNEY_MENU_SHA256


def game_loop(registers: str) -> dict[str, int] | None:
    match = re.search(
        r"(?m)^NPE_GAME_LOOP="
        r"GRID:(\d+)/(\d+) INIT:(\d+)/(\d+) "
        r"RANGE:(\d+) RAND:(\d+) CMP:(\d+) "
        r"DRAW:(\d+)/(\d+) ITEM:(\d+) STATEDISP:(\d+)",
        registers,
    )
    if match is None:
        return None
    names = (
        "grid_calls", "grid_returns", "init_calls", "init_returns",
        "range_calls", "randomize_calls", "compare_calls",
        "draw_calls", "draw_returns", "item_calls", "state_dispatches",
    )
    return dict(zip(names, (int(value, 10) for value in match.groups())))


def game_ready(registers: str) -> bool:
    loop = game_loop(registers)
    return bool(
        application_state(registers) == 0x0078
        and loop is not None
        and loop["grid_calls"] == loop["grid_returns"]
        and loop["init_calls"] == loop["init_returns"]
        and loop["draw_calls"] > 0
        and loop["draw_calls"] == loop["draw_returns"]
        and diagnostic_failure(registers) is None
    )


def diagnostic_summary(registers: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in ("ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL"):
        match = re.search(rf"(?m)^{name}=([^\r\n]+)", registers)
        result[name.lower()] = match.group(1) if match else "absent"
    return result


def compact_state(state: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    registers = str(state.get("registers", ""))
    frame = base64.b64decode(str(state.get("frame", "")), validate=True)
    width = int(state.get("width", 0))
    height = int(state.get("height", 0))
    if state.get("format") != "gray5" or len(frame) != width * height:
        raise ValueError("Web state does not contain a valid gray5 LCD frame")
    pc_match = re.search(r"(?m)^PC=([^\r\n]+)", registers)
    return ({
        "running": bool(state.get("running", False)),
        "pc": pc_match.group(1) if pc_match else None,
        "application_state": application_state(registers),
        "matrix_reads": decimal_field(registers, "MATRIX_READS"),
        "desktop_blit_count": desktop_blit_count(registers),
        "root_render_count": root_render_count(registers),
        "game_loop": game_loop(registers),
        "diagnostics": diagnostic_summary(registers),
        "frame": {
            "format": "gray5",
            "width": width,
            "height": height,
            "bytes": len(frame),
            "sha256": hashlib.sha256(frame).hexdigest(),
        },
    }, frame)


def capture_checkpoint(
    web: WebBridge, output_dir: Path, prefix: str,
) -> dict[str, Any]:
    state = web.get_json("/api/state")
    registers = str(state.get("registers", ""))
    failure = diagnostic_failure(registers)
    if failure:
        raise RuntimeError(failure)
    summary, frame = compact_state(state)
    summary["key_status"] = web.get_json("/api/key-status")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{prefix}.gray5").write_bytes(frame)
    (output_dir / f"{prefix}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def wait_for(
    web: WebBridge,
    predicate: Callable[[str], bool],
    *,
    timeout: float,
    poll_interval: float,
    description: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = web.get_json("/api/state")
        registers = str(last.get("registers", ""))
        failure = diagnostic_failure(registers)
        if failure:
            raise RuntimeError(failure)
        if predicate(registers):
            return last
        time.sleep(poll_interval)
    raise TimeoutError(f"timed out waiting for {description}")


def wait_for_lcd(
    web: WebBridge,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    timeout: float,
    poll_interval: float,
    description: str,
) -> dict[str, Any]:
    """Wait on completed LCD frames while still enforcing fault diagnostics."""
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status = web.get_json("/api/key-status")
        raise_if_key_status_faulted(web, status)
        last = web.get_json("/api/frame")
        if predicate(last):
            return last
        time.sleep(poll_interval)
    raise TimeoutError(f"timed out waiting for {description}")


def write_manifest(output_dir: Path, manifest: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = output_dir / "manifest.json.tmp"
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output_dir / "manifest.json")


def key_counter_snapshot(status: dict[str, Any]) -> tuple[int, int, int, int]:
    return tuple(int(status.get(name, 0)) for name in (
        "candidates", "maps", "acknowledgements", "modal_acknowledgements",
    ))


def wait_for_key_quiescence(
    web: WebBridge,
    *,
    quiet_duration: float,
    timeout: float,
    poll_interval: float,
) -> dict[str, Any]:
    """Wait until all key-pipeline counters stay unchanged for a window."""
    deadline = time.monotonic() + timeout
    stable_since = time.monotonic()
    status = web.get_json("/api/key-status")
    counters = key_counter_snapshot(status)
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        current = web.get_json("/api/key-status")
        current_counters = key_counter_snapshot(current)
        if current_counters != counters:
            status = current
            counters = current_counters
            stable_since = time.monotonic()
            continue
        if time.monotonic() - stable_since >= quiet_duration:
            return current
    raise TimeoutError("guest key pipeline did not become quiescent")


def single_edge_violation(result: dict[str, Any]) -> str | None:
    """Return why one asserted matrix edge produced a non-single delivery."""
    counts = {
        "candidate": int(result.get("candidate_writes_total", -1)),
        "map": int(result.get("maps_total", -1)),
        "consumer_ack": int(result.get(
            "consumer_acknowledgements_total", -1,
        )),
    }
    if all(value == 1 for value in counts.values()):
        return None
    return ", ".join(f"{name}={value}" for name, value in counts.items())


def play_limit_reached(
    action_index: int,
    elapsed: float,
    *,
    duration: float | None,
    action_count: int | None,
) -> bool:
    """Return whether the selected, mutually exclusive play limit is met."""
    if action_count is not None:
        return action_index >= action_count
    if duration is None:
        raise ValueError("a duration or action count is required")
    return elapsed >= duration


def run_step(
    web: WebBridge,
    step: RouteStep,
    *,
    press_timeout: float,
    release_timeout: float,
    poll_interval: float,
    settle: float,
    frame_stable_samples: int = 0,
    frame_stable_timeout: float = 3.0,
    frame_stable_interval: float = 0.2,
    use_bounded_status: bool = True,
    pulse_duration: float = 0.0,
) -> dict[str, Any]:
    return replay_step(
        web,
        step,
        press_timeout=press_timeout,
        release_timeout=release_timeout,
        poll_interval=poll_interval,
        settle=settle,
        frame_stable_samples=frame_stable_samples,
        frame_stable_timeout=frame_stable_timeout,
        frame_stable_interval=frame_stable_interval,
        use_bounded_status=use_bounded_status,
        pulse_duration=pulse_duration,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8781")
    parser.add_argument("--output-dir", type=Path, required=True)
    limit = parser.add_mutually_exclusive_group()
    limit.add_argument(
        "--duration", type=float,
        help="wall-clock play duration in seconds (default: 600)",
    )
    limit.add_argument(
        "--action-count", type=int,
        help="run exactly this many physical play-key edges",
    )
    parser.add_argument("--action-interval", type=float, default=5.0)
    parser.add_argument("--checkpoint-interval", type=float, default=60.0)
    parser.add_argument(
        "--manifest-action-interval", type=int, default=1,
        help=(
            "persist the growing manifest every N play edges; failures and "
            "checkpoints are always written (default: 1)"
        ),
    )
    parser.add_argument("--startup-timeout", type=float, default=240.0)
    parser.add_argument("--transition-timeout", type=float, default=120.0)
    parser.add_argument("--request-timeout", type=float, default=10.0)
    parser.add_argument("--press-timeout", type=float, default=5.0)
    parser.add_argument(
        "--release-timeout", type=float, default=30.0,
        help=(
            "seconds allowed for the guest scanner to observe key release; "
            "NPE startup loaders can pause scanning after already mapping "
            "and acknowledging the edge"
        ),
    )
    parser.add_argument("--poll-interval", type=float, default=0.02)
    parser.add_argument("--settle", type=float, default=0.35)
    parser.add_argument(
        "--route-settle", type=float, default=2.0,
        help=(
            "seconds to leave each native menu/page transition stable before "
            "the next route key (default: 2)"
        ),
    )
    parser.add_argument(
        "--route-frame-stable-samples", type=int, default=3,
        help=(
            "wait for this many identical completed LCD frames after every "
            "route key; 0 uses --route-settle only (default: 3)"
        ),
    )
    parser.add_argument(
        "--play-pulse-duration", type=float, default=0.0,
        help=(
            "release play keys after this fixed wall-clock pulse instead of "
            "waiting for the candidate observation (default: disabled)"
        ),
    )
    parser.add_argument(
        "--input-quiet-duration", type=float, default=0.25,
        help="stable counter window required before play begins (default: 0.25s)",
    )
    parser.add_argument(
        "--strict-single-edge", action="store_true",
        help=(
            "require every play/exit matrix assertion to produce exactly one "
            "candidate, map, and guest-consumer acknowledgement"
        ),
    )
    parser.add_argument(
        "--desktop-settle", type=float, default=5.0,
        help="seconds to leave the native root menu stable before capture",
    )
    parser.add_argument(
        "--exit-transition-settle", type=float, default=2.0,
        help=(
            "seconds to leave application-state exit cleanup undisturbed "
            "before requesting a root-menu redraw (default: 2)"
        ),
    )
    parser.add_argument("--minimum-matrix-reads", type=int, default=2500)
    parser.add_argument(
        "--route-to-game", action="store_true",
        help="wait for stable boot and traverse the seven recovered menu keys",
    )
    args = parser.parse_args()
    if args.duration is None and args.action_count is None:
        args.duration = 600.0

    if ((args.duration is not None and args.duration <= 0) or
            (args.action_count is not None and args.action_count <= 0) or
            args.action_interval <= 0):
        parser.error("duration, action count, and action interval must be positive")
    if (args.checkpoint_interval <= 0 or
            args.manifest_action_interval <= 0 or
            args.minimum_matrix_reads < 0):
        parser.error("checkpoint interval must be positive and reads non-negative")
    if (args.route_frame_stable_samples not in (0,) and
            args.route_frame_stable_samples < 2):
        parser.error("route frame stable samples must be 0 or at least 2")
    if min(
        args.startup_timeout, args.transition_timeout, args.request_timeout,
        args.press_timeout, args.release_timeout, args.poll_interval,
        args.input_quiet_duration,
    ) <= 0 or min(
        args.settle, args.route_settle, args.desktop_settle,
        args.play_pulse_duration,
        args.exit_transition_settle,
    ) < 0:
        parser.error("timeouts must be positive and settle values non-negative")

    web = WebBridge(args.root, args.request_timeout)
    web.set_matrix(None)
    manifest: dict[str, Any] = {
        "schema": "np560-npe-play-session-v1",
        "root": args.root,
        "requested_duration_seconds": args.duration,
        "requested_action_count": args.action_count,
        "action_interval_seconds": args.action_interval,
        "manifest_action_interval": args.manifest_action_interval,
        "minimum_matrix_reads": args.minimum_matrix_reads,
        "input_quiet_duration_seconds": args.input_quiet_duration,
        "play_pulse_duration_seconds": args.play_pulse_duration,
        "exit_transition_settle_seconds": args.exit_transition_settle,
        "strict_single_edge": bool(args.strict_single_edge),
        "route_to_game_requested": bool(args.route_to_game),
        "route_frame_stable_samples": args.route_frame_stable_samples,
        "route_boot_start_required": None,
        "route_start_menu_expanded": None,
        "route": [],
        "actions": [],
        "checkpoints": [],
        "failed_action": None,
        "exit": None,
        "complete": False,
    }
    write_manifest(args.output_dir, manifest)

    try:
        if args.route_to_game:
            startup_state = wait_for(
                web,
                lambda registers: (
                    (decimal_field(registers, "MATRIX_READS") or 0)
                    >= args.minimum_matrix_reads
                    and application_state(registers) in (0x00FD, 0x00FF)
                ),
                timeout=args.startup_timeout,
                poll_interval=0.5,
                description="native startup or desktop matrix scanning",
            )
            startup_registers = str(startup_state.get("registers", ""))
            boot_start_required = application_state(startup_registers) == 0x00FD
            manifest["route_boot_start_required"] = boot_start_required
            if boot_start_required:
                result = run_step(
                    web, BOOT_START_STEP,
                    press_timeout=args.press_timeout,
                    release_timeout=args.release_timeout,
                    poll_interval=args.poll_interval,
                    settle=args.route_settle,
                    frame_stable_samples=args.route_frame_stable_samples,
                    frame_stable_timeout=args.transition_timeout,
                    use_bounded_status=False,
                )
                manifest["route"].append(result)
                write_manifest(args.output_dir, manifest)
                desktop_state = wait_for(
                    web,
                    lambda registers: application_state(registers) == 0x00FF,
                    timeout=args.transition_timeout,
                    poll_interval=0.25,
                    description="native desktop after startup Start key",
                )
            else:
                desktop_state = startup_state
            expanded = start_menu_expanded(desktop_state)
            manifest["route_start_menu_expanded"] = expanded
            route = (ROUTE_FROM_EXPANDED_START_MENU if expanded
                     else ROUTE_TO_GAME)
            write_manifest(args.output_dir, manifest)
            # The penultimate Enter launches Hero.  Its animated studio splash
            # can remain on screen much longer than an ordinary menu redraw;
            # keys are mapped and acknowledged during that interval but have
            # no journey-menu action.  Run every step except the final
            # StartGame confirmation, then wait for the exact guest LCD menu.
            for step in route[:-1]:
                result = run_step(
                    web, step,
                    press_timeout=args.press_timeout,
                    release_timeout=args.release_timeout,
                    poll_interval=args.poll_interval,
                    settle=args.route_settle,
                    frame_stable_samples=args.route_frame_stable_samples,
                    frame_stable_timeout=args.transition_timeout,
                    use_bounded_status=False,
                )
                manifest["route"].append(result)
                write_manifest(args.output_dir, manifest)
            wait_for_lcd(
                web,
                hero_journey_menu_ready,
                timeout=args.transition_timeout,
                poll_interval=0.25,
                description="Hero journey menu after animated splash",
            )
            step = route[-1]
            result = run_step(
                web, step,
                press_timeout=args.press_timeout,
                release_timeout=args.release_timeout,
                poll_interval=args.poll_interval,
                settle=args.route_settle,
                frame_stable_samples=args.route_frame_stable_samples,
                frame_stable_timeout=args.transition_timeout,
                use_bounded_status=False,
            )
            manifest["route"].append(result)
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
            quiet_duration=args.input_quiet_duration,
            timeout=args.transition_timeout,
            poll_interval=args.poll_interval,
        )
        initial = capture_checkpoint(web, args.output_dir, "0000-game-ready")
        manifest["checkpoints"].append({
            "elapsed_seconds": 0.0,
            "prefix": "0000-game-ready",
            "frame_sha256": initial["frame"]["sha256"],
        })
        write_manifest(args.output_dir, manifest)

        started = time.monotonic()
        next_action = started
        next_checkpoint = started + args.checkpoint_interval
        action_index = 0
        checkpoint_index = 1
        while True:
            now = time.monotonic()
            elapsed = now - started
            if play_limit_reached(
                action_index,
                elapsed,
                duration=args.duration,
                action_count=args.action_count,
            ):
                break
            if now < next_action:
                time.sleep(min(next_action - now, 0.25))
                continue
            step = PLAY_ACTIONS[action_index % len(PLAY_ACTIONS)]
            result = run_step(
                web, step,
                press_timeout=args.press_timeout,
                release_timeout=args.release_timeout,
                poll_interval=args.poll_interval,
                settle=args.settle,
                pulse_duration=args.play_pulse_duration,
            )
            if args.strict_single_edge:
                violation = single_edge_violation(result)
                if violation:
                    result["single_edge_violation"] = violation
                    result["elapsed_seconds"] = round(
                        time.monotonic() - started, 3
                    )
                    manifest["failed_action"] = result
                    write_manifest(args.output_dir, manifest)
                    raise RuntimeError(
                        f"{step.label} physical edge was not single: "
                        f"{violation}"
                    )
            after_status = web.get_json("/api/key-status")
            if "application_state" in after_status:
                raise_if_key_status_faulted(web, after_status)
                if int(after_status["application_state"]) != 0x0078:
                    raise RuntimeError(
                        "NPE foreground left application state 0x0078 "
                        "during play"
                    )
            else:
                after = web.get_json("/api/state")
                registers = str(after.get("registers", ""))
                if application_state(registers) != 0x0078:
                    raise RuntimeError(
                        "NPE foreground left application state 0x0078 "
                        "during play"
                    )
                failure = diagnostic_failure(registers)
                if failure:
                    raise RuntimeError(failure)
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            manifest["actions"].append(result)
            action_index += 1
            next_action += args.action_interval

            now = time.monotonic()
            if now >= next_checkpoint:
                prefix = f"{checkpoint_index:04d}-play"
                checkpoint = capture_checkpoint(web, args.output_dir, prefix)
                manifest["checkpoints"].append({
                    "elapsed_seconds": round(now - started, 3),
                    "prefix": prefix,
                    "frame_sha256": checkpoint["frame"]["sha256"],
                })
                checkpoint_index += 1
                while next_checkpoint <= now:
                    next_checkpoint += args.checkpoint_interval
            if action_index % args.manifest_action_interval == 0:
                write_manifest(args.output_dir, manifest)

        observed_duration = time.monotonic() - started
        before_exit_state = web.get_json("/api/state")
        before_exit_registers = str(before_exit_state.get("registers", ""))
        before_blits = desktop_blit_count(before_exit_registers) or 0
        before_root_renders = root_render_count(before_exit_registers) or 0
        exit_steps = []
        exit_steps.append(run_step(
            web, EXIT_STEP,
            press_timeout=args.press_timeout,
            release_timeout=args.release_timeout,
            poll_interval=args.poll_interval,
            settle=args.settle,
        ))
        if args.strict_single_edge:
            violation = single_edge_violation(exit_steps[-1])
            if violation:
                exit_steps[-1]["single_edge_violation"] = violation
                manifest["failed_action"] = exit_steps[-1]
                write_manifest(args.output_dir, manifest)
                raise RuntimeError(
                    "StartExit physical edge was not single: " + violation
                )
        state_after_game_exit = wait_for(
            web,
            lambda registers: application_state(registers) == 0x00FF,
            timeout=args.transition_timeout,
            poll_interval=0.25,
            description="native game state exit after Start key",
        )
        after_exit_registers = str(state_after_game_exit.get("registers", ""))
        manifest["exit"] = {
            "steps": exit_steps,
            "application_state_before": application_state(
                before_exit_registers
            ),
            "application_state_after": application_state(after_exit_registers),
            "desktop_blits_before": before_blits,
            "desktop_blits_after": desktop_blit_count(after_exit_registers),
            "root_renders_before": before_root_renders,
            "root_renders_after": root_render_count(after_exit_registers),
            "root_menu_complete": False,
        }
        write_manifest(args.output_dir, manifest)
        wait_for_key_quiescence(
            web,
            quiet_duration=args.input_quiet_duration,
            timeout=args.transition_timeout,
            poll_interval=args.poll_interval,
        )
        if args.exit_transition_settle:
            time.sleep(args.exit_transition_settle)
        state_after_game_exit = web.get_json("/api/state")
        after_exit_registers = str(state_after_game_exit.get("registers", ""))
        failure = diagnostic_failure(after_exit_registers)
        if failure:
            raise RuntimeError(failure)

        # In an active game the first B0 edge belongs to the modal controller:
        # it closes application state 0078 but can leave the last game body in
        # LCD GRAM.  A fresh B0 edge is then delivered to the root foreground
        # and requests the real menu redraw.  On shorter paths the first edge
        # may already have rendered the root, so avoid an unnecessary toggle.
        if not desktop_menu_ready(after_exit_registers, before_root_renders):
            exit_steps.append(run_step(
                web, RouteStep("StartMenuAfterExit", 55, 0xB0),
                press_timeout=args.press_timeout,
                release_timeout=args.release_timeout,
                poll_interval=args.poll_interval,
                settle=args.settle,
                use_bounded_status=False,
            ))
            manifest["exit"]["steps"] = exit_steps
            write_manifest(args.output_dir, manifest)
            if args.strict_single_edge:
                violation = single_edge_violation(exit_steps[-1])
                if violation:
                    exit_steps[-1]["single_edge_violation"] = violation
                    manifest["failed_action"] = exit_steps[-1]
                    write_manifest(args.output_dir, manifest)
                    raise RuntimeError(
                        "StartMenuAfterExit physical edge was not single: " +
                        violation
                    )

        final_state = wait_for(
            web,
            lambda registers: desktop_menu_ready(
                registers, before_root_renders
            ),
            timeout=args.transition_timeout,
            poll_interval=0.25,
            description="native root-menu render after game exit",
        )
        if args.desktop_settle:
            time.sleep(args.desktop_settle)
            final_state = web.get_json("/api/state")
            final_after_settle = str(final_state.get("registers", ""))
            failure = diagnostic_failure(final_after_settle)
            if failure:
                raise RuntimeError(failure)
            if not desktop_menu_ready(final_after_settle, before_root_renders):
                raise RuntimeError(
                    "native root menu did not remain active after settle"
                )
        final_registers = str(final_state.get("registers", ""))
        final = capture_checkpoint(web, args.output_dir, "final-desktop")
        exit_result = {
            "steps": exit_steps,
            "application_state_before": application_state(
                before_exit_registers
            ),
            "application_state_after": application_state(final_registers),
            "desktop_blits_before": before_blits,
            "desktop_blits_after": desktop_blit_count(final_registers),
            "root_renders_before": before_root_renders,
            "root_renders_after": root_render_count(final_registers),
            "root_menu_complete": True,
        }
        manifest.update({
            "observed_duration_seconds": round(observed_duration, 3),
            "ten_minute_requirement_met": bool(
                args.duration is not None and observed_duration >= 600.0
            ),
            "action_count_requirement_met": bool(
                args.action_count is not None and
                len(manifest["actions"]) == args.action_count
            ),
            "exit": exit_result,
            "final_frame_sha256": final["frame"]["sha256"],
            "complete": True,
        })
        write_manifest(args.output_dir, manifest)
        print(
            "NPE play session passed: "
            f"{observed_duration:.1f}s, {len(manifest['actions'])} actions, "
            f"application 0078->00FF, {len(exit_steps)} Start edge(s), "
            f"root renders {before_root_renders}->"
            f"{exit_result['root_renders_after']}"
        )
        return 0
    except Exception as error:
        manifest["error"] = f"{type(error).__name__}: {error}"
        write_manifest(args.output_dir, manifest)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
