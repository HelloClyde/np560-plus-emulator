#!/usr/bin/env python3
"""Execute the original battle zero-counter restore block, not an entire round.

The block is placed at 38:FB72 with unchanged bytes/local branch offsets.
Its original 33:07B0 multiply helper is included; a test RETS follows FCA6.
Fixture guest instructions initialize records. No live game/NAND is used.
This does not test decrement scheduling, death, stacking or full gameplay.
"""
import argparse
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_np560_dtu import execute, write_word


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    prg = (root/'NP560+V3.80版系统升级程序/NP560.PRG').read_bytes()
    assert hashlib.sha256(prg).hexdigest() == 'd555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5'
    # Production 33:07B0 code view aliases its factory 50:07B0 source.
    regions = ((0x5007b0, prg[0x3007b0:0x3007e4]),
               (0x38fb72, prg[0x18fb72:0x18fca6] + bytes.fromhex('20c6')))
    for index in (0, 2):
        for attack_timer, defense_timer in ((0,0), (1,0), (0,1), (2,3)):
            words = [0x68ff,0x6000,0x68fb,0x5000,0x6810,0xa4]
            write_word(words,0x4ffc,index)
            delta = 0x94 * index
            for offset,value in ((0x6496,attack_timer),(0x6498,defense_timer),
                                 (0x64ac,13),(0x64ae,11),(0x64b0,143),(0x64b2,41)):
                write_word(words,offset+delta,value,banked=True)
            # Adjacent record output must not be touched by index arithmetic.
            write_word(words,0x64b0+delta+0x94,0x5a5a,banked=True)
            words += [0xbd38,0xfb72,0x6810,0xa4]
            for register,offset in ((4,0x64ac),(5,0x64ae),(6,0x64b0),(7,0x64b2),
                                    (8,0x64b0+0x94),(9,0x6496),(10,0x6498)):
                words += [0x88f0 | register, offset+delta]
            execute(args.qemu, f'native restore index={index} counters={attack_timer}/{defense_timer}',
                    words, {4:13,5:11,6:143 if attack_timer else 13,
                            7:41 if defense_timer else 11,8:0x5a5a,
                            9:attack_timer,10:defense_timer,11:0x5000,15:0x6000},
                    extra_regions=regions,verify_extra_code=True)
    print('PASS: eight original restore-block cases; not full-round expiry evidence')


if __name__ == '__main__':
    main()
