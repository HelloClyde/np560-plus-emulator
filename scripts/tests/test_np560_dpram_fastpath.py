"""DPRAM fast-port equivalence, including the adjacent real SFR boundary."""

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import argparse
import json
from pathlib import Path
from test_np560_mac import run
from test_np560_dtu import write_word, read_word, read_sfr
from web.np560_web import artifact_identity


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--qemu', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    words = [0x6800, 2, 0x68ff, 0x6000, 0x6811, 0xa0]
    write_word(words, 0xf000, 0x5678)
    write_word(words, 0xf0fe, 0x1234)
    read_word(words, 0xf000, 1)
    read_word(words, 0xf0fe, 2)
    read_word(words, 0xf0ff, 3)  # Must split RAM/SOCR, not raw SRAM.
    read_word(words, 0xf100, 4)
    read_sfr(words, 0, 5)
    # Byte F0FF is the low byte of the F0FE word (high-byte-first numbering).
    words += [0x68f0, 0x00ab, 0x3f10, 0xa9f1, 0xf0ff]
    read_word(words, 0xf0fe, 6)
    read_word(words, 0xf0fe, 7, banked=True)  # Separate DS1=A0 bank.
    results = []
    for minimal in (False, True):
        for shift in (None, 0):
            results.append(run(args.qemu, args.output, f'dpram-{minimal}-{shift}',
                words, {1:0x5678, 2:0x1234, 3:0x0212, 4:2, 5:2, 6:0x12ab, 7:0},
                minimal=minimal, icount=shift))
    (args.output/'report.json').write_text(json.dumps(dict(
        passed=True, qemu_sha256=artifact_identity(args.qemu)[1], cases=results), indent=2))


if __name__ == '__main__':
    main()
