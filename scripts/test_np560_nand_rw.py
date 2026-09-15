#!/usr/bin/env python3
"""Exercise reconstructed BBF6/BCC6/BDD6 entirely from guest code."""

from __future__ import annotations

import argparse
import re
import tempfile
import time
from pathlib import Path

from web.np560_web import Emulator


PATTERN = bytes.fromhex("00112233445566778899aabbccddeeff")
READBACK = 0x500600
ERASED_READBACK = 0x500700
OOB_READBACK = 0x500800
OOB_PROBE_READBACK = 0x500900
ERASED_STATUS_READBACK = 0x500A00
OOB_PATTERN = bytes(range(64))


def counter(state: str, name: str) -> int:
    match = re.search(rf"\b{name}=(\d+)", state)
    return int(match.group(1)) if match else -1


def wait_for_nand(emulator: Emulator, **minimums: int) -> str:
    deadline = time.monotonic() + 8
    while True:
        state = emulator.qmp.execute(
            "qom-get", {"path": "/machine", "property": "nand-state"}
        )
        if all(counter(state, name) >= value
               for name, value in minimums.items()):
            return state
        if time.monotonic() >= deadline:
            raise AssertionError(f"guest NAND sequence timed out: {state}")
        time.sleep(0.01)


def memory(emulator: Emulator, address: int, size: int = 16) -> bytes:
    emulator.qmp.execute(
        "pmemsave",
        {"val": address, "size": size,
         "filename": str(emulator.frame_path)},
    )
    return emulator.frame_path.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--persist-write-firmware", type=Path, required=True)
    parser.add_argument("--persist-read-firmware", type=Path, required=True)
    parser.add_argument("--soc-rom", type=Path, required=True)
    args = parser.parse_args()

    emulator = Emulator(
        qemu=args.qemu,
        firmware=args.firmware,
        soc_rom=args.soc_rom,
        soc_rom_skeleton=True,
    )
    try:
        state = wait_for_nand(emulator, READS=5, PROGRAMS=2, ERASES=1)
        programmed = memory(emulator, READBACK)
        erased = memory(emulator, ERASED_READBACK)
        oob = memory(emulator, OOB_READBACK, len(OOB_PATTERN))
        # Scalar byte DMA follows the DMCU external-bus A0 lane swap.  The
        # requested logical even address is therefore stored at physical +1.
        oob_probe_lane = memory(emulator, OOB_PROBE_READBACK, 2)
        erased_status_lane = memory(emulator, ERASED_STATUS_READBACK, 2)
        if programmed != PATTERN:
            raise AssertionError(
                f"program/read mismatch: {programmed.hex()} != {PATTERN.hex()}"
            )
        if erased != b"\xFF" * 16:
            raise AssertionError(f"erase/read mismatch: {erased.hex()}")
        expected_oob = OOB_PATTERN
        if oob != expected_oob:
            raise AssertionError(
                f"logical spare mismatch: {oob.hex()} != {expected_oob.hex()}"
            )
        if oob_probe_lane != bytes([0, 55]):
            raise AssertionError(
                "programmed OOB byte-lane probe mismatch: "
                f"{oob_probe_lane.hex()} != 0037"
            )
        if erased_status_lane != b"\x00\xff":
            raise AssertionError(
                "erased logical status byte-lane mismatch: "
                f"{erased_status_lane.hex()} != 00ff"
            )
        if "STATUS=1 ERROR=0" not in state:
            raise AssertionError(state)
        print("NP560+ NAND guest data/OOB read/program/erase passed")
        print(state)
    finally:
        emulator.close()

    with tempfile.TemporaryDirectory(prefix="np560-nand-persist-") as temp:
        checkpoint = Path(temp) / "live.nand"
        writer = Emulator(
            qemu=args.qemu,
            firmware=args.persist_write_firmware,
            soc_rom=args.soc_rom,
            soc_rom_skeleton=True,
            nand_save_on_exit=checkpoint,
        )
        try:
            write_state = wait_for_nand(writer, PROGRAMS=2, ERASES=2)
        finally:
            writer.close()
        expected_checkpoint_size = 64 + 0x20000000 + 0x01000000
        if checkpoint.stat().st_size != expected_checkpoint_size:
            raise AssertionError(
                f"checkpoint size {checkpoint.stat().st_size} != "
                f"{expected_checkpoint_size}"
            )

        reader = Emulator(
            qemu=args.qemu,
            firmware=args.persist_read_firmware,
            soc_rom=args.soc_rom,
            soc_rom_skeleton=True,
            nand_checkpoint=checkpoint,
        )
        try:
            read_state = wait_for_nand(reader, READS=3)
            persisted_data = memory(reader, READBACK)
            persisted_oob = memory(reader, OOB_READBACK, len(OOB_PATTERN))
            persisted_probe_lane = memory(reader, OOB_PROBE_READBACK, 2)
        finally:
            reader.close()
        if "CHECKPOINT=restored" not in read_state:
            raise AssertionError(read_state)
        if persisted_data != PATTERN:
            raise AssertionError(
                f"persisted data mismatch: {persisted_data.hex()}"
            )
        if (persisted_oob != OOB_PATTERN or
                persisted_probe_lane != bytes([0, 55])):
            raise AssertionError(
                "persisted OOB mismatch: "
                f"{persisted_oob.hex()} "
                f"probe-lane={persisted_probe_lane.hex()}"
            )
        print("NP560+ NAND checkpoint save/restart data+OOB passed")
        print(write_state)
        print(read_state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
