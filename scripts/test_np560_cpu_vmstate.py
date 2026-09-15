#!/usr/bin/env python3
"""Link the production DMCU serializer to QEMU's existing VMState test libs.

Run in the Linux build environment. No guest, NAND, Web instance or alternate
serializer is used; this is not proof of whole-machine snapshot support.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import re
import struct
import tempfile
import time

from web.np560_web import Emulator, QMPClient, QMPError


def snapshot_boundary(qemu, baseline, output, snapshot_dir):
    """Show the old missing-CPU stream, then exercise the new safety boundary."""
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    firmware = output / "register-loop.prg"
    firmware.write_bytes(struct.pack("<3H", 0x68F0, 0xBEEF, 0xD0FF))
    snapshot = snapshot_dir / "old-incomplete.vmstate"
    report = {"scope": "no NAND image or journal; old snapshot is diagnostic",
              "qemu_sha256": hashlib.sha256(qemu.read_bytes()).hexdigest(),
              "baseline_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest()}
    old = Emulator(qemu=baseline, firmware=firmware, start_paused=True)
    report["old_pid"] = old.process.pid
    try:
        old.qmp.execute("cont")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            registers = old.qmp.hmp("info registers")
            if re.search(r"R0\s*=beef", registers):
                break
            time.sleep(.02)
        else:
            raise AssertionError("baseline did not execute register loop")
        old.qmp.execute("stop")
        report["old_before"] = old.qmp.hmp("info registers")
        old.qmp.execute("migrate", {"uri": f"file:{snapshot}"})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            progress = old.qmp.execute("query-migrate")
            if progress["status"] in ("completed", "failed", "cancelled"):
                break
            time.sleep(.05)
        assert progress["status"] == "completed", progress
        report["old_migration"] = progress
        report["old_stream_bytes"] = snapshot.stat().st_size
    finally:
        old.close()
        report["old_returncode"] = old.process.returncode
        (output / "machine-boundary-progress.json").write_text(
            json.dumps(report, indent=2) + "\n")

    # Cold-load the old file into the same old binary, with the vCPU paused.
    # This is deliberately a broken diagnostic snapshot, not a user save.
    with tempfile.TemporaryDirectory(prefix="np560-snapshot-") as temporary:
        socket = Path(temporary) / "restore.qmp"
        with (output / "old-restore.log").open("w") as log:
            process = subprocess.Popen([
                str(baseline), "-M", "np560", "-bios", str(firmware),
                "-incoming", f"file:{snapshot}", "-S", "-nographic",
                "-monitor", "none", "-qmp", f"unix:{socket},server=on,wait=off",
            ], stdout=log, stderr=subprocess.STDOUT)
            bridge = QMPClient(socket)
            report["old_restore_pid"] = process.pid
            try:
                bridge.connect()
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    status = bridge.execute("query-status")
                    if status["status"] != "inmigrate":
                        break
                    time.sleep(.02)
                assert status["status"] == "paused", status
                report["old_restored"] = bridge.hmp("info registers")
                assert re.search(r"R0\s*=0000", report["old_restored"])
                assert report["old_before"] != report["old_restored"]
            finally:
                if process.poll() is None:
                    try:
                        bridge.execute("quit")
                    except (QMPError, OSError):
                        process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                bridge.close()
                report["old_restore_returncode"] = process.returncode
                (output / "machine-boundary-progress.json").write_text(
                    json.dumps(report, indent=2) + "\n")

    current = Emulator(qemu=qemu, firmware=firmware, start_paused=True)
    report["new_pid"] = current.process.pid
    try:
        before = current.qmp.hmp("info registers")
        report["yank_instances_before"] = current.qmp.execute("query-yank")
        rejected_file = snapshot_dir / "must-not-exist.vmstate"
        try:
            current.qmp.execute("migrate", {"uri": f"file:{rejected_file}"})
        except QMPError as exc:
            report["migration_rejected"] = str(exc)
        else:
            raise AssertionError("incomplete machine migration was accepted")
        assert "whole-machine snapshot is not implemented" in report["migration_rejected"]
        assert not rejected_file.exists()
        report["savevm_rejected"] = current.qmp.hmp("savevm unavailable")
        assert "whole-machine snapshot is not implemented" in report["savevm_rejected"]
        fds = Path(f"/proc/{current.process.pid}/fd")
        before_fds = len(list(fds.iterdir()))
        for attempt in range(2):
            try:
                current.qmp.execute("xen-save-devices-state", {
                    "filename": str(snapshot_dir / f"rejected-device-{attempt}.state"),
                    "live": False,
                })
            except QMPError as exc:
                assert "IO error" in str(exc), exc
                report[f"device_save_rejected_{attempt}"] = str(exc)
            else:
                raise AssertionError("device-only save bypassed the guard")
        report["fd_count_before"] = before_fds
        report["fd_count_after_failed_saves"] = len(list(fds.iterdir()))
        assert report["fd_count_after_failed_saves"] == before_fds
        # This existing QMP loader reaches load_setup without -incoming;
        # a startup-only guard or outgoing blocker would not intercept it.
        try:
            current.qmp.execute("xen-load-devices-state", {"filename": str(snapshot)})
        except QMPError as exc:
            report["device_load_rejected"] = str(exc)
            assert "IO error" in str(exc), exc
        else:
            raise AssertionError("old incomplete state was accepted")
        assert current.qmp.hmp("info registers") == before
        report["yank_instances_after_failed_load"] = current.qmp.execute("query-yank")
        assert report["yank_instances_after_failed_load"] == report["yank_instances_before"]
        report["new_migration_status"] = current.qmp.execute("query-migrate")
    finally:
        current.close()
        report["new_returncode"] = current.process.returncode
        new_log = current.log_path.read_bytes()
        (output / "new-qemu.log").write_bytes(new_log)
        (output / "machine-boundary-progress.json").write_text(
            json.dumps(report, indent=2) + "\n")
    assert b"whole-machine restore is not implemented" in new_log
    assert b"Assertion" not in new_log
    for label, options in (("incoming", ["-incoming", "defer"]),
                           ("only_migratable", ["-only-migratable"])):
        result = subprocess.run([str(qemu), "-M", "np560", "-bios", str(firmware),
                                 "-nographic", "-monitor", "none", *options],
                                text=True, capture_output=True, timeout=10)
        report[label] = {"returncode": result.returncode, "stderr": result.stderr}
        assert result.returncode == 1 and "NP560+" in result.stderr
    assert report["old_returncode"] == report["old_restore_returncode"] == report["new_returncode"] == 0
    report["passed"] = True
    (output / "machine-boundary.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Old stream lost R0=BEEF on cold load; new save/load entry points reject it.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-qemu", type=Path)
    parser.add_argument("--snapshot-dir", type=Path)
    args = parser.parse_args()
    build = args.build.resolve()
    # Never report an integration result for a stale executable after a
    # failed or still-pending build.
    subprocess.run(["ninja", "-C", str(build), "qemu-system-dmcu",
                    "tests/unit/test-vmstate"], check=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).with_name("np560_cpu_vmstate_test.c").resolve()
    database = json.loads((build / "compile_commands.json").read_text())
    entry = next(e for e in database
                 if e["file"].endswith("/target/dmcu/machine.c"))
    command = shlex.split(entry["command"])
    production_object = (build / command[command.index("-o") + 1]).resolve()
    # Reuse the target's exact compiler configuration and replace only the
    # source/output/dependency paths. Do not compile or link a CPU stub.
    command[command.index("-c") + 1] = str(source)
    test_object = output / "test.o"
    command[command.index("-o") + 1] = str(test_object)
    for flag in ("-MF", "-MQ"):
        if flag in command:
            command[command.index(flag) + 1] = str(output / "test.d")
    subprocess.run(command, cwd=build, check=True)
    link_text = subprocess.check_output(
        ["ninja", "-t", "commands", "tests/unit/test-vmstate"],
        cwd=build, text=True).strip().splitlines()[-1]
    link = shlex.split(link_text)
    executable = output / "test-dmcu-vmstate"
    link[link.index("-o") + 1] = str(executable)
    original = "tests/unit/test-vmstate.p/test-vmstate.c.o"
    index = link.index(original)
    link[index:index + 1] = [str(test_object), str(production_object)]
    subprocess.run(link, cwd=build, check=True)
    result = subprocess.run([str(executable), "--tap"], cwd=build,
                            text=True, capture_output=True)
    (output / "test.log").write_text(result.stdout + result.stderr)
    (output / "report.json").write_text(json.dumps({
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "scope": "production CPU VMState serialization only, not whole VM",
        "production_object_sha256": hashlib.sha256(
            production_object.read_bytes()).hexdigest(),
        "commands": [command, link],
    }, indent=2) + "\n")
    print(result.stdout + result.stderr)
    if result.returncode == 0 and args.baseline_qemu:
        assert args.snapshot_dir, "--baseline-qemu requires --snapshot-dir"
        snapshot_boundary(build / "qemu-system-dmcu", args.baseline_qemu.resolve(),
                          output, args.snapshot_dir.resolve())
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
