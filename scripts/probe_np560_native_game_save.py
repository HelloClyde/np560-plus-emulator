#!/usr/bin/env python3
"""Native Hero save/load, cancel and existing-slot overwrite routes.

The caller owns the processes and NAND save-on-exit. This client only presses
physical switches and reads diagnostic/LCD state. Its reports do not by
themselves prove that the writer terminated or its output was used by the reader.
Only the original sound-off configuration is currently supported; no gate writes
or audio bypasses are performed here. This is not full NPE compatibility testing.
The overwrite phase modifies slot one on the caller's disposable medium and
checks same-process reload only. A separate cold reader is still required.
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
    parser.add_argument("--phase", choices=("writer", "reader", "cancel", "overwrite"), required=True)
    parser.add_argument("--writer-report", type=Path)
    parser.add_argument("--expected-nand-sha256")
    parser.add_argument("--journal-reader", action="store_true",
                        help="Cold reader replays the writer's NAND journal over the unchanged base NAND")
    parser.add_argument("--allow-physical-input", action="store_true")
    parser.add_argument("--pulse-duration", type=float, default=0.15,
                        help="Physical hold in seconds; 0 releases at the first original candidate, never injects an event")
    parser.add_argument("--start-at-title", action="store_true",
                        help="Resume an owned instance already at the Hero title; no state injection")
    args = parser.parse_args()
    if not 0 <= args.pulse_duration <= 1:
        parser.error("pulse duration must be between zero and one second")
    if not args.allow_physical_input:
        parser.error("only use this probe on an isolated disposable instance")
    writer = None
    if args.phase == "reader":
        if not args.writer_report or not args.expected_nand_sha256:
            parser.error("reader requires the completed writer report and saved NAND SHA-256")
        writer = json.loads(args.writer_report.read_text(encoding="utf-8"))
        expected_phase = "overwrite" if args.journal_reader else "writer"
        if not writer.get("passed") or writer.get("phase") != expected_phase:
            parser.error("writer did not complete the native save operation")
    elif args.journal_reader:
        parser.error("--journal-reader requires --phase reader")
    args.output.mkdir(parents=True, exist_ok=False)
    web = WebBridge(args.url, 10)
    toolbar, provenance = expected_from_package(args.package)
    report = {
        "schema": "np560-native-game-save-v1", "phase": args.phase,
        "passed": False, "host_guest_memory_writes": 0,
        "scope": "Hero first slot, sound-off; caller verifies process lifecycle and disk identity",
        "package": provenance, "steps": [], "observations": {},
        "pulse_duration": args.pulse_duration,
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
            "nand_journal_state": value.get("nand_journal_state"),
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
        # A running foreground may poll or render away from the old idle PC.
        # wait_for requires three consecutive mode observations; the captured
        # LCD still supplies the separate visual evidence for the transition.
        return lambda value: f"NPE_GAME_CONTROL=LIVE:m{mode:04x}/" in value["registers"]

    def key(name: str, index: int, settle: float = 2) -> dict:
        step = replay_step(web, RouteStep(name, index, ACTIVE_MATRIX_EVENTS[index]),
                           press_timeout=3, release_timeout=8, poll_interval=0.02,
                           settle=settle, pulse_duration=args.pulse_duration)
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
            if args.journal_reader:
                if (writer["health"]["artifacts"]["nand_checkpoint"]["sha256"] !=
                        args.expected_nand_sha256.lower()):
                    raise RuntimeError("writer and reader must use the same base NAND")

                def journal_path(run: dict) -> str:
                    machine = run["command"][run["command"].index("-M") + 1]
                    match = re.search(r"(?:^|,)nand-journal=([^,]+)", machine)
                    if not match:
                        raise RuntimeError("NAND journal is missing from the QEMU command")
                    return match.group(1)

                report["nand_journal_path"] = journal_path(health)
                if report["nand_journal_path"] != journal_path(writer["health"]):
                    raise RuntimeError("reader is not replaying the writer's NAND journal")
                journal = state().get("nand_journal_state", "")
                report["cold_journal_state"] = journal
                replayed = re.search(r"\bREPLAYED=(\d+)\b", journal)
                if (not journal.startswith("durable ") or not replayed or
                        int(replayed.group(1)) <= 0 or "TORN_BYTES=0" not in journal):
                    raise RuntimeError("reader did not replay a clean durable NAND journal")
        if not args.start_at_title:
            wait_for("00-desktop", lambda value: assess(value, toolbar[1])["passed"], 150)
        report["start_at_title"] = args.start_at_title
        memory = web.get_json("/api/state?source=memory&base=0x50b87a&size=2")
        sound_off = int.from_bytes(base64.b64decode(memory["frame"]), "little")
        report["sound_off"] = sound_off
        if sound_off != 1:
            raise RuntimeError("this route requires the native sound-off setting")
        if not args.start_at_title:
            for name, index in (("01-start", 55), ("02-entertainment", 53),
                                ("03-game-world", 37), ("04-npe-list", 53)):
                key(name, index, settle=4 if index == 53 else 2)
            key("05-select-hero", 53)
        wait_for("06-title", mode_ready(7), 40)
        if args.phase == "overwrite":
            def slots(prefix: str, save: bool) -> None:
                key(prefix + "-menu", 4)
                for number in range(3):
                    key(f"{prefix}-system-down-{number}", 37)
                key(prefix + "-system", 53)
                if save:
                    key(prefix + "-select-save", 37)
                key(prefix + "-slots", 53)

            key("20-continue", 37)
            key("21-load-slots", 53)
            key("22-load-existing-slot", 53)
            wait_for("23-original-scene", mode_ready(1), 40)
            original = report["observations"]["23-original-scene"]["position"]
            moved = key("24-move-right", 29)["position"]
            if moved["current_x"] != original["current_x"] + 1:
                raise RuntimeError("overwrite requires a distinct reachable save position")
            slots("25-save", True)
            before = capture("26-before-cancel")
            key("27-cancel-f4", 4)
            wait_for("28-cancelled-scene", mode_ready(1), 40)
            after = report["observations"]["28-cancelled-scene"]
            for field in ("PROGRAMS", "ERASES", "COPIES"):
                if (re.search(rf"\b{field}=(\d+)", before["nand_state"]).group(1)
                        != re.search(rf"\b{field}=(\d+)", after["nand_state"]).group(1)):
                    raise RuntimeError("cancel mutated NAND: " + field)
            slots("29-reload", False)
            key("30-read-old-slot", 53)
            wait_for("31-old-preserved", mode_ready(1), 40)
            if report["observations"]["31-old-preserved"]["position"] != original:
                raise RuntimeError("cancel did not preserve the old saved position")
            target = key("32-move-right-again", 29)["position"]
            if target != moved:
                raise RuntimeError("overwrite target changed unexpectedly")
            slots("33-overwrite", True)
            before = capture("34-before-overwrite")
            key("35-confirm-existing-slot", 53)
            wait_for("36-overwritten-scene", mode_ready(1), 40)
            after = report["observations"]["36-overwritten-scene"]
            report["native_program_delta"] = programs(after) - programs(before)
            if report["native_program_delta"] <= 0:
                raise RuntimeError("overwrite did not program NAND")
            changed = key("37-move-away", 37)["position"]
            if changed == target:
                raise RuntimeError("must change live state before verifying reload")
            slots("38-reload-new", False)
            key("39-read-overwritten-slot", 53)
            wait_for("40-new-restored", mode_ready(1), 40)
            if report["observations"]["40-new-restored"]["position"] != target:
                raise RuntimeError("overwrite reload did not restore the new position")
            report.update(original_position=original, saved_position=target, passed=True,
                          scope="Hero existing first slot: cancel preserves old position; overwrite and native reload in one process; not cold persistence")
            return 0
        if args.phase in ("writer", "cancel"):
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
            if args.phase == "cancel":
                # This game's modal save menu consumes F4/0x8E to dismiss;
                # Esc/0x84 is delivered but does not cancel it.
                key("17-cancel-slot-f4", 4)
                wait_for("18-after-cancel", mode_ready(1), 40)
                after = report["observations"]["18-after-cancel"]
                report["native_program_delta"] = programs(after) - programs(before)
                report["native_mutation_deltas"] = {
                    field: int(re.search(rf"\b{field}=(\d+)", after["nand_state"]).group(1))
                    - int(re.search(rf"\b{field}=(\d+)", before["nand_state"]).group(1))
                    for field in ("PROGRAMS", "ERASES", "COPIES")
                }
                if any(report["native_mutation_deltas"].values()):
                    raise RuntimeError("cancel mutated NAND")
                if report["native_program_delta"] != 0 or after["position"] != moved:
                    raise RuntimeError("cancel programmed NAND or changed scene position")
                report["scope"] = (
                    "Hero F4 save-slot cancel: scene mode restored, unchanged NAND program count and position; "
                    "LCD transition requires separate visual inspection")
                report["passed"] = True
                return 0
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
        if hasattr(error, "input_evidence"):
            report["input_failure"] = error.input_evidence
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
