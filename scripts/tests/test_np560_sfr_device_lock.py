#!/usr/bin/env python3
"""Check BQL ownership at actual timer/DAC register callbacks using GDB.

Only an isolated diagnostic guest is run. Breakpoints observe thread-local
lock state; no guest memory/register writes or user-running QEMU attachment.
Requires a debug-symbol build and GDB. Complements functional timer tests:
a race need not happen on every run to make unlocked device access invalid.
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
import os
from pathlib import Path
import re
import signal
import struct
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--icr", action="store_true",
                   help="also require locked interrupt/DTU controls and ICR ALU/bit/alias access")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    # Direct timer + DAC writes, direct counter read; then their data-bus
    # aliases. The aliases already acquire BQL in QEMU's MMIO dispatch.
    words = [0x6800, 2, 0x68FF, 0x6000,
             0x682D, 0x80, 0x6870, 0x1234, 0x1F2B, 0x384F,
             0x68F0, 0x80, 0x3F10, 0xA8F0, 0xF15A,
             0x68F0, 0x5678, 0x3F10, 0xA8F0, 0xF1E0,
             0x3F10, 0x88F4, 0xF156]
    if args.icr:
        words += [0x6861, 0x43, 0x7461, 0xfffe, 0x7561, 1,
                  0xf061, 0xe061, 0x6461, 0xfe, 0x6561, 1,
                  0x68f0, 0x41, 0x3f10, 0xa8f0, 0xf1c2,
                  0x3f10, 0x88f4, 0xf1c2,
                  0x68f0, 0xfffe, 0x3f10, 0xb4f0, 0xf1c2,
                  0x3f10, 0x9461, 0xf1c2, 0x6821, 0x8000]
    words += [0x6872, 0, 0xD0FF]
    guest = args.output / "caller.prg"
    guest.write_bytes(struct.pack(f"<{len(words)}H", *words))
    script = args.output / "observe.gdb"
    body = """commands
silent
printf "DEVICE_KIND reg=%02x locked=%d\\n", reg, co_tls_iothread_locked
set $hits = $hits + 1
if $hits == 1
bt 9
end
if STOP_CONDITION
quit
end
continue
end
"""
    script.write_text("set pagination off\nset confirm off\nset $hits = 0\n" +
                     "break np560_sfr_device_write\n" +
                     body.replace("KIND", "WRITE").replace("STOP_CONDITION", "reg == 0x72") +
                     "break np560_sfr_device_read\n" +
                     body.replace("KIND", "READ").replace("STOP_CONDITION", "$hits > 1000") + "run\n",
                     encoding="utf-8")
    command = ["gdb", "--batch", "-x", str(script), "--args", str(args.qemu),
               "-M", "np560,boot-mode=firmware,rom-hle=off,hle-ui=off",
               "-bios", str(guest), "-nographic", "-monitor", "none"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    timed_out = False
    try:
        raw, _ = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        timed_out = True
        # Only the process group created above (GDB + its isolated inferior).
        os.killpg(process.pid, signal.SIGKILL)
        raw, _ = process.communicate()
    output = raw.decode("utf-8", errors="replace")
    (args.output / "gdb.log").write_text(output, encoding="utf-8")
    rows = [(kind, int(r, 16), int(v)) for kind, r, v in re.findall(
        r"DEVICE_(READ|WRITE) reg=([0-9a-f]+) locked=([01])", output)]
    # Writes perform a read of the previous SFR value before device update.
    expected = [("READ", 0x2D), ("WRITE", 0x2D),
                ("READ", 0x70), ("WRITE", 0x70), ("READ", 0x2B)]
    observed = [(kind, r) for kind, r, _ in rows]
    icr_complete = (not args.icr or
        (sum(kind == "WRITE" and r == 0x61 for kind, r in observed) == 10 and
         ("WRITE", 0x21) in observed and ("READ", 0x61) in observed))
    report = {"passed": not timed_out and process.returncode == 0 and
              observed[:5] == expected and
              set(expected) <= set(observed[5:]) and
              observed[-1:] == [("WRITE", 0x72)] and all(v for _, _, v in rows) and icr_complete,
              "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
              "returncode": process.returncode, "timed_out": timed_out, "observations": rows,
              "command": command, "host_guest_memory_writes": 0,
              "icr_requested": args.icr, "icr_complete": icr_complete}
    (args.output / "report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
