#!/usr/bin/env python3
"""Exercise Timer0/1/2 and the original two-channel DAC transport setup.

No host memory writes or HLE: original 24:97AC/99D2/99F6/98FC/9A1E/9AB8
select, configure, fill, start and stop the two timer-driven DTU channels.
F1E0/F1E2 are checked as sample registers, not as implemented analog audio.
"""
from __future__ import annotations

import argparse
import itertools
import re
from pathlib import Path

from test_np560_dtu import execute, read_sfr, read_word, write_word
from test_np560_timer2 import check_timer


def check_original_transport(qemu: Path, original: Path, first: int, second: int,
                             *, icount: int | None = None,
                             audio_pll: int | None = None, audio_div1536: bool = False) -> dict:
    dedicated = audio_pll is not None
    assert (first == second == 3) if dedicated else (
        first != second and first in range(3) and second in range(3))
    # Timer for F1E0 is selected by config[7:6], F1E2 by config[9:8].
    # Each uses the original periodic config 0080 and 2 MHz / 2000 = 1 kHz.
    mode = first << 6 | second << 8 | 8
    if dedicated:
        mode |= 0x30 | (2 if audio_div1536 else 0)
    words = [0x68FF, 0x6000, 0x68FB, 0, 0x6800, 2,
             0x6810, 0xA2, 0x6811, 0xA3,
             0x68E9, 0x8020, 0xEE00, 0x682E, 2, 0xFE00]
    if dedicated:
        words.extend([0x68EA, audio_pll])
    for address, value in ((0x303E, 0xA531), (0x403E, 0x7ABE)):
        write_word(words, address, value)
    # Arguments are far addresses, TxC, TxP, then packed routing flags.
    args = (0, 0x3000, 0, 0x3100, 0, 0x4000, 0, 0x4100, 0x80, 1999, mode)
    for value in reversed(args):
        words.extend([0x68F0, value, 0x58F0])
    words.extend([0xBD24, 0x97AC, 0x70FF, len(args) * 2,
                  0x68F0, 32, 0x58F0, 0xBD24, 0x99D2, 0x50F2,
                  0xBD24, 0x99F6, 0xBD24, 0x98FC, 0xBD24, 0x9A1E])
    for channel, register in ((0, 4), (1, 5)):
        loop = len(words) * 2
        read_sfr(words, 0x21 + channel, register)
        words.extend([0x74F0 | register, 0x03FF, 0x5600 | register << 4,
                      0xAC02, loop])
    words.extend([0xBD24, 0x9AB8])
    read_word(words, 0xF1E0, 6)
    read_sfr(words, 0x70, 7)
    read_word(words, 0xF1E2, 8)
    read_sfr(words, 0x71, 9)
    read_word(words, 0xF0F0, 10)
    read_word(words, 0xF0F4, 12)
    if dedicated:
        read_sfr(words, 0x61, 13)
        read_sfr(words, 0x60, 14)
        words.extend([0x74FD, 1, 0x74FE, 1])
    else:
        read_sfr(words, 0x27 + first * 3, 13)
        read_sfr(words, 0x27 + second * 3, 14)
    data = original.read_bytes()[0x2197AC:0x219BE8]
    assert data[:2] == b"\x00\x2e" and data[-2:] == b"\x20\xc6"
    result = execute(qemu, f"original DAC transport T{first}/T{second} PLL={audio_pll} icount={icount}",
                     words, {4: 0, 5: 0, 6: 0xA531, 7: 0xA531,
                             8: 0x7ABE, 9: 0x7ABE, 10: 0x3040, 12: 0x4040,
                             13: 0 if dedicated else 0x80,
                             14: 0 if dedicated else 0x80, 15: 0x6000},
                     extra=(0x2497AC, data), icount=icount)
    for channel in range(2):
        match = re.search(rf"CH{channel}:8000/(\d+)/(\d+)", result["dtu"])
        assert match and (int(match[1]), int(match[2])) == (32, 1), result["dtu"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path, required=True)
    args = parser.parse_args()
    for index in range(3):
        check_timer(args.qemu, index=index)
        check_timer(args.qemu, index=index, icount=5)
        check_timer(args.qemu, index=index, pause=True)
    for first, second in itertools.permutations(range(3), 2):
        check_original_transport(args.qemu, args.original_prg, first, second)
    check_original_transport(args.qemu, args.original_prg, 1, 2, icount=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
