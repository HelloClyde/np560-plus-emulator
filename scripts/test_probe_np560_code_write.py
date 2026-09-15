#!/usr/bin/env python3
"""Positive control: a diagnostic guest must trip the host RAM write watch."""
from __future__ import annotations

import argparse
import base64
import json
import struct
import tempfile
import time
from pathlib import Path

from probe_np560_code_write import HostWatch, WriteObserved
from web.np560_web import Emulator, artifact_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    size, digest = artifact_identity(args.qemu)
    result = {"passed": False, "qemu_sha256": digest, "qemu_size": size,
              "host_guest_memory_writes": 0, "nand_used": False}
    with tempfile.TemporaryDirectory(prefix="np560-code-watch-positive-") as directory:
        firmware = Path(directory) / "write.prg"
        # DS0=44 maps [1840] to physical 22:1840. Only this guest MOV writes
        # the watched word; there are no debug-memory writes or real firmware.
        firmware.write_bytes(struct.pack("<7H", 0x6810, 0x44, 0x68F0, 0x1234,
                                        0xA8F0, 0x1840, 0xD0FF))
        emulator = Emulator(qemu=args.qemu, firmware=firmware, start_paused=True)
        watch = None
        try:
            result["owned_qemu_pid"] = emulator.process.pid
            watch = HostWatch(args.qemu, emulator.process.pid, 0x221840, args.output)
            watch.ready()
            emulator.qmp.execute("cont")
            deadline = time.monotonic() + 10
            observed = False
            while time.monotonic() < deadline:
                try:
                    watch.check()
                except WriteObserved:
                    observed = True
                    break
                time.sleep(0.05)
            assert observed, watch.text()
            log = watch.text()
            assert "WATCH_HIT guest_address=0x221840 value=1234" in log, log
            assert "writer_pc=200008" in log, log
            emulator.qmp.execute("stop")
            snapshot = emulator.snapshot("data", 0x221840, 2)
            assert base64.b64decode(snapshot["frame"]) == b"\x34\x12", snapshot
            result["passed"] = True
            print("Positive control passed: guest MOV at 20:0008 captured writing 1234 to 22:1840")
        finally:
            if watch:
                watch.close()
                result["gdb_exit_code"] = watch.process.returncode
            emulator.close()
            result["qemu_exit_code"] = emulator.process.returncode
            (args.output / "report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
