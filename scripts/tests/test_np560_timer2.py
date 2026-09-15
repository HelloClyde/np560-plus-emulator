#!/usr/bin/env python3
"""Check real Timer2 expiry, PLL register coherence and virtual-clock pause.

Guest code configures the device. No host writes to guest state or countdowns.
These are checks of the implemented periodic mode, not a full clock-tree,
capture-mode, Timer0/1, DTU or audio verification.
"""
from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import re
import struct
import tempfile
import time
from pathlib import Path

from test_np560_bit_sfr_addressing import run, run_original_waiter
from web.np560_web import Emulator


def get_timer(emulator: Emulator, index: int = 2) -> tuple[str, dict[str, int]]:
    text = emulator.qmp.execute("qom-get", {
        "path": "/machine", "property": f"timer{index}-state"})
    fields = {key: int(value, 16 if key in {"COUNT", "PRELOAD", "CONTROL", "ICR"} else 10)
              for key, value in re.findall(r"([A-Z_]+):([0-9a-f]+)", text)}
    return text, fields


def check_timer(qemu: Path, *, index: int = 2, icount: int | None = None,
                pause: bool = False) -> None:
    # PLL ratio 2:1 gives 8 MHz; CLKCON /4 gives 2 MHz. P=999 => 0.5 ms.
    # Both global IE and source EN are disabled: hardware still sets RQ.
    assert 0 <= index <= 2
    icr, control, preload = 0x51 + index, 0x27 + index * 3, 0x26 + index * 3
    words = [0x6800, 2, 0x68E9, 0x8020, 0xEE00, 0x682E, 2, 0xFE00,
             0x6800 | icr, 0, 0x6800 | preload, 999, 0x6800 | control, 0x8080]
    if not pause:
        words += [0x9B00 | icr, 0x01FE,  # wait until hardware RQ becomes 1
                  0xFF00 | control,     # stop through the direct bit view
                  0x1F00 | icr, 0x384F]
    final_pc = f"PC=20:{len(words) * 2:04x}"
    words += [0xD0FF]
    with tempfile.TemporaryDirectory(prefix="np560-timer2-") as directory:
        firmware = Path(directory) / "timer.prg"
        firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
        emulator = Emulator(qemu=qemu, firmware=firmware, start_paused=True,
                            icount_shift=icount)
        try:
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
                if final_pc.lower() in state.lower():
                    break
                time.sleep(0.01)
            assert final_pc.lower() in state.lower(), state[:1600]
            text, fields = get_timer(emulator, index)
            assert fields["HZ"] == 2000000, text
            assert fields["UNSUPPORTED_CONFIGS"] == 0, text
            for field in ("UNSUPPORTED", "ROM_MISSING", "INVALID_CONTROL"):
                assert f"{field}=none" in state, state[:1600]
            if pause:
                emulator.qmp.execute("stop")
                before_text, before = get_timer(emulator, index)
                time.sleep(0.05)
                after_text, after = get_timer(emulator, index)
                assert before == after, (before_text, after_text)
                emulator.qmp.execute("cont")
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    text, fields = get_timer(emulator, index)
                    if fields["EXPIRED"] > before["EXPIRED"]:
                        break
                    time.sleep(0.01)
                assert fields["EXPIRED"] > before["EXPIRED"], text
            else:
                assert fields["EXPIRED"] >= 1 and fields["ICR"] == 2, text
                assert fields["RUNNING"] == 0 and fields["CONTROL"] == 0x80, text
                assert re.search(r"\bR4\s*=0002\b", state, re.I), state[:1500]
                time.sleep(0.03)
                _, stopped = get_timer(emulator, index)
                assert stopped["EXPIRED"] == fields["EXPIRED"], (fields, stopped)
            print(f"Timer{index} icount={icount}, pause={pause}: {text}", flush=True)
        finally:
            emulator.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path, required=True)
    args = parser.parse_args()
    run(args.qemu, "PLL direct / IGNDS / banked views", [
        0x68E9, 0x8020, 0x3F10, 0x88F4, 0xF2D2,
        0x6811, 1, 0x88F5, 0xF2D2,
        0x68F0, 0x8061, 0xA8F0, 0xF2D2, 0x3F10, 0x88F6, 0xF2D2,
        0x69F1, 0x0080, 0x3F10, 0xA9F1, 0xF2D2,
        0x69F1, 0x0020, 0x3F10, 0xA9F1, 0xF2D3,
        0x3F10, 0x88F7, 0xF2D2,
    ], {4: 0x8020, 5: 0x8020, 6: 0x8061, 7: 0x8020})
    check_timer(args.qemu)
    check_timer(args.qemu, icount=5)
    check_timer(args.qemu, pause=True)
    run_original_waiter(args.qemu, args.original_prg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
