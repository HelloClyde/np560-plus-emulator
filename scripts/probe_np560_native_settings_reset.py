#!/usr/bin/env python3
"""Exercise the native sound setting on an isolated Web run.

Uses physical matrix input and read-only observations, never guest memory writes.
The default mode checks system_reset. Separate set-off/read-off modes allow the
caller to close the first process and boot a second from its saved NAND. Process
and file identities must be checked by that caller; read-off alone does not prove
disk persistence, NPE audio decoding, or all board reset semantics.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import time
from pathlib import Path

from probe_np560_checkpoint_boot import assess, save_snapshot
from probe_np560_matrix_route import (
    ACTIVE_MATRIX_EVENTS, RouteStep, WebBridge, diagnostic_failure, replay_step,
)
from verify_np560_toolbar_frames import expected_from_package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--boot-timeout", type=float, default=150)
    parser.add_argument("--mode", choices=("reset", "set-off", "read-off"),
                        default="reset")
    parser.add_argument("--allow-input-and-reset", action="store_true",
                        help="Confirm the URL is an isolated disposable session")
    args = parser.parse_args()
    if not args.allow_input_and_reset or args.boot_timeout <= 0:
        parser.error("an isolated session and positive boot timeout are required")
    args.output.mkdir(parents=True, exist_ok=False)
    web = WebBridge(args.url, 10)
    expected, provenance = expected_from_package(args.package)
    report = {
        "schema": "np560-native-settings-reset-v1", "passed": False,
        "mode": args.mode,
        "scope": {
            "reset": "native sound setting across system_reset; not process restart",
            "set-off": "native confirmation only; caller must save and close",
            "read-off": "native cold-boot readback only; caller must prove saved input identity",
        }[args.mode],
        "host_guest_memory_writes": 0,
        "package": provenance, "steps": [], "observations": {},
    }

    def capture(name: str) -> tuple[dict, int]:
        state = web.get_json("/api/state")
        report["nand_save_enabled"] = state.get("nand_save_enabled")
        save_snapshot(args.output, name, state)
        memory = web.get_json("/api/state?source=memory&base=0x50b830&size=0x80")
        data = base64.b64decode(memory["frame"], validate=True)
        if len(data) != 128:
            raise ValueError("incomplete native configuration snapshot")
        (args.output / f"{name}-config.bin").write_bytes(data)
        value = int.from_bytes(data[0x4A:0x4C], "little")
        report["observations"][name] = {
            "sound_off": value, "nand_state": state["nand_state"],
            "native_writers": [line for line in state["registers"].splitlines()
                               if line.startswith(("RESOURCE_PERSIST_",
                                                   "NPE_TRANSITION_GATE="))],
        }
        print(f"{name}: sound_off={value}", flush=True)
        failure = diagnostic_failure(state["registers"])
        if failure:
            raise RuntimeError(failure)
        if not re.search(r"\bERROR=0\b", state["nand_state"]):
            raise RuntimeError("NAND reports an error")
        return state, value

    def desktop(name: str) -> None:
        deadline = time.monotonic() + args.boot_timeout
        stable = 0
        while time.monotonic() < deadline:
            state = web.get_json("/api/state")
            failure = diagnostic_failure(state["registers"])
            if failure:
                save_snapshot(args.output, name + "-fault", state)
                raise RuntimeError(failure)
            result = assess(state, expected[1])
            stable = stable + 1 if result["passed"] else 0
            if stable >= 3:
                save_snapshot(args.output, name, state)
                report["observations"][name] = result
                print(f"{name}: original learning toolbar stable", flush=True)
                return
            time.sleep(0.5)
        save_snapshot(args.output, name + "-timeout", state)
        raise TimeoutError("original cold desktop did not become stable")

    def key(label: str, index: int) -> None:
        step = replay_step(web, RouteStep(label, index, ACTIVE_MATRIX_EVENTS[index]),
                           press_timeout=3, release_timeout=8, poll_interval=0.02,
                           settle=1, pulse_duration=0.15)
        report["steps"].append(step)
        capture(label)

    def open_effect(prefix: str) -> None:
        for number in range(4):
            key(f"{prefix}-right-{number + 1}", 29)
        key(prefix + "-speech-down", 37)
        key(prefix + "-speech-open", 53)
        for number in range(4):
            key(f"{prefix}-effect-down-{number + 1}", 37)
        key(prefix + "-effect-open", 53)

    try:
        report["health_before"] = web.get_json("/api/health")
        if not report["health_before"].get("qemu_alive"):
            raise RuntimeError("QEMU is not alive")
        desktop("00-cold-desktop")
        _, initial = capture("01-initial-setting")
        if args.mode == "read-off":
            if initial != 1:
                raise RuntimeError("cold boot lost the saved native sound setting")
            open_effect("09-readback")
            _, displayed = capture("10-native-readback")
            if displayed != 1:
                raise RuntimeError("reopening the native editor lost the setting")
            report["passed"] = True
            return 0
        if initial != 0:
            raise RuntimeError("expected the unmodified sound-on baseline")
        open_effect("02-select")
        before, _ = capture("03-before-change")
        key("04-select-off", 37)
        key("05-confirm-off", 53)
        after, selected = capture("06-after-confirm")
        if selected != 1:
            raise RuntimeError("native confirmation did not select sound off")
        count = lambda state: int(re.search(
            r"\bPROGRAMS=(\d+)", state["nand_state"]).group(1))
        report["native_program_delta"] = count(after) - count(before)
        if report["native_program_delta"] <= 0:
            raise RuntimeError("native confirmation did not program NAND")
        if args.mode == "set-off":
            report["passed"] = True
            return 0
        web.post_json("/api/control", {"action": "reset"})
        desktop("07-reset-desktop")
        _, restored = capture("08-after-reset")
        if restored != 1:
            raise RuntimeError("system_reset lost the saved native sound setting")
        open_effect("09-readback")
        _, displayed = capture("10-native-readback")
        if displayed != 1:
            raise RuntimeError("reopening the native editor lost the setting")
        report["passed"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        print(report["error"], flush=True)
        try:
            capture("failure")
        except Exception as capture_error:
            report["capture_error"] = str(capture_error)
    finally:
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
