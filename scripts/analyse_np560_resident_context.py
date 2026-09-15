#!/usr/bin/env python3
"""Extract the NP560 resident outer-context contract from DMCU listings.

The mask-ROM reset entry at 03:0030 is absent from the upgrade image.  The
first recoverable consumer of the object which that entry supplied is the
33:4510 event handler.  This tool turns its repeated far-pointer arithmetic
into a compact field/use map and records the two exact overlay helpers used by
the cold-start branch.  It is deliberately static and read-only: no guessed
context bytes are written to a firmware or NAND image.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


LINE_RE = re.compile(
    r"^(?P<segment>[0-9A-Fa-f]{2}):(?P<pc>[0-9A-Fa-f]{4})"
    r"\s+(?:[0-9A-Fa-f]{4}\s+)+"
    r"(?P<text>[A-Z.][^;]*?)(?:\s+;.*)?$"
)
ADD_FIELD_RE = re.compile(
    r"^ADD REG\[0xF(?P<low>[1357])\], #0x(?P<offset>[0-9A-Fa-f]{4})$"
)


FIELD_NOTES = {
    0x001E: "byte-sized input/selection state; also passed as a range length",
    0x001F: "byte-sized resident interaction state (observed writes 1, 2, 3, 4)",
    0x0020: "byte-sized activation mode; reset path tests it against 2",
    0x0023: "byte-sized event/status state; event 0x00C0 writes 3",
    0x0024: "16-bit application/registry selector mapped by 32:2396",
    0x002C: "far-pointer/base term paired arithmetically with field +0x30",
    0x0030: "active far pointer; reset copies field +0x38 here",
    0x0034: "fallback far pointer copied into +0x2C on a secondary path",
    0x0038: "activation far pointer consumed by the cold-start continuation",
    0x128A: "byte flag controlling input-mask restoration",
    0x128B: "byte flag selecting the +0x128A input-mask branch",
    0x167C: "embedded resident buffer/object passed to 30:FE0E and 14:2262",
    0x169E: "byte completion/status flag written after +0x167C setup",
    0x1CC4: "16-bit menu/registry lookup key used by 31:5300",
    0x1CE2: "byte activation-complete flag written to 1 at cold-start exit",
    0x1DB6: "embedded status/event object passed by address to resident helpers",
}


@dataclass(frozen=True)
class Instruction:
    address: int
    segment: int
    pc: int
    text: str

    @property
    def label(self) -> str:
        return f"{self.segment:02X}:{self.pc:04X}"


@dataclass(frozen=True)
class FieldUse:
    offset: int
    address: str
    pair: str
    operation: str
    width_bits: int | None
    callee: str | None
    evidence: str


def parse_listing(path: Path) -> list[Instruction]:
    instructions: list[Instruction] = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        match = LINE_RE.match(raw_line)
        if not match:
            continue
        segment = int(match.group("segment"), 16)
        pc = int(match.group("pc"), 16)
        instructions.append(
            Instruction(
                address=(segment << 16) | pc,
                segment=segment,
                pc=pc,
                text=match.group("text").strip(),
            )
        )
    return instructions


def is_context_reload(window: list[Instruction], high: int, low: int) -> bool:
    high_load = f"MOV R{high}, [R11+0xFFFC]"
    low_load = f"MOV R{low}, [R11+0xFFFE]"
    texts = [item.text for item in window]
    if high_load in texts and low_load in texts:
        return True
    if high == 2 and low == 3:
        # The handler frequently reloads context into R0:R1 and copies it to
        # R2:R3 before adding two different field offsets in parallel.
        return (
            "MOV R0, [R11+0xFFFC]" in texts
            and "MOV R1, [R11+0xFFFE]" in texts
            and "MOV R2, R0" in texts
            and "MOV R3, R1" in texts
        )
    return False


def classify_use(
    instructions: list[Instruction], index: int, low: int
) -> tuple[str, int | None, str | None, str]:
    pointer = f"R{low}"
    evidence = [instructions[index].label + " " + instructions[index].text]
    for item in instructions[index + 1:index + 24]:
        text = item.text
        evidence.append(item.label + " " + text)
        if ADD_FIELD_RE.match(text):
            break
        if re.match(rf"^MOVB RB[0-9]+, \[{pointer}\]$", text):
            return "read", 8, None, " | ".join(evidence)
        if re.match(rf"^MOV R[0-9]+, \[{pointer}\]$", text):
            return "read", 16, None, " | ".join(evidence)
        if re.match(rf"^MOV R[0-9]+, \[{pointer}\+\+\]$", text):
            return "read", 32, None, " | ".join(evidence)
        if re.match(rf"^MOVB \[{pointer}\],", text):
            return "write", 8, None, " | ".join(evidence)
        if re.match(rf"^MOV \[{pointer}\],", text):
            return "write", 16, None, " | ".join(evidence)
        if re.match(rf"^MOV \[{pointer}\+\+\],", text):
            return "write", 32, None, " | ".join(evidence)
        call = re.match(r"^SCALL ([0-9A-Fa-f]{2}:[0-9A-Fa-f]{4})$", text)
        if call:
            return "address-pass", None, call.group(1).upper(), " | ".join(evidence)
        if text.startswith(("AJMP ", "RJMP ", "RETS", "RET ")):
            break
    return "address-only", None, None, " | ".join(evidence)


def extract_outer_uses(
    instructions: list[Instruction], start: int, end: int
) -> list[FieldUse]:
    body = [item for item in instructions if start <= item.address < end]
    uses: list[FieldUse] = []
    for index, item in enumerate(body):
        match = ADD_FIELD_RE.match(item.text)
        if not match:
            continue
        low = int(match.group("low"), 16)
        if low not in (1, 3):
            continue
        high = low - 1
        # The longest paired-field idiom reads one far field through R2:R3
        # before adding a second offset to the still-live R0:R1 context.  A
        # 24-instruction backward slice covers that sequence while still
        # excluding the unrelated event jump-table arithmetic.
        if not is_context_reload(body[max(0, index - 24):index], high, low):
            continue
        offset = int(match.group("offset"), 16)
        operation, width, callee, evidence = classify_use(body, index, low)
        uses.append(
            FieldUse(
                offset=offset,
                address=item.label,
                pair=f"R{high}:R{low}",
                operation=operation,
                width_bits=width,
                callee=callee,
                evidence=evidence,
            )
        )
    return uses


def helper_summary(instructions: list[Instruction]) -> dict[str, object]:
    ranges = {
        "activation_context": (0x4D9E30, 0x4D9F20),
        "input_mask_dispatch": (0x4EC224, 0x4EC2C2),
    }
    result: dict[str, object] = {}
    for name, (start, end) in ranges.items():
        body = [item for item in instructions if start <= item.address < end]
        calls = [
            item.text.split(" ", 1)[1]
            for item in body
            if item.text.startswith("SCALL ")
        ]
        offsets = [
            int(match.group("offset"), 16)
            for item in body
            if (match := ADD_FIELD_RE.match(item.text))
        ]
        result[name] = {
            "range": f"{start >> 16:02X}:{start & 0xFFFF:04X}.."
            f"{end >> 16:02X}:{end & 0xFFFF:04X}",
            "calls": calls,
            "field_offsets": [f"0x{offset:04X}" for offset in offsets],
        }
    result["input_mask_bits"] = {
        "0x0001": "0x0175",
        "0x0002": "0x01A3",
        "0x0004": "0x0186",
        "0x0008": "0x0193",
        "0x0010": "0x01B4",
        "0x0020": "0x01C3",
    }
    return result


def build_report(
    listing: Path,
    helper_listing: Path,
    uses: list[FieldUse],
    helpers: dict[str, object],
) -> dict[str, object]:
    grouped: dict[int, list[FieldUse]] = defaultdict(list)
    for use in uses:
        grouped[use.offset].append(use)
    fields = []
    for offset in sorted(grouped):
        field_uses = grouped[offset]
        fields.append(
            {
                "offset": f"0x{offset:04X}",
                "note": FIELD_NOTES.get(offset, "unlabelled resident-context field"),
                "operations": dict(Counter(use.operation for use in field_uses)),
                "uses": [asdict(use) for use in field_uses],
            }
        )
    return {
        "schema": "np560-resident-context-v1",
        "consumer": "33:4510..33:52A8",
        "missing_producer": "resident mask-ROM entry 03:0030",
        "listing": str(listing),
        "helper_listing": str(helper_listing),
        "field_count": len(fields),
        "use_count": len(uses),
        "fields": fields,
        "helpers": helpers,
        "cold_start_observations": [
            "field +0x0038 is copied into +0x0030 before 30:9E30",
            "30:9E30 consumes +0x001F, +0x002C and +0x0030",
            "a zero (+0x0030 + +0x002C) sum applies input mask 0x0011",
            "field +0x1CE2 is set to 1 before the activation branch returns",
        ],
    }


def markdown(report: dict[str, object]) -> str:
    lines = [
        "# NP560 resident outer-context map",
        "",
        f"- Consumer: `{report['consumer']}`",
        f"- Missing producer: `{report['missing_producer']}`",
        f"- Recovered fields: {report['field_count']}",
        f"- Static use sites: {report['use_count']}",
        "",
        "| Offset | Static operations | Evidence-backed role |",
        "|---:|---|---|",
    ]
    for field in report["fields"]:
        operations = ", ".join(
            f"{name}×{count}" for name, count in field["operations"].items()
        )
        lines.append(
            f"| `{field['offset']}` | {operations} | {field['note']} |"
        )
    lines.extend(["", "## Use sites", ""])
    for field in report["fields"]:
        sites = ", ".join(
            f"`{use['address']}` {use['operation']}"
            + (f"/{use['width_bits']}" if use["width_bits"] else "")
            + (f" → `{use['callee']}`" if use["callee"] else "")
            for use in field["uses"]
        )
        lines.append(f"- `{field['offset']}`: {sites}")
    lines.extend(["", "## Cold-start contract", ""])
    lines.extend(f"- {item}" for item in report["cold_start_observations"])
    lines.extend(
        [
            "",
            "The report is diagnostic only. It does not synthesize a context, "
            "patch a ROM service, or change guest execution.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--listing",
        type=Path,
        default=Path("tmp/handler334510/NP560_handler_334510_reachable.asm"),
    )
    parser.add_argument(
        "--helper-listing",
        type=Path,
        default=Path("tmp/resident-context-helper-exact-v592.asm"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("tmp"))
    parser.add_argument("--stem", default="np560-resident-context-v592")
    args = parser.parse_args()

    outer = parse_listing(args.listing)
    helpers = parse_listing(args.helper_listing)
    uses = extract_outer_uses(outer, 0x334510, 0x3352A8)
    if not uses:
        raise ValueError("no resident-context field uses were recovered")
    report = build_report(
        args.listing, args.helper_listing, uses, helper_summary(helpers)
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"{args.stem}.json"
    md_path = args.output_dir / f"{args.stem}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(markdown(report), encoding="utf-8")
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
