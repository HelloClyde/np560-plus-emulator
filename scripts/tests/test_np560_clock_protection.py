#!/usr/bin/env python3
"""CLKCON unlock/lock through guest instructions and original 24:FF92.

No NAND or host writes to guest state. CN1916884A p16, figs. 7A/21/22,
and the factory EE00/FE00 sequences establish SOCR.UP and REG2E.
"""
from __future__ import annotations

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
import re
import tempfile
import time
from pathlib import Path

from test_np560_dtu import read_sfr, read_word
from test_np560_mac import pack
from web.np560_web import Emulator


def cases(original):
    # Initialise CLKCON legally, then try each write path while locked.
    setup = [0x6800, 2, 0x68FF, 0x6000, 0x6810, 1, 0x6811, 1,
             0xEE00, 0x682E, 2, 0xFE00]
    writes = {
        'direct-word': [0x682E, 0x10],
        'direct-byte': [0x692E, 0x10],
        'bit': [0xE42E],
        'banked-word': [0x68F0, 0x10, 0xA8F0, 0x715C],
        'unbanked-word': [0x68F0, 0x10, 0x3F10, 0xA8F0, 0xF15C],
        'unbanked-low-byte': [0x68F0, 0x10, 0x3F10, 0xA9F0, 0xF15D],
        'unbanked-high-byte': [0x68F0, 0x10, 0x3F10, 0xA9F0, 0xF15C],
        'pop': [0x68F0, 0x10, 0x58F0, 0x1FAE],
    }
    for name, attempt in writes.items():
        words = setup + attempt
        read_sfr(words, 0x2E, 2)
        read_word(words, 0x715C, 3, banked=True)
        read_word(words, 0xF15C, 4)
        yield 'locked-' + name, words, {2: 2, 3: 2, 4: 2, 15: 0x6000}, 6144000, None

    words = setup + [0xEE00, 0x692E, 0x10, 0xFE00]
    read_sfr(words, 0x2E, 2)
    read_sfr(words, 0, 3)
    yield 'unlocked-byte', words, {2: 0x10, 3: 2, 15: 0x6000}, 32768, None

    words = setup + [0xEE00, 0x68F0, 3, 0xA8F0, 0x715C, 0xFE00,
                     0xF12E]  # Locked BCLR cannot change 3 to 1.
    read_sfr(words, 0x2E, 2)
    yield 'unlocked-bank-then-relock', words, {2: 3, 15: 0x6000}, 3072000, None

    # TBC has its own control, not the CLKCON protection contract.
    words = setup + [0x682F, 0x8009]
    read_sfr(words, 0x2F, 2)
    yield 'unrelated-timebase-not-protected', words, {2: 0x8009, 15: 0x6000}, 6144000, None

    start, end = 0x24FF92, 0x24FFD2
    body = original[start - 0x30000:end - 0x30000]
    assert body[:4] == pack([0x58F0, 0x1F2E]) and body[-2:] == pack([0xC620])
    words = setup + [0x68F0, 0x1234, 0xBD24, 0xFF92]
    read_sfr(words, 0x2E, 2)
    read_sfr(words, 0, 3)
    yield 'original-clock-save-change-restore', words, {
        0: 0x1234, 2: 2, 3: 2, 15: 0x6000}, 6144000, (start, body)


def check(qemu, output, case, icount):
    name, words, expected, hz, original_body = case
    name += f'-icount{icount}'
    final_pc = f'PC=20:{len(words) * 2:04x}'
    result = {'name': name, 'passed': False, 'expected_registers': expected,
              'expected_timer_hz': hz, 'host_guest_memory_writes': 0, 'nand_used': False}
    with tempfile.TemporaryDirectory(prefix='np560-clock-protection-') as temp:
        firmware = Path(temp) / 'caller.prg'
        program = bytearray(pack(words + [0xD0FF]))
        if original_body is not None:
            start, body = original_body
            offset = start - 0x200000
            assert offset > len(program)
            program.extend(bytes(offset + len(body) - len(program)))
            program[offset:] = body
            result['original_function_sha256'] = hashlib.sha256(body).hexdigest()
        firmware.write_bytes(program)
        emulator = Emulator(qemu=qemu, firmware=firmware,
                            start_paused=True, icount_shift=icount)
        result['owned_pid'] = emulator.process.pid
        try:
            if original_body is not None:
                start, body = original_body
                actual = base64.b64decode(emulator.snapshot('code', start, len(body))['frame'])
                assert actual == body, 'factory function differs on instruction bus'
                result['original_code_bus_verified'] = True
            emulator.qmp.execute('cont')
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                state = emulator.qmp.execute('qom-get', {'path': '/machine', 'property': 'cpu-state'})
                if final_pc in state or 'UNSUPPORTED=none' not in state:
                    break
                time.sleep(.01)
            emulator.qmp.execute('stop')
            result['cpu'] = emulator.qmp.execute('qom-get', {'path': '/machine', 'property': 'cpu-state'})
            result['timers'] = [emulator.qmp.execute('qom-get', {
                'path': '/machine', 'property': f'timer{i}-state'}) for i in range(3)]
            registers = {int(k): int(v, 16) for k, v in re.findall(
                r'\bR(\d+)\s*=([0-9a-f]{4})\b', '\n'.join(result['cpu'].splitlines()[:5]), re.I)}
            result['registers'] = registers
            assert final_pc in result['cpu'], result['cpu'][:1000]
            assert all(f'{field}=none' in result['cpu'] for field in
                       ('ROM_MISSING', 'UNSUPPORTED', 'INVALID_CONTROL'))
            assert all(registers[k] == v for k, v in expected.items()), (name, expected, registers)
            assert all(re.search(rf'\bHZ:{hz}\b', text) for text in result['timers']), result['timers']
            result['passed'] = True
        finally:
            emulator.close()
            result['exit_code'] = emulator.process.returncode
            (output / f'{name}.json').write_text(json.dumps(result, indent=2) + '\n')
            (output / f'{name}.qemu.log').write_bytes(emulator.log_path.read_bytes())
        assert result['exit_code'] == 0, result
    print(f'{name}: passed', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', required=True, type=Path)
    parser.add_argument('--original-prg', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--first-only', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in
                (('qemu', args.qemu), ('prg', args.original_prg))}
    (args.output / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    results = []
    for case in cases(args.original_prg.read_bytes()):
        for icount in (None, 5):
            results.append(check(args.qemu, args.output, case, icount))
            if args.first_only:
                return 0
    assert identity['qemu'] == hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    (args.output / 'report.json').write_text(json.dumps({'passed': True, 'identity': identity,
                                                       'cases': results}, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
