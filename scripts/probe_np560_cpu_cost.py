#!/usr/bin/env python3
"""Bounded CPU throughput and optional read-only host stack sampling.

The timed guest runs a fixed register/branch loop, without NAND/ROM/HLE or
enabled interrupts. GDB sampling is a SEPARATE owned process, never a speed
measurement or a debugger attached to a user's emulator.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import time

from web.np560_web import Emulator, RunJournal


def program(outer, workload="register"):
    words = [0x6800, 2, 0x68ff, 0x6000, 0x68fb, 0, 0x68f4, outer]
    outer_pc = 2*len(words)
    words += [0x68f0, 4096]
    inner_pc = 2*len(words)
    if workload == "memory-read":
        # Eight normal guest data loads end eight TBs (the address may be
        # MMIO in other guests). This guest reads zero-initialized RAM, not
        # NAND/devices; it exercises fall-through dispatch independently of
        # the taken branch at the end of the inner loop.
        words += [0x88f7, 0x3000] * 8
    words += [0x5061, 0x5201, 0xac02, inner_pc, 0x5241, 0xac02, outer_pc,
              0x68fe, 0xc0de]
    end = 2*len(words)
    words += [0xd0ff]
    return struct.pack(f"<{len(words)}H", *words), end


def run(qemu, output, index, samples, minimal=False, workload="register"):
    name = "host-profile" if samples else f"timed-{index}"
    firmware = output/(name+".prg")
    raw, end = program(65535 if samples else 256, workload)
    firmware.write_bytes(raw)
    journal = RunJournal(output / "runs", case=name)
    emu = None
    result = dict(name=name, passed=False, profile_only=bool(samples),
                  run_directory=str(journal.directory), exit_code=None,
                  control_observers_minimal=minimal, workload=workload)
    try:
        emu = Emulator(qemu=qemu, firmware=firmware, start_paused=True,
                       journal=journal)
        if minimal:
            emu.qmp.execute("qom-set", {"path":"/machine",
                "property":"control-observers-minimal", "value":True})
        start = time.monotonic()
        emu.qmp.execute("cont")
        if samples:
            print(f"sampling only owned QEMU PID={emu.process.pid}", flush=True)
            stacks = []
            for i in range(samples):
                stack = subprocess.check_output(["gdb", "-q", "-nx", "-batch",
                    "-ex", "set pagination off", "-ex", "thread apply all bt 6",
                    "-ex", "detach", "-p", str(emu.process.pid)],
                    stderr=subprocess.STDOUT, timeout=15).decode(errors="replace")
                assert f"(process {emu.process.pid}) detached" in stack, "GDB did not confirm detach"
                assert re.search(r"^Thread \d+ .*\n#0", stack, re.M), "no sampled thread stack"
                stacks.append(stack)
                print(f"host sample {i+1}/{samples}", flush=True)
                time.sleep(.03)
            (output/"host-stacks.txt").write_text("\n".join(stacks))
            result["passed"] = True
        else:
            deadline = start+60
            while time.monotonic() < deadline:
                state = emu.qmp.execute("qom-get", {"path":"/machine", "property":"cpu-state"})
                if f"PC=20:{end:04x}".lower() in state.lower():
                    break
                time.sleep(.05)
            result["seconds"] = time.monotonic()-start
            assert f"PC=20:{end:04x}".lower() in state.lower(), "fixed guest loop timed out"
            assert all(f+"=none" in state for f in ["ROM_MISSING","UNSUPPORTED","INVALID_CONTROL"])
            for reg,value in [(0,0),(4,0),(6,0),(14,0xc0de),(15,0x6000)]:
                m=re.search(rf"\bR{reg}\s*=([0-9a-f]+)",state,re.I)
                assert m and int(m[1],16)==value,(reg, m[1] if m else None)
            if workload == "memory-read":
                assert re.search(r"\bR7\s*=0000\b", state, re.I), "RAM load mismatch"
            (output/(name+".cpu.txt")).write_text(state)
            inner_instructions = 11 if workload == "memory-read" else 3
            result.update(guest_instructions=4+1+256*(1+inner_instructions*4096+2), passed=True)
            result["million_instructions_per_second"] = result["guest_instructions"]/result["seconds"]/1e6
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        if emu is not None:
            emu.close()
            result["exit_code"] = emu.process.returncode
        else:
            # Emulator.__init__ owns cleanup after a failed spawn/connect.
            # Keep its durable log and return a failed case, not a lost report.
            result["exit_code"] = journal.snapshot().get("qemu_returncode")
    result["passed"] &= result["exit_code"] == 0
    print(json.dumps(result), flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--samples",type=int,choices=range(33),default=0)
    p.add_argument("--runs",type=int,choices=range(1,6),default=3)
    p.add_argument("--minimal-control-observers",action="store_true")
    p.add_argument("--workload",choices=("register", "memory-read"),default="register")
    args=p.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    report=dict(qemu_sha256=hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
                nand_used=False,host_guest_memory_writes=0,cases=[])
    for i in range(args.runs):
        report["cases"].append(run(args.qemu,args.output,i,0,args.minimal_control_observers,args.workload))
        if not report["cases"][-1]["passed"]: break
    if args.samples and all(c["passed"] for c in report["cases"]):
        report["cases"].append(run(args.qemu,args.output,0,args.samples,args.minimal_control_observers,args.workload))
    report["passed"]=all(c["passed"] for c in report["cases"])
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    return 0 if report["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
