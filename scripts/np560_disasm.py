#!/usr/bin/env python3
"""Static disassembler for the King Billion 16-bit DMCU used by NP560+.

The opcode map is transcribed from the instruction-set appendix of patent
CN1916884A.  NP560.PRG stores each 16-bit instruction word little-endian,
although the patent prints a word as opcode-byte followed by operand-byte.

This is a recursive-control-flow disassembler.  It follows direct calls and
jumps, and deliberately stops at unknown words or erased-image padding so that
font/audio/resource data is not rendered as millions of fake instructions.
"""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path


DEFAULT_IMAGE = (
    Path(__file__).resolve().parents[1]
    / "NP560+V3.80版系统升级程序"
    / "NP560.PRG"
)
DEFAULT_BASE_SEGMENT = 0x20


CONDITIONS = {
    0x0: "ALWAYS",
    0x1: "Z/EQ",
    0x2: "NZ/NE",
    0x3: "V",
    0x4: "NV",
    0x5: "C/UL",
    0x6: "NC/UGE",
    0x7: "N",
    0x8: "NN",
    0x9: "SL",
    0xA: "UG",
    0xB: "SG",
    0xC: "ULE",
    0xD: "SLE",
    0xE: "SGE",
}

ALU_OPS = {
    0x0: "ADD",
    0x1: "ADDC",
    0x2: "SUB",
    0x3: "SUBC",
    0x4: "AND",
    0x5: "OR",
    0x6: "CMP",
    0x7: "XOR",
}

SHIFT_REG = {
    0x0C: "SL",
    0x1C: "SLOSB",
    0x0D: "SR",
    0x1D: "SROSB",
    0x4A: "ASR",
    0xC8: "ROL",
    0xC9: "ROR",
}

SHIFT_IMM = {
    0x4B: "ASR",
    0x4C: "SL",
    0x5C: "SLOSB",
    0x4D: "SR",
    0x5D: "SROSB",
    0xCA: "ROL",
    0xCB: "ROR",
}

BIT_BINARY = {
    0x6C: "BOR",
    0x6D: "BXOR",
    0x7C: "BMOV",
    0x7D: "BMOVN",
    0x8C: "BAND",
    0x8D: "BCMP",
}

BIT_BRANCH = {
    0x9A: "JB",
    0x9B: "JNB",
    0x9C: "JBC",
    # The Chinese publication drops the leading 9 in this row; 9D is the
    # only encoding consistent with the adjacent 9A/9B/9C sequence.
    0x9D: "JNBS",
}

EXP_OPS = {
    0x0: ("EDS", False),
    0x1: ("EDS", True),
    0x2: ("EDU", False),
    0x3: ("EDU", True),
    0x4: ("BEDS", False),
    0x5: ("BEDS", True),
    0x6: ("BEDU", False),
    0x7: ("BEDU", True),
}


@dataclass(frozen=True)
class Address:
    segment: int
    pc: int

    def __str__(self) -> str:
        return f"{self.segment:02X}:{self.pc:04X}"


@dataclass
class Instruction:
    index: int
    address: Address
    size: int
    words: tuple[int, ...]
    text: str
    flow: str = "next"
    targets: tuple[Address, ...] = ()
    note: str = ""


