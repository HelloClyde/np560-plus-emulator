#!/usr/bin/env python3
"""Monitor the bounded Game World modal-event decoder trace.

The monitor is read-only.  It polls the QEMU Web diagnostics endpoint and
reports the actual caller reached by the exact worker's ``RETS`` at
``1E:FD7A`` after it consumes modal event ``0x86``, including the event type
and code written through the two output pointers owned by live ``2F:C216``.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request


LINE_NAME = "NPE_CONTROL_TRACE="
ENTRY_RE = re.compile(
    r"#(?P<sequence>\d+)/"
    r"(?P<from>[0-9a-fA-F]{2}:[0-9a-fA-F]{4})>"
    r"(?P<target>[0-9a-fA-F]{2}:[0-9a-fA-F]{4})/"
    r"w(?P<word>[0-9a-fA-F]{4})/"
    r"sp(?P<sp>[0-9a-fA-F]{4})/fp(?P<fp>[0-9a-fA-F]{4})"
)


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


def summarize(line: str) -> str:
    head = re.fullmatch(
        r"NPE_CONTROL_TRACE=COUNT:(\d+) FROZEN:(\d+) PENDING:(\d+) "
        r"ACTIVE:(\d+) CALLER:([0-9a-fA-F]{2}:[0-9a-fA-F]{4}) "
        r"RESULT:([0-9a-fA-F]{4}) OUTPUTS:(\d+) "
        r"TYPE:([0-9a-fA-F]{4}) CODE:([0-9a-fA-F]{4}) "
        r"DECODER:(\d+)@([0-9a-fA-F]{2}:[0-9a-fA-F]{4})/"
        r"R([0-9a-fA-F]{4}) TRACE:(.*)",
        line,
    )
    if not head:
        raise RuntimeError("malformed NPE control-trace diagnostic")

    (count, frozen, pending, active, caller, result, outputs_valid,
     event_type, event_code, decoder_valid, decoder_caller,
     decoder_result, trace) = head.groups()
    entries = list(ENTRY_RE.finditer(trace))
    worker_return = next(
        (entry for entry in entries
         if entry.group("from").lower() == "1e:fd7a"),
        None,
    )
    lines = [
        f"modal dispatch count={count} frozen={frozen} pending={pending} "
        f"active={active} "
        f"retained={len(entries)}",
        "modal event 0x86 return=" + (
            f"1e:fd7a>{worker_return.group('target')} result={result} "
            f"outputs={outputs_valid} type={event_type} code={event_code} "
            f"(w{worker_return.group('word')}, "
            f"sp{worker_return.group('sp')}/fp{worker_return.group('fp')})"
            if worker_return else
            f"pending caller={caller} result={result} outputs={outputs_valid} "
            f"type={event_type} code={event_code}"
        ),
        f"event decoder return={decoder_valid}@{decoder_caller} "
        f"result={decoder_result}",
    ]
    if entries:
        last = entries[-1]
        lines.append(
            f"last transfer=#{last.group('sequence')} "
            f"{last.group('from')}>{last.group('target')}"
        )
    elif pending == "0" and active == "0" and frozen == "0":
        lines.append("waiting for modal event 0x86")
    return "\n".join(lines)


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
