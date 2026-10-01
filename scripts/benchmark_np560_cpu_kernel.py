"""Fixed guest work; no debugger, NAND, or injected guest state."""
import argparse
import json
from pathlib import Path
import struct
import time
from np560_host_time import read_thread_time, thread_time_delta
from web.np560_web import Emulator, artifact_identity


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--qemu', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--host-cpu', action='store_true',
                   help='read the owned vCPU thread only at benchmark endpoints')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    words = [0x6800, 2, 0x68ff, 0x6000, 0x68f1, 0]
    for _ in range(8):
        end = (len(words)+5)*2
        words += [0xaeff, end, 0xbf00, 65535, 0x5011]
    words += [0xad20, 0xfffe]
    raw = bytearray(65536)
    struct.pack_into('<%dH' % len(words), raw, 0, *words)
    struct.pack_into('<H', raw, 65534, 0xc701)
    firmware = args.output/'kernel.prg'
    firmware.write_bytes(raw)
    expected = 3 + 8*(1+256*(1+65536)) + 2
    result = dict(qemu_sha256=artifact_identity(args.qemu)[1],
                  firmware_sha256=artifact_identity(firmware)[1], expected=expected, passed=False)
    emu = Emulator(qemu=args.qemu, firmware=firmware, start_paused=True, icount_shift=0)
    try:
        for prop in ('instruction-clock', 'control-observers-minimal'):
            emu.qmp.execute('qom-set', {'path':'/machine','property':prop,'value':True})
        if args.host_cpu:
            threads = emu.qmp.execute('query-cpus-fast')
            assert len(threads) == 1, 'expected one owned vCPU thread'
            tid = int(threads[0]['thread-id'])
            before_cpu = read_thread_time(emu.process.pid, tid)
        started = time.monotonic()
        emu.qmp.execute('cont')
        while time.monotonic()-started < 60:
            # Low-cost count sampling until the intentional terminal fault.
            if emu.qmp.execute('query-replay')['icount'] >= expected:
                break
            time.sleep(.1)
        emu.qmp.execute('stop')
        elapsed = time.monotonic()-started
        if args.host_cpu:
            after_cpu = read_thread_time(emu.process.pid, tid)
        count = emu.qmp.execute('query-replay')['icount']
        state = emu.qmp.execute('qom-get', {'path':'/machine','property':'instruction-clock-state'})
        cpu = emu.qmp.execute('qom-get', {'path':'/machine','property':'cpu-state'})
        result.update(host_seconds=elapsed, actual=count, clock=state, cpu=cpu,
                      instructions_per_second=count/elapsed)
        if args.host_cpu:
            result['host_cpu'] = thread_time_delta(before_cpu, after_cpu,
                                                   elapsed, count)
        assert count == expected, (expected, count, cpu[:500])
        assert 'UNSUPPORTED=20:fffe WORD=c701 COUNT=1' in cpu, cpu[:1000]
        assert 'ROM_MISSING=none' in cpu and 'INVALID_CONTROL=none' in cpu
        assert artifact_identity(args.qemu)[1] == result['qemu_sha256'], 'build changed'
        result['passed'] = True
        print({k:v for k,v in result.items() if k != 'cpu'}, flush=True)
    finally:
        emu.close()
        result['exit_code'] = emu.process.returncode
        (args.output/'report.json').write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
