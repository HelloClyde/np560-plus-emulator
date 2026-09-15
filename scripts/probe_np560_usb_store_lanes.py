#!/usr/bin/env python3
"""Run the original loader's exact MOVB store opcode on real QEMU.

This deliberately isolates CPU/RAM serialization: it supplies already received
FIFO bytes in RB1 (R0's low byte), not a claim that USB endpoints are implemented.
No existing Web instance or NAND checkpoint is opened/modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import tempfile
import time
from pathlib import Path

from np560_usb_transport import USB_RECEIVE_STORE_WORD, usb_data_to_physical_ram
from web.np560_web import Emulator


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--loader", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    loader = args.loader.read_bytes()
    store = int.from_bytes(loader[0x950:0x952], "big")
    if store != USB_RECEIVE_STORE_WORD or loader[0x94C:0x950] != bytes.fromhex("88f0f230"):
        raise ValueError("original loader receive opcode does not match")
    wire = bytes(range(256)) * 2
    destinations = (0x526000, 0x528000)
    words = []
    for address in destinations:
        words.extend((0x6810, address >> 15, 0x68F8, address & 0x7FFF))
        for byte in wire:
            # RB0 is R0's high byte; RB1 is its low byte. Poison the unused
            # high byte so a register-byte numbering error cannot pass.
            words.extend((0x68F0, ((byte ^ 0xA5) << 8) | byte, store))
    stop = len(words) * 2
    words.extend((0xAC00, stop))
    program = struct.pack(f"<{len(words)}H", *words)
    # Never leave a stale successful manifest in a reused failed run directory.
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    with tempfile.TemporaryDirectory(prefix="np560-usb-lanes-") as name:
        root = Path(name)
        firmware = root / "store.prg"
        firmware.write_bytes(program)
        emulator = Emulator(qemu=args.qemu, firmware=firmware)
        try:
            deadline = time.monotonic() + 10
            while True:
                state = emulator.qmp.execute("qom-get", {"path": "/machine", "property": "cpu-state"})
                if re.search(rf"^PC=20:{stop:04x}\b", state, re.I):
                    break
                if time.monotonic() >= deadline or emulator.process.poll() is not None:
                    raise RuntimeError("guest store probe did not reach stop: " + state[:300])
                time.sleep(0.02)
            (args.output / "cpu-state.txt").write_text(state, encoding="utf-8")
            for address in destinations:
                emulator.qmp.execute("pmemsave", {"val": address, "size": len(wire),
                                                  "filename": str(emulator.frame_path)})
                physical = emulator.frame_path.read_bytes()
                expected = usb_data_to_physical_ram(wire)
                mismatch = sum(a != b for a, b in zip(physical, expected))
                (args.output / f"physical-{address:06x}.bin").write_bytes(physical)
                records.append({"address": address, "length": len(physical),
                                "expected_mismatches": mismatch,
                                "raw_wire_mismatches": sum(a != b for a, b in zip(physical, wire)),
                                "physical_sha256": hashlib.sha256(physical).hexdigest()})
        finally:
            emulator.close()
    passed = all(r["length"] == len(wire) and r["expected_mismatches"] == 0
                 for r in records) and len(records) == len(destinations)
    manifest = {"schema": "np560-exact-usb-byte-store-probe-v1", "passed": passed,
                "scope": "CPU/RAM byte stores; USB FIFO and enumeration NOT tested",
                "loader_sha256": hashlib.sha256(loader).hexdigest(),
                "store_source_pc": "00:1950", "store_word": f"{store:04x}",
                "register_input": "R0=((wire_byte ^ 0xA5) << 8) | wire_byte; RB1 is low byte",
                "program_sha256": hashlib.sha256(program).hexdigest(),
                "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
                "wire_sha256": hashlib.sha256(wire).hexdigest(), "records": records}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
