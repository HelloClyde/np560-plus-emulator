#!/usr/bin/env python3
"""Diff hardware-register writes while a real NPE game receives input.

This probe never writes guest RAM and never injects a decoded application
event.  It drives the existing Web/QEMU 8x8 matrix, requires the original
guest scanner/consumer chain to acknowledge each edge, and compares the
observer-only unbanked, banked-Fxxx and direct-SFR inventories before and
after every step.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

try:
    from monitor_np560_npe_play_session import (
        PLAY_ACTIONS,
        compact_state,
        game_ready,
        write_manifest,
    )
    from probe_np560_matrix_route import (
        RouteStep,
        WebBridge,
        diagnostic_failure,
        replay_step,
    )
except ModuleNotFoundError:  # imported as scripts.probe_...
    from .monitor_np560_npe_play_session import (
        PLAY_ACTIONS,
        compact_state,
        game_ready,
        write_manifest,
    )
    from .probe_np560_matrix_route import (
        RouteStep,
        WebBridge,
        diagnostic_failure,
        replay_step,
    )


SFR_LINE = re.compile(
    r"(?m)^UNBANKED_SFR_WRITE=TOTAL:(\d+) UNKNOWN:(\d+) "
    r"BUCKETS:([^\r\n]*?) TRACE:([^\r\n]*)$"
)
BANKED_LINE = re.compile(
    r"(?m)^BANKED_FXXX_WRITE=TOTAL:(\d+) UNKNOWN:(\d+) "
    r"BUCKETS:([^\r\n]*?) TRACE:([^\r\n]*)$"
)
DIRECT_LINE = re.compile(
    r"(?m)^DIRECT_SFR_WRITE=TOTAL:(\d+) "
    r"COUNTS:([^\r\n]*?) TRACE:([^\r\n]*)$"
)
STREAM_POSITION_LINE = re.compile(
    r"(?m)^NPE_STREAM_POSITION=CALLS:(\d+) RETURNS:(\d+) "
    r"CHANGED:(\d+) REVERSE:(\d+) RANGE:([0-9A-Fa-f]{8})-"
    r"([0-9A-Fa-f]{8}) REQUESTED:(\d+) ADVANCED:(\d+) "
    r"PAGES:(\d+) TRACE:([^\r\n]*)$"
)
STREAM_IO_LINE = re.compile(r"(?m)^NPE_GAME_TABLE=.* TRACE:([^\r\n]*)$")
STREAM_IO_ENTRY = re.compile(
    r"#(\d+)/([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})/"
    r"s([0-9A-Fa-f]{8})/d([0-9A-Fa-f]{8})/n([0-9A-Fa-f]{4})/"
    r"p([0-9A-Fa-f]{8})>([0-9A-Fa-f]{8})/"
    r"m([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})/"
    r"r([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})/"
    r"e([0-9A-Fa-f]{4})/w(\d+)"
)
STREAM_RESOLVE_LINE = re.compile(
    r"(?m)^NPE_STREAM_RESOLVE=CALLS:(\d+) RETURNS:(\d+) "
    r"ACTIVE:(\d+) TRACE:([^\r\n]*)$"
)
STREAM_RESOLVE_ENTRY = re.compile(
    r"#(\d+)/([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})/"
    r"s([0-9A-Fa-f]{6})/o([0-9A-Fa-f]{8})/w([0-9A-Fa-f]{4})/"
    r"p([0-9A-Fa-f]{8})>([0-9A-Fa-f]{8})/"
    r"r([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})/e([0-9A-Fa-f]{4})"
)
HIGH_STREAM_IO_LINE = re.compile(
    r"(?m)^NPE_HIGH_STREAM_IO=CALLS:(\d+) RETURNS:(\d+) "
    r"ACTIVE:(\d+) TRACE:([^\r\n]*)$"
)
HIGH_STREAM_IO_ENTRY = re.compile(
    r"#(\d+)/([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})/"
    r"d([0-9A-Fa-f]{6})/n([0-9A-Fa-f]{4})/"
    r"p([0-9A-Fa-f]{8})>([0-9A-Fa-f]{8})/"
    r"r([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})/e([0-9A-Fa-f]{4})"
)
TRANSITION_LEAF_LINE = re.compile(
    r"(?m)^NPE_TRANSITION_LEAF=CALLS:(\d+) RETURNS:(\d+) "
    r"LOW:(\d+) HIGH:(\d+) TRACE:([^\r\n]*)$"
)
TRANSITION_LEAF_ENTRY = re.compile(
    r"#(\d+)/([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})/"
    r"sp([0-9A-Fa-f]{4})/s([0-9A-Fa-f]{4})/f([0-9A-Fa-f]{4})/"
    r"a([0-9A-Fa-f]{4}),([0-9A-Fa-f]{4}),([0-9A-Fa-f]{4}),"
    r"([0-9A-Fa-f]{4}),([0-9A-Fa-f]{4}),([0-9A-Fa-f]{4})/"
    r"b([LH-])/r([0-9A-Fa-f]{4})"
)
BUCKET = re.compile(r"F([0-9A-Fa-f])=(\d+)")
DIRECT_COUNT = re.compile(r"([0-9A-Fa-f]{2})=(\d+)")
STREAM_PAGE_COUNT = re.compile(r"([0-9A-Fa-f]{3})=(\d+)")


def parse_inventory(
    registers: str, pattern: re.Pattern[str], label: str,
) -> dict[str, Any]:
    match = pattern.search(registers)
    if match is None:
        raise RuntimeError(f"{label} diagnostics are absent")
    buckets = {
        int(index, 16): int(count, 10)
        for index, count in BUCKET.findall(match.group(3))
    }
    if set(buckets) != set(range(16)):
        raise RuntimeError(f"incomplete SFR bucket inventory: {buckets!r}")
    trace = match.group(4)
    return {
        "total": int(match.group(1), 10),
        "unknown": int(match.group(2), 10),
        "buckets": {f"F{index:X}": buckets[index] for index in range(16)},
        "trace": [] if trace == "none" else trace.split(";"),
        "line": match.group(0),
    }


def parse_sfr_inventory(registers: str) -> dict[str, Any]:
    return parse_inventory(registers, SFR_LINE, "UNBANKED_SFR_WRITE")


def parse_banked_inventory(registers: str) -> dict[str, Any]:
    return parse_inventory(registers, BANKED_LINE, "BANKED_FXXX_WRITE")


def parse_direct_inventory(registers: str) -> dict[str, Any]:
    match = DIRECT_LINE.search(registers)
    if match is None:
        raise RuntimeError("DIRECT_SFR_WRITE diagnostics are absent")
    counts_text = match.group(2)
    counts = {} if counts_text == "none" else {
        f"{int(index, 16):02X}": int(count, 10)
        for index, count in DIRECT_COUNT.findall(counts_text)
    }
    trace = match.group(3)
    return {
        "total": int(match.group(1), 10),
        "counts": counts,
        "trace": [] if trace == "none" else trace.split(";"),
        "line": match.group(0),
    }


def parse_stream_position_inventory(registers: str) -> dict[str, Any]:
    match = STREAM_POSITION_LINE.search(registers)
    if match is None:
        raise RuntimeError("NPE_STREAM_POSITION diagnostics are absent")
    pages_text = match.group(10)
    pages = {} if pages_text == "none" else {
        f"{int(page, 16):03X}": int(count, 10)
        for page, count in STREAM_PAGE_COUNT.findall(pages_text)
    }
    if len(pages) != int(match.group(9), 10):
        raise RuntimeError(
            "NPE stream page inventory count does not match diagnostics"
        )
    return {
        "calls": int(match.group(1), 10),
        "returns": int(match.group(2), 10),
        "changed": int(match.group(3), 10),
        "reverse": int(match.group(4), 10),
        "range_start": int(match.group(5), 16),
        "range_end": int(match.group(6), 16),
        "requested_bytes": int(match.group(7), 10),
        "advanced_bytes": int(match.group(8), 10),
        "pages_touched": int(match.group(9), 10),
        "page_calls": pages,
        "line": match.group(0),
        "io_trace": (
            parse_stream_io_trace(registers)
            if STREAM_IO_LINE.search(registers) else []
        ),
        "resolve": (
            parse_stream_resolve_trace(registers)
            if STREAM_RESOLVE_LINE.search(registers) else {
                "calls": 0, "returns": 0, "active": False, "trace": [],
            }
        ),
        "high_io": (
            parse_high_stream_io_trace(registers)
            if HIGH_STREAM_IO_LINE.search(registers) else {
                "calls": 0, "returns": 0, "active": False, "trace": [],
            }
        ),
        "transition_leaf": (
            parse_transition_leaf_trace(registers)
            if TRANSITION_LEAF_LINE.search(registers) else {
                "calls": 0, "returns": 0, "low": 0, "high": 0,
                "trace": [],
            }
        ),
    }


def parse_stream_io_trace(registers: str) -> list[dict[str, Any]]:
    match = STREAM_IO_LINE.search(registers)
    if match is None:
        raise RuntimeError("NPE_GAME_TABLE I/O diagnostics are absent")
    entries = []
    for item in STREAM_IO_ENTRY.finditer(match.group(1)):
        entries.append({
            "sequence": int(item.group(1), 10),
            "caller": f"{int(item.group(2), 16):02X}:"
                      f"{int(item.group(3), 16):04X}",
            "stream": int(item.group(4), 16),
            "destination": int(item.group(5), 16),
            "length": int(item.group(6), 16),
            "position_before": int(item.group(7), 16),
            "position_after": int(item.group(8), 16),
            "method": f"{int(item.group(9), 16):02X}:"
                      f"{int(item.group(10), 16):04X}",
            "result_r0": int(item.group(11), 16),
            "result_r1": int(item.group(12), 16),
            "error": int(item.group(13), 16),
            "table_writes": int(item.group(14), 10),
        })
    return entries


def parse_stream_resolve_trace(registers: str) -> dict[str, Any]:
    match = STREAM_RESOLVE_LINE.search(registers)
    if match is None:
        raise RuntimeError("NPE_STREAM_RESOLVE diagnostics are absent")
    entries = []
    for item in STREAM_RESOLVE_ENTRY.finditer(match.group(4)):
        entries.append({
            "sequence": int(item.group(1), 10),
            "caller": f"{int(item.group(2), 16):02X}:"
                      f"{int(item.group(3), 16):04X}",
            "stream": int(item.group(4), 16),
            "offset": int(item.group(5), 16),
            "whence": int(item.group(6), 16),
            "position_before": int(item.group(7), 16),
            "position_after": int(item.group(8), 16),
            "result_r0": int(item.group(9), 16),
            "result_r1": int(item.group(10), 16),
            "error": int(item.group(11), 16),
        })
    return {
        "calls": int(match.group(1), 10),
        "returns": int(match.group(2), 10),
        "active": bool(int(match.group(3), 10)),
        "trace": entries,
        "line": match.group(0),
    }


def parse_high_stream_io_trace(registers: str) -> dict[str, Any]:
    """Parse the bounded section-13-and-above stream-read ring."""
    match = HIGH_STREAM_IO_LINE.search(registers)
    if match is None:
        raise RuntimeError("NPE_HIGH_STREAM_IO diagnostics are absent")
    entries = []
    for item in HIGH_STREAM_IO_ENTRY.finditer(match.group(4)):
        entries.append({
            "sequence": int(item.group(1), 10),
            "caller": f"{int(item.group(2), 16):02X}:"
                      f"{int(item.group(3), 16):04X}",
            "destination": int(item.group(4), 16),
            "length": int(item.group(5), 16),
            "position_before": int(item.group(6), 16),
            "position_after": int(item.group(7), 16),
            "result_r0": int(item.group(8), 16),
            "result_r1": int(item.group(9), 16),
            "error": int(item.group(10), 16),
        })
    return {
        "calls": int(match.group(1), 10),
        "returns": int(match.group(2), 10),
        "active": bool(int(match.group(3), 10)),
        "trace": entries,
        "line": match.group(0),
    }


def parse_transition_leaf_trace(registers: str) -> dict[str, Any]:
    """Parse the bounded 25:0000 call/format/branch observer."""
    match = TRANSITION_LEAF_LINE.search(registers)
    if match is None:
        raise RuntimeError("NPE_TRANSITION_LEAF diagnostics are absent")
    entries = []
    for item in TRANSITION_LEAF_ENTRY.finditer(match.group(5)):
        entries.append({
            "sequence": int(item.group(1), 10),
            "caller": f"{int(item.group(2), 16):02X}:"
                      f"{int(item.group(3), 16):04X}",
            "sp": int(item.group(4), 16),
            "state": int(item.group(5), 16),
            "format": int(item.group(6), 16),
            "args": [int(item.group(index), 16) for index in range(7, 13)],
            "branch": item.group(13),
            "result": int(item.group(14), 16),
        })
    return {
        "calls": int(match.group(1), 10),
        "returns": int(match.group(2), 10),
        "low": int(match.group(3), 10),
        "high": int(match.group(4), 10),
        "trace": entries,
        "line": match.group(0),
    }


def capture(web: WebBridge, label: str) -> dict[str, Any]:
    state = web.get_json("/api/state")
    registers = str(state.get("registers", ""))
    failure = diagnostic_failure(registers)
    if failure:
        raise RuntimeError(failure)
    if not game_ready(registers):
        raise RuntimeError(f"NPE game loop is not ready at {label}")
    compact, _frame = compact_state(state)
    return {
        "label": label,
        "captured_at": time.time(),
        "pc": compact["pc"],
        "application_state": compact["application_state"],
        "game_loop": compact["game_loop"],
        "diagnostics": compact["diagnostics"],
        "frame": compact["frame"],
        "sfr": parse_sfr_inventory(registers),
        "banked_fxxx": parse_banked_inventory(registers),
        "direct_sfr": parse_direct_inventory(registers),
        "stream_position": parse_stream_position_inventory(registers),
    }


def inventory_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    left = before["sfr"]
    right = after["sfr"]
    return {
        "total": right["total"] - left["total"],
        "unknown": right["unknown"] - left["unknown"],
        "buckets": {
            name: right["buckets"][name] - left["buckets"][name]
            for name in left["buckets"]
        },
        "new_unknown_trace": right["trace"][
            max(0, len(right["trace"]) -
                max(0, right["unknown"] - left["unknown"])):
        ] if right["unknown"] > left["unknown"] else [],
    }


def banked_inventory_delta(
    before: dict[str, Any], after: dict[str, Any],
) -> dict[str, Any]:
    return inventory_delta(
        {"sfr": before["banked_fxxx"]},
        {"sfr": after["banked_fxxx"]},
    )


def direct_inventory_delta(
    before: dict[str, Any], after: dict[str, Any],
) -> dict[str, Any]:
    left = before["direct_sfr"]
    right = after["direct_sfr"]
    total_delta = right["total"] - left["total"]
    names = sorted(set(left["counts"]) | set(right["counts"]))
    return {
        "total": total_delta,
        "counts": {
            name: right["counts"].get(name, 0) - left["counts"].get(name, 0)
            for name in names
            if right["counts"].get(name, 0) != left["counts"].get(name, 0)
        },
        "new_trace": right["trace"][
            max(0, len(right["trace"]) - max(0, total_delta)):
        ] if total_delta > 0 else [],
        "trace_complete": total_delta <= len(right["trace"]),
    }


def stream_position_delta(
    before: dict[str, Any], after: dict[str, Any],
) -> dict[str, Any]:
    left = before["stream_position"]
    right = after["stream_position"]
    names = sorted(set(left["page_calls"]) | set(right["page_calls"]))
    call_delta = right["calls"] - left["calls"]
    new_io_trace = [
        entry for entry in right.get("io_trace", [])
        if left["calls"] < entry["sequence"] <= right["calls"]
    ]
    left_resolve = left.get("resolve", {"calls": 0, "trace": []})
    right_resolve = right.get("resolve", {"calls": 0, "trace": []})
    resolve_call_delta = right_resolve["calls"] - left_resolve["calls"]
    new_resolve_trace = [
        entry for entry in right_resolve.get("trace", [])
        if left_resolve["calls"] < entry["sequence"] <=
           right_resolve["calls"]
    ]
    left_leaf = left.get("transition_leaf", {"calls": 0, "trace": []})
    right_leaf = right.get("transition_leaf", {"calls": 0, "trace": []})
    leaf_call_delta = right_leaf["calls"] - left_leaf["calls"]
    new_leaf_trace = [
        entry for entry in right_leaf.get("trace", [])
        if left_leaf["calls"] < entry["sequence"] <= right_leaf["calls"]
    ]
    return {
        name: right[name] - left[name]
        for name in (
            "calls", "returns", "changed", "reverse",
            "requested_bytes", "advanced_bytes",
        )
    } | {
        "page_calls": {
            name: right["page_calls"].get(name, 0) -
                  left["page_calls"].get(name, 0)
            for name in names
            if right["page_calls"].get(name, 0) !=
               left["page_calls"].get(name, 0)
        },
        "range_start": right["range_start"],
        "range_end": right["range_end"],
        "new_io_trace": new_io_trace,
        "trace_complete": len(new_io_trace) == call_delta,
        "resolve_calls": resolve_call_delta,
        "new_resolve_trace": new_resolve_trace,
        "resolve_trace_complete":
            len(new_resolve_trace) == resolve_call_delta,
        "transition_leaf_calls": leaf_call_delta,
        "new_transition_leaf_trace": new_leaf_trace,
        "transition_leaf_trace_complete":
            len(new_leaf_trace) == leaf_call_delta,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8801")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--hold-duration", type=float, default=5.0)
    parser.add_argument("--idle-duration", type=float, default=5.0)
    parser.add_argument("--press-timeout", type=float, default=30.0)
    parser.add_argument("--release-timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=0.01)
    parser.add_argument("--settle", type=float, default=0.25)
    args = parser.parse_args()
    if min(
        args.hold_duration, args.idle_duration, args.press_timeout,
        args.release_timeout, args.poll_interval,
    ) <= 0 or args.settle < 0:
        parser.error("durations/timeouts must be positive and settle nonnegative")

    web = WebBridge(args.root, timeout=max(args.press_timeout, 10.0))
    actions = [
        PLAY_ACTIONS[0],  # down: held to exercise native repeat
        PLAY_ACTIONS[1],  # right
        PLAY_ACTIONS[2],  # up
        PLAY_ACTIONS[3],  # left
        RouteStep("PrimaryAction", 53, 0x86),
    ]
    manifest: dict[str, Any] = {
        "schema": "np560-npe-unbanked-sfr-v1",
        "started_at": time.time(),
        "root": args.root,
        "observer_only": True,
        "input_path": "Web /api/key -> QEMU 8x8 matrix -> guest scanner",
        "steps": [],
        "snapshots": [],
        "deltas": [],
        "complete": False,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        previous = capture(web, "before-input")
        manifest["snapshots"].append(previous)
        write_manifest(args.output_dir, manifest)
        for index, action in enumerate(actions):
            result = replay_step(
                web, action,
                press_timeout=args.press_timeout,
                release_timeout=args.release_timeout,
                poll_interval=args.poll_interval,
                settle=args.settle,
                hold_duration=args.hold_duration if index == 0 else 0.0,
            )
            current = capture(web, f"after-{action.label.lower()}")
            manifest["steps"].append(result)
            manifest["snapshots"].append(current)
            manifest["deltas"].append({
                "from": previous["label"],
                "to": current["label"],
                "unbanked": inventory_delta(previous, current),
                "banked_fxxx": banked_inventory_delta(previous, current),
                "direct_sfr": direct_inventory_delta(previous, current),
                "stream_position": stream_position_delta(previous, current),
            })
            previous = current
            write_manifest(args.output_dir, manifest)

        time.sleep(args.idle_duration)
        idle = capture(web, "after-idle")
        manifest["snapshots"].append(idle)
        manifest["deltas"].append({
            "from": previous["label"],
            "to": idle["label"],
            "unbanked": inventory_delta(previous, idle),
            "banked_fxxx": banked_inventory_delta(previous, idle),
            "direct_sfr": direct_inventory_delta(previous, idle),
            "stream_position": stream_position_delta(previous, idle),
        })
        manifest["complete"] = True
        manifest["finished_at"] = time.time()
        manifest["input_unknown_delta"] = (
            manifest["snapshots"][-2]["sfr"]["unknown"] -
            manifest["snapshots"][0]["sfr"]["unknown"]
        )
        manifest["idle_unknown_delta"] = (
            idle["sfr"]["unknown"] - previous["sfr"]["unknown"]
        )
        manifest["input_banked_unknown_delta"] = (
            manifest["snapshots"][-2]["banked_fxxx"]["unknown"] -
            manifest["snapshots"][0]["banked_fxxx"]["unknown"]
        )
        manifest["idle_banked_unknown_delta"] = (
            idle["banked_fxxx"]["unknown"] -
            previous["banked_fxxx"]["unknown"]
        )
        manifest["input_direct_sfr_delta"] = (
            manifest["snapshots"][-2]["direct_sfr"]["total"] -
            manifest["snapshots"][0]["direct_sfr"]["total"]
        )
        manifest["idle_direct_sfr_delta"] = (
            idle["direct_sfr"]["total"] -
            previous["direct_sfr"]["total"]
        )
        manifest["input_stream_call_delta"] = (
            manifest["snapshots"][-2]["stream_position"]["calls"] -
            manifest["snapshots"][0]["stream_position"]["calls"]
        )
        manifest["idle_stream_call_delta"] = (
            idle["stream_position"]["calls"] -
            previous["stream_position"]["calls"]
        )
        write_manifest(args.output_dir, manifest)
        print(json.dumps({
            "complete": True,
            "input_unknown_delta": manifest["input_unknown_delta"],
            "idle_unknown_delta": manifest["idle_unknown_delta"],
            "input_banked_unknown_delta":
                manifest["input_banked_unknown_delta"],
            "idle_banked_unknown_delta":
                manifest["idle_banked_unknown_delta"],
            "input_direct_sfr_delta": manifest["input_direct_sfr_delta"],
            "idle_direct_sfr_delta": manifest["idle_direct_sfr_delta"],
            "input_stream_call_delta": manifest["input_stream_call_delta"],
            "idle_stream_call_delta": manifest["idle_stream_call_delta"],
            "final_total": idle["sfr"]["total"],
            "final_unknown": idle["sfr"]["unknown"],
            "final_banked_total": idle["banked_fxxx"]["total"],
            "final_banked_unknown": idle["banked_fxxx"]["unknown"],
            "final_direct_sfr_total": idle["direct_sfr"]["total"],
        }, ensure_ascii=False))
        return 0
    except Exception as error:
        manifest["error"] = f"{type(error).__name__}: {error}"
        manifest["finished_at"] = time.time()
        write_manifest(args.output_dir, manifest)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
