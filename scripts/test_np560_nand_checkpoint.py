#!/usr/bin/env python3
"""Verify complete NP560 NAND data/OOB checkpoint save and restore."""

from __future__ import annotations

import argparse
import re
import struct
import tempfile
import time
from pathlib import Path

from web.np560_web import Emulator


HEADER_SIZE = 64
DATA_SIZE = 512 * 1024 * 1024
OOB_SIZE = 16 * 1024 * 1024
PAGE_DATA = 2048
PAGE_OOB = 64
OOB_PAGE = 0x140
OOB_PATTERN = bytes(range(64))


def counter(state: str, name: str) -> int:
    match = re.search(rf"\b{name}=(\d+)", state)
    return int(match.group(1)) if match else -1


def wait_for_rw(emulator: Emulator) -> str:
    deadline = time.monotonic() + 5
    while True:
        state = emulator.qmp.execute(
            "qom-get", {"path": "/machine", "property": "nand-state"}
        )
        if (counter(state, "READS") >= 4 and
                counter(state, "PROGRAMS") >= 2 and
                counter(state, "ERASES") >= 1):
            return state
        if time.monotonic() >= deadline:
            raise AssertionError(f"guest NAND sequence timed out: {state}")
        time.sleep(0.01)


def validate_checkpoint(path: Path) -> bytes:
    checkpoint = path.read_bytes()
    expected_size = HEADER_SIZE + DATA_SIZE + OOB_SIZE
    if len(checkpoint) != expected_size:
        raise AssertionError(
            f"checkpoint size {len(checkpoint)} != {expected_size}"
        )
    if checkpoint[:8] != b"NP560N1\0":
        raise AssertionError(f"bad checkpoint magic: {checkpoint[:8]!r}")
    fields = struct.unpack_from("<6I2Q2I", checkpoint, 8)
    expected = (
        1, HEADER_SIZE, PAGE_DATA, PAGE_OOB, 64, 4096,
        DATA_SIZE, OOB_SIZE,
    )
    if fields[:8] != expected:
        raise AssertionError(f"bad checkpoint geometry: {fields[:8]!r}")

    erased_page = checkpoint[
        HEADER_SIZE + 0x120 * PAGE_DATA:
        HEADER_SIZE + 0x121 * PAGE_DATA
    ]
    if erased_page != b"\xff" * PAGE_DATA:
        raise AssertionError("erased data page was not preserved")
    oob_offset = HEADER_SIZE + DATA_SIZE + OOB_PAGE * PAGE_OOB
    if checkpoint[oob_offset:oob_offset + len(OOB_PATTERN)] != OOB_PATTERN:
        raise AssertionError("64-byte OOB stream was not preserved")
    return checkpoint


def save_nand(emulator: Emulator, path: Path) -> None:
    emulator.qmp.execute("qom-set", {
        "path": "/machine", "property": "nand-save", "value": str(path),
    })
    saved = emulator.qmp.execute(
        "qom-get", {"path": "/machine", "property": "nand-save"}
    )
    if saved != str(path):
        raise AssertionError(f"nand-save did not retain output path: {saved!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--soc-rom", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="np560-nand-") as directory:
        work = Path(directory)
        first_checkpoint = work / "written.nand"
        second_checkpoint = work / "restored.nand"
        loop_firmware = work / "loop.prg"
        loop_firmware.write_bytes(b"\xff\xd0" + bytes(0x400000 - 2))

        emulator = Emulator(
            qemu=args.qemu, firmware=args.firmware,
            soc_rom=args.soc_rom, soc_rom_skeleton=True,
        )
        try:
            wait_for_rw(emulator)
            save_nand(emulator, first_checkpoint)
        finally:
            emulator.close()
        first = validate_checkpoint(first_checkpoint)

        emulator = Emulator(
            qemu=args.qemu, firmware=loop_firmware,
            soc_rom=args.soc_rom, soc_rom_skeleton=True,
            nand_checkpoint=first_checkpoint,
        )
        try:
            sample_path = work / "debug-load.bin"
            sample_path.write_bytes(b"NP560-debug-load")
            emulator.load_data(0x500A00, sample_path)
            emulator.write_data(0x500A20, b"\x00\x11\x22\x33")
            emulator.qmp.execute("pmemsave", {
                "val": 0x500A00, "size": 0x24,
                "filename": str(emulator.frame_path),
            })
            debug_data = emulator.frame_path.read_bytes()
            if debug_data[:len(b"NP560-debug-load")] != b"NP560-debug-load":
                raise AssertionError("debug file load did not reach external RAM")
            if debug_data[0x20:0x24] != b"\x00\x11\x22\x33":
                raise AssertionError("debug hex write did not reach external RAM")
            state = emulator.qmp.execute(
                "qom-get", {"path": "/machine", "property": "nand-state"}
            )
            if "CHECKPOINT=restored" not in state:
                raise AssertionError(state)
            for name in ("READS", "PROGRAMS", "ERASES", "COPIES"):
                if counter(state, name) != 0:
                    raise AssertionError(
                        f"idle restore unexpectedly changed {name}: {state}"
                    )
            save_nand(emulator, second_checkpoint)
        finally:
            emulator.close()
        second = validate_checkpoint(second_checkpoint)
        if first != second:
            raise AssertionError("save/restore/save checkpoint bytes differ")

    print("NP560+ NAND checkpoint data/OOB save/restore passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
