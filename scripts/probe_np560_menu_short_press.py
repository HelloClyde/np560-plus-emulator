#!/usr/bin/env python3
"""Reproduce native menu input with wall-clock physical holds in an owned QEMU.

No browser, guest-state injection, single-scan pulse or NAND persistence.
The first divergence is retained, not repaired. A passing run only covers this
bounded route and does not establish factory timing or general menu stability.
"""
from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path

from probe_np560_checkpoint_boot import assess, save_snapshot
from probe_np560_matrix_route import ACTIVE_MATRIX_EVENTS
from verify_np560_toolbar_frames import compare, expected_from_package
from web.np560_web import Emulator, RunJournal, artifact_identity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("qemu", "firmware", "soc-rom", "nand-checkpoint", "package", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--hold", type=float, default=0.12)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--boot-timeout", type=float, default=180)
    args = parser.parse_args()
    if args.hold <= 0 or args.cycles <= 0 or args.boot_timeout <= 0:
        parser.error("hold, cycles and boot-timeout must be positive")
    # Match the current browser and original event table, not historical aliases.
    assert ACTIVE_MATRIX_EVENTS[29] == 0x81
    assert ACTIVE_MATRIX_EVENTS[45] == 0x80
    args.output.mkdir(parents=True, exist_ok=False)
    paths = {name: getattr(args, name) for name in
             ("qemu", "firmware", "soc_rom", "nand_checkpoint")}
    identities = {}
    for name, path in {**paths, "package": args.package}.items():
        size, digest = artifact_identity(path)
        identities[name] = {"path": str(path.resolve()), "size": size, "sha256": digest}
    expected, provenance = expected_from_package(args.package)
    report = {"scope": __doc__, "artifacts": identities, "package": provenance,
              "hold_seconds": args.hold, "host_guest_memory_writes": 0,
              "nand_save_enabled": False, "passed": False, "steps": []}
    journal = RunJournal(args.output / "process", kind="native-short-press",
                         artifacts=identities)
    emulator = None
    try:
        emulator = Emulator(**paths, soc_rom_skeleton=True,
                            boot_mode="firmware-vma03", start_paused=True,
                            journal=journal)
        emulator.control("resume")
        started = time.monotonic()
        next_message = 0
        stable = 0
        while time.monotonic() - started < args.boot_timeout:
            snapshot = emulator.snapshot("lcd", 0, 0)
            result = assess(snapshot, expected[1])
            elapsed = time.monotonic() - started
            stable = stable + 1 if result["passed"] else 0
            if elapsed >= next_message:
                print(f"boot {elapsed:.1f}s pixels={result['toolbar']['mismatch_pixels']}",
                      flush=True)
                next_message = elapsed + 20
            if stable >= 3:
                break
            time.sleep(1)
        if stable < 3:
            raise RuntimeError("cold boot did not reach the original learning toolbar")
        save_snapshot(args.output, "before", snapshot)
        report["boot_elapsed"] = time.monotonic() - started
        category = 1
        counters = ("candidates", "maps", "acknowledgements", "modal_acknowledgements")
        for number, index in enumerate(([29] * 4 + [45] * 4) * args.cycles, 1):
            before = emulator.key_status()
            started = time.monotonic()
            low, high = (1 << index, 0) if index < 32 else (0, 1 << (index - 32))
            emulator.set_key(0, 0, low, high)
            made = time.monotonic()
            try:
                time.sleep(args.hold)
            finally:
                emulator.set_key(0, 0, 0, 0)
            released = time.monotonic()
            timeline = []
            previous = None
            while time.monotonic() - released < 4:
                status = emulator.key_status()
                signature = tuple(status[key] for key in counters)
                if signature != previous:
                    timeline.append({"elapsed": time.monotonic() - started,
                                     "counters": dict(zip(counters, signature)),
                                     "rearmed": status["matrix_rearmed"]})
                    previous = signature
                if status["faulted"]:
                    break
                if status["matrix_rearmed"] and time.monotonic() - released > 0.8:
                    break
                time.sleep(0.02)
            category += 1 if index == 29 else -1
            snapshot = emulator.snapshot("lcd", 0, 0)
            pixels = compare(base64.b64decode(snapshot["frame"]), expected[category])
            delta = {key: status[key] - before[key] for key in counters}
            step = {"number": number, "matrix": index, "expected_category": category,
                    "before": before, "after": status, "delta": delta,
                    "hold_wall_seconds": released - made,
                    "timeline": timeline, "toolbar": pixels}
            report["steps"].append(step)
            print(f"step {number} M{index} hold={released - made:.3f} "
                  f"delta={delta} pixels={pixels['mismatch_pixels']}", flush=True)
            if (status["faulted"] or delta["maps"] != 1 or
                    delta["acknowledgements"] != 1 or not pixels["passed"]):
                emulator.control("pause")
                save_snapshot(args.output, "first-divergence",
                              emulator.snapshot("lcd", 0, 0))
                report["diverged_at"] = number
                break
        else:
            report["passed"] = True
        save_snapshot(args.output, "final", emulator.snapshot("lcd", 0, 0))
    except Exception as error:
        report["error"] = repr(error)
        print(f"ERROR {error!r}", flush=True)
    finally:
        if emulator is not None:
            emulator.close()
            report["qemu_returncode"] = emulator.process.returncode
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"passed={report['passed']} report={args.output / 'report.json'}", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
