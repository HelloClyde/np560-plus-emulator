#!/usr/bin/env python3
"""DMCU ordinary Y-pointer accesses must use internal Y-RAM, not DS banks.

CN1916884A figures 2, 5 and 9 specify R12..R14 and all indirect forms.
Reuse the existing owned-QEMU runner; no NAND or running user instance.
"""
from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import hashlib
import json
from pathlib import Path

from test_np560_dtu import read_word, write_word
from test_np560_mac import run


def setup():
    words = [0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 1,
             0x681D, 0]
    for address, value in ((0x8500, 0x1234), (0x8502, 0x5678),
                           (0xBFFE, 0x1357), (0x8000, 0x2468)):
        write_word(words, address, value)
    words += [0x6811, 0xA0]
    for address, value in ((0x8500, 0xABCD), (0x8502, 0xEF01)):
        write_word(words, address, value, banked=True)
    return words


def cases():
    words = setup()
    words += [0x68FC, 0x8500, 0x68FD, 0x8500, 0x68FE, 0x8500,
              0x281C, 0x382D, 0x783E, 2,
              0x68F8, 0x8500, 0x2848]
    yield 'read-base-post-offset-and-x-control', words, {
        1: 0x1234, 2: 0x1234, 3: 0x5678, 4: 0xABCD,
        12: 0x8500, 13: 0x8502, 14: 0x8500}, None

    words = setup()
    words += [0x68FC, 0x8500, 0x68FD, 0x8504, 0x68FE, 0x8500,
              0x68F0, 0xF00D, 0x0AC0, 0x58D0,
              0x68F0, 0x2400, 0x5A0E]
    read_word(words, 0x8500, 1)
    read_word(words, 0x8502, 2)
    read_word(words, 0x2400, 3)
    read_word(words, 0x8500, 4, banked=True)
    read_word(words, 0x8502, 5, banked=True)
    yield 'write-predecrement-copy-and-bank-isolation', words, {
        0: 0x2402, 1: 0xF00D, 2: 0xF00D, 3: 0xF00D,
        4: 0xABCD, 5: 0xEF01, 13: 0x8502, 14: 0x8502}, None

    words = setup()
    # Effective address, not initial register, determines Y-RAM membership.
    words += [0x68FC, 0xC000, 0x68F0, 0xBEEF, 0x58C0,
              0x68FD, 0x7FFE, 0x781D, 2,
              0x68FE, 0x8002, 0x782E, 0xFFFE]
    read_word(words, 0xBFFE, 3)
    yield 'predecrement-upper-and-offset-lower-edge', words, {
        1: 0x2468, 2: 0x2468, 3: 0xBEEF, 12: 0xBFFE}, None

    words = setup()
    words += [0x68FC, 0x8500, 0x68F1, 1, 0x3014,
              0x68F0, 1, 0x2CC1]  # ADD R1,[Y0]; SL [Y0++],RB1.
    read_word(words, 0x8500, 2)
    read_word(words, 0x8500, 3, banked=True)
    yield 'alu-and-read-modify-write', words, {
        1: 0x1235, 2: 0x2468, 3: 0xABCD, 12: 0x8502}, None

    words = setup()
    words += [0x68FE, 0x8502, 0x681D, 4, 0x381E, 0x382E]
    yield 'y2-circular-read', words, {
        1: 0x5678, 2: 0x1234, 14: 0x8502}, None

    words = setup()
    words += [0x68FE, 0x8500, 0x68F1, 0, 0x392E, 0x393E,
              0x68FC, 0x8500, 0x68FD, 0x8502, 0x68F0, 0xAA,
              0x0BC1, 0x59D1]
    read_word(words, 0x8500, 2)
    read_word(words, 0x8500, 3, banked=True)
    yield 'byte-lanes-and-byte-predecrement', words, {
        1: 0x1234, 2: 0xAAAA, 3: 0xABCD, 13: 0x8501, 14: 0x8502}, None

    words = setup()
    write_word(words, 0x2400, 0x55AA)
    words += [0x68FE, 0x8500, 0x8A0E, 0x2400,
              0x68FC, 0xBFFF, 0x68F2, 0, 0x395C]
    read_word(words, 0x8500, 3)
    read_word(words, 0x8500, 4, banked=True)
    yield 'direct-source-store-and-last-byte', words, {
        2: 0x57, 3: 0x55AA, 4: 0xABCD, 12: 0xC000}, None

    for name, initial, instruction, expected in (
        ('reject-outside-before-postincrement', 0x7500, [0x381E], {1: 0x3333, 14: 0x7500}),
        ('reject-predecrement-before-register-change', 0x8000, [0x58E0], {14: 0x8000}),
        ('reject-offset-outside-before-read', 0xBFFE, [0x781E, 2], {1: 0x3333, 14: 0xBFFE}),
        ('reject-two-pointer-store-before-source-update', 0xC000, [0x5AEE], {14: 0xC000}),
    ):
        words = setup() + [0x68F1, 0x3333, 0x68FE, initial]
        fault = f'20:{len(words) * 2:04x} WORD={instruction[0]:04x}'
        words += instruction
        yield name, words, expected, fault


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--first-only', action='store_true')
    parser.add_argument('--minimal', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    (args.output / 'identity.json').write_text(json.dumps({'qemu_sha256': identity}) + '\n')
    results = []
    for name, words, expected, fault in cases():
        results.append(run(args.qemu, args.output, name, words,
                           {15: 0x6000, **expected}, fault=fault, minimal=args.minimal))
        if args.first_only:
            break
    assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
    (args.output / 'report.json').write_text(json.dumps(
        {'passed': True, 'qemu_sha256': identity, 'cases': results}, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
