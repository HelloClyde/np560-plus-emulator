#!/usr/bin/env python3
"""Print concise NP560 directory-record decisions from the Web endpoint."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import re
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


TRACE_LINE = "FILE_RECORD_CANDIDATES"
RECORD_BYTES = 0x40


@dataclass(frozen=True)
class FileRecordCandidate:
    sequence: int
    call: int
    output: int
    selector: int
    pointer: int
    cursor: int
    limit: int
    span: int
    active: int
    compare_valid: bool
    compare: int
    data: bytes

    @property
    def short_name(self) -> str:
        raw = self.data[:11]
        base = raw[:8].decode("ascii", errors="replace").rstrip()
        extension = raw[8:11].decode("ascii", errors="replace").rstrip()
        return f"{base}.{extension}" if extension else base

    @property
    def attribute(self) -> int:
        return self.data[11]

    @property
    def kind(self) -> str:
        first = self.data[0]
        if first == 0:
            return "end"
        if first == 0xE5:
            return "deleted"
        if self.attribute & 0x0F == 0x0F:
            return "long-name"
        if self.attribute & 0x08:
            return "volume"
        if self.attribute & 0x10:
            return "directory"
        return "file"

    @property
    def decision(self) -> str:
        if self.kind in {"end", "deleted", "long-name"}:
            return self.kind
        if self.compare_valid and self.compare != 0:
            return "selector-mismatch"
        if self.attribute & 0x08:
            return "volume-rejected"
        return "eligible"


ENTRY_RE = re.compile(
    r"#(?P<sequence>\d+)/call(?P<call>\d+)/"
    r"out(?P<output>[0-9a-fA-F]{6})/"
    r"sel(?P<selector>[0-9a-fA-F]{6})/"
    r"p(?P<pointer>[0-9a-fA-F]{6})/"
    r"cur(?P<cursor>[0-9a-fA-F]{4})/"
    r"lim(?P<limit>[0-9a-fA-F]{4})/"
    r"span(?P<span>[0-9a-fA-F]{4})/"
    r"act(?P<active>[0-9a-fA-F]{4})/"
    r"cmp(?P<invalid>-?)(?P<compare>[0-9a-fA-F]{4})/"
    rf"data(?P<data>[0-9a-fA-F]{{{RECORD_BYTES * 2}}})"
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


def parse_candidates(registers: str) -> tuple[int, list[FileRecordCandidate]]:
    line = state_line(registers, TRACE_LINE)
    header = re.fullmatch(r"COUNT:(\d+) TRACE:(.*)", line)
    if not header:
        return 0, []
    count = int(header.group(1))
    candidates: list[FileRecordCandidate] = []
    for encoded in filter(None, header.group(2).split(";")):
        match = ENTRY_RE.fullmatch(encoded)
        if not match:
            raise ValueError(f"invalid file-record candidate: {encoded!r}")
        values = match.groupdict()
        candidates.append(FileRecordCandidate(
            sequence=int(values["sequence"]),
            call=int(values["call"]),
            output=int(values["output"], 16),
            selector=int(values["selector"], 16),
            pointer=int(values["pointer"], 16),
            cursor=int(values["cursor"], 16),
            limit=int(values["limit"], 16),
            span=int(values["span"], 16),
            active=int(values["active"], 16),
            compare_valid=values["invalid"] != "-",
            compare=int(values["compare"], 16),
            data=bytes.fromhex(values["data"]),
        ))
    return count, candidates


def format_candidate(candidate: FileRecordCandidate) -> str:
    compare = f"{candidate.compare:04x}" if candidate.compare_valid else "----"
    return (
        f"#{candidate.sequence} call={candidate.call} "
        f"name={candidate.short_name!r} attr={candidate.attribute:02x} "
        f"kind={candidate.kind} compare={compare} "
        f"cursor={candidate.cursor:04x}/{candidate.span:04x} "
        f"decision={candidate.decision}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--startup-timeout", type=float, default=90.0)
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument(
        "--once", action="store_true",
        help="print the current ring once (including an empty ring) and exit",
    )
    args = parser.parse_args()

    started = time.monotonic()
    connected = False
    previous_sequence = 0
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
        count, candidates = parse_candidates(str(state.get("registers", "")))
        for candidate in candidates:
            if args.once or candidate.sequence > previous_sequence:
                print(f"{now:8.3f}s {format_candidate(candidate)}", flush=True)
        if candidates:
            previous_sequence = max(candidate.sequence for candidate in candidates)
        if args.once:
            if not candidates:
                print(f"{now:8.3f}s CANDIDATES count={count}", flush=True)
            return 0
        time.sleep(max(args.interval, 0.01))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
