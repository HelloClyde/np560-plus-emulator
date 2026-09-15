#!/usr/bin/env python3
"""Capture the first host RAM write to a specified guest code word.

Owns an isolated, non-persisting QEMU and attaches host GDB before guest boot.
No guest memory writes, software breakpoints or ROM interception. A bounded
normal matrix route is optional; no-write observations do not prove a fix.
"""
from __future__ import annotations

import argparse
import json
import re
import signal
import subprocess
import time
from pathlib import Path

from probe_np560_checkpoint_boot import assess, save_snapshot
from probe_np560_matrix_route import matrix_masks, parse_step, replay_step
from verify_np560_toolbar_frames import expected_from_package
from web.np560_web import Emulator, RunJournal, artifact_identity


class WriteObserved(RuntimeError):
    pass


class HostWatch:
    def __init__(self, qemu, pid, address, output):
        self.path = output / "host-watch.log"
        self.log = self.path.open("x", encoding="utf-8")
        self.process = subprocess.Popen(
            ["gdb", "-q", "-nx", str(qemu)], stdin=subprocess.PIPE,
            stdout=self.log, stderr=subprocess.STDOUT, text=True)
        commands = f"""set pagination off
set confirm off
set max-value-size unlimited
attach {pid}
set $np = (NP560MachineState *)current_machine
set $env = &$np->cpu->env
set $watched = (unsigned short *)($np->data.ram_block->host + {address})
watch -l *$watched
commands
silent
printf "WATCH_HIT guest_address={address:#x} value=%04x\\n", *$watched
printf "guest_pc=%06x writer_pc=%06x completed_pc=%06x completed_next=%06x\\n", $env->pc, $env->current_instruction_pc, $env->completed_instruction_pc, $env->completed_instruction_next_pc
p/x $env->gpr
printf "SOCR=%04x DS0=%04x DS1=%04x IGNDS=%u CRIT=%u IN_INTERRUPT=%u REPEAT=%u\\n", $env->sfr[0], $env->sfr[16], $env->sfr[17], $env->ignore_ds_count, $env->critical_count, $env->in_interrupt, $env->repeat_count
x/32hx $watched-8
bt 32
detach
quit
end
printf "WATCH_READY guest_address={address:#x} value=%04x\\n", *$watched
continue
"""
        self.process.stdin.write(commands)
        self.process.stdin.flush()

    def text(self):
        return self.path.read_text(encoding="utf-8", errors="replace")

    def check(self):
        if self.process.poll() is not None:
            if "WATCH_HIT guest_address=" in self.text():
                raise WriteObserved("first RAM write captured by host hardware watchpoint")
            raise RuntimeError("host debugger exited without a captured write")

    def ready(self):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            self.check()
            content = self.text()
            if "WATCH_READY guest_address=" in content and "Continuing." in content:
                if "Hardware watchpoint" not in content:
                    raise RuntimeError("GDB did not install a hardware watchpoint")
                return
            time.sleep(0.05)
        raise TimeoutError("host write watchpoint did not arm")

    def close(self):
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)
            try:
                self.process.stdin.write("detach\nquit\n")
                self.process.stdin.flush()
                self.process.wait(timeout=5)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        self.process.stdin.close()
        self.log.close()


