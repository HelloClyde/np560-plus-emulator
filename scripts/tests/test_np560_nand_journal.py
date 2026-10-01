#!/usr/bin/env python3
"""NAND durability after SIGKILL, using only guest controller transactions.

No full-size NAND output is created. Diagnostic programs operate on a blank
medium; this does not replace native application save/readback validation.
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
import hashlib
import json
import re
import struct
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

from test_np560_dtu import read_word, write_word
from web.np560_web import Emulator

PATTERN = bytes.fromhex("00112233445566778899aabbccddeeff")
MASKED = bytes(x & 0xF0 for x in PATTERN)


def command(words, op, page, column=0, buffer=0x2400, length=16):
    for offset, value in ((4, page >> 16), (6, page & 65535),
                          (8, column), (10, buffer >> 16),
                          (12, buffer & 65535), (14, length), (0, op)):
        write_word(words, 0xF300 + offset, value)


def program(path, writer, *, read_after_failure=False):
    words = [0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 1]
    if writer:
        for addr, data in ((0x2400, PATTERN), (0x2420, b"\xF0" * 16),
                           (0x2440, bytes.fromhex("aabbddcc")),
                           (0x2460, bytes(range(1, 9)))):
            for i in range(0, len(data), 2):
                write_word(words, addr + i, int.from_bytes(data[i:i+2], "little"))
        for page in (0x100, 0x140, 0x180):
            command(words, 3, page)
        command(words, 2, 0x101)
        command(words, 2, 0x101, buffer=0x2420)
        command(words, 2, 0x101, column=2046, buffer=0x2440, length=4)
        command(words, 2, 0x102, column=2110, buffer=0x2460, length=8)
        command(words, 5, 0x101, buffer=0x141, length=2112)
        command(words, 2, 0x181, length=4)
        command(words, 3, 0x180)
        # The second erase changes no bytes. It must still report success to
        # the guest without forcing another durable journal record.
        command(words, 3, 0x180)
        # OOB alone makes a block non-erased. Its erase must be journaled even
        # though all ordinary data bytes are still FF.
        command(words, 2, 0x1c0, column=2110, buffer=0x2460, length=8)
        command(words, 3, 0x1c0)
    if read_after_failure:
        # Preserve the failed command status in guest registers before reads
        # clear the controller latch. No host register/RAM injection is used.
        # write_word() uses R0 while issuing the later read commands.
        read_word(words, 0xF302, 2)
        read_word(words, 0xF31E, 3)
    if not writer or read_after_failure:
        for page, col, dest, length in ((0x101, 0, 0x4000, 16),
                                        (0x101, 2046, 0x4020, 4),
                                        (0x102, 2110, 0x4040, 8),
                                        (0x141, 0, 0x4060, 16),
                                        (0x141, 2046, 0x4080, 4),
                (0x181, 0, 0x40A0, 4),
                (0x1c0, 2110, 0x40C0, 8)):
            command(words, 1, page, col, dest, length)
    final = f"PC=20:{2 * len(words):04x}"
    words.append(0xD0FF)
    path.write_bytes(struct.pack(f"<{len(words)}H", *words))
    return final


def property_value(emu, name):
    return emu.qmp.execute("qom-get", {"path": "/machine", "property": name})


def finish_guest(emu, final):
    emu.qmp.execute("cont")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = property_value(emu, "cpu-state")
        if final in state or "UNSUPPORTED=none" not in state:
            break
        time.sleep(0.02)
    emu.qmp.execute("stop")
    state = property_value(emu, "cpu-state")
    assert final in state, state[:2000]
    assert all(f"{s}=none" in state for s in
               ("UNSUPPORTED", "INVALID_CONTROL", "ROM_MISSING")), state[:2000]
    return state


def verify_reader(emu):
    checks = []
    for address, expected in ((0x4000, MASKED),
                               (0x4020, bytes.fromhex("aabbddcc")),
                               (0x4040, bytes(range(1, 9))),
                               (0x4060, MASKED),
                               (0x4080, bytes.fromhex("aabbddcc")),
                               (0x40A0, b"\xFF" * 4),
                               (0x40C0, b"\xFF" * 8)):
        actual = base64.b64decode(emu.snapshot("data", address, len(expected))["frame"])
        checks.append({"address": address, "expected": expected.hex(),
                       "actual": actual.hex(), "passed": actual == expected})
    return checks


def reject_start(qemu, reader, journal, text, directory, name, image=None):
    before = journal.read_bytes()
    options = f"np560,nand-journal={journal}"
    if image is not None:
        options += f",nand-image={image}"
    result = subprocess.run([str(qemu), "-M", options, "-bios", str(reader),
                             "-nographic", "-monitor", "none", "-S"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=20)
    output = result.stdout.decode("utf-8", errors="replace")
    (directory / f"{name}.log").write_text(output)
    assert result.returncode != 0 and text in output, output
    assert journal.read_bytes() == before, "rejected journal was modified"
    return {"name": name, "exit_code": result.returncode, "unchanged": True}


def verify_io_failure(qemu, out, original, reader, final_reader):
    """Force a real EFBIG write error in only this owned QEMU, not a full disk.

    Seed the previous committed state, then allow only a partial record header.
    All subsequent program/OOB/copy/erase attempts must be refused, while guest
    reads still see the previously committed data in the live process.
    """
    import resource
    import signal

    path = out / "io-failure.npj"
    path.write_bytes(original)
    firmware = out / "io-failure.prg"
    final = program(firmware, True, read_after_failure=True)
    popen = subprocess.Popen

    def limit_child_file_size():
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        _, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
        resource.setrlimit(resource.RLIMIT_FSIZE, (len(original) + 16, hard))

    def limited_popen(*args, **kwargs):
        original_preexec = kwargs.pop("preexec_fn", None)

        def prepare_child():
            if original_preexec is not None:
                original_preexec()
            limit_child_file_size()

        return popen(*args, preexec_fn=prepare_child, **kwargs)

    with patch("web.np560_web.subprocess.Popen", side_effect=limited_popen):
        emu = Emulator(qemu=qemu, firmware=firmware, start_paused=True,
                       nand_journal=path)
    try:
        cpu = finish_guest(emu, final)
        (out / "io-failure.cpu.txt").write_text(cpu)
        assert re.search(r"\bR2\s*=0000\b", cpu), cpu[:1600]
        assert re.search(r"\bR3\s*=0005\b", cpu), cpu[:1600]
        state = property_value(emu, "nand-journal-state")
        assert state == "failed SEQUENCE=9 REPLAYED=9 TORN_BYTES=0 NOOP_ERASES=0", state
        checks = verify_reader(emu)
        assert all(c["passed"] for c in checks), checks
        nand = property_value(emu, "nand-state")
        for name in ("PROGRAMS", "ERASES", "COPIES"):
            assert re.search(rf"\b{name}=0\b", nand), nand
        assert path.stat().st_size == len(original) + 16
        result = {"error": "EFBIG", "failed_state": state,
                  "guest_status": 0, "guest_error": 5,
                  "live_checks": checks, "nand_state": nand}
    finally:
        emu.close()
    emu = Emulator(qemu=qemu, firmware=reader, start_paused=True,
                   nand_journal=path)
    try:
        finish_guest(emu, final_reader)
        assert all(c["passed"] for c in verify_reader(emu))
        result["reopened_state"] = property_value(emu, "nand-journal-state")
        assert "TORN_BYTES=16" in result["reopened_state"]
        assert path.read_bytes() == original
    finally:
        emu.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--without-journal", action="store_true",
                        help="reproduce loss on the prior core, expected failure")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    writer, reader = out / "writer.prg", out / "reader.prg"
    wf, rf = program(writer, True), program(reader, False)
    log = out / "medium.npj"
    journal = None if args.without_journal else log
    report = {"passed": False, "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
              "host_guest_memory_writes": 0, "checkpoint_exports": 0,
              "rejections": [], "recovery": []}
    try:
        emu = Emulator(qemu=args.qemu, firmware=writer, start_paused=True,
                       nand_journal=journal)
        try:
            report["writer_pid"] = emu.process.pid
            (out / "writer.cpu.txt").write_text(finish_guest(emu, wf))
            report["writer_nand"] = property_value(emu, "nand-state")
            if journal:
                report["writer_journal"] = property_value(emu, "nand-journal-state")
                assert "SEQUENCE=9" in report["writer_journal"]
                assert "NOOP_ERASES=4" in report["writer_journal"]
                report["rejections"].append(reject_start(
                    args.qemu, reader, log, "locked by another process", out, "exclusive-lock"))
                for prop, value in (("nand-journal", ""),
                                     ("nand-checkpoint", "changed"),
                                     ("nand-save", str(log))):
                    try:
                        emu.qmp.execute("qom-set", {"path": "/machine", "property": prop,
                                                    "value": value})
                    except Exception as exc:
                        assert any(t in str(exc) for t in
                                   ("before startup", "active NAND journal base", "must not overwrite"))
                    else:
                        raise AssertionError(f"unsafe {prop} was accepted")
            # Deliberately kill this owned QEMU without QMP quit or export.
            emu.process.kill()
            report["writer_exit"] = emu.process.wait(timeout=10)
            assert report["writer_exit"] == -9
        finally:
            emu.close()

        emu = Emulator(qemu=args.qemu, firmware=reader, start_paused=True,
                       nand_journal=journal)
        try:
            (out / "reader.cpu.txt").write_text(finish_guest(emu, rf))
            report["checks"] = verify_reader(emu)
            if journal:
                report["reader_journal"] = property_value(emu, "nand-journal-state")
                assert "REPLAYED=9" in report["reader_journal"]
            assert all(c["passed"] for c in report["checks"]), report["checks"]
        finally:
            emu.close()
            report["reader_exit"] = emu.process.returncode

        original = log.read_bytes()
        assert len(original) == 2520, len(original)
        report["journal_bytes"] = len(original)
        bad_base = out / "different-seed.bin"
        bad_base.write_bytes(b"BASE")
        report["rejections"].append(reject_start(
            args.qemu, reader, log, "header/base SHA-256 mismatch", out, "wrong-base", bad_base))
        for name, offset, changed, error in (
            ("checksum", 64 + 28, None, "checksum error"),
            ("sequence", 64 + 8, 2, "invalid record"),
            ("range", 64 + 16, 0x40000, "invalid record"),
        ):
            corrupted = bytearray(original)
            if changed is None:
                corrupted[offset] ^= 1
            else:
                struct.pack_into("<I", corrupted, offset, changed)
            path = out / f"bad-{name}.npj"
            path.write_bytes(corrupted)
            report["rejections"].append(reject_start(
                args.qemu, reader, path, error, out, name))
        partial = struct.pack("<4sIQIIII", b"NJR1", 1, 10, 0x101, 0, 16, 0)
        for name, tail in (("short-header", b"NJR"), ("short-payload", partial + b"1234")):
            path = out / f"torn-{name}.npj"
            path.write_bytes(original + tail)
            emu = Emulator(qemu=args.qemu, firmware=reader, start_paused=True,
                           nand_journal=path)
            try:
                finish_guest(emu, rf)
                assert all(c["passed"] for c in verify_reader(emu))
                state = property_value(emu, "nand-journal-state")
                assert f"TORN_BYTES={len(tail)}" in state, state
                assert path.read_bytes() == original
                report["recovery"].append({"name": name, "state": state})
            finally:
                emu.close()
        report["io_failure"] = verify_io_failure(args.qemu, out, original, reader, rf)
        report["passed"] = True
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"durable guest NAND passed: {out / 'report.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
