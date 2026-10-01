#!/usr/bin/env python3
"""Execute the original clock-tail branches, not the complete timer or RTC."""
import argparse
import hashlib
from pathlib import Path
import sys
import struct

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_np560_dtu import execute


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    prg = (root / 'NP560+V3.80版系统升级程序/NP560.PRG').read_bytes()
    assert hashlib.sha256(prg).hexdigest() == (
        'd555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5')
    # Diagnostic prologue supplies the frame saved by the full callback.
    # Keep all original tail bytes and same-segment branch destinations.
    # No case enters the cross-day subcalls, which need a separate fixture.
    code = struct.pack('<5H', 0x2e00, 0x58f0, 0x58f1, 0x58f2, 0x58f3)
    code += prg[0x24e6b0:0x24e84c]
    cases = [
        ('same bucket', 63, 0, (12, 34, 56), (12, 34, 56)),
        ('next second', 64, 0, (12, 34, 56), (12, 34, 57)),
        ('next minute', 64, 0, (12, 34, 59), (12, 35, 0)),
        ('next hour', 64, 0, (12, 59, 59), (13, 0, 0)),
        ('skipped bucket advances once', 192, 0, (12, 34, 56), (12, 34, 57)),
    ]
    for name, tick, previous, initial, expected in cases:
        words = [0x6800, 2, 0x68ff, 0x1800, 0x6810, 0]
        for address, value in ((0x4b40, tick), (0x4b4a, previous)):
            words += [0x68f0, value, 0xa8f0, address]
        words += [0x6810, 0xa1]
        for address, value in zip((0x3842, 0x3841, 0x3840), initial):
            words += [0x68f0, value, 0xa9f1, address]
        words += [0xbd21, 0xe6a6, 0x6810, 0xa1,
                  0x99f0, 0x3842, 0x99f1, 0x3841, 0x99f2, 0x3840]
        execute(args.qemu, name, words,
                {0: expected[0], 1: expected[1], 2: expected[2], 15: 0x1800},
                extra=(0x21e6a6, code), icount=5, verify_extra_code=True)
    # Relocate only the two SCALL segment operands to the diagnostic CS21.
    # Both targets are complete original functions, not successful-return stubs.
    day_code = bytearray(code)
    for pc, target in ((0xe7b6, 0x7b9e), (0xe830, 0x3212)):
        offset = pc - 0xe6a6
        assert day_code[offset:offset + 4] == struct.pack('<2H', 0xbd31, target)
        day_code[offset:offset + 2] = struct.pack('<H', 0xbd21)
    regions = ((0x213212, prg[0x2e3212:0x2e32d6]),
               (0x217b9e, prg[0x2e7b9e:0x2e7c50]))
    for initial, expected in (
        ((2024, 2, 28), (2024, 2, 29)),
        ((2024, 2, 29), (2024, 3, 1)),
        ((2025, 2, 28), (2025, 3, 1)),
        ((2000, 2, 28), (2000, 2, 29)),
        ((2100, 2, 28), (2100, 3, 1)),
        ((2025, 4, 30), (2025, 5, 1)),
        ((2025, 12, 31), (2026, 1, 1)),
        ((2100, 12, 31), (1901, 1, 1)),
    ):
        words = [0x6800, 2, 0x68ff, 0x1800, 0x6810, 0,
                 0x68f0, 64, 0xa8f0, 0x4b40, 0x68f0, 0, 0xa8f0, 0x4b4a,
                 0x6810, 0xa4]
        for index, days in enumerate((0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)):
            words += [0x68f0, days, 0xa9f1, 0x52ee + index]
        # Exercise 31:3212's state-changing path, not its FF early exit.
        words += [0x6810, 0xa2]
        for address, value in ((0x260a, 7), (0x2609, 8), (0x25fe, 0), (0x25fd, 0)):
            words += [0x68f0, value, 0xa9f1, address]
        words += [0x6810, 0xa1, 0x68f0, initial[0], 0xa8f0, 0x3846]
        for address, value in ((0x3844, initial[1]), (0x3843, initial[2]),
                               (0x3842, 23), (0x3841, 59), (0x3840, 59)):
            words += [0x68f0, value, 0xa9f1, address]
        words += [0xbd21, 0xe6a6, 0x6810, 0xa1,
                  0x88f0, 0x3846, 0x99f1, 0x3844, 0x99f2, 0x3843,
                  0x99f3, 0x3842, 0x99f4, 0x3841, 0x99f5, 0x3840,
                  0x6810, 0xa2, 0x99f6, 0x25fe, 0x99f7, 0x25fd,
                  0x88f8, 0x260c, 0x99f9, 0x260a, 0x99fa, 0x2609]
        execute(args.qemu, f'midnight {initial} -> {expected}', words,
                {0: expected[0], 1: expected[1], 2: expected[2],
                 3: 0, 4: 0, 5: 0, 6: 7, 7: 8, 8: 3000, 9: 255, 10: 255,
                 15: 0x1800}, extra=(0x21e6a6, bytes(day_code)),
                extra_regions=regions, icount=5, verify_extra_code=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
