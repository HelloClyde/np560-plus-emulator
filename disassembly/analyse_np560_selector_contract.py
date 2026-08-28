#!/usr/bin/env python3
"""Compare exact NP560+ scheduler-return state for events 82/83/85.

This is a clean-room reverse-engineering probe.  It boots the reconstructed
SoC ROM variant whose scheduler self-loops at 03:0084, first exits the
bootstrap-owned application with Enter, then injects one selected application
event into the scheduler-owned lifecycle.  QEMU is stopped as soon as the
complete shipped 20:026A frame returns through 20:0326 -> 03:0084.

Each event is repeated so volatile timer/scan bytes can be separated from
repeatable event-dependent RAM state.  The generated JSON is evidence for the
missing factory selector contract; it does not claim to contain factory ROM.
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
WEB = PROJECT / "qemu-dmcu" / "web"
sys.path.insert(0, str(WEB))

from np560_web import Emulator  # noqa: E402


EVENT_INPUTS = {
    0x82: {"key_state": 0, "matrix_low": 0, "matrix_high": 1 << 29},
    0x83: {"key_state": 0, "matrix_low": 0, "matrix_high": 1 << 5},
    0x85: {"key_state": 16, "matrix_low": 1 << 20, "matrix_high": 0},
}


def cpu_state(emulator: Emulator) -> str:
    return emulator.qmp.execute(
        "qom-get", {"path": "/machine", "property": "cpu-state"}
    )


def physical_memory(emulator: Emulator, address: int, size: int) -> bytes:
    with tempfile.NamedTemporaryFile(prefix="np560-selector-", delete=False) as out:
        path = Path(out.name)
    try:
        emulator.qmp.execute("pmemsave", {
            "val": address, "size": size, "filename": str(path),
        })
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def application_calls(state: str, name: str) -> int:
    match = re.search(
        rf"(?:APPLICATION_TRACE=|,){re.escape(name)}:(\d+)@", state
    )
    return int(match.group(1)) if match else 0


def trace_register(state: str, name: str, register: int) -> int:
    match = re.search(
        rf"(?:APPLICATION_TRACE=|,){re.escape(name)}:\d+@[^,\n]*/r"
        rf"([0-9A-Fa-f]{{4}}):([0-9A-Fa-f]{{4}}):"
        rf"([0-9A-Fa-f]{{4}})/a",
        state,
    )
    if not match or register not in (0, 1, 2):
        return -1
    return int(match.group(register + 1), 16)


def trace_entry(state: str, name: str) -> str:
    match = re.search(
        rf"(?:APPLICATION_TRACE=|,){re.escape(name)}:[^\n]+?"
        rf"(?=,[A-Z][A-Z0-9]*:|\n)",
        state,
    )
    return match.group(0).lstrip(",") if match else "none"


def current_cpu_registers(state: str) -> dict[str, str]:
    """Parse the complete architectural state printed at the stop boundary."""
    registers = {
        f"r{number}": value.lower()
        for number, value in re.findall(
            r"\bR\s*(1[0-5]|[0-9])\s*=([0-9A-Fa-f]{4})\b", state
        )
    }
    header = re.search(
        r"^PC=([0-9A-Fa-f]{2}:[0-9A-Fa-f]{4})\s+"
        r"PSW=([ZCNV-]{4})\s+DS0=([0-9A-Fa-f]{3})\s+"
        r"DS1=([0-9A-Fa-f]{3})$",
        state,
        re.MULTILINE,
    )
    if not header or len(registers) != 16:
        raise AssertionError(f"could not parse stopped CPU state:\n{state}")
    return {
        "pc": header.group(1).lower(),
        "psw": header.group(2),
        "ds0": header.group(3).lower(),
        "ds1": header.group(4).lower(),
        **registers,
    }


def diagnostic_line(state: str, prefix: str) -> str:
    match = re.search(rf"^{re.escape(prefix)}[^\n]*", state, re.MULTILINE)
    return match.group(0) if match else f"{prefix}none"


def rom_call_count(state: str) -> int:
    match = re.search(r"\bROM_CALL=[^\n]*\bCALLS=(\d+)", state)
    return int(match.group(1)) if match else 0


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


def set_key(emulator: Emulator, *, key_state: int, matrix_low: int,
            matrix_high: int) -> None:
    for property_name, value in (
        ("key-code", 0),
        ("key-matrix-low", matrix_low),
        ("key-matrix-high", matrix_high),
        ("key-state", key_state),
    ):
        emulator.qmp.execute("qom-set", {
            "path": "/machine", "property": property_name, "value": value,
        })


def release_key(emulator: Emulator) -> None:
    set_key(emulator, key_state=0, matrix_low=0, matrix_high=0)


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


def changed_bytes(before: bytes, after: bytes) -> dict[int, tuple[int, int]]:
    if len(before) != len(after):
        raise ValueError("snapshot sizes differ")
    return {
        address: (old, new)
        for address, (old, new) in enumerate(zip(before, after))
        if old != new
    }


def summarize_runs(runs: list[dict]) -> dict:
    event_summaries = {}
    all_changed = set()
    for event_name, event_runs in runs.items():
        changed_sets = [set(run["changes"]) for run in event_runs]
        repeatable_changed = set.intersection(*changed_sets)
        stable_transitions = {}
        for address in sorted(repeatable_changed):
            transitions = {
                tuple(run["changes"][address]) for run in event_runs
            }
            if len(transitions) == 1:
                old, new = transitions.pop()
                stable_transitions[address] = (old, new)
        event_summaries[event_name] = {
            "changed_counts": [len(run["changes"]) for run in event_runs],
            "repeatable_changed_count": len(repeatable_changed),
            "stable_transition_count": len(stable_transitions),
            "stable_transitions": stable_transitions,
        }
        all_changed.update(*(set(run["changes"]) for run in event_runs))

    stable_discriminators = {}
    for address in sorted(all_changed):
        signatures = {}
        stable = True
        for event_name, event_runs in runs.items():
            values = {
                (run["before"][address], run["after"][address])
                for run in event_runs
            }
            if len(values) != 1:
                stable = False
                break
            signatures[event_name] = next(iter(values))
        if stable and len({value[1] for value in signatures.values()}) > 1:
            stable_discriminators[address] = signatures

    return {
        "events": event_summaries,
        "stable_event_discriminators": stable_discriminators,
    }


def encode_transitions(transitions: dict) -> list[dict]:
    return [
        {
            "address": f"{address:06x}",
            "before": f"{values[0]:02x}",
            "after": f"{values[1]:02x}",
        }
        for address, values in sorted(transitions.items())
    ]


def encode_summary(summary: dict) -> dict:
    encoded_events = {}
    for event_name, event in summary["events"].items():
        encoded_events[event_name] = {
            key: value for key, value in event.items()
            if key != "stable_transitions"
        }
        encoded_events[event_name]["stable_transitions"] = encode_transitions(
            event["stable_transitions"]
        )
    discriminators = []
    for address, signatures in sorted(
            summary["stable_event_discriminators"].items()):
        discriminators.append({
            "address": f"{address:06x}",
            "events": {
                event: {"before": f"{pair[0]:02x}", "after": f"{pair[1]:02x}"}
                for event, pair in signatures.items()
            },
        })
    return {
        "events": encoded_events,
        "stable_event_discriminators": discriminators,
    }


def run_event(args, event: int, repetition: int) -> dict:
    emulator = Emulator(
        qemu=args.qemu,
        firmware=args.firmware,
        soc_rom=args.soc_rom,
        soc_rom_skeleton=True,
        nand_checkpoint=args.nand_checkpoint,
    )
    state = ""
    try:
        state = wait_for_state(
            emulator,
            lambda sample: (
                application_calls(sample, "TOP") >= 1 and
                "rom_call=06:b126" in sample.lower()
            ),
            args.timeout,
            "the bootstrap-owned native key reader",
        )

        # Exit the bootstrap-owned foreground.  This return does not yet pass
        # through the reconstructed scheduler, so it gives every event run the
        # same complete TOP 2 starting state.
        initial_main_returns = application_calls(state, "MAINRET")
        set_key(
            emulator, key_state=16, matrix_low=1 << 20, matrix_high=0,
        )
        pressed = wait_for_state(
            emulator,
            lambda sample: (
                application_calls(sample, "MAINRET") > initial_main_returns and
                trace_register(sample, "MAINRET", 0) == 0x85
            ),
            args.timeout,
            "bootstrap Enter return",
        )
        release_calls = rom_call_count(pressed)
        release_key(emulator)
        state = wait_for_state(
            emulator,
            lambda sample: (
                application_calls(sample, "TOP") >= 2 and
                "rom_call=06:b126" in sample.lower() and
                rom_call_count(sample) > release_calls
            ),
            args.timeout,
            "the scheduler-owned native key reader",
        )

        before = physical_memory(emulator, 0, 0x1000000)
        initial_scheduler_returns = application_calls(state, "SCHEDRET")
        initial_main_returns = application_calls(state, "MAINRET")
        set_key(emulator, **EVENT_INPUTS[event])
        state = wait_for_state(
            emulator,
            lambda sample: (
                application_calls(sample, "MAINRET") > initial_main_returns and
                trace_register(sample, "MAINRET", 0) == event
            ),
            args.timeout,
            f"event {event:02x} application return",
        )
        # Remove the physical key before sampling the manager boundary.  This
        # eliminates F160/F164 and the active scanner latch as trivial event
        # discriminators while retaining state committed by the application.
        release_key(emulator)
        state = wait_for_state(
            emulator,
            lambda sample: (
                application_calls(sample, "SCHEDRET") >
                initial_scheduler_returns and
                trace_register(sample, "SCHEDRET", 2) == event
            ),
            args.timeout,
            f"event {event:02x} scheduler return",
        )
        emulator.qmp.execute("stop")
        state = cpu_state(emulator)
        require_clean_state(state)
        if trace_register(state, "SCHEDRET", 2) != event:
            raise AssertionError(
                f"event {event:02x} was not preserved in R2:\n{state}"
            )
        after = physical_memory(emulator, 0, 0x1000000)
        changes = changed_bytes(before, after)
        return {
            "event": f"{event:02x}",
            "repetition": repetition,
            "before_sha256": hashlib.sha256(before).hexdigest(),
            "after_sha256": hashlib.sha256(after).hexdigest(),
            "changed_count": len(changes),
            "schedret": trace_entry(state, "SCHEDRET"),
            "mainret": trace_entry(state, "MAINRET"),
            "selector_state_writes": diagnostic_line(
                state, "SELECTOR_STATE_WRITES="
            ),
            "registers": {
                f"r{register}": f"{trace_register(state, 'SCHEDRET', register):04x}"
                for register in range(3)
            },
            "stopped_cpu": current_cpu_registers(state),
            "before": before,
            "after": after,
            "changes": changes,
        }
    finally:
        emulator.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--soc-rom", type=Path, required=True)
    parser.add_argument("--nand-checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=40.0)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")

    runs = {f"{event:02x}": [] for event in EVENT_INPUTS}
    for event in EVENT_INPUTS:
        for repetition in range(1, args.repetitions + 1):
            print(
                f"selector probe event={event:02x} "
                f"repetition={repetition}/{args.repetitions}",
                flush=True,
            )
            runs[f"{event:02x}"].append(run_event(args, event, repetition))

    summary = summarize_runs(runs)
    report = {
        "schema": "np560-selector-contract-v1",
        "probe": {
            "scheduler_return": "20:0326 -> 03:0084",
            "events": [f"{event:02x}" for event in EVENT_INPUTS],
            "repetitions": args.repetitions,
            "soc_rom_sha256": hashlib.sha256(args.soc_rom.read_bytes()).hexdigest(),
            "nand_checkpoint_sha256": hashlib.sha256(
                args.nand_checkpoint.read_bytes()
            ).hexdigest(),
        },
        "runs": {
            event: [
                {key: value for key, value in run.items()
                 if key not in ("before", "after", "changes")}
                for run in event_runs
            ]
            for event, event_runs in runs.items()
        },
        "summary": encode_summary(summary),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"wrote {args.output}")
    for event, event_summary in report["summary"]["events"].items():
        print(
            f"event={event} changed={event_summary['changed_counts']} "
            f"stable={event_summary['stable_transition_count']}"
        )
    print(
        "stable_event_discriminators="
        f"{len(report['summary']['stable_event_discriminators'])}"
    )
    for discriminator in report["summary"]["stable_event_discriminators"]:
        values = " ".join(
            f"{event}:{pair['before']}>{pair['after']}"
            for event, pair in discriminator["events"].items()
        )
        print(f"  {discriminator['address']} {values}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
