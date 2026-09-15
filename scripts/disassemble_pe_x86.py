#!/usr/bin/env python3
"""Disassemble a virtual-address range from a PE32 x86 executable."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_32, Cs


def _word(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _dword(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def va_to_offset(data: bytes, va: int) -> int:
    pe = _dword(data, 0x3C)
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("not a PE image")
    coff = pe + 4
    section_count = _word(data, coff + 2)
    optional_size = _word(data, coff + 16)
    optional = coff + 20
    if _word(data, optional) != 0x10B:
        raise ValueError("only PE32 images are supported")
    image_base = _dword(data, optional + 28)
    rva = va - image_base
    section_table = optional + optional_size
    for index in range(section_count):
        section = section_table + index * 40
        virtual_size = _dword(data, section + 8)
        virtual_address = _dword(data, section + 12)
        raw_size = _dword(data, section + 16)
        raw_offset = _dword(data, section + 20)
        extent = max(virtual_size, raw_size)
        if virtual_address <= rva < virtual_address + extent:
            delta = rva - virtual_address
            if delta >= raw_size:
                raise ValueError(f"VA 0x{va:X} is in a zero-filled section tail")
            return raw_offset + delta
    raise ValueError(f"VA 0x{va:X} does not belong to a PE section")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("start", type=lambda value: int(value, 0))
    parser.add_argument("end", type=lambda value: int(value, 0))
    args = parser.parse_args()
    if args.end <= args.start:
        parser.error("end must be greater than start")

    data = args.image.read_bytes()
    start_offset = va_to_offset(data, args.start)
    end_offset = va_to_offset(data, args.end - 1) + 1
    disassembler = Cs(CS_ARCH_X86, CS_MODE_32)
    for instruction in disassembler.disasm(
        data[start_offset:end_offset], args.start,
    ):
        raw = instruction.bytes.hex(" ")
        print(
            f"{instruction.address:08X}  {raw:<24} "
            f"{instruction.mnemonic:<8} {instruction.op_str}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
