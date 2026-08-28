#!/usr/bin/env python3
"""Compactly monitor the NP560 hardware-init far return frame via Web/QEMU."""

from __future__ import annotations

import argparse
import json
import re
import time
from urllib.error import URLError
from urllib.request import urlopen


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


def counter(line: str, name: str) -> int:
    match = re.search(rf"\b{re.escape(name)}:(\d+)\b", line)
    return int(match.group(1)) if match else 0


def should_stop(mode: str, watch: str, invalid: str, unsupported: str) -> bool:
    incident = invalid != "INVALID_CONTROL=none" or not unsupported.startswith(
        "UNSUPPORTED=none"
    )
    if mode == "incident":
        return incident
    if mode == "overwrite":
        return incident or (
            counter(watch, "ENTRIES") >= 2 and " FIRST:none " not in watch
        )
    if mode == "second-exit":
        return counter(watch, "EXITS") >= 2
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--request-timeout", type=float, default=5.0)
    parser.add_argument(
        "--stop-at",
        choices=("overwrite", "second-exit", "incident", "never"),
        default="overwrite",
    )
    args = parser.parse_args()
    if args.interval <= 0 or args.timeout <= 0 or args.request_timeout <= 0:
        parser.error("interval and timeouts must be positive")

    started = time.monotonic()
    previous: tuple[str, str, str] | None = None
    while time.monotonic() - started < args.timeout:
        try:
            registers = fetch_registers(args.url, args.request_timeout)
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            time.sleep(args.interval)
            continue
        pc = field(registers, "PC=")
        watch = field(registers, "HARDWARE_INIT_RETURN=")
        invalid = field(registers, "INVALID_CONTROL=")
        unsupported = field(registers, "UNSUPPORTED=")
        current = (
            watch,
            invalid,
            re.sub(r"\bCOUNT=\d+\b", "COUNT=#", unsupported),
        )
        if current != previous:
            elapsed = time.monotonic() - started
            print(f"{elapsed:8.3f}s {pc}", flush=True)
            print(f"{elapsed:8.3f}s {watch}", flush=True)
            if invalid != "INVALID_CONTROL=none":
                print(f"{elapsed:8.3f}s {invalid}", flush=True)
            if not unsupported.startswith("UNSUPPORTED=none"):
                print(f"{elapsed:8.3f}s {unsupported}", flush=True)
            previous = current
        if should_stop(args.stop_at, watch, invalid, unsupported):
            return 0
        time.sleep(args.interval)
    raise TimeoutError(f"no {args.stop_at} condition within {args.timeout:g}s")


if __name__ == "__main__":
    raise SystemExit(main())
