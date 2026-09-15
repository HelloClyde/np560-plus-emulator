#!/usr/bin/env python3
"""Stream a package NAND image through the unmodified NP560 burner in QEMU."""

from __future__ import annotations

import argparse
import json
import re
import struct
import tempfile
import time
from pathlib import Path

from web.np560_web import Emulator, RunJournal, artifact_identity
from np560_usb_transport import usb_data_to_physical_ram
from build_np560_stream_burn_harness import (
    STREAM_PROTOCOL as PROTOCOL_OFFSET, STREAM_RETURN as RETURN_OFFSET,
    STREAM_UPDATEALL_PROTOCOL, build_program,
)


GLOBAL_BASE = 0x500000
CHUNK_LENGTH = GLOBAL_BASE + 0x0010
SOURCE_POINTER = GLOBAL_BASE + 0x0014
COMMAND_RESULT = GLOBAL_BASE + 0x001A
TARGET_PAGE = GLOBAL_BASE + 0x0030
STREAM_FLAG = 0xE00000
STREAM_ACK = 0xE00002
STREAM_PROBE = 0xE00004
STREAM_SETUP_TRACE = 0xE00010
STREAM_MAPPING_TRACE = 0xE00100
STREAM_READY = 0xA55A
STREAM_FINALIZE_COMMAND = 18
SOURCE = 0x526000
PAGE_SIZE = 512
OFFICIAL_CHUNK_SIZE = 0xC000
SETUP_COMMANDS = {
    "updateall": (23,),
    "official": (23, 1, 27, 11, 2, 25),
    "diagnostic-reset": (23, 1, 2, 25),
}
START_PAGE = 0x880


