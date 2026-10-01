#!/usr/bin/env python3
"""Integration check of atomic QOM key input, without user firmware or NAND."""
from __future__ import annotations

import argparse
import base64
import json
import re
import struct
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web.np560_web import Emulator, QMPError


ROW_MASKS = (0x0004, 0x0008, 0x0010, 0x0020,
             0x0040, 0x0080, 0x4000, 0x8000)
DRIVES = tuple(0xFFFF ^ row for row in ROW_MASKS) + (0xFFFF, 0)


def scanner_program() -> bytes:
    # The guest selects each F164 strobe and stores F160 in ordinary RAM.
    # IGNDS prefixes address these registers directly, independent of DS0.
    # Distinct byte lanes: logical A2:28D3 is the LOW byte of word 28D2.
    # Diagnostics must apply the same byte-lane XOR as guest MOVZE.
    words = [0x6810, 0x00A2, 0x68F0, 0x12AB, 0xA8F0, 0x28D2]
    for index, drive in enumerate(DRIVES):
        words += [0x68F0, drive, 0x3F10, 0xA8F0, 0xF164,
                  0x3F10, 0x88F0, 0xF160,
                  0x3F10, 0xA8F0, 0x2400 + index * 2]
    words += [0xAD03, 0x0000]  # repeat at VMA03:0000
    return struct.pack(f"<{len(words)}H", *words)


def expected_columns(matrix: int) -> list[int]:
    # Independently form the eight column bytes, then OR selected rows.
    columns = [(matrix >> (column * 8)) & 0xFF for column in range(8)]
    result = []
    for drive in DRIVES:
        selected = sum(1 << row for row, mask in enumerate(ROW_MASKS)
                       if not drive & mask)
        result.append(0xFF ^ sum(1 << column for column, rows in enumerate(columns)
                                if rows & selected))
    return result


def check_guest_scan(emulator: Emulator) -> int:
    def expect(matrix, state=0):
        emulator.set_key(state, 0, 0 if state else matrix & 0xFFFFFFFF,
                         0 if state else matrix >> 32)
        expected = expected_columns(matrix)
        deadline = time.monotonic() + 3
        while True:
            frame = emulator.snapshot("data", 0x2400, len(DRIVES) * 2,
                                      diagnostics=False)["frame"]
            actual = [value & 0xFF for value in struct.unpack(
                f"<{len(DRIVES)}H", base64.b64decode(frame))]
            if actual == expected:
                return
            if time.monotonic() >= deadline:
                raise AssertionError({"matrix": f"{matrix:016x}",
                                      "expected": expected, "actual": actual})
            time.sleep(0.005)

    count = 0
    for index in range(64):
        expect(1 << index)
        expect(0)
        count += 2
    # Same row/different columns, same column/different rows, low/high
    # boundary, and all switches. No host-side scan-priority selection.
    for matrix in ((1 << 0) | (1 << 56), (1 << 0) | (1 << 7),
                   (1 << 31) | (1 << 32), (1 << 29) | (1 << 53),
                   0xFFFFFFFFFFFFFFFF, 0):
        expect(matrix)
        count += 1
    for bit, index in enumerate((61, 37, 45, 29, 53, 28, 28, 37,
                                 60, 52, 44, 4, 61, 37, 54, 55)):
        expect(1 << index, state=1 << bit)
        expect(0)
        count += 2
    return count


