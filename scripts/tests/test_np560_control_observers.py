#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check required fault/key diagnostics in full and minimal observer modes.

Synthetic guest programs only; no original firmware/NAND or RAM injection.
These checks cover the required subset, not equivalence of historical logs.
"""

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import time

from web.np560_web import Emulator, QMPError, RunJournal


def case(qemu, output, name, target, minimal):
    root = output / (name + ('-minimal' if minimal else '-full'))
    root.mkdir()
    words = [0x6800, 2, 0x68ff, 0x6000, 0x68fb, 0x5500, 0x68f0, 0x0092]
    if target is None:
        # C700 is the modeled NOP; C701 has no supported encoding. 0F00 is
        # a valid software TRAP and must not be used as an invalid fixture.
        words.append(0xc701)
    else:
        words += [0xbd00 | target >> 16, target & 65535, 0xd0ff]
    image = bytearray(struct.pack(f'<{len(words)}H', *words))
    if name == 'key-ack':
        # The board's existing foreground overlay fetches logical 20:2E9E
        # from immutable PRG source 37:2E9E (file offset 1D2E9E), not from
        # the writable flat destination. Populate that source, not guest RAM.
        image.extend(bytes(0x1d2ea0 - len(image)))
        struct.pack_into('<H', image, 0x1d2e9e, 0xd0ff)
    firmware = root/'caller.prg'; firmware.write_bytes(image)
    journal = RunJournal(root/'process', case=name)
    result = dict(name=name, minimal=minimal, passed=False)
    emu = None
    try:
        emu = Emulator(qemu=qemu, firmware=firmware, start_paused=True, journal=journal)
        prop = {'path':'/machine', 'property':'control-observers-minimal'}
        assert emu.qmp.execute('qom-get', prop) is False
        if minimal: emu.qmp.execute('qom-set', {**prop, 'value':True})
        emu.qmp.execute('system_reset')
        assert emu.qmp.execute('qom-get', prop) is minimal
        if name == 'key-ack':
            assert base64.b64decode(emu.snapshot('code',target,2)['frame']) == b'\xff\xd0'
        emu.qmp.execute('cont')
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            state = emu.qmp.execute('qom-get', {'path':'/machine','property':'cpu-state'})
            if name == 'key-ack': done = 'PC=20:2e9e' in state
            elif target is None: done = 'UNSUPPORTED=none' not in state
            else: done = 'INVALID_CONTROL=none' not in state
            if done: break
            time.sleep(.05)
        assert done, state[:300]
        try:
            emu.qmp.execute('qom-set', {**prop, 'value':not minimal})
        except QMPError as e:
            assert 'Pause the CPU' in str(e)
        else: raise AssertionError('running observer change was accepted')
        emu.qmp.execute('stop')
        state = emu.qmp.execute('qom-get', {'path':'/machine','property':'cpu-state'})
        (root/'cpu.txt').write_text(state)
        assert f'CONTROL_OBSERVERS={"minimal" if minimal else "full"}' in state
        assert 'ROM_MISSING=none' in state
        result['diagnostic_lines'] = [line for line in state.splitlines()
                                     if line.startswith(('INVALID_CONTROL=', 'INVALID_CONTROL_CONTEXT=', 'UNSUPPORTED='))]
        # A bad control transfer records (but does not architecturally trap)
        # the first target. Subsequent execution at that target may reach an
        # unrelated unsupported encoding before the host manages to pause.
        # Compare the required first-fault snapshot, not that racing later
        # observation. The dedicated C701 case checks unsupported separately.
        result['fault_lines'] = [line for line in result['diagnostic_lines']
                                if target is None or name == 'key-ack' or
                                not line.startswith('UNSUPPORTED=')]
        if name == 'key-ack':
            values = [emu.qmp.execute('qom-get', {'path':'/machine','property':p})
                      for p in ('key-foreground-ack-count','key-foreground-ack-last')]
            assert values == [1, 0x92], values
            assert all(k+'=none' in state for k in ('UNSUPPORTED','INVALID_CONTROL'))
            result['key_ack'] = values
        elif target is not None:
            expected = f'INVALID_CONTROL=20:0010/{0xbd00 | target>>16:04x}>{target>>16:02x}:{target&65535:04x}'
            assert expected in state, result['fault_lines']
            assert 'POSTSP:5ffc POSTFP:5500' in state
        else:
            assert 'UNSUPPORTED=20:0010 WORD=c701 COUNT=1' in state, result['diagnostic_lines']
        result['passed'] = True
    except Exception as e: result['error'] = f'{type(e).__name__}: {e}'
    finally:
        if emu is not None: emu.close(); result['exit_code'] = emu.process.returncode
    result['passed'] &= result.get('exit_code') == 0
    print(json.dumps(result), flush=True)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    report=dict(passed=False, qemu_sha256=hashlib.sha256(args.qemu.read_bytes()).hexdigest(), cases=[])
    for name,target in [('odd-call',0x200021),('outside-call',0x800000),('unsupported',None),('key-ack',0x202e9e)]:
        pair=[case(args.qemu,args.output,name,target,minimal) for minimal in (False,True)]
        report['cases'] += pair
        if not all(c['passed'] for c in pair): break
        if pair[0]['fault_lines'] != pair[1]['fault_lines']:
            report['error'] = name+': required fault context differs'; break
    else: report['passed']=True
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
