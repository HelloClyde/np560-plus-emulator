#!/usr/bin/env python3
"""A finite guest-owned DAC buffer must retain the dedicated sample clock.

No NAND, codec, ROM service, debugger or host RAM injection. The guest fills
both channels' source, arms DTU/ICR, starts the PLL-backed DAC, then stops it
after both counters reach zero. Count requests, not just a nonzero last DAC.
This isolates per-request transport from the real player's refill latency.
"""
from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import time
import wave

from test_np560_dtu import write_word
from web.np560_web import Emulator

COUNT = 1023
HZ = 44084


def case(qemu, output, icount, snapshot_load=False, instruction_clock=False):
    name = "adaptive" if icount == "auto" else "instruction" if icount is not None else "normal"
    # IE remains off. DTU still accepts real peripheral requests; no CPU
    # handler, refiller, repeat instruction, file work or competing timer.
    words = [0x6800, 2, 0x68ff, 0x6000, 0x6810, 0, 0x6811, 0]
    for i in range(COUNT):
        write_word(words, 0x3000 + 2*i, round(8000*math.sin(2*math.pi*440*i/44100)) & 65535)
    for addr, value in ((0xf0f0, 0x3000), (0xf0f2, 0xf1e0),
                        (0xf0f4, 0x3000), (0xf0f6, 0xf1e2)):
        write_word(words, addr, value)
    words += [0x6821, 0x8000 | COUNT, 0x6822, 0x8000 | COUNT,
              0x6861, 0x41, 0x6860, 0x51, 0x68ea, 0x89c6, 0x6872, 9]
    for reg in (0x21, 0x22):
        loop = 2*len(words)
        words += [0x1f00 | reg, 0x380f, 0x74f0, 0x3ff, 0x5600, 0xac02, loop]
    words += [0x6861, 0, 0x6860, 0, 0x6872, 0x8009, 0x68fe, 0xc0de]
    end = 0x200000 + 2*len(words)
    words += [0xd0ff]
    firmware = output/f"{name}.prg"
    firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
    emu = Emulator(qemu=qemu, firmware=firmware, start_paused=True, icount_shift=icount)
    parts = []
    result = dict(name=name, icount_shift=icount, passed=False,
                  guest_source_samples=COUNT, expected_request_hz=HZ,
                  readonly_snapshot_load=snapshot_load, snapshot_queries=0)
    try:
        if instruction_clock:
            emu.qmp.execute("qom-set", {"path":"/machine", "property":"instruction-clock", "value":True})
        emu.qmp.execute("cont")
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            if snapshot_load:
                # A read-only main-loop operation can delay timer delivery.
                # There is no PCM refiller or codec in this finite test, so
                # timing changes here cannot be blamed on their throughput.
                emu.qmp.execute("qom-get", {"path":"/machine", "property":"cpu-state"})
                result["snapshot_queries"] += 1
            audio = emu.audio()
            raw = base64.b64decode(audio["pcm"])
            first, last = audio["first_frame"], audio["next_frame"]
            if last > first:
                part = parts[-1] if parts else None
                if part is None or part[0] != audio["generation"] or first > part[2]:
                    part = [audio["generation"], first, first, bytearray()]
                    parts.append(part)
                assert last >= part[2], "audio time moved backwards"
                part[3].extend(raw[(part[2]-first)*4:]); part[2] = last
            if audio["registers"][2] == 0x8009:
                break
            time.sleep(.005)
        assert audio["registers"][2] == 0x8009, "guest did not stop DAC"
        emu.qmp.execute("stop")
        if instruction_clock:
            result["instruction_clock"] = emu.qmp.execute("qom-get", {"path":"/machine", "property":"instruction-clock-state"})
            assert "FAULT:0" in result["instruction_clock"]
        state = emu.qmp.execute("qom-get", {"path":"/machine", "property":"cpu-state"})
        (output/f"{name}.cpu.txt").write_text(state)
        assert all(f+"=none" in state for f in ("UNSUPPORTED", "ROM_MISSING", "INVALID_CONTROL"))
        assert f"PC=20:{end & 65535:04x}".lower() in state.lower()
        dtu = emu.qmp.execute("qom-get", {"path":"/machine", "property":"dtu-state"})
        assert "FAULT_SOURCES:00000000" in dtu
        result.update(request_clock=audio["request_clock"], dtu=dtu)
        for ch in range(2):
            m = re.search(rf"CH{ch}:8000/(\d+)/(\d+)", dtu)
            assert m and (int(m[1]), int(m[2])) == (COUNT, 1), dtu
        # The exact stop instruction follows a few polls after completion.
        # Allow eight sample periods for that guest control latency. A
        # persistent 30% loss cannot be called correct clock delivery.
        ticks = audio["request_clock"]["ticks"]
        if "request_delivery" in audio:
            delivery=audio["request_delivery"]
            result["request_delivery"]=delivery
            assert delivery==dict(writes=[COUNT,COUNT],
                without_write=[ticks-COUNT,ticks-COUNT],multiple_writes=[0,0],
                writes_outside_request=[0,0]),delivery
        result.update(requests_per_sample=ticks/COUNT,
                      excess_requests=ticks-COUNT,
                      clock_delivery_passed=COUNT <= ticks <= COUNT+8,
                      passed=COUNT <= ticks <= COUNT+8)
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        emu.close(); result["exit_code"] = emu.process.returncode
        result["audio_parts"] = []
        for i, (generation, first, last, pcm) in enumerate(parts):
            path = output/f"{name}-{i}.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setparams((2, 2, 48000, 0, "NONE", "not compressed")); wav.writeframes(pcm)
            result["audio_parts"].append(dict(path=str(path), generation=generation,
                first_frame=first, next_frame=last, pcm_sha256=hashlib.sha256(pcm).hexdigest()))
        # Check the actual DAC presentation, not an offline decoded source.
        # The same source feeds both DTUs, so skew between channels is a
        # device timestamp error. Ten tone cycles suffice to reject the
        # previous ~270 Hz output without relying on an FFT bin width.
        frames = [sample for part in parts for sample in struct.iter_unpack("<hh", part[3])]
        crossings = [i for i in range(1, len(frames))
                     if frames[i-1][0] < 0 <= frames[i][0]]
        frequency = (48000 * (len(crossings)-1) / (crossings[-1]-crossings[0])
                     if len(crossings) > 1 else 0)
        skew = sum(a != b for a, b in frames)
        expected_frequency = 440*HZ/44100
        waveform_passed = (len(parts) == 1 and len(crossings) >= 9
                           and abs(frequency-expected_frequency) <= 1.5 and skew == 0)
        result.update(measured_hz=frequency, positive_crossings=len(crossings),
                      expected_hz=expected_frequency, frequency_tolerance_hz=1.5,
                      stereo_mismatched_frames=skew, waveform_passed=waveform_passed)
        result["passed"] &= waveform_passed
    result["passed"] &= result["exit_code"] == 0
    print(json.dumps({k:v for k,v in result.items() if k != "audio_parts"}), flush=True)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--snapshot-load", action="store_true",
                   help="issue read-only CPU snapshots while the prefilled DAC is running")
    p.add_argument("--only-icount-auto", action="store_true",
                   help="test QEMU adaptive instruction scheduling only; not a physical CPU clock model")
    p.add_argument("--instruction-clock", action="store_true",
                   help="test only PLL/CLKCON partial cycle model at icount shift=0")
    args = p.parse_args()
    if args.instruction_clock and args.only_icount_auto:
        p.error("instruction-clock cannot use auto")
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(qemu_sha256=hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
                  host_guest_memory_writes=0, nand_used=False, codec_used=False, cases=[])
    for icount in ((0,) if args.instruction_clock else ("auto",) if args.only_icount_auto else (None, 5)):
        report["cases"].append(case(args.qemu, args.output, icount,args.snapshot_load,args.instruction_clock))
    report["passed"] = all(c["passed"] for c in report["cases"])
    (args.output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
