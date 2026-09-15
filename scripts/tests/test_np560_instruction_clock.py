#!/usr/bin/env python3
"""Check the explicit one-cycle clock-domain baseline, not full CPU cycles.

Guest programs select clocks and operate timers. No NAND, host RAM writes,
fake IRQ, or MP3 decoder. Independent 32.768 kHz TB bounds instruction
progress, preventing a mere self-consistent diagnostic counter from passing.
"""
from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import struct
import time

from web.np560_web import Emulator, QMPError, RunJournal


class Program:
    def __init__(self):
        self.words = []
        self.rates = []
        self.hz = 24576000

    def add(self, *words, hz_after=None):
        self.words.extend(words)
        self.rates.append(self.hz)
        if hz_after is not None:
            self.hz = hz_after

    def select(self, select, hz):
        self.add(0xee00)
        self.add(0x682e, select, hz_after=hz)
        self.add(0xfe00)


def program(name):
    p = Program()
    p.add(0x6800, 2)  # IE off; CLKCON locked until UP is set.
    p.add(0x68ff, 0x6000)
    if name == "changes":
        # Includes fractional periods, extremes, aliases, PLL switches and
        # a locked write that MUST NOT alter CPU time or device frequency.
        for select, hz in ((0,24576000),(7,192000),(8,16384000),(15,128000),
                           (16,32768),(31,32768),(1,12288000),(0,24576000)):
            p.select(select, hz)
            for _ in range(257):
                p.add(0xc700)
        p.add(0x682e, 16)  # locked: ignored
        p.add(0x68e9, 0x85e3, hz_after=48000000)
        p.select(1, 24000000)
        for _ in range(1024):
            p.add(0xc700)
        p.add(0x68e9, 0, hz_after=12288000)
    elif name in ("timer-fast", "timer-slow"):
        # Timer0 runs in the same clock domain. Its count must advance one
        # tick per baseline instruction, irrespective of the selected rate.
        if name == "timer-slow":
            p.select(16, 32768)
        p.add(0x6826, 65535)
        p.add(0x6827, 0x8080)
        p.add(0x1f25); p.add(0x384f)
        for _ in range(4096):
            p.add(0xc700)
        p.add(0x1f25); p.add(0x385f)
        p.add(0xff27)
    elif name == "independent-tb":
        p.add(0x6850, 0)
        p.add(0x682f, 0x8000)
        p.add(0x5061)
        p.add(0x9b50, 0x01fd)  # R6++; JNB TBICR.RQ back to the ADD
        p.add(0xff2f)
        # Dynamic loop count is verified independently after running.
    elif name == "power-unsupported":
        p.select(0x40, 24576000)
    elif name == "rate-unsupported":
        p.add(0x68e9, 0x9fe0, hz_after=1024000000)
    else:
        raise ValueError(name)
    final_pc = len(p.words)*2
    p.add(0xc701)  # checked terminal attempted instruction
    return p, final_pc


def fields(text):
    return {k: int(v, 16 if k in ("FRACTION", "LAST_UNKNOWN") else 10)
            for k,v in re.findall(r"\b([A-Z_]+):([0-9a-f]+)\b", text)}


