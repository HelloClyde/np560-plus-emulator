#!/usr/bin/env python3
"""REP must reject forbidden targets before their architectural side effects.

This checks an explicit stop at the unimplemented IREP exception boundary,
NOT an implemented EXR register or exception-vector dispatch. All initial
state is installed by guest instructions; the suite uses no NAND.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from test_np560_mac import run


# CN1916884A PDF p120 lists these instruction classes, independently of
# whether a conditional branch would be taken. IGNDS and ordinary memory
# operations are not in the list and must remain legal REP targets.
TARGETS = {
    "ajmp-untaken": [0xAC01, 0x1000],
    "sjmp": [0xAD20, 0x1000],
    "acall-untaken": [0xBC01, 0x1000],
    "scall": [0xBD20, 0x1000],
    "icall-untaken": [0xCC12],
    "ijmp-untaken": [0xCE12],
    "rcall": [0xCD00],
    "rjmp-untaken": [0xD100],
    "ret": [0xC600],
    "rets": [0xC620],
    "reti": [0xC610],
    "trap": [0x0F37],
    "jb": [0x9AF1, 0x0000],
    "jnb": [0x9BF1, 0x0000],
    "jbc": [0x9CF1, 0x0000],
    "jnbs": [0x9DF1, 0x0000],
    "rep-immediate": [0xBF00, 3],
    "rep-register": [0xCF01],
    "repb-immediate": [0xAE03, 0x1000],
    "repb-register": [0xAF01, 0x1000],
    "crit": [0x3F01],
    "link": [0x2E02],
    "unlink": [0x2F00],
}


def check(qemu, output, name, icount, minimal=False):
    words = [0x6800, 2, 0x6801, 0, 0x68FF, 0x6000, 0x68FB, 0x6100,
             0x68F0, 0x1234, 0x68F1, 1, 0x68F2, 0x2400]
    if name.startswith("cirq-"):
        # Software-visible PSR.CIRQ is the documented processing-mode bit.
        # This is not a host-forced IRQ or a pretend exception handler.
        words += [0x6801, 0x4000]
        target = {"cirq-rep": [0xBF00, 1],
                  "cirq-repb": [0xAE01, 0x1000]}[name]
        reason = "processing-mode"
    else:
        # Include the zero-count form: even a single attempted iteration
        # must reject a forbidden instruction, before LINK/CALL/RET writes.
        words += [0xBF00, 0]
        target = TARGETS[name]
        reason = "target"
    address = len(words) * 2
    words += target + [0x68F0, 0xBEEF]
    case = f"{name}-icount{icount}"
    result = run(qemu, output, case, words,
                 {0: 0x1234, 1: 1, 2: 0x2400, 11: 0x6100, 15: 0x6000},
                 icount=icount, minimal=minimal, fault=f"20:{address:04x} WORD={target[0]:04x}",
                 metadata={"boundary": "IREP dispatch remains unimplemented",
                           "reason": reason, "target_words": target})
    state = (output / f"{case}.cpu.txt").read_text(encoding="utf-8")
    assert f"IREP_DISPATCH=unimplemented REPEAT_REASON={reason}" in state
    assert "TRAPS:0" in state
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=[*TARGETS, "cirq-rep", "cirq-repb"])
    parser.add_argument('--minimal', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "identity.json").write_text(json.dumps({
        "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
        "scope": "illegal REP boundary, not EXR/IREP hardware completion",
    }, indent=2) + "\n", encoding="utf-8")
    cases = [args.case] if args.case else [*TARGETS, "cirq-rep", "cirq-repb"]
    results = [check(args.qemu, args.output, name, icount, args.minimal)
               for name in cases for icount in (None, 5)]
    (args.output / "report.json").write_text(json.dumps({
        "passed": all(r["passed"] for r in results), "results": results,
    }, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
