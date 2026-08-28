#!/usr/bin/env python3
"""Classify calls to the recovered NP560 mask-ROM byte reader.

The compiler passes five words to ``25:206E`` in this order::

    length, source_offset, source_segment, output_offset, output_segment

Most call sites materialise those values immediately before pushing them.  A
few use run-time pointers; those are deliberately reported as unknown rather
than guessed.  This tool makes the static mask-ROM data dependencies auditable
while the missing ROM image is reconstructed.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


LINE_RE = re.compile(
    r"^(?P<segment>[0-9A-F]{2}):(?P<offset>[0-9A-F]{4})"
    r"\s{2}(?P<words>.*?)\s{2}(?P<text>.*)$"
)
TARGET_WORDS = (0xBD25, 0x206E)


@dataclass(frozen=True)
class Instruction:
    segment: int
    offset: int
    words: tuple[int, ...]
    text: str

    @property
    def address(self) -> int:
        return self.segment << 16 | self.offset


def parse_assembly(path: Path) -> list[Instruction]:
    instructions: list[Instruction] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = LINE_RE.match(line)
        if not match:
            continue
        instructions.append(
            Instruction(
                int(match.group("segment"), 16),
                int(match.group("offset"), 16),
                tuple(int(word, 16) for word in match.group("words").split()),
                match.group("text"),
            )
        )
    return instructions


def _written_register(text: str) -> int | None:
    """Return a direct GPR destination when the disassembly exposes one."""
    match = re.match(r"(?:MOVB?|MOVZE|ADD?C?|SUBC?|AND|OR|XOR|SL|SR|SLOSB) "
                     r"(?:REG\[0xF|R)([0-9A-F])(?:\]|),", text)
    return int(match.group(1), 16) if match else None


def recover_pushes(window: list[Instruction]) -> list[int | None]:
    registers: list[int | None] = [None] * 16
    pushes: list[int | None] = []
    for instruction in window:
        first = instruction.words[0]

        # MOV REG[0xFn], #imm16 (REG[F0]..REG[FF] alias R0..R15).
        if first & 0xFFF0 == 0x68F0 and len(instruction.words) >= 2:
            registers[first & 0xF] = instruction.words[1]
            continue

        # MOV Rn, #imm4.
        if first & 0xF000 == 0x4000 and first & 0x0F00 == 0x0800:
            registers[(first >> 4) & 0xF] = first & 0xF
            continue

        # MOV Rn, Rm.
        if first & 0xFF00 == 0x0800:
            registers[(first >> 4) & 0xF] = registers[first & 0xF]
            continue

        # MOV [--R15], Rn.
        if first & 0xFFF0 == 0x58F0:
            pushes.append(registers[first & 0xF])
            continue

        written = _written_register(instruction.text)
        if written is not None:
            registers[written] = None

    return pushes


def format_word(value: int | None) -> str:
    return "????" if value is None else f"{value:04X}"


def classify(instructions: list[Instruction], window_size: int) -> list[dict]:
    calls: list[dict] = []
    for index, instruction in enumerate(instructions):
        if instruction.words[:2] != TARGET_WORDS:
            continue
        start = max(0, index - window_size)
        # A previous call can clobber registers and belongs to another argument
        # construction.  Keep only the current straight-line suffix.
        for candidate in range(index - 1, start - 1, -1):
            if instructions[candidate].text.startswith(("SCALL ", "LCALL ")):
                start = candidate + 1
                break
        pushes = recover_pushes(instructions[start:index])[-5:]
        pushes = [None] * (5 - len(pushes)) + pushes
        length, source_offset, source_segment, output_offset, output_segment = pushes
        calls.append(
            {
                "call": instruction.address,
                "length": length,
                "source": (
                    None if source_segment is None or source_offset is None
                    else source_segment << 16 | source_offset
                ),
                "output": (
                    None if output_segment is None or output_offset is None
                    else output_segment << 16 | output_offset
                ),
                "pushes": pushes,
            }
        )
    return calls


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "assembly",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("NP560_reachable_code.asm"),
    )
    parser.add_argument("--window", type=int, default=48)
    parser.add_argument(
        "--source-segment",
        type=lambda value: int(value, 16),
        help="show only statically recovered sources in this hex segment",
    )
    args = parser.parse_args()

    calls = classify(parse_assembly(args.assembly), args.window)
    shown = 0
    for call in calls:
        source = call["source"]
        if args.source_segment is not None and (
            source is None or source >> 16 != args.source_segment
        ):
            continue
        output = call["output"]
        source_text = "??:????" if source is None else f"{source >> 16:02X}:{source & 0xFFFF:04X}"
        output_text = "??:????" if output is None else f"{output >> 16:02X}:{output & 0xFFFF:04X}"
        print(
            f"{call['call'] >> 16:02X}:{call['call'] & 0xFFFF:04X} "
            f"len={format_word(call['length'])} source={source_text} "
            f"output={output_text} pushes="
            + ",".join(format_word(value) for value in call["pushes"])
        )
        shown += 1
    print(f"calls={len(calls)} shown={shown}")


if __name__ == "__main__":
    main()
