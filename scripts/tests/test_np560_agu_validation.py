#!/usr/bin/env python3
"""Check R8/R10/R14 invalid circular modes halt before loads, without false positives."""
import argparse
import hashlib
import json
from pathlib import Path

from test_np560_mac import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cases = []
    for minimal in (False, True):
        for reg, modifier in ((8, 0x13), (10, 0x17), (14, 0x1d)):
            for kind in ('unsupported-mode', 'outside-ring', 'unused-invalid-mode'):
                length = 6 if kind == 'outside-ring' else 65535
                address = (0x8500 if reg == 14 else 0x2400) + 6
                words = [0x6800, 2, 0x68ff, 0x6000, 0x6810, 0, 0x6811, 0,
                         0x6800 | modifier, length, 0x68f0 | reg, address,
                         0x68f0, 0xbeef, 0x68f1, 0xcafe]
                pc = len(words)*2
                # MOV R0,[Rn++] must stop before changing R0 or Rn. A
                # register-only MOV must ignore the unused invalid modifier.
                words += [0x0810 if kind == 'unused-invalid-mode' else 0x3800 | reg]
                fault = None if kind == 'unused-invalid-mode' else f'20:{pc:04x}'
                cases.append(run(args.qemu, args.output,
                    f'r{reg}-{kind}-minimal{minimal}', words,
                    {0: 0xbeef, 1: 0xbeef if fault is None else 0xcafe,
                     reg: address, 15: 0x6000}, fault=fault, minimal=minimal))
    report = dict(passed=all(c['passed'] for c in cases), cases=cases,
                  qemu_sha256=hashlib.sha256(args.qemu.read_bytes()).hexdigest())
    (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