def signed_word(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def updater_partition_kib(payload_length: int) -> int:
    # UpdateAll.exe 404A8F..404AAC: (slot3_size + 0x110000) >> 10,
    # then add one iff the payload's low ten bits are nonzero.
    if not 0 < payload_length <= 0xFFFFFFFF - 0x110000:
        raise ValueError("payload length overflows the updater partition calculation")
    return (payload_length + 0x110000 + 0x3FF) >> 10


def read_updateall_return(emulator: Emulator, command: int) -> dict:
    raw = words(emulator, STREAM_FLAG + RETURN_OFFSET, 8)
    returned = (raw[0] << 16) | raw[1]
    if returned & 0x80000000:
        returned -= 0x100000000
    result, detail = signed_word(raw[4]), signed_word(raw[5])
    # Original 50:7DB8 sign-extends result into R0:R1. Keep all four return
    # registers as evidence; internal 50:0860 is NOT the host error detail.
    if returned != result:
        raise RuntimeError(f"command {command}: R0:R1={returned} != result={result}")
    return {"command": command, "registers": list(raw[:4]), "result": result,
            "detail": detail, "partition_base": raw[6], "partition_extent": raw[7]}


def prepare_updateall(run_command, total_length: int, partition_kib: int) -> list[dict]:
    """Host decisions recovered from UpdateAll, with explicit unknown errors.

    Known branches: 4024D7..40261E (command 1), 4028AC..402A7B (command 27).
    Unrecognized errors are rejected, not guessed as permission to format.
    run_command executes original guest code and returns its real result.
    """
    records = []

    def run(command, assignments=()):
        result = run_command(command, assignments)
        records.append(result)
        return result

    def require_success(result):
        if result["result"] != 0:
            raise RuntimeError(f"UpdateAll command failed: {result}")

    require_success(run(23))
    size_words = ((partition_kib >> 16) & 0xFFFF, partition_kib & 0xFFFF)
    initial = run(1, ((0x0034, size_words[0]), (0x0036, size_words[1]), (0x0094, 2)))
    code, detail = initial["result"], initial["detail"]
    if code == -10 and detail == -2:
        require_success(run(2))
    elif code == -11 and detail in (-2, -3):
        pass  # NFTL detection failure handled by the vendor's command-27 path.
    elif code != 0:
        raise RuntimeError(f"Unimplemented UpdateAll prepare-error branch: {initial}")
    partition = run(27)
    if partition["result"] == -12:
        require_success(run(11, ((0x0010, size_words[0]), (0x0012, size_words[1]))))
        require_success(run(2))
    elif partition["result"] != 0:
        raise RuntimeError(f"Unexpected UpdateAll partition result: {partition}")
    require_success(run(25, ((0x0038, total_length >> 16),
                            (0x003A, total_length & 0xFFFF),
                            (0x003C, 0), (0x003E, OFFICIAL_CHUNK_SIZE))))
    return records


def run_updateall_setup(emulator: Emulator, total_length: int, partition_kib: int,
                       timeout: float, report_dir: Path, journal: RunJournal):
    if words(emulator, STREAM_FLAG + PROTOCOL_OFFSET, 1)[0] != STREAM_UPDATEALL_PROTOCOL:
        raise RuntimeError("harness does not implement the UpdateAll command protocol")
    ack = STREAM_READY
    index = 0

    def execute(command, assignments):
        nonlocal ack, index
        if command != 23:
            emulator.qmp.execute("stop")
            if words(emulator, STREAM_FLAG, 2) != (0, ack):
                raise RuntimeError("updater command mailbox is not idle")
            for offset, value in (*assignments, (0x0008, command)):
                emulator.write_data(GLOBAL_BASE + offset, struct.pack("<H", value))
            ack = (ack + 1) & 0xFFFF
            emulator.write_data(STREAM_FLAG, struct.pack("<H", 2))
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + timeout
            while words(emulator, STREAM_FLAG, 2) != (0, ack):
                if emulator.process.poll() is not None:
                    raise RuntimeError(f"QEMU exited during setup command {command}")
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"UpdateAll setup command {command} timed out")
                time.sleep(0.1)
        result = read_updateall_return(emulator, command)
        index += 1
        capture_diagnostics(emulator, report_dir / f"setup-{index:02d}-cmd{command:02d}.json",
                            command_result=result)
        journal.record("updater_command", **result)
        print(f"UPDATEALL command={command} result={result['result']} detail={result['detail']} "
              f"partition={result['partition_base']:04x}:{result['partition_extent']:04x}", flush=True)
        return result

    records = prepare_updateall(execute, total_length, partition_kib)
    return ack, records


def capture_diagnostics(emulator: Emulator, path: Path, **context) -> None:
    """Keep small failure evidence even when large NAND saves are disabled."""
    report = {"schema": "np560-stream-burn-diagnostics-v1", **context}
    report["qemu_returncode"] = emulator.process.poll()
    if report["qemu_returncode"] is None:
        for prop in ("cpu-state", "nand-state", "ecc-state"):
            try:
                report[prop] = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": prop},
                    timeout=5.0,
                )
            except Exception as error:
                report[prop + "-error"] = str(error)
        try:
            report["storage_guard"] = storage_guard_state(emulator)
        except Exception as error:
            report["storage_guard_error"] = str(error)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def memory(emulator: Emulator, address: int, size: int) -> bytes:
    emulator.qmp.execute("pmemsave", {
        "val": address, "size": size,
        "filename": str(emulator.frame_path),
    })
    return emulator.frame_path.read_bytes()


def words(emulator: Emulator, address: int, count: int) -> tuple[int, ...]:
    return struct.unpack(f"<{count}H", memory(emulator, address, count * 2))


def nand_counter(state: str, name: str) -> int:
    match = re.search(rf"\b{name}=(\d+)", state)
    return int(match.group(1)) if match else -1


def ecc_counter(state: str, name: str) -> int:
    match = re.search(rf"\b{name}=(\d+)", state)
    return int(match.group(1)) if match else -1


