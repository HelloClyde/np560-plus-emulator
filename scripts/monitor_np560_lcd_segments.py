#!/usr/bin/env python3
"""Monitor the NP560+ factory LCD annunciator buffer without mutating QEMU.

The V3.80 firmware keeps two 240-bit annunciator planes at data address
51:2734.  Resident routine 14:6E10 transfers those planes to ST7529 lines 19
and 140, outside the 240x120 dot-matrix window.  On the real device those
signals drive the custom-glass status icons above the main LCD surface.

This monitor polls the existing read-only Web memory endpoint and prints only
changes, which makes hardware-input and firmware-state correlations quick to
spot without adding guest hooks or injecting keys.
"""

from __future__ import annotations

import argparse
import base64
import json
import time
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import urlopen


STATUS_ADDRESS = 0x512734
PLANE_BYTES = 30
STATUS_BYTES = PLANE_BYTES * 2


@dataclass(frozen=True)
class StatusPlanes:
    raw: bytes

    @property
    def bits(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        planes: list[tuple[int, ...]] = []
        for plane in range(2):
            payload = self.raw[plane * PLANE_BYTES:(plane + 1) * PLANE_BYTES]
            planes.append(tuple(
                byte_index * 8 + bit
                for byte_index, value in enumerate(payload)
                for bit in range(8)
                if value & (1 << bit)
            ))
        return planes[0], planes[1]

    @property
    def hex(self) -> str:
        return self.raw.hex()


def endpoint(base_url: str) -> str:
    query = urlencode({
        "source": "data",
        "base": hex(STATUS_ADDRESS),
        "size": STATUS_BYTES,
    })
    return f"{base_url.rstrip('/')}/api/state?{query}"


def read_status(base_url: str, timeout: float) -> StatusPlanes:
    with urlopen(endpoint(base_url), timeout=timeout) as response:
        state = json.load(response)
    if state.get("source") != "data" or state.get("format") != "packed":
        raise ValueError("Web endpoint did not return a packed data-bus view")
    payload = base64.b64decode(state["frame"], validate=True)
    if len(payload) != STATUS_BYTES:
        raise ValueError(
            f"status buffer is {len(payload)} bytes, expected {STATUS_BYTES}"
        )
    return StatusPlanes(payload)


def bit_delta(
    previous: tuple[int, ...], current: tuple[int, ...],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    old = set(previous)
    new = set(current)
    return tuple(sorted(new - old)), tuple(sorted(old - new))


def format_bits(bits: tuple[int, ...]) -> str:
    return ",".join(str(bit) for bit in bits) if bits else "-"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument(
        "--samples", type=int, default=0,
        help="number of samples; zero keeps monitoring until interrupted",
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--show-unchanged", action="store_true",
        help="print every sample instead of only changes",
    )
    args = parser.parse_args()
    if args.interval <= 0 or args.samples < 0 or args.timeout <= 0:
        parser.error("interval/timeout must be positive and samples nonnegative")

    previous: StatusPlanes | None = None
    sample = 0
    try:
        while args.samples == 0 or sample < args.samples:
            current = read_status(args.url, args.timeout)
            sample += 1
            current_bits = current.bits
            if previous is None:
                print(
                    f"#{sample} plane19={format_bits(current_bits[0])} "
                    f"plane140={format_bits(current_bits[1])} "
                    f"hex={current.hex}"
                )
            elif current.raw != previous.raw:
                previous_bits = previous.bits
                changes = []
                for plane in range(2):
                    enabled, disabled = bit_delta(
                        previous_bits[plane], current_bits[plane],
                    )
                    changes.append(
                        f"plane{(19, 140)[plane]} "
                        f"+{format_bits(enabled)} -{format_bits(disabled)}"
                    )
                print(f"#{sample} {'; '.join(changes)} hex={current.hex}")
            elif args.show_unchanged:
                print(f"#{sample} unchanged hex={current.hex}")
            previous = current
            if args.samples == 0 or sample < args.samples:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
