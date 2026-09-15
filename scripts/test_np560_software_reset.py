#!/usr/bin/env python3
"""Run original USB-loader RESET tail; preserve RAM across a guest SoC reset.

CN1916884A p115. All memory preparation is guest code; the host presses a
physical matrix key to leave the observation loop. No production NAND is
loaded or saved. This is not a complete USB upgrade/reboot verification.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import struct
import time
from pathlib import Path

from test_np560_dtu import write_word
from web.np560_web import Emulator


def build(loader: Path) -> tuple[bytes, dict]:
    original = loader.read_bytes()
    tail = original[0x4E8:0x4F0]
    assert tail == bytes.fromhex("4800a8f0f2263fff"), tail.hex()
    tail_words = struct.unpack(">4H", tail)
    # First boot runs setup. Software reboot must retain marker=1 and take
    # the other arm, including code patched by the guest before RESET.
    words = [0x88F0, 0x2400, 0x5201, 0xAC01, 0x0600,
             0x6800, 2, 0x68FF, 0x4000, 0x6810, 0]
    write_word(words, 0x2400, 1)
    write_word(words, 0x2404, 0xA55A)
    words += [0x68FC, 0x8500, 0x68F0, 0xB66B, 0x0AC0]
    words += [0x6810, 0xA4]
    write_word(words, 0x2340, 0xC77C, banked=True)
    words += [0x6810, 6]
    write_word(words, 0x0602, 0xCAFE, banked=True)
    # A visible GRAM sample belongs to the external ST7529, not CPU RAM.
    words += [0x6811, 0x1E0]
    for command in (0x94, 0xAF, 0x5C):
        words += [0x68F0, command, 0xA9F1, 0x8000]
    words += [0x68F0, 0xF8, 0xA9F1, 0x8002]
    # Reset defaults to 2B3P: the second bus byte commits the pixel group.
    words += [0x68F0, 0, 0xA9F1, 0x8002]
    words += [0x6810, 0, 0x6811, 1]
    write_word(words, 0xF164, 0)
    # Active on-chip timer/timebase and DAC must not survive the reset.
    words += [0x682C, 0xFFFF, 0x682D, 0x8080, 0x682F, 0x8009,
              0x6870, 0x1234, 0x6871, 0xEDCC, 0x6872, 1,
              0x68F1, 0x1111, 0x68F2, 0x2222, 0x68F3, 0x3333,
              0x68F4, 0x4444, 0x68F5, 0x5555, 0x68F6, 0x6666,
              0x68F7, 0x7777, 0x4C71, 0xAD03, 0x0300]
    assert len(words) * 2 < 0x100
    image = bytearray(0x700)
    struct.pack_into(f"<{len(words)}H", image, 0, *words)
    struct.pack_into("<H", image, 0x100, 0xD0FF)
    # Wait for physical Up (any active column suffices). No guest-state poke.
    wait = [0x3F10, 0x88F0, 0xF160, 0x74F0, 0xFF,
            0x76F0, 0xFF, 0xAC01, 0x0300,
            0x6810, 0xA0, 0x6811, 0xA1, 0x3F03, 0x3F13]
    reset_pc = 0x030300 + len(wait) * 2 + len(tail) - 2
    # Poison fall-through proves RESET does not merely request and continue.
    wait += list(tail_words)
    write_word(wait, 0x2406, 0xDEAD)
    wait += [0xD0FF]
    struct.pack_into(f"<{len(wait)}H", image, 0x300, *wait)
    struct.pack_into("<4H", image, 0x600, 0x68F9, 0xDEAD, 0xAD03, 0x0100)
    return bytes(image), {"loader_sha256": hashlib.sha256(original).hexdigest(),
                         "original_file_range": "0x4e8..0x4f0",
                         "original_tail_hex": tail.hex(), "reset_pc": reset_pc}


def get(emulator, prop):
    return emulator.qmp.execute("qom-get", {"path": "/machine", "property": prop})


def wait_pc(emulator, predicate):
    deadline = time.monotonic() + 10
    while True:
        state = get(emulator, "cpu-state")
        assert all(f"{field}=none" in state for field in
                   ("ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL")), state[:1300]
        if predicate(state):
            return state
        assert emulator.process.poll() is None, emulator.process.returncode
        assert time.monotonic() < deadline, state[:1300]
        time.sleep(.01)


def check(qemu, loader, output, icount):
    folder = output / f"reset-icount{icount}"
    folder.mkdir()
    payload, provenance = build(loader)
    firmware = folder / "caller.prg"
    firmware.write_bytes(payload)
    result = {"passed": False, "provenance": provenance, "icount": icount,
              "host_guest_memory_writes": 0, "production_nand_used": False}
    emulator = Emulator(qemu=qemu, firmware=firmware,
                        boot_mode="firmware-vma03", start_paused=True,
                        icount_shift=icount)
    result["owned_pid"] = emulator.process.pid
    print(f"RESET icount={icount}, owned PID={emulator.process.pid}", flush=True)
    try:
        emulator.qmp.execute("cont")
        before = wait_pc(emulator, lambda s: re.match(r"PC=03:03[0-1][0-9a-f]", s))
        emulator.qmp.execute("stop")
        result["timer_before"] = get(emulator, "timer2-state")
        result["audio_before"] = emulator.audio()["registers"]
        lcd_before = get(emulator, "lcd-state")
        result["lcd_before"] = lcd_before
        gram_before = get(emulator, "lcd-gram-frame")
        assert "RUNNING:1" in result["timer_before"]
        assert result["audio_before"] == [0x1234, 0xEDCC, 1]
        assert any(base64.b64decode(gram_before)), "GRAM sample not written"
        # Hold physical M61 across reset; it must not become a fake release.
        emulator.qmp.execute("qom-set", {"path": "/machine",
                             "property": "key-matrix-high", "value": 1 << 29})
        emulator.qmp.execute("cont")
        after = wait_pc(emulator, lambda s: s.startswith("PC=03:0100"))
        emulator.qmp.execute("stop")
        (folder / "before.cpu.txt").write_text(before, encoding="utf-8")
        (folder / "after.cpu.txt").write_text(after, encoding="utf-8")
        regs = {int(k): int(v, 16) for k, v in re.findall(
            r"\bR(\d+)\s*=([0-9a-f]{4})\b", "\n".join(after.splitlines()[:5]), re.I)}
        expected = dict.fromkeys(range(1, 15), 0)
        expected.update({9: 0xCAFE, 15: 0xFFFE})
        assert all(regs[k] == v for k, v in expected.items()), regs
        assert "DS0=000 DS1=001" in after.splitlines()[0], after[:200]
        register_dump = emulator.qmp.execute("human-monitor-command", {"command-line": "info registers"})
        assert "SB=0000" in register_dump, register_dump
        expected_words = {0x2400: 1, 0x2404: 0xA55A, 0x2406: 0,
                          0x8500: 0xB66B, 0x522340: 0xC77C, 0x030602: 0xCAFE}
        result["memory"] = {}
        for address, expected_word in expected_words.items():
            data = base64.b64decode(emulator.snapshot("data", address, 2)["frame"])
            actual = int.from_bytes(data, "little")
            result["memory"][f"{address:06x}"] = actual
            assert actual == expected_word, (hex(address), hex(actual), hex(expected_word))
        result["timer_after"] = get(emulator, "timer2-state")
        result["timebase_after"] = get(emulator, "timebase-state")
        result["audio_after"] = emulator.audio()["registers"]
        assert "RUNNING:0" in result["timer_after"]
        assert "CONTROL:0000" in result["timer_after"]
        assert "RUNNING:0" in result["timebase_after"]
        assert result["audio_after"] == [0, 0, 0]
        assert get(emulator, "key-matrix-high") == 1 << 29
        assert get(emulator, "lcd-state") == lcd_before
        assert get(emulator, "lcd-gram-frame") == gram_before
        # The existing explicit Web/QMP cold restart remains a separate
        # operation: restore boot images and release frontend input.
        emulator.qmp.execute("system_reset")
        cold = get(emulator, "cpu-state")
        assert cold.startswith("PC=03:0000"), cold[:300]
        cold_words = {0x2400: 0, 0x522340: 0, 0x030602: 0xDEAD}
        result["cold_restart_memory"] = {}
        for address, expected_word in cold_words.items():
            data = base64.b64decode(emulator.snapshot("data", address, 2)["frame"])
            actual = int.from_bytes(data, "little")
            result["cold_restart_memory"][f"{address:06x}"] = actual
            assert actual == expected_word, (hex(address), hex(actual), hex(expected_word))
        assert get(emulator, "key-matrix-high") == 0
        assert "DISPLAY=off SLEEP=on" in get(emulator, "lcd-state")
        result["passed"] = True
    finally:
        if not result["passed"] and emulator.process.poll() is None:
            (folder / "failure.cpu.txt").write_text(get(emulator, "cpu-state"), encoding="utf-8")
        emulator.close()
        result["exit_code"] = emulator.process.returncode
        (folder / "qemu.log").write_bytes(emulator.log_path.read_bytes())
        (folder / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--loader", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--normal-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    identity = hashlib.sha256(args.qemu.read_bytes()).hexdigest()
    report = {"passed": False, "qemu_sha256": identity, "cases": []}
    try:
        for icount in ([None] if args.normal_only else [None, 5]):
            report["cases"].append(check(args.qemu, args.loader, args.output, icount))
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity
        report["passed"] = True
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Original loader RESET tail and warm-reset state checks passed")


if __name__ == "__main__":
    main()