def storage_guard_state(emulator: Emulator) -> str:
    id_words = words(emulator, GLOBAL_BASE + 0x0000, 2)
    device_words = words(emulator, GLOBAL_BASE + 0x0856, 3)
    page_size = words(emulator, GLOBAL_BASE + 0x002E, 1)[0]
    extent = words(emulator, GLOBAL_BASE + 0x0832, 2)
    sentinels = words(emulator, GLOBAL_BASE + 0x07C8, 4)
    shifts = words(emulator, GLOBAL_BASE + 0x07EA, 2)
    nftl_counts = words(emulator, GLOBAL_BASE + 0x07D0, 12)
    mapping_cache = words(emulator, GLOBAL_BASE + 0x0096, 8)
    command_words = words(emulator, GLOBAL_BASE + 0x0034, 6)
    return (
        f"id={id_words[0]:04x}:{id_words[1]:04x} "
        f"device={device_words[0]:04x}:{device_words[1]:04x}:"
        f"{device_words[2]:04x} "
        f"page_size=0x{page_size:04x} "
        f"extent={extent[0]:04x}:{extent[1]:04x} "
        f"sentinels={':'.join(f'{value:04x}' for value in sentinels)} "
        f"shifts={shifts[0]:04x}:{shifts[1]:04x} "
        f"nftl={':'.join(f'{value:04x}' for value in nftl_counts)} "
        f"mapping={':'.join(f'{value:04x}' for value in mapping_cache)} "
        f"cmd34={':'.join(f'{value:04x}' for value in command_words)}"
    )


