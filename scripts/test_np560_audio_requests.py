#!/usr/bin/env python3
"""Original dedicated DAC request routes, separate from timer-driven audio.

Uses the rate/PLL pairs in original 32:BD96 and unmodified 24:97AC..9BE6.
No codec, NAND, host RAM writes or replacement firmware callbacks.
"""
import argparse
import hashlib
import json
import struct
import tempfile
import time
from pathlib import Path

from test_np560_dtu import execute, read_word
from test_np560_timers import check_original_transport
from web.np560_web import Emulator


def check_clock(qemu, pll, control, enabled):
    words = [0x6800, 2, 0x68ea, pll, 0x6872, control, 0xd0ff]
    with tempfile.TemporaryDirectory(prefix="np560-audio-clock-") as directory:
        firmware = Path(directory) / "clock.prg"
        firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
        emu = Emulator(qemu=qemu, firmware=firmware, start_paused=True)
        try:
            emu.qmp.execute("cont")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = emu.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
                if "pc=20:000c" in state.lower():
                    break
                time.sleep(.01)
            assert "pc=20:000c" in state.lower(), state[:1000]
            time.sleep(.03)
            emu.qmp.execute("stop")
            before = emu.audio()["request_clock"]
            assert before["running"] == enabled, before
            assert (before["ticks"] > 0) == enabled, before
            if enabled:
                assert before["hz"] == 44084, before
            time.sleep(.03)
            assert emu.audio()["request_clock"] == before, "paused virtual clock advanced"
            emu.qmp.execute("cont")
            time.sleep(.03)
            emu.qmp.execute("stop")
            resumed = emu.audio()["request_clock"]
            assert (resumed["ticks"] > before["ticks"]) == enabled, (before, resumed)
            emu.qmp.execute("system_reset")
            reset = emu.audio()["request_clock"]
            assert reset == {"running": False, "hz": 0, "pll": 0, "ticks": 0}, reset
            return {"name": "clock lifecycle", "pll": pll, "control": control,
                    "before": before, "resumed": resumed, "reset": reset}
        finally:
            emu.close()
            assert emu.process.returncode == 0, emu.process.returncode


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--original-prg", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--first-only", action="store_true")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"passed": False, "cases": [], "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
              "prg_sha256": hashlib.sha256(args.original_prg.read_bytes()).hexdigest(),
              "full_player_test": False, "host_guest_memory_writes": 0}
    try:
        raw = args.original_prg.read_bytes()
        for selector in (6, 3, 5, 8, 9):
            off = 0x32bd96 - 0x30000 + (selector - 1) * 8
            rate, mode, _, pll = [int.from_bytes(raw[n:n+2], "little") for n in range(off, off+8, 2)]
            assert mode & 0x3c0 == 0x3c0
            for icount in (None, 5):
                result = check_original_transport(args.qemu, args.original_prg, 3, 3,
                    icount=icount, audio_pll=0x8000 | pll, audio_div1536=bool(mode & 2))
                report["cases"].append({"selector": selector, "nominal_hz": rate,
                    "pll": 0x8000 | pll, "icount": icount, **result})
                if args.first_only:
                    report["passed"] = True
                    return 0
        # Direct and memory PLL views must share one register. Word byte lanes
        # follow the guest high-byte-first data bus, including a nonzero DS.
        for icount in (None, 5):
            words = [0x6800, 2, 0x68ff, 0x6000, 0x6810, 1, 0x68ea, 0x89c6]
            read_word(words, 0xf2d4, 2)
            read_word(words, 0x72d4, 3, banked=True)
            words.extend([0x69f1, 0xce, 0x3f10, 0xa9f1, 0xf2d5])
            read_word(words, 0xf2d4, 4)
            words.extend([0x69f1, 0x8f, 0xa9f1, 0x72d4])
            read_word(words, 0xf2d4, 5)
            result = execute(args.qemu, f"audio PLL aliases icount={icount}", words,
                             {2: 0x89c6, 3: 0x89c6, 4: 0x89ce, 5: 0x8fce, 15: 0x6000}, icount=icount)
            report["cases"].append({"name": "audio PLL aliases", "icount": icount, **result})
        for pll, control, enabled in ((0x89c6, 9, True), (0x09c6, 9, False),
                                       (0x89c6, 0x8009, False), (0x89c6, 5, False)):
            report["cases"].append(check_clock(args.qemu, pll, control, enabled))
        report["passed"] = True
    except AssertionError as error:
        report["failure"] = str(error)
        print(report["failure"], flush=True)
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
