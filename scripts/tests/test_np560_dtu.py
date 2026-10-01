#!/usr/bin/env python3
"""Check DMCU DTU transfers and the original NP560 buffer-refill driver.

All setup, requests and checks of RAM/register values are guest instructions.
The original-driver case uses real Timer2 requests and unmodified 24:98FC.
This does not claim that codecs, DAC sound, DTU cycle stealing or nested IRQs
are implemented. No NAND or user-running emulator is involved.
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
from pathlib import Path

from web.np560_web import Emulator


def write_word(words: list[int], address: int, value: int, *, banked: bool = False) -> None:
    words.extend([0x68F0, value])
    if not banked:
        words.append(0x3F10)
    words.extend([0xA8F0, address])


def read_word(words: list[int], address: int, register: int, *, banked: bool = False) -> None:
    if not banked:
        words.append(0x3F10)
    words.extend([0x88F0 | register, address])


def read_sfr(words: list[int], sfr: int, register: int) -> None:
    words.extend([0x1F00 | sfr, 0x380F | (register << 4)])


def execute(qemu: Path, name: str, words: list[int], expected: dict[int, int], *,
            extra: tuple[int, bytes] | None = None, isr: list[int] | None = None,
            icount: int | None = None,
            verify_extra_code: bool = False,
            extra_regions: tuple[tuple[int, bytes], ...] = (),
            transfers: tuple[int, int] | None = None,
            refill_trace_output: Path | None = None) -> dict[str, str]:
    final_pc = f"PC=20:{len(words) * 2:04x}"
    payload = struct.pack(f"<{len(words) + 1}H", *words, 0xD0FF)
    image = bytearray(payload)
    if isr is not None:
        assert len(image) <= 0x200
        image.extend(bytes(0x200 + len(isr) * 2 - len(image)))
        image[0x200:] = struct.pack(f"<{len(isr)}H", *isr)
    code_regions = sorted(((extra,) if extra is not None else ()) + extra_regions)
    for address, data in code_regions:
        offset = address - 0x200000
        assert offset >= len(image)
        image.extend(bytes(offset + len(data) - len(image)))
        image[offset:] = data
    with tempfile.TemporaryDirectory(prefix="np560-dtu-") as directory:
        root = Path(directory)
        firmware, resident = root / "caller.prg", root / "legacy-tick.bin"
        firmware.write_bytes(image)
        rom = bytearray(b"\x00\x0f" * (0x0840D2 // 2))
        rom[0x0840D0:] = struct.pack("<H", 0xC610)
        resident.write_bytes(rom)
        emulator = Emulator(qemu=qemu, firmware=firmware, soc_rom=resident,
                            soc_rom_skeleton=True, icount_shift=icount,
                            start_paused=True)
        try:
            if verify_extra_code:
                assert code_regions
                for address, expected_code in code_regions:
                    actual_code = base64.b64decode(emulator.snapshot('code', address, len(expected_code))['frame'])
                    assert actual_code == expected_code, (
                        f'fixture differs on instruction bus before execution at {address:06x}',
                        actual_code[:16].hex(), expected_code[:16].hex())
            if refill_trace_output is not None:
                emulator.qmp.execute("qom-set", {
                    "path":"/machine", "property":"dtu-refill-trace", "value":True})
            emulator.qmp.execute("cont")
            # With icount=5, a 1,025 ms guest transfer needs about 32 million
            # interpreted instructions. A short host timeout is not a stall.
            deadline = time.monotonic() + (45 if extra and icount is not None else 12)
            state = ""
            while time.monotonic() < deadline:
                state = emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "cpu-state"})
                if final_pc.lower() in state.lower():
                    break
                time.sleep(0.01)
            if final_pc.lower() not in state.lower():
                detail = {prop: emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": prop})
                    for prop in ("dtu-state", "timer2-state")}
                raise AssertionError((name, state[:1600], detail))
            for register, value in expected.items():
                match = re.search(rf"\bR{register}\s*=([0-9a-f]{{4}})\b", state, re.I)
                assert match and int(match[1], 16) == value, (
                    name, f"R{register} expected {value:04x}", state[:1300])
            for field in ("ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL"):
                assert f"{field}=none" in state, (name, state[:1600])
            dtu = emulator.qmp.execute("qom-get", {
                "path": "/machine", "property": "dtu-state"})
            assert "FAULT_SOURCES:00000000" in dtu, dtu
            if transfers is not None:
                channel, count = transfers
                match = re.search(rf"CH{channel}:([0-9a-f]{{4}})/(\d+)/(\d+)", dtu)
                assert match and int(match[2]) == count, (name, dtu)
                assert int(match[3]) == (2 if extra else 1), (name, dtu)
            if refill_trace_output is not None:
                trace = json.loads(emulator.qmp.execute("qom-get", {
                    "path":"/machine", "property":"dtu-refill-state"}))
                refill_trace_output.write_text(json.dumps(trace, indent=2)+"\n", encoding="utf-8")
                assert trace["enabled"] and trace["count"] == 1, trace
                e = trace["events"][0]
                assert e["channel"] == 0 and e["source"] == 3 and e["count"] == 1, e
                assert e["accepted"] and e["completed_ns"] <= e["accepted_ns"] <= e["reloaded_ns"], e
                assert e["cpu_entries"] == 1 and trace["irq_entries"][3] == 3, trace
            print(f"{name}: {dtu}", flush=True)
            return {"cpu": state, "dtu": dtu}
        finally:
            emulator.close()


def check_transfer(qemu: Path, channel: int, increment: int, *, byte: bool = False,
                   icount: int | None = None) -> None:
    # Deliberately use nonzero DS banks while testing unbanked pointers.
    src_banked, dst_banked = bool(channel & 1), bool(channel & 2)
    control = increment << 14 | (0x2000 if byte else 0) | (
        0x1000 if src_banked else 0) | (0x800 if dst_banked else 0)
    request = 0x43 | channel << 4
    words = [0x6800, 2, 0x6801, 0x7000, 0x6810, 0xA2, 0x6811, 0xA3]
    for index, value in enumerate((0x1234, 0x5678, 0x9ABC)):
        write_word(words, 0x3000 + index * 2, value, banked=src_banked)
        write_word(words, 0xB000 + index * 2, 0xA5A5, banked=dst_banked)
    write_word(words, 0xF0F0 + channel * 4, 0x3000)
    write_word(words, 0xF0F2 + channel * 4, 0xB000)
    words.extend([0x6821 + channel, control | 3])
    # EN masks DTU requests too; enabling the latched RQ performs exactly
    # one transfer, even with CPU IE=0 and CPRI=3/CIRQ=1.
    words.extend([0x6853, request & ~1])
    read_sfr(words, 0x21 + channel, 14)
    for index in range(3):
        words.extend([0x6853, request])
        read_sfr(words, 0x21 + channel, 4 + index)
    read_sfr(words, 0x53, 7)
    read_word(words, 0xF0F0 + channel * 4, 8)
    read_word(words, 0xF0F2 + channel * 4, 9)
    for index, register in enumerate((10, 12, 13)):
        read_word(words, 0xB000 + index * 2, register, banked=dst_banked)
    step = 1 if byte else 2
    output = ([0x1234] * 3 if increment == 1 else
              [0x9ABC if increment == 2 else 0x1234, 0xA5A5, 0xA5A5])
    if byte:
        output = ([0x1212, 0x12A5, 0xA5A5] if increment == 1 else
                  [0x56A5 if increment == 2 else 0x12A5, 0xA5A5, 0xA5A5])
    expected = {4: control | 2, 5: control | 1, 6: control, 7: request,
                8: 0x3000 + (3 * step if increment == 2 else 0),
                9: 0xB000 + (3 * step if increment == 1 else 0),
                10: output[0], 12: output[1], 13: output[2], 14: control | 3}
    execute(qemu, f"CH{channel} INC{increment} byte={byte} icount={icount}",
            words, expected, icount=icount, transfers=(channel, 3))


def check_sfr_bus(qemu: Path) -> None:
    words = [0x6800, 2, 0x6810, 0xA2, 0x6811, 0xA3, 0x6813, 0xBEEF]
    write_word(words, 0xF0F0, 0xF126)  # REG13 on the shared SFR bus
    write_word(words, 0xF0F2, 0xF124)  # REG12, not unrelated banked RAM
    words.extend([0x6821, 1, 0x6853, 0x43])
    read_sfr(words, 0x12, 4)
    read_sfr(words, 0x21, 5)
    execute(qemu, "unbanked DTU accesses device MMIO", words,
            {4: 0xBEEF, 5: 0}, transfers=(0, 1))


def check_bank_boundary(qemu: Path, *, wrap: bool = False) -> None:
    words = [0x6800, 2, 0x6810, 0xA2, 0x6811, 0xA5]
    start, second, control = (0xFFFF, 0, 0xB002) if wrap else (0x7FFE, 0x8000, 0x9002)
    write_word(words, start & ~1, 0x12AB, banked=True)
    write_word(words, second, 0xCD34, banked=True)
    write_word(words, 0x6000, 0)
    write_word(words, 0xF0F0, start)
    write_word(words, 0xF0F2, 0x6000)
    words.extend([0x6821, control, 0x6853, 0x43, 0x6853, 0x43])
    read_word(words, 0xF0F0, 4)
    read_word(words, 0x6000, 5)
    execute(qemu, f"DTU source bank boundary, wrap={wrap}", words,
            {4: 1 if wrap else 0x8002, 5: 0xCD00 if wrap else 0xCD34}, transfers=(0, 2))


def check_original_driver(qemu: Path, original: Path, *, icount: int | None = None,
                          refill_trace_output: Path | None = None) -> None:
    words = [0x68FF, 0x4000, 0x68FB, 0, 0x6800, 2, 0x6810, 0, 0x6811, 1]
    write_word(words, 0x58, 0xAD20)
    write_word(words, 0x5A, 0x200)
    for address, value in ((0xF0F0, 0x3000), (0xF0F2, 0x6000),
                           (0x4AB0, 1024), (0x4AAC, 1024), (0x37FE, 0xCAFE)):
        write_word(words, address, value)
    write_word(words, 0xF01C, 0x0800)  # DPRAM word addressed by BIT[8E]
    words.extend([0x6821, 0, 0x6822, 0,
                  0x68E9, 0x8020, 0xEE00, 0x682E, 2, 0xFE00, 0x682C, 1999,
                  0x6853, 0x41, 0x6800, 0x8002, 0x682D, 0x8080])
    wait = len(words) * 2
    words.extend([0x5643, 0xAC02, wait, 0x6800, 2])
    read_word(words, 0xF0F0, 6)
    read_word(words, 0x6000, 7)
    read_sfr(words, 0x21, 8)
    read_sfr(words, 0x22, 9)
    read_sfr(words, 0x53, 10)
    # A real empty-count request first invokes the unmodified refill code.
    # It programs 83FF, then 8001 on the next completion. Our ISR wrapper
    # only counts entries and stops the test after the second data block.
    isr = [0x5041, 0x5643, 0xAC01, 0x210, 0xBD24, 0x98FC, 0xC610, 0xC700,
           0xFF2D, 0x6853, 0, 0xC610]
    data = original.read_bytes()[0x2198FC:0x2199CE]
    assert data[:2] == b"\x10\x1f" and data[-2:] == b"\x20\xc6"
    execute(qemu, f"original 24:98FC with real Timer2 icount={icount}", words,
            {4: 3, 6: 0x3800, 7: 0xCAFE, 8: 0x8000, 9: 0x8001, 10: 0, 15: 0x4000},
            extra=(0x2498FC, data), isr=isr, icount=icount, transfers=(0, 1024),
            refill_trace_output=refill_trace_output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--original-prg", type=Path, required=True)
    parser.add_argument("--refill-trace-output", type=Path,
                        help="enable and verify completion/IRQ/refill trace in the original-driver cases")
    args = parser.parse_args()
    for channel in range(4):
        for increment in range(3):
            check_transfer(args.qemu, channel, increment)
            check_transfer(args.qemu, channel, increment, byte=True)
    check_transfer(args.qemu, 3, 2, byte=True, icount=5)
    check_sfr_bus(args.qemu)
    check_bank_boundary(args.qemu)
    check_bank_boundary(args.qemu, wrap=True)
    if args.refill_trace_output:
        args.refill_trace_output.mkdir(parents=True, exist_ok=False)
    for icount in (None, 5):
        check_original_driver(args.qemu, args.original_prg, icount=icount,
            refill_trace_output=(args.refill_trace_output/f"refill-{icount}.json")
            if args.refill_trace_output else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
