#!/usr/bin/env python3
"""Sample the vCPU of an explicitly owned, live NP560 Web run.

Read-only host CPU-clock sampling. The caller supplies this run's lifecycle
record, not an arbitrary PID. Use only with an isolated run you launched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from np560_host_time import read_thread_time
from probe_np560_perf_samples import UserIPSampler


PROJECT = Path(__file__).resolve().parents[1]


def select_vcpu_thread(pid: int) -> tuple[int, dict]:
    tasks = sorted(int(path.name) for path in Path(f"/proc/{pid}/task").iterdir())
    if len(tasks) < 2:
        raise RuntimeError("QEMU has no separate vCPU thread")
    before = {tid: read_thread_time(pid, tid) for tid in tasks}
    time.sleep(0.25)
    after = {tid: read_thread_time(pid, tid) for tid in tasks}
    deltas = {
        tid: after[tid]["user_ticks"] + after[tid]["system_ticks"] -
             before[tid]["user_ticks"] - before[tid]["system_ticks"]
        for tid in tasks
    }
    ranked = sorted(deltas, key=deltas.get, reverse=True)
    if deltas[ranked[0]] < 5 or deltas[ranked[0]] < 2 * max(1, deltas[ranked[1]]):
        raise RuntimeError(f"vCPU thread is not unambiguous: {deltas}")
    return ranked[0], {"ticks": deltas, "start_ticks": before[ranked[0]]["start_ticks"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, choices=range(1, 31), default=10)
    args = parser.parse_args()
    status_path = args.status_json.resolve(strict=True)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    run_directory = Path(status["directory"]).resolve(strict=True)
    if status_path != run_directory / "status.json":
        raise ValueError("status file and run directory disagree")
    try:
        run_directory.relative_to(PROJECT / "tmp")
    except ValueError as error:
        raise ValueError("live perf sampling requires an isolated tmp run") from error
    if status["phase"] != "serving" or status["host"] != "127.0.0.1":
        raise ValueError("run is not a serving loopback isolation")
    pid = int(status["qemu_pid"])
    qemu = Path(status["artifacts"]["qemu"]["path"]).resolve(strict=True)
    digest = hashlib.sha256(qemu.read_bytes()).hexdigest()
    if digest != status["artifacts"]["qemu"]["sha256"]:
        raise ValueError("QEMU binary differs from lifecycle record")
    command = Path(f"/proc/{pid}/cmdline").read_bytes().rstrip(b"\0").decode().split("\0")
    if command != status["command"]:
        raise ValueError("live process command differs from lifecycle record")
    tid, selection = select_vcpu_thread(pid)
    before = read_thread_time(pid, tid)
    if before["start_ticks"] != selection["start_ticks"]:
        raise RuntimeError("selected vCPU thread was replaced")
    sampler = UserIPSampler(tid)
    try:
        sampler.start()
        start = time.monotonic()
        time.sleep(args.seconds)
        elapsed = time.monotonic() - start
        samples = sampler.stop()
    finally:
        sampler.close()
    after = read_thread_time(pid, tid)
    if after["start_ticks"] != before["start_ticks"]:
        raise RuntimeError("vCPU thread was replaced during sampling")
    if not samples["samples"]:
        raise RuntimeError("perf returned no vCPU samples")
    if any(item["pid"] != pid or item["tid"] != tid or item["misc"] & 7 != 2
           for item in samples["samples"]):
        raise RuntimeError("perf returned a sample outside the selected user vCPU")
    report = {
        "qemu_sha256": digest,
        "run_id": status["run_id"],
        "qemu_pid": pid,
        "vcpu_tid": tid,
        "selection": selection,
        "elapsed_seconds": elapsed,
        "vcpu_cpu_seconds": (after["user_ticks"] + after["system_ticks"] -
                              before["user_ticks"] - before["system_ticks"]) /
                             os.sysconf("SC_CLK_TCK"),
        "scope": "Read-only CPU-clock user-IP samples; no inclusive stacks or guest timing claim",
        "maps": Path(f"/proc/{pid}/maps").read_text(),
        **samples,
    }
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ("samples", "maps")}, indent=2))
    print(f"samples={len(samples['samples'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
