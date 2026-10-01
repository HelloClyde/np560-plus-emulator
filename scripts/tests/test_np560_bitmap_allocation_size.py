#!/usr/bin/env python3
"""Execute the unchanged original bitmap-size leaf, relocated outside aliases.

This checks allocation sizing, not bitmap contents or player redraw success.
No NAND, guest heap initialization, or user instance is involved.
"""
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
    original = (root / 'NP560+V3.80版系统升级程序/NP560.PRG').read_bytes()
    assert hashlib.sha256(original).hexdigest() == (
        'd555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5')
    # Source 50:1E7A, normally linked at 33:1E7A. This leaf has no absolute
    # references; use a diagnostic address not subject to production aliases.
    code = original[0x301e7a:0x301ea6]
    assert len(code) == 44 and code[-2:] == b'\x20\xc6'
    for width, height, expected in ((240, 120, 14410), (5, 6, 34),
                                     (4, 1, 12), (1, 1, 12)):
        words = [0x6800, 2, 0x68ff, 0x6000,
                 0x68f0, height, 0x58f0, 0x68f0, width, 0x58f0,
                 0xbd20, 0x100, 0x50f4]
        execute(args.qemu, f'original bitmap size {width}x{height}={expected}',
                words, {0: expected, 15: 0x6000},
                extra=(0x200100, code), icount=5)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