def check(qemu: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="np560-key-snapshot-") as directory:
        firmware = Path(directory) / "loop.bin"
        firmware.write_bytes(scanner_program())
        emulator = Emulator(qemu=qemu, firmware=firmware,
                            boot_mode="firmware-vma03", start_paused=True)
        try:
            assert emulator.atomic_key_input, "core lacks atomic input property"

            def read():
                return emulator.qmp.execute("qom-get", {
                    "path": "/machine", "property": "key-input-snapshot"})

            def write(value):
                return emulator.qmp.execute("qom-set", {
                    "path": "/machine", "property": "key-input-snapshot",
                    "value": value})

            assert read() == "00000000:00000000:00000000:00000000"
            def trace():
                return json.loads(emulator.qmp.execute('qom-get', {
                    'path': '/machine', 'property': 'key-contact-trace'}))

            assert trace()['enabled'] is False
            assert trace()['count'] == 0
            emulator.qmp.execute('qom-set', {'path': '/machine',
                'property': 'key-contact-trace-enabled', 'value': True})
            # Both halves change atomically; duplicates are not new edges.
            write('00000000:00000000:80000001:80000001')
            write('00000000:00000000:80000001:80000001')
            first_trace = trace()
            assert first_trace['count'] == 1
            assert first_trace['events'][0]['low'] == 0x80000001
            assert first_trace['events'][0]['high'] == 0x80000001
            assert first_trace['events'][0]['scan'] is False
            assert trace() == first_trace, 'read mutated contact record'
            for i in range(130):
                write(f'00000000:00000000:{i & 1:08x}:00000000')
            wrapped = trace()
            assert wrapped['count'] == 131 and wrapped['dropped'] == 3
            assert len(wrapped['events']) == 128
            assert [e['sequence'] for e in wrapped['events']] == list(range(3, 131))
            emulator.set_key(0, 0)
            snapshots = 0
            # Exercise run_on_cpu both when paused and when actively executing.
            for running in (False, True):
                if running:
                    emulator.qmp.execute("cont")
                    try:
                        emulator.qmp.execute('qom-set', {'path': '/machine',
                            'property': 'key-contact-trace-enabled', 'value': False})
                    except QMPError:
                        pass
                    else:
                        raise AssertionError('changed trace mode while running')
                for index in range(64):
                    low = (1 << index) & 0xFFFFFFFF
                    high = (1 << index) >> 32
                    emulator.set_key(0, 0, low, high)
                    assert read() == f"00000000:00000000:{low:08x}:{high:08x}"
                    snapshots += 1
                write("ffffffff:ABCDEF01:80000000:ffffffff")
                expected = "ffffffff:abcdef01:80000000:ffffffff"
                assert read() == expected
                for invalid in ("", "0:0:0:0", expected + "0",
                                " " + expected[1:], expected[:-1] + "g",
                                expected.replace(":", ";", 1)):
                    try:
                        write(invalid)
                    except QMPError:
                        pass
                    else:
                        raise AssertionError(f"accepted malformed input: {invalid!r}")
                    assert read() == expected, "failed write mutated held keys"
                emulator.set_key(0, 0)
                assert read() == "00000000:00000000:00000000:00000000"
            scan_before = emulator.key_status()
            # Availability is explicit, not inferred from zero counters.
            emulator.qmp.execute("stop")
            for minimal in (True, False):
                emulator.qmp.execute("qom-set", {"path": "/machine",
                    "property": "control-observers-minimal", "value": minimal})
                assert emulator.key_status()["full_control_observers"] is (not minimal)
            emulator.qmp.execute("cont")
            guest_scans = check_guest_scan(emulator)
            emulator.qmp.execute("stop")
            scan_after = emulator.key_status()
            scan_again = emulator.key_status()
            contact_trace = trace()
            assert any(e['scan'] for e in contact_trace['events'])
            assert [e['ns'] for e in contact_trace['events']] == sorted(
                e['ns'] for e in contact_trace['events'])
            assert trace() == contact_trace
            emulator.qmp.execute('qom-set', {'path': '/machine',
                'property': 'key-contact-trace-enabled', 'value': False})
            emulator.set_key(0, 0, 1, 1)
            assert trace()['count'] == contact_trace['count']
            emulator.set_key(0, 0)
            registers = emulator.snapshot("data", 0x2400, 2)["registers"]
            assert re.search(r"\b28D2:12ab\b", registers, re.I), registers
            assert re.search(r"\b28D3:ab\b", registers, re.I), "mode diagnostic read wrong byte lane"
            assert scan_after["matrix_active_reads"] > scan_before["matrix_active_reads"]
            assert scan_after["matrix_active_reads"] <= scan_after["matrix_reads"]
            assert scan_after["virtual_time_ns"] >= scan_before["virtual_time_ns"]
            for field in ("matrix_active_reads", "matrix_last_active_pc", "virtual_time_ns"):
                assert scan_again[field] == scan_after[field], "observer changed paused state"
            return {"passed": True, "single_switch_snapshots": snapshots,
                    "guest_matrix_patterns": guest_scans,
                    "row_drives_per_pattern": len(DRIVES),
                    "legacy_state_keys": 16,
                    "active_read_observer_verified": True,
                    "bounded_contact_trace_verified": True,
                    "duplicate_matrix_write_not_an_edge": True,
                    "mode_byte_lane_verified": True,
                    "invalid_payloads_rejected_without_mutation": 12,
                    "modes": ["paused", "running"],
                    "scope": "QOM snapshot and guest F160/F164 reads; not factory debounce or game event consumption"}
        finally:
            emulator.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.qemu), indent=2))
