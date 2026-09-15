#!/usr/bin/env python3
"""Read exact NP560 QEMU code-bus words or internal SRAM through GDB.

The Web memory endpoint exposes the physical/data view.  Source-pinned
Harvard overlays and the DMCU internal 64 KiB SRAM therefore need a separate
read-only view when diagnosing a paused process.  This utility attaches to a
local QEMU PID, calls only the existing read helpers, prints exact words, and
detaches without changing guest state.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def parse_range(value: str) -> tuple[int, int]:
    """Parse ``SEG:OFFSET+SIZE`` or ``ADDRESS+SIZE`` byte ranges."""
    try:
        address_text, size_text = value.split("+", 1)
        if ":" in address_text:
            segment_text, offset_text = address_text.split(":", 1)
            address = (int(segment_text, 16) << 16) | int(offset_text, 16)
        else:
            address = int(address_text, 0)
        size = int(size_text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "range must be SEG:OFFSET+SIZE or ADDRESS+SIZE"
        ) from error
    if address < 0 or address & 1 or size <= 0 or size & 1:
        raise argparse.ArgumentTypeError(
            "address and size must describe positive whole words"
        )
    return address, size


def word_addresses(ranges: list[tuple[int, int]], limit: int):
    for address, size in ranges:
        if address + size > limit:
            raise ValueError(f"range at 0x{address:X} exceeds 0x{limit:X}")
        yield from range(address, address + size, 2)


def code_expression(address: int) -> str:
    return (
        "address_space_lduw_le(((CPUState*)qemu_get_cpu(0))->"
        f"cpu_ases[1].as, 0x{address:x}, (MemTxAttrs){{0}}, 0)"
    )


def internal_expression(address: int) -> str:
    # Do not call internal_data_read(): it relies on QEMU's current_cpu TLS,
    # which is unset when GDB stops the main ppoll thread.  Read the owning
    # DMCUCPU buffer directly; this is both side-effect-free and independent
    # of which host thread GDB selected.
    pointer = "((DMCUCPU*)qemu_get_cpu(0))->internal_data"
    return (
        f"*(unsigned char*)({pointer} + 0x{address:x}) | "
        f"(*(unsigned char*)({pointer} + 0x{address + 1:x}) << 8)"
    )


def gdb_commands(
    code_ranges: list[tuple[int, int]],
    internal_ranges: list[tuple[int, int]],
) -> list[str]:
    """Build the read-only GDB command stream.

    The stream is supplied through ``/dev/stdin`` instead of expanding one
    ``-ex`` argument per word.  That keeps large stack/code captures below the
    Windows CreateProcess command-line limit.
    """
    commands = [
        "set pagination off",
        # DMCUCPU embeds the 64 KiB internal SRAM in a roughly 290 KiB CPU
        # object.  GDB's conservative default rejects member access before it
        # can reduce the expression to the requested byte.  Raising this host
        # debugger limit is read-only and does not alter QEMU or guest state.
        "set max-value-size unlimited",
    ]
    for address in word_addresses(code_ranges, 0x1000000):
        commands.append(
            f'printf "C {address:06X} %04x\\n", '
            f"{code_expression(address)}"
        )
    for address in word_addresses(internal_ranges, 0x10000):
        commands.append(
            f'printf "I {address:04X} %04x\\n", '
            f"{internal_expression(address)}"
        )
    commands.append("detach")
    return commands


def windows_to_wsl_path(path: str) -> str:
    """Translate an absolute Windows path for a WSL process."""
    drive, tail = os.path.splitdrive(os.path.abspath(path))
    if not drive or len(drive) != 2 or drive[1] != ":":
        raise ValueError(f"not an absolute Windows drive path: {path}")
    relative = tail.lstrip("\\/").replace("\\", "/")
    return f"/mnt/{drive[0].lower()}/{relative}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--code", action="append", type=parse_range, default=[])
    parser.add_argument(
        "--internal", action="append", type=parse_range, default=[],
    )
    parser.add_argument(
        "--gdb", default="gdb",
        help="GDB executable inside WSL (default: %(default)s)",
    )
    args = parser.parse_args()
    if args.pid <= 0:
        parser.error("--pid must be positive")
    if not args.code and not args.internal:
        parser.error("at least one --code or --internal range is required")

    try:
        commands = gdb_commands(args.code, args.internal)
    except ValueError as error:
        parser.error(str(error))
    command_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".gdb", encoding="ascii", newline="\n",
            delete=False,
        ) as command_file:
            command_file.write("\n".join(commands) + "\n")
            command_path = Path(command_file.name)
        command = [
            "wsl.exe", "-e", args.gdb, "-nx", "-q", "-batch",
            "-p", str(args.pid), "-x", windows_to_wsl_path(str(command_path)),
        ]
        result = subprocess.run(command, check=False, text=True)
        return result.returncode
    finally:
        if command_path is not None:
            command_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