def signed8(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def reg4(value: int) -> str:
    return f"R{value & 0xF}"


def reg8(value: int) -> str:
    # The patent defines RR as an 8-bit register number but does not publish
    # all SoC-specific SFR names.  Preserve the exact register address.
    return f"REG[0x{value:02X}]"


def byte_reg4(value: int) -> str:
    return f"RB{value & 0xF}"


def address_for_index(index: int, base_segment: int) -> Address:
    """Translate a file word index to the DMCU's byte-addressed CS:PC."""
    physical = (base_segment << 16) + index * 2
    return Address((physical >> 16) & 0xFF, physical & 0xFFFF)


def index_for_address(address: Address, base_segment: int, word_count: int) -> int | None:
    physical = (address.segment << 16) | address.pc
    delta = physical - (base_segment << 16)
    if delta < 0 or delta & 1:
        return None
    index = delta // 2
    return index if 0 <= index < word_count else None


def relative_target(address: Address, instruction_words: int, rel: int) -> Address:
    return Address(
        address.segment,
        (address.pc + instruction_words * 2 + rel * 2) & 0xFFFF,
    )


def decode(words: list[int], index: int, base_segment: int) -> Instruction:
    address = address_for_index(index, base_segment)
    word = words[index]
    op = word >> 8
    arg = word & 0xFF

    def make(
        text: str,
        size: int = 1,
        flow: str = "next",
        targets: tuple[Address, ...] = (),
        note: str = "",
    ) -> Instruction:
        actual = min(size, len(words) - index)
        if actual != size:
            return Instruction(index, address, 1, (word,), f".word 0x{word:04X}", "stop", (), "truncated")
        return Instruction(index, address, size, tuple(words[index : index + size]), text, flow, targets, note)

    def extword() -> int:
        return words[index + 1]

    # Dense arithmetic families.  The high nibble selects the addressing
    # mode; the low three opcode bits select the ALU operation.
    low = op & 0x0F
    high = op >> 4
    if low in ALU_OPS:
        mnemonic = ALU_OPS[low]
        byte_mode = high in {0x0, 0x2, 0x4, 0x6, 0x8, 0xA}
        suffix = "B" if byte_mode else ""
        mnemonic += suffix
        dst = byte_reg4(arg >> 4) if byte_mode else reg4(arg >> 4)
        src = byte_reg4(arg) if byte_mode else reg4(arg)
        if high in {0x0, 0x1}:
            return make(f"{mnemonic} {dst}, {src}")
        if high in {0x2, 0x3}:
            indirect = reg4(8 + (arg & 0x7))
            post = "++" if arg & 0x8 else ""
            return make(f"{mnemonic} {dst}, [{indirect}{post}]")
        if high in {0x4, 0x5}:
            return make(f"{mnemonic} {dst}, #0x{arg & 0xF:X}")
        if high in {0x6, 0x7} and index + 1 < len(words):
            width = 8 if byte_mode else 16
            return make(f"{mnemonic} {reg8(arg)}, #0x{extword():0{width // 4}X}", 2)
        if high in {0x8, 0x9} and index + 1 < len(words):
            return make(f"{mnemonic} {reg8(arg)}, [0x{extword():04X}]", 2)
        if high in {0xA, 0xB} and low != 0x6 and index + 1 < len(words):
            return make(f"{mnemonic} [0x{extword():04X}], {reg8(arg)}", 2)

    # Data movement.
    if op in {0x08, 0x09}:
        byte = op == 0x09
        r = byte_reg4 if byte else reg4
        return make(f"MOV{'B' if byte else ''} {r(arg >> 4)}, {r(arg)}")
    if op in {0x0A, 0x0B}:
        byte = op == 0x0B
        return make(f"MOV{'B' if byte else ''} [{reg4(arg >> 4)}], {(byte_reg4 if byte else reg4)(arg)}")
    if op in {0x18, 0x19}:
        name = "MOVSE" if op == 0x18 else "MOVZE"
        return make(f"{name} {reg4(arg >> 4)}, {byte_reg4(arg)}")
    if op in {0x1A, 0x1B}:
        byte = op == 0x1B
        return make(f"MOV{'B' if byte else ''} [{reg4(arg >> 4)}++], {(byte_reg4 if byte else reg4)(arg)}")
    if op in {0x28, 0x29}:
        byte = op == 0x29
        return make(f"MOV{'B' if byte else ''} {(byte_reg4 if byte else reg4)(arg >> 4)}, [{reg4(arg)}]")
    if op in {0x2A, 0x2B}:
        byte = op == 0x2B
        return make(f"MOV{'B' if byte else ''} [{reg4(arg >> 4)}], [{reg4(arg)}]")
    if op in {0x38, 0x39}:
        byte = op == 0x39
        return make(f"MOV{'B' if byte else ''} {(byte_reg4 if byte else reg4)(arg >> 4)}, [{reg4(arg)}++]")
    if op in {0x3A, 0x3B}:
        byte = op == 0x3B
        return make(f"MOV{'B' if byte else ''} [{reg4(arg >> 4)}], [{reg4(arg)}++]")
    if op in {0x48, 0x49}:
        byte = op == 0x49
        return make(f"MOV{'B' if byte else ''} {(byte_reg4 if byte else reg4)(arg >> 4)}, #0x{arg & 0xF:X}")
    if op in {0x58, 0x59}:
        byte = op == 0x59
        return make(f"MOV{'B' if byte else ''} [--{reg4(arg >> 4)}], {(byte_reg4 if byte else reg4)(arg)}")
    if op in {0x5A, 0x5B}:
        byte = op == 0x5B
        return make(f"MOV{'B' if byte else ''} [{reg4(arg >> 4)}++], [{reg4(arg)}++]")
    if op in {0x68, 0x69} and index + 1 < len(words):
        byte = op == 0x69
        return make(f"MOV{'B' if byte else ''} {reg8(arg)}, #0x{extword():04X}", 2)
    if op in {0x6A, 0x6B} and index + 1 < len(words):
        byte = op == 0x6B
        src = byte_reg4(arg >> 4) if byte else reg4(arg >> 4)
        return make(f"MOV{'B' if byte else ''} [{reg4(arg)}+0x{extword():04X}], {src}", 2)
    if op in {0x78, 0x79} and index + 1 < len(words):
        byte = op == 0x79
        dst = byte_reg4(arg >> 4) if byte else reg4(arg >> 4)
        return make(f"MOV{'B' if byte else ''} {dst}, [{reg4(arg)}+0x{extword():04X}]", 2)
    if op in {0x88, 0x89} and index + 1 < len(words):
        byte = op == 0x89
        return make(f"MOV{'B' if byte else ''} {reg8(arg)}, [0x{extword():04X}]", 2)
    if op in {0x8A, 0x8B} and index + 1 < len(words) and arg < 0x10:
        byte = op == 0x8B
        return make(f"MOV{'B' if byte else ''} [{reg4(arg)}], [0x{extword():04X}]", 2)
    if op in {0x98, 0x99} and index + 1 < len(words):
        name = "MOVSE" if op == 0x98 else "MOVZE"
        return make(f"{name} {reg8(arg)}, [0x{extword():04X}]", 2)
    if op in {0xA8, 0xA9} and index + 1 < len(words):
        byte = op == 0xA9
        return make(f"MOV{'B' if byte else ''} [0x{extword():04X}], {reg8(arg)}", 2)
    if op in {0xB8, 0xB9} and index + 1 < len(words):
        name = "MOVSE" if op == 0xB8 else "MOVZE"
        return make(f"{name} [0x{extword():04X}], {reg8(arg)}", 2)

    if op == 0x0E:
        return make(f"EXCH {reg4(arg >> 4)}, {reg4(arg)}")

    # Shift/rotate and shift-buffer operations.
    if op in SHIFT_REG:
        return make(f"{SHIFT_REG[op]} {reg4(arg >> 4)}, {byte_reg4(arg)}")
    if op in SHIFT_IMM:
        return make(f"{SHIFT_IMM[op]} {reg4(arg >> 4)}, #0x{arg & 0xF:X}")
    if op in {0x2C, 0x2D, 0x3C, 0x3D}:
        name = {0x2C: "SL", 0x2D: "SR", 0x3C: "SLOSB", 0x3D: "SROSB"}[op]
        return make(f"{name} [{reg4(arg >> 4)}++], {byte_reg4(arg)}")

    # Unary arithmetic and DSP helpers.
    if op == 0x3E:
        if arg >> 4 == 0:
            return make(f"NEG {reg4(arg)}")
        if arg >> 4 == 1:
            return make(f"NEGB {byte_reg4(arg)}")
    if op in {0xC0, 0xC1}:
        # The Google Patents HTML OCR renders these rows as "C0 0n" / "C 1n".
        # Visual inspection of PDF pages 32-33 shows the regular nm operand.
        name = "MUL" if op == 0xC0 else "UMUL"
        return make(f"{name} {reg4(arg >> 4)}, {reg4(arg)}")
    if op in {0xC2, 0xC3, 0xC4, 0xC5} and arg >> 4 == 0:
        name = {0xC2: "DIV", 0xC3: "UDIV", 0xC4: "DIVL", 0xC5: "UDIVL"}[op]
        return make(f"{name} {reg4(arg)}")
    if op == 0xBE and index + 1 < len(words):
        tail = extword()
        kind = (arg >> 4) & 3
        invalid = bool(tail & 0xF0F0)
        invalid |= kind == 0 and ((tail >> 8) & 3 == 3 or tail & 3 == 3)
        invalid |= kind == 1 and bool(arg & 2)
        invalid |= kind in (2, 3) and bool(arg & 3)
        invalid |= kind == 2 and tail != 0
        if invalid:
            return make(f".word 0x{word:04X}, 0x{tail:04X}", 2,
                        flow="stop", note="reserved DSP operand/configuration")
        name = ("MAC", "MAC", "RNDST", "MULS")[kind]
        if kind != 2:
            name += "." + ("ss", "su", "us", "uu")[(arg >> 2) & 3]
        for bit, suffix in ((0x80, "r"), (0x40, "s")):
            if arg & bit:
                name += "." + suffix
        if kind == 0 and arg & 2:
            name += ".m"
        if kind in (0, 1) and arg & 1:
            name += ".-"
        if kind == 2:
            return make(name, 2)
        if kind in (1, 3):
            return make(f"{name} {reg4(tail >> 8)}, {reg4(tail)}", 2)
        def mac_pointer(axis, value):
            index = value & 3
            suffix = ("", "++", "--", f"+{axis}C{index}")[value >> 2]
            return f"[{axis}{index}{suffix}]"
        return make(f"{name} {mac_pointer('X', tail >> 8)}, {mac_pointer('Y', tail & 15)}", 2)

    if op == 0x1E and (arg >> 4) in EXP_OPS:
        name, indirect = EXP_OPS[arg >> 4]
        operand = f"[{reg4(arg)}++]" if indirect else reg4(arg)
        return make(f"{name} {operand}")

    # Compare-and-update.  The appendix prints 2E for CMPD2 imm4, but that
    # conflicts with LINK and breaks the otherwise exact 4E/5E, 4F/5F grid.
    # 5E is therefore used here; 2E remains LINK.
    if op in {0x4E, 0x5E, 0x4F, 0x5F}:
        name = {0x4E: "CMPD1", 0x5E: "CMPD2", 0x4F: "CMPI1", 0x5F: "CMPI2"}[op]
        return make(f"{name} {reg4(arg >> 4)}, #0x{arg & 0xF:X}")
    if op in {0x6E, 0x7E, 0x6F, 0x7F, 0x8E, 0x9E, 0x8F, 0x9F} and index + 1 < len(words):
        name = {
            0x6E: "CMPD1", 0x7E: "CMPD2", 0x6F: "CMPI1", 0x7F: "CMPI2",
            0x8E: "CMPD1", 0x9E: "CMPD2", 0x8F: "CMPI1", 0x9F: "CMPI2",
        }[op]
        operand = f"#0x{extword():04X}" if op < 0x80 else f"[0x{extword():04X}]"
        return make(f"{name} {reg8(arg)}, {operand}", 2)

    # Bit manipulation.
    if op in BIT_BINARY and index + 1 < len(words):
        extra = extword()
        z_addr = (extra >> 8) & 0xFF
        z_bit = extra & 0xF
        q_bit = (extra >> 4) & 0xF
        return make(f"{BIT_BINARY[op]} BIT[0x{z_addr:02X}].{z_bit}, BIT[0x{arg:02X}].{q_bit}", 2)
    if 0xE0 <= op <= 0xEF:
        return make(f"BSET BIT[0x{arg:02X}].{op & 0xF}")
    if 0xF0 <= op <= 0xFF:
        return make(f"BCLR BIT[0x{arg:02X}].{op & 0xF}")

    # Calls, branches, returns.
    if op in {0xBC, 0xAC} and index + 1 < len(words) and arg >> 4 == 0:
        target = Address(address.segment, extword())
        cond = CONDITIONS.get(arg & 0xF, f"CC{arg & 0xF:X}")
        name = "ACALL" if op == 0xBC else "AJMP"
        flow = "call" if op == 0xBC else ("jump" if (arg & 0xF) == 0 else "cjump")
        return make(f"{name} {cond}, {target}", 2, flow, (target,))
    if op in {0xBD, 0xAD} and index + 1 < len(words):
        target = Address(arg, extword())
        name = "SCALL" if op == 0xBD else "SJMP"
        return make(f"{name} {target}", 2, "call" if op == 0xBD else "jump", (target,))
    if op in {0xCC, 0xCE}:
        cond = CONDITIONS.get(arg >> 4, f"CC{arg >> 4:X}")
        name = "ICALL" if op == 0xCC else "IJMP"
        flow = "call" if op == 0xCC else ("stop" if (arg >> 4) == 0 else "next")
        return make(f"{name} {cond}, [{reg4(arg)}]", flow=flow)
    if op == 0xCD:
        target = relative_target(address, 1, signed8(arg))
        return make(f"RCALL {target} ; rel {signed8(arg):+d}", flow="call", targets=(target,))
    if 0xD0 <= op <= 0xDE:
        cond_code = op & 0xF
        target = relative_target(address, 1, signed8(arg))
        flow = "jump" if cond_code == 0 else "cjump"
        return make(f"RJMP {CONDITIONS[cond_code]}, {target} ; rel {signed8(arg):+d}", flow=flow, targets=(target,))
    if op in BIT_BRANCH and index + 1 < len(words):
        extra = extword()
        bit = (extra >> 8) & 0xF
        rel = signed8(extra & 0xFF)
        target = relative_target(address, 2, rel)
        return make(f"{BIT_BRANCH[op]} BIT[0x{arg:02X}].{bit}, {target} ; rel {rel:+d}", 2, "cjump", (target,))
    if op == 0xC6 and arg in {0x00, 0x10, 0x20}:
        return make({0x00: "RET", 0x10: "RETI", 0x20: "RETS"}[arg], flow="stop")

    # Miscellaneous and stack instructions.
    if op == 0x2E:
        return make(f"LINK #0x{arg:02X}")
    if op == 0x2F and arg == 0:
        return make("UNLINK")
    if op == 0x1F:
        name = "POP" if arg & 0x80 else "PUSH"
        return make(f"{name} {reg8(arg & 0x7F)}")
    if op == 0x3F:
        if arg <= 0x03:
            return make(f"CRIT #{arg & 0x3}")
        if 0x10 <= arg <= 0x13:
            return make(f"IGNDS #{arg & 0x3}")
        if arg == 0xFF:
            return make("RESET", flow="stop")
    if op == 0xC7 and arg == 0:
        return make("NOP")
    if op == 0xBF and arg == 0 and index + 1 < len(words):
        return make(f"REP #0x{extword():04X}", 2)
    if op == 0xCF and arg >> 4 == 0:
        return make(f"REP {reg4(arg)}")
    if op in {0xAE, 0xAF} and index + 1 < len(words):
        count = f"#0x{arg:02X}" if op == 0xAE else reg4(arg)
        return make(f"REPB {count}, encoded_end=0x{extword():04X}", 2)
    if op == 0x0F:
        return make(f"TRAP #0x{arg:02X}", flow="call")

    return make(f".word 0x{word:04X}", flow="stop", note="unknown/reserved encoding")


def erased_padding(words: list[int], index: int, run: int = 8) -> bool:
    value = words[index]
    return value in {0x0000, 0xFFFF} and words[index : index + run] == [value] * run


def analyse(words: list[int], base_segment: int, seeds: list[Address]):
    queue = deque(seeds)
    decoded: dict[int, Instruction] = {}
    occupied: dict[int, int] = {}
    xrefs: dict[int, list[Address]] = defaultdict(list)
    unresolved: Counter[Address] = Counter()
    conflicts: list[tuple[Address, int]] = []

    while queue:
        address = queue.popleft()
        index = index_for_address(address, base_segment, len(words))
        if index is None:
            unresolved[address] += 1
            continue
        if index in decoded:
            continue
        if index in occupied and occupied[index] != index:
            conflicts.append((address, occupied[index]))
            continue
        if erased_padding(words, index):
            continue

        instruction = decode(words, index, base_segment)
        decoded[index] = instruction
        for offset in range(instruction.size):
            word_index = index + offset
            if word_index in occupied and occupied[word_index] != index:
                conflicts.append((address_for_index(word_index, base_segment), occupied[word_index]))
            occupied[word_index] = index

        local_targets: list[Address] = []
        for target in instruction.targets:
            target_index = index_for_address(target, base_segment, len(words))
            if target_index is None:
                unresolved[target] += 1
            else:
                xrefs[target_index].append(instruction.address)
                local_targets.append(target)

        next_address = address_for_index(index + instruction.size, base_segment)
        if instruction.flow == "next":
            queue.append(next_address)
        elif instruction.flow == "call":
            queue.extend(local_targets)
            queue.append(next_address)
        elif instruction.flow == "cjump":
            queue.extend(local_targets)
            queue.append(next_address)
        elif instruction.flow == "jump":
            queue.extend(local_targets)

    return decoded, xrefs, unresolved, conflicts


def make_seeds(base_segment: int) -> tuple[list[Address], dict[Address, str]]:
    # Start from the reset stub. Direct control flow from it reaches the main
    # image. Exception slot units differ between core documentation and this
    # SoC image, so they are left to the explicitly linear vector-area listing.
    named = {Address(base_segment, 0x0000): "vector_reset"}
    return list(named), named


def write_listing(
    path: Path,
    decoded: dict[int, Instruction],
    xrefs: dict[int, list[Address]],
    seed_names: dict[Address, str],
    base_segment: int,
) -> None:
    call_targets: set[int] = set()
    all_targets: set[int] = set(xrefs)
    for instruction in decoded.values():
        if instruction.flow == "call":
            for target in instruction.targets:
                target_index = index_for_address(target, base_segment, 1 << 30)
                if target_index is not None:
                    call_targets.add(target_index)

    lines = [
        "; NP560+ reachable-code disassembly",
        "; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)",
        f"; image mapping used here: file byte 0 = {base_segment:02X}:0000",
        "; addresses are CS:PC; raw words are shown in CPU numeric order",
        "",
    ]
    previous_end: int | None = None
    for index in sorted(decoded):
        instruction = decoded[index]
        if previous_end is not None and index > previous_end:
            lines.append(f"; ---- gap: {index - previous_end} word(s), data or unreachable code ----")
            lines.append("")
        elif previous_end is not None and index < previous_end:
            lines.append(f"; ---- overlapping control-flow decode at {instruction.address} ----")

        if instruction.address in seed_names:
            lines.append(f"{seed_names[instruction.address]}:")
        elif index in call_targets:
            lines.append(f"sub_{instruction.address.segment:02X}_{instruction.address.pc:04X}:")
        elif index in all_targets:
            lines.append(f"loc_{instruction.address.segment:02X}_{instruction.address.pc:04X}:")

        refs = xrefs.get(index, [])
        if refs:
            lines.append("; xref: " + ", ".join(str(ref) for ref in refs[:12]) + (" ..." if len(refs) > 12 else ""))
        raw = " ".join(f"{value:04X}" for value in instruction.words)
        comment = f" ; {instruction.note}" if instruction.note else ""
        lines.append(f"{instruction.address}  {raw:<9}  {instruction.text}{comment}")
        previous_end = max(previous_end or 0, index + instruction.size)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_vectors(path: Path, words: list[int], base_segment: int, count: int = 0x120) -> None:
    lines = [
        "; Linear decode of the NP560+ reset/exception-vector area",
        "; This file is intentionally linear; resource/data words may appear as instructions.",
        "",
    ]
    index = 0
    limit = min(count, len(words))
    while index < limit:
        instruction = decode(words, index, base_segment)
        raw = " ".join(f"{value:04X}" for value in instruction.words)
        note = f" ; {instruction.note}" if instruction.note else ""
        lines.append(f"{instruction.address}  {raw:<9}  {instruction.text}{note}")
        index += instruction.size
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(
    path: Path,
    image: Path,
    image_bytes: bytes,
    base_segment: int,
    decoded: dict[int, Instruction],
    unresolved: Counter[Address],
    conflicts: list[tuple[Address, int]],
) -> None:
    unknown = [ins for ins in decoded.values() if ins.text.startswith(".word")]
    calls = [ins for ins in decoded.values() if ins.flow == "call"]
    jumps = [ins for ins in decoded.values() if ins.flow in {"jump", "cjump"}]
    local_words = sum(ins.size for ins in decoded.values())
    top_unresolved = unresolved.most_common(20)
    lines = [
        "# NP560+ V3.80 静态反汇编报告",
        "",
        f"- 输入：`{image}`",
        f"- 大小：{len(image_bytes):,} 字节（{len(image_bytes) // 2:,} 个 16 位字）",
        f"- SHA-256：`{hashlib.sha256(image_bytes).hexdigest()}`",
        f"- CPU 字节序：16 位小端；反汇编地址以 `CS:PC` 表示",
        f"- 映射假设：文件首字节对应 `{base_segment:02X}:0000`，连续覆盖 "
        f"0x{len(image_bytes) // 0x10000:X} 个 64KB 代码段",
        "- ISA 依据：[CN1916884A 指令集附录](https://patents.google.com/patent/CN1916884A/zh)",
        "",
        "## 结果",
        "",
        f"- 控制流可达指令：{len(decoded):,} 条 / {local_words:,} 个字",
        f"- 直接或间接调用类指令：{len(calls):,} 条",
        f"- 跳转类指令：{len(jumps):,} 条",
        f"- 未识别/保留编码前沿：{len(unknown):,} 处",
        f"- 落入另一条指令中间的冲突目标：{len(conflicts):,} 处",
        "",
        "复位入口的确定性解码：",
        "",
        "```asm",
    ]
    entry_instructions: list[Instruction] = []
    for reset_index in (0, 2):
        if reset_index in decoded:
            entry_instructions.append(decoded[reset_index])
    if 2 in decoded and decoded[2].targets:
        main_index = index_for_address(decoded[2].targets[0], base_segment, len(image_bytes) // 2)
        while main_index is not None and main_index in decoded and len(entry_instructions) < 10:
            ins = decoded[main_index]
            entry_instructions.append(ins)
            main_index += ins.size
    for ins in entry_instructions:
        raw = " ".join(f"{value:04X}" for value in ins.words)
        lines.append(f"{ins.address}  {raw:<9}  {ins.text}")
    lines += ["```", "", "## 尚未解析到本文件内的远地址（按引用次数）", ""]
    if top_unresolved:
        lines.extend(f"- `{address}`：{count} 次" for address, count in top_unresolved)
    else:
        lines.append("- 无")
    lines += [
        "",
        "## 边界说明",
        "",
        "这是基于专利编码表的第一版静态反汇编，不是厂商符号版源码。SoC 专用 SFR 名称尚未公开，因此 8 位寄存器号保留为 `REG[0xNN]`。图形、字库、语音及压缩资源不会强行线性解码；只有从复位入口和直接控制流能够到达的区域进入主清单。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--base-segment", type=lambda value: int(value, 0), default=DEFAULT_BASE_SEGMENT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "doc",
    )
    args = parser.parse_args()

    image = args.image.resolve()
    image_bytes = image.read_bytes()
    if len(image_bytes) % 2:
        raise SystemExit("firmware size is not an even number of bytes")
    words = [int.from_bytes(image_bytes[i : i + 2], "little") for i in range(0, len(image_bytes), 2)]

    seeds, seed_names = make_seeds(args.base_segment)
    decoded, xrefs, unresolved, conflicts = analyse(words, args.base_segment, seeds)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_listing(output_dir / "NP560_reachable_code.asm", decoded, xrefs, seed_names, args.base_segment)
    write_vectors(output_dir / "NP560_vectors_linear.asm", words, args.base_segment)
    write_report(
        output_dir / "NP560_disassembly_report.md",
        image,
        image_bytes,
        args.base_segment,
        decoded,
        unresolved,
        conflicts,
    )

    print(f"decoded {len(decoded):,} reachable instructions")
    print(f"wrote {output_dir / 'NP560_reachable_code.asm'}")
    print(f"wrote {output_dir / 'NP560_vectors_linear.asm'}")
    print(f"wrote {output_dir / 'NP560_disassembly_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
