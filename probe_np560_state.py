#!/usr/bin/env python3
"""Run an NP560 guest briefly and print CPU/NAND state for RE probes."""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from web.np560_web import Emulator


def parse_pc(value: str) -> int:
    segment_text, separator, offset_text = value.partition(":")
    if not separator:
        raise argparse.ArgumentTypeError("PC must use SEGMENT:OFFSET")
    try:
        segment = int(segment_text, 16)
        offset = int(offset_text, 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("PC must contain hexadecimal values") from exc
    if not 0 <= segment <= 0xFF or not 0 <= offset <= 0xFFFF:
        raise argparse.ArgumentTypeError("PC is outside the 24-bit code space")
    return segment << 16 | offset


def state_pc(state: str) -> int | None:
    match = re.search(r"^PC=([0-9a-fA-F]{2}):([0-9a-fA-F]{4})", state)
    if match is None:
        return None
    return int(match.group(1), 16) << 16 | int(match.group(2), 16)


def compact_progress(cpu_state: str, nand_state: str, elapsed: float) -> str:
    pc_line = cpu_state.splitlines()[0] if cpu_state else "PC=unknown"
    counters = re.search(
        r"READS=(\d+) PROGRAMS=(\d+) ERASES=(\d+) COPIES=(\d+)",
        nand_state,
    )
    page = re.search(r"PAGE_ADDR=([0-9a-fA-F]+)", nand_state)
    detail = counters.group(0) if counters else "NAND counters unavailable"
    page_text = page.group(1) if page else "unknown"
    return f"PROGRESS={elapsed:.1f}s {pc_line} PAGE={page_text} {detail}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--soc-rom", type=Path, required=True)
    parser.add_argument("--burn-code", type=Path)
    parser.add_argument("--nand-image", type=Path)
    parser.add_argument("--nand-checkpoint", type=Path)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument(
        "--until-pc", type=parse_pc,
        help="wait until guest execution reaches SEGMENT:OFFSET; --seconds is the timeout",
    )
    parser.add_argument(
        "--progress-interval", type=float, default=0.0,
        help="print compact CPU/NAND progress at this interval while waiting",
    )
    parser.add_argument(
        "--no-log-unimp", action="store_true",
        help="disable the high-volume QEMU unimplemented/resident-call log",
    )
    parser.add_argument("--save", type=Path)
    parser.add_argument(
        "--save-nand", type=Path,
        help="write complete NAND data/OOB state as a restartable checkpoint",
    )
    args = parser.parse_args()

    if args.nand_image is not None and args.nand_checkpoint is not None:
        parser.error("--nand-image and --nand-checkpoint are mutually exclusive")

    emulator = Emulator(
        qemu=args.qemu,
        firmware=args.firmware,
        soc_rom=args.soc_rom,
        soc_rom_skeleton=True,
        burn_code=args.burn_code,
        nand_image=args.nand_image,
        nand_checkpoint=args.nand_checkpoint,
        log_unimp=not args.no_log_unimp,
    )
    try:
        started = time.monotonic()
        deadline = started + max(args.seconds, 0.0)
        next_progress = started + max(args.progress_interval, 0.0)
        reached = args.until_pc is None
        while args.until_pc is not None and time.monotonic() < deadline:
            cpu_state = emulator.qmp.execute(
                "qom-get", {"path": "/machine", "property": "cpu-state"}
            )
            if state_pc(cpu_state) == args.until_pc:
                reached = True
                break
            now = time.monotonic()
            if args.progress_interval > 0 and now >= next_progress:
                nand_state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "nand-state"}
                )
                print(compact_progress(cpu_state, nand_state, now - started),
                      flush=True)
                next_progress = now + args.progress_interval
            time.sleep(0.1)
        if args.until_pc is None:
            time.sleep(max(deadline - time.monotonic(), 0.0))
        cpu_state = emulator.qmp.execute(
            "qom-get", {"path": "/machine", "property": "cpu-state"}
        )
        nand_state = emulator.qmp.execute(
            "qom-get", {"path": "/machine", "property": "nand-state"}
        )
        print(cpu_state)
        print(nand_state)
        if args.until_pc is not None:
            target = f"{args.until_pc >> 16:02x}:{args.until_pc & 0xffff:04x}"
            print(f"WAIT_PC={target} {'reached' if reached else 'timeout'}", flush=True)
        if args.save is not None:
            emulator.qmp.execute("pmemsave", {
                "val": 0,
                "size": 0x1000000,
                "filename": str(args.save),
            })
        if args.save_nand is not None:
            emulator.qmp.execute("qom-set", {
                "path": "/machine",
                "property": "nand-save",
                "value": str(args.save_nand),
            })
            print(f"NAND checkpoint saved: {args.save_nand}")
    finally:
        emulator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
