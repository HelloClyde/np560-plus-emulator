#!/usr/bin/env python3
"""Inspect an isolated NP560+ MP3 route without modifying the user's NAND."""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from web.np560_web import Emulator


def mp3_state(emulator: Emulator) -> dict:
    return json.loads(emulator.qmp.execute("qom-get", {
        "path": "/machine", "property": "rom-mp3-hle-state",
    }))


def audio_state(emulator: Emulator) -> dict:
    packet = emulator.audio()
    pcm = base64.b64decode(packet["pcm"])
    values = (int.from_bytes(pcm[i:i + 2], "little", signed=True)
              for i in range(0, len(pcm), 2))
    peak = max((abs(value) for value in values), default=0)
    return {
        "enabled": packet.get("enabled"),
        "first_frame": packet["first_frame"],
        "next_frame": packet["next_frame"],
        "peak": peak,
    }


def ram_probe(emulator: Emulator, workspace: int | None) -> dict:
    def read(address: int, size: int) -> bytes:
        return base64.b64decode(emulator.snapshot("data", address, size,
                                                 diagnostics=False)["frame"])

    volume = int.from_bytes(read(0x4a64, 2), "little")
    flags = int.from_bytes(read(0xf014, 2), "little")
    result = {"volume_word": volume, "current_level": volume >> 8,
              "target_level": volume & 0xff, "f014": flags,
              "mute_bit": bool(flags & 0x80)}
    if workspace:
        pcm = read(workspace + 0x5700, 2304)
        result["decoded_peak"] = max((abs(int.from_bytes(pcm[i:i + 2],
                              "little", signed=True)) for i in range(0, len(pcm), 2)),
                              default=0)
    return result


def wait_for_pulse(emulator: Emulator, timeout: float = 8.0) -> int:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        index = emulator.qmp.execute("qom-get", {
            "path": "/machine", "property": "key-matrix-pulse-index",
        })
        if int(index) == 64:
            return 64
        time.sleep(0.1)
    return int(index)


def wait_for_menu(emulator: Emulator, timeout: float = 180.0) -> dict:
    end = time.monotonic() + timeout
    last = {}
    while time.monotonic() < end:
        last = emulator.diagnostics()
        match = re.search(r"MATRIX_READS:(\d+)", last["registers"])
        reads = int(match.group(1)) if match else 0
        if reads >= 500:
            return last
        time.sleep(2)
    return last


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--soc-rom", type=Path, required=True)
    parser.add_argument("--nand-checkpoint", type=Path, required=True)
    parser.add_argument("--nand-journal", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    journal_copy = None
    if args.nand_journal:
        journal_copy = args.output.parent / "diagnostic-device.npj"
        shutil.copy2(args.nand_journal, journal_copy)
    report = {"schema": "np560-mp3-silence-diagnostic-v1", "steps": []}
    emulator = Emulator(
        qemu=args.qemu, firmware=args.firmware, soc_rom=args.soc_rom,
        nand_checkpoint=args.nand_checkpoint, boot_mode="firmware-vma03",
        soc_rom_skeleton=True, rom_mp3_hle_base=138790,
        rom_mp3_arena_image=93952, icount_shift=0, icount_align=True,
        nand_journal=journal_copy, start_paused=True,
    )
    try:
        emulator.qmp.execute("qom-set", {"path": "/machine",
                              "property": "instruction-clock", "value": True})
        emulator.qmp.execute("qom-set", {"path": "/machine",
                              "property": "control-observers-minimal", "value": True})
        emulator.qmp.execute("cont")
        boot_diagnostics = wait_for_menu(emulator)
        report["boot_wait"] = boot_diagnostics
        for name, index, settle in (
            ("boot", None, 0),
            ("mp3_button", 35, 1),
            ("open", 60, 1),
            ("select_file", 37, 0.5),
            ("confirm", 53, 1),
        ):
            if index is not None:
                try:
                    emulator.pulse_matrix(index)
                except Exception as exc:
                    report["error"] = f"{name}: {exc}"
                    break
                time.sleep(settle)
                pulse_state = wait_for_pulse(emulator)
                if pulse_state != 64:
                    report["error"] = f"{name}: pulse {pulse_state} unconsumed"
            step = {"name": name, "hle": mp3_state(emulator),
                    "audio": audio_state(emulator),
                    "diagnostics": emulator.diagnostics()}
            events = step["hle"].get("lifecycle_events", [])
            workspace = events[-1]["workspace"] if events else None
            step["ram"] = ram_probe(emulator, workspace)
            if index is not None:
                step["pulse_state"] = pulse_state
            report["steps"].append(step)
            print(name, "frames", step["hle"].get("frames"),
                  "codec", step["hle"].get("codec_results"),
                  "peak", step["audio"]["peak"], flush=True)
            if "error" in report:
                break
        for index in range(25 if "error" not in report else 0):
            hle = mp3_state(emulator)
            events = hle.get("lifecycle_events", [])
            workspace = events[-1]["workspace"] if events else None
            report["steps"].append({
                "name": f"playback_{index}",
                "hle": hle, "audio": audio_state(emulator),
                "ram": ram_probe(emulator, workspace),
            })
            time.sleep(0.1)
        if "error" not in report:
            for index in range(7):
                emulator.pulse_matrix(61)
                pulse_state = wait_for_pulse(emulator)
                if pulse_state != 64:
                    report["error"] = f"volume_up_{index}: pulse unconsumed"
                    break
                time.sleep(0.15)
            for index in range(30 if "error" not in report else 0):
                hle = mp3_state(emulator)
                events = hle.get("lifecycle_events", [])
                workspace = events[-1]["workspace"] if events else None
                report["steps"].append({
                    "name": f"volume_playback_{index}",
                    "hle": hle, "audio": audio_state(emulator),
                    "ram": ram_probe(emulator, workspace),
                })
                time.sleep(0.1)
    finally:
        emulator.close()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
