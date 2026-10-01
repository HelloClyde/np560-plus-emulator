#!/usr/bin/env python3
"""Execute guest-authored A/B cycle and EMCR wait-state fixtures.

No NAND, host guest-memory writes, timer injection, or decoder. Expected
cycles are annotations in the fixture, not a copy of the C opcode decoder.
Unknown cost counts are checked too: this is explicitly a partial model.
"""
from __future__ import annotations

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
import re
import struct
import time

from test_np560_instruction_clock import fields
from web.np560_web import Emulator, RunJournal


class Program:
    def __init__(self, base):
        self.base = base
        self.words = []
        self.instructions = self.cycles = self.waits = self.accesses = 0
        self.unknown_cost = self.unknown_map = 0

    def add(self, *words, cycles=1, waits=0, accesses=0, unknown=0, badmap=0):
        self.words.extend(words)
        self.instructions += 1
        self.cycles += cycles + waits
        self.waits += waits
        self.accesses += accesses
        self.unknown_cost += unknown
        self.unknown_map += badmap

    def terminal(self):
        pc = self.base + len(self.words)*2
        self.add(0xc701, unknown=1)
        return pc


def fixture(name):
    if name == 'unknown-regions':
        # USB-mapped SRAM executes NOP/SJMP, ROM executes MOV/MOV/AJMP/SJMP,
        # then SRAM NOP/terminal. Only conditional ROM AJMP lacks a cost; every
        # SRAM instruction lacks region timing even when its opcode is known.
        # NZ is true at reset; MOV does not alter flags. Keep this a
        # conditional encoding so cc=0 timing coverage cannot erase the case.
        words = [0x6800, 2, 0x68ff, 0x6000, 0xac02, 12, 0xad00, 0x1006]
        return (struct.pack('<8H', *words), 0x1008,
                dict(instructions=8, cycles=10, waits=0, accesses=0,
                     unknown_cost=5, unknown_map=0), {15: 0x6000}, None)
    external = name.endswith("-external")
    base = 0x210100 if external else 0x200100
    head = Program(0x200000)
    head.add(0x6800, 2)
    head.add(0x68ff, 0x6000)
    # Zero waits isolate A/B costs; the second group programs other values.
    head.add(0x6804, 0x5000)
    head.add(0x6805, 0x6000)
    head.add(0x6806, 0xf000)
    head.add(0xad00 | (base >> 16), base & 65535, cycles=3)
    p = Program(base)
    ab = 2 if external else 1
    expected_regs = {}
    timer_ticks = None
    if name.startswith('acall-always-'):
        # PDF pp.18,79: cc=0 ACALL costs four, RET costs two (p.92).
        # Execute actual call/return pairs, then jump around each subroutine.
        p.add(0x6826, 65535, cycles=ab)
        p.add(0x6827, 0x8080, cycles=ab)
        p.add(0x1f25); p.add(0x384f)
        for _ in range(256):
            start = base + len(p.words)*2
            p.add(0xbc00, (start+10) & 65535, cycles=4)
            p.add(0xac00, (start+16) & 65535, cycles=3)
            p.words.append(0xc701)
            p.add(0xc700)
            p.add(0xc600, cycles=2)
            p.words.append(0xc701)
        p.add(0x1f25); p.add(0x385f)
        p.add(0x6827, 0, cycles=ab)
        timer_ticks = 2560 + 2
        expected_regs[15] = 0x6000
    elif name.startswith('ret-'):
        # PDF p.92: RET alone (not RETI/RETS) costs two cycles.
        # Build a near-return frame in guest; skip a faulting word each time.
        p.add(0x6826, 65535, cycles=ab)
        p.add(0x6827, 0x8080, cycles=ab)
        p.add(0x1f25); p.add(0x384f)
        for _ in range(256):
            target = (base + len(p.words)*2 + 10) & 65535
            p.add(0x68f0, target, cycles=ab)
            p.add(0x58f0)  # MOV [--SP],R0
            p.add(0xc600, cycles=2)
            p.words.append(0xc701)
        p.add(0x1f25); p.add(0x385f)
        p.add(0x6827, 0, cycles=ab)
        timer_ticks = 256 * (ab + 3) + 2
        expected_regs.update({0: target, 15: 0x6000})
    elif name.startswith("rjmp-always-"):
        # PDF pp.18,90: cc=0 has no test, RJMP is four cycles.
        # Exercise signed forward AND backward offsets without a loop or
        # executing the unsupported word. Relative origin is next PC.
        p.add(0x6826, 65535, cycles=ab)
        p.add(0x6827, 0x8080, cycles=ab)
        p.add(0x1f25); p.add(0x384f)
        for _ in range(256):
            p.add(0xd002, cycles=4)  # word 0 -> word 3
            p.add(0xd003, cycles=4)  # word 1 -> word 5
            p.words.append(0xc701)  # word 2: must not execute
            p.add(0xd0fd, cycles=4) # word 3 -> word 1 (-3 words)
            p.words.append(0xc701)  # word 4: must not execute
        p.add(0x1f25); p.add(0x385f)
        p.add(0x6827, 0, cycles=ab)
        timer_ticks = 256 * 12 + 2
    elif name.startswith(("sjmp-", "ajmp-always-")):
        # PDF pp.18,88,91: SJMP and AJMP cc=0 cost three, no A/B split.
        # Jump over an unsupported word each time; it must never execute.
        p.add(0x6826, 65535, cycles=ab)
        p.add(0x6827, 0x8080, cycles=ab)
        p.add(0x1f25); p.add(0x384f)
        for _ in range(256):
            target = base + len(p.words) * 2 + 6
            opcode = 0xac00 if name.startswith('ajmp-') else 0xad00 | (target >> 16)
            p.add(opcode, target & 65535, cycles=3)
            p.words.append(0xc701)
        p.add(0x1f25); p.add(0x385f)
        p.add(0x6827, 0, cycles=ab)
        timer_ticks = 770
    elif name.startswith("arithmetic-"):
        p.add(0x68f0, 0, cycles=ab)
        p.add(0x6826, 65535, cycles=ab)
        p.add(0x6827, 0x8080, cycles=ab)
        p.add(0x1f25); p.add(0x384f)
        for _ in range(1024):
            p.add(0x70f0, 1, cycles=ab)
        p.add(0x1f25); p.add(0x385f)
        p.add(0x6827, 0, cycles=ab)
        timer_ticks = 1024*ab + 2
        expected_regs[0] = 1024
        # Signed 16/32-bit division costs four even on the A path.
        p.add(0x68f1, 7, cycles=ab)
        p.add(0x68f7, 100, cycles=ab)
        p.add(0xc201, cycles=4)
        p.add(0x0827)
        p.add(0x68f6, 1, cycles=ab)
        p.add(0x68f7, 0, cycles=ab)
        p.add(0xc401, cycles=4)
        p.add(0x0837)
        expected_regs.update({2:14, 3:9362, 6:2, 7:9362})
    elif name.split('-')[0] in ('and', 'or', 'sub', 'subc', 'xor', 'cmp'):
        family = name.split('-')[0]
        alu_delta = {'and': 0, 'or': 0x100, 'sub': -0x200,
                     'subc': -0x100, 'xor': 0x300, 'cmp': 0x200}[family]
        p.add(0x6810, 0, cycles=ab)
        p.add(0x68f0, 0xffff, cycles=ab)
        p.add(0x68f1, 0x00ff, cycles=ab)
        p.add(0x68f8, 0x0400, cycles=ab)
        p.add(0xa8f0, 0x0400, cycles=ab)
        p.add(0x6826, 65535, cycles=ab)
        p.add(0x6827, 0x8080, cycles=ab)
        p.add(0x1f25); p.add(0x384f)
        for _ in range(256):
            p.add(0x74f0 + alu_delta, 0xffff, cycles=ab)
            p.add(0x64f1 + alu_delta, 0xff, cycles=ab)
        p.add(0x1f25); p.add(0x385f)
        p.add(0x6827, 0, cycles=ab)
        timer_ticks = 512 * ab + 2
        # CN1916884A pp.24-25,49-56,95-96: both widths and
        # all addressing forms, including postincrement.
        for word in (0x1401,0x0401,0x3400,0x3408,0x2400,0x2408,0x540f,0x440f):
            p.add(word + alu_delta)
        # CMP has no memory-destination forms (A6/B6 are not CMP).
        long_forms = (0x94f0,0x84f0) if family == 'cmp' else (0x94f0,0x84f0,0xb4f0,0xa4f0)
        for word in long_forms:
            p.add(word + alu_delta,0x0400,cycles=ab)
        expected_regs[8] = 0x403
        if family == 'cmp':
            p.add(0x88f2, 0x0400, cycles=ab)  # original memory operand intact
            p.add(0x66f1, 0xff, cycles=ab)  # equal byte compare: Z, no C/N/V
            expected_regs.update({0: 0xffff, 1: 0xff, 2: 0xffff})
    elif name.startswith('multiply-'):
        # Only C0 0n is unambiguous in the published MUL encoding row.
        # UMUL's row permits the two register nibbles. No FR mode here.
        p.add(0x68f0, 0xfffd, cycles=ab)
        p.add(0x68f1, 11, cycles=ab)
        p.add(0x6826, 65535, cycles=ab)
        p.add(0x6827, 0x8080, cycles=ab)
        p.add(0x1f25); p.add(0x384f)
        for _ in range(256):
            p.add(0xc001)
            p.add(0xc101)
        p.add(0x1f25); p.add(0x385f)
        p.add(0x6827, 0, cycles=ab)
        timer_ticks = 514
        p.add(0xc001)  # signed -3 * 11 = -33
        p.add(0x0826); p.add(0x0837)
        p.add(0xc101)  # unsigned 65533 * 11 = 0x000affdf
        expected_regs.update({0: 0xfffd, 1: 11, 2: 0xffff, 3: 0xffdf,
                              6: 10, 7: 0xffdf})
    elif name.split('-')[0] in ('sl', 'sr', 'slosb', 'srosb'):
        # CN1916884A pp.63-70: three forms per family, one cycle each.
        # Negative register counts reverse direction, including [Rn++].
        family = name.split('-')[0]
        immediate, register, memory = {
            'sl': (0x4c00, 0x0c00, 0x2c00),
            'sr': (0x4d00, 0x0d00, 0x2d00),
            'slosb': (0x5c00, 0x1c00, 0x3c00),
            'srosb': (0x5d00, 0x1d00, 0x3d00),
        }[family]
        p.add(0x6810, 0, cycles=ab)
        p.add(0x68f0, 3, cycles=ab)
        p.add(0x68f1, 0xff, cycles=ab)
        p.add(0x68f8, 0x0400, cycles=ab)
        p.add(0x68f2, 0x8001, cycles=ab)
        p.add(0xa8f2, 0x0400, cycles=ab)
        p.add(0x6826, 65535, cycles=ab)
        p.add(0x6827, 0x8080, cycles=ab)
        p.add(0x1f25); p.add(0x384f)
        for _ in range(512):
            p.add(immediate)  # count zero is still a real instruction
        p.add(0x1f25); p.add(0x385f)
        p.add(0x6827, 0, cycles=ab)
        timer_ticks = 514
        p.add(immediate | 1)
        p.add(register | 3)  # R0,RB3 (R1 low byte, -1)
        p.add(memory | 0x83)  # [R8++],RB3 (-1)
        p.add(0x88f2, 0x0400, cycles=ab)
        left_family = family in ('sl', 'slosb')
        expected_regs.update({0: 3 if left_family else 2,
                              2: 0x4000 if left_family else 2, 8: 0x402})
        if family in ('slosb', 'srosb'):
            p.add(0x6802, 0x10, cycles=ab)  # nonzero SB must merge even at count zero
            p.add(immediate)
            expected_regs[0] |= 0x10
    elif name.startswith('cmpupdate-'):
        p.add(0x6810, 0, cycles=ab)
        p.add(0x68f0, 0x100, cycles=ab)
        p.add(0xa8f0, 0x0400, cycles=ab)
        p.add(0x6826, 65535, cycles=ab)
        p.add(0x6827, 0x8080, cycles=ab)
        p.add(0x1f25); p.add(0x384f)
        for _ in range(128):
            for word in (0x6ef0, 0x7ef0, 0x6ff0, 0x7ff0):
                p.add(word, 0x100, cycles=2)
        p.add(0x1f25); p.add(0x385f)
        p.add(0x6827, 0, cycles=ab)
        timer_ticks = 1026
        # Check each update independently, not only their net zero sum.
        for word, destination in ((0x8ef0, 1), (0x9ef0, 2),
                                  (0x8ff0, 3), (0x9ff0, 6)):
            p.add(word, 0x0400, cycles=2)
            p.add(0x0800 | (destination << 4))
        p.add(0x4e00); p.add(0x4f00); p.add(0x5f00)
        # The PDF prints 2E for short CMPD2, conflicting with LINK;
        # runtime decodes 5E. Do not assert an unverified short-form cost.
        p.add(0x5e00, unknown=1)
        p.add(0x88f7, 0x0400, cycles=ab)
        p.add(0x6ef0, 0x100, cycles=2)  # compare equal THEN decrement
        expected_regs.update({0: 0xff, 1: 0xff, 2: 0xfd,
                              3: 0xfe, 6: 0x100, 7: 0x100})
    elif name == "wait-timer":
        p.add(0x6804, 0x5003)
        p.add(0x6810, 0xa2)
        p.add(0x68f8, 0x0400)
        p.add(0x6826, 65535)
        p.add(0x6827, 0x8080)
        p.add(0x1f25); p.add(0x384f)
        for _ in range(4096):
            p.add(0x2808, waits=3, accesses=1)
        p.add(0x1f25); p.add(0x385f)
        p.add(0x6827, 0)
        timer_ticks = 4096*4 + 2
    elif name == "unknown-divide":
        p.add(0x68f1, 7)
        p.add(0x68f6, 1)
        p.add(0x68f7, 0)
        p.add(0xc501, unknown=1)  # Legal semantics; source timing is '?'.
        expected_regs.update({6:2, 7:9362})
    elif name == "wait-boundaries":
        p.add(0x6800, 2 | (3 << 6))  # first region: SOCR.WS, not EMCR1.WS
        p.add(0x6804, 0x5001)
        p.add(0x6805, 0x6002)
        p.add(0x6806, 0xf000)
        for address, ws in ((0x20fffc,0), (0x210000,3),
                            (0x4ffffe,3), (0x500000,1),
                            (0x5ffffe,1), (0x600000,2),
                            (0xeffffe,2), (0xf00000,0),
                            (0xfffffe,0)):
            p.add(0x6810, address >> 15)
            p.add(0x68f8, address & 0x7fff)
            for word in (0x2808, 0x2908):  # word/byte each ONE bus access
                p.add(word, waits=ws, accesses=int(address >= 0x210000))
    elif name in ("wait-data", "wait-data-minimal"):
        p.add(0x6804, 0x5003)
        p.add(0x6810, 0xa2)  # external 51:xxxx data RAM
        p.add(0x6811, 0xa3)
        p.add(0x68f8, 0x0400)
        p.add(0x68f9, 0x0402)
        p.add(0x68fb, 0x0400)
        p.add(0x68fc, 0x8000)
        p.add(0x68f1, 0x1234)
        p.add(0x0a81, waits=3, accesses=1)
        p.add(0x2828, waits=3, accesses=1)
        p.add(0x2968, waits=3, accesses=1)  # high byte -> RB6 (R3 high)
        p.add(0xb0f1, 0x0400, waits=6, accesses=2)  # genuine RMW
        p.add(0x2a98, waits=6, accesses=2)  # genuine read + write
        p.add(0x2839, waits=3, accesses=1)
        p.add(0x3f10)
        p.add(0x2808)  # IGNDS -> internal SRAM, no external wait
        p.add(0x280b)  # FP internal even with DS selecting external RAM
        p.add(0x280c)  # Y internal even with DS1 selecting external RAM
        p.add(0x280f)  # SP internal
        # Change the actual wait register in guest; subsequent accesses
        # must not retain a stale value cached at TB translation.
        p.add(0x6804, 0x5001)
        p.add(0x2848, waits=1, accesses=1)
        # Unknown/inverted map is reported, not sorted or fabricated.
        p.add(0x6804, 0x7001)
        p.add(0x2808, accesses=1, badmap=1)
        expected_regs.update({2:0x1234, 3:0x2468, 4:0x2468})
    elif name == "repeat":
        p.add(0x68f0, 0)
        p.add(0xbf00, 15)
        p.add(0x70f0, 1)
        # The operand executes 16 times, but the setup only once.
        p.instructions += 15
        p.cycles += 15
        expected_regs[0] = 16
    else:
        raise ValueError(name)
    terminal = p.terminal()
    image = bytearray(base - 0x200000 + len(p.words)*2)
    struct.pack_into(f"<{len(head.words)}H", image, 0, *head.words)
    struct.pack_into(f"<{len(p.words)}H", image, base-0x200000, *p.words)
    totals = {key:getattr(head,key)+getattr(p,key) for key in (
        "instructions","cycles","waits","accesses","unknown_cost","unknown_map")}
    return image, terminal, totals, expected_regs, timer_ticks


