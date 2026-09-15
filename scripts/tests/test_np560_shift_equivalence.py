"""Compare guest shifts with the former bit-at-a-time semantics, all byte counts."""

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import argparse
import base64
import json
from pathlib import Path
import struct
import time
from web.np560_web import Emulator, artifact_identity


def reference(kind, value, count, sb=0xa55a):
    if kind in ('rol', 'ror'):
        count &= 15
    elif count < 0:
        count = -count
        kind = {'sl':'sr', 'sr':'sl', 'slosb':'srosb', 'srosb':'slosb', 'asr':'asl'}[kind]
    carry = overflow = outgoing = 0
    for _ in range(count):
        if kind in ('sl', 'slosb'):
            out = value >> 15
            if kind == 'sl': outgoing = ((outgoing << 1) | out) & 65535
            value = (value << 1) & 65535
            overflow |= out
        elif kind in ('sr', 'srosb', 'asr'):
            out = value & 1
            if kind in ('sr', 'asr'): outgoing = (outgoing >> 1) | (out << 15)
            overflow |= carry
            value = (value >> 1) | ((value & 0x8000) if kind == 'asr' else 0)
        elif kind == 'asl':
            sign = value & 0x8000
            out = (value >> 14) & 1
            overflow |= bool(out) != bool(sign)
            value = sign | ((value << 1) & 0x7fff)
        elif kind == 'rol':
            out = value >> 15
            value = ((value << 1) | out) & 65535
        else:
            out = value & 1
            value = (value >> 1) | (out << 15)
        carry = out
    if kind in ('slosb', 'srosb'): value |= sb
    elif kind in ('sl', 'sr', 'asr', 'asl'): sb = outgoing
    if kind == 'asl' and overflow: value = 0x8000 if value & 0x8000 else 0x7fff
    # Hardware PSR readback order is Z,V,C,N, unlike env's internal flags.
    flags = int(value == 0) | (int(bool(count and carry)) << 2) | (int(bool(value & 0x8000)) << 3)
    if kind not in ('rol', 'ror'): flags |= int(bool(overflow)) << 1
    return value, flags, sb


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args=p.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    identity=artifact_identity(args.qemu)[1]
    cases=[(kind, op, value, count) for kind,op in (
        ('sl',0x0c),('sr',0x0d),('slosb',0x1c),('srosb',0x1d),
        ('asr',0x4a),('rol',0xc8),('ror',0xc9))
        for value in (0,1,0x8000,0xffff,0xa55a,0x7fff,0x1234,0x8001)
        for count in range(-128,128)]
    results=[]
    for batch,start in enumerate(range(0,len(cases),1024)):
        selected=cases[start:start+1024]; words=[0x6800,2,0x68ff,0x4000]
        expected=[]
        for i,(kind,op,value,count) in enumerate(selected):
            addr=0x5000+i*6
            words += [0x6802,0xa55a,0x68f0,value,0x68f1,(count & 255)<<8,
                      (op<<8)|2,0xa8f0,addr,0xa801,addr+2,0xa802,addr+4]
            expected.extend(reference(kind,value,count))
        final=0x030000+len(words)*2; words.append(0xc701)
        firmware=args.output/f'shift-{batch}.prg'
        firmware.write_bytes(struct.pack('<%dH'%len(words),*words))
        minimal=bool(batch & 1)
        emu=Emulator(qemu=args.qemu,firmware=firmware,start_paused=True,icount_shift=0,
                     boot_mode='firmware-vma03')
        try:
            for prop,val in (('instruction-clock',True),('control-observers-minimal',minimal)):
                emu.qmp.execute('qom-set',{'path':'/machine','property':prop,'value':val})
            emu.qmp.execute('cont'); deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                cpu=emu.qmp.execute('qom-get',{'path':'/machine','property':'cpu-state'})
                if f'UNSUPPORTED=03:{final & 65535:04x} WORD=c701 COUNT=1' in cpu: break
                time.sleep(.02)
            emu.qmp.execute('stop')
            assert f'UNSUPPORTED=03:{final & 65535:04x} WORD=c701 COUNT=1' in cpu, cpu[:800]
            raw=base64.b64decode(emu.snapshot('memory',0x5000,len(expected)*2,diagnostics=False)['frame'])
            actual=list(struct.unpack('<%dH'%len(expected),raw))
            for i in range(1,len(actual),3): actual[i] &= 15
            bad=[i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b]
            assert not bad, [(selected[i//3],i%3,actual[i],expected[i]) for i in bad[:10]]
            assert 'ROM_MISSING=none' in cpu and 'INVALID_CONTROL=none' in cpu
            results.append(dict(batch=batch,cases=len(selected),minimal=minimal,passed=True))
            print(results[-1],flush=True)
        finally: emu.close()
        assert emu.process.returncode==0
    assert identity==artifact_identity(args.qemu)[1]
    (args.output/'report.json').write_text(json.dumps(dict(passed=True,qemu_sha256=identity,
        cases=len(cases),batches=results,scope='equivalence to prior interpreter, not new hardware proof'),indent=2))


if __name__=='__main__': main()
