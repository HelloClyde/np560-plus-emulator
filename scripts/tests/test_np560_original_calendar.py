#!/usr/bin/env python3
"""Original month-length code with a diagnostic month table; not RTC hardware."""
import argparse
import hashlib
from pathlib import Path
import sys

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
    code = prg[0x2e7b9e:0x2e7c50]
    assert len(code) == 0xb2 and code[-2:] == b'\x20\xc6'
    # Keep original same-segment jump offsets in CS21. CS20:7B9E overlaps
    # the production file-record overlay at 20:76CA..7C55 and is unsuitable.
    # The runtime data table is
    # initialized here, not claimed to have been recovered from ROM/NAND.
    prefix = [0x6800, 2, 0x68ff, 0x1800, 0x6810, 0xa4]
    for index, days in enumerate((0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)):
        prefix += [0x68f0, days, 0xa9f1, 0x52ee + index]
    for year, month, expected in ((1900, 2, 28), (2000, 2, 29), (2100, 2, 28),
                                   (2024, 2, 29), (2025, 2, 28), (2025, 4, 30),
                                   (2025, 12, 31), (2025, 0, 0), (2025, 13, 0)):
        words = prefix + [0x68f0, month, 0x58f0, 0x68f0, year, 0x58f0,
                          0xbd21, 0x7b9e, 0x50f4]
        execute(args.qemu, f'original calendar {year}-{month}: {expected}',
                words, {0: expected, 15: 0x1800}, extra=(0x217b9e, code), icount=5,
                verify_extra_code=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