class LocalMatrixBridge:
    """Reuse the normal matrix route checks without opening a Web port."""
    def __init__(self, emulator, watch):
        self.emulator, self.watch = emulator, watch

    def get_json(self, endpoint):
        self.watch.check()
        if endpoint == "/api/key-status":
            return self.emulator.key_status()
        if endpoint in ("/api/state", "/api/diagnostics"):
            return self.emulator.snapshot("lcd", 0, 0)
        raise ValueError(endpoint)

    def set_matrix(self, index):
        self.watch.check()
        low, high = (0, 0) if index is None else matrix_masks(index)
        self.emulator.set_key(0, 0, low, high)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("qemu", "firmware", "soc-rom", "nand-checkpoint", "package", "output"):
        parser.add_argument("--" + flag, type=Path, required=True)
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0x221840)
    parser.add_argument("--boot-timeout", type=float, default=150)
    parser.add_argument("--post-route-seconds", type=float, default=8,
                        help="Observe pending guest work after the final key (0..30 seconds)")
    parser.add_argument("--pre-route-ticks", type=int, default=0,
                        help="Wait for the saved IRQ64.TICKS boot age before any keys (0..20000)")
    parser.add_argument("--step", type=parse_step, action="append", default=[])
    args = parser.parse_args()
    if not 0 <= args.address <= 0xFFFFFE or args.address & 1:
        parser.error("address must be an aligned word in physical data RAM")
    if not 0 < args.boot_timeout <= 300:
        parser.error("boot-timeout must be in (0, 300]")
    if not 0 <= args.post_route_seconds <= 30:
        parser.error("post-route-seconds must be in [0, 30]")
    if not 0 <= args.pre_route_ticks <= 20000:
        parser.error("pre-route-ticks must be in [0, 20000]")
    args.output.mkdir(parents=True, exist_ok=False)
    identities = {}
    for name in ("qemu", "firmware", "soc_rom", "nand_checkpoint", "package"):
        path = getattr(args, name)
        size, digest = artifact_identity(path)
        identities[name] = {"path": str(path.resolve()), "size": size, "sha256": digest}
    report = {"artifacts": identities, "address": args.address, "write_captured": False,
              "boot_passed": False, "route": [], "host_guest_memory_writes": 0,
              "pre_route_ticks": args.pre_route_ticks,
              "nand_save_enabled": False, "scope": "first write evidence, not stability acceptance"}
    journal = RunJournal(args.output / "process", kind="host-code-write-watch", artifacts=identities)
    emulator = watch = None
    try:
        expected, _ = expected_from_package(args.package)
        emulator = Emulator(qemu=args.qemu, firmware=args.firmware, soc_rom=args.soc_rom,
                            nand_checkpoint=args.nand_checkpoint, soc_rom_skeleton=True,
                            boot_mode="firmware-vma03", start_paused=True, journal=journal)
        watch = HostWatch(args.qemu, emulator.process.pid, args.address, args.output)
        watch.ready()
        print(f"watch armed before boot; owned QEMU PID={emulator.process.pid}", flush=True)
        emulator.qmp.execute("cont")
        started, next_capture, stable = time.monotonic(), 0, 0
        while time.monotonic() - started < args.boot_timeout:
            watch.check()
            snapshot = emulator.snapshot("lcd", 0, 0)
            elapsed = time.monotonic() - started
            result = assess(snapshot, expected[1])
            stable = stable + 1 if result["passed"] else 0
            if elapsed >= next_capture:
                save_snapshot(args.output, f"boot-{int(elapsed):03d}", snapshot)
                print(f"{elapsed:.1f}s {snapshot['registers'].splitlines()[0]} "
                      f"toolbar={result['toolbar']['mismatch_pixels']}/5280", flush=True)
                next_capture = elapsed + 15
            if stable >= 3:
                report["boot_passed"] = True
                break
            time.sleep(1)
        if not report["boot_passed"]:
            raise TimeoutError("bounded cold boot did not reach the expected toolbar")
        if args.pre_route_ticks:
            deadline = time.monotonic() + 180
            next_notice = 0
            while time.monotonic() < deadline:
                watch.check()
                snapshot = emulator.snapshot("lcd", 0, 0)
                match = re.search(r"(?m)^IRQ64=.*?\bTICKS:(\d+)", snapshot["registers"])
                if not match:
                    raise RuntimeError("IRQ64.TICKS is absent; cannot match the saved boot age")
                ticks = int(match.group(1))
                if time.monotonic() >= next_notice:
                    print(f"pre-route age: TICKS={ticks}/{args.pre_route_ticks}", flush=True)
                    next_notice = time.monotonic() + 15
                if ticks >= args.pre_route_ticks:
                    report["actual_pre_route_ticks"] = ticks
                    break
                time.sleep(1)
            else:
                raise TimeoutError("saved boot age was not reached within 180 seconds")
        save_snapshot(args.output, "00-before-route", snapshot)
        bridge = LocalMatrixBridge(emulator, watch)
        for index, step in enumerate(args.step, 1):
            print(f"physical route: {step.label} M{step.matrix_index}", flush=True)
            result = replay_step(bridge, step, press_timeout=10, release_timeout=10,
                                 poll_interval=0.02, pulse_duration=0.12, settle=1.0)
            report["route"].append(result)
            save_snapshot(args.output, f"route-{index:02d}", emulator.snapshot("lcd", 0, 0))
        deadline = time.monotonic() + args.post_route_seconds
        while time.monotonic() < deadline:
            watch.check()
            time.sleep(0.1)
        watch.check()
        report["observation_completed"] = True
    except WriteObserved as error:
        report.update(write_captured=True, observation=str(error))
        print(str(error), flush=True)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        print(report["error"], flush=True)
    finally:
        if watch:
            try:
                watch.close()
            except Exception as error:
                report["gdb_cleanup_error"] = f"{type(error).__name__}: {error}"
            report["gdb_exit_code"] = watch.process.poll()
        if emulator:
            try:
                emulator.qmp.execute("stop")
                save_snapshot(args.output, "final", emulator.snapshot("lcd", 0, 0))
            except Exception as error:
                report["final_capture_error"] = f"{type(error).__name__}: {error}"
            finally:
                try:
                    emulator.close()
                except Exception as error:
                    report["qemu_cleanup_error"] = f"{type(error).__name__}: {error}"
                report["qemu_exit_code"] = emulator.process.poll()
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 1 if "error" in report else 0


if __name__ == "__main__":
    raise SystemExit(main())
