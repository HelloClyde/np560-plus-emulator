#!/usr/bin/env python3
"""Monitor the bounded Game World render-object diagnostic from Web/QEMU.

The script is read-only: it polls ``/api/diagnostics`` and condenses the
``NPE_RENDER_OBJECT`` line into the control decisions and byte differences
needed while restoring the original resident/application initialization path.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request


LINE_NAME = "NPE_RENDER_OBJECT="


def fetch_registers(root: str, timeout: float) -> str:
    url = root.rstrip("/") + "/api/diagnostics"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.load(response)
    registers = payload.get("registers")
    if not isinstance(registers, str):
        raise RuntimeError("diagnostics response has no string 'registers'")
    return registers


def find_diagnostic(registers: str, name: str = LINE_NAME) -> str:
    for line in registers.splitlines():
        if line.startswith(name):
            return line
    raise RuntimeError(f"diagnostic line {name.rstrip('=')} is absent")


def _match(line: str, pattern: str) -> re.Match[str]:
    match = re.search(pattern, line)
    if not match:
        raise RuntimeError(f"malformed NPE render-object diagnostic: {pattern}")
    return match


def _snapshot(line: str, label: str) -> bytes | None:
    value = _match(line, rf"\b{label}:(pending|[0-9a-fA-F]+)").group(1)
    if value == "pending":
        return None
    if len(value) % 2:
        raise RuntimeError(f"odd-length {label} snapshot")
    return bytes.fromhex(value)


def _diff(before: bytes | None, after: bytes | None) -> str:
    if before is None or after is None:
        return "pending"
    changes = [
        f"+{index:02X}:{old:02X}>{new:02X}"
        for index, (old, new) in enumerate(zip(before, after))
        if old != new
    ]
    if len(before) != len(after):
        changes.append(f"length:{len(before)}>{len(after)}")
    return ",".join(changes) if changes else "none"


def summarize(line: str) -> str:
    head = _match(
        line,
        r"ACTIVE:(\d+) BASE:([0-9a-fA-F]{4}) CALLS:(\d+) RETURNS:(\d+)",
    )
    context = _match(
        line,
        r"CONTEXT:(\d+)/(\d+)@([0-9a-fA-F]{2}:[0-9a-fA-F]{4})/"
        r"w([0-9a-fA-F]{4})/sp([0-9a-fA-F]{4})/fp([0-9a-fA-F]{4})/"
        r"result([0-9a-fA-F]{4})/init(\d+)/"
        r"branch(\d+)>([0-9a-fA-F]{2}:[0-9a-fA-F]{4})/"
        r"psw([0-9a-fA-F]{4})/r([0-9a-fA-F]{4}):([0-9a-fA-F]{4})/"
        r"fail(\d+)@([0-9a-fA-F]{2}:[0-9a-fA-F]{4})",
    )
    branch0 = _match(
        line,
        r"BRANCH0:(\d+)/([0-9a-fA-F]{2}:[0-9a-fA-F]{4})>"
        r"([0-9a-fA-F]{2}:[0-9a-fA-F]{4})/psw([0-9a-fA-F]{4})/"
        r"r0([0-9a-fA-F]{4})",
    )
    branch1 = _match(
        line,
        r"BRANCH1:(\d+)/([0-9a-fA-F]{2}:[0-9a-fA-F]{4})>"
        r"([0-9a-fA-F]{2}:[0-9a-fA-F]{4})/psw([0-9a-fA-F]{4})/"
        r"r0([0-9a-fA-F]{4})",
    )
    trampoline = _match(
        line,
        r"/tramp(\d+)@([0-9a-fA-F]{2}:[0-9a-fA-F]{4})/"
        r"w([0-9a-fA-F]{4})/sp([0-9a-fA-F]{4})/"
        r"fp([0-9a-fA-F]{4})/r([0-9a-fA-F]{4})",
    )
    compositor = _match(
        line,
        r"\bCOMP:(\d+)@([0-9a-fA-F]{2}:[0-9a-fA-F]{4})/"
        r"w([0-9a-fA-F]{4})/sp([0-9a-fA-F]{4})/fp([0-9a-fA-F]{4})/"
        r"child(\d+)@([0-9a-fA-F]{2}:[0-9a-fA-F]{4})/"
        r"w([0-9a-fA-F]{4})/sp([0-9a-fA-F]{4})/fp([0-9a-fA-F]{4})/"
        r"ret13(\d+)@([0-9a-fA-F]{2}:[0-9a-fA-F]{4})/"
        r"w([0-9a-fA-F]{4})/sp([0-9a-fA-F]{4})/fp([0-9a-fA-F]{4})/"
        r"src(\d+)@([0-9a-fA-F]{2}:[0-9a-fA-F]{4})>"
        r"([0-9a-fA-F]{2}:[0-9a-fA-F]{4})/w([0-9a-fA-F]{4})/"
        r"sp([0-9a-fA-F]{4})/fp([0-9a-fA-F]{4})/r([0-9a-fA-F]{4})/"
        r"stack([0-9a-fA-F,]+)",
    )
    tail = _match(line, r"LAYOUT:(\d+) HELPER:(\d+).*? WRITES:(\d+)/(\d+)")
    initial = _snapshot(line, "INITIAL")
    before = _snapshot(line, "BEFORE")
    after = _snapshot(line, "AFTER")
    retained_writes = line.split(" TRACE:", 1)[1] if " TRACE:" in line else ""

    return "\n".join(
        (
            f"object active={head.group(1)} base={head.group(2)} "
            f"render={head.group(3)}/{head.group(4)}",
            f"context calls/returns={context.group(1)}/{context.group(2)} "
            f"from={context.group(3)}/w{context.group(4)}/"
            f"sp{context.group(5)}/fp{context.group(6)} "
            f"result={context.group(7)} init={context.group(8)} "
            f"branch={context.group(9)}>{context.group(10)} "
            f"psw={context.group(11)} r={context.group(12)}:{context.group(13)} "
            f"failure={context.group(14)}@{context.group(15)}",
            f"context trampoline={trampoline.group(1)} from={trampoline.group(2)} "
            f"w{trampoline.group(3)}/sp{trampoline.group(4)}/"
            f"fp{trampoline.group(5)}/r{trampoline.group(6)}",
            f"compositor entry={compositor.group(1)}@{compositor.group(2)} "
            f"w{compositor.group(3)}/sp{compositor.group(4)}/fp{compositor.group(5)} "
            f"child={compositor.group(6)}@{compositor.group(7)} "
            f"w{compositor.group(8)}/sp{compositor.group(9)}/fp{compositor.group(10)}",
            f"compositor return resident={compositor.group(11)}@{compositor.group(12)} "
            f"w{compositor.group(13)}/sp{compositor.group(14)}/fp{compositor.group(15)} "
            f"source={compositor.group(16)}@{compositor.group(17)}>"
            f"{compositor.group(18)}/w{compositor.group(19)}/"
            f"sp{compositor.group(20)}/fp{compositor.group(21)}/"
            f"r{compositor.group(22)}/stack{compositor.group(23)}",
            f"renderer b0={branch0.group(1)}:{branch0.group(2)}>"
            f"{branch0.group(3)}/psw{branch0.group(4)}/r0{branch0.group(5)} "
            f"b1={branch1.group(1)}:{branch1.group(2)}>"
            f"{branch1.group(3)}/psw{branch1.group(4)}/r0{branch1.group(5)} "
            f"layout={tail.group(1)} helper={tail.group(2)}",
            f"diff initial>before: {_diff(initial, before)}",
            f"diff before>after:  {_diff(before, after)}",
            f"writes total/retained={tail.group(3)}/{tail.group(4)} "
            f"{retained_writes or 'none'}",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8778")
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--raw", action="store_true")
    args = parser.parse_args()

    previous = None
    while True:
        try:
            line = find_diagnostic(fetch_registers(args.root, args.timeout))
            if line != previous:
                stamp = time.strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{stamp}]\n{line if args.raw else summarize(line)}", flush=True)
                previous = line
            if args.once:
                return 0
        except (OSError, RuntimeError, ValueError) as error:
            if args.once:
                raise SystemExit(str(error)) from error
            message = f"ERROR: {error}"
            if message != previous:
                print(message, flush=True)
                previous = message
        time.sleep(max(args.interval, 0.05))


if __name__ == "__main__":
    raise SystemExit(main())
