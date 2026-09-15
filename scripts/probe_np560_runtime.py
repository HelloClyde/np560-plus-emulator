#!/usr/bin/env python3
"""Take low-overhead NP560 Web/QEMU runtime snapshots.

Unlike the interactive frontend, this probe performs one state request per
interval.  It keeps the fields needed for current ROM reconstruction visible
without continuously asking QEMU for the large diagnostic register block.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
import re
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


IMPORTANT_LINES = (
    "APPLICATION_STATE",
    "APPLICATION_STATE_WRITE",
    "APPLICATION_TRACE",
    "APPLICATION_INIT",
    "PROVISION",
    "FILE_OPEN",
    "FILE_WRITE",
    "FILE_COMMIT",
    "STORAGE_DRIVER",
    "FILE_ROOT_POOL",
    "FILE_ROOT_RELEASE",
    "FILE_SIZE_RECORD",
    "FILE_RECORD_RESOLVE",
    "RESOURCE_OPEN",
    "RESOURCE_RECOVERY_WORD",
    "INDIRECT_CALLBACK",
    "MENU_OVERLAY_COPY",
    "NATIVE_LCD_FLUSH",
    "NATIVE_FB",
    "NATIVE_REFRESH",
    "TEXT_TRACE",
    "USERINFO_FLOW",
    "IRQ_SAVE_FP_OVERWRITE",
    "IRQ64",
    "TIMER64",
    "EVENT_STATE",
    "INVALID_CONTROL",
    "UNSUPPORTED",
    "NAND",
)

FOREGROUND_STAGES = (
    "FGLOOP", "FGRAWRET", "FGMAPRET", "FGDECODE", "FGCHANGE", "FGEXIT",
    "LAUNCH", "MANAGER", "MENU",
)


def fetch_state(url: str, timeout: float) -> dict[str, Any]:
    root = url.rstrip("/")
    try:
        with urlopen(f"{root}/api/diagnostics", timeout=timeout) as response:
            state = json.load(response)
    except HTTPError as exc:
        if exc.code != 404:
            raise
        # An existing Web process may predate the lightweight endpoint.
        with urlopen(f"{root}/api/state", timeout=timeout) as response:
            state = json.load(response)
    if not isinstance(state, dict) or "error" in state:
        raise ValueError(f"invalid Web state: {state!r}")
    return state


def state_lines(registers: str) -> dict[str, str]:
    result: dict[str, str] = {}
    pc = re.search(r"(?:^|\n)(PC=[^\n]+)", registers)
    if pc:
        result["PC"] = pc.group(1)[3:].strip()
    for name in IMPORTANT_LINES:
        match = re.search(
            rf"(?:^|\n){re.escape(name)}=([^\n]*)", registers,
        )
        result[name] = match.group(1).strip() if match else "missing"
    return result


def integer(text: str, field: str) -> int | None:
    match = re.search(rf"(?:^|\s){re.escape(field)}[:=](\d+)", text)
    return int(match.group(1)) if match else None


def application_calls(text: str, stage: str) -> int | None:
    match = re.search(
        rf"(?:^|,){re.escape(stage)}:(\d+)@", text,
    )
    return int(match.group(1)) if match else None


def application_stage_r0(text: str, stage: str) -> int | None:
    """Return R0 captured at the most recent named foreground stage."""
    match = re.search(
        rf"(?:^|,){re.escape(stage)}:\d+@[^/]+/sp[^/]+/r([0-9a-fA-F]{{4}})",
        text,
    )
    return int(match.group(1), 16) if match else None


def state_write_transition(
    text: str,
) -> tuple[str | None, int | None, int | None]:
    """Extract the last application-state write site and old/new values."""
    match = re.search(
        r"(?:^|\s)PC:([0-9a-fA-F]{2}:[0-9a-fA-F]{4})"
        r"(?:\s+[^\s]+)*\s+VALUE:([0-9a-fA-F]{4})>"
        r"([0-9a-fA-F]{4})/",
        text,
    )
    if not match:
        return None, None, None
    return match.group(1).lower(), int(match.group(2), 16), int(match.group(3), 16)


def hex_integer(text: str, field: str) -> int | None:
    match = re.search(
        rf"(?:^|\s){re.escape(field)}[:=]([0-9a-fA-F]+)", text,
    )
    return int(match.group(1), 16) if match else None


def text_y_values(text_trace: str) -> tuple[int, ...]:
    return tuple(sorted({
        int(value) for value in re.findall(
            r"(?:^|,)[0-9a-fA-F]{2}:[0-9a-fA-F]{4}@[0-9]+,([0-9]+)",
            text_trace,
        )
    }))


def userinfo_state_copy(text: str) -> tuple[int | None, int | None, str]:
    """Extract the relocated state-copy call balance and code prefix."""
    match = re.search(
        r"(?:^|\s)STATE:(\d+)/(\d+)/[^\s]*/CODE:([0-9a-fA-F.]+)",
        text,
    )
    if not match:
        return None, None, "missing"
    return int(match.group(1)), int(match.group(2)), match.group(3).lower()


def is_incident(lines: dict[str, str]) -> list[str]:
    incidents: list[str] = []
    fp = lines["IRQ_SAVE_FP_OVERWRITE"]
    if fp != "none" and not fp.startswith("none "):
        incidents.append(f"0x04D6 frame-pointer overwrite: {fp}")
    invalid = lines["INVALID_CONTROL"]
    if invalid != "none" and not invalid.startswith("none "):
        incidents.append(f"invalid control transfer: {invalid}")
    unsupported = lines["UNSUPPORTED"]
    if unsupported != "none" and not unsupported.startswith("none "):
        incidents.append(f"unsupported instruction: {unsupported}")
    state_calls, state_returns, state_code = userinfo_state_copy(
        lines["USERINFO_FLOW"]
    )
    if state_calls and state_code != "missing" and set(state_code) <= {"f", "."}:
        incidents.append(
            "USERINFO state-copy overlay is blank at runtime "
            f"({state_calls}/{state_returns or 0} calls/returns)"
        )
    application = lines["APPLICATION_STATE"]
    file_size = lines["FILE_SIZE_RECORD"]
    menu = lines["MENU_OVERLAY_COPY"]
    foreground_calls = application_calls(
        lines["APPLICATION_TRACE"], "FGLOOP"
    )
    if (
        "RESOURCE_FLAG:0001" in application
        and "LENGTH:0000:0000" in file_size
        and "READS:0" in menu
        and not foreground_calls
    ):
        incidents.append(
            "main resource resolved to zero length before the menu entry"
        )
    state_write = lines["APPLICATION_STATE_WRITE"].lower()
    if "pc:2e:46c0" in state_write and "addr:512aaa" in state_write:
        incidents.append(
            "application state overwritten by the sector-copy worker"
        )
    irq_bad = integer(lines["IRQ64"], "BAD")
    if irq_bad:
        incidents.append(f"64-Hz interrupt returned through a bad frame ({irq_bad})")
    refresh_mismatches = integer(lines["NATIVE_REFRESH"], "MISMATCHES")
    if refresh_mismatches:
        incidents.append(
            "LCD refresh front/back mismatch "
            f"({refresh_mismatches})"
        )
    modal_polls = application_calls(lines["APPLICATION_TRACE"], "MODALPOLL")
    resource_calls = application_calls(lines["APPLICATION_TRACE"], "RESOURCE")
    modal_entries = application_calls(lines["APPLICATION_TRACE"], "MODALEVT")
    modal_cleanups = application_calls(lines["APPLICATION_TRACE"], "CLEANUP")
    if (
        modal_polls is not None
        and modal_polls >= 1000
        and modal_entries is not None
        and modal_entries > (modal_cleanups or 0)
        and not resource_calls
    ):
        incidents.append(
            "pre-resource modal loop is blocking the main resource entry "
            f"({modal_polls} polls)"
        )
    return incidents


def compact_observation(state: dict[str, Any]) -> dict[str, Any]:
    lines = state_lines(str(state.get("registers", "")))
    encoded_frame = str(state.get("frame", ""))
    frame = (
        base64.b64decode(encoded_frame, validate=True)
        if encoded_frame else None
    )
    callbacks = integer(lines["INDIRECT_CALLBACK"], "CALLS")
    file_opens = integer(lines["FILE_OPEN"], "CALLS")
    flushes = integer(lines["NATIVE_LCD_FLUSH"], "CALLS")
    nonzero = integer(lines["NATIVE_FB"], "NONZERO")
    provision_stage = integer(lines["PROVISION"], "STAGE")
    file_writes = integer(lines["FILE_WRITE"], "CALLS")
    file_commits = integer(lines["FILE_COMMIT"], "CALLS")
    storage_driver_calls = integer(lines["STORAGE_DRIVER"], "CALLS")
    file_root_allocs = integer(lines["FILE_ROOT_POOL"], "CALLS")
    file_root_releases = integer(lines["FILE_ROOT_RELEASE"], "CALLS")
    nand_programs = integer(lines["NAND"], "PROGRAMS")
    nand_erases = integer(lines["NAND"], "ERASES")
    modal_polls = application_calls(lines["APPLICATION_TRACE"], "MODALPOLL")
    resource_calls = application_calls(lines["APPLICATION_TRACE"], "RESOURCE")
    userinfo_state_calls, userinfo_state_returns, userinfo_state_code = (
        userinfo_state_copy(lines["USERINFO_FLOW"])
    )
    foreground = {
        stage.lower(): application_calls(lines["APPLICATION_TRACE"], stage)
        for stage in FOREGROUND_STAGES
    }
    state_write_pc, state_old, state_new = state_write_transition(
        lines["APPLICATION_STATE_WRITE"]
    )
    return {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "running": bool(state.get("running")),
        "pc": lines.get("PC", "missing"),
        "provision_stage": provision_stage,
        "callbacks": callbacks,
        "file_opens": file_opens,
        "file_writes": file_writes,
        "file_commits": file_commits,
        "storage_driver_calls": storage_driver_calls,
        "file_root_allocs": file_root_allocs,
        "file_root_releases": file_root_releases,
        "nand_programs": nand_programs,
        "nand_erases": nand_erases,
        "modal_polls": modal_polls,
        "resource_calls": resource_calls,
        "lcd_flushes": flushes,
        "lcd_nonzero": nonzero,
        "text_y": text_y_values(lines["TEXT_TRACE"]),
        "frame_sha256": (
            hashlib.sha256(frame).hexdigest()[:12]
            if frame is not None else None
        ),
        "state_write_count": integer(
            lines["APPLICATION_STATE_WRITE"], "COUNT"
        ),
        "state_write_pc": state_write_pc,
        "state_old": state_old,
        "state_new": state_new,
        "state_write": lines["APPLICATION_STATE_WRITE"],
        "foreground": foreground,
        "foreground_event": application_stage_r0(
            lines["APPLICATION_TRACE"], "FGDECODE"
        ),
        "event_tick": hex_integer(lines["EVENT_STATE"], "TICK"),
        "irq_ticks": integer(lines["IRQ64"], "TICKS"),
        "irq_entries": integer(lines["IRQ64"], "ENTRIES"),
        "irq_returns": integer(lines["IRQ64"], "RETURNS"),
        "irq_bad": integer(lines["IRQ64"], "BAD"),
        "refresh_calls": integer(lines["NATIVE_REFRESH"], "CALLS"),
        "refresh_mismatches": integer(
            lines["NATIVE_REFRESH"], "MISMATCHES"
        ),
        "menu_reads": integer(lines["MENU_OVERLAY_COPY"], "READS"),
        "menu_entries": integer(lines["MENU_OVERLAY_COPY"], "ENTRY"),
        "userinfo_events": integer(lines["USERINFO_FLOW"], "EVENTS"),
        "userinfo_state_calls": userinfo_state_calls,
        "userinfo_state_returns": userinfo_state_returns,
        "userinfo_state_code": userinfo_state_code,
        "application": lines["APPLICATION_STATE"],
        "file_size_record": lines["FILE_SIZE_RECORD"],
        "file_record_resolve": lines["FILE_RECORD_RESOLVE"],
        "resource_open": lines["RESOURCE_OPEN"],
        "resource_recovery_word": lines["RESOURCE_RECOVERY_WORD"],
        "menu_overlay": lines["MENU_OVERLAY_COPY"],
        "incidents": is_incident(lines),
    }


def incident_changes(
    previous: set[str], current: list[str],
) -> tuple[list[str], list[str]]:
    """Return newly observed and newly resolved incidents in stable order."""
    def identity(incident: str) -> str:
        # Runtime counters grow while the CPU remains at one fault.  Treat a
        # new COUNT value as the same incident so long monitors report the
        # transition once instead of printing a false resolve/new pair on
        # every sample.
        return re.sub(r"\bCOUNT[=:]\d+", "COUNT:*", incident)

    previous_by_identity = {identity(item): item for item in previous}
    current_by_identity = {identity(item): item for item in current}
    added = [
        incident for incident in current
        if identity(incident) not in previous_by_identity
    ]
    resolved = sorted(
        incident for key, incident in previous_by_identity.items()
        if key not in current_by_identity
    )
    return added, resolved


def observation_signature(observation: dict[str, Any]) -> tuple[object, ...]:
    """Select state changes worth printing in long-running monitor mode."""
    return tuple(
        observation.get(key) for key in (
            "running", "pc", "provision_stage", "callbacks", "file_opens",
            "file_writes", "file_commits", "storage_driver_calls",
            "file_root_allocs", "file_root_releases", "nand_programs",
            "nand_erases", "modal_polls", "resource_calls", "lcd_flushes",
            "lcd_nonzero", "text_y", "frame_sha256", "application",
            "state_write_count", "state_write_pc", "state_old", "state_new",
            "foreground", "foreground_event", "event_tick", "irq_ticks",
            "irq_entries", "irq_returns", "irq_bad", "refresh_calls",
            "refresh_mismatches", "menu_reads", "menu_entries",
            "userinfo_events", "userinfo_state_calls",
            "userinfo_state_returns", "userinfo_state_code",
            "file_size_record", "file_record_resolve", "resource_open",
            "resource_recovery_word", "menu_overlay", "incidents",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--changes-only", action="store_true",
        help="suppress unchanged snapshots during long-running monitoring",
    )
    args = parser.parse_args()
    if args.interval <= 0 or args.count <= 0 or args.timeout <= 0:
        parser.error("interval, count and timeout must be positive")

    incident_seen = False
    previous: dict[str, Any] | None = None
    previous_incidents: set[str] = set()
    previous_signature: tuple[object, ...] | None = None
    for sample in range(args.count):
        try:
            observation = compact_observation(fetch_state(args.url, args.timeout))
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            print(f"probe failed: {exc}", file=sys.stderr)
            return 1
        added_incidents, resolved_incidents = incident_changes(
            previous_incidents, observation["incidents"]
        )
        signature = observation_signature(observation)
        should_print = not args.changes_only or signature != previous_signature
        if args.json and should_print:
            observation["new_incidents"] = added_incidents
            observation["resolved_incidents"] = resolved_incidents
            print(json.dumps(observation, ensure_ascii=False))
        elif not args.json and should_print:
            deltas = ""
            if previous is not None:
                delta_parts = []
                for key in (
                    "callbacks", "file_opens", "file_writes",
                    "file_commits", "storage_driver_calls", "nand_programs",
                    "file_root_allocs", "file_root_releases", "lcd_flushes",
                ):
                    current = observation[key]
                    old = previous[key]
                    if current is not None and old is not None:
                        delta_parts.append(f"d-{key}={current - old:+d}")
                deltas = " " + " ".join(delta_parts)
            print(
                f"[{observation['time']}] pc={observation['pc']} "
                f"provision={observation['provision_stage']} "
                f"callbacks={observation['callbacks']} "
                f"file-opens={observation['file_opens']} "
                f"writes={observation['file_writes']} "
                f"commits={observation['file_commits']} "
                f"drivers={observation['storage_driver_calls']} "
                f"roots-a/r={observation['file_root_allocs']}/"
                f"{observation['file_root_releases']} "
                f"nand-p/e={observation['nand_programs']}/"
                f"{observation['nand_erases']} "
                f"modal/resource={observation['modal_polls']}/"
                f"{observation['resource_calls']} "
                f"lcd={observation['lcd_nonzero']}/"
                f"{observation['lcd_flushes']} text-y={observation['text_y']} "
                f"userinfo={observation['userinfo_events']}:"
                f"{observation['userinfo_state_calls']}/"
                f"{observation['userinfo_state_returns']} "
                f"state-code={observation['userinfo_state_code'][:24]} "
                f"frame={observation['frame_sha256']}{deltas}",
                flush=True,
            )
            print(f"  app: {observation['application']}")
            foreground = observation["foreground"]
            if observation["state_old"] is None:
                state_transition = "missing"
            else:
                state_transition = (
                    f"{observation['state_old']:04x}>"
                    f"{observation['state_new']:04x}@"
                    f"{observation['state_write_pc']}"
                )
            foreground_event = observation["foreground_event"]
            foreground_event_text = (
                f"{foreground_event:04x}"
                if foreground_event is not None else "missing"
            )
            print(
                "  flow: "
                f"state-writes={observation['state_write_count']} "
                f"last={state_transition} event={foreground_event_text} "
                f"fg={foreground['fgloop']}/{foreground['fgrawret']}/"
                f"{foreground['fgmapret']}/{foreground['fgdecode']}/"
                f"{foreground['fgchange']}/{foreground['fgexit']} "
                f"menu={observation['menu_reads']}/"
                f"{observation['menu_entries']} "
                f"event-tick={observation['event_tick']} "
                f"irq={observation['irq_entries']}/"
                f"{observation['irq_returns']}/bad{observation['irq_bad']} "
                f"refresh={observation['refresh_calls']}/"
                f"bad{observation['refresh_mismatches']}",
            )
            for incident in added_incidents:
                print(f"  ALERT NEW: {incident}", file=sys.stderr)
            for incident in resolved_incidents:
                print(f"  ALERT RESOLVED: {incident}", file=sys.stderr)
        incident_seen |= bool(observation["incidents"])
        previous = observation
        previous_incidents = set(observation["incidents"])
        previous_signature = signature
        if sample + 1 < args.count:
            time.sleep(args.interval)
    return 2 if incident_seen else 0


if __name__ == "__main__":
    raise SystemExit(main())
