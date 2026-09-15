#!/usr/bin/env python3
"""Verify Web/QOM keys traverse the legacy MMIO latch into guest code."""

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import re
import time
from pathlib import Path

from web.np560_web import Emulator


def number(state: str, name: str) -> int:
    match = re.search(rf"\b{name}=([0-9A-Fa-f]+)", state)
    return int(match.group(1), 16) if match else -1


def in_poll_loop(state: str) -> bool:
    match = re.search(r"\bPC=03:([0-9a-fA-F]{4})", state)
    return bool(match and 0x0080 <= int(match.group(1), 16) <= 0x008E)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--soc-rom", type=Path, required=True)
    parser.add_argument(
        "--nand-image", type=Path,
        help="optional raw NAND image recovered from NP560+.upd",
    )
    args = parser.parse_args()

    emulator = Emulator(
        qemu=args.qemu,
        firmware=args.firmware,
        soc_rom=args.soc_rom,
        nand_image=args.nand_image,
        soc_rom_skeleton=True,
    )
    try:
        def state() -> str:
            return emulator.qmp.execute(
                "qom-get", {"path": "/machine", "property": "cpu-state"}
            )

        # The native 20:0030 startup callback clears several hundred KiB
        # through scalar DMCU code before polling starts.
        deadline = time.monotonic() + 10
        while not in_poll_loop(state()):
            if time.monotonic() >= deadline:
                raise AssertionError(f"guest did not reach key poll loop:\n{state()}")
            time.sleep(0.01)

        # The resident loader must have copied the compiler helper template
        # from PRG/NOR 4F:F786 into the shared executable-RAM overlay at
        # 32:F786 using guest DMCU instructions.
        emulator.qmp.execute(
            "pmemsave",
            {"val": 0x32F786, "size": 0x3C,
             "filename": str(emulator.frame_path)},
        )
        installed_copy_helper = emulator.frame_path.read_bytes()
        firmware_bytes = args.firmware.read_bytes()
        source_offset = 0x4FF786 - 0x200000
        expected_copy_helper = firmware_bytes[source_offset:source_offset + 0x3C]
        if installed_copy_helper != expected_copy_helper:
            raise AssertionError(
                "resident loader did not install the 32:F786 copy-helper overlay"
            )

        # Web ArrowDown is raw make code 0x101. The reconstructed controller
        # exposes application event 0x0083 and consumes the make latch.
        emulator.set_key(1 << 1, 0x101)
        deadline = time.monotonic() + 5
        while True:
            current = state()
            if (number(current, "KEYBOARD_EVENTS") >= 1 and
                    number(current, "LAST") == 0x83 and
                    "KEY_CODE=00000000" in current):
                break
            if time.monotonic() >= deadline:
                raise AssertionError(f"keyboard event was not consumed:\n{current}")
            time.sleep(0.01)

        # The handler exercises reconstructed overlays and may spend many
        # seconds in native LCD rendering after the latch is consumed.  The
        # durable hardware observation is the consumed make code above; the
        # strict system regression separately covers the physical matrix path.
        # Release the physical key and require execution to remain valid
        # rather than demanding a return to the obsolete 03:0080 loop.
        emulator.set_key(0, 0)
        time.sleep(0.1)
        current = state()
        if ("KEY_STATE=00000000" not in current or
                "KEY_CODE=00000000" not in current or
                "ROM_MISSING=none" not in current or
                "UNSUPPORTED=none" not in current):
            raise AssertionError(
                "guest became invalid after consuming the key:\n" + current
            )

        print("NP560+ legacy keyboard MMIO/guest-consumption integration passed")
        print(current)
    finally:
        emulator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
