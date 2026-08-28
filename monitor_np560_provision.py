#!/usr/bin/env python3
"""Monitor NP560 guest-native provisioning and its startup frame guard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import time
from urllib.error import URLError
from urllib.request import urlopen


PREFIXES = (
    "PC=",
    "PROVISION=",
    "FILE_OPEN=",
    "FILE_OPEN_NESTED=",
    "FILE_WRAPPER_TRACE=",
    "FILE_WRAPPER_FRAME=",
    "USERINFO_PATH_TRACE=",
    "FILE_OPEN_ERROR_TRACE=",
    "FILE_PATH_RESOLVE=",
    "FILE_PATH_TRACE=",
    "FILE_COMPONENT_FRAME=",
    "FILE_ROOT_POOL=",
    "FILE_WRITE=",
    "FILE_COMMIT=",
    "CAPACITY_SCAN=",
    "REGISTRY_INIT=",
    "FILE_ENTRY_BUILD=",
    "FILE_RECORD_RESOLVE=",
    "FILE_RECORD_CANDIDATES=",
    "ROOT_METADATA=",
    "ROOT_OBJECT_INIT=",
    "ROOT_OBJECT_FAIL=",
    "APPLICATION_INIT_FRAME=",
    "INVALID_CONTROL=",
    "UNSUPPORTED=",
)


PROGRESS_FIELDS = (
    "provision",
    "file_open",
    "file_open_nested",
    "file_wrapper_trace",
    "file_wrapper_frame",
    "userinfo_path_trace",
    "file_open_error_trace",
    "file_path_resolve",
    "file_path_trace",
    "file_component_frame",
    "file_root_pool",
    "file_write",
    "file_commit",
    "capacity_scan",
    "registry_init",
    "file_entry_build",
    "file_record_resolve",
    "file_record_candidates",
    "root_metadata",
    "root_object_init",
    "root_object_fail",
    "application_init_frame",
    "invalid_control",
    "unsupported",
)


def fetch_registers(url: str, timeout: float) -> str:
    with urlopen(f"{url.rstrip('/')}/api/state", timeout=timeout) as response:
        state = json.load(response)
    if not isinstance(state, dict) or "error" in state:
        raise ValueError(f"invalid Web/QEMU state: {state!r}")
    return str(state.get("registers", ""))


def field(registers: str, prefix: str) -> str:
    for line in registers.splitlines():
        if line.startswith(prefix):
            return line
    return f"{prefix}missing"


def decimal_field(line: str, name: str) -> int:
    match = re.search(rf"\b{re.escape(name)}:(\d+)\b", line)
    return int(match.group(1)) if match else 0


def result_words(line: str) -> tuple[int, int] | None:
    match = re.search(r"\bRESULT:([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\b", line)
    if not match:
        return None
    return int(match.group(1), 16), int(match.group(2), 16)


def snapshot(registers: str) -> dict[str, str]:
    return {prefix[:-1].lower(): field(registers, prefix) for prefix in PREFIXES}


def outcome(current: dict[str, str], expected_write_calls: int) -> str:
    invalid = current["invalid_control"]
    unsupported = current["unsupported"]
    provision = current["provision"]
    file_write = current["file_write"]
    file_commit = current["file_commit"]
    frame = current["application_init_frame"]

    if invalid != "INVALID_CONTROL=none":
        return "invalid-control"
    if not unsupported.startswith("UNSUPPORTED=none"):
        return "unsupported-instruction"
    # Stage 7 is entered only after all writes, close/commit, and the final
    # read-only stat call.  The wrapper then invokes the original 2B:2F44
    # initializer, which is precisely the routine that can wait indefinitely;
    # requiring the wrapper's later RETS (stage 8) would hide a valid commit.
    if decimal_field(provision, "STAGE") >= 7:
        if decimal_field(file_write, "CALLS") < expected_write_calls:
            return "incomplete-write-count"
        if result_words(file_write) != (0, 0x100):
            return "write-failed"
        if (decimal_field(file_commit, "CALLS") < 1 or
                decimal_field(file_commit, "RETURNS") < 1):
            return "close-incomplete"
        commit_result = result_words(file_commit)
        if commit_result is None or commit_result[0] != 0:
            return "commit-failed"
        return "complete"
    if decimal_field(frame, "WRITES") > 0:
        return "frame-overwrite"
    if decimal_field(provision, "STAGE") > 0:
        return "provisioning"
    return "startup"


def should_stop(mode: str, result: str) -> bool:
    incident = result in {
        "invalid-control",
        "unsupported-instruction",
        "frame-overwrite",
        "incomplete-write-count",
        "write-failed",
        "close-incomplete",
        "commit-failed",
    }
    if mode == "terminal":
        return incident or result == "complete"
    if mode == "incident":
        return incident
    if mode == "provisioning":
        return result == "provisioning" or incident or result == "complete"
    if mode == "complete":
        return result == "complete" or incident
    return False


def write_json(path: Path | None, elapsed: float, result: str,
               current: dict[str, str]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"elapsed_seconds": elapsed, "outcome": result, **current},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--request-timeout", type=float, default=5.0)
    parser.add_argument(
        "--expected-write-calls",
        type=int,
        default=256,
        help="guest writer call count required for a complete result",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="print only provisioning, write, close, and terminal diagnostics",
    )
    parser.add_argument(
        "--stop-at",
        choices=("terminal", "incident", "provisioning", "complete", "never"),
        default="terminal",
    )
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    if (args.interval <= 0 or args.timeout <= 0 or args.request_timeout <= 0 or
            args.expected_write_calls <= 0):
        parser.error("interval, timeouts, and expected write calls must be positive")

    started = time.monotonic()
    previous: dict[str, str] | None = None
    previous_signature: tuple[str, ...] | None = None
    last: dict[str, str] | None = None
    last_result = "unavailable"
    while time.monotonic() - started < args.timeout:
        try:
            registers = fetch_registers(args.url, args.request_timeout)
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            time.sleep(args.interval)
            continue

        current = snapshot(registers)
        result = outcome(current, args.expected_write_calls)
        last = current
        last_result = result
        signature = tuple(current[name] for name in PROGRESS_FIELDS)
        if signature != previous_signature:
            elapsed = time.monotonic() - started
            print(f"{elapsed:8.3f}s OUTCOME={result}", flush=True)
            print(f"{elapsed:8.3f}s {current['pc']}", flush=True)
            display_fields = (
                ("provision", "file_write", "file_commit",
                 "invalid_control", "unsupported")
                if args.compact else PROGRESS_FIELDS
            )
            for name in display_fields:
                if previous is None or current[name] != previous[name]:
                    print(f"{elapsed:8.3f}s {current[name]}", flush=True)
            previous = current
            previous_signature = signature
        if should_stop(args.stop_at, result):
            elapsed = time.monotonic() - started
            write_json(args.json_output, elapsed, result, current)
            return 0 if result == "complete" else 2
        time.sleep(args.interval)

    elapsed = time.monotonic() - started
    if last is not None:
        write_json(args.json_output, elapsed, last_result, last)
    raise TimeoutError(f"no {args.stop_at} condition within {args.timeout:g}s")


if __name__ == "__main__":
    raise SystemExit(main())
