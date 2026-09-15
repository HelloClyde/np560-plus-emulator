#!/usr/bin/env python3
"""One native Hero save/load route, with separate isolated writer and reader.

The caller owns the processes and NAND save-on-exit. This client only presses
physical switches and reads diagnostic/LCD state. Its reports do not by
themselves prove that the writer terminated or its output was used by the reader.
Only the original sound-off configuration is currently supported; no gate writes
or audio bypasses are performed here. This is not full NPE compatibility testing.
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

POSITION_FIELDS = (
    "current_x", "current_y", "current_map_index", "current_offset_x",
    "current_offset_y", "current_direction", "current_scroll",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--phase", choices=("writer", "reader"), required=True)
    parser.add_argument("--writer-report", type=Path)
    parser.add_argument("--expected-nand-sha256")
    parser.add_argument("--allow-physical-input", action="store_true")
    args = parser.parse_args()
    if not args.allow_physical_input:
        parser.error("only use this probe on an isolated disposable instance")
    writer = None
    if args.phase == "reader":
        if not args.writer_report or not args.expected_nand_sha256:
            parser.error("reader requires the completed writer report and saved NAND SHA-256")
        writer = json.loads(args.writer_report.read_text(encoding="utf-8"))
        if not writer.get("passed") or writer.get("phase") != "writer":
            parser.error("writer did not complete the native save operation")
    args.output.mkdir(parents=True, exist_ok=False)
    web = WebBridge(args.url, 10)
    toolbar, provenance = expected_from_package(args.package)
    report = {
        "schema": "np560-native-game-save-v1", "phase": args.phase,
        "passed": False, "host_guest_memory_writes": 0,
        "scope": "Hero first slot, sound-off; caller verifies process lifecycle and disk identity",
        "package": provenance, "steps": [], "observations": {},
    }

    def state() -> dict:
        value = web.get_json("/api/state")
        fault = diagnostic_failure(value["registers"])
        if fault:
            raise RuntimeError(fault)
        if not re.search(r"\bERROR=0\b", value["nand_state"]):
            raise RuntimeError("NAND reports an error")
        return value

    def capture(name: str) -> dict:
        value = state()
        save_snapshot(args.output, name, value)
        status = web.get_json("/api/key-status")
        observation = {
            "position": {field: int(status[field]) for field in POSITION_FIELDS},
            "nand_state": value["nand_state"],
            "nand_save_enabled": value["nand_save_enabled"],
        }
        report["observations"][name] = observation
        print(name, observation["position"], flush=True)
        return observation

    def wait_for(name: str, predicate, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        stable = 0
        while time.monotonic() < deadline:
            value = state()
            stable = stable + 1 if predicate(value) else 0
            if stable >= 3:
                capture(name)
                return
            time.sleep(0.5)
        raise TimeoutError(name + " did not become ready")

    def mode_ready(mode: int):
        return lambda value: (
            f"NPE_GAME_CONTROL=LIVE:m{mode:04x}/" in value["registers"]
            and "PC=00:1018 " in value["registers"])

    def key(name: str, index: int, settle: float = 2) -> dict:
        step = replay_step(web, RouteStep(name, index, ACTIVE_MATRIX_EVENTS[index]),
                           press_timeout=3, release_timeout=8, poll_interval=0.02,
                           settle=settle, pulse_duration=0.15)
        report["steps"].append(step)
        return capture(name)

    def programs(observation: dict) -> int:
        return int(re.search(r"\bPROGRAMS=(\d+)", observation["nand_state"]).group(1))

    try:
        health = report["health"] = web.get_json("/api/health")
        if not health.get("qemu_alive"):
            raise RuntimeError("QEMU is not alive")
        if writer:
            if health["qemu_pid"] == writer["health"]["qemu_pid"]:
                raise RuntimeError("reader must be a new QEMU process")
            for component in ("qemu", "firmware", "soc_rom"):
                if (health["artifacts"][component]["sha256"] !=
                        writer["health"]["artifacts"][component]["sha256"]):
                    raise RuntimeError(component + " changed between writer and reader")
            if (health["artifacts"]["nand_checkpoint"]["sha256"] !=
                    args.expected_nand_sha256.lower()):
                raise RuntimeError("reader is not using the expected saved NAND")
        wait_for("00-desktop", lambda value: assess(value, toolbar[1])["passed"], 150)
        memory = web.get_json("/api/state?source=memory&base=0x50b87a&size=2")
        sound_off = int.from_bytes(base64.b64decode(memory["frame"]), "little")
        report["sound_off"] = sound_off
        if sound_off != 1:
            raise RuntimeError("this route requires the native sound-off setting")
        for name, index in (("01-start", 55), ("02-entertainment", 53),
                            ("03-game-world", 37), ("04-npe-list", 53)):
            key(name, index, settle=4 if index == 53 else 2)
        key("05-select-hero", 53)
        wait_for("06-title", mode_ready(7), 40)
        if args.phase == "writer":
            key("07-new-journey", 53)
            wait_for("08-initial-scene", mode_ready(1), 40)
            initial = report["observations"]["08-initial-scene"]["position"]
            if (initial["current_x"], initial["current_y"]) != (7, 1):
                raise RuntimeError("unexpected initial Hero position")
            key("09-move-down", 37)
            moved = key("10-move-right", 29)["position"]
            if (moved["current_x"], moved["current_y"]) != (8, 2):
                raise RuntimeError("native input did not reach the non-default save position")
            report["saved_position"] = moved
            key("11-f4-game-menu", 4)
            for number in range(3):
                key(f"12-system-down-{number + 1}", 37)
            key("13-system", 53)
            key("14-select-save", 37)
            key("15-open-save", 53)
            before = capture("16-before-save")
            if not before["nand_save_enabled"]:
                raise RuntimeError("writer must have an explicit NAND save-on-exit output")
            key("17-save-slot1", 53)
            wait_for("18-saved-scene", mode_ready(1), 40)
            after = report["observations"]["18-saved-scene"]
            report["native_program_delta"] = programs(after) - programs(before)
            if report["native_program_delta"] <= 0 or after["position"] != moved:
                raise RuntimeError("native save did not program NAND or changed the saved position")
        else:
            # From the verified title choose the original continue-game path;
            # never start a new journey before loading the saved progress.
            key("07-select-continue", 37)
            key("08-open-continue", 53)
            key("09-read-slot1", 53)
            wait_for("10-restored-scene", mode_ready(1), 40)
            restored = report["observations"]["10-restored-scene"]["position"]
            report["expected_position"] = writer["saved_position"]
            if restored != writer["saved_position"]:
                raise RuntimeError("cold native load did not restore the recorded save state")
        report["passed"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        print(report["error"], flush=True)
        try:
            save_snapshot(args.output, "failure", web.get_json("/api/state"))
        except Exception as capture_error:
            report["capture_error"] = str(capture_error)
    finally:
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
