#!/usr/bin/env python3
"""Monitor native NPE map-draw transactions through the read-only Web API."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request


DRAW_RE = re.compile(r"\bCALL:(\d+)\b")


def fetch_registers(root: str, timeout: float) -> str:
    with urllib.request.urlopen(
        f"{root.rstrip('/')}/api/state", timeout=timeout
    ) as response:
        state = json.load(response)
    return str(state.get("registers", ""))


def select_line(registers: str, prefix: str) -> str:
    return next(
        (line for line in registers.splitlines() if line.startswith(prefix)),
        "",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Poll observer-only NPE draw counters and print every distinct "
            "29:BBF2 transaction. No key or guest-memory API is used."
        )
    )
    parser.add_argument("--root", default="http://127.0.0.1:8778")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--request-timeout", type=float, default=10.0)
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument(
        "--changes",
        type=int,
        default=0,
        help="stop after this many call-number changes; zero waits to timeout",
    )
    parser.add_argument(
        "--include-trace",
        action="store_true",
        help="include the bounded control-flow ring for each observed draw",
    )
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    last_call: int | None = None
    changes = 0

    while time.monotonic() < deadline:
        try:
            registers = fetch_registers(args.root, args.request_timeout)
        except (OSError, ValueError) as exc:
            print(f"{time.strftime('%H:%M:%S')} API_ERROR={exc}", flush=True)
            time.sleep(args.interval)
            continue

        draw_line = select_line(registers, "NPE_GAME_DRAW_TRACE=")
        match = DRAW_RE.search(draw_line)
        if match:
            call = int(match.group(1))
            if call != last_call:
                loop_line = select_line(registers, "NPE_GAME_LOOP=")
                pc_line = select_line(registers, "PC=")
                summary = (
                    draw_line
                    if args.include_trace
                    else draw_line.split(" TRACE:", 1)[0]
                )
                print(
                    f"{time.strftime('%H:%M:%S')} {pc_line} "
                    f"{loop_line} {summary}",
                    flush=True,
                )
                if last_call is not None:
                    changes += 1
                    if args.changes and changes >= args.changes:
                        return 0
                last_call = call
        time.sleep(args.interval)

    print("TIMEOUT", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
