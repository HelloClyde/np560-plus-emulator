#!/usr/bin/env python3
"""Monitor NP560 NAND/FTL geometry changes without mutating the emulator.

The client attaches to an existing Web/QEMU endpoint, prints only new guest
writes and value changes, and exits at the first post-initialization geometry
divergence or NAND error.  It is intended to replace multi-gigabyte execution
logs when a late storage scan turns the normal 0x0836 OOB probe into an invalid
column.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import re
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


GEOMETRY_LINE = "STORAGE_GEOMETRY"
WRITE_LINE = "STORAGE_GEOMETRY_WRITES"


@dataclass(frozen=True)
class GeometryWrite:
    pc: str
    address: int
    old: int
    new: int
    bits: int


def fetch_state(base_url: str, timeout: float) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/state"
    with urlopen(url, timeout=timeout) as response:
        state = json.load(response)
    if not isinstance(state, dict) or "error" in state:
        raise ValueError(f"invalid Web/QEMU state: {state!r}")
    return state


def state_line(registers: str, name: str) -> str:
    prefix = f"{name}="
    for line in registers.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return "none"


def parse_geometry(registers: str) -> dict[str, int]:
    line = state_line(registers, GEOMETRY_LINE)
    values = {
        name: int(value, 16)
        for name, value in re.findall(
            r"(SHIFT|MODE|BUFFER_STEP|PAGE_DATA|FTL_BLOCK|"
            r"MAP_SLOT_9B|MAP_SLOT_C9):([0-9a-fA-F]{4})",
            line,
        )
    }
    buffer_match = re.search(
        r"(?:^|\s)BUFFER:([0-9a-fA-F]{4}):([0-9a-fA-F]{4})", line
    )
    if buffer_match:
        values["BUFFER_HI"] = int(buffer_match.group(1), 16)
        values["BUFFER_LO"] = int(buffer_match.group(2), 16)
    range_match = re.search(
        r"(?:^|\s)RANGE:([0-9a-fA-F]{4})\.\.([0-9a-fA-F]{4})", line
    )
    if range_match:
        values["RANGE_FIRST"] = int(range_match.group(1), 16)
        values["RANGE_LAST"] = int(range_match.group(2), 16)
    return values


def parse_writes(registers: str) -> tuple[int, list[GeometryWrite]]:
    line = state_line(registers, WRITE_LINE)
    count_match = re.search(r"(?:^|\s)COUNT:(\d+)", line)
    count = int(count_match.group(1)) if count_match else 0
    writes = [
        GeometryWrite(pc.lower(), int(address, 16), int(old, 16),
                      int(new, 16), int(bits))
        for pc, address, old, new, bits in re.findall(
            r"([0-9a-fA-F]{2}:[0-9a-fA-F]{4})/"
            r"([0-9a-fA-F]{6})/([0-9a-fA-F]{4})>"
            r"([0-9a-fA-F]{4})/(8|16)",
            line,
        )
    ]
    return count, writes


def new_writes(previous_count: int, count: int,
               ring: list[GeometryWrite]) -> tuple[int, list[GeometryWrite]]:
    if count <= previous_count:
        return 0, []
    delta = count - previous_count
    if delta >= len(ring):
        return max(0, delta - len(ring)), ring
    return 0, ring[-delta:]


def nand_error(state: dict[str, Any]) -> int | None:
    match = re.search(r"(?:^|\s)ERROR=(\d+)", str(state.get("nand_state", "")))
    return int(match.group(1)) if match else None


def format_geometry(values: dict[str, int]) -> str:
    order = (
        "SHIFT", "MODE", "BUFFER_HI", "BUFFER_LO", "BUFFER_STEP",
        "PAGE_DATA", "FTL_BLOCK", "RANGE_FIRST", "RANGE_LAST",
        "MAP_SLOT_9B", "MAP_SLOT_C9",
    )
    return " ".join(
        f"{name}={values[name]:04x}" for name in order if name in values
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--startup-timeout", type=float, default=90.0)
    parser.add_argument("--duration", type=float, default=120.0)
    args = parser.parse_args()

    started = time.monotonic()
    connected = False
    previous_values: dict[str, int] = {}
    previous_write_count = 0
    geometry_armed = False
    while args.duration <= 0 or time.monotonic() - started < args.duration:
        try:
            state = fetch_state(args.url, args.timeout)
        except (OSError, URLError, ValueError):
            if connected or time.monotonic() - started >= args.startup_timeout:
                raise
            time.sleep(max(args.interval, 0.01))
            continue

        now = time.monotonic() - started
        if not connected:
            connected = True
            print(f"{now:8.3f}s READY {args.url}", flush=True)
        registers = str(state.get("registers", ""))
        values = parse_geometry(registers)
        if values != previous_values:
            print(f"{now:8.3f}s STATE {format_geometry(values)}", flush=True)
            previous_values = values

        count, ring = parse_writes(registers)
        lost, writes = new_writes(previous_write_count, count, ring)
        if lost:
            print(f"{now:8.3f}s WRITES lost={lost}", flush=True)
        sequence = count - len(writes) + 1
        for offset, write in enumerate(writes):
            print(
                f"{now:8.3f}s WRITE #{sequence + offset} "
                f"{write.address:06x} {write.old:04x}>{write.new:04x}/"
                f"{write.bits} by {write.pc}",
                flush=True,
            )
        previous_write_count = count

        expected = (
            values.get("BUFFER_HI") == 0x0051 and
            values.get("BUFFER_LO") == 0x1000 and
            values.get("PAGE_DATA") == 0x0800
        )
        geometry_armed = geometry_armed or expected
        error = nand_error(state)
        if geometry_armed and not expected:
            print(
                f"{now:8.3f}s INCIDENT geometry diverged after valid setup: "
                f"{format_geometry(values)}",
                flush=True,
            )
            return 2
        if error:
            print(f"{now:8.3f}s INCIDENT NAND error={error}", flush=True)
            return 2
        time.sleep(max(args.interval, 0.01))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
