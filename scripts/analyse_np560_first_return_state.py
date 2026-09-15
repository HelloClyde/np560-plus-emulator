#!/usr/bin/env python3
"""Capture NP560+ state at the first bootstrap-to-resident return.

The probe ROM loops at 03:0080 before the reconstructed scheduler can start a
second 20:026A lifecycle.  This preserves the bootstrap foreground's exit
state and makes it possible to identify the application/resource descriptor
which the missing factory resident manager would have consumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import time
from pathlib import Path


PROJECT = Path(__file__).resolve().parent.parent
WEB = PROJECT / "scripts" / "web"
sys.path.insert(0, str(WEB))

from np560_web import Emulator  # noqa: E402


WINDOWS = {
    "outer_context": (0x000000, 0x2000),
    "a0_globals": (0x507000, 0x1000),
    "a2_globals": (0x512800, 0x0400),
}

EVENT_INPUTS = {
    0x82: {"key_state": 0, "matrix_low": 0, "matrix_high": 1 << 29},
    0x83: {"key_state": 0, "matrix_low": 0, "matrix_high": 1 << 5},
    0x85: {"key_state": 16, "matrix_low": 1 << 20, "matrix_high": 0},
}

# Logical compiler globals named by exact recovered callers.  A0 and A2 are
# 32-KiB DS windows, hence their physical backing bases are 50:0000 and
# 51:0000 respectively for offsets below 0x8000.
SELECTED_WORDS = {
    "a0_7086": 0x507086,
    "a0_7088": 0x507088,
    "a0_7090": 0x507090,
    "a0_7092": 0x507092,
    "a0_70b6": 0x5070B6,
    "a0_70b8": 0x5070B8,
    "a0_70be": 0x5070BE,
    "a0_72d8": 0x5072D8,
    "a0_72da": 0x5072DA,
    "a0_72dc": 0x5072DC,
    "a0_72de": 0x5072DE,
    "a0_7dee": 0x507DEE,
    "a0_7df0": 0x507DF0,
    "a2_2984": 0x512984,
    "a2_2986": 0x512986,
    "a2_29c8": 0x5129C8,
    "a2_29ca": 0x5129CA,
    "a2_2aa4": 0x512AA4,
    "a2_2aaa": 0x512AAA,
    "a2_2aba": 0x512ABA,
    "a2_2ad6": 0x512AD6,
    "a2_2ad8": 0x512AD8,
    "a2_2ae0": 0x512AE0,
}


def cpu_state(emulator: Emulator) -> str:
    return emulator.qmp.execute(
        "qom-get", {"path": "/machine", "property": "cpu-state"}
    )


def data_memory(emulator: Emulator, address: int, size: int) -> bytes:
    with tempfile.NamedTemporaryFile(prefix="np560-first-return-",
                                     delete=False) as output:
        path = Path(output.name)
    try:
        # Read the machine's dedicated external-data RAM directly.  pmemsave
        # is not sufficient below the SoC-ROM limit because program ROM has
        # priority in QEMU's physical address-space view there.
        emulator.qmp.execute("qom-set", {
            "path": "/machine", "property": "debug-data-save",
            "value": f"0x{address:x}:0x{size:x}@{path}",
        })
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def application_calls(state: str, name: str) -> int:
    match = re.search(
        rf"(?:APPLICATION_TRACE=|,){re.escape(name)}:(\d+)@", state
    )
    return int(match.group(1)) if match else 0


def trace_entry(state: str, name: str) -> str:
    match = re.search(
        rf"(?:APPLICATION_TRACE=|,){re.escape(name)}:[^\n]+?"
        rf"(?=,[A-Z][A-Z0-9]*:|\n)", state,
    )
    return match.group(0).lstrip(",") if match else "none"


def current_pc(state: str) -> str:
    match = re.search(r"^PC=([0-9A-Fa-f]{2}:[0-9A-Fa-f]{4})\b",
                      state, re.MULTILINE)
    return match.group(1).lower() if match else "none"


def require_clean_state(state: str) -> None:
    for expected in (
        "ROM_HLE=off",
        "ROM_MISSING=none",
        "INVALID_CONTROL=none",
        "UNSUPPORTED=none",
        "FIRST_LOW_FP=none",
        "FIRST_LOW_SP=none",
    ):
        if expected not in state:
            raise AssertionError(f"missing {expected!r}:\n{state}")


def set_event(emulator: Emulator, event: int) -> None:
    key = EVENT_INPUTS[event]
    for name, value in (
        ("key-code", 0),
        ("key-matrix-low", key["matrix_low"]),
        ("key-matrix-high", key["matrix_high"]),
        ("key-state", key["key_state"]),
    ):
        emulator.qmp.execute("qom-set", {
            "path": "/machine", "property": name, "value": value,
        })


def release_key(emulator: Emulator) -> None:
    for name in ("key-code", "key-matrix-low", "key-matrix-high", "key-state"):
        emulator.qmp.execute("qom-set", {
            "path": "/machine", "property": name, "value": 0,
        })


def wait_for_state(emulator: Emulator, predicate, timeout: float,
                   description: str) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = cpu_state(emulator)
        require_clean_state(last)
        if predicate(last):
            return last
        if emulator.process.poll() is not None:
            raise AssertionError(
                f"QEMU exited while waiting for {description}:\n{last}"
            )
        time.sleep(0.01)
    raise AssertionError(f"timeout waiting for {description}:\n{last}")


def read_windows(emulator: Emulator) -> dict[str, bytes]:
    return {
        name: data_memory(emulator, base, size)
        for name, (base, size) in WINDOWS.items()
    }


def word_at(windows: dict[str, bytes], physical: int) -> int:
    for name, (base, size) in WINDOWS.items():
        if base <= physical and physical + 2 <= base + size:
            offset = physical - base
            return int.from_bytes(windows[name][offset:offset + 2], "little")
    raise KeyError(f"address {physical:06x} is outside captured windows")


def selected_words(windows: dict[str, bytes]) -> dict[str, str]:
    return {
        name: f"{word_at(windows, address):04x}"
        for name, address in SELECTED_WORDS.items()
    }


def changed_bytes(before: bytes, after: bytes, base: int) -> list[dict]:
    return [
        {"physical": f"{base + offset:06x}",
         "before": f"{old:02x}", "after": f"{new:02x}"}
        for offset, (old, new) in enumerate(zip(before, after))
        if old != new
    ]


def encode_windows(windows: dict[str, bytes]) -> dict:
    return {
        name: {
            "physical": f"{WINDOWS[name][0]:06x}",
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "hex": data.hex(),
        }
        for name, data in windows.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--soc-rom", type=Path, required=True)
    parser.add_argument("--nand-checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--event", type=lambda value: int(value, 0), default=0x85,
        choices=sorted(EVENT_INPUTS),
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    emulator = Emulator(
        qemu=args.qemu,
        firmware=args.firmware,
        soc_rom=args.soc_rom,
        soc_rom_skeleton=True,
        nand_checkpoint=args.nand_checkpoint,
    )
    try:
        ready = wait_for_state(
            emulator,
            lambda state: (
                application_calls(state, "TOP") >= 1 and
                "rom_call=06:b126" in state.lower()
            ),
            args.timeout,
            "bootstrap foreground key reader",
        )
        emulator.qmp.execute("stop")
        before_state = cpu_state(emulator)
        require_clean_state(before_state)
        before = read_windows(emulator)
        initial_main_returns = application_calls(ready, "MAINRET")

        set_event(emulator, args.event)
        emulator.qmp.execute("cont")
        returned = wait_for_state(
            emulator,
            lambda state: (
                application_calls(state, "MAINRET") > initial_main_returns and
                current_pc(state) == "03:0080"
            ),
            args.timeout,
            "first bootstrap return to resident 03:0080",
        )
        emulator.qmp.execute("stop")
        release_key(emulator)
        after_state = cpu_state(emulator)
        require_clean_state(after_state)
        after = read_windows(emulator)

        report = {
            "schema": "np560-first-return-state-v1",
            "boundary": "bootstrap foreground -> 03:0080 before scheduler",
            "event": f"{args.event:02x}",
            "before_pc": current_pc(before_state),
            "after_pc": current_pc(after_state),
            "mainret": trace_entry(returned, "MAINRET"),
            "schedret_count": application_calls(returned, "SCHEDRET"),
            "selected_before": selected_words(before),
            "selected_after": selected_words(after),
            "changes": {
                name: changed_bytes(before[name], after[name], WINDOWS[name][0])
                for name in WINDOWS
            },
            "before_windows": encode_windows(before),
            "after_windows": encode_windows(after),
            "cpu_state": after_state,
            "soc_rom_sha256": hashlib.sha256(args.soc_rom.read_bytes()).hexdigest(),
            "nand_checkpoint_sha256": hashlib.sha256(
                args.nand_checkpoint.read_bytes()
            ).hexdigest(),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.output}")
        print(f"before_pc={report['before_pc']} after_pc={report['after_pc']}")
        print(f"mainret={report['mainret']}")
        print(f"schedret_count={report['schedret_count']}")
        for name in WINDOWS:
            print(f"{name}_changes={len(report['changes'][name])}")
        print("selected_after=" + json.dumps(report["selected_after"],
                                               sort_keys=True))
        return 0
    finally:
        emulator.close()


if __name__ == "__main__":
    raise SystemExit(main())
