#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Version-4 software copy gate: exact bytes, ABI and no partial invalid writes.

An isolated synthetic guest creates the documented HLE workspace and owner;
it is not a factory heap/lifecycle or playback test. All input construction
runs as guest instructions. No debugger RAM writes, NAND or device bypass.
"""

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_np560_mp3_resident import load_bundle
from np560_assembler import _DMCUAssembler
from test_np560_mac import run

OWNER, WORK, OUTPUT = 0x514a46, 0x518100, 0x1782
BUFFERS = (0x1784, 0x2084, 0x1c04, 0x2504)


def check(qemu, bundle, output, name, *, phase=0, mutation=None,
          offset=None, ds=None, bad=False, icount=None):
    _, rom, manifest = load_bundle(bundle)
    hle = manifest['rom_mp3_hle']
    assert hle['version'] in (4, 5)
    a = _DMCUAssembler(0x200000)
    def imm(r, value): a.emit(0x68f0 | r, value & 65535)
    def call(target): a.emit(0xbd00 | target >> 16, target & 65535)
    def const(address, value):
        a.emit(0x6810, address >> 15)
        imm(0, value); a.emit(0xa8f0, address & 0x7fff)
    def fill(address, count, start, step=0):
        a.emit(0x6811, address >> 15)
        imm(5, (address & 0x7fff) | 0x8000)
        imm(1, count); imm(0, start)
        label = 'fill_' + str(address)
        a.label(label); a.emit(0x1a50)
        if step: a.emit(0x70f0, step)
        a.emit(0x5211); a.ajmp(label, 2)

    a.emit(0x6800, 2); imm(15, 0x7000)
    a.emit(0x6810, WORK >> 15); imm(3, WORK & 0x7fff)
    call(hle['targets']['reset'])
    fill(OWNER, 48, 0)
    fields = {8: WORK >> 15, 16: WORK & 0x7fff,
              44: 0x534d, 46: 1, 48: phase ^ 1, 50: 0, 80: 1, 82: 0x504d}
    fields.update({20 + 4*i: ptr for i, ptr in enumerate(BUFFERS)})
    for off, value in fields.items(): const(OWNER + off, value)
    const(WORK + 14, 576)
    fill(WORK + 0x5700, 576, 0x8123, 31)
    fill(WORK + 0x5b80, 576, 0x4567, 17)
    fill(OUTPUT, 2306, 0x5aa5)  # both guards plus four complete buffers
    if mutation:
        for address, value in mutation.items(): const(address, value)
    for reg in range(1, 15): imm(reg, 0x1100 + reg)
    input_offset = OWNER & 0x7fff if offset is None else offset
    input_ds = OWNER >> 15 if ds is None else ds
    imm(0, phase); imm(3, input_offset)
    a.emit(0x6810, input_ds, 0x6811, 0x34)
    call(hle['targets']['copy_pcm'])
    # Capture the unchanged bank registers into scratch result registers.
    a.emit(0x1f10, 0x38cf, 0x1f11, 0x38df)
    expected = {reg: 0x1100 + reg for reg in range(1, 15)}
    expected.update({0: 0 if bad else 576, 2: 2 if bad else 0,
                     3: input_offset, 12: input_ds, 13: 0x34, 15: 0x7000})
    case = run(qemu, output, name, a.finish(), expected, rom=rom,
               rom_mp3_hle_base=hle['base'], icount=icount,
               capture_ranges=[('outputs', OUTPUT, 4612), ('owner', OWNER, 96),
                               ('pcm', WORK + 0x5700, 2304)],
               metadata={'synthetic_gate_contract_only': True, 'invalid': bad,
                         'phase': phase, 'rom_sha256': manifest['rom_sha256']})
    want = [0x5aa5] * 2306
    source = [[(0x8123 + 31*i) & 65535 for i in range(576)],
              [(0x4567 + 17*i) & 65535 for i in range(576)]]
    if not bad:
        for ch in range(2):
            start = (BUFFERS[ch*2 + phase] - OUTPUT) // 2
            want[start:start+576] = source[ch]
    expected_owner = [0] * 48
    for off, value in fields.items(): expected_owner[off//2] = value
    for address, value in (mutation or {}).items():
        if OWNER <= address < OWNER+96: expected_owner[(address-OWNER)//2] = value
    def matches(label, values):
        return Path(case['captures'][label]['path']).read_bytes() == struct.pack(
            '<' + str(len(values)) + 'H', *values)
    state = case['rom_mp3_hle']
    case['copy_checks'] = dict(outputs_exact=matches('outputs', want),
                              owner_unchanged=matches('owner', expected_owner),
                              source_unchanged=matches('pcm', source[0]+source[1]),
                              counters=(state['pcm_copy_calls'] == 1 and
                                        state['pcm_copy_failures'] == int(bad)))
    case['passed'] = case['passed'] and all(case['copy_checks'].values())
    (output/(name+'.json')).write_text(json.dumps(case, indent=2)+'\n')
    print(name, case['copy_checks'], flush=True)
    return case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('qemu', 'resident-bundle', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(passed=False, cases=[], qemu_sha256=hashlib.sha256(args.qemu.read_bytes()).hexdigest())
    cases = [('phase-a', {}), ('phase-b-icount', dict(phase=1, icount=5)),
             ('invalid-phase', dict(phase=2)), ('unaligned-owner', dict(offset=0x4a47)),
             ('overflow-owner', dict(offset=0x7fa2)), ('non-owner-bank', dict(ds=0))]
    for name, address, value in (
        ('not-claimed', OWNER+46, 0), ('phase-not-toggled', OWNER+48, 0),
        ('wrong-owner-signature', OWNER+82, 0), ('no-owner-handle', OWNER+80, 0),
        ('closed-owner', OWNER+44, 0), ('invalid-workspace-bank', OWNER+8, 0x200),
        ('unregistered-workspace', OWNER+16, 0x200), ('invalid-workspace-magic', WORK+20, 0),
        ('short-pcm', WORK+14, 575), ('nonzero-output-bank', OWNER+30, 1),
        ('unaligned-output', OWNER+32, 0x2505), ('overlapping-output', OWNER+32, 0x1784),
        ('low-output', OWNER+32, 0x1000), ('overflow-output', OWNER+32, 0x7b82)):
        cases.append((name, dict(mutation={address: value})))
    try:
        for index, (name, options) in enumerate(cases):
            report['cases'].append(check(args.qemu, args.resident_bundle, args.output,
                                         name, bad=index >= 2, **options))
        report['passed'] = all(case['passed'] for case in report['cases'])
    except (AssertionError, RuntimeError) as error:
        report['failure'] = str(error)[:2000]
        print(report['failure'], flush=True)
    finally:
        (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
