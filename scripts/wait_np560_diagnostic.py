#!/usr/bin/env python3
"""Wait for a numeric field in the NP560 Web diagnostics.

This is an observer-only synchronization helper for repeatable firmware routes.
It polls ``/api/diagnostics`` and never writes guest RAM or injects input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request


FAULT_PATTERNS = (
    re.compile(r"(?m)^ROM_MISSING=(?!none\b)(.+)$"),
    re.compile(r"(?m)^INVALID_CONTROL=(?!none\b)(.+)$"),
    re.compile(r"(?m)^UNSUPPORTED=(?!none\b)(.+)$"),
)


def fetch_registers(root: str, timeout: float) -> str:
    request = urllib.request.Request(
        root.rstrip("/") + "/api/diagnostics",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    registers = payload.get("registers")
    if not isinstance(registers, str):
        raise RuntimeError("diagnostics response has no string 'registers' field")
    return registers


def first_fault(registers: str) -> str | None:
    for pattern in FAULT_PATTERNS:
        match = pattern.search(registers)
        if match:
            return match.group(0)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8778")
    parser.add_argument(
        "--pattern",
        required=True,
        help="regular expression whose first capture group is the numeric field",
    )
    comparison = parser.add_mutually_exclusive_group(required=True)
    comparison.add_argument("--at-least", type=lambda value: int(value, 0))
    comparison.add_argument("--equals", type=lambda value: int(value, 0))
    parser.add_argument(
        "--stable-polls",
        type=int,
        default=1,
        help="require the comparison to pass for this many consecutive polls",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--request-timeout", type=float, default=3.0)
    parser.add_argument(
        "--allow-fault",
        action="store_true",
        help="do not stop early when a structured CPU/ROM fault appears",
    )
    args = parser.parse_args()

    try:
        pattern = re.compile(args.pattern, re.MULTILINE)
    except re.error as exc:
        parser.error(f"invalid --pattern: {exc}")
    if pattern.groups < 1:
        parser.error("--pattern must contain at least one capture group")
    if args.stable_polls < 1:
        parser.error("--stable-polls must be at least one")

    deadline = time.monotonic() + args.timeout
    last_value: int | None = None
    last_line = ""
    last_error = ""
    stable_polls = 0
    while time.monotonic() < deadline:
        try:
            registers = fetch_registers(args.root, args.request_timeout)
            fault = first_fault(registers)
            if fault and not args.allow_fault:
                print(f"FAULT {fault}", file=sys.stderr)
                return 2
            match = pattern.search(registers)
            if match:
                token = match.group(1)
                try:
                    last_value = int(token, 0)
                except ValueError:
                    last_value = int(token, 16 if re.search(r"[a-fA-F]", token) else 10)
                line_start = registers.rfind("\n", 0, match.start()) + 1
                line_end = registers.find("\n", match.end())
                if line_end < 0:
                    line_end = len(registers)
                last_line = registers[line_start:line_end]
                passed = (
                    last_value >= args.at_least
                    if args.at_least is not None
                    else last_value == args.equals
                )
                stable_polls = stable_polls + 1 if passed else 0
                if stable_polls >= args.stable_polls:
                    print(
                        f"READY value={last_value} stable={stable_polls} "
                        f"{last_line}"
                    )
                    return 0
            else:
                stable_polls = 0
            last_error = ""
        except (OSError, RuntimeError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(args.poll_interval)

    detail = last_line or last_error or "pattern was not observed"
    print(f"TIMEOUT last={last_value!r} {detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
