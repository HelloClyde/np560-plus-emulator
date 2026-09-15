"""Banked word crossing DS0/DS1: compare full and minimal, guest writes only."""
import argparse
import json
from pathlib import Path
import re
import struct
import time
from web.np560_web import Emulator, artifact_identity


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--qemu', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    words = [0x6800,2, 0x6810,0xa0, 0x6811,0xa2,
             0x68f4,0x7ffe, 0x68f2,0x1234, 0x0a42,
             0x68f4,0x8000, 0x68f2,0xabcd, 0x0a42,
             0x68f4,0x7fff, 0x2834,
             0x68f2,0x9876, 0x0a42,
             0x68f4,0x7ffe, 0x2854,
             0x68f4,0x8000, 0x2864]
    final = 0x200000 + len(words)*2
    words.append(0xd0ff)
    firmware = args.output/'boundary.prg'
    firmware.write_bytes(struct.pack('<%dH' % len(words), *words))
    results = []
    for minimal in (False, True):
        emu = Emulator(qemu=args.qemu, firmware=firmware, start_paused=True, icount_shift=0)
        try:
            for prop, value in [('instruction-clock',True), ('control-observers-minimal',minimal)]:
                emu.qmp.execute('qom-set', {'path':'/machine','property':prop,'value':value})
            emu.qmp.execute('cont')
            deadline = time.monotonic()+5
            while time.monotonic() < deadline:
                state = emu.qmp.execute('qom-get', {'path':'/machine','property':'cpu-state'})
                if f'PC=20:{final & 65535:04x}' in state:
                    break
                time.sleep(.01)
            registers = {int(k):int(v,16) for k,v in re.findall(r'\bR(\d+)\s*=([0-9a-f]{4})\b', state, re.I)}
            expected = {3:0xcd12, 5:0x7634, 6:0xab98}
            assert f'PC=20:{final & 65535:04x}' in state, state[:1500]
            assert all(registers[k] == v for k,v in expected.items()), (expected, registers)
            assert all(f'{f}=none' in state for f in ('ROM_MISSING','UNSUPPORTED','INVALID_CONTROL'))
            results.append(dict(minimal=minimal, registers=registers, passed=True))
            print(results[-1], flush=True)
        finally:
            emu.close()
    (args.output/'report.json').write_text(json.dumps(dict(qemu_sha256=artifact_identity(args.qemu)[1], cases=results), indent=2))


if __name__ == '__main__':
    main()
