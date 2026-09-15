#!/usr/bin/env python3
"""Check ST7529 LI/CI output mapping with real guest MMIO and sparse pixels.

The guest writes RAM, changes DATSDR without rewriting the pixels, and reads
the original RAM addresses back. The host only observes RAM/LCD afterwards.
Fixed physical coordinates below use the existing NP560 COMSCN=1 wiring;
the controller direction rules come from ST7529 v1.8 pp.25-26,41-43.
"""
from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import hashlib
import json
from pathlib import Path

from test_np560_lcd_formats import command, read_bytes, setup, write_bytes
from test_np560_mac import run


# Logical column group, logical line, three pixel intensities.
# Column 84 is outside the 240-dot panel, but must become visible under CI.
GROUPS = [(0, 20, (1, 8, 21)), (79, 139, (7, 19, 2)),
          (84, 20, (25, 25, 25)), (5, 21, (31, 6, 9)),
          (0, 19, (30, 0, 0)), (84, 140, (0, 30, 0))]

# (physical x, physical y, index into GROUPS), independent of MPU window.
VISIBLE = {
    0: [(0, 119, 0), (237, 0, 1), (15, 118, 3)],
    1: [(0, 0, 0), (237, 119, 1), (15, 1, 3)],
    2: [(15, 0, 1), (0, 119, 2), (237, 118, 3)],
    3: [(15, 119, 1), (0, 0, 2), (237, 1, 3)],
}
# Physical status plane, pixel; CI changes which status group is visible.
STATUS = {0: (0, 0), 1: (1, 0), 2: (1, 1), 3: (0, 1)}


def check(qemu, output, scan, clr=0):
    words = setup(mode=2, clr=clr, window=None)
    command(words, 0xBB, 1)  # Original system's existing COMSCN setting.
    for column, line, pixels in GROUPS:
        command(words, 0x15, column, column)
        command(words, 0x75, line, line)
        write_bytes(words, [p << 3 for p in pixels])

    # Changing scan direction must change the visible output, not rewrite
    # GRAM or change which logical addresses the MPU can subsequently read.
    command(words, 0xBC, scan, clr, 2)
    expected_data = []
    for column, line, pixels in GROUPS:
        command(words, 0x15, column, column)
        command(words, 0x75, line, line)
        read_bytes(words, 3)
        expected_data.extend(p << 3 for p in pixels)

    # DISNOR on this positive glass: RAM 0 is dark, RAM 31 is light.
    frame = bytearray([31] * (240 * 120))
    for x, y, group in VISIBLE[scan & 3]:
        pixels = GROUPS[group][2]
        if clr:
            pixels = pixels[::-1]
        frame[y * 240 + x:y * 240 + x + 3] = bytes(31 - p for p in pixels)
    annunciators = bytearray(60)
    plane, x = STATUS[scan & 3]
    if clr and not (scan & 2):
        x = 2  # CLR reverses the first status group's pixel, not its group.
    annunciators[plane * 30 + x // 8] = 1 << (x & 7)
    return run(qemu, output, f"scan-{scan}-clr-{clr}", words,
               {3: 0x2400 + len(expected_data) * 2, 15: 0x4000},
               expected_data=expected_data, expected_lcd=bytes(frame),
               expected_annunciators=bytes(annunciators),
               metadata={"device": "ST7529", "com_scan": 1,
                         "scan": scan, "clr": clr,
                         "changed_direction_after_ram_writes": True})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scan", type=int, choices=range(8))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"qemu_sha256": identity, "passed": False, "cases": []}
    try:
        for scan in range(8) if args.scan is None else [args.scan]:
            report["cases"].append(check(args.qemu, args.output, scan))
        if args.scan is None:
            # CLR combined with both reversed addresses must not cancel CI.
            report["cases"].append(check(args.qemu, args.output, 3, clr=1))
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
        report["passed"] = True
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
