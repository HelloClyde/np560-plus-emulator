#!/usr/bin/env python3
"""Find the physical NP560+ matrix event that exits the current foreground.

This is a read-mostly diagnostic for an already running Web/QEMU instance.
It presents one real F160/F164 matrix position at a time, waits for the guest's
own debounce/mapping path, releases the key, and reports any MAINRET/SCHEDRET
transition.  It does not write guest RAM or intercept resident ROM calls.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from urllib.request import Request, urlopen


RECOVERED_MATRIX_EVENTS = (
    0x65, 0x64, 0x71, 0x77, 0x8E, 0xFFFF, 0x78, 0xC0,
    0x72, 0x66, 0x61, 0x94, 0xE0, 0xE6, 0x63, 0x8D,
    0x74, 0x67, 0x73, 0x92, 0x85, 0x90, 0x76, 0x8B,
    0x79, 0x68, 0x8C, 0x95, 0x84, 0x81, 0x62, 0x88,
    0x75, 0x6A, 0x7A, 0x97, 0xE9, 0x83, 0x6E, 0x8A,
    0x69, 0x6B, 0xB8, 0xBF, 0xEA, 0x80, 0x6D, 0x89,
    0x6F, 0x6C, 0xEE, 0xB7, 0xE1, 0x86, 0x20, 0xB0,
    0x70, 0xE3, 0x7B, 0xB4, 0xE2, 0x82, 0xE7, 0x8F,
)


def application_calls(state: str, name: str) -> int:
    match = re.search(
        rf"(?:APPLICATION_TRACE=|,){re.escape(name)}:(\d+)@", state
    )
    return int(match.group(1)) if match else 0


def diagnostic_counter(state: str, name: str) -> int:
    match = re.search(rf"\b{re.escape(name)}[=:](\d+)", state)
    return int(match.group(1)) if match else 0


def matrix_event_last(state: str) -> int:
    match = re.search(
        r"\bMATRIX_EVENT_MAPS=\d+\s+LAST=([0-9a-fA-F]{4})", state
    )
    return int(match.group(1), 16) if match else -1


def current_pc(state: str) -> str:
    match = re.search(r"^PC=([0-9a-fA-F]{2}:[0-9a-fA-F]{4})", state)
    return match.group(1).lower() if match else "unknown"


def gate(state: str) -> int:
    match = re.search(r"\b2A5C:([0-9a-fA-F]{4})", state)
    return int(match.group(1), 16) if match else -1


def diagnostic_failure(state: str) -> str | None:
    missing = re.search(r"\bROM_MISSING=([^\r\n]+)", state)
    if missing and not missing.group(1).lower().startswith("none"):
        return f"ROM_MISSING={missing.group(1)}"
    unsupported = re.search(r"\bUNSUPPORTED=([^\r\n]+)", state)
    if unsupported and not unsupported.group(1).lower().startswith("none"):
        return f"UNSUPPORTED={unsupported.group(1)}"
    invalid = re.search(r"\bINVALID_CONTROL=([^\r\n]+)", state)
    if invalid and not invalid.group(1).lower().startswith("none"):
        return f"INVALID_CONTROL={invalid.group(1)}"
    return None


class WebClient:
    def __init__(self, root: str) -> None:
        self.root = root.rstrip("/")

    def state(self) -> str:
        with urlopen(f"{self.root}/api/state", timeout=5) as response:
            return json.load(response)["registers"]

    def matrix(self, low: int = 0, high: int = 0) -> None:
        payload = json.dumps({
            "state": 0,
            "code": 0,
            "matrix_low": low & 0xFFFFFFFF,
            "matrix_high": high & 0xFFFFFFFF,
        }).encode()
        request = Request(
            f"{self.root}/api/key",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8775")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=64)
    parser.add_argument("--edge-timeout", type=float, default=1.5)
    parser.add_argument("--rearm-timeout", type=float, default=2.0)
    args = parser.parse_args()
    if not 0 <= args.start < 64 or not 1 <= args.count <= 64 - args.start:
        parser.error("the selected matrix range must stay inside 0..63")

    web = WebClient(args.root)
    web.matrix()
    state = web.state()
    initial_mainret = application_calls(state, "MAINRET")
    initial_schedret = application_calls(state, "SCHEDRET")
    initial_top = application_calls(state, "TOP")
    print(
        f"BASE PC={current_pc(state)} MAINRET={initial_mainret} "
        f"SCHEDRET={initial_schedret} TOP={initial_top}"
    )

    for index in range(args.start, args.start + args.count):
        expected = RECOVERED_MATRIX_EVENTS[index]
        before = web.state()
        maps = diagnostic_counter(before, "MATRIX_EVENT_MAPS")
        active = diagnostic_counter(before, "ACTIVE")
        mainret = application_calls(before, "MAINRET")
        schedret = application_calls(before, "SCHEDRET")
        low = 1 << index if index < 32 else 0
        high = 1 << (index - 32) if index >= 32 else 0
        web.matrix(low, high)

        deadline = time.monotonic() + args.edge_timeout
        edge = before
        mapped = False
        while time.monotonic() < deadline:
            edge = web.state()
            mapped = (
                diagnostic_counter(edge, "MATRIX_EVENT_MAPS") > maps
                and matrix_event_last(edge) == expected
            )
            debounced = diagnostic_counter(edge, "ACTIVE") >= active + 16
            if mapped or debounced:
                break
            time.sleep(0.005)

        web.matrix()
        deadline = time.monotonic() + args.rearm_timeout
        after = edge
        released = False
        rearmed = False
        while time.monotonic() < deadline:
            after = web.state()
            # The Web transport clears the physical matrix immediately.  The
            # last sampled F160 value may remain stale until the guest scans
            # that column again, so also accept the authoritative host matrix
            # state exposed by the machine diagnostics.
            released = (
                "F160:00ff" in after.lower()
                or "KEY_MATRIX=00000000:00000000" in after
            )
            rearmed = gate(after) == 0
            if released and rearmed:
                break
            time.sleep(0.005)

        # The guest sometimes publishes the mapped event only after the
        # physical matrix edge has been released.  Include that final state;
        # otherwise a valid debounce/mapping is incorrectly reported as 0.
        mapped = mapped or (
            diagnostic_counter(after, "MATRIX_EVENT_MAPS") > maps
            and matrix_event_last(after) == expected
        )

        new_mainret = application_calls(after, "MAINRET")
        new_schedret = application_calls(after, "SCHEDRET")
        new_top = application_calls(after, "TOP")
        print(
            f"M{index:02d} EVENT={expected:04X} MAPPED={int(mapped)} "
            f"PC={current_pc(after)} MAINRET={mainret}->{new_mainret} "
            f"SCHEDRET={schedret}->{new_schedret} "
            f"TOP={new_top} GATE={gate(after):04X}"
        )
        failure = diagnostic_failure(after)
        if failure:
            print(f"ABORT=M{index:02d}/{expected:04X} {failure}")
            return 2
        if not released or not rearmed:
            print(
                f"ABORT=M{index:02d}/{expected:04X} "
                f"RELEASED={int(released)} REARMED={int(rearmed)}"
            )
            return 2
        if new_mainret > mainret or new_schedret > schedret:
            print(f"EXIT=M{index:02d}/{expected:04X}")
            return 0
        if new_top != initial_top:
            print(f"TRANSITION=M{index:02d}/{expected:04X} TOP={initial_top}->{new_top}")
            return 0

    print("EXIT=none")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
