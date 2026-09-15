#!/usr/bin/env python3
"""ST7529 read pipeline and RMW via guest MMIO (datasheet pp20/45/46/63).

No NAND, ROM replacement, runtime RAM injection or Web pixel repair. Dummy
read values are unspecified; only subsequent device data is asserted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from test_np560_lcd_formats import byte_write, command, setup, write_bytes
from test_np560_mac import run


WIRE = {
    1: ((0x0A, 0x15), (0x3C, 0xC2), (0xF9, 0x89), (0xCE, 0x59)),
    2: ((8, 64, 168), (56, 152, 16), (248, 48, 72), (200, 200, 200)),
}
# Independent fixed pixel examples after guest ANDs each bus byte with 7F.
MODIFIED_PIXELS = {
    1: ((1, 8, 21), (7, 17, 2), (15, 4, 9), (9, 25, 25)),
    2: ((1, 8, 5), (7, 3, 2), (15, 6, 9), (9, 9, 9)),
}


def read_data(words, count, *, dummy=False):
    if dummy:
        words.append(0x2941)  # Discard first data-port read, no stored oracle.
    for _ in range(count):
        words.extend((0x2941, 0x1944, 0x1A34))


def status(words):
    # A0=0 read is not a command and must not cancel RMW.
    words.extend((0x2940, 0x1944, 0x1A34))


def seeded(mode, scan=0, clr=0):
    words = setup(mode=mode, scan=scan, clr=clr)
    command(words, 0xBB, 1)
    write_bytes(words, [v for group in WIRE[mode] for v in group])
    return words


def cases():
    for mode, groups in WIRE.items():
        raw = [v for group in groups for v in group]
        n = len(groups[0])
        words = seeded(mode)
        command(words, 0x5D)
        read_data(words, len(raw) + n, dummy=True)
        # RAMRD itself resets the address and starts a fresh dummy cycle.
        command(words, 0x5D)
        read_data(words, n, dummy=True)
        yield f"ramrd-dummy-and-wrap-gs{mode}", words, raw + list(groups[0]) * 2, None

        for scan, clr in ((0, 0), (4, 0), (0, 1)):
            words = seeded(mode, scan, clr)
            command(words, 0xE0)
            status(words)
            expected = [0xEA | (0x10 if scan else 0)]
            for group in groups:
                words.append(0x2941)  # Datasheet p63: dummy for each group.
                for i in range(n):
                    read_data(words, 1)
                    words.append(0x0854 + (i << 4))  # Save R4 in R5/R6/R7.
                expected.extend(group)
                for i in range(n):
                    reg = 5 + i
                    words.extend((0x7400 | (0xF0 + reg), 0x7F,
                                  0x0940 | (reg * 2 + 1), 0x0B14))
            modified = [v & 0x7F for v in raw]
            # Reads do not advance the group: two full reads return G0 twice.
            read_data(words, n * 2, dummy=True)
            expected.extend(modified[:n] * 2)
            status(words)
            expected.append(0xEA | (0x10 if scan else 0))
            command(words, 0xEE)
            status(words)
            expected.append(0xCA | (0x10 if scan else 0))
            command(words, 0x5D)
            read_data(words, len(raw), dummy=True)
            expected.extend(modified)
            frame = bytearray([31] * (240 * 120))
            for i, pixels in enumerate(MODIFIED_PIXELS[mode]):
                column, line = (i // 2, i % 2) if scan else (i % 2, i // 2)
                offset = (119 - line) * 240 + column * 3
                frame[offset:offset + 3] = bytes(
                    31 - p for p in (pixels[::-1] if clr else pixels))
            yield f"rmw-cycle-gs{mode}-scan{scan}-clr{clr}", words, expected, bytes(frame)

        for end in (0xEE, 0x25):
            words = seeded(mode)
            command(words, 0xE0)
            read_data(words, n, dummy=True)
            byte_write(words, True, 0xFF)  # Incomplete write group.
            command(words, end)
            for _ in range(n):
                byte_write(words, True, 0xFF)  # No longer a RAM transfer.
            status(words)
            command(words, 0x5D)
            read_data(words, len(raw), dummy=True)
            yield f"rmw-cancel-partial-gs{mode}-{end:02x}", words, list(groups[0]) + [0xCA] + raw, None

        words = seeded(mode)
        command(words, 0xE0)
        for v in groups[3]:
            byte_write(words, True, v)  # Advances to G1 without any read.
        command(words, 0xE0)  # Reenter resets to the configured start.
        read_data(words, n, dummy=True)
        command(words, 0x5C)  # RAMWR cancels RMW and starts ordinary writes.
        for v in groups[2]:
            byte_write(words, True, v)
        status(words)
        command(words, 0x5D)  # RAMRD also cancels any prior RMW.
        read_data(words, n * 2, dummy=True)
        yield f"rmw-reenter-and-ramwr-gs{mode}", words, list(groups[3]) + [0xCA] + list(groups[2]) + list(groups[1]), None

    words = seeded(2)
    command(words, 0x31)
    command(words, 0xE0)  # This command is defined in EXT=0 only.
    status(words)
    command(words, 0x30)
    command(words, 0xE0)
    status(words)
    command(words, 0x5D)
    status(words)
    read_data(words, 3, dummy=True)
    yield "rmw-extension-and-ramrd-cancel", words, [0xCA, 0xEA, 0xCA, 8, 64, 168], None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=[name for name, *_ in cases()])
    parser.add_argument("--icount", type=int)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"passed": False, "qemu_sha256": identity, "cases": []}
    try:
        for name, words, expected, frame in cases():
            if args.case and name != args.case:
                continue
            report["cases"].append(run(
                args.qemu, args.output, name, words,
                {3: 0x2400 + len(expected) * 2, 15: 0x4000},
                expected_data=expected, expected_lcd=frame, icount=args.icount,
                metadata={"source": "ST7529 v1.8 pp20,45,46,63",
                          "dummy_value_asserted": False}))
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
        report["passed"] = all(case["passed"] for case in report["cases"])
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
