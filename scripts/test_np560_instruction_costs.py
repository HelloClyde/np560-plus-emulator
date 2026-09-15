#!/usr/bin/env python3
"""Execute guest-authored A/B cycle and EMCR wait-state fixtures.

No NAND, host guest-memory writes, timer injection, or decoder. Expected
cycles are annotations in the fixture, not a copy of the C opcode decoder.
Unknown cost counts are checked too: this is explicitly a partial model.
"""
from __future__ import annotations

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
    external = name == "arithmetic-external"
    base = 0x210100 if external else 0x200100
    head = Program(0x200000)
    head.add(0x6800, 2)
    head.add(0x68ff, 0x6000)
    # Zero waits isolate A/B costs; the second group programs other values.
    head.add(0x6804, 0x5000)
    head.add(0x6805, 0x6000)
    head.add(0x6806, 0xf000)
    head.add(0xad00 | (base >> 16), base & 65535, unknown=1)
    p = Program(base)
    ab = 2 if external else 1
    expected_regs = {}
    timer_ticks = None
    if name.startswith("arithmetic-"):
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


def run(qemu, output, name):
    image, terminal, expected, expected_regs, timer_ticks = fixture(name)
    firmware = output / (name + ".prg")
    firmware.write_bytes(image)
    result = dict(name=name, expected=expected, passed=False)
    journal = RunJournal(output/"runs", case=name)
    emu = None
    try:
        emu = Emulator(qemu=qemu, firmware=firmware, start_paused=True,
                       icount_shift=0, journal=journal)
        for prop in ("instruction-clock", "control-observers-minimal"):
            emu.qmp.execute("qom-set", {"path":"/machine", "property":prop,
                "value": prop == "instruction-clock" or name.endswith("-minimal")})
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
        (output/(name+".cpu.txt")).write_text(state)
        (output/(name+".clock.txt")).write_text(clock)
        f = fields(clock)
        result.update(clock=clock, raw_icount=emu.qmp.execute("query-replay")["icount"])
        assert marker in state and "ROM_MISSING=none" in state and "INVALID_CONTROL=none" in state, state[:1200]
        assert f["FAULT"] == 0 and "MODEL:documented-partial-v1 " in clock, result
        for field, key in (("INSTRUCTIONS","instructions"), ("CYCLES","cycles"),
                           ("DATA_WAITS","waits"), ("EXTERNAL_DATA","accesses"),
                           ("UNKNOWN_COST","unknown_cost"), ("UNKNOWN_MAP","unknown_map")):
            assert f[field] == expected[key], (field, f[field], expected[key], result)
        assert result["raw_icount"] == expected["instructions"], result
        fixed = ((1000000000 << 32)//24576000) * expected["cycles"]
        assert (f["NS"],f["FRACTION"]) == (fixed>>32,fixed&0xffffffff), result
        regs = {int(k):int(v,16) for k,v in re.findall(
            r"\bR(\d+)\s*=([0-9a-f]+)", "\n".join(state.splitlines()[:5]), re.I)}
        result["registers"] = regs
        assert all(regs[k] == v for k,v in expected_regs.items()), (regs, expected_regs)
        if timer_ticks is not None:
            delta = (regs[5]-regs[4]) & 65535
            result["timer_ticks"] = delta
            assert abs(delta-timer_ticks) <= 1, (delta,timer_ticks)
        # Read-only state observation must not invent guest bus transactions.
        for _ in range(3):
            emu.qmp.execute("qom-get", {"path":"/machine", "property":"cpu-state"})
        assert emu.qmp.execute("qom-get", {"path":"/machine", "property":"instruction-clock-state"}) == clock
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
    args = p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    cases = [run(args.qemu,args.output,name) for name in (
        "arithmetic-internal","arithmetic-external","unknown-divide",
        "wait-boundaries","wait-data","wait-data-minimal","wait-timer","repeat")]
    assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
    report = dict(passed=all(c["passed"] for c in cases), cases=cases,
                  qemu_sha256=identity, host_guest_memory_writes=0, nand_used=False,
                  scope="documented subset and inserted data waits, NOT full pipeline/bus timing")
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
