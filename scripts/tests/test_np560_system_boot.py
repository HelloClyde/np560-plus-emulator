#!/usr/bin/env python3
"""Boot the recovered NP560+ guest to its native keyboard event loop."""

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import base64
import hashlib
import re
import tempfile
import time
from pathlib import Path

from web.np560_web import Emulator


# Exact active-table result at 4F:2AB2, indexed by the raw 8x8 position
# returned from 2E:5F28.  Index 5 is the firmware's reserved 0xFFFF result;
# it is deliberately retained so the exhaustive regression covers every
# physical row/column intersection rather than only user-visible keys.
RECOVERED_MATRIX_EVENTS = (
    0x65, 0x64, 0x71, 0x77, 0x8E, 0xFFFF, 0x78, 0xC0,
    0x72, 0x66, 0x61, 0x94, 0xE0, 0xE6, 0x63, 0x8D,
    0x74, 0x67, 0x73, 0x92, 0x85, 0x90, 0x76, 0x8B,
    0x79, 0x68, 0x8C, 0x95, 0x84, 0x81, 0x62, 0x88,
    0x75, 0x6A, 0x7A, 0x97, 0xE9, 0x83, 0x6E, 0x8A,
    0x69, 0x6B, 0xB8, 0xBF, 0xEA, 0x80, 0x6D, 0x89,
    0x6F, 0x6C, 0xEE, 0xB7, 0xE1, 0x86, 0x20, 0xB0,
    0x70, 0xE3, 0x7B, 0xB4, 0xE2, 0x82, 0xE7, 0x8F,
)

RESOURCE_STORAGE_ENTRY = 0x33524C
RESOURCE_STORAGE_ENTRY_SOURCE_OFFSET = 0x30524C
RESOURCE_STORAGE_ENTRY_SIZE = 0x12


def cpu_state(emulator: Emulator) -> str:
    return emulator.qmp.execute(
        "qom-get", {"path": "/machine", "property": "cpu-state"}
    )


def physical_memory(emulator: Emulator, address: int, size: int) -> bytes:
    with tempfile.NamedTemporaryFile(prefix="np560-pmem-", delete=False) as out:
        path = Path(out.name)
    try:
        emulator.qmp.execute("pmemsave", {
            "val": address, "size": size, "filename": str(path),
        })
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def require_resource_storage_overlay(
    emulator: Emulator, firmware: Path,
) -> None:
    """Prove the late ROM loader installed the lifecycle storage wrapper."""
    expected = firmware.read_bytes()[
        RESOURCE_STORAGE_ENTRY_SOURCE_OFFSET:
        RESOURCE_STORAGE_ENTRY_SOURCE_OFFSET + RESOURCE_STORAGE_ENTRY_SIZE
    ]
    actual = physical_memory(
        emulator, RESOURCE_STORAGE_ENTRY, RESOURCE_STORAGE_ENTRY_SIZE
    )
    if actual != expected:
        raise AssertionError(
            "resource storage overlay 50:524C -> 33:524C was not retained: "
            f"expected={expected.hex()} actual={actual.hex()}"
        )


def memory_summary(name: str, address: int, data: bytes) -> str:
    summary = (
        f"{name}={address:06x}+{len(data):x} "
        f"SHA256={hashlib.sha256(data).hexdigest()} "
        f"NONZERO={sum(value != 0 for value in data)} "
        f"LEVELS={','.join(f'{value:02x}' for value in sorted(set(data)))}"
    )
    return summary + (f" HEX={data.hex()}" if len(data) <= 64 else "")


