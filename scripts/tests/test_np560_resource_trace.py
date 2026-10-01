#!/usr/bin/env python3
"""Resource trace entry/stack tests; synthetic RETS body, not resource decoding."""
import argparse
import json
from pathlib import Path
import struct
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web.np560_web import Emulator


def check(qemu, enabled, thunk):
    words = [0x6800, 2, 0x68ff, 0x6000]
    for value in (0x4444, 0x3333, 0x2222, 0x1111):
        words += [0x68f0, value, 0x58f0]
    words += [0xbd32, 0x13e8] if thunk else [0xbd2e, 0x0af6]
    words += [0x50f8]
    end = len(words)*2
    words += [0xd0ff]
    image = bytearray(0x1213ec)
    image[:len(words)*2] = struct.pack('<%dH' % len(words), *words)
    image[0xe0af6:0xe0af8] = struct.pack('<H', 0xc620)
    image[0x1213e8:0x1213ec] = struct.pack('<2H', 0xad2e, 0x0af6)
    with tempfile.TemporaryDirectory(prefix='np560-resource-trace-') as directory:
        firmware = Path(directory)/'caller.prg'
        firmware.write_bytes(image)
        emu = Emulator(qemu=qemu, firmware=firmware, start_paused=True, icount_shift=5)
        try:
            prop = {'path':'/machine', 'property':'resource-trace-all'}
            assert emu.qmp.execute('qom-get', prop) is False
            emu.qmp.execute('qom-set', dict(prop, value=enabled))
            assert emu.qmp.execute('qom-get', prop) is enabled
            emu.qmp.execute('cont')
            deadline = time.monotonic()+10
            while time.monotonic() < deadline:
                state = emu.qmp.execute('qom-get', {'path':'/machine','property':'cpu-state'})
                if 'PC=20:%04x' % end in state:
                    break
                time.sleep(.01)
            assert 'PC=20:%04x' % end in state, state[:500]
            emu.qmp.execute('stop')
            trace = next(line for line in state.splitlines() if line.startswith('ROOT_RESOURCE_TRACE='))
            assert 'COUNT:%d ' % int(enabled) in trace, trace
            if enabled:
                assert '1111,2222,3333,4444' in trace, trace
            emu.qmp.execute('system_reset')
            assert emu.qmp.execute('qom-get', prop) is False
            return {'enabled':enabled, 'thunk':thunk, 'trace':trace}
        finally:
            emu.close()
            assert emu.process.returncode == 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps([check(args.qemu, enabled, thunk)
                      for enabled, thunk in ((False, True), (True, True), (True, False))]))
