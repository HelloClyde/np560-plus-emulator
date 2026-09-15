#!/usr/bin/env python3
"""Print only NP560 initialization/event-state changes and their writers.

Attach to an existing Web/QEMU process.  The QEMU hardware model records the
instruction PC for every value-changing write to the low-level event helper's
flags and timestamps.  This client de-duplicates polling snapshots, so a long
modal wait produces a compact causal timeline instead of a multi-gigabyte
instruction log.
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


EVENT_LINE = "EVENT_STATE"
WRITE_LINE = "EVENT_STATE_WRITES"
USB_LINE = "USB_BOOT_STATE"
USB_WRITE_LINE = "USB_BOOT_WRITES"
MILESTONES = ("MODALPOLL", "MODALDONE", "LAUNCH", "MENU")
USB_MILESTONES = (
    "DETECT", "INIT", "SVCCLEAR", "SVCSET", "TRIGGER",
)
# 2ABC is a continuously advancing firmware tick, useful in a one-shot state
# dump but not as an initialization transition.  Suppress it from delta output
# so a long cold-boot monitor remains a short causal trace.
USB_VOLATILE_VALUES = frozenset(("2ABC",))
USB_VOLATILE_MILESTONES = frozenset(("DETECT",))


@dataclass(frozen=True)
class EventWrite:
    pc: str
    address: int
    old: int
    new: int
    bits: int


def endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def fetch_state(base_url: str, timeout: float) -> dict[str, Any]:
    with urlopen(endpoint(base_url, "/api/state"), timeout=timeout) as response:
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


def parse_values(registers: str) -> dict[str, int]:
    line = state_line(registers, EVENT_LINE)
    return {
        name: int(value, 16)
        for name, value in re.findall(r"([0-9A-Z]+):([0-9a-fA-F]{4})", line)
    }


def parse_usb_values(registers: str) -> dict[str, int]:
    line = state_line(registers, USB_LINE)
    result = {
        name: int(value, 16)
        for name, value in re.findall(
            r"(SFRB0|4B28|2A48|2A4A|2A56|2ABC):([0-9a-fA-F]{4})",
            line,
        )
    }
    bit_match = re.search(r"(?:^|\s)BIT13:([01])", line)
    if bit_match:
        result["BIT13"] = int(bit_match.group(1))
    return result


def parse_named_writes(registers: str,
                       line_name: str) -> tuple[int, list[EventWrite]]:
    line = state_line(registers, line_name)
    count_match = re.search(r"(?:^|\s)COUNT:(\d+)", line)
    count = int(count_match.group(1)) if count_match else 0
    writes = [
        EventWrite(pc.lower(), int(address, 16), int(old, 16),
                   int(new, 16), int(bits))
        for pc, address, old, new, bits in re.findall(
            r"([0-9a-fA-F]{2}:[0-9a-fA-F]{4})/"
            r"([0-9a-fA-F]{6})/([0-9a-fA-F]{4})>"
            r"([0-9a-fA-F]{4})/(8|16)",
            line,
        )
    ]
    return count, writes


def parse_writes(registers: str) -> tuple[int, list[EventWrite]]:
    return parse_named_writes(registers, WRITE_LINE)


def parse_usb_writes(registers: str) -> tuple[int, list[EventWrite]]:
    return parse_named_writes(registers, USB_WRITE_LINE)


def usb_milestone_counts(registers: str) -> dict[str, int]:
    line = state_line(registers, USB_LINE)
    return {
        name: int(match.group(1)) if (match := re.search(
            rf"(?:MILESTONES:|,){name}:(\d+)", line,
        )) else 0
        for name in USB_MILESTONES
    }


def application_counts(registers: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for milestone in MILESTONES:
        match = re.search(
            rf"(?:APPLICATION_TRACE=|,){milestone}:(\d+)@", registers,
        )
        result[milestone] = int(match.group(1)) if match else 0
    return result


def incidents(registers: str) -> list[str]:
    result: list[str] = []
    for name in ("ROM_MISSING", "INVALID_CONTROL", "UNSUPPORTED"):
        value = state_line(registers, name)
        if value != "none" and not value.startswith("none "):
            result.append(f"{name}={value}")
    return result


def new_writes(previous_count: int, count: int,
               ring: list[EventWrite]) -> tuple[int, list[EventWrite]]:
    if count <= previous_count:
        return 0, []
    delta = count - previous_count
    if delta >= len(ring):
        return max(0, delta - len(ring)), ring
    return 0, ring[-delta:]


def format_values(changed: dict[str, tuple[int | None, int]]) -> str:
    return " ".join(
        f"{name}:{'----' if old is None else f'{old:04x}'}>{new:04x}"
        for name, (old, new) in changed.items()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8777")
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=90.0,
        help=(
            "wait this long for the Web/QEMU endpoint before failing; large "
            "checkpoints are hash-validated before the port starts listening"
        ),
    )
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--stop-at", choices=("done", "launch", "menu",
                                               "usb-trigger", "incident",
                                               "never"),
                        default="launch")
    args = parser.parse_args()

    started = time.monotonic()
    previous_values: dict[str, int] = {}
    previous_writes = 0
    previous_milestones = {name: 0 for name in MILESTONES}
    previous_usb_values: dict[str, int] = {}
    previous_usb_writes = 0
    previous_usb_milestones = {name: 0 for name in USB_MILESTONES}
    connected = False
    while args.duration <= 0 or time.monotonic() - started < args.duration:
        try:
            state = fetch_state(args.url, args.timeout)
        except (OSError, URLError, ValueError):
            if connected or time.monotonic() - started >= args.startup_timeout:
                raise
            time.sleep(max(args.interval, 0.05))
            continue
        if not connected:
            connected = True
            print(
                f"{time.monotonic() - started:8.3f}s READY {args.url}",
                flush=True,
            )
        registers = str(state.get("registers", ""))
        now = time.monotonic() - started
        values = parse_values(registers)
        changed = {
            name: (previous_values.get(name), value)
            for name, value in values.items()
            if previous_values.get(name) != value and
            (not previous_values or name not in ("0494", "0496", "0498", "TICK"))
        }
        if changed:
            print(f"{now:8.3f}s STATE {format_values(changed)}", flush=True)
            previous_values = values

        write_count, ring = parse_writes(registers)
        lost, writes = new_writes(previous_writes, write_count, ring)
        if lost:
            print(f"{now:8.3f}s WRITES lost={lost} (poll slower than ring)",
                  flush=True)
        sequence = write_count - len(writes) + 1
        for offset, write in enumerate(writes):
            print(f"{now:8.3f}s WRITE #{sequence + offset} "
                  f"{write.address:06x} {write.old:04x}>{write.new:04x}/"
                  f"{write.bits} by {write.pc}", flush=True)
        previous_writes = write_count

        usb_values = parse_usb_values(registers)
        usb_changed = {
            name: (previous_usb_values.get(name), value)
            for name, value in usb_values.items()
            if (name not in USB_VOLATILE_VALUES and
                previous_usb_values.get(name) != value)
        }
        if usb_changed:
            print(f"{now:8.3f}s USB_STATE {format_values(usb_changed)}",
                  flush=True)
        previous_usb_values = usb_values

        usb_write_count, usb_ring = parse_usb_writes(registers)
        lost, usb_writes = new_writes(previous_usb_writes, usb_write_count,
                                      usb_ring)
        if lost:
            print(f"{now:8.3f}s USB_WRITES lost={lost} "
                  "(poll slower than ring)", flush=True)
        sequence = usb_write_count - len(usb_writes) + 1
        for offset, write in enumerate(usb_writes):
            address = "SFRB0" if write.address == 0xFF00B0 else \
                      f"{write.address:06x}"
            print(f"{now:8.3f}s USB_WRITE #{sequence + offset} "
                  f"{address} {write.old:04x}>{write.new:04x}/"
                  f"{write.bits} by {write.pc}", flush=True)
        previous_usb_writes = usb_write_count

        usb_milestones = usb_milestone_counts(registers)
        for name, count in usb_milestones.items():
            if (name not in USB_VOLATILE_MILESTONES and
                count != previous_usb_milestones[name]):
                print(f"{now:8.3f}s USB_MILESTONE {name}={count}",
                      flush=True)
        previous_usb_milestones = usb_milestones

        milestones = application_counts(registers)
        for name, count in milestones.items():
            if count != previous_milestones[name]:
                print(f"{now:8.3f}s MILESTONE {name}={count}", flush=True)
        previous_milestones = milestones

        problems = incidents(registers)
        if problems:
            for problem in problems:
                print(f"{now:8.3f}s INCIDENT {problem}", flush=True)
            if args.stop_at in ("incident", "done", "launch", "menu"):
                return 2
        if args.stop_at == "done" and milestones["MODALDONE"]:
            return 0
        if args.stop_at == "launch" and milestones["LAUNCH"]:
            return 0
        if args.stop_at == "menu" and milestones["MENU"]:
            return 0
        if args.stop_at == "usb-trigger" and usb_milestones["TRIGGER"]:
            return 0
        time.sleep(max(args.interval, 0.01))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
