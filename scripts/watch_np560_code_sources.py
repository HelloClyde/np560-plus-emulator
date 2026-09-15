#!/usr/bin/env python3
"""Pause an NP560 Web/QEMU run on the first recovered-code mismatch.

This is a read-only execution guard except for the optional QEMU pause sent
after a mismatch.  It caches the firmware and destination/source mapping,
polls the bounded execution traces exposed by the hardware model, and stops
as soon as a fetched instruction differs from its exact recovered PRG source.
Data-backed but still byte-identical code is informational and is ignored by
default because it is not evidence that execution has failed.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_np560_runtime_code_sources as analyzer  # noqa: E402
import mirror_np560_runtime_patches as runtime_patches  # noqa: E402
from scripts.np560_overlay_map import (  # noqa: E402
    DEFAULT_QEMU_SOURCE,
    parse_qemu_mappings,
)


DEFAULT_FIRMWARE = (
    ROOT / "tmp" / "NP560-runtime-finalized-source-patched-v506.PRG"
)


def pause_vm(url: str, timeout: float) -> None:
    payload = json.dumps({"action": "pause"}).encode("utf-8")
    request = Request(
        f"{url.rstrip('/')}/api/control",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"pause failed: {result!r}")


def format_finding(item: analyzer.Finding) -> str:
    expected = (
        "unknown" if item.expected_word is None else f"{item.expected_word:04x}"
    )
    return (
        f"{item.status.upper()} "
        f"{analyzer.formatted_address(item.address)} "
        f"got={item.actual_word:04x} expected={expected} "
        f"source={analyzer.formatted_address(item.expected_source)} "
        f"mapped={analyzer.formatted_address(item.mapped_source)} "
        f"overlay={item.overlay} traces={','.join(item.traces)}"
    )


def actionable_findings(
    findings: list[analyzer.Finding],
    include_data_backed: bool,
    accepted_guest_words: dict[int, int] | None = None,
) -> list[analyzer.Finding]:
    accepted_guest_words = accepted_guest_words or {}
    return [
        item for item in findings
        if (include_data_backed or item.status != "data-backed")
        and accepted_guest_words.get(item.address) != item.actual_word
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--firmware", type=Path, default=DEFAULT_FIRMWARE)
    parser.add_argument("--qemu-source", type=Path, default=DEFAULT_QEMU_SOURCE)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--request-timeout", type=float, default=5.0)
    parser.add_argument("--no-pause", action="store_true")
    parser.add_argument(
        "--include-data-backed",
        action="store_true",
        help="also stop on source-proven code that is still byte-identical",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    firmware = args.firmware.read_bytes()
    mappings = parse_qemu_mappings(
        args.qemu_source.read_text(encoding="utf-8")
    )
    specs = analyzer.runtime_overlay_specs()
    guest_write_sequences, _ = runtime_patches.static_program_writes(
        runtime_patches.current_resident_routines()
    )
    accepted_guest_words = {
        address: values[-1]
        for address, values in guest_write_sequences.items()
        if values
    }
    deadline = time.monotonic() + args.timeout
    samples = 0

    while time.monotonic() < deadline:
        samples += 1
        registers = analyzer.fetch_registers(args.url, args.request_timeout)
        findings = analyzer.diagnose(
            analyzer.executed_words(registers),
            specs,
            mappings,
            firmware,
        )
        findings = actionable_findings(
            findings,
            args.include_data_backed,
            accepted_guest_words,
        )
        if findings:
            if not args.no_pause:
                pause_vm(args.url, args.request_timeout)
            if args.json:
                print(json.dumps({
                    "samples": samples,
                    "paused": not args.no_pause,
                    "findings": [asdict(item) for item in findings],
                }, indent=2))
            else:
                print(
                    f"CODE_SOURCE_INCIDENT samples={samples} "
                    f"paused={int(not args.no_pause)}"
                )
                for item in findings:
                    print(format_finding(item))
            return 1
        time.sleep(max(args.poll_interval, 0.05))

    print(f"TIMEOUT samples={samples}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
