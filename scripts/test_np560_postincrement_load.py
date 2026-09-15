#!/usr/bin/env python3
"""MOV destination / source-pointer aliases: operand fetch precedes writeback.

Original 08:2FF4 uses MOV R7,[R7++] to load the final audio-table word.
This is a CPU check, not an audio-address special case.
"""
import argparse
import hashlib
import json
from pathlib import Path

from test_np560_dtu import write_word
from test_np560_mac import run


def cases():
    setup = [0x6800, 2, 0x68ff, 0x6000, 0x6810, 0, 0x6811, 0]
    for pointer in (3, 7, 11, 15):
        words = setup.copy()
        write_word(words, 0x3000, 0x09c6)
        words += [0x68f0 | pointer, 0x3000, 0x3800 | pointer << 4 | pointer]
        yield f"word-r{pointer}-self", words, {pointer: 0x09c6}
    words = setup.copy()
    write_word(words, 0x3000, 0x09c6)
    words += [0x68f7, 0x3000, 0x3867]
    yield "word-distinct", words, {6: 0x09c6, 7: 0x3002}
    # Destination is an RB byte alias, not a word-register number. Preserve
    # the other byte of the incremented pointer, including a carry boundary.
    for address, byte_register, expected in ((0x3000, 6, 0xab01), (0x30ff, 7, 0x315a)):
        words = setup.copy()
        write_word(words, address & ~1, 0xab5a)
        words += [0x68f3, address, 0x3900 | byte_register << 4 | 3]
        yield f"byte-rb{byte_register}-self", words, {3: expected}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"passed": False, "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(), "cases": []}
    try:
        for name, words, expected in cases():
            for icount in (None, 5):
                report["cases"].append(run(args.qemu, args.output, f"{name}-icount{icount}",
                                            words, expected, icount=icount))
        report["passed"] = True
    except AssertionError as error:
        report["failure"] = str(error)
        print(report["failure"], flush=True)
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