def require_bottom_up_lcd_rows(frame: bytes, framebuffer: bytes) -> None:
    """Pin the native framebuffer-to-panel Y contract without OCR.

    The LCD property is the last completed ST7529 frame, while pmemsave may
    observe the guest already drawing the next one.  Permit framebuffer-only
    pixels on rows which are still blank in the completed LCD frame.  A guest
    write can also race the sample within an already visible row, so permit a
    two-pixel count delta there.  A vertical mirror changes many row counts by
    far more than this and therefore still fails.
    """
    if len(frame) != 240 * 120 or len(framebuffer) != 240 * 120 // 2:
        raise AssertionError("invalid LCD/framebuffer size for Y-order check")
    background = max(set(frame), key=frame.count)
    lcd_rows = [
        sum(pixel != background for pixel in frame[y * 240:(y + 1) * 240])
        for y in range(120)
    ]
    packed_rows = []
    for y in range(120):
        row = framebuffer[y * 120:(y + 1) * 120]
        packed_rows.append(sum(
            ((value >> 4) != 0) + ((value & 0x0f) != 0)
            for value in row
        ))
    reversed_rows = packed_rows[::-1]
    mismatches = [
        (row, lcd, source)
        for row, (lcd, source) in enumerate(zip(lcd_rows, reversed_rows))
        if abs(lcd - source) > 2 and lcd != 0
    ]
    if not any(lcd_rows) or mismatches:
        raise AssertionError(
            "ST7529 visible rows do not match the guest's bottom-up "
            f"framebuffer: LCD={lcd_rows} FB_REVERSED={reversed_rows} "
            f"VISIBLE_MISMATCHES={mismatches}"
        )


def require_clean_state(state: str) -> None:
    for expected in (
        "ROM_HLE=off",
        "ROM_MISSING=none",
        "INVALID_CONTROL=none",
        "UNSUPPORTED=none",
        "FIRST_LOW_FP=none",
        "FIRST_LOW_SP=none",
        "NAND=EC:DC:10:95",
        "ERROR=0",
    ):
        if expected not in state:
            raise AssertionError(f"missing {expected!r}:\n{state}")


def trace_calls(state: str, name: str) -> int:
    match = re.search(rf"(?:^|,){re.escape(name)}:(\d+)@", state)
    return int(match.group(1)) if match else 0


def trace_r0(state: str, name: str) -> int:
    match = re.search(
        rf"(?:^|,){re.escape(name)}:\d+@[^,\n]*/r([0-9A-Fa-f]{{4}}):",
        state,
    )
    return int(match.group(1), 16) if match else -1


def trace_r2(state: str, name: str) -> int:
    match = re.search(
        rf"(?:^|,){re.escape(name)}:\d+@[^,\n]*/r"
        rf"[0-9A-Fa-f]{{4}}:[0-9A-Fa-f]{{4}}:"
        rf"([0-9A-Fa-f]{{4}})/a",
        state,
    )
    return int(match.group(1), 16) if match else -1


def application_calls(state: str, name: str) -> int:
    match = re.search(
        rf"(?:APPLICATION_TRACE=|,){re.escape(name)}:(\d+)@", state
    )
    return int(match.group(1)) if match else 0


def rom_call_count(state: str) -> int:
    """Return the cumulative resident-ROM call counter from cpu-state."""
    match = re.search(r"\bROM_CALL=[^\n]*\bCALLS=(\d+)", state)
    return int(match.group(1)) if match else 0


def diagnostic_counter(state: str, name: str) -> int:
    """Return one decimal counter from the machine's diagnostic state."""
    # Diagnostic groups are not completely uniform: top-level counters use
    # ``NAME=value`` while counters embedded in a group use ``NAME:value``.
    match = re.search(rf"\b{re.escape(name)}[=:](\d+)", state)
    return int(match.group(1)) if match else 0


def keyboard_last_event(state: str) -> int:
    match = re.search(
        r"\bKEYBOARD_EVENTS=\d+\s+LAST=([0-9a-fA-F]{4})", state
    )
    return int(match.group(1), 16) if match else -1


def matrix_event_last(state: str) -> int:
    match = re.search(
        r"\bMATRIX_EVENT_MAPS=\d+\s+LAST=([0-9a-fA-F]{4})", state
    )
    return int(match.group(1), 16) if match else -1


def matrix_key(raw_event: int) -> tuple[int, int, int]:
    """Translate Web make codes to the evidenced F160/F164 matrix."""
    if raw_event in (0x100, 0x10C):
        return 1 << 0, 61, 0x82
    if raw_event in (0x101, 0x107, 0x10D):
        return 1 << 1, 37, 0x83
    if raw_event == 0x102:
        return 1 << 2, 45, 0x80
    if raw_event == 0x105:
        return 1 << 5, 4, 0x8E
    if raw_event == 0x106:
        return 1 << 6, 28, 0x84
    if raw_event == 0x103:
        return 1 << 3, 29, 0x81
    if raw_event == 0x104:
        return 1 << 4, 53, 0x86
    if raw_event == 0x10F:
        return 1 << 15, 55, 0xB0
    raise ValueError(f"raw event {raw_event:#06x} has no recovered matrix key")


