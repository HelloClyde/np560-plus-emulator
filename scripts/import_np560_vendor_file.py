#!/usr/bin/env python3
"""Import and read back a file using the original package burner file commands.

The diagnostic RAM transport substitutes only for USB delivery. Directory/FAT/
FTL/NAND operations execute in the unmodified slot-0 guest code. No formatting,
offline filesystem construction, or host implementation of ROM services.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import time
from pathlib import Path

from burn_np560_stream import (
    GLOBAL_BASE, STREAM_FLAG, STREAM_READY, SOURCE, PROTOCOL_OFFSET,
    capture_diagnostics,
    read_updateall_return, wait_ready, words,
)
from build_np560_stream_burn_harness import build_file_program, STREAM_FILES_PROTOCOL
from np560_usb_transport import usb_data_to_physical_ram
from web.np560_web import Emulator, RunJournal, artifact_identity


PATH_BUFFER = 0x0FF0
READ_SIZE = 0x2000  # Literal in original command 7 at 51:D0E8.
FILE_COMMANDS = frozenset((1, 3, 4, 5, 7, 8, 10))


def data_memory(emulator, address, size):
    # Low physical addresses also have code-bus aliases. Read the backing
    # data RAM explicitly for the original near buffer, not through pmemsave.
    emulator.qmp.execute("qom-set", {
        "path": "/machine", "property": "debug-data-save",
        "value": f"0x{address:x}:0x{size:x}@{emulator.frame_path}",
    })
    return emulator.frame_path.read_bytes()


def u32_fields(offset: int, value: int) -> tuple[tuple[int, int], ...]:
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("vendor field must fit uint32")
    return ((offset, value >> 16), (offset + 2, value & 0xFFFF))


def encode_path(path: str) -> bytes:
    if not path.startswith("0:\\") or "\x00" in path:
        raise ValueError("destination must be an absolute drive-0 guest path")
    parts = path[3:].split("\\")
    if any(not part or part in (".", "..") or any(c in part for c in '/:*?"<>|')
           for part in parts):
        raise ValueError("guest path contains an empty or unsupported component")
    raw = path.encode("gbk")
    if len(raw) > 255:
        raise ValueError("guest path is longer than the bounded pathname transfer")
    return raw


class VendorFiles:
    """One owned QEMU mailbox; only the documented file-operation subset."""

    def __init__(self, emulator, report_dir, journal, timeout):
        self.emulator = emulator
        self.report_dir = report_dir
        self.journal = journal
        self.timeout = timeout
        self.ack = STREAM_READY
        self.index = 0
        self.records = []

    def command(self, code, assignments=(), *, payload=None, pathname=None):
        if code not in FILE_COMMANDS:
            raise ValueError("not a file-operation command; format/burn commands are forbidden")
        if pathname is not None and payload is not None:
            raise ValueError("one transfer per command")
        emulator = self.emulator
        emulator.qmp.execute("stop")
        if words(emulator, STREAM_FLAG, 2) != (0, self.ack):
            raise RuntimeError("vendor mailbox is not idle")
        if pathname is not None:
            raw = encode_path(pathname)
            # The guest handler appends NUL at pathname + length. Supply it
            # too so that odd transfers never borrow an unknown word half.
            terminated = raw.ljust(256, b"\0")
            emulator.write_data(SOURCE, usb_data_to_physical_ram(terminated))
            assignments = (*assignments, *u32_fields(0x10, len(raw)))
        if payload is not None:
            if not 1 <= len(payload) <= READ_SIZE:
                raise ValueError("file chunk must contain 1..8192 bytes")
            padded = payload + b"\0" * (len(payload) % 2)
            chunk_path = self.report_dir / "transfer.bin"
            chunk_path.write_bytes(usb_data_to_physical_ram(padded))
            emulator.load_data(SOURCE, chunk_path)
            assignments = (*assignments, *u32_fields(0x10, len(payload)),
                           *u32_fields(0x14, SOURCE))
        for offset, value in (*assignments, (8, code)):
            emulator.write_data(GLOBAL_BASE + offset, struct.pack("<H", value))
        self.ack = (self.ack + 1) & 0xFFFF
        emulator.write_data(STREAM_FLAG, struct.pack("<H", 3 if pathname is not None else 2))
        emulator.qmp.execute("cont")
        deadline = time.monotonic() + self.timeout
        while words(emulator, STREAM_FLAG, 2) != (0, self.ack):
            if emulator.process.poll() is not None:
                raise RuntimeError(f"QEMU exited during file command {code}")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"file command {code} timed out")
            time.sleep(0.05)
        result = read_updateall_return(emulator, code)
        length = words(emulator, GLOBAL_BASE + 0x10, 2)
        handle = words(emulator, GLOBAL_BASE + 0x852, 2)
        result.update(count=(length[0] << 16) | length[1],
                      handle=(handle[0] << 16) | handle[1], pathname=pathname)
        if pathname is not None:
            # Verify delivery independently of a successful filesystem result.
            size = (len(encode_path(pathname)) + 2) & ~1
            delivered = usb_data_to_physical_ram(data_memory(emulator, PATH_BUFFER, size))
            result["pathname_bytes"] = delivered.hex()
        self.index += 1
        self.records.append(result)
        self.journal.record("vendor_file_command", **result)
        if code not in (7, 8) or result["result"]:
            capture_diagnostics(emulator, self.report_dir / f"{self.index:04d}-cmd{code}.json",
                                command_result=result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        if pathname is not None and not delivered.startswith(encode_path(pathname) + b"\0"):
            raise RuntimeError("pathname did not reach the original guest near buffer intact")
        return result

    @staticmethod
    def require_success(result):
        if result["result"] != 0:
            raise RuntimeError(f"original file command failed: {result}")
        return result

    def read_chunk(self):
        result = self.require_success(self.command(7))
        count = result["count"]
        if not 0 <= count <= READ_SIZE:
            raise RuntimeError(f"invalid guest read length: {count}")
        if not count:
            return b""
        raw = data_memory(self.emulator, PATH_BUFFER, count + count % 2)
        return usb_data_to_physical_ram(raw)[:count]  # Lane exchange is involutive.


def verify_file(client, source: Path, destination: str):
    opened = client.require_success(client.command(5, pathname=destination))
    if not opened["handle"]:
        raise RuntimeError("reopen returned success without a file handle")
    read_hash = hashlib.sha256()
    received = 0
    with source.open("rb") as stream:
        while True:
            data = client.read_chunk()
            expected = stream.read(len(data)) if data else b""
            if data != expected:
                raise RuntimeError(f"guest file readback differs at chunk offset {received}")
            if not data:
                if stream.read(1):
                    raise RuntimeError(f"premature EOF after {received} bytes")
                break
            received += len(data)
            read_hash.update(data)
    client.require_success(client.command(10))
    return {"destination": destination, "read_bytes": received,
            "sha256": read_hash.hexdigest(), "guest_readback_verified": True}


def transfer_file(client, source: Path, destination: str):
    # Mode 0 (command 4) also truncates an existing file. Probe with mode 1
    # first and refuse overwrites; only original ENOENT (-10, -7) permits create.
    existing = client.command(5, pathname=destination)
    if existing["result"] == 0:
        client.require_success(client.command(10))
        raise FileExistsError(f"guest file already exists: {destination}")
    if (existing["result"], existing["detail"]) != (-10, -7):
        raise RuntimeError(f"cannot confirm missing destination: {existing}")
    opened = client.require_success(client.command(4, pathname=destination))
    if not opened["handle"]:
        raise RuntimeError("create returned success without a file handle")
    expected_hash = hashlib.sha256()
    count = 0
    with source.open("rb") as stream:
        while chunk := stream.read(READ_SIZE):
            result = client.require_success(client.command(8, payload=chunk))
            if result["count"] != len(chunk):
                raise RuntimeError(f"short guest write at {count}: {result}")
            count += len(chunk)
            expected_hash.update(chunk)
            if count % 0x40000 == 0:
                print(f"IMPORT {count}/{source.stat().st_size} bytes", flush=True)
    client.require_success(client.command(10))
    report = verify_file(client, source, destination)
    if report["read_bytes"] != count or expected_hash.hexdigest() != report["sha256"]:
        raise RuntimeError("guest file length/hash mismatch")
    return {**report, "written_bytes": count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("qemu", "soc-rom", "burn-code", "nand-checkpoint", "source", "report-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output", type=Path, help="new NAND checkpoint; required for import")
    parser.add_argument("--verify-only", action="store_true",
                        help="cold guest readback only; no file/directory creation or output NAND")
    parser.add_argument("--destination", required=True)
    parser.add_argument("--mkdir", action="append", default=[],
                        help="create this new guest directory first; existing/error is not silently ignored")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    for path in (args.destination, *args.mkdir):
        encode_path(path)
    if args.verify_only and (args.output is not None or args.mkdir):
        parser.error("--verify-only cannot create directories or output NAND")
    if not args.verify_only and args.output is None:
        parser.error("--output is required for import")
    if (args.output is not None and args.output.exists()) or args.report_dir.exists():
        parser.error("output and report directory must both be new")
    if not args.source.is_file() or not 0 < args.source.stat().st_size <= 0xFFFFFFFF:
        parser.error("source must be a nonempty file of at most uint32 size")
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    args.report_dir.mkdir(parents=True, exist_ok=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
    firmware = args.report_dir / "transport.prg"
    firmware.write_bytes(build_file_program()[0])
    identities = {}
    for name in ("qemu", "soc_rom", "burn_code", "nand_checkpoint", "source"):
        path = getattr(args, name)
        size, sha = artifact_identity(path)
        identities[name] = {"path": str(path.resolve()), "size": size, "sha256": sha}
    journal = RunJournal(args.report_dir / "process", kind="vendor-file-import", artifacts=identities)
    report = {"schema": "np560-vendor-file-import-v1", "artifacts": identities,
              "transport": "diagnostic RAM / original loader byte lanes",
              "usb_hardware_verified": False, "filesystem_host_writes": False,
              "verify_only": args.verify_only,
              "completed": False}
    emulator = None
    client = None
    try:
        emulator = Emulator(qemu=args.qemu, firmware=firmware, soc_rom=args.soc_rom,
                            soc_rom_skeleton=True, boot_mode="firmware-vma03",
                            burn_code=args.burn_code, nand_checkpoint=args.nand_checkpoint,
                            start_paused=True, journal=journal)
        emulator.qmp.execute("cont")
        wait_ready(emulator, args.timeout)
        if words(emulator, STREAM_FLAG + PROTOCOL_OFFSET, 1)[0] != STREAM_FILES_PROTOCOL:
            raise RuntimeError("invalid vendor transport protocol")
        VendorFiles.require_success(read_updateall_return(emulator, 23))
        client = VendorFiles(emulator, args.report_dir, journal, args.timeout)
        # Original command 1 mounts storage. Do not call 2/11/25/27 here:
        # inability to mount is an implementation failure, not permission to format.
        client.require_success(client.command(1, ((0x94, 2),)))
        for directory in args.mkdir:
            client.require_success(client.command(3, pathname=directory))
        report.update((verify_file if args.verify_only else transfer_file)(
            client, args.source, args.destination))
        if report["sha256"] != identities["source"]["sha256"]:
            raise RuntimeError("source content changed after input identity was recorded")
        emulator.qmp.execute("stop")
        capture_diagnostics(emulator, args.report_dir / "final.json")
        if args.output is not None:
            emulator.save_nand(args.output, timeout=120)
            size, sha = artifact_identity(args.output)
            report["output"] = {"path": str(args.output.resolve()), "size": size, "sha256": sha}
        report["completed"] = True
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        if emulator is not None:
            capture_diagnostics(emulator, args.report_dir / "failure.json", error=report["error"])
        raise
    finally:
        report["commands"] = client.records if client else []
        try:
            (args.report_dir / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        finally:
            if emulator is not None:
                emulator.close()


if __name__ == "__main__":
    main()
