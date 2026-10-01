#!/usr/bin/env python3
"""Execute the original key gate; proves scan-count semantics, not real-time polling."""
import argparse
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_np560_dtu import execute, read_word, write_word


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    prg = (root / 'NP560+V3.80版系统升级程序/NP560.PRG').read_bytes()
    assert hashlib.sha256(prg).hexdigest() == (
        'd555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5')
    # Runtime 31:BE70 uses only same-segment absolute jumps and DS=A2 data.
    # Retain its PC offset under CS=20, outside production overlays.
    code = prg[0x2ebe70:0x2ebf0e]
    assert len(code) == 158 and code[-2:] == b'\x20\xc6'
    words = [0x6800, 2, 0x68ff, 0x6000, 0x6810, 0x00a2]
    write_word(words, 0x2a8c, 0, banked=True)
    write_word(words, 0x2a94, 1, banked=True)
    # First contact requires two invocations. With no release, accept counts
    # 6 and 10, then clamp count 11 back to 6 without accepting that sample.
    results = [0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0]
    for register in range(2, 15):
        words.extend([0xbd20, 0xbe70, 0x0800 | (register << 4)])
    # The counter is byte-addressed: a word read would observe 0x0600 on
    # this bus. Use the same MOVZE byte access as the original gate.
    words.extend([0x99f0, 0x2a8c])
    read_word(words, 0x2a94, 1, banked=True)
    expected = dict(enumerate(results, 2))
    expected.update({0: 6, 1: 0, 15: 0x6000})
    execute(args.qemu, 'original key gate: first-contact and repeat counts',
            words, expected, extra=(0x20be70, code), icount=5)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
