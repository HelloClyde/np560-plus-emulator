#!/usr/bin/env python3
"""Verify guest-written DAC PCM, mute, virtual time and original ramp code.

The guest configures the registers and real Timer2. Host reads only audio
and CPU state; QMP pause/reset controls do not inject samples or game state.
This verifies the output model, not the still-missing NPE ROM decoder.
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
import json
import re
import struct
import tempfile
import time
import wave
from pathlib import Path

from test_np560_dtu import write_word
from web.np560_web import Emulator


def wait_ticks(words: list[int], count: int) -> None:
    words.extend([0x68F2, count])
    loop = len(words) * 2
    # A masked hardware source still latches RQ; the guest clears each one.
    words.extend([0x9B53, 0x01FE, 0xF153, 0x5221, 0xAC02, loop])


def build_guest(original: Path) -> tuple[bytes, bytes, str]:
    words = [0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 1,
             0x68E9, 0x8020, 0xEE00, 0x682E, 2, 0xFE00, 0x6853, 0,
             0x682C, 19999, 0x682D, 0x8080]
    # Inactive DAC writes latch values but must not become audible PCM.
    words.extend([0x6870, 0x2000, 0x6871, 0xE000])
    wait_ticks(words, 3)
    words.extend([0x6872, 1])
    wait_ticks(words, 3)
    # Banked/direct/unbanked views all reach the same DAC boundary. Swap signs.
    write_word(words, 0xF1E0, 0xE000, banked=True)
    write_word(words, 0xF1E2, 0x2000)
    wait_ticks(words, 3)
    # Power-down while enable remains set is silent; sample words still latch.
    words.extend([0x6872, 0x8001, 0x6870, 0x1111, 0x6871, 0xEEEE])
    wait_ticks(words, 3)
    # Original signed ramp from small positive/negative values to zero.
    words.extend([0x6870, 3, 0x6871, 0xFFFD, 0x6872, 1])
    wait_ticks(words, 2)
    for value in (95, 0, 0):
        words.extend([0x68F0, value, 0x58F0])
    words.extend([0xBD08, 0x33FA, 0x50F6])
    wait_ticks(words, 2)
    words.extend([0xFF2D, 0x6872, 0, 0x68FE, 0x600D])
    final_pc = f"PC=20:{len(words) * 2:04x}"
    words.append(0xD0FF)
    image = struct.pack(f"<{len(words)}H", *words)
    resident = bytearray(b"\x00\x0f" * (0x0840D2 // 2))
    prg = original.read_bytes()
    resident[0x0833FA:0x083462] = prg[0x0533FA:0x053462]
    resident[0x0840D0:] = struct.pack("<H", 0xC610)  # unrelated legacy tick only
    return image, bytes(resident), final_pc


def check(qemu: Path, original: Path, *, icount: int | None,
          output: Path) -> None:
    image, resident, final_pc = build_guest(original)
    with tempfile.TemporaryDirectory(prefix="np560-audio-") as directory:
        root = Path(directory)
        firmware, rom = root / "caller.prg", root / "ramp.bin"
        firmware.write_bytes(image)
        rom.write_bytes(resident)
        emulator = Emulator(qemu=qemu, firmware=firmware, soc_rom=rom,
                            soc_rom_skeleton=True, start_paused=True, icount_shift=icount)
        captured = bytearray()
        cursor = 0
        generation = None
        report = {"passed": False, "icount": icount,
                  "guest_memory_writes_by_host": 0,
                  "original_function": "08:33FA", "wave": str(output)}

        def collect(packet: dict) -> None:
            nonlocal cursor, generation
            if generation is None:
                generation = packet["generation"]
            assert packet["generation"] == generation
            assert packet["first_frame"] <= cursor <= packet["next_frame"], (
                "audio reader overrun or sequence reversal", packet["first_frame"],
                cursor, packet["next_frame"])
            raw = base64.b64decode(packet["pcm"], validate=True)
            assert len(raw) == (packet["next_frame"] - packet["first_frame"]) * 4
            captured.extend(raw[(cursor - packet["first_frame"]) * 4:])
            cursor = packet["next_frame"]

        try:
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 20
            state = ""
            while time.monotonic() < deadline:
                collect(emulator.audio())
                state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
                if final_pc.lower() in state.lower():
                    break
                time.sleep(0.005)
            assert final_pc.lower() in state.lower(), state[:1500]
            for field in ("ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL"):
                assert f"{field}=none" in state, state[:1500]
            assert re.search(r"R14\s*=600d", state, re.I), state[:500]
            emulator.qmp.execute("stop")
            before = emulator.audio()
            # The CPU can finish between the last audio read and the CPU-state
            # query above. Drain its final output before checking sample counts.
            collect(before)
            output.with_suffix(".cpu.txt").write_text(state, encoding="utf-8")
            time.sleep(0.03)
            after = emulator.audio()
            assert before == after, "QMP reads/pause must not advance audio"
            assert after["registers"] == [0, 0, 0], after["registers"]
            assert after["writes"][0] >= 7 and after["writes"][1] >= 7, after["writes"]
            pairs = list(struct.iter_unpack("<hh", captured))
            with wave.open(str(output), "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(48000)
                wav.writeframes(captured)
            report.update(frames=len(pairs), sample_writes=after["writes"],
                          sample_counts={str(pair): pairs.count(pair) for pair in
                                         ((8192, -8192), (-8192, 8192), (3, -3), (0, 0))})
            for pair in ((8192, -8192), (-8192, 8192), (3, -3), (0, 0)):
                assert pairs.count(pair) >= 200, (icount, pair, pairs.count(pair))
            assert (0x1111, -0x1112) not in pairs, "power-down must mute held words"
            # Allow sub-frame skew between the two real register writes, but
            # never reinterpret the unsigned negative sample as a positive one.
            assert not any(a > 8192 or b > 8192 for a, b in pairs), "signedness or mute failure"
            emulator.qmp.execute("system_reset")
            reset = emulator.audio()
            assert reset["generation"] > generation and reset["next_frame"] == 0, reset
            assert reset["registers"] == [0, 0, 0], reset["registers"]
            report["passed"] = True
            print(report, flush=True)
        except Exception as error:
            report["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            emulator.close()
            report["exit_code"] = emulator.process.returncode
            output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def check_active_reset(qemu: Path, output: Path, *,
                       firmware_output: Path | None = None) -> None:
    """Reset while samples and a periodic source are active, not already zero."""
    words = [0x6800, 2, 0x68FF, 0x6000, 0x6870, 0x1234, 0x6871, 0xEDCC,
             0x6872, 1, 0x68E9, 0x8020, 0xEE00, 0x682E, 2, 0xFE00, 0x682C, 19999,
             0x682D, 0x8080]
    final_pc = f"PC=20:{len(words) * 2:04x}"
    words.append(0xD0FF)
    image = struct.pack(f"<{len(words)}H", *words)
    if firmware_output is not None:
        # Optional tiny diagnostic input for the real browser/audio transport.
        # This is not a game ROM or an implementation of a missing codec.
        firmware_output.write_bytes(image)
    with tempfile.TemporaryDirectory(prefix="np560-active-audio-reset-") as directory:
        firmware = Path(directory) / "active.prg"
        firmware.write_bytes(image)
        emulator = Emulator(qemu=qemu, firmware=firmware, start_paused=True)
        try:
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 10
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "cpu-state"})
                if final_pc.lower() in state.lower():
                    break
                time.sleep(0.01)
            assert final_pc.lower() in state.lower(), state[:500]
            emulator.qmp.execute("stop")
            before = emulator.audio()
            assert before["registers"] == [0x1234, 0xEDCC, 1], before["registers"]
            timer_before = emulator.qmp.execute("qom-get", {
                "path": "/machine", "property": "timer2-state"})
            assert "RUNNING:1" in timer_before, timer_before
            emulator.qmp.execute("system_reset")
            after = emulator.audio()
            timer_after = emulator.qmp.execute("qom-get", {
                "path": "/machine", "property": "timer2-state"})
            passed = (after["registers"] == [0, 0, 0] and not after["enabled"]
                      and after["next_frame"] == 0
                      and after["generation"] > before["generation"]
                      and "RUNNING:0" in timer_after and "CONTROL:0000" in timer_after
                      and "HZ:24576000" in timer_after)
            report = {"passed": passed, "before_registers": before["registers"],
                      "after_registers": after["registers"], "timer_before": timer_before,
                      "timer_after": timer_after, "guest_memory_writes_by_host": 0}
            output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(report, flush=True)
            assert passed, "reset left stale device state after CPU registers were cleared"
        finally:
            emulator.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    check(args.qemu, args.original_prg, icount=None, output=args.output_dir / "guest-dac.wav")
    check(args.qemu, args.original_prg, icount=5, output=args.output_dir / "guest-dac-icount.wav")
    check_active_reset(args.qemu, args.output_dir / "active-reset.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
