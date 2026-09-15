#!/usr/bin/env python3
"""Original 0C:7142 64-word product loop and memory MAC bus/AGU boundaries."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from test_np560_dtu import read_word, write_word
from test_np560_mac import MASK40, pack, run


def original_block(qemu, original, output, ds1=1, icount=None):
    prg = original.read_bytes()
    start, end = 0x0C7142, 0x0C71B2
    body = prg[start - 0x30000:end - 0x30000]
    rom = bytearray(pack([0x0F00] * (end // 2)))
    rom[start:end] = body
    # The factory function uses a near RET; this caller-side trampoline
    # converts SCALL to ACALL without changing a single function byte.
    rom[0x0C7000:0x0C7006] = pack([0xBC00, 0x7142, 0xC620])
    words = [0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 1]
    for address, value in ((0x17DC, 0x1234), (0x187A, 1), (0x18BC, 0),
                           (0x17E2, 1), (0x17F0, 0x2800),
                           (0x1BA8, 0x1357), (0x1C2A, 0x2468)):
        write_word(words, address, value)
    inputs = [((i * 997) + 0x321) & 65535 for i in range(64)]
    coeffs = [0x1000 + i * 13 for i in range(64)]
    for i, (x, y) in enumerate(zip(inputs, coeffs)):
        write_word(words, 0x2800 + 2 * i, x)
        write_word(words, 0x85D2 + 2 * i, y)
    if ds1 != 1:
        words += [0x6811, ds1]
        for i in range(64):
            write_word(words, 0x85D2 + 2 * i, 0x7777, banked=True)
    words += [0xBD0C, 0x7000]
    # Copy the completed factory output through guest instructions to the
    # common read-only snapshot window used by the existing test runner.
    words += [0x68F0, 0x1BAA, 0x68F1, 0x2400, 0xBF00, 63, 0x5A10]
    read_word(words, 0x1BA8, 3)
    read_word(words, 0x1C2A, 4)
    read_word(words, 0x85D2, 8)
    read_word(words, 0x85D2, 9, banked=True)
    expected = [((x * y) >> 12) & 65535 for x, y in zip(inputs, coeffs)]
    expected = [v - 65536 if v >= 32768 else v for v in expected]
    return run(qemu, output, f'original-block-ds1-{ds1:03x}-icount{icount}',
               words, {2: 0x1C2A, 3: 0x1357, 4: 0x2468,
                       8: coeffs[0], 9: coeffs[0] if ds1 == 1 else 0x7777,
                       10: 0x2880, 14: 0x8652, 15: 0x6000},
               rom=rom, expected_data=expected, icount=icount,
               metadata={'function': '0C:7142..71B0', 'bytes': len(body),
                         'sha256': hashlib.sha256(body).hexdigest(),
                         'ds1': ds1, 'input_words': inputs,
                         'coefficient_words': coeffs})


def memory_case(qemu, output, name, *, cfg=0x0C, ext=0x0606,
                x=3, y=5, acc=7, value=22, socr=2, xm=0, ym=0,
                xp=0x2404, yp=0x8504, next_x=0x2406, next_y=0x8506,
                move_value=0xDEAD, move_address=0x2402, fault=False, ds1=1,
                icount=None):
    words = [0x6800, socr, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 1]
    for address, initial in ((0x2402, 0xDEAD), (0x2406, 0xBEEF),
                              (xp, x), (yp, y)):
        write_word(words, address, initial)
    words += [0x6811, ds1, 0x6817, xm, 0x681D, ym,
              0x68FA, xp, 0x68FE, yp, 0x68F0, 0x1234]
    x0 = ((ext >> 8) & 3) == 0
    if x0:
        words += [0x6813, xm, 0x68F8, xp]
    encoded = acc & MASK40
    words += [0x68F5, 0xA500 | (encoded >> 32),
              0x68F6, (encoded >> 16) & 65535, 0x68F7, encoded & 65535]
    fault_text = f'20:{len(words) * 2:04x} WORD={0xBE00 | cfg:04x}' if fault else None
    words += [0xBE00 | cfg, ext]
    read_word(words, move_address, 2)
    read_word(words, 0x2406, 3)
    result = (acc if fault else value) & MASK40
    expected = {0: 0x1234, 5: 0xA500 | (result >> 32),
                6: (result >> 16) & 65535, 7: result & 65535,
                10: xp if fault or x0 else next_x, 14: yp if fault else next_y,
                15: 0x6000}
    if x0:
        expected[8] = xp if fault else next_x
    if not fault:
        expected[2] = move_value
    return run(qemu, output, name, words, expected, fault=fault_text, icount=icount,
               metadata={'xm2': xm, 'ym2': ym, 'ds1': ds1})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', required=True, type=Path)
    parser.add_argument('--original-prg', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--first-only', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = {'qemu_sha256': hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
                'prg_sha256': hashlib.sha256(args.original_prg.read_bytes()).hexdigest()}
    (args.output / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    results = [original_block(args.qemu, args.original_prg, args.output)]
    if not args.first_only:
        results += [original_block(args.qemu, args.original_prg, args.output, 0xA0),
                    original_block(args.qemu, args.original_prg, args.output, 0xA0, 5)]
        cases = [
            ('unsigned', {}),
            ('signed-subtract', dict(cfg=1, x=-2, y=3, value=13)),
            ('signed-unsigned', dict(cfg=4, x=-2, y=65535, value=-131063)),
            ('unsigned-signed', dict(cfg=8, x=65535, y=-2, value=-131063)),
            ('fractional', dict(cfg=0, x=0x4000, y=0x4000, acc=0,
                               socr=10, value=0x20000000)),
            ('move-after-read', dict(cfg=0x0E, move_value=3)),
            ('mmio-modifier-write', dict(cfg=0x0E, ext=0x0406, x=1, value=12,
                                         xp=0xF128, next_x=0xF12A,
                                         move_address=0xF126, move_value=1)),
            ('mmio-modifier-write-icount5', dict(cfg=0x0E, ext=0x0406, x=1, value=12,
                                                xp=0xF128, next_x=0xF12A,
                                                move_address=0xF126, move_value=1,
                                                icount=5)),
            ('move-alias-y-read-first', dict(cfg=0x0E, xp=0x8506, yp=0x8504,
                                            next_x=0x8508, next_y=0x8506,
                                            move_address=0x8504, move_value=3)),
            ('move-decrement', dict(cfg=0x0E, ext=0x0A0A,
                                    next_x=0x2402, next_y=0x8502,
                                    move_address=0x2406, move_value=3)),
            ('hold-no-overwrite', dict(cfg=0x0E, ext=0x0202,
                                       next_x=0x2404, next_y=0x8504)),
            ('decrement', dict(ext=0x0A0A, next_x=0x2402, next_y=0x8502)),
            ('circular-forward', dict(xm=6, ym=6, next_x=0x2400, next_y=0x8500)),
            ('x0-circular-forward', dict(ext=0x0406, xm=6, ym=6,
                                         next_x=0x2400, next_y=0x8500)),
            ('circular-backward', dict(ext=0x0A0A, xm=6, ym=6,
                                       xp=0x2400, yp=0x8500,
                                       next_x=0x2404, next_y=0x8504)),
            ('bit-reversal-stop', dict(xm=65535, fault=True)),
            ('y-bit-reversal-stop', dict(ym=65535, fault=True)),
            ('invalid-y-stop', dict(yp=0x7504, fault=True)),
            ('unknown-modifier-index-stop', dict(ext=0x0505, fault=True)),
            ('unknown-offset-mode-stop', dict(ext=0x0E06, fault=True)),
            ('reserved-index-stop', dict(ext=0x0706, fault=True)),
        ]
        results += [memory_case(args.qemu, args.output, name, **kw) for name, kw in cases]
    assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity['qemu_sha256']
    (args.output / 'report.json').write_text(json.dumps(
        {'passed': True, 'identity': identity, 'cases': results}, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