def run(qemu, output, name, minimal=False):
    p, final_pc = program(name)
    raw = struct.pack(f"<{len(p.words)}H", *p.words)
    firmware = output/(name + ".prg")
    firmware.write_bytes(raw)
    journal = RunJournal(output/"runs", case=name)
    result = dict(name=name, passed=False, minimal=minimal, run_directory=str(journal.directory))
    emu = None
    try:
        emu = Emulator(qemu=qemu, firmware=firmware, start_paused=True,
                       icount_shift=0, journal=journal)
        emu.qmp.execute("qom-set", {"path":"/machine", "property":"instruction-clock", "value":True})
        if minimal:
            emu.qmp.execute('qom-set', {'path':'/machine', 'property':'control-observers-minimal', 'value':True})
        emu.qmp.execute("cont")
        for attempt in range(300):
            clock = emu.qmp.execute("qom-get", {"path":"/machine", "property":"instruction-clock-state"})
            state = emu.qmp.execute("qom-get", {"path":"/machine", "property":"cpu-state"})
            if fields(clock)["FAULT"] or f"UNSUPPORTED=20:{final_pc:04x} WORD=c701 COUNT=1" in state:
                break
            time.sleep(.01)
        emu.qmp.execute("stop")
        state = emu.qmp.execute("qom-get", {"path":"/machine", "property":"cpu-state"})
        clock = emu.qmp.execute("qom-get", {"path":"/machine", "property":"instruction-clock-state"})
        (output/(name+".cpu.txt")).write_text(state)
        f = fields(clock)
        result.update(clock=clock, icount=emu.qmp.execute("query-replay")["icount"])
        assert "ROM_MISSING=none" in state and "INVALID_CONTROL=none" in state
        if name.endswith("unsupported"):
            assert f["FAULT"] == (1 if name.startswith("power") else 2), clock
            assert "UNSUPPORTED=none" in state  # clock-mode gap, not a bad opcode
        else:
            assert f"UNSUPPORTED=20:{final_pc:04x} WORD=c701 COUNT=1" in state, state[:1000]
            assert f["FAULT"] == 0 and result["icount"] == f["INSTRUCTIONS"], result
            header = "\n".join(state.splitlines()[:5])
            regs = {int(k):int(v,16) for k,v in re.findall(r"\bR(\d+)\s*=([0-9a-f]+)",header,re.I)}
            if name == "independent-tb":
                # 24.576 MHz / 32768 Hz = 750 cycles. Two instructions per
                # poll. Event dispatch occurs at instruction boundaries.
                assert 375 <= regs[6] <= 376, regs
                expected_count = len(p.rates)+2*(regs[6]-1)
                assert f["INSTRUCTIONS"] == expected_count
                tb = emu.qmp.execute("qom-get", {"path":"/machine", "property":"timebase-state"})
                result["timebase"] = tb
                assert "RUNNING:0 " in tb and "EXPIRED:1 " in tb, tb
            else:
                assert f["INSTRUCTIONS"] == len(p.rates), result
                fixed = sum((1000000000 << 32)//hz for hz in p.rates)
                exact = sum((Fraction(1000000000,hz) for hz in p.rates),Fraction())
                result.update(expected_ns=fixed>>32, rational_ns_floor=int(exact))
                assert (f["NS"], f["FRACTION"]) == (fixed>>32, fixed&0xffffffff), result
                assert 0 <= exact-f["NS"] < 2, result
                if name.startswith("timer-"):
                    delta=(regs[5]-regs[4])&65535
                    result["timer_ticks"] = delta
                    assert 4097 <= delta <= 4099, result  # 4098 ± sub-ns boundary rounding
            # A paused read must not advance the clock-domain phase.
            time.sleep(.03)
            assert emu.qmp.execute("qom-get", {"path":"/machine", "property":"instruction-clock-state"}) == clock
            try:
                emu.qmp.execute("qom-set", {"path":"/machine", "property":"instruction-clock", "value":False})
            except QMPError as error:
                assert "before first execution" in str(error)
            else:
                raise AssertionError("late clock-mode change accepted")
            if name == "changes":
                emu.qmp.execute("system_reset")
                reset=fields(emu.qmp.execute("qom-get", {"path":"/machine", "property":"instruction-clock-state"}))
                assert reset["ENABLED"] == 1 and reset["NS"] == reset["FRACTION"] == reset["INSTRUCTIONS"] == 0
                assert reset["HZ"] == 24576000, reset
        result["passed"] = True
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        if emu is not None:
            emu.close(); result["exit_code"] = emu.process.returncode
        else:
            result["exit_code"] = journal.snapshot().get("qemu_returncode")
    result["passed"] &= result["exit_code"] == 0
    print(json.dumps(result), flush=True)
    return result


def reject(qemu, output, shift):
    firmware=output/f"reject-{shift}.prg"
    firmware.write_bytes(struct.pack("<H",0xc701))
    emu=Emulator(qemu=qemu,firmware=firmware,start_paused=True,icount_shift=shift)
    try:
        try:
            emu.qmp.execute("qom-set", {"path":"/machine", "property":"instruction-clock", "value":True})
        except QMPError as error:
            assert "fixed icount shift=0" in str(error)
        else: raise AssertionError("invalid icount mode accepted")
    finally: emu.close()
    assert emu.process.returncode == 0
    return dict(name=f"reject-{shift}", passed=True, exit_code=emu.process.returncode)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument('--minimal', action='store_true')
    args=p.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    identity=hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    cases=[run(args.qemu,args.output,name,args.minimal) for name in (
        "changes","timer-fast","timer-slow","independent-tb","power-unsupported","rate-unsupported")]
    cases += [reject(args.qemu,args.output,shift) for shift in (None,5,"auto")]
    assert hashlib.sha256(args.qemu.read_bytes()).hexdigest()==identity
    report=dict(qemu_sha256=identity,cases=cases,passed=all(c["passed"] for c in cases),
                host_guest_memory_writes=0,nand_used=False,
                scope="clock domains and baseline cycles; not instruction/bus/pipeline timing completion")
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    return 0 if report["passed"] else 1


if __name__=="__main__": raise SystemExit(main())
