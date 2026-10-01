#!/usr/bin/env python3
"""Read-only per-process CPU and device-audio timing for an isolated Web run.

Run this inside WSL beside a browser audio probe. The lifecycle status file
selects the exact three child processes; no guest RAM or controls are changed.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from urllib.parse import urlparse
from urllib.request import urlopen

from np560_host_time import parse_stat


def process_time(pid: int) -> dict:
    record = parse_stat(Path(f"/proc/{pid}/stat").read_text())
    if record["tid"] != pid:
        raise ValueError(f"process identity mismatch for {pid}")
    return record


def audio_frame(root: str) -> dict:
    with urlopen(root + "api/audio", timeout=5) as response:
        payload = json.load(response)
    return {
        "stream_id": payload["stream_id"],
        "generation": payload["generation"],
        "next_frame": payload["next_frame"],
    }


def sample(root: str, pids: dict) -> dict:
    processes = {name: process_time(pid) for name, pid in pids.items()}
    audio = audio_frame(root)
    return {"time": time.monotonic(), "processes": processes, "audio": audio}


def delta(before: dict, after: dict, ticks_per_second: int = None) -> dict:
    wall = after["time"] - before["time"]
    if ticks_per_second is None:
        ticks_per_second = os.sysconf("SC_CLK_TCK")
    process_cpu = {}
    for name in before["processes"]:
        first = before["processes"][name]
        last = after["processes"][name]
        if first["start_ticks"] != last["start_ticks"]:
            raise ValueError(f"{name} process was replaced during observation")
        ticks = (last["user_ticks"] + last["system_ticks"] -
                 first["user_ticks"] - first["system_ticks"])
        if ticks < 0:
            raise ValueError(f"{name} process CPU time regressed")
        process_cpu[name] = round(ticks / ticks_per_second, 3)
    first_audio, last_audio = before["audio"], after["audio"]
    if (first_audio["stream_id"], first_audio["generation"]) != (
            last_audio["stream_id"], last_audio["generation"]):
        raise ValueError("device audio stream changed during observation")
    frames = last_audio["next_frame"] - first_audio["next_frame"]
    if frames < 0:
        raise ValueError("device audio frame counter regressed")
    return {
        "wall_seconds": round(wall, 3),
        "device_frames": frames,
        "device_speed_ratio": round(frames / 48000 / wall, 3),
        "cpu_seconds": process_cpu,
        "cpu_wall_ratio": {name: round(cpu / wall, 3)
                           for name, cpu in process_cpu.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="isolated loopback Web URL")
    parser.add_argument("--status-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=15)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    url = urlparse(args.root)
    if url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost"):
        parser.error("root must be a loopback HTTP URL")
    if not 1 <= args.seconds <= 120 or not 0.2 <= args.interval <= 5:
        parser.error("seconds must be 1..120 and interval 0.2..5")
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    status = json.loads(args.status_json.read_text(encoding="utf-8"))
    if status.get("phase") != "serving" or status.get("port") != url.port:
        parser.error("status does not identify the serving URL")
    pids = {name: int(status[key]) for name, key in (
        ("qemu", "qemu_pid"), ("codec", "codec_pid"),
        ("bridge", "bridge_pid"))}
    root = args.root.rstrip("/") + "/"
    first = sample(root, pids)
    previous = first
    windows = []
    deadline = first["time"] + args.seconds
    while previous["time"] < deadline:
        time.sleep(min(args.interval, max(0, deadline - previous["time"])))
        current = sample(root, pids)
        windows.append(delta(previous, current))
        previous = current
    report = {
        "schema": "np560-audio-cpu-window-v1",
        "root": root, "run_id": status["run_id"], "pids": pids,
        "interval_seconds": args.interval,
        "aggregate": delta(first, previous), "windows": windows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["aggregate"], indent=2))


if __name__ == "__main__":
    main()
