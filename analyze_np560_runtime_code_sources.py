#!/usr/bin/env python3
"""Compare executed NP560 instructions with recovered linked PRG sources.

The emulator exposes bounded foreground and control-flow traces in its Web
state.  This tool resolves every executed PC through the ROM builder's
destination/source/size records, reads the expected instruction word from the
PRG, and reports code islands that are still data-backed or already differ
from their recovered source.  It is read-only and never sends control input.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.error import HTTPError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from disassembly.np560_overlay_map import (  # noqa: E402
    DEFAULT_QEMU_SOURCE,
    OverlaySpec,
    collect_builder_overlays,
    covering_mapping,
    parse_qemu_mappings,
)
from disassembly import build_np560_reconstructed_rom as rom  # noqa: E402


PROGRAM_BASE = 0x200000
DEFAULT_FIRMWARE = (
    ROOT / "tmp" / "NP560-runtime-finalized-source-patched-v506.PRG"
)
TRACE_NAMES = ("FOREGROUND_TRACE", "CONTROL_TRACE", "EXEC_TRACE")
TRACE_WORD = re.compile(
    r"(?P<segment>[0-9a-fA-F]{2}):(?P<offset>[0-9a-fA-F]{4})/"
    r"(?P<word>[0-9a-fA-F]{4})(?=[>@,]|$)"
)


@dataclass(frozen=True)
class Finding:
    address: int
    actual_word: int
    expected_word: int | None
    overlay: str
    expected_source: int
    mapped_source: int | None
    traces: tuple[str, ...]
    status: str


def fetch_registers(url: str, timeout: float) -> str:
    root = url.rstrip("/")
    try:
        with urlopen(f"{root}/api/diagnostics", timeout=timeout) as response:
            state = json.load(response)
    except HTTPError as exc:
        if exc.code != 404:
            raise
        # Compatibility with an already running pre-endpoint Web process.
        with urlopen(f"{root}/api/state", timeout=timeout) as response:
            state = json.load(response)
    if not isinstance(state, dict) or "error" in state:
        raise ValueError(f"invalid Web state: {state!r}")
    return str(state.get("registers", ""))


def executed_words(registers: str) -> dict[int, tuple[int, set[str]]]:
    """Return the last observed word and trace sources for each executed PC."""
    result: dict[int, tuple[int, set[str]]] = {}
    for name in TRACE_NAMES:
        match = re.search(rf"(?:^|\n){name}=([^\n]*)", registers)
        if not match:
            continue
        for item in TRACE_WORD.finditer(match.group(1)):
            address = (
                (int(item.group("segment"), 16) << 16)
                | int(item.group("offset"), 16)
            )
            word = int(item.group("word"), 16)
            if address in result:
                _, traces = result[address]
                traces.add(name)
                result[address] = (word, traces)
            else:
                result[address] = (word, {name})
    return result


def runtime_overlay_specs() -> list[OverlaySpec]:
    """Include named overlays plus the source-proven modal closure tuple."""
    specs = list(collect_builder_overlays())
    for index, (destination, source, size) in enumerate(
        rom.APPLICATION_OPERATION_MODAL_CLOSURE_OVERLAYS
    ):
        specs.append(OverlaySpec(
            destination,
            size,
            f"APPLICATION_OPERATION_MODAL_CLOSURE_{index:02d}",
            source,
            "code",
        ))
    return sorted(set(specs))


def firmware_word(firmware: bytes, address: int) -> int | None:
    offset = address - PROGRAM_BASE
    if offset < 0 or offset + 2 > len(firmware):
        return None
    return int.from_bytes(firmware[offset:offset + 2], "little")


def diagnose(
    words: dict[int, tuple[int, set[str]]],
    specs: list[OverlaySpec],
    mappings: list,
    firmware: bytes,
    include_clean: bool = False,
) -> list[Finding]:
    findings: list[Finding] = []
    for address, (actual_word, trace_names) in sorted(words.items()):
        matches = [
            spec for spec in specs
            if spec.role == "code" and spec.source is not None
            and spec.destination <= address < spec.end
        ]
        # Prefer the narrowest exact recovered island when historical overlay
        # records overlap at the same destination.
        if matches:
            spec = min(matches, key=lambda item: item.size)
            source = spec.source + address - spec.destination
            expected_word = firmware_word(firmware, source)
            mapping = covering_mapping(spec, mappings)
            mapped_source = None
            if mapping is not None and mapping.source is not None:
                mapped_source = mapping.source + address - mapping.base
            if expected_word is not None and actual_word != expected_word:
                status = "word-mismatch"
            elif mapped_source != source:
                status = "data-backed"
            else:
                status = "clean"
            if include_clean or status != "clean":
                findings.append(Finding(
                    address,
                    actual_word,
                    expected_word,
                    spec.name,
                    source,
                    mapped_source,
                    tuple(sorted(trace_names)),
                    status,
                ))
            continue

        # A runtime address may be a QEMU-only Harvard window that predates
        # the reconstructed-ROM catalogue.  Source-pinned mappings are still
        # fully auditable.  For a writable/data-backed code window without a
        # recovered source, compare against the flat PRG word and report only
        # when guest data has replaced it.  Such a mismatch is not proof that
        # the flat word is the final code body, but it is a high-value signal
        # that execution has entered a code/data collision and needs source
        # recovery.  This catches legal-looking corruption before it becomes
        # an unsupported opcode or a damaged return address.
        address_mappings = sorted(
            (
                mapping for mapping in mappings
                if mapping.code and mapping.base <= address < mapping.end
            ),
            key=lambda item: item.size,
        )
        if address_mappings:
            mapping = address_mappings[0]
            if mapping.source is not None:
                source = mapping.source + address - mapping.base
                expected_word = firmware_word(firmware, source)
                status = (
                    "word-mismatch"
                    if expected_word is not None and actual_word != expected_word
                    else "clean"
                )
                if include_clean or status != "clean":
                    findings.append(Finding(
                        address,
                        actual_word,
                        expected_word,
                        mapping.symbol,
                        source,
                        source,
                        tuple(sorted(trace_names)),
                        status,
                    ))
                continue

            expected_word = firmware_word(firmware, address)
            if expected_word is not None and actual_word != expected_word:
                findings.append(Finding(
                    address,
                    actual_word,
                    expected_word,
                    mapping.symbol,
                    address,
                    None,
                    tuple(sorted(trace_names)),
                    "data-backed-mismatch",
                ))
            continue

        # Code outside an explicit overlay is backed by immutable PRG NOR.
        # Any observed difference is therefore always a mapping/model bug.
        expected_word = firmware_word(firmware, address)
        if expected_word is not None and actual_word != expected_word:
            findings.append(Finding(
                address,
                actual_word,
                expected_word,
                "FLAT_PROGRAM",
                address,
                address,
                tuple(sorted(trace_names)),
                "flat-mismatch",
            ))
    return findings


def formatted_address(address: int | None) -> str:
    if address is None:
        return "data-backed"
    return f"{address >> 16:02x}:{address & 0xffff:04x}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--firmware", type=Path, default=DEFAULT_FIRMWARE)
    parser.add_argument("--qemu-source", type=Path, default=DEFAULT_QEMU_SOURCE)
    parser.add_argument("--all", action="store_true",
                        help="also print correctly pinned executed islands")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    registers = fetch_registers(args.url, args.timeout)
    mappings = parse_qemu_mappings(
        args.qemu_source.read_text(encoding="utf-8")
    )
    findings = diagnose(
        executed_words(registers),
        runtime_overlay_specs(),
        mappings,
        args.firmware.read_bytes(),
        args.all,
    )
    if args.json:
        print(json.dumps([asdict(item) for item in findings], indent=2))
    else:
        for item in findings:
            expected = (
                "unknown" if item.expected_word is None
                else f"{item.expected_word:04x}"
            )
            print(
                f"{item.status.upper():13} "
                f"{formatted_address(item.address)} "
                f"got={item.actual_word:04x} expected={expected} "
                f"source={formatted_address(item.expected_source)} "
                f"mapped={formatted_address(item.mapped_source)} "
                f"overlay={item.overlay} traces={','.join(item.traces)}"
            )
        counts = {
            status: sum(item.status == status for item in findings)
            for status in (
                "word-mismatch", "data-backed", "data-backed-mismatch",
                "flat-mismatch", "clean",
            )
        }
        print(
            "SUMMARY "
            f"executed={len(executed_words(registers))} "
            f"mismatch={counts['word-mismatch'] + counts['data-backed-mismatch'] + counts['flat-mismatch']} "
            f"data-backed={counts['data-backed']} "
            f"clean={counts['clean']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
