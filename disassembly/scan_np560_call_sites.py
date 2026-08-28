#!/usr/bin/env python3
"""Find raw DMCU SCALL sites and recover instruction context around them.

NP560.PRG mixes executable code and resources, so a whole-image linear
disassembly quickly loses synchronization.  This tool starts from the exact
two-word SCALL encoding and reconstructs every valid instruction path through
a small window ending at that call.  It is intended as a fast first pass for
xrefs such as the common resource loader at 2E:0AF6.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from np560_disasm import Instruction, decode


DEFAULT_IMAGE = (
    Path(__file__).resolve().parents[1]
    / "NP560+V3.80版系统升级程序"
    / "NP560.PRG"
)


def parse_address(value: str) -> int:
    try:
        segment, pc = value.split(":", 1)
        address = (int(segment, 16) << 16) | int(pc, 16)
    except ValueError as error:
        raise argparse.ArgumentTypeError("address must be SEG:PC") from error
    if address & 1:
        raise argparse.ArgumentTypeError("address must be word aligned")
    return address


def scall_words(target: int) -> tuple[int, int]:
    return 0xBD00 | ((target >> 16) & 0xFF), target & 0xFFFF


def recover_context(
    words: list[int], call_index: int, base_segment: int, context_words: int,
) -> list[Instruction]:
    """Return the longest decodable path ending exactly at *call_index*."""
    first = max(0, call_index - context_words)
    best: list[Instruction] = []
    for start in range(first, call_index + 1):
        index = start
        path: list[Instruction] = []
        while index <= call_index:
            instruction = decode(words, index, base_segment)
            path.append(instruction)
            index += instruction.size
            if instruction.flow == "stop" and index <= call_index:
                break
        if index == call_index + 2 and path[-1].index == call_index:
            if not best or path[0].index < best[0].index:
                best = path
    if not best:
        best = [decode(words, call_index, base_segment)]
    return best


_MOV_IMMEDIATE = re.compile(
    r"^MOV (?:R([0-9]|1[0-5])|REG\[0xF([0-9A-F])\]), #0x([0-9A-F]+)$"
)
_PUSH_REGISTER = re.compile(r"^MOV \[--R15\], R([0-9]|1[0-5])$")


def recover_constant_pushes(context: list[Instruction]) -> list[int | None]:
    """Symbolically recover constant register pushes before the final call."""
    registers: dict[int, int | None] = {index: None for index in range(16)}
    pushes: list[int | None] = []
    for instruction in context[:-1]:
        immediate = _MOV_IMMEDIATE.match(instruction.text)
        if immediate:
            register_text = immediate.group(1) or immediate.group(2)
            registers[int(register_text, 16)] = int(immediate.group(3), 16)
            continue
        push = _PUSH_REGISTER.match(instruction.text)
        if push:
            pushes.append(registers[int(push.group(1))])
            continue
        if instruction.text.startswith("SCALL "):
            for register in registers:
                registers[register] = None
            pushes.clear()
            continue
        if instruction.text.startswith("MOV "):
            destination = instruction.text[4:].split(",", 1)[0]
            register = re.fullmatch(r"R([0-9]|1[0-5])", destination)
            if register:
                registers[int(register.group(1))] = None
    return pushes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=parse_address)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument(
        "--base-segment", type=lambda value: int(value, 0), default=0x20,
    )
    parser.add_argument("--context-words", type=int, default=20)
    parser.add_argument(
        "--segment", type=lambda value: int(value, 16),
        help="only show callers in this hexadecimal segment",
    )
    parser.add_argument(
        "--compact", action="store_true",
        help="print one context line per call instead of an assembly block",
    )
    parser.add_argument(
        "--arguments", action="store_true",
        help="print only the last four symbolically recovered stack arguments",
    )
    args = parser.parse_args()

    payload = args.image.read_bytes()
    if len(payload) & 1:
        raise SystemExit("program image has an odd byte count")
    words = [
        int.from_bytes(payload[offset:offset + 2], "little")
        for offset in range(0, len(payload), 2)
    ]
    call_word, target_word = scall_words(args.target)
    hits = [
        index for index in range(len(words) - 1)
        if words[index] == call_word and words[index + 1] == target_word
    ]
    if args.segment is not None:
        hits = [
            index for index in hits
            if ((args.base_segment << 16) + index * 2) >> 16 == args.segment
        ]

    print(
        f"TARGET={args.target >> 16:02X}:{args.target & 0xFFFF:04X} "
        f"CALLS={len(hits)}"
    )
    for call_index in hits:
        context = recover_context(
            words, call_index, args.base_segment, args.context_words,
        )
        if args.arguments:
            pushes = recover_constant_pushes(context)[-4:]
            values = ",".join(
                "????" if value is None else f"{value:04X}"
                for value in pushes
            )
            print(f"{context[-1].address} ARGS={values}")
            continue
        if args.compact:
            snippets = " | ".join(instruction.text for instruction in context)
            print(f"{context[-1].address}  {snippets}")
            continue
        print(f"\n--- caller {context[-1].address}")
        for instruction in context:
            raw = " ".join(f"{word:04X}" for word in instruction.words)
            print(f"{instruction.address}  {raw:<9}  {instruction.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
