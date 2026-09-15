#!/usr/bin/env python3
"""Check atomic journal compaction using real guest NAND commands.

Includes independent whole-affected-block data/OOB comparison, nonblank seed
pages, erase-to-FF, OOB crossing a block, copy-back, lock and I/O failures.
No full NAND copies or host writes to guest memory are made.
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
import os
import re
import struct
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from test_np560_dtu import write_word
from test_np560_nand_journal import command, finish_guest, property_value, reject_start
from web.np560_web import Emulator, RunJournal, artifact_identity

PD, PO, BP, PAGES = 2048, 64, 64, 262144
PATTERN = bytes.fromhex("00112233445566778899aabbccddeeff")
READS = ((0x101, 0, PATTERN),
         (0x101, 2046, bytes.fromhex("aabbddcc")),
         (0x13F, 2110, bytes(range(1, 9))),
         (0x141, 0, PATTERN),
         (0x141, 2046, bytes.fromhex("aabbddcc")),
         (0x142, 0, b"KEEP-SEED-PAGE"),
         (0x181, 0, b"\xff" * 16))


def make_program(path, writer):
    words = [0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 1]
    if writer:
        for addr, data in ((0x2400, PATTERN),
                           (0x2440, bytes.fromhex("aabbddcc")),
                           (0x2460, bytes(range(1, 9)))):
            for i in range(0, len(data), 2):
                write_word(words, addr + i, int.from_bytes(data[i:i+2], "little"))
        for _ in range(4):
            command(words, 3, 0x100)
            command(words, 2, 0x101)
            command(words, 2, 0x101, column=2046, buffer=0x2440, length=4)
            command(words, 2, 0x13F, column=2110, buffer=0x2460, length=8)
            command(words, 5, 0x101, buffer=0x141, length=2112)
            command(words, 2, 0x181, length=4)
            command(words, 3, 0x180)
    for i, (page, col, data) in enumerate(READS):
        command(words, 1, page, col, 0x4000 + i * 0x40, len(data))
    final = f"PC=20:{len(words) * 2:04x}"
    words.append(0xD0FF)
    path.write_bytes(struct.pack(f"<{len(words)}H", *words))
    return final


def check_reads(emu):
    result = []
    for i, (_, _, expected) in enumerate(READS):
        actual = base64.b64decode(emu.snapshot(
            "data", 0x4000 + i * 0x40, len(expected))["frame"])
        assert actual == expected, (i, expected.hex(), actual.hex())
        result.append(actual.hex())
    return result


CRC_TABLE = []
for _byte in range(256):
    _crc = _byte
    for _bit in range(8):
        _crc = (_crc >> 1) ^ (0x82F63B78 if _crc & 1 else 0)
    CRC_TABLE.append(_crc)


def crc32c(data):
    crc = 0xFFFFFFFF
    for byte in data:
        crc = CRC_TABLE[(crc ^ byte) & 255] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def journal_blocks(raw):
    assert raw[:8] == b"NP560J1\0"
    assert struct.unpack_from("<5I", raw, 8) == (1, PD, PO, PAGES, BP)
    blocks, offset, expected = {}, 64, 1
    while offset < len(raw):
        record = raw[offset:offset+32]
        assert len(record) == 32
        magic, op, seq, page, col, length, crc = struct.unpack("<4sIQIIII", record)
        assert magic == b"NJR1" and seq == expected and page < PAGES
        data = raw[offset+32:offset+32+length]
        assert len(data) == length and crc32c(record[:28] + data) == crc
        last = page
        if op == 1:
            assert col < PD and length <= PD + PO - col
        elif op == 2:
            assert PD <= col <= PD + 4 * PO and length <= PD + 4 * PO - col
            if length:
                last += (col - PD + length - 1) // PO
            assert last < PAGES
        else:
            assert op == 3 and page % BP == 0 and col == length == 0
        for block in range(page // BP, last // BP + 1):
            blocks.setdefault(block, []).append((op, page, col, data))
        offset += 32 + length
        expected += 1
    assert offset == len(raw)
    return blocks


def replay_block(seed, block, operations, checkpoint):
    # Each block is two planes, not interleaved pages. Only a single block
    # at a time is materialized, even for a complete native 512 MiB seed.
    seed.seek((64 if checkpoint else 0) + block * BP * PD)
    data = bytearray(seed.read(BP * PD).ljust(BP * PD, b"\xff"))
    if checkpoint:
        seed.seek(64 + PAGES * PD + block * BP * PO)
        oob = bytearray(seed.read(BP * PO))
        assert len(oob) == BP * PO
    else:
        oob = bytearray(b"\xff" * (BP * PO))
    for op, page, col, payload in operations:
        if op == 3:
            data[:] = b"\xff" * len(data)
            oob[:] = b"\xff" * len(oob)
            continue
        for i, byte in enumerate(payload):
            if op == 1 and col + i < PD:
                data[(page - block * BP) * PD + col + i] &= byte
            else:
                position = (page - block * BP) * PO + col - PD + i
                if 0 <= position < len(oob):
                    oob[position] &= byte
    return data + oob


def compare_media(seed_path, before, after, *, checkpoint=False):
    assert before[:64] == after[:64], "immutable base identity changed"
    left, right = journal_blocks(before), journal_blocks(after)
    results = {}
    with seed_path.open("rb") as seed:
        for block in sorted(left.keys() | right.keys()):
            old = replay_block(seed, block, left.get(block, []), checkpoint)
            new = replay_block(seed, block, right.get(block, []), checkpoint)
            assert old == new, f"data/OOB differ in complete block {block:x}"
            results[f"{block:x}"] = hashlib.sha256(old).hexdigest()
    return results


def compact(emu):
    emu.qmp.execute("qom-set", {
        "path": "/machine", "property": "nand-journal-compact", "value": True,
    }, timeout=30)


def failed_compaction(qemu, out, seed, reader, rf, original):
    import resource
    import signal

    path = out / "failed.npj"
    path.write_bytes(original)
    popen = subprocess.Popen

    def limited_popen(*args, **kwargs):
        prior = kwargs.pop("preexec_fn", None)

        def prepare():
            if prior:
                prior()
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
            _, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
            resource.setrlimit(resource.RLIMIT_FSIZE, (256, hard))

        return popen(*args, preexec_fn=prepare, **kwargs)

    with patch("web.np560_web.subprocess.Popen", side_effect=limited_popen):
        emu = Emulator(qemu, reader, nand_image=seed, nand_journal=path,
                       start_paused=True)
    try:
        try:
            compact(emu)
        except Exception as exc:
            assert "compaction failed" in str(exc), str(exc)
            error = str(exc)
        else:
            raise AssertionError("EFBIG compaction unexpectedly succeeded")
        assert path.read_bytes() == original
        assert not list(out.glob("failed.npj.compact.*"))
        assert property_value(emu, "nand-journal-state").startswith("durable ")
        finish_guest(emu, rf)
        check_reads(emu)
        return {"error": error, "old_log_unchanged": True,
                "temporary_removed": True, "prior_data_readable": True}
    finally:
        emu.close()


def publication_faults(args, out, seed, writer, wf, reader, rf, original, after):
    results = []
    for mode in ("before-rename", "after-rename", "directory-sync-error"):
        path = out / f"{mode}.npj"
        path.write_bytes(original)
        popen = subprocess.Popen

        def fault_popen(*argv, **kwargs):
            env = dict(os.environ)
            env.update(LD_PRELOAD=str(args.fault_shim.resolve()),
                       NP560_FAULT_JOURNAL=str(path), NP560_FAULT_MODE=mode)
            return popen(*argv, env=env, **kwargs)

        with patch("web.np560_web.subprocess.Popen", side_effect=fault_popen):
            emu = Emulator(args.qemu, writer, nand_image=seed, nand_journal=path,
                           start_paused=True)
        result = {"mode": mode, "pid": emu.process.pid}
        try:
            if mode == "directory-sync-error":
                try:
                    compact(emu)
                except Exception as exc:
                    assert "compaction failed" in str(exc), str(exc)
                    result["error"] = str(exc)
                else:
                    raise AssertionError("post-publication sync error not reported")
                assert property_value(emu, "nand-journal-state").startswith("failed ")
                finish_guest(emu, wf)
                check_reads(emu)
                nand = property_value(emu, "nand-state")
                for counter in ("PROGRAMS", "ERASES", "COPIES"):
                    assert re.search(rf"\b{counter}=0\b", nand), nand
                result["subsequent_mutations_refused"] = True
            else:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(compact, emu)
                    try:
                        deadline = time.monotonic() + 10
                        status = Path(f"/proc/{emu.process.pid}/status")
                        while time.monotonic() < deadline:
                            if re.search(r"^State:\s+T\b", status.read_text(), re.M):
                                result["observed_stopped_at_boundary"] = True
                                break
                            if emu.process.poll() is not None or future.done():
                                raise AssertionError("fault boundary was not reached")
                            time.sleep(0.01)
                        else:
                            raise AssertionError("timed out waiting for the owned SIGSTOP")
                    finally:
                        emu.process.kill()
                        result["exit"] = emu.process.wait(timeout=10)
                    try:
                        future.result(timeout=5)
                    except Exception as exc:
                        result["qmp_interruption"] = str(exc)
            expected = original if mode == "before-rename" else after
            assert path.read_bytes() == expected
            result["visible_log"] = "old" if mode == "before-rename" else "new"
        finally:
            emu.close()
            result["exit"] = emu.process.returncode
        # The new process has no preload/fault environment and must read the
        # committed original or replacement, never a temporary filename.
        emu = Emulator(args.qemu, reader, nand_image=seed, nand_journal=path,
                       start_paused=True)
        try:
            finish_guest(emu, rf)
            result["cold_reads"] = check_reads(emu)
        finally:
            emu.close()
            result["reader_exit"] = emu.process.returncode
        results.append(result)
    return results


def native_compaction(args, out):
    """Compact a COPY of an existing native log, then boot the original OS.

    One guest erase of a proven already-erased block triggers the normal size
    threshold. It changes no NAND bytes; independent replay checks every block
    touched by either history. This does not manufacture an application save.
    """
    from probe_np560_checkpoint_boot import assess, save_snapshot
    from verify_np560_toolbar_frames import expected_from_package

    report = {"passed": False, "host_guest_memory_writes": 0,
              "full_nand_exports": 0, "injected_keys": 0, "artifacts": {}}
    for name in ("qemu", "native_seed", "native_journal", "firmware", "soc_rom", "package"):
        path = getattr(args, name).resolve()
        size, digest = artifact_identity(path)
        report["artifacts"][name] = {"path": str(path), "size": size, "sha256": digest}
    original = args.native_journal.read_bytes()
    assert len(original) >= 16 * 1024 * 1024, "native log must reach automatic threshold"
    blocks = journal_blocks(original)
    erased = b"\xff" * (BP * (PD + PO))
    with args.native_seed.open("rb") as seed:
        assert seed.read(8) == b"NP560N1\0"
        for block in reversed(range(PAGES // BP)):
            if replay_block(seed, block, blocks.get(block, []), True) == erased:
                break
        else:
            raise AssertionError("no already-erased block available")
    report["unchanged_erase_block"] = block
    path = out / "device.npj"
    path.write_bytes(original)
    words = [0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 1]
    command(words, 3, block * BP)
    final = f"PC=20:{2 * len(words):04x}"
    words.append(0xD0FF)
    probe = out / "unchanged-erase.prg"
    probe.write_bytes(struct.pack(f"<{len(words)}H", *words))
    try:
        emu = Emulator(args.qemu, probe, nand_checkpoint=args.native_seed,
                       nand_journal=path, start_paused=True,
                       journal=RunJournal(out / "auto-process"))
        try:
            report["auto_pid"] = emu.process.pid
            report["before"] = property_value(emu, "nand-journal-maintenance")
            finish_guest(emu, final)
            after = path.read_bytes()
            report["after"] = property_value(emu, "nand-journal-maintenance")
            assert "COMPACTIONS=1" in report["after"], report["after"]
            report["equivalent_blocks"] = compare_media(
                args.native_seed, original, after, checkpoint=True)
            report["bytes_before"], report["bytes_after"] = len(original), len(after)
            report["compacted_sha256"] = hashlib.sha256(after).hexdigest()
            print(f"native auto compaction: {len(original)} -> {len(after)} bytes; "
                  f"{len(report['equivalent_blocks'])} complete blocks identical", flush=True)
            emu.process.kill()
            report["auto_exit"] = emu.process.wait(timeout=10)
            assert report["auto_exit"] == -9
        finally:
            emu.close()

        expected, _ = expected_from_package(args.package)
        emu = Emulator(args.qemu, args.firmware, soc_rom=args.soc_rom,
                       soc_rom_skeleton=True, boot_mode="firmware-vma03",
                       nand_checkpoint=args.native_seed, nand_journal=path,
                       start_paused=True, journal=RunJournal(out / "native-process"))
        try:
            report["native_pid"] = emu.process.pid
            emu.qmp.execute("cont")
            start, stable, last_print = time.monotonic(), 0, -15
            while time.monotonic() - start < 150:
                snapshot = emu.snapshot("lcd", 0, 0)
                result = assess(snapshot, expected[1])
                stable = stable + 1 if result["passed"] else 0
                elapsed = time.monotonic() - start
                if elapsed - last_print >= 15:
                    print(f"native boot {elapsed:.1f}s: "
                          f"{result['toolbar']['mismatch_pixels']}/5280 pixels differ", flush=True)
                    last_print = elapsed
                if stable >= 3:
                    break
                time.sleep(1)
            save_snapshot(out, "native-desktop", snapshot)
            report["native_desktop"] = result
            assert stable >= 3, result
            config = base64.b64decode(emu.snapshot("data", 0x50B87A, 2)["frame"])
            report["native_sound_off"] = int.from_bytes(config, "little")
            assert report["native_sound_off"] == 1, report["native_sound_off"]
            report["native_journal"] = property_value(emu, "nand-journal-state")
            assert re.search(r"\bERROR=0\b", snapshot["nand_state"])
        finally:
            emu.close()
            report["native_exit"] = emu.process.returncode
        for name in ("native_seed", "native_journal"):
            size, digest = artifact_identity(getattr(args, name))
            assert digest == report["artifacts"][name]["sha256"]
        report["inputs_unchanged"] = True
        report["passed"] = True
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"native journal compaction passed: {out / 'report.json'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--native-only", action="store_true")
    parser.add_argument("--fault-shim", type=Path)
    for name in ("native-seed", "native-journal", "firmware", "soc-rom", "package"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.native_only and not all(getattr(args, name) for name in
            ("native_seed", "native_journal", "firmware", "soc_rom", "package")):
        parser.error("native mode needs seed, journal, original firmware, ROM and package")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if args.native_only:
        native_compaction(args, out)
        return
    seed = out / "nonblank-seed.bin"
    data = bytearray(b"\xff" * (0x182 * PD))
    data[0x142 * PD:0x142 * PD+14] = b"KEEP-SEED-PAGE"
    data[0x181 * PD:0x181 * PD+16] = b"ERASE-THIS-PAGE!"
    seed.write_bytes(data)
    seed_hash = hashlib.sha256(data).hexdigest()
    writer, reader, path = out / "writer.prg", out / "reader.prg", out / "medium.npj"
    wf, rf = make_program(writer, True), make_program(reader, False)
    report = {"passed": False, "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
              "host_guest_memory_writes": 0, "full_nand_exports": 0}
    try:
        emu = Emulator(args.qemu, writer, nand_image=seed, nand_journal=path,
                       start_paused=True)
        try:
            finish_guest(emu, wf)
            report["live_reads"] = check_reads(emu)
            original = path.read_bytes()
            (out / "before.npj").write_bytes(original)
            nand_before = property_value(emu, "nand-state")
            compact(emu)
            try:
                after = path.read_bytes()
            except OSError as exc:
                report["publication_error"] = str(exc)
                report["publication_files"] = [str(p) for p in out.iterdir()]
                report["publication_fds"] = {
                    str(p): os.readlink(p)
                    for p in Path(f"/proc/{emu.process.pid}/fd").iterdir()
                }
                report["publication_maintenance"] = property_value(
                    emu, "nand-journal-maintenance")
                raise
            assert len(after) < len(original), (len(original), len(after))
            assert property_value(emu, "nand-state") == nand_before
            report["blocks"] = compare_media(seed, original, after)
            report["bytes_before"], report["bytes_after"] = len(original), len(after)
            report["maintenance"] = property_value(emu, "nand-journal-maintenance")
            report["lock"] = reject_start(args.qemu, reader, path,
                "locked by another process", out, "lock-after-rename", seed)
            try:
                emu.qmp.execute("qom-set", {"path": "/machine", "property": "nand-save",
                                           "value": str(path) + ".lock"})
            except Exception as exc:
                assert "must not overwrite" in str(exc), str(exc)
            else:
                raise AssertionError("active sidecar lock could be overwritten")
            alias = out / "hardlink.npj"
            os.link(path, alias)
            try:
                try:
                    compact(emu)
                except Exception as exc:
                    assert "hard links" in str(exc), str(exc)
                else:
                    raise AssertionError("hardlinked journal was replaced")
                assert path.read_bytes() == after == alias.read_bytes()
            finally:
                alias.unlink()
            compact(emu)
            assert path.read_bytes() == after, "already compact log was rewritten"
            emu.qmp.execute("system_reset")
            finish_guest(emu, wf)
            assert path.stat().st_size > len(after)
            report["same_process_append_blocks"] = compare_media(
                seed, original, path.read_bytes())
            compact(emu)
            assert path.read_bytes() == after
            emu.process.kill()
            report["writer_exit"] = emu.process.wait(timeout=10)
            assert report["writer_exit"] == -9
        finally:
            emu.close()
        emu = Emulator(args.qemu, reader, nand_image=seed, nand_journal=path,
                       start_paused=True)
        try:
            finish_guest(emu, rf)
            report["cold_reads"] = check_reads(emu)
        finally:
            emu.close()
            report["reader_exit"] = emu.process.returncode
        # Further normal writes must append to the replacement, not the old
        # unlinked inode. Re-run the guest writer against the compacted log.
        emu = Emulator(args.qemu, writer, nand_image=seed, nand_journal=path,
                       start_paused=True)
        try:
            finish_guest(emu, wf)
            report["append_blocks"] = compare_media(seed, original, path.read_bytes())
            compact(emu)
            assert path.read_bytes() == after
        finally:
            emu.close()
        report["io_failure"] = failed_compaction(args.qemu, out, seed, reader, rf, original)
        if args.fault_shim:
            report["publication_faults"] = publication_faults(
                args, out, seed, writer, wf, reader, rf, original, after)
        assert hashlib.sha256(seed.read_bytes()).hexdigest() == seed_hash
        report["seed_unchanged"] = True
        report["passed"] = True
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"journal compaction passed: {out / 'report.json'}", flush=True)


if __name__ == "__main__":
    main()
