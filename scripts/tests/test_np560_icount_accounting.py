#!/usr/bin/env python3
"""Count executed guest instructions, including dynamic early TB exits.

This tests QEMU instruction accounting, NOT DMCU cycles or real-time speed.
All setup is guest code; no NAND, host RAM writes or enabled interrupts.
The terminal unsupported instruction is an intentional, checked halt. It
occupies a page's last word so its own TB cannot count a speculative tail.
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

from web.np560_web import Emulator, RunJournal


def fixture(kind, tail):
    words = [0x6800, 2, 0x68ff, 0x6000, 0x68fb, 0]
    count = 3
    expected_r6 = 1
    if kind == "straight":
        words += [0x5061]
        count += 1
    elif kind == "repeat":
        words += [0xbf00, 31, 0x5061]
        count += 1 + 32
        expected_r6 = 32
    elif kind == "repeat-block":
        # REPB's end is exclusive; repeat two register-only instructions.
        end = len(words) * 2 + 8
        words += [0xae1f, end, 0x5061, 0x5081]
        count += 1 + 64
        expected_r6 = 32
    elif kind in ("crit", "ignds"):
        words += [0x3f00 if kind == "crit" else 0x3f10, 0x5061]
        count += 2
    elif kind == "ds":
        words += [0x6810, 0x44, 0x5061]
        count += 2
    else:
        raise ValueError(kind)
    # ADD stays within a multi-instruction TB. The current conservative
    # translator treats C700/NOP as an I/O boundary, hiding long tails.
    words += [0x5071] * tail + [0xad20, 0xfffe]
    count += tail + 1 + 1  # tail, SJMP, attempted terminal instruction
    raw = bytearray(struct.pack("<32768H", *([0xd0ff] * 32768)))
    struct.pack_into(f"<{len(words)}H", raw, 0, *words)
    struct.pack_into("<H", raw, 0xfffe, 0xc701)
    return raw, count, expected_r6


def check(qemu, output, kind, tail, shift, minimal=False):
    name = f"{kind}-tail{tail}-shift{shift}"
    firmware = output / (name + ".prg")
    raw, expected, expected_r6 = fixture(kind, tail)
    firmware.write_bytes(raw)
    journal = RunJournal(output / "runs", case=name)
    result = dict(name=name, expected_icount=expected, passed=False,
                  run_directory=str(journal.directory))
    emu = None
    try:
        emu = Emulator(qemu=qemu, firmware=firmware, start_paused=True,
                       icount_shift=shift, journal=journal)
        if minimal:
            emu.qmp.execute('qom-set', {'path':'/machine', 'property':'control-observers-minimal', 'value':True})
        before = emu.qmp.execute("query-replay")["icount"]
        emu.qmp.execute("cont")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = emu.qmp.execute("qom-get", {
                "path": "/machine", "property": "cpu-state"})
            if "UNSUPPORTED=20:fffe WORD=c701 COUNT=1" in state:
                break
            time.sleep(.01)
        emu.qmp.execute("stop")
        state = emu.qmp.execute("qom-get", {
            "path": "/machine", "property": "cpu-state"})
        (output / (name + ".cpu.txt")).write_text(state)
        actual = emu.qmp.execute("query-replay")["icount"] - before
        result.update(actual_icount=actual, excess_instructions=actual-expected)
        assert "UNSUPPORTED=20:fffe WORD=c701 COUNT=1" in state, state[:1600]
        assert "ROM_MISSING=none" in state and "INVALID_CONTROL=none" in state
        header = "\n".join(state.splitlines()[:5])
        m = re.search(r"\bR6\s*=([0-9a-f]+)", header, re.I)
        assert m and int(m[1], 16) == expected_r6, header
        m = re.search(r"\bR7\s*=([0-9a-f]+)", header, re.I)
        assert m and int(m[1], 16) == tail, header
        assert actual == expected, f"executed {expected}, accounted {actual}"
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
    p.add_argument("--shift", type=int, choices=range(11), default=5)
    p.add_argument('--minimal', action='store_true')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    cases = [check(args.qemu, args.output, kind, tail, args.shift, args.minimal)
             for kind in ("straight", "repeat", "repeat-block", "crit", "ignds", "ds")
             for tail in (0, 12)]
    assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
    report = dict(qemu_sha256=identity, minimal=args.minimal, nand_used=False, host_guest_memory_writes=0,
                  scope="instruction accounting; not hardware cycle accuracy",
                  cases=cases, passed=all(c["passed"] for c in cases))
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
