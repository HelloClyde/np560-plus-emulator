#!/usr/bin/env python3
"""Instruction-level emulator for the King Billion DMCU in the Noah NP560+.

The emulator loads NP560.PRG at physical program address 0x20:0000.  Program
addresses are word-addressed (CS:PC); instructions are 16-bit little-endian.
It implements the integer core, control flow, stack, data movement, bit
operations, shifts, multiply/divide, and a useful subset of DSP operations.

The NP560 SoC's boot ROM and peripherals are not present in the update image.
Calls outside the loaded program image can therefore be logged and returned as
ROM-service stubs, or treated as errors with --rom-stub error.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "disassembly"))
import np560_disasm as dasm  # noqa: E402


DEFAULT_IMAGE = ROOT / "NP560+V3.80版系统升级程序" / "NP560.PRG"
PROGRAM_BASE = 0x200000
PROGRAM_BASE_SEGMENT = 0x20
DATA_SIZE = 0x10000
FP_REGISTER = 11
SP_REGISTER = 15
MASK16 = 0xFFFF
MASK40 = (1 << 40) - 1


class EmulationError(RuntimeError):
    pass


class ProgramFault(EmulationError):
    pass


class UnsupportedInstruction(EmulationError):
    pass


class TrapRaised(EmulationError):
    pass


def signed(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    value &= (1 << bits) - 1
    return value - (1 << bits) if value & sign else value


def signed8(value: int) -> int:
    return signed(value, 8)


def signed16(value: int) -> int:
    return signed(value, 16)


def parse_address(text: str) -> dasm.Address:
    try:
        segment, pc = text.split(":", 1)
        return dasm.Address(int(segment, 16), int(pc, 16))
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("地址格式应为 CS:PC，例如 33:4F50") from exc


@dataclass
class Flags:
    z: bool = False
    c: bool = False
    n: bool = False
    v: bool = False

    def pack(self) -> int:
        return int(self.z) | (int(self.c) << 1) | (int(self.n) << 2) | (int(self.v) << 3)

    def unpack(self, value: int) -> None:
        self.z = bool(value & 0x1)
        self.c = bool(value & 0x2)
        self.n = bool(value & 0x4)
        self.v = bool(value & 0x8)

    def __str__(self) -> str:
        return "".join(letter if state else "-" for letter, state in zip("ZCNV", (self.z, self.c, self.n, self.v)))


class ProgramMemory:
    def __init__(self, image: bytes, base: int = PROGRAM_BASE):
        if len(image) & 1:
            raise ValueError("program image has an odd byte count")
        self.image = image
        self.base = base
        self.end = base + len(image) // 2
        self.words = [int.from_bytes(image[i : i + 2], "little") for i in range(0, len(image), 2)]

    @staticmethod
    def physical(address: dasm.Address) -> int:
        return ((address.segment & 0xFF) << 16) | (address.pc & 0xFFFF)

    def contains(self, address: dasm.Address, size: int = 1) -> bool:
        physical = self.physical(address)
        return self.base <= physical and physical + size <= self.end

    def offset(self, address: dasm.Address) -> int:
        physical = self.physical(address)
        offset = (physical - self.base) * 2
        if offset < 0 or offset + 2 > len(self.image):
            raise ProgramFault(f"unmapped program address {address}")
        return offset

    def read16(self, address: dasm.Address) -> int:
        offset = self.offset(address)
        return int.from_bytes(self.image[offset : offset + 2], "little")

    def instruction(self, address: dasm.Address) -> dasm.Instruction:
        index = self.offset(address) // 2
        return dasm.decode(self.words, index, self.base >> 16)


class DataMemory:
    """64 KiB byte-addressed X/data memory with optional MMIO hooks."""

    def __init__(self, size: int = DATA_SIZE):
        self.data = bytearray(size)
        self.read_hooks: dict[int, Callable[[int], int]] = {}
        self.write_hooks: dict[int, Callable[[int, int], None]] = {}

    def read8(self, address: int) -> int:
        address &= 0xFFFF
        if address in self.read_hooks:
            return self.read_hooks[address](address) & 0xFF
        return self.data[address]

    def write8(self, address: int, value: int) -> None:
        address &= 0xFFFF
        value &= 0xFF
        if address in self.write_hooks:
            self.write_hooks[address](address, value)
        else:
            self.data[address] = value

    def read16(self, address: int) -> int:
        address &= 0xFFFF
        return self.read8(address) | (self.read8(address + 1) << 8)

    def write16(self, address: int, value: int) -> None:
        address &= 0xFFFF
        self.write8(address, value)
        self.write8(address + 1, value >> 8)


class DMCU:
    def __init__(
        self,
        program: ProgramMemory,
        data: DataMemory | None = None,
        *,
        rom_stub: str = "return",
        trace: bool = False,
    ):
        self.program = program
        self.data = data or DataMemory()
        self.gpr = [0] * 16
        self.sfr = [0] * 256
        self.cs = PROGRAM_BASE_SEGMENT
        self.pc = 0
        self.flags = Flags()
        self.shift_buffer = 0
        self.steps = 0
        self.halted = False
        self.halt_reason = ""
        self.rom_stub = rom_stub
        self.trace = trace
        self.breakpoints: set[dasm.Address] = set()
        self.rom_calls: Counter[dasm.Address] = Counter()
        self.repeat_address: dasm.Address | None = None
        self.repeat_remaining = 0
        self.segmented_interrupts = True
        self.gpr[SP_REGISTER] = 0xFFFE
        self.gpr[FP_REGISTER] = 0xFFFE

    @property
    def address(self) -> dasm.Address:
        return dasm.Address(self.cs, self.pc)

    @property
    def sp(self) -> int:
        return self.gpr[SP_REGISTER]

    @sp.setter
    def sp(self, value: int) -> None:
        self.gpr[SP_REGISTER] = value & MASK16

    @property
    def fp(self) -> int:
        return self.gpr[FP_REGISTER]

    @fp.setter
    def fp(self, value: int) -> None:
        self.gpr[FP_REGISTER] = value & MASK16

    def reset(self, start: dasm.Address | None = None) -> None:
        self.gpr[:] = [0] * 16
        self.sfr[:] = [0] * 256
        self.flags = Flags()
        self.shift_buffer = 0
        self.cs = (start or dasm.Address(PROGRAM_BASE_SEGMENT, 0)).segment
        self.pc = (start or dasm.Address(PROGRAM_BASE_SEGMENT, 0)).pc
        self.sp = 0xFFFE
        self.fp = 0xFFFE
        self.steps = 0
        self.halted = False
        self.halt_reason = ""
        self.rom_calls.clear()
        self.repeat_address = None
        self.repeat_remaining = 0

    def _gpr_read(self, number: int, width: int = 16) -> int:
        value = self.gpr[number & 0xF]
        return value & (0xFF if width == 8 else MASK16)

    def _gpr_write(self, number: int, value: int, width: int = 16) -> None:
        number &= 0xF
        if width == 8:
            self.gpr[number] = (self.gpr[number] & 0xFF00) | (value & 0xFF)
        else:
            self.gpr[number] = value & MASK16

    def _sfr_read(self, number: int, width: int = 16) -> int:
        value = self.sfr[number & 0xFF]
        return value & (0xFF if width == 8 else MASK16)

    def _sfr_write(self, number: int, value: int, width: int = 16) -> None:
        number &= 0xFF
        if width == 8:
            self.sfr[number] = (self.sfr[number] & 0xFF00) | (value & 0xFF)
        else:
            self.sfr[number] = value & MASK16

    def push(self, value: int) -> None:
        self.sp = self.sp - 2
        self.data.write16(self.sp, value)

    def pop(self) -> int:
        value = self.data.read16(self.sp)
        self.sp = self.sp + 2
        return value

    def _condition(self, code: int) -> bool:
        z, c, n, v = self.flags.z, self.flags.c, self.flags.n, self.flags.v
        tests = {
            0x0: True,
            0x1: z,
            0x2: not z,
            0x3: v,
            0x4: not v,
            0x5: c,
            0x6: not c,
            0x7: n,
            0x8: not n,
            0x9: n != v,
            0xA: not (z or c),
            0xB: not ((n != v) or z),
            0xC: z or c,
            0xD: (n != v) or z,
            0xE: n == v,
        }
        return tests.get(code, False)

    def _logic_flags(self, result: int, width: int) -> None:
        mask = (1 << width) - 1
        result &= mask
        self.flags.z = result == 0
        self.flags.n = bool(result & (1 << (width - 1)))
        self.flags.c = False
        self.flags.v = False

    def _add(self, left: int, right: int, carry: int, width: int, chained_z: bool) -> int:
        mask = (1 << width) - 1
        sign_bit = 1 << (width - 1)
        total = left + right + carry
        result = total & mask
        self.flags.c = total > mask
        self.flags.v = bool((~(left ^ right) & (left ^ result) & sign_bit) != 0)
        self.flags.n = bool(result & sign_bit)
        self.flags.z = (self.flags.z and result == 0) if chained_z else result == 0
        return result

    def _sub(self, left: int, right: int, borrow: int, width: int, chained_z: bool) -> int:
        mask = (1 << width) - 1
        sign_bit = 1 << (width - 1)
        subtrahend = right + borrow
        result = (left - subtrahend) & mask
        self.flags.c = left < subtrahend  # DMCU C is the borrow flag.
        self.flags.v = bool(((left ^ right) & (left ^ result) & sign_bit) != 0)
        self.flags.n = bool(result & sign_bit)
        self.flags.z = (self.flags.z and result == 0) if chained_z else result == 0
        return result

    def _alu(self, operation: int, left: int, right: int, width: int) -> int:
        mask = (1 << width) - 1
        left &= mask
        right &= mask
        if operation == 0x0:
            return self._add(left, right, 0, width, False)
        if operation == 0x1:
            return self._add(left, right, int(self.flags.c), width, True)
        if operation == 0x2:
            return self._sub(left, right, 0, width, False)
        if operation == 0x3:
            return self._sub(left, right, int(self.flags.c), width, True)
        if operation == 0x4:
            result = left & right
        elif operation == 0x5:
            result = left | right
        elif operation == 0x6:
            return self._sub(left, right, 0, width, False)
        elif operation == 0x7:
            result = left ^ right
        else:
            raise AssertionError(operation)
        self._logic_flags(result, width)
        return result & mask

    def _acc_read(self) -> int:
        return ((self.gpr[5] & 0xFF) << 32) | (self.gpr[6] << 16) | self.gpr[7]

    def _acc_write(self, value: int) -> None:
        value &= MASK40
        self.gpr[5] = value >> 32
        self.gpr[6] = (value >> 16) & MASK16
        self.gpr[7] = value & MASK16

    def _bit_read(self, address: int, bit: int) -> int:
        return (self.data.read16(address) >> (bit & 0xF)) & 1

    def _bit_write(self, address: int, bit: int, value: int) -> None:
        current = self.data.read16(address)
        mask = 1 << (bit & 0xF)
        self.data.write16(address, (current | mask) if value else (current & ~mask))

    def _trace_line(self, instruction: dasm.Instruction) -> None:
        raw = " ".join(f"{word:04X}" for word in instruction.words)
        print(f"{self.steps:08d} {self.address}  {raw:<9} {instruction.text:<42} F={self.flags} SP={self.sp:04X}")

    def _rom_service(self, target: dasm.Address) -> bool:
        if self.program.contains(target):
            return False
        self.rom_calls[target] += 1
        if self.rom_stub == "error":
            raise ProgramFault(f"call to unavailable ROM service {target}")
        if self.trace:
            print(f"         [ROM stub {target}: immediate return]")
        return True

    def _execute_alu_family(self, op: int, arg: int, ext: int | None) -> bool:
        operation = op & 0xF
        high = op >> 4
        if operation not in dasm.ALU_OPS:
            return False
        byte_mode = high in {0x0, 0x2, 0x4, 0x6, 0x8, 0xA}
        width = 8 if byte_mode else 16
        destination_kind = ""
        destination = 0

        if high in {0x0, 0x1}:
            destination_kind = "gpr"
            destination = arg >> 4
            left = self._gpr_read(destination, width)
            right = self._gpr_read(arg, width)
        elif high in {0x2, 0x3}:
            destination_kind = "gpr"
            destination = arg >> 4
            pointer_register = 8 + (arg & 0x7)
            pointer = self.gpr[pointer_register]
            left = self._gpr_read(destination, width)
            right = self.data.read8(pointer) if byte_mode else self.data.read16(pointer)
            if arg & 0x8:
                self.gpr[pointer_register] = (pointer + width // 8) & MASK16
        elif high in {0x4, 0x5}:
            destination_kind = "gpr"
            destination = arg >> 4
            left = self._gpr_read(destination, width)
            right = arg & 0xF
        elif high in {0x6, 0x7} and ext is not None:
            destination_kind = "sfr"
            destination = arg
            left = self._sfr_read(destination, width)
            right = ext & ((1 << width) - 1)
        elif high in {0x8, 0x9} and ext is not None:
            destination_kind = "sfr"
            destination = arg
            left = self._sfr_read(destination, width)
            right = self.data.read8(ext) if byte_mode else self.data.read16(ext)
        elif high in {0xA, 0xB} and operation != 0x6 and ext is not None:
            destination_kind = "memory"
            destination = ext
            left = self.data.read8(ext) if byte_mode else self.data.read16(ext)
            right = self._sfr_read(arg, width)
        else:
            return False

        result = self._alu(operation, left, right, width)
        if operation != 0x6:
            if destination_kind == "gpr":
                self._gpr_write(destination, result, width)
            elif destination_kind == "sfr":
                self._sfr_write(destination, result, width)
            else:
                (self.data.write8 if byte_mode else self.data.write16)(destination, result)
        return True

    def _execute_move(self, op: int, arg: int, ext: int | None) -> bool:
        if op in {0x08, 0x09}:
            width = 8 if op == 0x09 else 16
            self._gpr_write(arg >> 4, self._gpr_read(arg, width), width)
        elif op in {0x0A, 0x0B}:
            width = 8 if op == 0x0B else 16
            writer = self.data.write8 if width == 8 else self.data.write16
            writer(self.gpr[arg >> 4], self._gpr_read(arg, width))
        elif op in {0x18, 0x19}:
            value = self._gpr_read(arg, 8)
            if op == 0x18:
                value = signed8(value) & MASK16
            self._gpr_write(arg >> 4, value)
        elif op in {0x1A, 0x1B}:
            width = 8 if op == 0x1B else 16
            pointer_register = arg >> 4
            pointer = self.gpr[pointer_register]
            (self.data.write8 if width == 8 else self.data.write16)(pointer, self._gpr_read(arg, width))
            self.gpr[pointer_register] = (pointer + width // 8) & MASK16
        elif op in {0x28, 0x29}:
            width = 8 if op == 0x29 else 16
            value = (self.data.read8 if width == 8 else self.data.read16)(self.gpr[arg & 0xF])
            self._gpr_write(arg >> 4, value, width)
        elif op in {0x2A, 0x2B}:
            width = 8 if op == 0x2B else 16
            value = (self.data.read8 if width == 8 else self.data.read16)(self.gpr[arg & 0xF])
            (self.data.write8 if width == 8 else self.data.write16)(self.gpr[arg >> 4], value)
        elif op in {0x38, 0x39}:
            width = 8 if op == 0x39 else 16
            pointer_register = arg & 0xF
            pointer = self.gpr[pointer_register]
            value = (self.data.read8 if width == 8 else self.data.read16)(pointer)
            self._gpr_write(arg >> 4, value, width)
            self.gpr[pointer_register] = (pointer + width // 8) & MASK16
        elif op in {0x3A, 0x3B}:
            width = 8 if op == 0x3B else 16
            source_register = arg & 0xF
            source = self.gpr[source_register]
            value = (self.data.read8 if width == 8 else self.data.read16)(source)
            (self.data.write8 if width == 8 else self.data.write16)(self.gpr[arg >> 4], value)
            self.gpr[source_register] = (source + width // 8) & MASK16
        elif op in {0x48, 0x49}:
            self._gpr_write(arg >> 4, arg & 0xF, 8 if op == 0x49 else 16)
        elif op in {0x58, 0x59}:
            width = 8 if op == 0x59 else 16
            pointer_register = arg >> 4
            self.gpr[pointer_register] = (self.gpr[pointer_register] - width // 8) & MASK16
            (self.data.write8 if width == 8 else self.data.write16)(self.gpr[pointer_register], self._gpr_read(arg, width))
        elif op in {0x5A, 0x5B}:
            width = 8 if op == 0x5B else 16
            dst_register, src_register = arg >> 4, arg & 0xF
            value = (self.data.read8 if width == 8 else self.data.read16)(self.gpr[src_register])
            (self.data.write8 if width == 8 else self.data.write16)(self.gpr[dst_register], value)
            self.gpr[dst_register] = (self.gpr[dst_register] + width // 8) & MASK16
            self.gpr[src_register] = (self.gpr[src_register] + width // 8) & MASK16
        elif op in {0x68, 0x69} and ext is not None:
            self._sfr_write(arg, ext, 8 if op == 0x69 else 16)
        elif op in {0x6A, 0x6B} and ext is not None:
            width = 8 if op == 0x6B else 16
            address = (self.gpr[arg & 0xF] + ext) & MASK16
            (self.data.write8 if width == 8 else self.data.write16)(address, self._gpr_read(arg >> 4, width))
        elif op in {0x78, 0x79} and ext is not None:
            width = 8 if op == 0x79 else 16
            address = (self.gpr[arg & 0xF] + ext) & MASK16
            value = (self.data.read8 if width == 8 else self.data.read16)(address)
            self._gpr_write(arg >> 4, value, width)
        elif op in {0x88, 0x89} and ext is not None:
            width = 8 if op == 0x89 else 16
            self._sfr_write(arg, (self.data.read8 if width == 8 else self.data.read16)(ext), width)
        elif op in {0x8A, 0x8B} and ext is not None and arg < 0x10:
            width = 8 if op == 0x8B else 16
            value = (self.data.read8 if width == 8 else self.data.read16)(ext)
            (self.data.write8 if width == 8 else self.data.write16)(self.gpr[arg], value)
        elif op in {0x98, 0x99} and ext is not None:
            value = self.data.read8(ext)
            self._sfr_write(arg, (signed8(value) & MASK16) if op == 0x98 else value)
        elif op in {0xA8, 0xA9} and ext is not None:
            width = 8 if op == 0xA9 else 16
            (self.data.write8 if width == 8 else self.data.write16)(ext, self._sfr_read(arg, width))
        elif op in {0xB8, 0xB9} and ext is not None:
            value = self._sfr_read(arg, 8)
            self.data.write16(ext, (signed8(value) & MASK16) if op == 0xB8 else value)
        else:
            return False
        return True

    def _execute_shift(self, op: int, arg: int) -> bool:
        if op not in dasm.SHIFT_REG and op not in dasm.SHIFT_IMM and op not in {0x2C, 0x2D, 0x3C, 0x3D}:
            return False
        if op in dasm.SHIFT_REG:
            name = dasm.SHIFT_REG[op]
            count = signed8(self._gpr_read(arg, 8))
            destination_register = arg >> 4
            memory_destination = False
        elif op in dasm.SHIFT_IMM:
            name = dasm.SHIFT_IMM[op]
            count = arg & 0xF
            destination_register = arg >> 4
            memory_destination = False
        else:
            name = {0x2C: "SL", 0x2D: "SR", 0x3C: "SLOSB", 0x3D: "SROSB"}[op]
            count = signed8(self._gpr_read(arg, 8))
            destination_register = arg >> 4
            memory_destination = True

        address = self.gpr[destination_register]
        value = self.data.read16(address) if memory_destination else self.gpr[destination_register]
        if count < 0:
            count = -count
            name = {"SL": "SR", "SR": "SL", "SLOSB": "SROSB", "SROSB": "SLOSB", "ASR": "ASL"}.get(name, name)
        count &= 0x7F
        overflow = False
        for _ in range(count):
            if name in {"SL", "SLOSB", "ASL"}:
                out = (value >> 15) & 1
                self.shift_buffer = ((self.shift_buffer << 1) | out) & MASK16
                value = (value << 1) & MASK16
                self.flags.c = bool(out)
            elif name in {"SR", "SROSB", "ASR"}:
                out = value & 1
                self.shift_buffer = (self.shift_buffer >> 1) | (out << 15)
                if name == "ASR":
                    value = (value >> 1) | (value & 0x8000)
                else:
                    value >>= 1
                self.flags.c = bool(out)
            elif name == "ROL":
                out = (value >> 15) & 1
                value = ((value << 1) | out) & MASK16
                self.flags.c = bool(out)
            elif name == "ROR":
                out = value & 1
                value = (value >> 1) | (out << 15)
                self.flags.c = bool(out)
            overflow |= self.flags.c
        if name in {"SLOSB", "SROSB"}:
            value |= self.shift_buffer
        self.flags.z = value == 0
        self.flags.n = bool(value & 0x8000)
        self.flags.v = overflow if name in {"ASL", "ASR"} else False
        if memory_destination:
            self.data.write16(address, value)
            self.gpr[destination_register] = (address + 2) & MASK16
        else:
            self.gpr[destination_register] = value
        return True

    def _execute_bit(self, op: int, arg: int, ext: int | None) -> bool:
        if 0xE0 <= op <= 0xEF:
            self._bit_write(arg, op & 0xF, 1)
            return True
        if 0xF0 <= op <= 0xFF:
            self._bit_write(arg, op & 0xF, 0)
            return True
        if op in dasm.BIT_BINARY and ext is not None:
            z_addr, z_bit = (ext >> 8) & 0xFF, ext & 0xF
            q_addr, q_bit = arg, (ext >> 4) & 0xF
            left, right = self._bit_read(z_addr, z_bit), self._bit_read(q_addr, q_bit)
            if op == 0x6C:
                result = left | right
            elif op == 0x6D:
                result = left ^ right
            elif op == 0x7C:
                result = right
            elif op == 0x7D:
                result = 1 - right
            elif op == 0x8C:
                result = left & right
            else:  # BCMP
                self.flags.z = left == right
                self.flags.n = left < right
                self.flags.c = left < right
                self.flags.v = False
                return True
            self._bit_write(z_addr, z_bit, result)
            self.flags.z = result == 0
            self.flags.n = bool(result)
            self.flags.c = False
            self.flags.v = False
            return True
        return False

    def _execute_compare_update(self, op: int, arg: int, ext: int | None) -> bool:
        names = {
            0x4E: (-1, "imm4"), 0x5E: (-2, "imm4"), 0x4F: (1, "imm4"), 0x5F: (2, "imm4"),
            0x6E: (-1, "imm"), 0x7E: (-2, "imm"), 0x6F: (1, "imm"), 0x7F: (2, "imm"),
            0x8E: (-1, "mem"), 0x9E: (-2, "mem"), 0x8F: (1, "mem"), 0x9F: (2, "mem"),
        }
        if op not in names:
            return False
        delta, kind = names[op]
        if kind == "imm4":
            register, operand = arg >> 4, arg & 0xF
            value = self.gpr[register]
            self._sub(value, operand, 0, 16, False)
            self.gpr[register] = (value + delta) & MASK16
        else:
            if ext is None:
                return False
            value = self._sfr_read(arg)
            operand = ext if kind == "imm" else self.data.read16(ext)
            self._sub(value, operand, 0, 16, False)
            self._sfr_write(arg, value + delta)
        return True

    def _execute_control(self, op: int, arg: int, ext: int | None, start: dasm.Address) -> bool:
        if op in {0xBC, 0xAC} and ext is not None and arg >> 4 == 0:
            if self._condition(arg & 0xF):
                target = dasm.Address(start.segment, ext)
                if op == 0xBC:
                    self.push(self.pc)
                self.pc = target.pc
            return True
        if op in {0xBD, 0xAD} and ext is not None:
            target = dasm.Address(arg, ext)
            if op == 0xBD:
                if self._rom_service(target):
                    return True
                self.push(self.pc)
                self.push(self.cs)
            self.cs, self.pc = target.segment, target.pc
            return True
        if op in {0xCC, 0xCE}:
            condition, register = arg >> 4, arg & 0xF
            if self._condition(condition):
                target = self.data.read16(self.gpr[register])
                if op == 0xCC:
                    self.push(self.pc)
                self.pc = target
            return True
        if op == 0xCD:
            self.push(self.pc)
            self.pc = (self.pc + signed8(arg)) & MASK16
            return True
        if 0xD0 <= op <= 0xDE:
            if self._condition(op & 0xF):
                self.pc = (self.pc + signed8(arg)) & MASK16
            return True
        if op in dasm.BIT_BRANCH and ext is not None:
            bit = (ext >> 8) & 0xF
            value = self._bit_read(arg, bit)
            take = value == 1 if op in {0x9A, 0x9C} else value == 0
            if take:
                if op == 0x9C:
                    self._bit_write(arg, bit, 0)
                elif op == 0x9D:
                    self._bit_write(arg, bit, 1)
                self.pc = (self.pc + signed8(ext & 0xFF)) & MASK16
            return True
        if op == 0xC6:
            if arg == 0x00:
                self.pc = self.pop()
            elif arg == 0x20:
                self.cs = self.pop() & 0xFF
                self.pc = self.pop()
            elif arg == 0x10:
                self.flags.unpack(self.pop())
                if self.segmented_interrupts:
                    self.cs = self.pop() & 0xFF
                self.pc = self.pop()
            else:
                return False
            return True
        return False

    def execute(self, instruction: dasm.Instruction, start: dasm.Address) -> None:
        word = instruction.words[0]
        op, arg = word >> 8, word & 0xFF
        ext = instruction.words[1] if instruction.size == 2 else None

        if self._execute_alu_family(op, arg, ext):
            return
        if self._execute_move(op, arg, ext):
            return
        if self._execute_shift(op, arg):
            return
        if self._execute_bit(op, arg, ext):
            return
        if self._execute_compare_update(op, arg, ext):
            return
        if self._execute_control(op, arg, ext, start):
            return

        if op == 0x0E:
            left, right = arg >> 4, arg & 0xF
            self.gpr[left], self.gpr[right] = self.gpr[right], self.gpr[left]
            return
        if op == 0x3E:
            width = 8 if arg >> 4 == 1 else 16
            if arg >> 4 not in {0, 1}:
                raise UnsupportedInstruction(f"unsupported NEG form 0x{word:04X}")
            register = arg & 0xF
            result = self._sub(0, self._gpr_read(register, width), 0, width, False)
            self._gpr_write(register, result, width)
            return
        if op in {0xC0, 0xC1}:
            left, right = self.gpr[arg >> 4], self.gpr[arg & 0xF]
            product = signed16(left) * signed16(right) if op == 0xC0 else left * right
            self._acc_write(product)
            self.flags.z = (product & 0xFFFFFFFF) == 0
            self.flags.n = bool(product & (1 << 31))
            self.flags.c = not (-0x8000 <= product <= 0xFFFF)
            self.flags.v = not (-0x80000000 <= product <= 0x7FFFFFFF)
            return
        if op in {0xC2, 0xC3, 0xC4, 0xC5} and arg >> 4 == 0:
            divisor_raw = self.gpr[arg & 0xF]
            if divisor_raw == 0:
                self.flags.v = True
                return
            if op in {0xC2, 0xC3}:
                dividend_raw = self.gpr[7]
            else:
                dividend_raw = (self.gpr[6] << 16) | self.gpr[7]
            if op in {0xC2, 0xC4}:
                dividend = signed(dividend_raw, 16 if op == 0xC2 else 32)
                divisor = signed16(divisor_raw)
                quotient = int(dividend / divisor)
                remainder = dividend - quotient * divisor
            else:
                quotient, remainder = divmod(dividend_raw, divisor_raw)
            self.gpr[7] = quotient & MASK16
            self.gpr[6] = remainder & MASK16
            self.flags.z = self.gpr[7] == 0
            self.flags.n = bool(self.gpr[7] & 0x8000)
            self.flags.c = False
            self.flags.v = not (-0x8000 <= quotient <= 0xFFFF)
            return
        if op == 0xBE and ext is not None:
            left_register, right_register = (ext >> 8) & 0xF, ext & 0xF
            left, right = self.gpr[left_register], self.gpr[right_register]
            signed_mode = (arg >> 2) & 0x3
            left_value = signed16(left) if signed_mode in {0, 1} else left
            right_value = signed16(right) if signed_mode in {0, 2} else right
            product = left_value * right_value
            accumulator = signed(self._acc_read(), 40)
            result = accumulator - product if arg & 1 else accumulator + product
            if arg & 0x80:
                result += 0x8000
                result &= ~0xFFFF
            self._acc_write(result)
            self.flags.z = (result & MASK40) == 0
            self.flags.n = bool(result & (1 << 39))
            self.flags.c = not (0 <= result <= MASK40)
            self.flags.v = not (-(1 << 39) <= result < (1 << 39))
            return
        if op == 0x1F:
            register = arg & 0x7F
            if arg & 0x80:
                self._sfr_write(register, self.pop())
            else:
                self.push(self._sfr_read(register))
            return
        if op == 0x2E:
            self.push(self.fp)
            self.fp = self.sp
            self.sp = self.sp - arg * 2
            return
        if op == 0x2F and arg == 0:
            self.sp = self.fp
            self.fp = self.pop()
            return
        if op == 0x3F:
            if arg in range(0x00, 0x04) or arg in range(0x10, 0x14):
                return  # CRIT / IGNDS prefix: atomicity/DS effects are peripheral-facing.
            if arg == 0xFF:
                self.halted = True
                self.halt_reason = "software RESET"
                return
        if op == 0xC7 and arg == 0:
            return
        if op == 0xBF and arg == 0 and ext is not None:
            self.repeat_address = self.address
            self.repeat_remaining = (ext + 1) & 0x1FFFF
            return
        if op == 0xCF and arg >> 4 == 0:
            self.repeat_address = self.address
            self.repeat_remaining = self.gpr[arg & 0xF] + 1
            return
        if op == 0x0F:
            if self.rom_stub == "return":
                self.rom_calls[dasm.Address(0x00, arg * 8)] += 1
                return
            raise TrapRaised(f"TRAP #{arg:02X}")
        raise UnsupportedInstruction(f"{start}: {instruction.text} (0x{word:04X})")

    def step(self) -> dasm.Instruction:
        if self.halted:
            raise EmulationError(self.halt_reason or "CPU halted")
        start = self.address
        instruction = self.program.instruction(start)
        if instruction.text.startswith(".word"):
            raise UnsupportedInstruction(f"{start}: unknown encoding 0x{instruction.words[0]:04X}")
        if self.trace:
            self._trace_line(instruction)

        self.pc = (self.pc + instruction.size) & MASK16
        self.execute(instruction, start)
        self.steps += 1

        if self.repeat_address == start:
            self.repeat_remaining -= 1
            if self.repeat_remaining > 0:
                self.cs, self.pc = start.segment, start.pc
            else:
                self.repeat_address = None
        return instruction

    def run(self, limit: int, *, stop_on_breakpoint: bool = True) -> int:
        executed = 0
        while not self.halted and executed < limit:
            if stop_on_breakpoint and self.address in self.breakpoints:
                self.halt_reason = f"breakpoint {self.address}"
                break
            self.step()
            executed += 1
        return executed

    def format_registers(self) -> str:
        rows = []
        for start in range(0, 16, 4):
            rows.append("  ".join(f"R{i:02d}={self.gpr[i]:04X}" for i in range(start, start + 4)))
        rows.append(f"CS:PC={self.address}  FLAGS={self.flags}  SB={self.shift_buffer:04X}  STEPS={self.steps}")
        return "\n".join(rows)


def monitor(cpu: DMCU) -> None:
    print("NP560 DMCU monitor: s [n], c [n], r, m addr [len], b CS:PC, bl, q")
    while True:
        try:
            line = input(f"({cpu.address})> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            line = "s"
        parts = shlex.split(line)
        command = parts[0].lower()
        try:
            if command in {"q", "quit", "exit"}:
                return
            if command in {"r", "regs"}:
                print(cpu.format_registers())
            elif command in {"s", "step"}:
                count = int(parts[1], 0) if len(parts) > 1 else 1
                for _ in range(count):
                    cpu.step()
                print(cpu.format_registers())
            elif command in {"c", "continue"}:
                count = int(parts[1], 0) if len(parts) > 1 else 100000
                cpu.run(count)
                print(cpu.halt_reason or f"stopped after {count} instructions")
            elif command in {"b", "break"} and len(parts) == 2:
                address = parse_address(parts[1])
                cpu.breakpoints.add(address)
                print(f"breakpoint added: {address}")
            elif command == "bl":
                print("\n".join(str(item) for item in sorted(cpu.breakpoints, key=lambda a: (a.segment, a.pc))) or "no breakpoints")
            elif command in {"m", "mem"} and len(parts) >= 2:
                address = int(parts[1], 0) & MASK16
                length = int(parts[2], 0) if len(parts) > 2 else 32
                for offset in range(0, length, 16):
                    chunk = [cpu.data.read8(address + offset + i) for i in range(min(16, length - offset))]
                    print(f"{(address + offset) & MASK16:04X}: " + " ".join(f"{value:02X}" for value in chunk))
            else:
                print("commands: s [n], c [n], r, m addr [len], b CS:PC, bl, q")
        except EmulationError as exc:
            print(f"stopped: {exc}")
        except (ValueError, IndexError) as exc:
            print(f"bad command: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--start", type=parse_address, default=dasm.Address(0x20, 0x0000))
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--break", dest="breakpoints", action="append", type=parse_address, default=[])
    parser.add_argument("--rom-stub", choices=("return", "error"), default="return")
    args = parser.parse_args()

    image_path = args.image.resolve()
    cpu = DMCU(ProgramMemory(image_path.read_bytes()), rom_stub=args.rom_stub, trace=args.trace)
    cpu.reset(args.start)
    cpu.breakpoints.update(args.breakpoints)

    print(f"loaded {image_path} ({len(cpu.program.image):,} bytes) at 20:0000")
    if args.interactive:
        monitor(cpu)
        return 0

    try:
        executed = cpu.run(args.steps)
    except EmulationError as exc:
        cpu.halt_reason = str(exc)
        executed = cpu.steps
    print(cpu.format_registers())
    print(f"executed={executed}, stop={cpu.halt_reason or 'step limit'}")
    if cpu.rom_calls:
        calls = ", ".join(f"{address}×{count}" for address, count in cpu.rom_calls.most_common(12))
        print(f"ROM stubs: {calls}")
    return 0 if not cpu.halt_reason or cpu.halt_reason.startswith("breakpoint") else 2


if __name__ == "__main__":
    raise SystemExit(main())
