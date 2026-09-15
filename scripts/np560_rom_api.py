#!/usr/bin/env python3
"""Inventory calls from an NP560+ auxiliary listing into resident SoC ROM.

The update burner is present in the upgrade package, while code segment 02 is
not.  This tool turns every direct SCALL into that missing segment into an
auditable ABI-reconstruction report.  It deliberately reports evidence and
does not manufacture implementations for the missing routines.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ADDRESS = r"[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}"
INSTRUCTION_RE = re.compile(
    rf"^(?P<address>{ADDRESS})\s+"
    r"(?P<words>[0-9A-Fa-f]{4}(?:\s+[0-9A-Fa-f]{4})?)\s{2,}"
    r"(?P<text>.+?)\s*$"
)
CALL_RE = re.compile(rf"^SCALL\s+(?P<target>{ADDRESS})(?:\s|$)", re.I)
STACK_CLEANUP_RE = re.compile(r"^ADD\s+R15,\s+#0x([0-9A-Fa-f]+)(?:\s|$)")
FUNCTION_RE = re.compile(
    r"^(?P<label>entry(?:_\d+)?|sub_[0-9A-Fa-f]{2}_[0-9A-Fa-f]{4}):$"
)


@dataclass(frozen=True)
class ListedInstruction:
    address: str
    words: str
    text: str
    function: str


@dataclass(frozen=True)
class RomCall:
    instruction_index: int
    address: str
    target: str
    function: str


EVIDENCE_NOTES = {
    "02:BBF6": (
        "Strong NAND page/spare transfer candidate. Calls in `sub_51_0000` "
        "supply a page-like address, `50:0760` buffer, and `0x0040`, then "
        "remove seven stack words."
    ),
    "02:BDD6": (
        "NAND follow-up/status candidate. It repeatedly follows transfer "
        "paths and its return value is checked by the caller."
    ),
    "02:BCC6": (
        "NAND transfer variant candidate. Its exact direction and spare-area "
        "contract remain unproven."
    ),
    "02:BE5C": (
        "Asynchronous NAND operation variant. Callers pair it immediately "
        "with `02:C04C`."
    ),
    "02:BF56": (
        "Second asynchronous NAND operation variant, selected for device ID "
        "`0x76` and paired immediately with `02:C04C`."
    ),
    "02:C04C": (
        "Completion/status routine candidate. It follows `02:BE5C` or "
        "`02:BF56`, and callers branch on R0."
    ),
}


def normalize_address(value: str) -> str:
    segment, pc = value.split(":", 1)
    return f"{int(segment, 16):02X}:{int(pc, 16):04X}"


def parse_listing(text: str, rom_segment: int = 0x02) -> tuple[
    list[ListedInstruction], list[RomCall]
]:
    instructions: list[ListedInstruction] = []
    calls: list[RomCall] = []
    current_function = "(unlabelled)"

    for raw_line in text.splitlines():
        line = raw_line.strip()
        label_match = FUNCTION_RE.match(line)
        if label_match:
            current_function = label_match.group("label")
            continue

        instruction_match = INSTRUCTION_RE.match(line)
        if not instruction_match:
            continue
        instruction = ListedInstruction(
            address=normalize_address(instruction_match.group("address")),
            words=" ".join(instruction_match.group("words").upper().split()),
            text=instruction_match.group("text"),
            function=current_function,
        )
        index = len(instructions)
        instructions.append(instruction)

        call_match = CALL_RE.match(instruction.text)
        if not call_match:
            continue
        target = normalize_address(call_match.group("target"))
        if int(target[:2], 16) == rom_segment:
            calls.append(
                RomCall(
                    instruction_index=index,
                    address=instruction.address,
                    target=target,
                    function=current_function,
                )
            )

    return instructions, calls


def render_report(
    source: Path,
    instructions: list[ListedInstruction],
    calls: list[RomCall],
    context_before: int = 8,
    context_after: int = 2,
) -> str:
    counts = Counter(call.target for call in calls)
    functions: dict[str, set[str]] = {}
    for call in calls:
        functions.setdefault(call.target, set()).add(call.function)

    def cleanup_for(call: RomCall) -> int | None:
        following = call.instruction_index + 1
        if following >= len(instructions):
            return None
        match = STACK_CLEANUP_RE.match(instructions[following].text)
        return int(match.group(1), 16) if match else None

    cleanup_summary: dict[str, set[int | None]] = {}
    for call in calls:
        cleanup_summary.setdefault(call.target, set()).add(cleanup_for(call))

    def format_cleanup(values: set[int | None]) -> str:
        rendered = [
            f"`0x{value:X}` ({value // 2} words)"
            for value in sorted(item for item in values if item is not None)
        ]
        if None in values:
            rendered.append("none immediately")
        return ", ".join(rendered)

    lines = [
        "# NP560+ resident SoC ROM API evidence",
        "",
        f"- Source listing: `{source}`",
        f"- Parsed instructions: {len(instructions):,}",
        f"- Direct calls into code segment 02: {len(calls):,}",
        f"- Distinct resident entry points: {len(counts):,}",
        "- Scope: static call-site evidence only; no original ROM bytes are present.",
        "",
        "## Entry-point inventory",
        "",
        "| Resident entry | Calls | Calling functions | Immediate R15 cleanup | Evidence status |",
        "|---|---:|---:|---|---|",
    ]
    for target in sorted(counts):
        status = "NAND-related hypothesis" if target in EVIDENCE_NOTES else "Unclassified"
        lines.append(
            f"| `{target}` | {counts[target]} | {len(functions[target])} | "
            f"{format_cleanup(cleanup_summary[target])} | {status} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation constraints",
            "",
            "The contexts below establish the call ABI and surrounding control flow. "
            "Names such as read, write, erase, and wait remain hypotheses until a "
            "reconstructed routine produces the caller-observed results for all call sites.",
            "",
        ]
    )

    for target in sorted(counts):
        lines.extend([f"## `{target}`", ""])
        note = EVIDENCE_NOTES.get(target)
        if note:
            lines.extend([note, ""])
        lines.append(
            "Call sites: "
            + ", ".join(f"`{call.address}`" for call in calls if call.target == target)
        )
        lines.append("")

        for call in (item for item in calls if item.target == target):
            start = max(0, call.instruction_index - context_before)
            end = min(len(instructions), call.instruction_index + context_after + 1)
            # Do not bleed context through an adjacent function boundary.
            while start < call.instruction_index and instructions[start].function != call.function:
                start += 1
            while end > call.instruction_index + 1 and instructions[end - 1].function != call.function:
                end -= 1
            lines.extend(
                [
                    f"### `{call.address}` in `{call.function}`",
                    "",
                    "```text",
                ]
            )
            for index in range(start, end):
                instruction = instructions[index]
                marker = ">" if index == call.instruction_index else " "
                lines.append(
                    f"{marker} {instruction.address}  {instruction.words:<9}  "
                    f"{instruction.text}"
                )
            lines.extend(["```", ""])

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("listing", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--rom-segment", type=lambda value: int(value, 0), default=2)
    parser.add_argument("--context-before", type=int, default=8)
    parser.add_argument("--context-after", type=int, default=2)
    args = parser.parse_args()

    if not 0 <= args.rom_segment <= 0xFF:
        raise SystemExit("ROM segment must fit in eight bits")
    if args.context_before < 0 or args.context_after < 0:
        raise SystemExit("context sizes must be non-negative")

    source = args.listing.resolve()
    instructions, calls = parse_listing(
        source.read_text(encoding="utf-8"), args.rom_segment
    )
    if not calls:
        raise SystemExit(f"no SCALL targets in segment {args.rom_segment:02X}")
    output = args.output or source.with_name("NP560_resident_rom_api.md")
    output.write_text(
        render_report(source, instructions, calls, args.context_before, args.context_after),
        encoding="utf-8",
    )
    print(f"found {len(calls)} calls to {len(set(call.target for call in calls))} entries")
    print(f"wrote {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