def wait_ready(emulator: Emulator, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    started = time.monotonic()
    next_report = started + 20.0
    last_state = ""
    last_cpu_state = ""
    while time.monotonic() < deadline:
        if words(emulator, STREAM_FLAG, 2) == (0, STREAM_READY):
            return
        if emulator.process.poll() is not None:
            raise RuntimeError(
                f"QEMU exited with status {emulator.process.returncode}"
            )
        now = time.monotonic()
        if now >= next_report:
            last_state = emulator.qmp.execute(
                "qom-get", {"path": "/machine", "property": "nand-state"}
            )
            last_cpu_state = emulator.qmp.execute(
                "qom-get", {"path": "/machine", "property": "cpu-state"}
            )
            bbf6 = re.search(r"^BBF6_STATUS=.*$", last_cpu_state, re.M)
            pc = re.search(r"^PC=.*$", last_cpu_state, re.M)
            print(
                f"SETUP_PROGRESS={now - started:.1f}s "
                f"reads={nand_counter(last_state, 'READS')} "
                f"programs={nand_counter(last_state, 'PROGRAMS')} "
                f"erases={nand_counter(last_state, 'ERASES')} "
                f"copies={nand_counter(last_state, 'COPIES')} "
                f"{pc.group(0) if pc else 'PC=unavailable'} "
                f"{bbf6.group(0) if bbf6 else 'BBF6_STATUS=unavailable'}",
                flush=True,
            )
            next_report = now + 20.0
        time.sleep(0.1)
    bbf6 = re.search(r"^BBF6_STATUS=.*$", last_cpu_state, re.M)
    raise TimeoutError(
        "burner setup did not become ready: "
        f"{bbf6.group(0) if bbf6 else 'BBF6_STATUS=unavailable'}; "
        f"{last_state}"
    )


def send_chunk(
    emulator: Emulator,
    chunk_path: Path,
    chunk: bytes,
    target_page: int,
    expected_ack: int,
    timeout: float,
) -> int:
    if not 1 <= len(chunk) <= OFFICIAL_CHUNK_SIZE:
        raise ValueError("command-13 chunk must contain 1..0xC000 bytes")
    padded = chunk + b"\xff" * (-len(chunk) % PAGE_SIZE)
    # Emulate the original USB loader's MOVB stores at the raw-RAM boundary.
    # Directly loading wire bytes bypasses the high-byte-first memory lane.
    # Full burner/NAND round-trip validation is separate from this boundary.
    staged = usb_data_to_physical_ram(padded)
    page_count = len(padded) // PAGE_SIZE
    emulator.qmp.execute("stop")
    emulator.qmp.execute("qom-set", {
        "path": "/machine", "property": "debug-trace-reset", "value": True,
    })
    chunk_path.write_bytes(staged)
    emulator.load_data(SOURCE, chunk_path)
    probe_size = min(len(padded), 64)
    if (memory(emulator, SOURCE, probe_size) != staged[:probe_size] or
            memory(emulator, SOURCE + len(padded) - probe_size, probe_size) !=
            staged[-probe_size:]):
        raise RuntimeError("stream chunk did not reach the updater staging RAM")
    fields = {
        CHUNK_LENGTH: struct.pack("<HH", 0, page_count),
        SOURCE_POINTER: struct.pack("<HH", SOURCE >> 16, SOURCE & 0xFFFF),
        TARGET_PAGE: struct.pack(
            "<HH", target_page >> 16, target_page & 0xFFFF,
        ),
    }
    for address, field_bytes in fields.items():
        emulator.write_data(address, field_bytes)
        if memory(emulator, address, len(field_bytes)) != field_bytes:
            raise RuntimeError(
                f"command-13 field at 0x{address:06x} did not reach globals"
            )
    emulator.write_data(STREAM_FLAG, struct.pack("<H", 1))
    emulator.qmp.execute("cont")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        flag, ack = words(emulator, STREAM_FLAG, 2)
        if flag == 0 and ack == expected_ack:
            result = words(emulator, COMMAND_RESULT, 1)[0]
            if result != 0:
                cpu_state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "cpu-state"},
                )
                nand_state = emulator.qmp.execute(
                    "qom-get", {"path": "/machine", "property": "nand-state"},
                )
                stream_trace = re.search(r"^STREAM_GUARD=.*$", cpu_state, re.M)
                detail = stream_trace.group(0) if stream_trace else cpu_state
                raise RuntimeError(
                    f"vendor command 13 returned 0x{result:04x}: {detail}; "
                    f"{nand_state}; {storage_guard_state(emulator)}"
                )
            observed = words(emulator, STREAM_PROBE, 1)[0]
            # The guest reads a numeric 16-bit word, not two wire bytes.
            expected = int.from_bytes(staged[:2], "little")
            if observed != expected:
                raise RuntimeError(
                    f"guest source probe 0x{observed:04x} != 0x{expected:04x}"
                )
            remaining = int.from_bytes(memory(emulator, SOURCE, 2), "little")
            if remaining != expected:
                raise RuntimeError(
                    f"source staging word changed to 0x{remaining:04x} "
                    f"during command 13 (expected 0x{expected:04x})"
                )
            return page_count
        if emulator.process.poll() is not None:
            raise RuntimeError(
                f"QEMU exited with status {emulator.process.returncode}"
            )
        time.sleep(0.05)
    state = emulator.qmp.execute(
        "qom-get", {"path": "/machine", "property": "nand-state"}
    )
    raise TimeoutError(
        f"target page 0x{target_page:x} chunk timed out: {state}"
    )


