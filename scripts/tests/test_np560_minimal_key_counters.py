"""Guest-authored repeated key-slot writes; public ACKs must survive minimal mode."""

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import argparse
import json
from pathlib import Path
import struct
import time
from web.np560_web import Emulator, artifact_identity


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    words = [0x6800, 2, 0x68ff, 0x6000, 0x6810, 0xa2,
             0x68f0, 0x86, 0xa8f0, 0x28d8, 0xa8f0, 0x28d8,
             0xc701]
    raw = struct.pack('<%dH' % len(words), *words)
    firmware = args.output/'key-slots.prg'
    firmware.write_bytes(raw)
    identity = artifact_identity(args.qemu)[1]
    results = []
    for minimal in (False, True):
        emu = Emulator(qemu=args.qemu, firmware=firmware,
                       start_paused=True, icount_shift=0)
        try:
            for prop, value in (('control-observers-minimal', minimal), ('instruction-clock', True)):
                emu.qmp.execute('qom-set', {'path':'/machine', 'property':prop, 'value':value})
            emu.qmp.execute('cont')
            deadline = time.monotonic()+10
            while time.monotonic() < deadline:
                status = emu.key_status()
                if status.get('faulted'):
                    break
                time.sleep(.02)
            emu.qmp.execute('stop')
            cpu = emu.qmp.execute('qom-get', {'path':'/machine', 'property':'cpu-state'})
            assert 'UNSUPPORTED=20:0018 WORD=c701 COUNT=1' in cpu, cpu[:700]
            assert 'ROM_MISSING=none' in cpu and 'INVALID_CONTROL=none' in cpu
            assert status['candidates'] == 2 and status['candidate'] == 0x86, status
            assert status['maps'] == 0, status
            results.append(dict(minimal=minimal, status=status, passed=True))
        finally:
            emu.close()
            assert emu.process.returncode == 0
    assert identity == artifact_identity(args.qemu)[1]
    report = dict(passed=True, qemu_sha256=identity, cases=results,
                  scope='guest slot writes / observer contract, not physical key scanning')
    (args.output/'report.json').write_text(json.dumps(report, indent=2))
    print(report)


if __name__ == '__main__':
    main()
