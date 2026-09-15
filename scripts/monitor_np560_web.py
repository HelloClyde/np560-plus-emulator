#!/usr/bin/env python3
"""Watch an NP560 Web/QEMU run and capture the first useful outcome.

The monitor attaches to an existing ``np560_web.py`` instance.  It records
compact heartbeats instead of QEMU's verbose instruction log, pauses the VM on
the first hardware-model incident or native-menu milestone, and saves the CPU
state plus the exact ST7529 frame for later analysis.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


NATIVE_MENU_STAGES = (
    "BOOT33", "STACK33", "INIT261", "INIT9", "SYSMAIN",
    "TOP", "RESINIT", "SELECTOR", "SELRET", "MANAGER",
    "REGLOOK", "REGRET", "MANRET", "MENU", "MENUPAGE",
    "MENUBUILDRET", "PAGEBUILD", "MENUOK",
)


@dataclass(frozen=True)
class Observation:
    status: str
    running: bool
    pc: str
    pc_value: int | None
    stage: str
    irq_entries: int
    irq_fp_overwrites: int
    irq_fp_overwrite_detail: str
    irq_fp_restore_expected: int | None
    irq_fp_restore_value: int | None
    unsupported: str
    rom_missing: str
    invalid_control: str
    frame_sha256: str
    frame_nonuniform_pixels: int
    lcd_nonzero_flushes: int
    incidents: tuple[str, ...]
    menu_reached: bool
    sysmain_calls: int
    sysmain_sp: int | None
    sysmain_from: str
    scheduler_returns: int
    main_returns: int
    cafe_record_reads: int
    cafe_record_detail: str
    resource_window_value: int | None
    resource_window_writes: int
    resource_window_zero_io_calls: int
    resource_window_detail: str
    application_state: int | None
    application_pending: int | None
    application_stage: int | None
    resource_path_flag: int | None
    resource_path_detail: str
    foreground_cycles: int
    operation_setup_returns: int
    result_handle_calls: int
    result_handle_ptr_calls: int
    modal_polls: int
    menu_calls: int
    menu_ok_calls: int
    root_object_failures: int
    npe_far_copy_root_overwrite: str


@dataclass
class StackDescentWatch:
    """Detect a repeated foreground-stack leak before it corrupts a frame."""

    required_cycles: int = 2
    min_bytes_per_cycle: int = 16
    last_calls: int = 0
    last_sp: int | None = None
    descending_cycles: int = 0
    descending_bytes: int = 0

    def update(self, observation: Observation) -> str | None:
        calls = observation.sysmain_calls
        sp = observation.sysmain_sp
        if not calls or sp is None:
            return None
        if calls == self.last_calls:
            return None
        if self.last_sp is None or calls < self.last_calls:
            self.last_calls = calls
            self.last_sp = sp
            self.descending_cycles = 0
            self.descending_bytes = 0
            return None

        cycle_delta = calls - self.last_calls
        byte_delta = self.last_sp - sp
        if byte_delta >= self.min_bytes_per_cycle * cycle_delta:
            self.descending_cycles += cycle_delta
            self.descending_bytes += byte_delta
        else:
            self.descending_cycles = 0
            self.descending_bytes = 0

        self.last_calls = calls
        self.last_sp = sp
        if self.descending_cycles < self.required_cycles:
            return None
        average = self.descending_bytes // self.descending_cycles
        return (
            "SYSMAIN stack descends across "
            f"{self.descending_cycles} lifecycle(s): "
            f"SP={sp:04x}, drop={self.descending_bytes:#x}, "
            f"about {average:#x}/cycle, caller={observation.sysmain_from}"
        )


@dataclass
class BlankAfterVisibleWatch:
    """Detect a display which becomes uniformly blank after showing content."""

    required_seconds: float = 15.0
    min_visible_pixels: int = 16
    seen_visible: bool = False
    blank_since: float | None = None

    def update(self, observation: Observation, now: float) -> str | None:
        nonuniform = observation.frame_nonuniform_pixels
        if nonuniform >= self.min_visible_pixels:
            self.seen_visible = True
            self.blank_since = None
            return None
        # QEMU retains the number of non-empty native LCD flushes.  Use that
        # history to arm a monitor which attaches after the display has
        # already gone blank; otherwise a late diagnostic attachment could
        # never observe the preceding visible frame.
        if observation.lcd_nonzero_flushes:
            self.seen_visible = True
        if not self.seen_visible:
            return None
        if self.blank_since is None:
            self.blank_since = now
            return None
        duration = now - self.blank_since
        if duration < self.required_seconds:
            return None
        return (
            "LCD became uniform after visible output: "
            f"nonuniform={nonuniform}, blank-for={duration:.2f}s"
        )


def endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def fetch_state(base_url: str, timeout: float) -> dict[str, Any]:
    with urlopen(endpoint(base_url, "/api/state"), timeout=timeout) as response:
        state = json.load(response)
    if not isinstance(state, dict):
        raise ValueError("Web state is not a JSON object")
    if "error" in state:
        raise ValueError(str(state["error"]))
    return state


def control(base_url: str, action: str, timeout: float) -> None:
    body = json.dumps({"action": action}).encode("utf-8")
    request = Request(
        endpoint(base_url, "/api/control"), data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    if not isinstance(result, dict) or not result.get("ok"):
        raise ValueError(f"control {action!r} failed: {result!r}")


def state_line(registers: str, name: str) -> str:
    prefix = f"{name}="
    for line in registers.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return "none"


def application_calls(registers: str, stage: str) -> int:
    match = re.search(
        rf"(?:APPLICATION_TRACE=|,){re.escape(stage)}:(\d+)@", registers,
    )
    return int(match.group(1)) if match else 0


def application_entry(registers: str, stage: str) -> tuple[int, str, int | None]:
    match = re.search(
        rf"(?:APPLICATION_TRACE=|,){re.escape(stage)}:(\d+)@"
        rf"([0-9a-fA-F]{{2}}:[0-9a-fA-F]{{4}})/sp([0-9a-fA-F]{{4}})",
        registers,
    )
    if not match:
        return 0, "none", None
    return int(match.group(1)), match.group(2).lower(), int(match.group(3), 16)


def integer_field(text: str, name: str) -> int | None:
    match = re.search(rf"(?:^|\s){re.escape(name)}:(\d+)", text)
    return int(match.group(1)) if match else None


def hex_field(text: str, name: str) -> int | None:
    match = re.search(rf"(?:^|\s){re.escape(name)}:([0-9a-fA-F]+)", text)
    return int(match.group(1), 16) if match else None


def observe(state: dict[str, Any]) -> Observation:
    registers = str(state.get("registers", ""))
    frame = base64.b64decode(str(state.get("frame", "")), validate=True)
    value_counts = [0] * 256
    for value in frame:
        value_counts[value] += 1
    frame_nonuniform_pixels = (
        len(frame) - max(value_counts) if frame else 0
    )
    pc_match = re.search(r"(?:^|\n)PC=([0-9a-fA-F]{2}):([0-9a-fA-F]{4})", registers)
    if pc_match:
        pc = f"{pc_match.group(1).lower()}:{pc_match.group(2).lower()}"
        pc_value = (int(pc_match.group(1), 16) << 16) | int(pc_match.group(2), 16)
    else:
        pc = "unknown"
        pc_value = None

    irq = state_line(registers, "IRQ64")
    irq_entries = integer_field(irq, "ENTRIES") or 0
    fp = state_line(registers, "IRQ_SAVE_FP")
    overwrite = state_line(registers, "IRQ_SAVE_FP_OVERWRITE")
    overwrite_count = integer_field(overwrite, "COUNT") or 0
    overwrite_bus = integer_field(overwrite, "BUS")
    restore_expected = hex_field(fp, "EXPECT")
    restore_value = hex_field(fp, "SLOT")
    restores = integer_field(fp, "RESTORES") or 0
    unsupported = state_line(registers, "UNSUPPORTED")
    rom_missing = state_line(registers, "ROM_MISSING")
    invalid_control = state_line(registers, "INVALID_CONTROL")
    native_lcd_flush = state_line(registers, "NATIVE_LCD_FLUSH")
    lcd_nonzero_flushes = integer_field(native_lcd_flush, "NONZERO_CALLS") or 0
    cafe_record = state_line(registers, "NAND_CAFE_RECORD")
    cafe_record_reads = integer_field(cafe_record, "READS") or 0
    resource_window = state_line(registers, "RESOURCE_WINDOW")
    resource_window_value = hex_field(resource_window, "VALUE")
    resource_window_writes = integer_field(resource_window, "WRITES") or 0
    resource_window_zero_io_calls = (
        integer_field(resource_window, "ZERO_IO") or 0
    )
    application_state_line = state_line(registers, "APPLICATION_STATE")
    application_state = hex_field(application_state_line, "STATE")
    application_pending = hex_field(application_state_line, "PENDING")
    application_stage = hex_field(application_state_line, "STAGE")
    resource_path_flag = hex_field(application_state_line, "RESOURCE_FLAG")
    root_object_failures = (
        integer_field(state_line(registers, "ROOT_OBJECT_FAIL"), "COUNT") or 0
    )
    file_root_pool = state_line(registers, "FILE_ROOT_POOL")
    npe_control_trace = state_line(registers, "NPE_CONTROL_TRACE")
    npe_far_copy_root_overwrite = "none"
    if ("@2e:46bc" in file_root_pool.lower() and
            hex_field(npe_control_trace, "PHASE") == 2):
        npe_far_copy_root_overwrite = file_root_pool
    sysmain_calls, sysmain_from, sysmain_sp = application_entry(
        registers, "SYSMAIN"
    )

    stage = "RESET"
    for candidate in NATIVE_MENU_STAGES:
        if application_calls(registers, candidate):
            stage = candidate

    incidents: list[str] = []
    if overwrite_count:
        bus_name = {
            1: "translated data bus",
            2: "internal SRAM path",
        }.get(overwrite_bus, f"unknown bus {overwrite_bus}")
        incidents.append(
            f"0x04D6 IRQ FP save slot overwritten via {bus_name}: {overwrite}"
        )
    if (restores and restore_expected is not None and restore_value is not None
            and restore_expected != restore_value):
        incidents.append(
            f"IRQ FP restore mismatch {restore_expected:04x}!={restore_value:04x}"
        )
    if unsupported != "none" and not unsupported.startswith("none "):
        incidents.append(f"unsupported stop: {unsupported}")
    if rom_missing != "none" and not rom_missing.startswith("none "):
        incidents.append(f"missing ROM: {rom_missing}")
    if invalid_control != "none" and not invalid_control.startswith("none "):
        incidents.append(f"invalid control transfer: {invalid_control}")
    if pc_value is not None and (pc_value & 1):
        incidents.append(f"odd instruction address {pc}")
    exec_trace = state_line(registers, "EXEC_TRACE")
    zero_data_instructions = sum(
        1 for segment, _offset, word in re.findall(
            r"(?:^|,)(5[1-3]):([0-9a-fA-F]{4})/([0-9a-fA-F]{4})",
            exec_trace,
        )
        if int(word, 16) == 0
    )
    if (pc_value is not None and 0x510000 <= pc_value < 0x540000 and
            zero_data_instructions >= 12):
        incidents.append(
            "execution entered writable data RAM with at least "
            f"{zero_data_instructions} zero instructions: PC={pc}"
        )
    if resource_window_zero_io_calls:
        incidents.append(
            "resource I/O used A2:28E0 while it was zero: "
            f"{resource_window}"
        )
    if npe_far_copy_root_overwrite != "none":
        incidents.append(
            "NPE far copy 2E:46BC overwrote the 50:FE74 file-root pool"
        )

    return Observation(
        status=str(state.get("status", "unknown")),
        running=bool(state.get("running")),
        pc=pc,
        pc_value=pc_value,
        stage=stage,
        irq_entries=irq_entries,
        irq_fp_overwrites=overwrite_count,
        irq_fp_overwrite_detail=overwrite,
        irq_fp_restore_expected=restore_expected,
        irq_fp_restore_value=restore_value,
        unsupported=unsupported,
        rom_missing=rom_missing,
        invalid_control=invalid_control,
        frame_sha256=hashlib.sha256(frame).hexdigest(),
        frame_nonuniform_pixels=frame_nonuniform_pixels,
        lcd_nonzero_flushes=lcd_nonzero_flushes,
        incidents=tuple(incidents),
        menu_reached=application_calls(registers, "MENUOK") > 0,
        sysmain_calls=sysmain_calls,
        sysmain_sp=sysmain_sp,
        sysmain_from=sysmain_from,
        scheduler_returns=application_calls(registers, "SCHEDRET"),
        main_returns=application_calls(registers, "MAINRET"),
        cafe_record_reads=cafe_record_reads,
        cafe_record_detail=cafe_record,
        resource_window_value=resource_window_value,
        resource_window_writes=resource_window_writes,
        resource_window_zero_io_calls=resource_window_zero_io_calls,
        resource_window_detail=resource_window,
        application_state=application_state,
        application_pending=application_pending,
        application_stage=application_stage,
        resource_path_flag=resource_path_flag,
        resource_path_detail=(
            "not attempted" if resource_path_flag == 0 else
            "resource path unavailable" if resource_path_flag == 1 else
            "unknown" if resource_path_flag is None else
            f"firmware value 0x{resource_path_flag:04x}"
        ),
        foreground_cycles=application_calls(registers, "FGPARENT"),
        operation_setup_returns=application_calls(registers, "OP0BRET"),
        result_handle_calls=application_calls(registers, "HANDLE"),
        result_handle_ptr_calls=application_calls(registers, "HANDLEPTR"),
        modal_polls=application_calls(registers, "MODALPOLL"),
        menu_calls=application_calls(registers, "MENU"),
        menu_ok_calls=application_calls(registers, "MENUOK"),
        root_object_failures=root_object_failures,
        npe_far_copy_root_overwrite=npe_far_copy_root_overwrite,
    )


def render_lcd(frame: bytes, width: int, height: int, output: Path) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to render the LCD PNG") from exc

    if len(frame) != width * height:
        raise ValueError(
            f"unexpected LCD frame size {len(frame)} != {width * height}"
        )
    lcd_off = (0xB7, 0xC8, 0xA1)
    lcd_on = (0x24, 0x31, 0x26)
    pixels = []
    for raw in frame:
        level = (raw & 31) / 31
        pixels.append(tuple(
            round(off + (on - off) * level)
            for off, on in zip(lcd_off, lcd_on)
        ))
    image = Image.new("RGB", (width, height))
    image.putdata(pixels)
    image = image.resize((width * 4, height * 4), Image.Resampling.NEAREST)
    image.save(output)


def capture(output_dir: Path, state: dict[str, Any], observation: Observation,
            reason: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    registers = str(state.get("registers", ""))
    frame = base64.b64decode(str(state.get("frame", "")), validate=True)
    metadata = dict(state)
    metadata.pop("frame", None)
    metadata["capture_reason"] = reason
    metadata["observation"] = asdict(observation)
    (output_dir / "state.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    (output_dir / "registers.txt").write_text(registers, encoding="utf-8")
    (output_dir / "lcd.gray5").write_bytes(frame)
    render_lcd(
        frame, int(state.get("width", 240)), int(state.get("height", 120)),
        output_dir / "lcd.png",
    )


def should_stop(mode: str, observation: Observation) -> str | None:
    # Milestone-specific modes still need to preserve the *first* hard-fault
    # state.  Waiting for a foreground return or menu after an unsupported
    # opcode, odd PC, corrupt IRQ frame, or invalid control transfer only lets
    # timer traffic obscure the original cause.  ``never`` is the one explicit
    # opt-out for users who want passive observation.
    if (mode not in ("never", "npe-overwrite") and
            observation.incidents):
        return "incident"
    if (mode == "npe-overwrite" and
            observation.npe_far_copy_root_overwrite != "none"):
        return "npe-overwrite"
    if mode in ("menu", "either") and observation.menu_reached:
        return "menu"
    if mode == "cafe" and observation.cafe_record_reads:
        return "cafe"
    if mode == "return" and observation.main_returns:
        return "foreground-return"
    if mode == "resource-failure" and observation.resource_path_flag == 1:
        return "resource-failure"
    return None


def change_signature(observation: Observation) -> tuple[Any, ...]:
    """Return only state transitions worth printing immediately.

    Lifecycle, allocation, IRQ, and framebuffer counters can advance several
    times between Web samples.  Including them in the signature turned the
    compact monitor into a multi-megabyte per-instruction transcript and hid
    the first useful transition.  They are still printed on each heartbeat
    and retained in captures; only immediate console/event-log emission is
    de-duplicated here.
    """
    return (
        observation.status,
        observation.stage,
        observation.irq_fp_overwrites,
        observation.unsupported,
        observation.rom_missing,
        observation.invalid_control,
        observation.resource_window_value,
        observation.resource_window_zero_io_calls,
        observation.application_state,
        observation.application_pending,
        observation.application_stage,
        observation.resource_path_flag,
        observation.menu_reached,
        observation.root_object_failures,
        observation.npe_far_copy_root_overwrite,
        observation.incidents,
    )


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8775")
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--heartbeat", type=float, default=5.0)
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--request-timeout", type=float, default=5.0)
    parser.add_argument(
        "--stop-on",
        choices=(
            "incident", "menu", "cafe", "return", "resource-failure",
            "npe-overwrite", "either", "never",
        ),
        default="either",
    )
    parser.add_argument("--no-pause", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--expect-soc-rom-sha256")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--stack-descent-cycles", type=int, default=2,
        help="stop after this many leaking SYSMAIN lifecycles (default: 2)",
    )
    parser.add_argument(
        "--stack-descent-min-bytes", type=int, default=16,
        help="minimum SP drop per lifecycle treated as a leak (default: 16)",
    )
    parser.add_argument("--no-stack-descent-check", action="store_true")
    parser.add_argument(
        "--blank-after-visible-seconds", type=float, default=15.0,
        help=(
            "stop when an LCD which showed content stays uniform for this "
            "many seconds (default: 15)"
        ),
    )
    parser.add_argument(
        "--blank-min-visible-pixels", type=int, default=16,
        help="nonuniform pixels required to arm the blank watch (default: 16)",
    )
    parser.add_argument("--no-blank-after-visible-check", action="store_true")
    args = parser.parse_args()
    if min(args.poll_interval, args.heartbeat, args.timeout,
           args.request_timeout) <= 0:
        parser.error("intervals and timeouts must be positive")
    if min(args.stack_descent_cycles, args.stack_descent_min_bytes) <= 0:
        parser.error("stack descent thresholds must be positive")
    if args.blank_after_visible_seconds <= 0:
        parser.error("blank-after-visible seconds must be positive")
    if args.blank_min_visible_pixels <= 0:
        parser.error("blank-min-visible-pixels must be positive")

    output_dir = args.output_dir or Path("tmp") / (
        "np560-monitor-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    event_log = output_dir / "events.jsonl"

    if args.resume:
        control(args.url, "resume", args.request_timeout)

    deadline = time.monotonic() + args.timeout
    next_heartbeat = 0.0
    last_signature: tuple[Any, ...] | None = None
    last_state: dict[str, Any] | None = None
    last_observation: Observation | None = None
    samples = 0
    stack_watch = StackDescentWatch(
        required_cycles=args.stack_descent_cycles,
        min_bytes_per_cycle=args.stack_descent_min_bytes,
    )
    blank_watch = BlankAfterVisibleWatch(
        required_seconds=args.blank_after_visible_seconds,
        min_visible_pixels=args.blank_min_visible_pixels,
    )

    while time.monotonic() < deadline:
        try:
            state = fetch_state(args.url, args.request_timeout)
            observation = observe(state)
            if not args.no_stack_descent_check:
                stack_incident = stack_watch.update(observation)
                if stack_incident:
                    observation = replace(
                        observation,
                        incidents=observation.incidents + (stack_incident,),
                    )
            if not args.no_blank_after_visible_check:
                blank_incident = blank_watch.update(
                    observation, time.monotonic(),
                )
                if blank_incident:
                    observation = replace(
                        observation,
                        incidents=observation.incidents + (blank_incident,),
                    )
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            print(f"[{timestamp()}] Web state unavailable: {exc}", file=sys.stderr)
            time.sleep(args.poll_interval)
            continue

        samples += 1
        last_state = state
        last_observation = observation
        expected_sha = args.expect_soc_rom_sha256
        if expected_sha and str(state.get("soc_rom_sha256", "")).lower() != expected_sha.lower():
            raise SystemExit(
                "attached Web instance uses a different SoC ROM: "
                f"{state.get('soc_rom_sha256')} != {expected_sha}"
            )

        signature = change_signature(observation)
        now = time.monotonic()
        changed = signature != last_signature
        if changed or now >= next_heartbeat:
            event = {
                "time": timestamp(), "sample": samples,
                "changed": changed, **asdict(observation),
            }
            with event_log.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            sysmain_sp = (
                f"{observation.sysmain_sp:04x}"
                if observation.sysmain_sp is not None else "----"
            )
            print(
                f"[{event['time']}] sample={samples} status={observation.status} "
                f"pc={observation.pc} stage={observation.stage} "
                f"irq={observation.irq_entries} fp-overwrite="
                f"{observation.irq_fp_overwrites} frame="
                f"{observation.frame_sha256[:12]}/pixels"
                f"{observation.frame_nonuniform_pixels} sysmain="
                f"{observation.sysmain_calls}/sp{sysmain_sp} cafe="
                f"{observation.cafe_record_reads} resource-window="
                f"{(f'{observation.resource_window_value:04x}' if observation.resource_window_value is not None else '----')}"
                f"/w{observation.resource_window_writes}/zero-io"
                f"{observation.resource_window_zero_io_calls} app-state="
                f"{(f'{observation.application_state:04x}' if observation.application_state is not None else '----')}"
                f"/pending{(f'{observation.application_pending:04x}' if observation.application_pending is not None else '----')}"
                f"/stage{(f'{observation.application_stage:04x}' if observation.application_stage is not None else '----')}"
                f" resource-path={observation.resource_path_detail}"
                f" lifecycle=fg{observation.foreground_cycles}"
                f"/op{observation.operation_setup_returns}"
                f"/handle{observation.result_handle_calls}"
                f"/ptr{observation.result_handle_ptr_calls}"
                f"/modal{observation.modal_polls}"
                f" menu={observation.menu_calls}/{observation.menu_ok_calls}"
                f" root-fail={observation.root_object_failures}"
            )
            next_heartbeat = now + args.heartbeat
            last_signature = signature

        reason = should_stop(args.stop_on, observation)
        if args.once and reason is None:
            reason = "one-shot"
        if reason is not None:
            if observation.incidents:
                for incident in observation.incidents:
                    print(f"INCIDENT: {incident}")
            if not args.no_pause and observation.running:
                incidents = observation.incidents
                control(args.url, "pause", args.request_timeout)
                state = fetch_state(args.url, args.request_timeout)
                observation = observe(state)
                observation = replace(observation, incidents=incidents)
            capture(output_dir, state, observation, reason)
            print(f"CAPTURE={output_dir.resolve()}")
            print(f"STOP_REASON={reason}")
            return 2 if reason == "incident" else 0

        time.sleep(args.poll_interval)

    if last_state is not None and last_observation is not None:
        capture(output_dir, last_state, last_observation, "timeout")
    print(f"TIMEOUT={args.timeout:g}s CAPTURE={output_dir.resolve()}")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
