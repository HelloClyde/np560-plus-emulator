#!/usr/bin/env python3
"""Capture NAND history at each new root bitmap-transfer count.

The monitor is read-only and polls the lightweight diagnostics endpoint.  It
exists to preserve the short-lived NAND trace that precedes the resident
29:AC4E resource copy, before background FTL reads overwrite the ring.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen


TRANSFER_RE = re.compile(r"^ROOT_BITMAP_TRANSFER=CALLS:(\d+).*$", re.M)


def diagnostic_line(registers: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}=.*$", registers, re.M)
    return match.group(0) if match else f"{name}=unavailable"


def fetch(url: str, timeout: float) -> dict[str, Any]:
    with urlopen(
        f"{url.rstrip('/')}/api/diagnostics", timeout=timeout
    ) as response:
        state = json.load(response)
    if not isinstance(state, dict) or "error" in state:
        raise ValueError(f"invalid diagnostics response: {state!r}")
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--request-timeout", type=float, default=2.0)
    parser.add_argument("--interval", type=float, default=0.01)
    parser.add_argument("--settle", type=float, default=1.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0 or args.request_timeout <= 0:
        parser.error("timeouts must be positive")
    if args.interval < 0 or args.settle < 0:
        parser.error("interval and settle must be non-negative")

    deadline = time.monotonic() + args.timeout
    last_calls = 0
    first_event_at: float | None = None
    samples: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        state = fetch(args.url, args.request_timeout)
        registers = str(state.get("registers", ""))
        match = TRANSFER_RE.search(registers)
        calls = int(match.group(1)) if match else 0
        if calls > last_calls:
            sample = {
                "elapsed_seconds": args.timeout - (deadline - time.monotonic()),
                "calls": calls,
                "pc": registers.splitlines()[0] if registers else "PC=unavailable",
                "nand_trace": diagnostic_line(registers, "NAND_TRACE"),
                "transfer": diagnostic_line(registers, "ROOT_BITMAP_TRANSFER"),
                "header_copy": diagnostic_line(
                    registers, "ROOT_BITMAP_HEADER_COPY"
                ),
                "resource": diagnostic_line(registers, "ROOT_BITMAP_RESOURCE"),
                "blit": diagnostic_line(registers, "ROOT_BITMAP_BLIT"),
            }
            samples.append(sample)
            print(json.dumps(sample, ensure_ascii=False), flush=True)
            last_calls = calls
            if first_event_at is None:
                first_event_at = time.monotonic()
        if first_event_at is not None and time.monotonic() >= first_event_at + args.settle:
            break
        if args.interval:
            time.sleep(args.interval)

    result = {
        "schema": "np560-bitmap-nand-monitor-v1",
        "url": args.url,
        "transfer_calls": last_calls,
        "samples": samples,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if not samples:
        raise TimeoutError("root bitmap transfer was not observed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
