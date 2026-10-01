"""Synthetic v7 parameter ABI only: no claim of implemented EQ DSP."""
import argparse
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_np560_mac import run


def check(qemu, output, name, invalid=False, disable=False, unloaded=False, reset=False):
    base = 0x18000
    rom = bytearray(b'\x00\x0f' * (0x30000 // 2))
    for service in range(9):
        rom[base+16*service:base+16*(service+1)] = struct.pack(
            '<8H', 0x0f00,0xc620,0x504d,0x484c,7,service,0,0)
    for address, service in ((0x14674,6),(0x146cc,7),(0x146d0,8)):
        target = base + 16*service
        rom[address:address+4] = struct.pack('<2H',0xad00 | target >> 16,target & 65535)
    coefficients = [0x8000,0xffff,1,0,0x1234,0x6101,0x5943,0x2222,0xaaaa,0x5555]
    words = [0x6800,2,0x68ff,0x7000,0x6810,0]
    for i,value in enumerate(coefficients):
        words += [0x68f0,value,0xa8f0,0x5000+2*i]
    def args(count):
        words.extend([0x68f0,count,0x58f0,0x68f0,0x5000,0x58f0,0x68f0,0,0x58f0])
    def regs():
        for r in range(15): words.extend([0x68f0|r,0x1100+r])
    if not unloaded:
        args(10); regs(); words += [0xbd01,0x4674,0x50f6]
    if invalid:
        args(9); regs(); words += [0xbd01,0x4674,0x50f6]
    regs(); words += [0xbd01,0x46cc]
    if disable: words += [0xbd01,0x46d0]
    result = run(qemu,output,name,words,
                 {**{r:0x1100+r for r in range(15)},15:0x7000},
                 rom=rom,rom_mp3_hle_base=base,verify_hle_reset=reset)
    state = result['rom_mp3_hle']['audio_mode']
    assert state['loaded'] == (not unloaded), state
    assert state['enabled'] == (not unloaded and not disable), state
    assert state['coefficients'] == ([0]*10 if unloaded else coefficients), state
    assert state['failures'] == int(invalid or unloaded), state
    assert not state['dsp_implemented']
    if reset:
        after = result['hle_after_reset']['audio_mode']
        assert not after['loaded'] and not after['enabled'], after
        assert after['coefficients'] == [0]*10, after
        assert after['calls'] == state['calls'], 'reset must not invent service calls'
    return dict(name=name,passed=True,audio_mode=state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    cases = [check(args.qemu,args.output,'load-enable'),
             check(args.qemu,args.output,'invalid-load-preserves-state',invalid=True),
             check(args.qemu,args.output,'disable',disable=True),
             check(args.qemu,args.output,'enable-without-load',unloaded=True),
             check(args.qemu,args.output,'board-reset',reset=True)]
    (args.output/'mode-report.json').write_text(json.dumps(cases,indent=2)+'\n')


if __name__ == '__main__':
    main()
