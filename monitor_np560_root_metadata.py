#!/usr/bin/env python3
"""Monitor NP560 root-directory metadata writes through the Web endpoint.

The QEMU probe is observation-only.  This client prints only new writes to the
51:2878 root object, making the producer or later clear of the +0x10/+0x12
record bounds visible without an instruction log.
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


TRACE_LINE = "ROOT_METADATA"


@dataclass(frozen=True)
class RootWrite:
    pc: str
    address: int
    old: int
    new: int
    bits: int
    sp: int
    fp: int


ENTRY_RE = re.compile(
    r"(?P<pc>[0-9a-fA-F]{2}:[0-9a-fA-F]{4})/"
    r"(?P<address>[0-9a-fA-F]{6})/"
    r"(?P<old>[0-9a-fA-F]{4})>(?P<new>[0-9a-fA-F]{4})/"
    r"(?P<bits>8|16)/sp(?P<sp>[0-9a-fA-F]{4})/"
    r"fp(?P<fp>[0-9a-fA-F]{4})"
)


def fetch_state(base_url: str, timeout: float) -> dict[str, Any]:
    with urlopen(
        f"{base_url.rstrip('/')}/api/state", timeout=timeout
    ) as response:
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


def parse_root_writes(
    registers: str,
) -> tuple[str, int, list[RootWrite]]:
    line = state_line(registers, TRACE_LINE)
    header = re.fullmatch(
        r"PTR:([0-9a-fA-F]{4}:[0-9a-fA-F]{4}) "
        r"WRITES:(\d+) TRACE:(.*)",
        line,
    )
    if not header:
        return "0000:0000", 0, []
    writes: list[RootWrite] = []
    for encoded in filter(None, header.group(3).split(";")):
        match = ENTRY_RE.fullmatch(encoded)
        if not match:
            raise ValueError(f"invalid root metadata trace entry: {encoded!r}")
        values = match.groupdict()
        writes.append(RootWrite(
            pc=values["pc"].lower(),
            address=int(values["address"], 16),
            old=int(values["old"], 16),
            new=int(values["new"], 16),
            bits=int(values["bits"]),
            sp=int(values["sp"], 16),
            fp=int(values["fp"], 16),
        ))
    return header.group(1).lower(), int(header.group(2)), writes


def new_writes(
    previous_count: int, count: int, ring: list[RootWrite],
) -> tuple[int, list[RootWrite]]:
    if count <= previous_count:
        return 0, []
    delta = count - previous_count
    if delta >= len(ring):
        return max(0, delta - len(ring)), ring
    return 0, ring[-delta:]


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
    previous_count = 0
    previous_pointer = ""
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
        pointer, count, ring = parse_root_writes(
            str(state.get("registers", ""))
        )
        if pointer != previous_pointer:
            print(f"{now:8.3f}s ROOT pointer={pointer}", flush=True)
            previous_pointer = pointer
        lost, writes = new_writes(previous_count, count, ring)
        if lost:
            print(f"{now:8.3f}s WRITES lost={lost}", flush=True)
        sequence = count - len(writes) + 1
        for offset, write in enumerate(writes):
            root_offset = write.address - 0x512878
            print(
                f"{now:8.3f}s WRITE #{sequence + offset} "
                f"+{root_offset:02x} {write.old:04x}>{write.new:04x}/"
                f"{write.bits} by {write.pc} sp={write.sp:04x} "
                f"fp={write.fp:04x}",
                flush=True,
            )
        previous_count = count
        time.sleep(max(args.interval, 0.01))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
