#!/usr/bin/env python3
"""Stop at the first resource-range candidate selected after a valid CAFE record."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import re
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


TRACE_LINE = "RESOURCE_CANDIDATES"
EXPECTED_BASE = 0x0E93
EXPECTED_RANGE = 0x0158


@dataclass(frozen=True)
class ResourceCandidate:
    pc: str
    caller: str
    source_logical: int
    source_physical: int
    old: int
    base: int
    range_: int
    r8: int
    r10: int
    sp: int
    fp: int
    ds0: int
    ds1: int
    parent_fp: int
    copy_args: tuple[int, ...]
    outer_caller: str
    outer_args: tuple[int, ...]
    record: tuple[int, ...]

    @property
    def cafe_consistent(self) -> bool:
        return (
            len(self.record) >= 3 and
            self.record[0] == 0xCAFE and
            self.record[1] == self.base and
            self.record[2] == self.range_
        )

    @property
    def expected(self) -> bool:
        return self.base == EXPECTED_BASE and self.range_ == EXPECTED_RANGE


ENTRY_RE = re.compile(
    r"(?P<pc>[0-9a-fA-F]{2}:[0-9a-fA-F]{4})<"
    r"(?P<caller>[0-9a-fA-F]{2}:[0-9a-fA-F]{4})/"
    r"src(?P<source_logical>[0-9a-fA-F]{4})"
    r"\(p(?P<source_physical>[0-9a-fA-F]{6})\)/"
    r"(?P<old>[0-9a-fA-F]{4})>"
    r"(?P<base>[0-9a-fA-F]{4}),"
    r"(?P<range>[0-9a-fA-F]{4})/"
    r"r8(?P<r8>[0-9a-fA-F]{4})/"
    r"r10(?P<r10>[0-9a-fA-F]{4})/"
    r"sp(?P<sp>[0-9a-fA-F]{4})/"
    r"fp(?P<fp>[0-9a-fA-F]{4})/"
    r"ds(?P<ds0>[0-9a-fA-F]{3}),(?P<ds1>[0-9a-fA-F]{3})/"
    r"pfp(?P<parent_fp>[0-9a-fA-F]{4})/"
    r"args(?P<copy_args>[0-9a-fA-F]{4}(?:,[0-9a-fA-F]{4}){5})/"
    r"outer(?P<outer_caller>[0-9a-fA-F]{2}:[0-9a-fA-F]{4})/"
    r"oargs(?P<outer_args>[0-9a-fA-F]{4}(?:,[0-9a-fA-F]{4}){5})/"
    r"rec(?P<record>-|[0-9a-fA-F]{4}(?:,[0-9a-fA-F]{4})*)"
)


def fetch_state(url: str, timeout: float) -> dict[str, Any]:
    with urlopen(f"{url.rstrip('/')}/api/state", timeout=timeout) as response:
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


def parse_candidates(registers: str) -> tuple[int, list[ResourceCandidate]]:
    line = state_line(registers, TRACE_LINE)
    header = re.fullmatch(r"COUNT:(\d+) TRACE=(.*)", line)
    if not header:
        return 0, []
    count = int(header.group(1))
    entries: list[ResourceCandidate] = []
    if not header.group(2):
        return count, entries
    for encoded in header.group(2).split(";"):
        match = ENTRY_RE.fullmatch(encoded)
        if not match:
            raise ValueError(f"invalid resource candidate trace entry: {encoded!r}")
        values = match.groupdict()
        record = () if values["record"] == "-" else tuple(
            int(word, 16) for word in values["record"].split(",")
        )
        entries.append(ResourceCandidate(
            pc=values["pc"].lower(),
            caller=values["caller"].lower(),
            source_logical=int(values["source_logical"], 16),
            source_physical=int(values["source_physical"], 16),
            old=int(values["old"], 16),
            base=int(values["base"], 16),
            range_=int(values["range"], 16),
            r8=int(values["r8"], 16),
            r10=int(values["r10"], 16),
            sp=int(values["sp"], 16),
            fp=int(values["fp"], 16),
            ds0=int(values["ds0"], 16),
            ds1=int(values["ds1"], 16),
            parent_fp=int(values["parent_fp"], 16),
            copy_args=tuple(
                int(word, 16) for word in values["copy_args"].split(",")
            ),
            outer_caller=values["outer_caller"].lower(),
            outer_args=tuple(
                int(word, 16) for word in values["outer_args"].split(",")
            ),
            record=record,
        ))
    return count, entries


def new_candidates(previous_count: int, count: int,
                   ring: list[ResourceCandidate]
                   ) -> tuple[int, list[ResourceCandidate]]:
    if count <= previous_count:
        return 0, []
    delta = count - previous_count
    if delta >= len(ring):
        return max(0, delta - len(ring)), ring
    return 0, ring[-delta:]


def first_divergent_after_expected(
    candidates: list[ResourceCandidate], armed: bool = False,
) -> tuple[bool, ResourceCandidate | None]:
    for candidate in candidates:
        if candidate.expected and candidate.cafe_consistent:
            armed = True
        elif armed and candidate.base != 0 and not candidate.expected:
            return armed, candidate
    return armed, None


def format_candidate(candidate: ResourceCandidate) -> str:
    signature = candidate.record[0] if candidate.record else None
    signature_text = "----" if signature is None else f"{signature:04x}"
    return (
        f"{candidate.base:04x}/{candidate.range_:04x} "
        f"record={signature_text} source={candidate.source_physical:06x} "
        f"copy={candidate.pc} caller={candidate.caller} "
        f"outer={candidate.outer_caller} r8={candidate.r8:04x} "
        f"sp={candidate.sp:04x} fp={candidate.fp:04x}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--interval", type=float, default=0.02)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--startup-timeout", type=float, default=90.0)
    parser.add_argument("--duration", type=float, default=120.0)
    args = parser.parse_args()

    started = time.monotonic()
    connected = False
    previous_count = 0
    armed = False
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
        count, ring = parse_candidates(str(state.get("registers", "")))
        lost, candidates = new_candidates(previous_count, count, ring)
        if lost:
            print(f"{now:8.3f}s CANDIDATES lost={lost}", flush=True)
        sequence = count - len(candidates) + 1
        for offset, candidate in enumerate(candidates):
            print(
                f"{now:8.3f}s CANDIDATE #{sequence + offset} "
                f"{format_candidate(candidate)} "
                f"consistent={int(candidate.cafe_consistent)}",
                flush=True,
            )
        previous_count = count
        armed, incident = first_divergent_after_expected(candidates, armed)
        if incident:
            record = ",".join(f"{word:04x}" for word in incident.record)
            print(
                f"{now:8.3f}s INCIDENT selected candidate after valid CAFE: "
                f"{format_candidate(incident)} record_words={record or '-'}",
                flush=True,
            )
            return 2
        time.sleep(max(args.interval, 0.01))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
