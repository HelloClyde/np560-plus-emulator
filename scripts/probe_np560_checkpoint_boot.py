#!/usr/bin/env python3
"""Cold-boot an isolated NAND checkpoint without keys, patches or persistence.

Compare one explicitly selected toolbar with original UPD pixels, retaining
failure frames and lifecycle evidence. This is not an NPE/gameplay acceptance
test, nor a full guest-FTL readback test.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import struct
import time
import zlib
from pathlib import Path

from verify_np560_toolbar_frames import compare, expected_from_package
from web.np560_web import Emulator, RunJournal, artifact_identity

OFF, ON = (0xB7, 0xC8, 0xA1), (0x24, 0x31, 0x26)


def render_png(frame: bytes) -> bytes:
    """Render raw device pixels, using only the standard library on WSL."""
    if len(frame) != 240 * 120 or any(level > 31 for level in frame):
        raise ValueError("invalid gray5 frame")
    palette = [bytes(round(OFF[c] + (ON[c] - OFF[c]) * level / 31)
                     for c in range(3)) for level in range(32)]
    rows = []
    for y in range(120):
        row = b"\0" + b"".join(palette[level] * 3 for level in frame[y * 240:(y + 1) * 240])
        rows.extend((row,) * 3)

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data)))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 720, 360, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def save_snapshot(directory: Path, name: str, snapshot: dict) -> None:
    (directory / f"{name}.json").write_text(
        json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    frame = base64.b64decode(snapshot["frame"], validate=True)
    if len(frame) != 240 * 120 or snapshot["format"] != "gray5":
        raise ValueError("expected a 240x120 gray5 frame")
    (directory / f"{name}.gray5").write_bytes(frame)
    (directory / f"{name}.png").write_bytes(render_png(frame))


def assess(snapshot: dict, expected: bytes) -> dict:
    frame = base64.b64decode(snapshot["frame"], validate=True)
    result = compare(frame, expected)
    # Require the fields to be present, not just an absence of error text.
    checks = {field: f"{field}=none" in snapshot["registers"]
              for field in ("ROM_MISSING", "INVALID_CONTROL", "UNSUPPORTED")}
    checks["rom_hle_off"] = "ROM_HLE=off" in snapshot["registers"]
    checks["nand_error_zero"] = bool(re.search(
        r"\bERROR=0\b", snapshot["nand_state"]))
    return {"toolbar": result, "diagnostic_checks": checks,
            "passed": result["passed"] and all(checks.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("qemu", "firmware", "soc-rom", "nand-checkpoint", "package", "output"):
        parser.add_argument("--" + flag, type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--expected-category", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--soc-rom-skeleton", action="store_true",
                        help="Treat explicit 0F00 holes in reconstructed ROM as missing services")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    expected, provenance = expected_from_package(args.package)
    args.output.mkdir(parents=True, exist_ok=False)
    identities = {}
    for key in ("qemu", "firmware", "soc_rom", "nand_checkpoint", "package"):
        path = getattr(args, key)
        size, sha256 = artifact_identity(path)
        identities[key] = {"path": str(path.resolve()), "size": size, "sha256": sha256}
    journal = RunJournal(args.output / "process", kind="checkpoint-cold-boot",
                         artifacts=identities)
    report = {"schema": "np560-isolated-checkpoint-boot-v1", "passed": False,
              "artifacts": identities, "package_evidence": provenance,
              "scope": "zero-input cold boot, one toolbar; not full menu/game/FTL validation",
              "expected_category": args.expected_category, "injected_keys": 0,
              "soc_rom_skeleton": args.soc_rom_skeleton,
              "host_guest_memory_writes": 0, "nand_save_enabled": False, "samples": []}
    emulator = None
    started = time.monotonic()
    try:
        emulator = Emulator(qemu=args.qemu, firmware=args.firmware,
                            soc_rom=args.soc_rom, nand_checkpoint=args.nand_checkpoint,
                            soc_rom_skeleton=args.soc_rom_skeleton,
                            boot_mode="firmware-vma03", start_paused=True, journal=journal)
        emulator.qmp.execute("cont")
        stable = 0
        next_capture = 0
        while time.monotonic() - started < args.timeout:
            snapshot = emulator.snapshot("lcd", 0, 0)
            elapsed = time.monotonic() - started
            result = assess(snapshot, expected[args.expected_category])
            sample = {"elapsed": elapsed, "pc": snapshot["registers"].splitlines()[0],
                      **result}
            report["samples"].append(sample)
            stable = stable + 1 if result["passed"] else 0
            if elapsed >= next_capture:
                save_snapshot(args.output, f"at-{int(elapsed):03d}", snapshot)
                next_capture = elapsed + 15
                print(f"{elapsed:.1f}s {sample['pc']} toolbar mismatches="
                      f"{result['toolbar']['mismatch_pixels']}/5280", flush=True)
            if stable >= 3:
                report["passed"] = True
                break
            time.sleep(1)
        save_snapshot(args.output, "final", snapshot)
        report["elapsed"] = time.monotonic() - started
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        journal.record("boot_probe_failed", error=report["error"])
    finally:
        if emulator is not None:
            emulator.close()
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Passed={report['passed']}; report={args.output / 'report.json'}", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