def parse_matrix_event(value: str) -> tuple[int, int]:
    """Parse an exact physical matrix index and expected guest event."""
    try:
        index_text, event_text = value.split(":", 1)
        index = int(index_text, 0)
        event = int(event_text, 0)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(
            "matrix events use INDEX:EVENT, for example 10:0x61"
        ) from exc
    if not 0 <= index < 64 or not 0 <= event <= 0xFFFF:
        raise argparse.ArgumentTypeError(
            "matrix index must be 0..63 and event must be 16-bit"
        )
    return index, event


def wait_for_native_idle(
    emulator: Emulator, timeout: float = 30.0, minimum_nand_reads: int = 1
) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = cpu_state(emulator)
        require_clean_state(last)
        frames = re.search(r"\bFRAMES=(\d+)", last)
        reads = re.search(r"\bREADS=(\d+)", last)
        scanner_calls = re.search(r"\bSTART_GPIO_SCAN_CALL_TRACE=COUNT:(\d+)", last)
        calls = re.search(r"\bROM_CALL=[^\n]*\bCALLS=(\d+)", last)
        # The recovered resident loop tail-jumps from 1E:F734 into the exact
        # 3B:F734 dispatcher.  Its stable pass calls the restored 33:2562
        # event gate and returns at 3B:F7CA; unlike the old exploratory
        # 03:0080 loop, it never parks at one fixed PC.
        resident_pass = (
            "3b:f7c6/bd33>33:2562" in last.lower()
            and "33:2588/c620>3b:f7ca" in last.lower()
        )
        # A full post-upgrade NAND boots into longer drawing passes which can
        # overwrite the bounded control-transfer trace before the host first
        # samples it. Use the existing read-only call trace for 31:D9AA,
        # the software audio-state scanner reached from 3B:F742. F010 is
        # DPRAM and no longer has a fabricated keyboard-MMIO read counter.
        scanner_pass = scanner_calls and int(scanner_calls.group(1)) >= 1
        if ((resident_pass or scanner_pass) and frames and reads and calls
                and int(frames.group(1)) >= 1
                and int(reads.group(1)) >= minimum_nand_reads
                and int(calls.group(1)) >= 1):
            return last
        if emulator.process.poll() is not None:
            raise AssertionError(
                f"QEMU exited with {emulator.process.returncode}:\n{last}"
            )
        time.sleep(0.01)
    raise AssertionError(f"guest did not reach native idle loop:\n{last}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--soc-rom", type=Path, required=True)
    parser.add_argument(
        "--boot-mode",
        choices=("firmware", "firmware-vma03"),
        default="firmware",
        help="firmware address view to test (default: firmware)",
    )
    nand = parser.add_mutually_exclusive_group(required=True)
    nand.add_argument("--nand", type=Path)
    nand.add_argument(
        "--nand-checkpoint", type=Path,
        help="complete QEMU NAND data/OOB checkpoint",
    )
    parser.add_argument(
        "--print-lcd-trace", action="store_true",
        help="print the ST7529 frame-completion trace after boot",
    )
    parser.add_argument(
        "--lcd-frame-output", type=Path,
        help="write the first native non-uniform 240x120 gray5 frame",
    )
    parser.add_argument(
        "--native-framebuffer-output", type=Path,
        help="write the packed 0x503840 native framebuffer at capture time",
    )
    parser.add_argument(
        "--native-backbuffer-output", type=Path,
        help="write the packed 0x500000 native backbuffer at capture time",
    )
    parser.add_argument(
        "--print-cpu-state", action="store_true",
        help="print the complete DMCU diagnostic state after boot",
    )
    parser.add_argument(
        "--log-unimp", action="store_true",
        help="enable QEMU's unimplemented/debug log for reverse engineering",
    )
    parser.add_argument(
        "--raw-event", action="append", type=lambda value: int(value, 0),
        help="Web key make-code to drive through F160/F164; may be repeated",
    )
    parser.add_argument(
        "--matrix-event", action="append", type=parse_matrix_event,
        help="physical 8x8 matrix INDEX:EVENT pair; may be repeated",
    )
    parser.add_argument(
        "--all-matrix-events", action="store_true",
        help="exercise all 64 positions using the recovered active key table",
    )
    parser.add_argument(
        "--matrix-start", type=int, default=0,
        help="first recovered-table index used with --all-matrix-events",
    )
    parser.add_argument(
        "--matrix-count", type=int, default=64,
        help="number of recovered-table entries used with --all-matrix-events",
    )
    parser.add_argument(
        "--skip-event", action="store_true",
        help="stop after native idle without injecting the keyboard smoke test",
    )
    parser.add_argument(
        "--skip-lcd-content-check", action="store_true",
        help="allow the current uniform LCD frame while testing other paths",
    )
    parser.add_argument(
        "--skip-lcd-row-check", action="store_true",
        help=(
            "capture a non-uniform completed LCD frame without comparing it "
            "to a concurrently changing native framebuffer"
        ),
    )
    parser.add_argument(
        "--idle-timeout", type=float, default=30.0,
        help="seconds to wait for the resident idle loop (default: 30)",
    )
    args = parser.parse_args()
    if not 0 <= args.matrix_start < len(RECOVERED_MATRIX_EVENTS):
        parser.error("--matrix-start must be in 0..63")
    if (args.matrix_count < 1 or
            args.matrix_start + args.matrix_count >
            len(RECOVERED_MATRIX_EVENTS)):
        parser.error("--matrix-count must keep the selected range inside 0..63")
    if ((args.matrix_start != 0 or args.matrix_count != 64) and
            not args.all_matrix_events):
        parser.error("--matrix-start/--matrix-count require --all-matrix-events")

    emulator = Emulator(
        qemu=args.qemu,
        firmware=args.firmware,
        soc_rom=args.soc_rom,
        soc_rom_skeleton=True,
        nand_image=args.nand,
        nand_checkpoint=args.nand_checkpoint,
        boot_mode=args.boot_mode,
        log_unimp=args.log_unimp,
    )
    state = ""
    try:
        minimum_nand_reads = 0 if args.nand_checkpoint else 1
        state = wait_for_native_idle(
            emulator,
            timeout=args.idle_timeout,
            minimum_nand_reads=minimum_nand_reads,
        )
        require_resource_storage_overlay(emulator, args.firmware)

        frame_deadline = time.monotonic() + args.idle_timeout
        while True:
            frame = base64.b64decode(emulator.qmp.execute(
                "qom-get", {"path": "/machine", "property": "lcd-frame"}
            ))
            if len(frame) != 240 * 120:
                raise AssertionError(f"LCD frame has {len(frame)} bytes")
            if (args.skip_lcd_content_check or not args.nand_checkpoint
                    or len(set(frame)) >= 2):
                break
            state = cpu_state(emulator)
            require_clean_state(state)
            if emulator.process.poll() is not None:
                raise AssertionError(
                    f"QEMU exited with {emulator.process.returncode}:\n{state}"
                )
            if time.monotonic() >= frame_deadline:
                raise AssertionError(
                    "full NAND checkpoint reached the scheduler but did not "
                    f"produce a non-uniform ST7529 frame:\n{state}"
                )
            time.sleep(0.01)
        lcd_trace = emulator.qmp.execute(
            "qom-get", {"path": "/machine", "property": "lcd-state"}
        )
        native_framebuffer = physical_memory(emulator, 0x503840, 0x3840)
        if len(set(frame)) >= 2 and not args.skip_lcd_row_check:
            require_bottom_up_lcd_rows(frame, native_framebuffer)
        if args.lcd_frame_output:
            args.lcd_frame_output.parent.mkdir(parents=True, exist_ok=True)
            args.lcd_frame_output.write_bytes(frame)
        for output, address in (
            (args.native_framebuffer_output, 0x503840),
            (args.native_backbuffer_output, 0x500000),
        ):
            if output:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(
                    native_framebuffer if address == 0x503840 else
                    physical_memory(emulator, address, 0x3840)
                )

        events = int(re.search(r"\bKEYBOARD_EVENTS=(\d+)", state).group(1))
        event_values: list[tuple[str, int, int, int, int]] = []
        if not args.skip_event:
            explicit_matrix_events = list(args.matrix_event or [])
            if args.all_matrix_events:
                end = args.matrix_start + args.matrix_count
                explicit_matrix_events.extend(
                    enumerate(
                        RECOVERED_MATRIX_EVENTS[args.matrix_start:end],
                        args.matrix_start,
                    )
                )
            raw_values = args.raw_event or (
                [] if explicit_matrix_events else [0x104]
            )
            for raw_event in raw_values:
                if not 0 < raw_event <= 0xffff:
                    raise ValueError("raw events must be non-zero 16-bit values")
                key_state, _raw_index, application_event = matrix_key(raw_event)
                event_values.append((
                    f"{raw_event:04x}", key_state, 0, 0, application_event,
                ))
            for matrix_index, application_event in explicit_matrix_events:
                matrix_low = ((1 << matrix_index) & 0xffffffff
                              if matrix_index < 32 else 0)
                matrix_high = (1 << (matrix_index - 32)
                               if matrix_index >= 32 else 0)
                event_values.append((
                    f"M{matrix_index:02d}", 0, matrix_low, matrix_high,
                    application_event,
                ))
        for event_index, (event_label, key_state, matrix_low, matrix_high,
                          application_event) in enumerate(event_values):
            # The earlier menu blocks in 06:B126.  Once the complete storage
            # context is restored, the active modal screen instead loops at
            # 31:F2AE and consumes the same F160/F164 matrix through the timer
            # scanner and 32:4C34 event-ready path.  Synchronise with whichever
            # exact guest consumer is active before presenting the host edge.
            # A complete checkpoint performs the recovered NAND/OOB scan
            # after the first visible wait frame.  That scan can legitimately
            # take tens of seconds before the modal UI reaches 06:B126, so use
            # the caller-selected boot timeout rather than the former 5 s
            # shortcut that only covered the pre-storage reconstruction.
            deadline = time.monotonic() + args.idle_timeout
            input_mode = ""
            while not input_mode:
                state = cpu_state(emulator)
                require_clean_state(state)
                if "rom_call=06:b126" in state.lower():
                    input_mode = "blocking"
                elif (application_calls(state, "MODALHEAD") > 0 and
                      diagnostic_counter(state, "MATRIX_READS") > 0):
                    input_mode = "polling"
                if time.monotonic() >= deadline:
                    raise AssertionError(
                        "guest did not reach a native matrix consumer:\n"
                        + state
                    )
                time.sleep(0.01)
            initial_main_returns = trace_calls(state, "MAINRET")
            initial_scheduler_returns = application_calls(state, "SCHEDRET")
            initial_lifecycles = application_calls(state, "TOP")
            initial_rom_app_calls = application_calls(state, "ROMAPP")
            initial_keymap_returns = application_calls(state, "KEYMAPRET")
            initial_matrix_maps = diagnostic_counter(
                state, "MATRIX_EVENT_MAPS"
            )
            initial_matrix_active = int(re.search(
                r"\bACTIVE:(\d+)", state
            ).group(1))
            initial_keyboard_events = int(re.search(
                r"\bKEYBOARD_EVENTS=(\d+)", state
            ).group(1))
            emulator.qmp.execute("qom-set", {
                "path": "/machine", "property": "key-code", "value": 0,
            })
            emulator.qmp.execute("qom-set", {
                "path": "/machine", "property": "key-matrix-low",
                "value": matrix_low,
            })
            emulator.qmp.execute("qom-set", {
                "path": "/machine", "property": "key-matrix-high",
                "value": matrix_high,
            })
            emulator.qmp.execute("qom-set", {
                "path": "/machine", "property": "key-state",
                "value": key_state,
            })

            # 06:B126 maps synchronously through exact 28:F4A4, so retain its
            # strong return/dispatch boundary.  The modal polling path first
            # lets the timer scanner debounce the physical edge.  Some of its
            # mappings are only committed after key-up, therefore release as
            # soon as both the guest matrix read and the expected host-to-GPIO
            # event edge have been observed.  The release phase below then
            # requires the guest's own 28:F6DE mapping boundary.
            deadline = time.monotonic() + 5
            returned_to_scheduler = False
            while True:
                state = cpu_state(emulator)
                require_clean_state(state)
                matrix_active = int(re.search(
                    r"\bACTIVE:(\d+)", state
                ).group(1))
                returned_to_scheduler = (
                    trace_calls(state, "MAINRET") > initial_main_returns
                    and trace_r0(state, "MAINRET") == application_event
                )
                dispatched_in_application = (
                    application_calls(state, "ROMAPP") >
                    initial_rom_app_calls
                    and trace_r0(state, "ROMAPP") == application_event
                )
                mapped_by_guest = (
                    application_calls(state, "KEYMAPRET") >
                    initial_keymap_returns
                    and trace_r0(state, "KEYMAPRET") == application_event
                )
                polling_edge = (
                    input_mode == "polling" and
                    matrix_active >= initial_matrix_active + 16 and
                    ((key_state and
                      diagnostic_counter(state, "KEYBOARD_EVENTS") >
                      initial_keyboard_events and
                      keyboard_last_event(state) == application_event) or
                     (not key_state and (matrix_low or matrix_high)))
                )
                if (polling_edge or
                        (input_mode == "blocking" and
                         matrix_active > initial_matrix_active and
                         (returned_to_scheduler or
                          dispatched_in_application or
                          mapped_by_guest))):
                    break
                if time.monotonic() >= deadline:
                    raise AssertionError(
                        f"matrix key {event_label} did not reach the "
                        f"{input_mode} guest scanner as "
                        f"{application_event:#04x}:\n"
                        f"{state}"
                    )
                time.sleep(0.01)

            emulator.qmp.execute("qom-set", {
                "path": "/machine", "property": "key-state", "value": 0,
            })
            emulator.qmp.execute("qom-set", {
                "path": "/machine", "property": "key-matrix-low", "value": 0,
            })
            emulator.qmp.execute("qom-set", {
                "path": "/machine", "property": "key-matrix-high", "value": 0,
            })

            # cpu-state retains the most recently entered resident-ROM call.
            # Merely seeing ROM_CALL=06:B126 after clearing the host matrix can
            # therefore be a stale sample from the just-completed key press.
            # A greater cumulative call count proves that the guest observed
            # the release, left 06:6A02's key-up barrier, and entered a fresh
            # 06:B126 polling call.
            release_rom_calls = rom_call_count(state)
            release_matrix_reads = diagnostic_counter(state, "MATRIX_READS")

            # A modal return takes the inferred resident continuation through
            # a new complete 20:026A system-main lifecycle; that parent then
            # prepares and enters exact continuation 2D:7DD2.  A consumed
            # 84/85 event remains in the current lifecycle.  Both paths must
            # eventually reach a released, ready 06:B126 reader before
            # another host edge.
            deadline = time.monotonic() + args.idle_timeout
            while True:
                state = cpu_state(emulator)
                require_clean_state(state)
                lifecycle_ready = (
                    application_calls(state, "TOP") > initial_lifecycles
                    if returned_to_scheduler else
                    application_calls(state, "TOP") >= initial_lifecycles
                )
                blocking_ready = (
                    input_mode == "blocking" and
                    "rom_call=06:b126" in state.lower() and
                    rom_call_count(state) > release_rom_calls
                )
                polling_ready = (
                    input_mode == "polling" and
                    diagnostic_counter(state, "MATRIX_READS") >
                    release_matrix_reads and
                    "f160:00ff" in state.lower() and
                    diagnostic_counter(state, "MATRIX_EVENT_MAPS") >
                    initial_matrix_maps and
                    matrix_event_last(state) == application_event
                )
                if lifecycle_ready and (blocking_ready or polling_ready):
                    break
                if time.monotonic() >= deadline:
                    raise AssertionError(
                        "resident continuation did not start the next native "
                        "application lifecycle:\n" + state
                    )
                time.sleep(0.01)
            events = int(re.search(
                r"\bKEYBOARD_EVENTS=(\d+)", state
            ).group(1))
            consumed_in_application = (
                application_calls(state, "ROMAPP") > initial_rom_app_calls
                and trace_r0(state, "ROMAPP") == application_event
            )
            # TOP 1 is entered by the bootstrap's one-shot parent.  From TOP
            # 2 onward every modal return must unwind the complete 20:026A
            # system-main frame through 03:0084.  R0 is cleared in its
            # epilogue, while the recovered selector event survives in R2.
            if (returned_to_scheduler and initial_lifecycles >= 2 and
                    (application_calls(state, "SCHEDRET") <=
                     initial_scheduler_returns or
                     trace_r2(state, "SCHEDRET") != application_event)):
                raise AssertionError(
                    "scheduler return did not preserve application event "
                    f"{application_event:#04x} in R2:\n{state}"
                )
            if "F340_READS=0" not in state:
                raise AssertionError(
                    "strict system path fell back to the legacy F340 latch:\n"
                    + state
                )
            if (returned_to_scheduler and not consumed_in_application
                    and events != initial_keyboard_events):
                raise AssertionError(
                    "completed application lifecycle retained a stale "
                    "matrix event:\n" + state
                )

            # 28:F6DE proves that the timer callback produced an event, but
            # it does not by itself mean the foreground queue is ready for a
            # second physical edge.  Exact foreground mapper 33:4ECC consumes
            # that slot and the timer path subsequently clears 2A5C.  Wait
            # for both boundaries before injecting another key; presenting
            # M01 immediately after M00 used to race this acknowledgement and
            # incorrectly look like a broken matrix scanner.
            if input_mode == "polling" and event_index + 1 < len(event_values):
                deadline = time.monotonic() + args.idle_timeout
                while True:
                    state = cpu_state(emulator)
                    require_clean_state(state)
                    gate_match = re.search(r"\b2A5C:([0-9A-Fa-f]{4})", state)
                    foreground_consumed = (
                        application_calls(state, "KEYMAPRET") >
                        initial_keymap_returns and
                        trace_r0(state, "KEYMAPRET") == application_event
                    )
                    if (foreground_consumed and gate_match and
                            int(gate_match.group(1), 16) == 0 and
                            "f160:00ff" in state.lower()):
                        break
                    if time.monotonic() >= deadline:
                        raise AssertionError(
                            f"foreground did not consume/rearm matrix event "
                            f"{event_label} ({application_event:#04x}):\n"
                            f"{state}"
                        )
                    time.sleep(0.01)
            if args.print_lcd_trace:
                framebuffer = physical_memory(emulator, 0x503840, 0x3840)
                event_frames = re.search(r"\bFRAMES=(\d+)", state).group(1)
                print(
                    f"EVENT={event_label} EVENTS={events} "
                    f"FRAMES={event_frames} "
                    f"FB_NONZERO={sum(value != 0 for value in framebuffer)} "
                    f"FB_SHA256={hashlib.sha256(framebuffer).hexdigest()}"
                )

        frames = re.search(r"\bFRAMES=(\d+)", state).group(1)
        reads = re.search(r"\bREADS=(\d+)", state).group(1)
        print("NP560+ native system boot passed")
        print(
            f"SCHEDULER=inferred-native-system-main-loop LCD_FRAMES={frames} "
            f"NAND_READS={reads} "
            f"KEYBOARD_EVENTS={events} ROM_HLE=off"
        )
        if args.print_cpu_state:
            print(state)
        if args.print_lcd_trace:
            print(lcd_trace)
            for name, address, size in (
                ("LCD_BACKBUFFER", 0x500000, 0x3840),
                ("LCD_FRAMEBUFFER", 0x503840, 0x3840),
                ("LCD_SOURCE_PTR", 0x0004FC, 4),
                ("FONT_CONFIG", 0x512914, 6),
                ("FONT_BASE", 0x51298C, 4),
                ("APPLICATION_STATE_A", 0x512A70, 0x40),
                ("APPLICATION_STATE_B", 0x512AB0, 0x20),
                ("APP_CONTEXT_KEYS", 0x001280, 0x40),
                ("APP_TIMER_GATE", 0x5243D0, 0x10),
            ):
                print(memory_summary(
                    name, address, physical_memory(emulator, address, size)
                ))
    except Exception:
        # Preserve the guest data backing at a failed synthetic far-call
        # target.  Dynamic applications execute from RAM outside the static
        # 20..5F PRG window, so this distinguishes an unloaded callback from
        # a missing code-bus alias without changing guest execution.
        invalid = re.search(
            r"\bINVALID_CONTROL=[^>]+>([0-9A-Fa-f]{2}):"
            r"([0-9A-Fa-f]{4})",
            state,
        )
        if invalid:
            target = (int(invalid.group(1), 16) << 16) | int(
                invalid.group(2), 16
            )
            start = target & ~0x1F
            data = physical_memory(emulator, start, 0x80)
            print(memory_summary("INVALID_TARGET_DATA", start, data))
        raise
    finally:
        emulator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