def finalize_stream(
    emulator: Emulator,
    expected_ack: int,
    timeout: float,
) -> None:
    emulator.qmp.execute("stop")
    emulator.write_data(STREAM_FLAG, struct.pack("<H", 0xFFFF))
    emulator.qmp.execute("cont")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        flag, ack = words(emulator, STREAM_FLAG, 2)
        if flag == 0 and ack == expected_ack:
            result = words(emulator, COMMAND_RESULT, 1)[0]
            if result != 0:
                raise RuntimeError(
                    f"vendor command {STREAM_FINALIZE_COMMAND} returned "
                    f"0x{result:04x}: {storage_guard_state(emulator)}"
                )
            return
        if emulator.process.poll() is not None:
            raise RuntimeError(
                f"QEMU exited with status {emulator.process.returncode}"
            )
        time.sleep(0.1)
    state = emulator.qmp.execute(
        "qom-get", {"path": "/machine", "property": "nand-state"}
    )
    raise TimeoutError(
        f"vendor command {STREAM_FINALIZE_COMMAND} timed out: {state}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True,
                        help="stream-burn guest harness")
    parser.add_argument("--soc-rom", type=Path, required=True)
    parser.add_argument("--boot-mode", choices=("firmware", "firmware-vma03"),
                        default="firmware-vma03",
                        help="harness mapping; VMA03 is the current SoC baseline")
    parser.add_argument("--burn-code", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="complete NAND data/OOB checkpoint")
    parser.add_argument("--report-dir", type=Path,
                        help="new directory for setup, first chunk, final/failure diagnostics")
    parser.add_argument("--nand-checkpoint", type=Path,
                        help="restartable NAND data/OOB input checkpoint")
    parser.add_argument("--setup-mode", choices=tuple(SETUP_COMMANDS), default="updateall",
                        help="updateall follows vendor decisions; official forces the old fixed sequence")
    parser.add_argument("--partition-kib", type=lambda value: int(value, 0),
                        help="diagnostic override; normally derived from payload size by UpdateAll's formula")
    parser.add_argument("--chunk-pages", type=int, default=OFFICIAL_CHUNK_SIZE // PAGE_SIZE)
    parser.add_argument("--progress-every", type=int, default=32,
                        help="report every N completed chunks (also first and last)")
    parser.add_argument("--limit-pages", type=int,
                        help="diagnostic: burn only the first N payload pages")
    parser.add_argument("--setup-timeout", type=float, default=240.0)
    parser.add_argument("--chunk-timeout", type=float, default=180.0)
    parser.add_argument("--finalize-timeout", type=float, default=300.0)
    parser.add_argument(
        "--no-failure-checkpoint", action="store_true",
        help="do not write the large NAND checkpoint when a diagnostic run fails",
    )
    parser.add_argument(
        "--log-unimp", action="store_true",
        help="write opt-in DMCU diagnostic traces to np560-web-qemu.log",
    )
    parser.add_argument(
        "--require-ecc", action="store_true",
        help=(
            "fail unless the vendor burner exercises the modeled "
            "F20A/F20C/F20E ECC registers"
        ),
    )
    args = parser.parse_args()

    failure_output = args.output.with_name(
        f"{args.output.stem}-failure{args.output.suffix}"
    )
    for target in (args.output, failure_output):
        if target.exists():
            parser.error(f"refusing to overwrite existing output: {target}")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if not 1 <= args.chunk_pages <= OFFICIAL_CHUNK_SIZE // PAGE_SIZE:
        parser.error("--chunk-pages must be in 1..96 (the official 0xC000 buffer)")
    if args.progress_every < 1:
        parser.error("--progress-every must be positive")
    payload_size = args.payload.stat().st_size
    if payload_size == 0:
        parser.error("payload must not be empty")
    if args.partition_kib is None:
        try:
            args.partition_kib = updater_partition_kib(payload_size)
        except ValueError as error:
            parser.error(str(error))
    if payload_size > 0xFFFFFFFF or not 0 < args.partition_kib <= 0xFFFFFFFF:
        parser.error("payload and partition request must fit the vendor's 32-bit fields")
    if args.setup_mode == "updateall":
        # Validate BEFORE launching; a legacy harness formats autonomously,
        # so checking a mailbox only after it has started would be too late.
        expected_harness, _ = build_program(payload_size, "updateall")
        if args.firmware.read_bytes() != expected_harness:
            parser.error("--setup-mode updateall requires a freshly generated updateall harness")
    if args.limit_pages is not None:
        if args.limit_pages < 1:
            parser.error("--limit-pages must be positive")
        payload_size = min(payload_size, args.limit_pages * PAGE_SIZE)
    total_pages = (payload_size + PAGE_SIZE - 1) // PAGE_SIZE
    report_dir = args.report_dir or args.output.with_suffix(".run")
    report_dir.mkdir(parents=True, exist_ok=False)
    identities = {}
    for name in ("qemu", "firmware", "soc_rom", "burn_code", "payload", "nand_checkpoint"):
        path = getattr(args, name)
        if path is not None:
            size, sha256 = artifact_identity(path)
            identities[name] = {"path": str(path.resolve()), "size": size, "sha256": sha256}
    (report_dir / "inputs.json").write_text(json.dumps({
        "schema": "np560-stream-burn-inputs-v1",
        "transport": "original-loader-movb-lanes",
        "payload_bytes": payload_size,
        "artifacts": identities,
        "arguments": {key: str(value) if isinstance(value, Path) else value
                      for key, value in vars(args).items()},
    }, indent=2) + "\n", encoding="utf-8")

    journal = RunJournal(report_dir / "process", kind="vendor-burner", artifacts=identities)
    try:
        emulator = Emulator(
            qemu=args.qemu, firmware=args.firmware,
            soc_rom=args.soc_rom, soc_rom_skeleton=True,
            boot_mode=args.boot_mode,
            burn_code=args.burn_code,
            nand_checkpoint=args.nand_checkpoint,
            log_unimp=args.log_unimp,
            # Establish diagnostics before running the initialization code.
            # This does not resolve machine-creation failures (such as the
            # independently observed legacy mapping assertion).
            start_paused=True, journal=journal,
        )
    except Exception as error:
        journal.record("burn_startup_failed", error=f"{type(error).__name__}: {error}")
        raise
    completed_bytes = 0
    completed_chunks = 0
    target_page = START_PAGE
    ack_base = STREAM_READY
    try:
        setup_commands = SETUP_COMMANDS[args.setup_mode]
        print(
            "Running original burner setup commands " +
            " -> ".join(str(command) for command in setup_commands) + "...",
            flush=True,
        )
        print("USB staging: original loader MOVB lanes (wire bytes -> word-swapped physical RAM)",
              flush=True)
        capture_diagnostics(emulator, report_dir / "before-start.json")
        emulator.qmp.execute("cont")
        wait_ready(emulator, args.setup_timeout)
        setup_results = []
        if args.setup_mode == "updateall":
            ack_base, setup_results = run_updateall_setup(
                emulator, args.payload.stat().st_size, args.partition_kib,
                args.setup_timeout, report_dir, journal)
            setup_commands = tuple(result["command"] for result in setup_results)
        legacy_setup_commands = setup_commands if args.setup_mode != "updateall" else ()
        capture_diagnostics(
            emulator, report_dir / "setup-ready.json",
            setup_commands=list(setup_commands),
            setup_results=setup_results,
            setup_trace=list(words(emulator, STREAM_SETUP_TRACE, len(legacy_setup_commands) * 4))
            if legacy_setup_commands else [],
            mapping_trace=list(words(emulator, STREAM_MAPPING_TRACE, len(legacy_setup_commands) * 4))
            if legacy_setup_commands else [],
        )
        setup_state = emulator.qmp.execute(
            "qom-get", {"path": "/machine", "property": "nand-state"}
        )
        print(
            "Burner stream loop ready, "
            f"programs={nand_counter(setup_state, 'PROGRAMS')}, "
            f"maskrom_writes={nand_counter(setup_state, 'MASKROM_WRITES')}",
            flush=True,
        )
        setup_cpu_state = emulator.qmp.execute(
            "qom-get", {"path": "/machine", "property": "cpu-state"},
        )
        for trace_name in (
            "NAND_TRACE", "PARTITION_TRACE", "BURN_ERROR", "OBJECT_INIT",
            "CB62", "CB62_HISTORY", "B0B2", "BBF6_STATUS",
        ):
            setup_trace_line = re.search(
                rf"^{trace_name}=.*$", setup_cpu_state, re.M,
            )
            if setup_trace_line:
                print(setup_trace_line.group(0), flush=True)
        print(f"C87E guard: {storage_guard_state(emulator)}", flush=True)
        descriptor_pointer = words(emulator, GLOBAL_BASE + 0x0842, 2)
        descriptor_base = ((descriptor_pointer[0] << 16) |
                           descriptor_pointer[1])
        descriptor = memory(emulator, descriptor_base, 0x26)
        primary_words = struct.unpack_from("<2H", descriptor, 0x22)
        secondary_words = struct.unpack_from("<2H", descriptor, 0x18)
        primary_pointer = (primary_words[0] << 16) | primary_words[1]
        secondary_pointer = (secondary_words[0] << 16) | secondary_words[1]
        print(
            f"Object0 descriptor={descriptor_base:08x}:"
            f"{descriptor.hex()} primary={primary_pointer:08x}:"
            f"{memory(emulator, primary_pointer, 0x30).hex()} "
            f"secondary={secondary_pointer:08x}:"
            f"{memory(emulator, secondary_pointer, 0x30).hex()}",
            flush=True,
        )
        setup_trace = words(emulator, STREAM_SETUP_TRACE,
                            len(legacy_setup_commands) * 4) if legacy_setup_commands else ()
        print(
            "Partition setup trace: " + ", ".join(
                f"{command}={setup_trace[index * 4]:04x}:"
                f"{setup_trace[index * 4 + 1]:04x}/"
                f"r{setup_trace[index * 4 + 2]:04x}/"
                f"s{setup_trace[index * 4 + 3]:04x}"
                for index, command in enumerate(legacy_setup_commands)
            ),
            flush=True,
        )
        mapping_trace = words(emulator, STREAM_MAPPING_TRACE,
                              len(legacy_setup_commands) * 4) if legacy_setup_commands else ()
        print(
            "Mapping setup trace: " + ", ".join(
                f"{command}={mapping_trace[index * 4]:04x}:"
                f"{mapping_trace[index * 4 + 1]:04x}/"
                f"e0={mapping_trace[index * 4 + 2]:04x}/"
                f"e56f={mapping_trace[index * 4 + 3]:04x}"
                for index, command in enumerate(legacy_setup_commands)
            ),
            flush=True,
        )
        metadata_pointer = words(emulator, GLOBAL_BASE + 0x0090, 2)
        metadata_physical = ((metadata_pointer[0] << 16) |
                             metadata_pointer[1])
        metadata = memory(emulator, metadata_physical, 3 * 0x208)
        print(
            f"NFTL probe buffer={metadata_physical:08x}: " +
            ", ".join(
                f"page{page}={metadata[page * 0x208:page * 0x208 + 32].hex()}"
                for page in range(3)
            ),
            flush=True,
        )
        with args.payload.open("rb") as source, tempfile.TemporaryDirectory(
            prefix="np560-stream-"
        ) as directory:
            chunk_path = Path(directory) / "chunk.bin"
            while completed_bytes < payload_size:
                wanted = min(
                    args.chunk_pages * PAGE_SIZE,
                    payload_size - completed_bytes,
                )
                chunk = source.read(wanted)
                if len(chunk) != wanted:
                    raise RuntimeError("payload ended before its reported size")
                ack = (ack_base + completed_chunks + 1) & 0xFFFF
                written_pages = send_chunk(
                    emulator, chunk_path, chunk,
                    target_page,
                    ack,
                    max(
                        args.chunk_timeout,
                        len(chunk) * 0.08 / PAGE_SIZE,
                    ),
                )
                completed_bytes += len(chunk)
                completed_chunks += 1
                target_page += written_pages
                state = emulator.qmp.execute(
                    "qom-get",
                    {"path": "/machine", "property": "nand-state"},
                )
                if "ERROR=0" not in state:
                    raise RuntimeError(state)
                if completed_chunks == 1:
                    capture_diagnostics(emulator, report_dir / "first-chunk.json",
                                        completed_bytes=completed_bytes)
                    cpu_state = emulator.qmp.execute(
                        "qom-get",
                        {"path": "/machine", "property": "cpu-state"},
                    )
                    ecc_state = emulator.qmp.execute(
                        "qom-get",
                        {"path": "/machine", "property": "ecc-state"},
                    )
                    for trace_name in (
                        "STREAM_COPY", "STREAM_GUARD", "PARTITION_TRACE",
                        "BURN_ERROR",
                    ):
                        source_trace = re.search(
                            rf"^{trace_name}=.*$", cpu_state, re.M,
                        )
                        if source_trace:
                            print(source_trace.group(0), flush=True)
                    print(ecc_state, flush=True)
                    if args.require_ecc and (
                            ecc_counter(ecc_state, "RESETS") < 1 or
                            ecc_counter(ecc_state, "FEEDS") < 256):
                        raise RuntimeError(
                            "first command-13 chunk did not exercise the "
                            f"sector ECC hardware: {ecc_state}"
                        )
                if (completed_chunks == 1 or completed_bytes == payload_size or
                        completed_chunks % args.progress_every == 0):
                    journal.record("burn_progress", completed_bytes=completed_bytes,
                                   payload_bytes=payload_size, completed_chunks=completed_chunks)
                    print(
                        f"{completed_bytes}/{payload_size} bytes "
                        f"({completed_bytes * 100 / payload_size:.1f}%), "
                        f"pages={min(total_pages, (completed_bytes + PAGE_SIZE - 1) // PAGE_SIZE)}, "
                        f"programs={nand_counter(state, 'PROGRAMS')}",
                        flush=True,
                    )

        final_ack = (ack_base + completed_chunks + 1) & 0xFFFF
        print(
            f"Running original burner finalize command "
            f"{STREAM_FINALIZE_COMMAND}...",
            flush=True,
        )
        finalize_stream(emulator, final_ack, args.finalize_timeout)
        emulator.qmp.execute("stop")
        final_state = emulator.qmp.execute(
            "qom-get", {"path": "/machine", "property": "nand-state"}
        )
        final_ecc_state = emulator.qmp.execute(
            "qom-get", {"path": "/machine", "property": "ecc-state"}
        )
        capture_diagnostics(emulator, report_dir / "final.json",
                            completed_bytes=completed_bytes,
                            completed_chunks=completed_chunks)
        if "ERROR=0" not in final_state:
            raise RuntimeError(final_state)
        emulator.qmp.execute("qom-set", {
            "path": "/machine", "property": "nand-save",
            "value": str(args.output),
        })
        print(final_state, flush=True)
        print(final_ecc_state, flush=True)
        print(f"Saved complete NAND checkpoint: {args.output}", flush=True)
        journal.record("burn_saved", completed_bytes=completed_bytes,
                       checkpoint=str(args.output.resolve()))
    except Exception as error:
        try:
            capture_diagnostics(emulator, report_dir / "failure.json",
                                error=f"{type(error).__name__}: {error}",
                                completed_bytes=completed_bytes,
                                completed_chunks=completed_chunks)
        except Exception as diagnostic_error:
            print(f"Could not save diagnostics: {diagnostic_error}", flush=True)
        if emulator.process.poll() is None and not args.no_failure_checkpoint:
            try:
                emulator.qmp.execute("stop")
                emulator.qmp.execute("qom-set", {
                    "path": "/machine", "property": "nand-save",
                    "value": str(failure_output),
                })
                print(
                    f"Saved failure-state NAND checkpoint: {failure_output}",
                    flush=True,
                )
            except Exception as checkpoint_error:
                print(
                    f"Could not save failure-state NAND: {checkpoint_error}",
                    flush=True,
                )
        raise
    finally:
        emulator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
