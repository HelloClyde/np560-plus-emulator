#!/usr/bin/env python3
"""Suggest source-proven NP560 overlay candidates after an invalid return.

The QEMU monitor snapshot contains a compact control-transfer trace.  This
tool reconstructs the still-open far-call stack, identifies the logical
function that emitted the invalid RETS, and scans every NP560.PRG bank at the
same PC for a conventional LINK ... UNLINK/RETS implementation.

It is deliberately diagnostic only: it never edits a ROM or a checkpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from np560_disasm import decode


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROGRAM = ROOT / "NP560+V3.80版系统升级程序" / "NP560.PRG"
TRACE_RE = re.compile(
    r"(?P<source_segment>[0-9a-fA-F]{2}):"
    r"(?P<source_pc>[0-9a-fA-F]{4})/"
    r"(?P<opcode>[0-9a-fA-F]{4})>"
    r"(?P<target_segment>[0-9a-fA-F]{2}):"
    r"(?P<target_pc>[0-9a-fA-F]{4})"
)
INVALID_RE = re.compile(
    r"(?P<source_segment>[0-9a-fA-F]{2}):"
    r"(?P<source_pc>[0-9a-fA-F]{4})/c620>"
    r"(?P<target_segment>[0-9a-fA-F]{2}):"
    r"(?P<target_pc>[0-9a-fA-F]{4})"
)


@dataclass(frozen=True)
class Transfer:
    source_segment: int
    source_pc: int
    opcode: int
    target_segment: int
    target_pc: int


@dataclass(frozen=True)
class OpenCall:
    target_segment: int
    target_pc: int
    source_segment: int
    source_pc: int
    trace_index: int


@dataclass(frozen=True)
class Candidate:
    segment: int
    pc: int
    size: int
    link_words: int
    instruction_count: int
    sha256: str


@dataclass(frozen=True)
class OverlayRecord:
    destination: int
    source: int | None
    size: int


def register_field(registers: str, name: str) -> str:
    prefix = name + "="
    try:
        return next(
            line[len(prefix):]
            for line in registers.splitlines()
            if line.startswith(prefix)
        )
    except StopIteration as error:
        raise ValueError(f"snapshot has no {name} field") from error


def load_snapshot(path: Path) -> tuple[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    registers = payload.get("registers")
    if not isinstance(registers, str):
        raise ValueError("snapshot has no textual registers field")
    return (
        register_field(registers, "CONTROL_TRACE"),
        register_field(registers, "INVALID_CONTROL"),
    )


def parse_transfer(text: str) -> Transfer | None:
    match = TRACE_RE.search(text)
    if match is None:
        return None
    return Transfer(*(int(match.group(name), 16) for name in (
        "source_segment", "source_pc", "opcode",
        "target_segment", "target_pc",
    )))


def reconstruct_far_calls(trace: str) -> list[OpenCall]:
    """Reconstruct far SCALL/RETS pairs from a possibly truncated trace."""

    stack: list[OpenCall] = []
    for index, text in enumerate(trace.split(",")):
        transfer = parse_transfer(text)
        if transfer is None:
            continue
        opcode = transfer.opcode
        if opcode >> 8 == 0xBD:  # SCALL seg:pc
            stack.append(OpenCall(
                transfer.target_segment,
                transfer.target_pc,
                transfer.source_segment,
                transfer.source_pc,
                index,
            ))
        elif opcode == 0xC620 and stack:
            # RETS closes the most recent far call.  Interrupt RETI entries
            # are intentionally ignored because the trace has no matching
            # synthetic call for hardware interrupt entry.
            stack.pop()
    return stack


def infer_entry(trace: str, invalid: str) -> OpenCall:
    match = INVALID_RE.search(invalid)
    if match is None:
        raise ValueError(f"unsupported INVALID_CONTROL field: {invalid}")
    invalid_segment = int(match.group("source_segment"), 16)
    invalid_pc = int(match.group("source_pc"), 16)

    # INVALID_CONTROL is also the final CONTROL_TRACE item.  Reconstruct the
    # stack before that RETS, not after it.
    items = trace.split(",")
    if items and parse_transfer(items[-1]) is not None:
        last = parse_transfer(items[-1])
        if (last is not None and last.opcode == 0xC620 and
                last.source_segment == invalid_segment and
                last.source_pc == invalid_pc):
            items.pop()
    stack = reconstruct_far_calls(",".join(items))
    if stack:
        return stack[-1]

    # Fallback for a short/truncated trace: use the closest earlier SCALL to
    # the invalid segment whose target is not beyond the bad RETS.
    transfers = [parse_transfer(item) for item in items]
    for index in range(len(transfers) - 1, -1, -1):
        transfer = transfers[index]
        if (transfer is not None and transfer.opcode >> 8 == 0xBD and
                transfer.target_segment == invalid_segment and
                transfer.target_pc <= invalid_pc):
            return OpenCall(
                transfer.target_segment,
                transfer.target_pc,
                transfer.source_segment,
                transfer.source_pc,
                index,
            )
    raise ValueError("could not infer the function entry from CONTROL_TRACE")


def segment_words(program: bytes, segment: int, base_segment: int) -> list[int] | None:
    offset = (segment - base_segment) << 16
    if offset < 0 or offset + 0x10000 > len(program):
        return None
    bank = program[offset:offset + 0x10000]
    return [
        int.from_bytes(bank[index:index + 2], "little")
        for index in range(0, len(bank), 2)
    ]


def linked_candidate(
    program: bytes,
    segment: int,
    pc: int,
    base_segment: int,
    max_size: int,
) -> Candidate | None:
    words = segment_words(program, segment, base_segment)
    if words is None or pc & 1:
        return None
    index = pc // 2
    if index >= len(words) or words[index] >> 8 != 0x2E:
        return None
    link_words = words[index] & 0xFF
    saw_unlink = False
    instruction_count = 0
    end_pc = pc
    while end_pc - pc < max_size and index < len(words):
        instruction = decode(words, index, segment)
        instruction_count += 1
        end_pc += instruction.size * 2
        index += instruction.size
        if instruction.text == "UNLINK":
            saw_unlink = True
        elif instruction.text == "RETS":
            if saw_unlink:
                offset = ((segment - base_segment) << 16) + pc
                data = program[offset:offset + end_pc - pc]
                return Candidate(
                    segment, pc, end_pc - pc, link_words,
                    instruction_count, hashlib.sha256(data).hexdigest(),
                )
            # Some vendor functions synthesize a far callback by pushing a
            # continuation CS:PC and then executing RETS.  Linear decoding
            # must continue at that continuation to find the real balanced
            # epilogue (for example source 3E:BF4E at 3E:C45C).
        if instruction.text.startswith(".word"):
            return None
    return None


def find_candidates(
    program: bytes,
    pc: int,
    base_segment: int,
    max_size: int,
) -> list[Candidate]:
    segment_count = len(program) // 0x10000
    return [
        candidate
        for segment in range(base_segment, base_segment + segment_count)
        if (candidate := linked_candidate(
            program, segment, pc, base_segment, max_size
        )) is not None
    ]


def parse_address(value: str) -> tuple[int, int]:
    try:
        segment_text, pc_text = value.split(":", 1)
        return int(segment_text, 16), int(pc_text, 16)
    except ValueError as error:
        raise argparse.ArgumentTypeError("address must be SEG:PC") from error


def numeric_address(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    try:
        if ":" in value:
            segment, pc = parse_address(value)
            return (segment << 16) | pc
        return int(value, 0)
    except (ValueError, argparse.ArgumentTypeError):
        return None


def manifest_overlays(payload: object) -> list[OverlayRecord]:
    records: list[OverlayRecord] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            destination = numeric_address(value.get("destination"))
            source = numeric_address(value.get("source"))
            size_value = value.get("bytes", value.get("size"))
            try:
                size = int(size_value, 0) if isinstance(size_value, str) else int(size_value)
            except (TypeError, ValueError):
                size = 0
            if destination is not None and size > 0:
                records.append(OverlayRecord(destination, source, size))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return records


def instructions_for_candidate(
    program: bytes,
    candidate: Candidate,
    base_segment: int,
):
    words = segment_words(program, candidate.segment, base_segment)
    assert words is not None
    index = candidate.pc // 2
    end = index + candidate.size // 2
    while index < end:
        instruction = decode(words, index, candidate.segment)
        yield instruction
        index += instruction.size


def direct_suspicious_callees(
    program: bytes,
    destination_segment: int,
    candidate: Candidate,
    base_segment: int,
    max_size: int,
) -> list[tuple[int, int, list[Candidate]]]:
    """Return source call PC, logical target and linked same-PC candidates."""

    results: list[tuple[int, int, list[Candidate]]] = []
    seen: set[int] = set()
    for instruction in instructions_for_candidate(program, candidate, base_segment):
        if instruction.flow != "call" or not instruction.targets:
            continue
        target = instruction.targets[0]
        physical = (target.segment << 16) | target.pc
        if physical in seen:
            continue
        seen.add(physical)
        words = segment_words(program, target.segment, base_segment)
        if words is not None and words[target.pc // 2] >> 8 == 0x2E:
            continue
        linked = find_candidates(program, target.pc, base_segment, max_size)
        # Vendor application overlays consistently map a logical destination
        # to its source at +0x1D segments.  Prefer that source when a PC is
        # shared by several unrelated linked functions.
        preferred_segment = target.segment + 0x1D
        preferred = [item for item in linked
                     if item.segment == preferred_segment]
        if preferred:
            linked = preferred
        if linked:
            logical_call = (destination_segment << 16) | instruction.address.pc
            results.append((logical_call, physical, linked))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", nargs="?", type=Path)
    parser.add_argument("--program", type=Path, default=DEFAULT_PROGRAM)
    parser.add_argument("--entry", type=parse_address,
                        help="inspect a known logical SEG:PC without a snapshot")
    parser.add_argument("--manifest", type=Path,
                        help="mark overlays already present in a reconstructed ROM")
    parser.add_argument("--base-segment", type=lambda value: int(value, 0), default=0x20)
    parser.add_argument("--max-size", type=lambda value: int(value, 0), default=0x2000)
    args = parser.parse_args()

    if args.entry is not None:
        entry = OpenCall(args.entry[0], args.entry[1], 0, 0, 0)
        invalid = "manual entry"
    else:
        if args.snapshot is None:
            parser.error("snapshot is required unless --entry is supplied")
        trace, invalid = load_snapshot(args.snapshot)
        entry = infer_entry(trace, invalid)
    program = args.program.read_bytes()
    candidates = find_candidates(
        program, entry.target_pc, args.base_segment, args.max_size
    )
    preferred = [item for item in candidates
                 if item.segment == entry.target_segment + 0x1D]
    if preferred:
        candidates = preferred

    print(f"invalid: {invalid}")
    if args.entry is None:
        print(
            f"inferred entry: {entry.target_segment:02X}:{entry.target_pc:04X} "
            f"called from {entry.source_segment:02X}:{entry.source_pc:04X}"
        )
    else:
        print(f"entry: {entry.target_segment:02X}:{entry.target_pc:04X}")
    if not candidates:
        print("candidates: none")
        return 2
    print("candidates:")
    for candidate in candidates:
        print(
            f"  {candidate.segment:02X}:{candidate.pc:04X} "
            f"size=0x{candidate.size:04X} LINK=0x{candidate.link_words:02X} "
            f"instructions={candidate.instruction_count} "
            f"sha256={candidate.sha256[:16]}"
        )
    unique = {candidate.sha256: candidate for candidate in candidates}
    if len(unique) == 1:
        candidate = next(iter(unique.values()))
        print(
            "suggested overlay: "
            f"{entry.target_segment:02X}:{entry.target_pc:04X} <- "
            f"{candidate.segment:02X}:{candidate.pc:04X} "
            f"size=0x{candidate.size:04X}"
        )
    overlays: list[OverlayRecord] = []
    if args.manifest is not None:
        overlays = manifest_overlays(json.loads(args.manifest.read_text(encoding="utf-8")))
        entry_address = (entry.target_segment << 16) | entry.target_pc
        installed = [record for record in overlays
                     if record.destination <= entry_address < record.destination + record.size]
        if installed:
            print("entry status: already covered by reconstructed-ROM overlay")

    # Preflight each complete candidate's direct callees.  This catches a
    # nested missing prologue before another several-minute cold boot.
    suspicious: list[tuple[Candidate, int, int, list[Candidate]]] = []
    for candidate in candidates:
        for call, target, linked in direct_suspicious_callees(
                program, entry.target_segment, candidate,
                args.base_segment, args.max_size):
            suspicious.append((candidate, call, target, linked))
    if suspicious:
        print("suspicious direct callees:")
        for candidate, call, target, linked in suspicious:
            relocated = [
                record for record in overlays
                for linked_candidate in linked
                if (record.source == ((linked_candidate.segment << 16) |
                                      linked_candidate.pc) and
                    record.size >= linked_candidate.size)
            ]
            if relocated and relocated[0].destination == target:
                status = "installed at logical target"
            elif relocated:
                status = (
                    f"relocated at {relocated[0].destination >> 16:02X}:"
                    f"{relocated[0].destination & 0xFFFF:04X}; retarget caller"
                )
            else:
                status = "not present in manifest"
            options = ",".join(
                f"{item.segment:02X}:{item.pc:04X}+0x{item.size:X}"
                for item in linked
            )
            print(
                f"  {call >> 16:02X}:{call & 0xFFFF:04X} -> "
                f"{target >> 16:02X}:{target & 0xFFFF:04X}; "
                f"candidates={options}; {status}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
