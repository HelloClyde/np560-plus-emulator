#!/usr/bin/env python3
"""DMCU BAND/BOR/BXOR/BCMP two-input flag truth tables.

CN1916884A PDF pp.71/73/76/78 specify Z=NOR, C=AND, N=XOR, V=OR,
independent of which of the four instructions is used. All operands and PSR
are prepared by guest instructions. No NAND, host RAM injection or ROM stub.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from test_np560_dtu import read_sfr
from test_np560_mac import pack, run


# Literal manual truth table in PSR's physical Z,V,C,N bit order.
FLAGS = {(0, 0): 0x1, (0, 1): 0xA, (1, 0): 0xA, (1, 1): 0x6}
OPS = (("BAND", 0x8C), ("BOR", 0x6C), ("BXOR", 0x6D), ("BCMP", 0x8D))


def signed_word(value):
    return value - 65536 if value & 0x8000 else value


def check_table(qemu, output, icount):
    words = [0x6800, 2, 0x6810, 0, 0x6811, 1, 0x68FF, 0x6000]
    expected, cases = [], []
    for name, opcode in OPS:
        for (left, right), flags in FLAGS.items():
            destination = (0xA55A & ~0x80) | left << 7
            source = (0x5AA5 & ~8) | right << 3
            result = {"BAND": left & right, "BOR": left | right,
                      "BXOR": left ^ right, "BCMP": left}[name]
            final_destination = (destination & ~0x80) | result << 7
            words += [0x68F0, destination, 0x68F1, source,
                      0x6801, 0x05FF, opcode << 8 | 0x71, 0x7037]
            read_sfr(words, 1, 4)
            for reg, value in ((4, 0x05F0 | flags),
                               (0, final_destination), (1, source)):
                words += [0x3F10, 0xA8F0 | reg, 0x2400 + 2 * len(expected)]
                expected.append(signed_word(value))
            cases.append({"instruction": name, "left": left, "right": right,
                          "expected_psr": 0x05F0 | flags})
    return run(qemu, output, f"binary-truth-table-icount{icount}", words,
               {15: 0x6000}, expected_data=expected, icount=icount,
               metadata={"cases": cases, "source": "CN1916884A PDF pp.71/73/76/78"})


def check_aliases(qemu, output, icount):
    words = [0x6800, 2, 0x6810, 0, 0x6811, 1, 0x68FF, 0x6000]
    expected = []

    def save_psr():
        read_sfr(words, 1, 4)
        words.extend([0x3F10, 0xA8F4, 0x2400 + 2 * len(expected)])

    # Destination/source are the same GPR bit: use both pre-write operands.
    # These BAND self-tests also occur in the original USB loader.
    for opcode in (0x8C, 0x6C, 0x6D, 0x8D):
        words += [0x68F0, 0x80, 0x6801, 0x030F,
                  opcode << 8 | 0x70, 0x7077]
        save_psr()
        expected.append(0x0306)

    # Read PSR operands before changing flags. BCMP never writes either bit.
    words += [0x6801, 0x0205, 0x8D01, 0x0120]  # old Z=1, C=1
    save_psr()
    expected.append(0x0206)
    # Explicit PSR destination write remains last, as in the existing bit ABI.
    # BXOR old C=1 with R0.7=1 computes 0 and clears C after truth flags=6.
    words += [0x68F0, 0x80, 0x6801, 0x0204, 0x6D70, 0x0172]
    save_psr()
    expected.append(0x0202)
    return run(qemu, output, f"binary-aliases-icount{icount}", words,
               {15: 0x6000}, expected_data=expected, icount=icount,
               metadata={"psr_destination_order": "existing explicit-write-last contract"})


def check_vendor_branch(qemu, output, burn_code, icount):
    # The unchanged BCMP/MOV/conditional-branch/MOV fragment at 51:7BD0.
    # Diagnostic returns are outside this 10-byte fragment, at its fallthrough
    # and original branch target. This is not a complete burner invocation.
    source = burn_code.read_bytes()
    source_hash = hashlib.sha256(source).hexdigest()
    assert source_hash == "efec500f345b1dee11dd4aef95cc555a002e47943241176cde2ba6447c3b7cc0"
    # The auxiliary image is loaded at 50:6000 and uses big-endian file words.
    fragment = source[0x517BD0 - 0x506000:0x517BDA - 0x506000]
    assert fragment.hex() == "8d73710048a1d71448a0", fragment.hex()
    body = bytearray(pack([0x0F00] * 25))
    body[:10] = pack([int.from_bytes(fragment[i:i+2], "big") for i in range(0, 10, 2)])
    body[10:12] = pack([0xC620])
    body[48:50] = pack([0xC620])
    words = [0x6800, 2, 0x6810, 0, 0x6811, 1, 0x68FF, 0x6000]
    expected = []
    for (left, right), flags in FLAGS.items():
        words += [0x68F1, 0x1100 | left, 0x68F3, 0x3300 | right,
                  0x68FA, 0x5555, 0x6801, 0x030F, 0xBD51, 0x7BD0]
        read_sfr(words, 1, 4)
        for reg, value in ((10, left ^ right), (4, 0x0300 | flags)):
            words += [0x3F10, 0xA8F0 | reg, 0x2400 + 2 * len(expected)]
            expected.append(value)
    return run(qemu, output, f"original-burner-branch-icount{icount}", words,
               {15: 0x6000}, expected_data=expected, icount=icount,
               tail=(0x517BD0 - 0x200000, body),
               metadata={"source_sha256": source_hash, "fragment": "51:7BD0..7BD8",
                         "fragment_bytes": 10, "branch_target": "51:7C00",
                         "fragment_sha256": hashlib.sha256(fragment).hexdigest(),
                         "complete_original_function": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--burn-code", type=Path)
    parser.add_argument("--first-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"passed": False,
              "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
              "results": []}
    try:
        for icount in ((None,) if args.first_only else (None, 5)):
            report["results"].append(check_table(args.qemu, args.output, icount))
            if not args.first_only:
                report["results"].append(check_aliases(args.qemu, args.output, icount))
                if args.burn_code:
                    report["results"].append(check_vendor_branch(
                        args.qemu, args.output, args.burn_code, icount))
        report["passed"] = True
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