def run(qemu, output, name, observer_minimal=None):
    image, terminal, expected, expected_regs, timer_ticks = fixture(name)
    minimal = name.endswith('-minimal') if observer_minimal is None else observer_minimal
    label = name if observer_minimal is None else name + ('-minimal-mode' if minimal else '-full-mode')
    firmware = output / (label + ".prg")
    firmware.write_bytes(image)
    result = dict(name=label, expected=expected, passed=False, minimal=minimal)
    journal = RunJournal(output/"runs", case=label)
    emu = None
    try:
        boot_options = {}
        if name == 'unknown-regions':
            loader = output / (label + '.usb')
            loader.write_bytes(struct.pack('>5H', 0xc700, 0xad20, 0, 0xc700, 0xc701))
            boot_options = dict(boot_mode='usb', usb_loader=loader)
        emu = Emulator(qemu=qemu, firmware=firmware, start_paused=True,
                       icount_shift=0, journal=journal, **boot_options)
        for prop in ("instruction-clock", "control-observers-minimal"):
            emu.qmp.execute("qom-set", {"path":"/machine", "property":prop,
                "value": prop == "instruction-clock" or minimal})
        profile_property = {'path': '/machine', 'property': 'instruction-clock-profile'}
        assert json.loads(emu.qmp.execute('qom-get', profile_property))['enabled'] is False
        emu.qmp.execute('qom-set', {'path': '/machine',
            'property': 'instruction-clock-profile-enabled', 'value': True})
        emu.qmp.execute("cont")
        marker = f"UNSUPPORTED={terminal>>16:02x}:{terminal&65535:04x} WORD=c701 COUNT=1"
        deadline = time.monotonic()+20
        while time.monotonic() < deadline:
            state = emu.qmp.execute("qom-get", {"path":"/machine", "property":"cpu-state"})
            if marker in state or "UNSUPPORTED=none" not in state:
                break
            time.sleep(.01)
        emu.qmp.execute("stop")
        state = emu.qmp.execute("qom-get", {"path":"/machine", "property":"cpu-state"})
        clock = emu.qmp.execute("qom-get", {"path":"/machine", "property":"instruction-clock-state"})
        (output/(label+".cpu.txt")).write_text(state)
        (output/(label+".clock.txt")).write_text(clock)
        f = fields(clock)
        result.update(clock=clock, raw_icount=emu.qmp.execute("query-replay")["icount"])
        assert marker in state and "ROM_MISSING=none" in state and "INVALID_CONTROL=none" in state, state[:1200]
        assert f["FAULT"] == 0 and "MODEL:documented-partial-v1 " in clock, result
        for field, key in (("INSTRUCTIONS","instructions"), ("CYCLES","cycles"),
                           ("DATA_WAITS","waits"), ("EXTERNAL_DATA","accesses"),
                           ("UNKNOWN_COST","unknown_cost"), ("UNKNOWN_MAP","unknown_map")):
            assert f[field] == expected[key], (field, f[field], expected[key], result)
        assert result["raw_icount"] == expected["instructions"], result
        sram_unknown = 4 if name == 'unknown-regions' else 0
        assert f['UNKNOWN_SRAM'] == sram_unknown, result
        assert f['UNKNOWN_OPCODE'] == expected['unknown_cost']-sram_unknown, result
        profile = json.loads(emu.qmp.execute('qom-get', profile_property))
        result['unknown_cycle_profile'] = profile
        assert profile['enabled'] and sum(profile['opcodes'].values()) == f['UNKNOWN_OPCODE'], profile
        assert sum(profile['executed'].values()) == f['INSTRUCTIONS'], profile
        assert (list(profile['top_words'].values()) ==
                sorted(profile['top_words'].values(), reverse=True)), profile
        assert sum(profile['top_words'].values()) <= f['INSTRUCTIONS'], profile
        assert json.loads(emu.qmp.execute('qom-get', profile_property)) == profile
        fixed = ((1000000000 << 32)//24576000) * expected["cycles"]
        assert (f["NS"],f["FRACTION"]) == (fixed>>32,fixed&0xffffffff), result
        regs = {int(k):int(v,16) for k,v in re.findall(
            r"\bR(\d+)\s*=([0-9a-f]+)", "\n".join(state.splitlines()[:5]), re.I)}
        result["registers"] = regs
        result['psw'] = re.search(r'\bPSW=([ZCNV-]+)', state)[1]
        assert all(regs[k] == v for k,v in expected_regs.items()), (regs, expected_regs)
        if name.startswith(('cmp-', 'cmpupdate-')):
            assert 'PSW=Z---' in state, state[:300]
        if timer_ticks is not None:
            delta = (regs[5]-regs[4]) & 65535
            result["timer_ticks"] = delta
            assert abs(delta-timer_ticks) <= 1, (delta,timer_ticks)
        # Read-only state observation must not invent guest bus transactions.
        for _ in range(3):
            emu.qmp.execute("qom-get", {"path":"/machine", "property":"cpu-state"})
        assert emu.qmp.execute("qom-get", {"path":"/machine", "property":"instruction-clock-state"}) == clock
        if name == 'unknown-regions':
            assert profile['opcodes'] == {'ac': 1}, profile
            emu.qmp.execute('qom-set', {'path': '/machine',
                'property': 'instruction-clock-profile-enabled', 'value': False})
            disabled = json.loads(emu.qmp.execute('qom-get', profile_property))
            assert (not disabled['enabled'] and
                    disabled['opcodes'] == profile['opcodes'] and
                    disabled['executed'] == profile['executed'] and
                    disabled['top_words'] == profile['top_words'])
            emu.qmp.execute('system_reset')
            reset = fields(emu.qmp.execute('qom-get', {
                'path': '/machine', 'property': 'instruction-clock-state'}))
            assert all(reset[k] == 0 for k in ('UNKNOWN_COST', 'UNKNOWN_SRAM', 'UNKNOWN_OPCODE')), reset
            reset_profile = json.loads(emu.qmp.execute('qom-get', profile_property))
            assert (not reset_profile['enabled'] and reset_profile['opcodes'] == {}
                    and reset_profile['executed'] == {} and
                    reset_profile['top_words'] == {}), reset_profile
            # Repeat the same guest with profiling left at its reset default.
            # The clock still counts unknown costs, but the histogram stays empty.
            emu.qmp.execute('cont')
            disabled_deadline = time.monotonic()+5
            while time.monotonic() < disabled_deadline:
                disabled_state = emu.qmp.execute('qom-get', {'path': '/machine', 'property': 'cpu-state'})
                if marker in disabled_state:
                    break
                time.sleep(.01)
            emu.qmp.execute('stop')
            assert marker in disabled_state, disabled_state[:1200]
            disabled_clock = fields(emu.qmp.execute('qom-get', {
                'path': '/machine', 'property': 'instruction-clock-state'}))
            assert disabled_clock['UNKNOWN_COST'] == 5 and disabled_clock['CYCLES'] == 10, disabled_clock
            assert json.loads(emu.qmp.execute('qom-get', profile_property)) == reset_profile
            result['disabled_profile_verified'] = True
        result["passed"] = True
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        if emu is not None:
            emu.close()
            result["exit_code"] = emu.process.returncode
        else:
            result["exit_code"] = journal.snapshot().get("qemu_returncode")
    result["passed"] &= result["exit_code"] == 0
    print(json.dumps(result), flush=True)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument('--compare-observers', action='store_true',
                   help='Run every fixture in full and minimal modes and compare architectural results')
    args = p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    names = (
        "arithmetic-internal","arithmetic-external","and-internal","and-external",
        "or-internal","or-external","unknown-divide",
        "sub-internal","sub-external","subc-internal","subc-external",
        "xor-internal","xor-external",
        "cmp-internal","cmp-external",
        "cmpupdate-internal","cmpupdate-external",
        "sl-internal","sl-external",
        "sr-internal","sr-external","slosb-internal","slosb-external",
        "srosb-internal","srosb-external",
        "multiply-internal","multiply-external","sjmp-internal","sjmp-external",
        "rjmp-always-internal","rjmp-always-external",
        "ajmp-always-internal","ajmp-always-external",
        "acall-always-internal","acall-always-external",
        "ret-internal","ret-external",
        "wait-boundaries","wait-data","wait-data-minimal","wait-timer","repeat","unknown-regions")
    cases = []
    comparisons = []
    for name in names:
        if not args.compare_observers:
            cases.append(run(args.qemu, args.output, name))
            continue
        pair = [run(args.qemu, args.output, name, mode) for mode in (False, True)]
        cases.extend(pair)
        # Timer0 sampling has a documented one-tick scheduling tolerance;
        # each run checks it independently. Do not hide other registers.
        excluded = {4, 5} if fixture(name)[4] is not None else set()
        regs = [{k: v for k, v in c.get('registers', {}).items() if k not in excluded}
                for c in pair]
        matched = (all(c['passed'] for c in pair) and regs[0] == regs[1]
                   and pair[0]['clock'] == pair[1]['clock']
                   and pair[0]['psw'] == pair[1]['psw']
                   and pair[0]['raw_icount'] == pair[1]['raw_icount'])
        comparisons.append(dict(name=name, passed=matched,
            independently_checked_timer_registers=sorted(excluded)))
    assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
    report = dict(passed=all(c["passed"] for c in cases) and
                        all(c['passed'] for c in comparisons), cases=cases,
                  observer_comparisons=comparisons,
                  qemu_sha256=identity, host_guest_memory_writes=0, nand_used=False,
                  scope="documented subset and inserted data waits, NOT full pipeline/bus timing")
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
