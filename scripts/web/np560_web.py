#!/usr/bin/env python3
"""Local Web bridge for the QEMU NP560+ machine."""

from __future__ import annotations

import argparse
import base64
import ctypes
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

if __package__:
    from .device_config import BOUND_FLAGS, create_device, load_device
else:
    from device_config import BOUND_FLAGS, create_device, load_device


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent.parent
DEFAULT_FIRMWARE = PROJECT / "NP560+V3.80版系统升级程序" / "NP560.PRG"
DEFAULT_QEMU = Path("/mnt/e/qemu-dmcu-build/qemu-system-dmcu")


def terminate_child_with_parent() -> None:
    """Ask Linux to terminate QEMU if the Web bridge is killed externally."""
    if os.name != "posix":
        return
    libc = ctypes.CDLL(None, use_errno=True)
    pr_set_pdeathsig = 1
    if libc.prctl(pr_set_pdeathsig, signal.SIGKILL, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_PDEATHSIG) failed")
    # Close the fork/prctl race if the parent died before prctl completed.
    if os.getppid() == 1:
        os.kill(os.getpid(), signal.SIGKILL)


def artifact_identity(path: Path | None) -> tuple[int, str]:
    """Return a stable size/SHA-256 identity for one configured artifact."""
    if path is None:
        return 0, ""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return path.stat().st_size, digest.hexdigest()


def parse_debug_program_load(value: str) -> tuple[int, Path]:
    """Parse the diagnostic ``ADDRESS@FILE`` program-source replacement."""
    try:
        address_text, path_text = value.split("@", 1)
        address = int(address_text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "debug program load must be ADDRESS@FILE"
        ) from error
    if not 0x200000 <= address < 0x500000 or not path_text:
        raise argparse.ArgumentTypeError(
            "debug program load must target data-visible PRG source"
        )
    return address, Path(path_text)


class QMPError(RuntimeError):
    pass


class RunJournal:
    """Small, durable lifecycle evidence; never infer a crash from a timeout."""

    def __init__(self, root: Path, **identity):
        self.run_id = (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") +
                       f"-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        self.directory = root / self.run_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.lock = threading.Lock()
        self.state = {
            "schema": "np560-web-run-v1", "run_id": self.run_id,
            "bridge_pid": os.getpid(), "directory": str(self.directory),
            **identity,
        }
        boot_id = Path("/proc/sys/kernel/random/boot_id")
        if boot_id.is_file():
            self.state["host_boot_id"] = boot_id.read_text().strip()
        self.record("bridge_starting", phase="starting")

    def record(self, event: str, **fields) -> None:
        with self.lock:
            timestamp = datetime.now(timezone.utc).isoformat()
            self.state.update(fields, last_event=event, updated_at=timestamp)
            try:
                with (self.directory / "events.jsonl").open(
                        "a", encoding="utf-8") as stream:
                    stream.write(json.dumps({
                        "time": timestamp, "event": event, **fields,
                    }, ensure_ascii=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary = self.directory / "status.json.tmp"
                with temporary.open("w", encoding="utf-8") as stream:
                    json.dump(self.state, stream, ensure_ascii=False, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(self.directory / "status.json")
            except OSError as error:
                # A full disk must not prevent child cleanup or reset the guest.
                self.state["journal_error"] = str(error)
                print(f"Lifecycle log failed: {error}", flush=True)

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.state)


class QMPClient:
    def __init__(self, socket_path: Path):
        self.socket_path = socket_path
        self.sock: socket.socket | None = None
        self.stream = None
        self.lock = threading.Lock()
        self.sequence = 0

    def connect(self, timeout: float = 8.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.settimeout(max(0.001, deadline - time.monotonic()))
                sock.connect(str(self.socket_path))
                self.sock = sock
                self.stream = sock.makefile("rwb", buffering=0)
                greeting = self._read_message()
                if "QMP" not in greeting:
                    raise QMPError("QMP greeting is missing")
                self.execute("qmp_capabilities")
                sock.settimeout(None)
                return
            except (FileNotFoundError, ConnectionRefusedError):
                sock.close()
                time.sleep(0.05)
            except BaseException:
                sock.close()
                self.close()
                raise
        raise QMPError("QEMU did not open its QMP socket")

    def close(self) -> None:
        stream, sock = self.stream, self.sock
        self.stream = None
        self.sock = None
        # Interrupt blocked readers before closing their file object. Do not
        # acquire execute's lock: its owner may itself be blocked in readline.
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if stream is not None:
            try:
                stream.close()
            finally:
                if sock is not None:
                    sock.close()
        elif sock is not None:
            sock.close()

    def _read_message(self) -> dict:
        stream = self.stream
        if not stream:
            raise QMPError("QMP is not connected")
        while True:
            try:
                line = stream.readline()
            except socket.timeout:
                raise
            except (OSError, ValueError) as error:
                raise QMPError(f"QMP read failed: {error}") from error
            if not line:
                raise QMPError("QMP connection closed")
            message = json.loads(line)
            if "event" not in message:
                return message

    def execute(self, command: str, arguments: dict | None = None,
                *, timeout: float | None = None):
        # Explicit deadlines are used by shutdown persistence. A blocked Web
        # request must not prevent closing QMP and terminating the owned child.
        acquired = (self.lock.acquire() if timeout is None else
                    self.lock.acquire(timeout=timeout))
        if not acquired:
            raise QMPError(f"{command}: QMP busy; command was not sent")
        sock = self.sock
        previous_timeout = None
        try:
            if sock is not None:
                previous_timeout = sock.gettimeout()
            if timeout is not None and sock is not None:
                sock.settimeout(timeout)
            self.sequence += 1
            request = {"execute": command, "id": self.sequence}
            if arguments:
                request["arguments"] = arguments
            stream = self.stream
            if not stream:
                raise QMPError("QMP is not connected")
            try:
                stream.write(json.dumps(request).encode("utf-8") + b"\r\n")
            except socket.timeout:
                raise
            except (OSError, ValueError) as error:
                raise QMPError(f"QMP write failed: {error}") from error
            while True:
                response = self._read_message()
                if response.get("id") != self.sequence:
                    continue
                if "error" in response:
                    detail = response["error"].get("desc", str(response["error"]))
                    raise QMPError(f"{command}: {detail}")
                return response.get("return")
        except socket.timeout as error:
            # A timed-out socket.makefile cannot safely resume parsing. Close
            # only the transport; this is not evidence the guest has exited.
            self.close()
            raise QMPError(f"{command}: QMP timed out; command outcome unknown") from error
        finally:
            try:
                if sock is not None and self.sock is sock:
                    try:
                        sock.settimeout(previous_timeout)
                    except OSError:
                        # Another thread may have closed it after the check.
                        pass
            finally:
                self.lock.release()

    def hmp(self, command: str) -> str:
        return self.execute(
            "human-monitor-command", {"command-line": command}
        ) or ""


class Emulator:
    def __init__(self, qemu: Path, firmware: Path,
                 mask_rom: Path | None = None,
                 soc_rom: Path | None = None,
                 usb_loader: Path | None = None,
                 burn_code: Path | None = None,
                 driver_code: Path | None = None,
                 nand_image: Path | None = None,
                 nand_checkpoint: Path | None = None,
                 boot_mode: str = "firmware",
                 rom_hle: bool = False,
                 rom_mp3_hle_base: int = 0,
                 rom_mp3_arena_image: int = 0,
                 hle_ui: bool = False,
                 startup_context: int = 0,
                 adc_level: int = 8,
                 external_power: int = 0,
                 soc_rom_skeleton: bool = False,
                 log_unimp: bool = False,
                 icount_shift: int | str | None = None,
                 icount_align: bool = False,
                 nand_save_on_exit: Path | None = None,
                 start_paused: bool = False,
                 journal: RunJournal | None = None,
                 nand_journal: Path | None = None):
        if icount_align and icount_shift != 0:
            raise ValueError("real-time pacing requires fixed icount shift 0")
        if nand_image is not None and nand_checkpoint is not None:
            raise ValueError("nand_image and nand_checkpoint are mutually exclusive")
        if rom_mp3_hle_base and (rom_hle or hle_ui or not soc_rom_skeleton or soc_rom is None):
            raise ValueError("MP3 HLE requires its marked strict skeleton, not legacy HLE")
        if nand_journal is not None and nand_save_on_exit is not None:
            for protected in (nand_journal, nand_image, nand_checkpoint):
                if protected is not None and (
                    nand_save_on_exit.resolve() == protected.resolve() or
                    (nand_save_on_exit.exists() and protected.exists() and
                     nand_save_on_exit.samefile(protected))
                ):
                    raise ValueError("NAND export must not overwrite the journal or its base")
        tag = f"np560-{os.getpid()}-{uuid.uuid4().hex[:12]}"
        self.audio_stream_id = tag
        self.qmp_path = Path(tempfile.gettempdir()) / f"{tag}.qmp"
        self.frame_path = Path(tempfile.gettempdir()) / f"{tag}.frame"
        # Multiple independent Web instances must not truncate or contend for
        # one shared log.  This is especially important while an interactive
        # frontend remains open and an integration test starts on another
        # port.
        self.log_path = (journal.directory / "qemu.log" if journal else
                         Path(tempfile.gettempdir()) / f"{tag}.log")
        self.journal = journal
        self._closing = threading.Event()
        self._closed = False
        self._exit_watcher = None
        self.process = None
        self.qmp = QMPClient(self.qmp_path)
        self.legacy_key_latch = rom_hle
        self.nand_save_on_exit = nand_save_on_exit
        self.nand_journal = nand_journal
        self.soc_rom_size, self.soc_rom_sha256 = artifact_identity(soc_rom)
        self.log = self.log_path.open("xb")
        machine_options = [
            "np560", f"boot-mode={boot_mode}",
            f"rom-hle={'on' if rom_hle else 'off'}",
            f"hle-ui={'on' if hle_ui else 'off'}",
            f"startup-context={startup_context & 0xFFFFFF}",
            f"adc-level={max(0, min(adc_level, 8))}",
            f"external-power={1 if external_power else 0}",
        ]
        if mask_rom is not None:
            machine_options.append(f"mask-rom={mask_rom}")
        if rom_mp3_hle_base:
            machine_options.append(f"rom-mp3-hle-base={rom_mp3_hle_base}")
        if rom_mp3_arena_image:
            if not rom_mp3_hle_base:
                raise ValueError('arena release image requires explicit MP3 HLE')
            machine_options.append(f"rom-mp3-arena-image={rom_mp3_arena_image}")
        if soc_rom is not None:
            machine_options.append(f"soc-rom={soc_rom}")
            if soc_rom_skeleton:
                machine_options.append("soc-rom-skeleton=on")
        if usb_loader is not None:
            machine_options.append(f"usb-loader={usb_loader}")
        if burn_code is not None:
            machine_options.append(f"burn-code={burn_code}")
        if driver_code is not None:
            machine_options.append(f"driver-code={driver_code}")
        if nand_image is not None:
            machine_options.append(f"nand-image={nand_image}")
        if nand_checkpoint is not None:
            machine_options.append(f"nand-checkpoint={nand_checkpoint}")
        if nand_journal is not None:
            machine_options.append(f"nand-journal={nand_journal}")
        machine = ",".join(machine_options)
        command = [
            str(qemu), "-M", machine, "-bios", str(firmware),
            "-nographic", "-monitor", "none",
            "-qmp", f"unix:{self.qmp_path},server=on,wait=off",
        ]
        if start_paused:
            command.append("-S")
        if icount_shift is not None:
            command.extend((
                "-icount", f"shift={icount_shift},align={'on' if icount_align else 'off'},sleep=on",
            ))
        if log_unimp:
            command.extend(("-d", "unimp"))
        try:
            if journal:
                journal.record("qemu_starting", command=command,
                               qemu_log=str(self.log_path),
                               soc_rom_sha256=self.soc_rom_sha256)
            self.process = subprocess.Popen(
                command,
                stdout=self.log,
                stderr=self.log,
                preexec_fn=terminate_child_with_parent if os.name == "posix" else None,
            )
            if journal:
                journal.record("qemu_spawned", qemu_pid=self.process.pid)
            self.qmp.connect()
            self._exit_watcher = threading.Thread(
                target=self._observe_exit, name="np560-qemu-exit", daemon=True,
            )
            self._exit_watcher.start()
        except BaseException:
            # Failed startup must not save a partially initialized NAND over
            # the caller's configured output, nor leave an orphan child.
            self.nand_save_on_exit = None
            self.close()
            raise

    def _observe_exit(self) -> None:
        returncode = self.process.wait()
        if self.journal:
            self.journal.record(
                "qemu_exited", qemu_returncode=returncode,
                unexpected_qemu_exit=not self._closing.is_set(),
            )

    def health(self) -> dict:
        """Read process liveness without QMP, keys, or guest state mutation."""
        returncode = self.process.poll()
        return {
            **(self.journal.snapshot() if self.journal else {}),
            "qemu_pid": self.process.pid, "qemu_returncode": returncode,
            "qemu_alive": returncode is None,
            "guest_health": "not_checked", "qemu_log": str(self.log_path),
        }

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._closing.set()
        save_error: Exception | None = None
        try:
            if (self.nand_save_on_exit is not None and
                    self.process is not None and
                    self.process.poll() is None):
                self.save_nand(self.nand_save_on_exit, timeout=30.0)
        except (OSError, QMPError) as exc:
            save_error = exc
        finally:
            with ExitStack() as cleanup:
                for path in (self.qmp_path, self.frame_path):
                    cleanup.callback(path.unlink, missing_ok=True)
                cleanup.callback(self.log.close)
                try:
                    self.qmp.close()
                finally:
                    try:
                        if self.process is not None and self.process.poll() is None:
                            self.process.terminate()
                            try:
                                self.process.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                self.process.kill()
                                self.process.wait(timeout=2)
                    finally:
                        if (self._exit_watcher is not None and
                                self._exit_watcher.ident is not None):
                            self._exit_watcher.join(timeout=2)
                        if self.journal and self.process is not None:
                            self.journal.record("qemu_reaped", qemu_returncode=self.process.poll())
        if save_error is not None:
            raise save_error

    def save_nand(self, path: Path | None = None,
                  *, timeout: float | None = None) -> Path:
        """Atomically serialize the live NAND data and OOB through QEMU."""
        target = path if path is not None else self.nand_save_on_exit
        if target is None:
            raise ValueError("NAND save output was not configured")
        target = target.resolve()
        if not target.parent.is_dir():
            raise ValueError(f"NAND save directory not found: {target.parent}")
        self.qmp.execute("qom-set", {
            "path": "/machine", "property": "nand-save",
            "value": str(target),
        }, **({"timeout": timeout} if timeout is not None else {}))
        return target

    def load_data(self, address: int, path: Path) -> None:
        """Diagnostic updater transport: load a file into external data RAM."""
        self.qmp.execute("qom-set", {
            "path": "/machine", "property": "debug-data-load",
            "value": f"0x{address:x}@{path}",
        })

    def load_program(self, address: int, path: Path) -> None:
        """Diagnostic updater transport: replace a program-source window."""
        self.qmp.execute("qom-set", {
            "path": "/machine", "property": "debug-program-load",
            "value": f"0x{address:x}@{path}",
        })

    def write_data(self, address: int, data: bytes) -> None:
        """Diagnostic updater transport: write a short external-RAM payload."""
        self.qmp.execute("qom-set", {
            "path": "/machine", "property": "debug-data-write",
            "value": f"0x{address:x}@{data.hex()}",
        })

    def snapshot(self, source: str, base: int, size: int, *, diagnostics: bool = True) -> dict:
        if self.process.poll() is not None:
            raise QMPError(f"QEMU exited with status {self.process.returncode}")
        if source == "lcd":
            frame = self.qmp.execute("qom-get", {
                "path": "/machine", "property": "lcd-frame",
            })
            lcd_state = self.qmp.execute("qom-get", {
                "path": "/machine", "property": "lcd-state",
            })
            frame_format = "gray5"
            width = 240
            height = 120
            stride = 240
        elif source == "lcd-gram":
            frame = self.qmp.execute("qom-get", {
                "path": "/machine", "property": "lcd-gram-frame",
            })
            lcd_state = self.qmp.execute("qom-get", {
                "path": "/machine", "property": "lcd-state",
            })
            frame_format = "gray5"
            width = 240
            height = 160
            stride = 240
        elif source in ("root-entry-back", "root-entry-front"):
            property_name = f"{source}-frame"
            frame = self.qmp.execute("qom-get", {
                "path": "/machine", "property": property_name,
            })
            if not frame:
                raise QMPError("root-entry framebuffer snapshot is not ready")
            lcd_state = "Observer-only framebuffer at natural root entry"
            frame_format = "packed"
            width = 240
            height = 120
            stride = 120
        elif source in ("root-top-object", "root-top-source"):
            property_name = (
                "root-top-bitmap" if source == "root-top-object"
                else "root-top-source"
            )
            frame = self.qmp.execute("qom-get", {
                "path": "/machine", "property": property_name,
            })
            if not frame:
                raise QMPError("root toolbar resource snapshot is not ready")
            lcd_state = "Observer-only root-toolbar resource snapshot"
            frame_format = "packed"
            width = 240
            height = 22
            stride = 120
        elif source in ("memory", "data", "code"):
            if not 0 <= base <= 0xFFFFFF:
                raise ValueError(
                    "framebuffer base is outside the 24-bit address space"
                )
            if not 1 <= size <= 65536 or base + size > 0x1000000:
                raise ValueError("framebuffer request size is invalid")
            if source == "memory":
                self.qmp.execute("pmemsave", {
                    "val": base, "size": size,
                    "filename": str(self.frame_path),
                })
                lcd_state = "Raw physical-memory diagnostic view"
            elif source == "data":
                self.qmp.execute("qom-set", {
                    "path": "/machine", "property": "debug-data-save",
                    "value": f"0x{base:x}:0x{size:x}@{self.frame_path}",
                })
                lcd_state = "Raw NP560 data-RAM diagnostic view"
            else:
                self.qmp.execute("qom-set", {
                    "path": "/machine", "property": "debug-code-save",
                    "value": f"0x{base:x}:0x{size:x}@{self.frame_path}",
                })
                lcd_state = "Raw NP560 DMCU code-bus diagnostic view"
            memory_frame = self.frame_path.read_bytes()
            if len(memory_frame) != size:
                raise QMPError(
                    f"QEMU returned {len(memory_frame)} bytes, expected {size}"
                )
            frame = base64.b64encode(memory_frame).decode("ascii")
            frame_format = "packed"
            width = 240
            height = 120
            stride = 0
        else:
            raise ValueError("unknown frame source")
        lcd_annunciators = self.qmp.execute("qom-get", {
            "path": "/machine", "property": "lcd-annunciators",
        })
        status = self.qmp.execute("query-status")
        registers = self.qmp.execute("qom-get", {
            "path": "/machine", "property": "cpu-state",
        }) if diagnostics else None
        nand_state = self.qmp.execute("qom-get", {
            "path": "/machine", "property": "nand-state",
        })
        nand_journal_state = "disabled"
        if getattr(self, "nand_journal", None) is not None:
            nand_journal_state = self.qmp.execute("qom-get", {
                "path": "/machine", "property": "nand-journal-state",
            })
        configured_soc_rom = self.qmp.execute("qom-get", {
            "path": "/machine", "property": "soc-rom",
        })
        return {
            "running": bool(status.get("running")),
            "status": status.get("status", "unknown"),
            "source": source,
            "format": frame_format,
            "width": width,
            "height": height,
            "stride": stride,
            "frame": frame,
            # Two 240-bit custom-glass planes written by the guest to ST7529
            # controller lines 19 and 140.  The browser maps these electrode
            # signals to the fixed NP560 panel artwork; it never derives icon
            # state directly from host-side ADC or power controls.
            "lcd_annunciators": lcd_annunciators,
            "lcd_state": lcd_state,
            "nand_state": nand_state,
            "nand_journal_state": nand_journal_state,
            "nand_save_enabled": self.nand_save_on_exit is not None,
            "device": getattr(self, "device_identity", None),
            # Bind screenshots and memory diagnostics to the exact ROM artifact
            # selected on QEMU's machine object.  This prevents two images with
            # identical resource pages but different executable patches from
            # being confused during reverse-engineering experiments.
            "soc_rom_configured": configured_soc_rom,
            "soc_rom_size": self.soc_rom_size,
            "soc_rom_sha256": self.soc_rom_sha256,
            "registers": registers,
        }

    def diagnostics(self) -> dict:
        """Return the CPU diagnostics without capturing LCD or NAND state.

        Runtime reverse-engineering monitors only need the bounded text
        counters exposed by the machine.  Avoiding lcd-frame, lcd-state and
        nand-state QMP requests keeps those monitors from throttling the
        guest while preserving the exact same read-only CPU diagnostics.
        """
        if self.process.poll() is not None:
            raise QMPError(f"QEMU exited with status {self.process.returncode}")
        status = self.qmp.execute("query-status")
        registers = self.qmp.execute("qom-get", {
            "path": "/machine", "property": "cpu-state",
        })
        return {
            "running": bool(status.get("running")),
            "status": status.get("status", "unknown"),
            "registers": registers,
        }

    def completed_frame(self) -> dict:
        """Return the last fully written ST7529 window without diagnostics."""
        if self.process.poll() is not None:
            raise QMPError(f"QEMU exited with status {self.process.returncode}")
        frame = self.qmp.execute("qom-get", {
            "path": "/machine", "property": "lcd-completed-frame",
        })
        sequence = self.qmp.execute("qom-get", {
            "path": "/machine",
            "property": "lcd-completed-frame-sequence",
        })
        if not isinstance(frame, str) or not frame:
            raise QMPError("no complete ST7529 frame is available yet")
        try:
            sequence_value = int(sequence, 10)
        except (TypeError, ValueError) as exc:
            raise QMPError("invalid complete ST7529 frame sequence") from exc
        return {
            "format": "gray5",
            "width": 240,
            "height": 120,
            "stride": 240,
            "sequence": sequence_value,
            "frame": frame,
        }

    def audio(self) -> dict:
        """Read the device's virtual-time PCM ring without consuming it."""
        if self.process.poll() is not None:
            raise QMPError(f"QEMU exited with status {self.process.returncode}")
        raw = self.qmp.execute("qom-get", {"path": "/machine", "property": "audio-pcm"})
        if not isinstance(raw, str):
            raise QMPError("audio-pcm returned a non-string value")
        try:
            packet = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise QMPError("audio-pcm returned invalid JSON") from exc
        if not isinstance(packet, dict):
            raise QMPError("invalid audio packet")
        first, last = packet.get("first_frame"), packet.get("next_frame")
        generation = packet.get("generation")
        if (packet.get("format") != "s16le" or packet.get("sample_rate") != 48000
                or packet.get("channels") != 2 or type(first) is not int
                or type(last) is not int or not 0 <= first <= last <= 2**53 - 1
                or type(generation) is not int or not 0 <= generation <= 2**53 - 1
                or last - first > 9600 or not isinstance(packet.get("pcm"), str)
                or len(packet["pcm"]) > 51200):
            raise QMPError("invalid audio format or sequence")
        samples = base64.b64decode(packet["pcm"], validate=True)
        if len(samples) != (last - first) * 4:
            raise QMPError("invalid audio payload length")
        # QEMU reset changes generation; a new QEMU process changes stream_id.
        # Neither operation is inferred from a decreasing packet sequence.
        packet["stream_id"] = self.audio_stream_id
        return packet

    def key_status(self) -> dict:
        """Return only bounded, read-only guest matrix edge counters."""
        if self.process.poll() is not None:
            raise QMPError(f"QEMU exited with status {self.process.returncode}")
        payload = self.qmp.execute("qom-get", {
            "path": "/machine", "property": "key-pipeline-status",
        })
        if not isinstance(payload, str):
            raise QMPError("key-pipeline-status returned a non-string value")
        try:
            status = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise QMPError("key-pipeline-status returned invalid JSON") from exc
        fields = (
            "maps", "event", "candidates", "candidate",
            "acknowledgements", "acknowledgement",
            "modal_acknowledgements", "modal_acknowledgement",
            "matrix_reads", "matrix_rearmed", "application_state",
            "primary_action_selector_calls",
            "primary_action_selector_returns",
            "primary_action_selector_result",
            "primary_action_late_paths",
            "primary_action_object_guard_checks",
            "primary_action_object_guard_value",
            "primary_action_object_guard_passes",
            "primary_action_object_guard_rejects",
            "primary_action_object_commits",
            "primary_action_object_commit_flag",
            "direction_up_paths", "direction_down_paths",
            "direction_left_paths", "direction_right_paths",
            "direction_helper_active", "direction_helper_calls",
            "direction_helper_returns", "direction_helper_result",
            "direction_code", "direction_before_x", "direction_before_y",
            "direction_before_offset_x", "direction_before_offset_y",
            "direction_after_x", "direction_after_y",
            "direction_after_offset_x", "direction_after_offset_y",
            "direction_before_map_index", "direction_before_scroll",
            "direction_after_map_index", "direction_after_scroll",
            "current_direction", "current_x", "current_y",
            "current_offset_x", "current_offset_y",
            "current_map_index", "current_scroll", "current_move_state",
            "render_calls", "render_callback_dispatches",
            "render_object_valid", "render_object_hi", "render_object_lo",
            "render_stack_object_hi", "render_stack_object_lo",
            "render_entry_callback_r0", "render_entry_callback_r1",
            "render_callback_object_valid", "render_callback_object_hi",
            "render_callback_object_lo", "render_callback_r0",
            "render_callback_r1", "render_callback_target_segment",
            "render_callback_target_pc", "render_callback_field_r0",
            "render_callback_field_r1",
            "faulted",
        )
        if not isinstance(status, dict) or any(
            name not in status for name in fields
        ):
            raise QMPError("key-pipeline-status is missing required fields")
        word_fields = {
            "event", "candidate", "acknowledgement",
            "modal_acknowledgement", "application_state",
            "primary_action_selector_result",
        }
        boolean_fields = {
            "matrix_rearmed", "render_object_valid",
            "render_callback_object_valid", "direction_helper_active",
            "faulted",
        }
        return {
            name: (
                bool(status[name]) if name in boolean_fields else
                int(status[name]) & (
                    0xFFFF if name in word_fields else 0xFFFFFFFFFFFFFFFF
                )
            )
            for name in fields
        }

    def control(self, action: str) -> None:
        commands = {
            "pause": "stop",
            "resume": "cont",
            "reset": "system_reset",
        }
        if action not in commands:
            raise ValueError("unknown control action")
        self.qmp.execute(commands[action])

    def set_key(self, state: int, code: int,
                matrix_low: int = 0, matrix_high: int = 0) -> None:
        # Strict hardware mode exposes the F160/F164 physical key matrix.
        # F010 is guest-owned audio-state RAM, never a keyboard register.
        # F340 is retained solely for the explicitly
        # requested diagnostic HLE UI.  Program the legacy code before the
        # physical level so HLE never observes a key-down edge with a stale
        # code.
        effective_code = code if self.legacy_key_latch else 0
        # The browser sends both its navigation alias and the recovered 64-bit
        # matrix position.  In strict mode the matrix is authoritative; ORing
        # the alias into the same physical key creates two asynchronous input
        # sources around key-up and can prevent the guest debounce queue from
        # observing one clean release edge.  Keep key-state as a compatibility
        # fallback for older QMP/Web clients which omit the matrix fields.
        effective_state = state
        if not self.legacy_key_latch and (matrix_low or matrix_high):
            effective_state = 0
        for name, value in (("key-code", effective_code),
                            ("key-matrix-low", matrix_low),
                            ("key-matrix-high", matrix_high),
                            ("key-state", effective_state)):
            self.qmp.execute("qom-set", {
                "path": "/machine", "property": name, "value": value,
            })

    def pulse_matrix(self, matrix_index: int) -> None:
        """Arm one diagnostic physical switch for one guest row scan."""
        if not 0 <= matrix_index < 64:
            raise ValueError("matrix pulse index is outside 0..63")
        self.qmp.execute("qom-set", {
            "path": "/machine",
            "property": "key-matrix-pulse-index",
            "value": matrix_index,
        })

    def set_adc_level(self, level: int) -> None:
        if not 0 <= level <= 8:
            raise ValueError("ADC level is outside the recovered 0..8 range")
        self.qmp.execute("qom-set", {
            "path": "/machine", "property": "adc-level", "value": level,
        })

    def set_external_power(self, connected: bool) -> None:
        self.qmp.execute("qom-set", {
            "path": "/machine", "property": "external-power",
            "value": 1 if connected else 0,
        })


class KeyInputLease:
    """Release opt-in browser-held matrix levels after heartbeat loss."""

    MIN_LEASE_MS = 500
    MAX_LEASE_MS = 5000

    def __init__(self, emulator: Emulator, *, poll_interval: float = 0.1,
                 clock=time.monotonic, start_worker: bool = True):
        self.emulator = emulator
        self.poll_interval = poll_interval
        self.clock = clock
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.owner = ""
        self.deadline = 0.0
        self.lease_seconds = 0.0
        self.worker = None
        if start_worker:
            self.worker = threading.Thread(
                target=self._run, name="np560-key-lease", daemon=True,
            )
            self.worker.start()

    @classmethod
    def _validate_lease(cls, lease_id: str, lease_ms: int) -> None:
        if not lease_id:
            return
        if (len(lease_id) > 64 or not all(
                character.isalnum() or character in "-_"
                for character in lease_id)):
            raise ValueError("invalid key lease id")
        if not cls.MIN_LEASE_MS <= lease_ms <= cls.MAX_LEASE_MS:
            raise ValueError("key lease duration is outside 500..5000 ms")

    def apply(self, state: int, code: int, matrix_low: int,
              matrix_high: int, lease_id: str = "",
              lease_ms: int = 0) -> bool:
        self._validate_lease(lease_id, lease_ms)
        held = bool(state or code or matrix_low or matrix_high)
        with self.lock:
            # One live browser lease owns the complete hardware matrix.  Both
            # a late break and a delayed make from another page must be
            # rejected; otherwise an older page can reclaim the matrix after
            # a newer page has acquired it.  The new page retries its locally
            # held level after the old lease expires.  Clients which omit a
            # lease_id intentionally retain the original probe/API behavior.
            if lease_id and self.owner and lease_id != self.owner:
                return False
            self.emulator.set_key(state, code, matrix_low, matrix_high)
            if lease_id and held:
                self.owner = lease_id
                self.lease_seconds = lease_ms / 1000.0
                self.deadline = self.clock() + self.lease_seconds
            else:
                self.owner = ""
                self.deadline = 0.0
                self.lease_seconds = 0.0
        return True

    def heartbeat(self, lease_id: str) -> bool:
        with self.lock:
            if not lease_id or lease_id != self.owner:
                return False
            self.deadline = self.clock() + self.lease_seconds
            return True

    def expire_due(self, now: float | None = None) -> bool:
        current = self.clock() if now is None else now
        with self.lock:
            if not self.owner or current < self.deadline:
                return False
            # This is the same hardware break as a browser release.  It does
            # not inject a guest event or touch menu/application state.
            self.emulator.set_key(0, 0, 0, 0)
            self.owner = ""
            self.deadline = 0.0
            self.lease_seconds = 0.0
            return True

    def _run(self) -> None:
        while not self.stop_event.wait(self.poll_interval):
            try:
                self.expire_due()
            except (OSError, QMPError):
                # QEMU shutdown and a transient QMP error are handled by the
                # server lifecycle; retain the lease so a later tick retries.
                pass

    def close(self) -> None:
        self.stop_event.set()
        if self.worker is not None:
            self.worker.join(timeout=max(1.0, self.poll_interval * 4))
        with self.lock:
            if self.owner:
                try:
                    self.emulator.set_key(0, 0, 0, 0)
                except (OSError, QMPError):
                    pass
            self.owner = ""
            self.deadline = 0.0
            self.lease_seconds = 0.0


class RequestHandler(SimpleHTTPRequestHandler):
    server_version = "NP560Web/0.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    @property
    def emulator(self) -> Emulator:
        return self.server.emulator  # type: ignore[attr-defined]

    @property
    def key_lease(self) -> KeyInputLease:
        return self.server.key_lease  # type: ignore[attr-defined]

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _json(self, data: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # Closing a page or disabling audio aborts its in-flight reads.
            # There is no client to receive a second error response.
            return

    def _error(self, exc: Exception) -> None:
        self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/key-status":
            try:
                self._json(self.emulator.key_status())
            except (ValueError, OSError, QMPError) as exc:
                self._error(exc)
            return
        if parsed.path == "/api/health":
            health = self.emulator.health()
            self._json(health, HTTPStatus.OK if health["qemu_alive"] else
                       HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if parsed.path == "/api/diagnostics":
            try:
                self._json(self.emulator.diagnostics())
            except (ValueError, OSError, QMPError) as exc:
                self._error(exc)
            return
        if parsed.path == "/api/frame":
            try:
                self._json(self.emulator.completed_frame())
            except (ValueError, OSError, QMPError) as exc:
                self._error(exc)
            return
        if parsed.path == "/api/audio":
            try:
                self._json(self.emulator.audio())
            except (ValueError, OSError, QMPError) as exc:
                self._error(exc)
            return
        if parsed.path != "/api/state":
            if parsed.path == "/":
                self.path = "/index.html"
            return super().do_GET()
        try:
            query = parse_qs(parsed.query)
            source = query.get("source", [
                "memory" if "base" in query else "lcd"
            ])[0]
            base = int(query.get("base", ["0"])[0], 0)
            size = int(query.get("size", ["3600"])[0], 0)
            self._json(self.emulator.snapshot(source, base, size,
                diagnostics=query.get("diagnostics", ["1"])[0] != "0"))
        except (ValueError, OSError, QMPError) as exc:
            self._error(exc)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 4096:
                raise ValueError("request is too large")
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/control":
                action = str(payload.get("action", ""))
                if action == "shutdown":
                    expected = getattr(self.server, "shutdown_token", None)
                    supplied = str(payload.get("token", ""))
                    if not expected or supplied != expected:
                        raise ValueError("invalid Web shutdown token")
                    self._json({"ok": True})
                    journal = getattr(self.server, "journal", None)
                    if journal:
                        journal.record("shutdown_requested", reason="api")
                    threading.Thread(
                        target=self.server.shutdown, daemon=True
                    ).start()
                    return
                self.emulator.control(action)
            elif self.path == "/api/key":
                state = int(payload.get("state", 0)) & 0xFFFFFFFF
                code = int(payload.get("code", 0)) & 0xFFFFFFFF
                matrix_low = int(payload.get("matrix_low", 0)) & 0xFFFFFFFF
                matrix_high = int(payload.get("matrix_high", 0)) & 0xFFFFFFFF
                lease_id = str(payload.get("lease_id", ""))
                lease_ms = int(payload.get("lease_ms", 0))
                applied = self.key_lease.apply(
                    state, code, matrix_low, matrix_high,
                    lease_id, lease_ms,
                )
                self._json({"ok": True, "applied": applied})
                return
            elif self.path == "/api/key-heartbeat":
                lease_id = str(payload.get("lease_id", ""))
                self._json({
                    "ok": True,
                    "active": self.key_lease.heartbeat(lease_id),
                })
                return
            elif self.path == "/api/key-pulse":
                matrix_index = int(payload.get("matrix_index", -1))
                self.emulator.pulse_matrix(matrix_index)
                self._json({"ok": True, "matrix_index": matrix_index})
                return
            elif self.path == "/api/hardware":
                if "adc_level" in payload:
                    self.emulator.set_adc_level(int(payload["adc_level"]))
                if "external_power" in payload:
                    self.emulator.set_external_power(
                        bool(payload["external_power"])
                    )
                if not {"adc_level", "external_power"} & payload.keys():
                    raise ValueError("no supported hardware input was supplied")
            elif self.path == "/api/nand/save":
                saved = self.emulator.save_nand()
                self._json({"ok": True, "path": str(saved)})
                return
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._json({"ok": True})
        except (ValueError, OSError, json.JSONDecodeError, QMPError) as exc:
            self._error(exc)

    def log_message(self, fmt: str, *args) -> None:
        print(f"web: {fmt % args}")


def parse_args(argv=None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    device_mode = parser.add_mutually_exclusive_group()
    device_mode.add_argument("--device", type=Path,
                             help="resume a persistent device configuration")
    device_mode.add_argument("--create-device", type=Path,
                             help="create a new device config from the supplied inputs, then exit")
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--firmware", type=Path, default=DEFAULT_FIRMWARE)
    parser.add_argument("--mask-rom", type=Path)
    parser.add_argument("--soc-rom", type=Path)
    parser.add_argument("--rom-mp3-hle-base", type=lambda s: int(s, 0), default=0)
    parser.add_argument("--rom-mp3-arena-image", type=lambda s: int(s, 0), default=0)
    parser.add_argument("--instruction-clock", action="store_true")
    parser.add_argument("--full-control-observers", action="store_true",
                        help="enable expensive historical reverse-engineering traces")
    parser.add_argument(
        "--soc-rom-skeleton", action="store_true",
        help="treat reserved holes in an experimental SoC ROM as missing",
    )
    parser.add_argument("--usb-loader", type=Path)
    parser.add_argument("--burn-code", type=Path)
    parser.add_argument("--driver-code", type=Path)
    parser.add_argument("--nand-image", type=Path)
    parser.add_argument(
        "--nand-checkpoint", type=Path,
        help="restore a complete NAND data/OOB checkpoint",
    )
    parser.add_argument(
        "--nand-journal", type=Path,
        help=("durably append NAND changes and replay them on restart; "
              "reuse with the unchanged base image/checkpoint (POSIX QEMU)"),
    )
    parser.add_argument(
        "--nand-save-on-exit", type=Path,
        help=("save the complete live NAND data/OOB checkpoint on exit and "
              "enable the Web save button"),
    )
    parser.add_argument(
        "--boot-mode",
        choices=("firmware", "firmware-vma03", "usb", "burn", "driver"),
        default="firmware",
    )
    parser.add_argument(
        "--rom-hle", action="store_true",
        help="enable diagnostic replacements for unavailable resident ROM code",
    )
    parser.add_argument(
        "--hle-ui", action="store_true",
        help="enable the diagnostic compatibility menu (also enables ROM HLE)",
    )
    parser.add_argument(
        "--startup-context", type=lambda value: int(value, 0), default=0,
        help="24-bit resident-loader context pointer (diagnostic)",
    )
    parser.add_argument(
        "--adc-level", type=int, choices=range(0, 9), default=8,
        help="F2D0 analog comparator level exposed to the guest (0..8)",
    )
    parser.add_argument(
        "--external-power", type=int, choices=(0, 1), default=0,
        help="F160 bit-12 external-power/charger input (0 or 1)",
    )
    parser.add_argument(
        "--log-unimp", action="store_true",
        help="write bounded QEMU DMCU diagnostic traces to a per-process log",
    )
    parser.add_argument(
        "--icount-shift", type=int, choices=range(0, 21),
        help=("advance virtual time by 2^N ns per DMCU instruction instead "
              "of tying the 64 Hz timer to slow host execution"),
    )
    parser.add_argument('--realtime', action='store_true',
                        help='pace a sufficiently fast instruction-clock CPU to host time; requires --instruction-clock --icount-shift 0')
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--run-log-dir", type=Path, default=PROJECT / "tmp" / "web-runs",
        help="retain per-run lifecycle records and QEMU logs across WSL restarts",
    )
    parser.add_argument(
        "--shutdown-token",
        help="allow a matching local API request to stop this Web instance",
    )
    parser.add_argument(
        "--debug-program-load", action="append", default=[],
        type=parse_debug_program_load, metavar="ADDRESS@FILE",
        help=("diagnostic only: replace a PRG source window through QMP "
              "immediately after QEMU starts"),
    )
    parser.add_argument(
        "--initial-key-matrix-low", type=lambda value: int(value, 0), default=0,
        help=("diagnostic only: hold these low 32 matrix bits before the "
              "first guest instruction; release them through /api/key"),
    )
    parser.add_argument(
        "--initial-key-matrix-high", type=lambda value: int(value, 0), default=0,
        help=("diagnostic only: hold these high 32 matrix bits before the "
              "first guest instruction; release them through /api/key"),
    )
    args = parser.parse_args(argv)
    args.device_identity = None
    if args.device:
        supplied = {token.split("=", 1)[0] for token in argv if token.startswith("--")}
        conflicts = supplied & BOUND_FLAGS
        if conflicts:
            parser.error("--device binds these settings; remove overrides: " +
                         ", ".join(sorted(conflicts)))
        try:
            args.device_identity = load_device(
                args.device, args, qemu_override="--qemu" in supplied)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            parser.error(str(error))
    return args


def main() -> int:
    args = parse_args()
    if args.create_device:
        try:
            config = create_device(args.create_device, args)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            raise SystemExit(str(error)) from error
        print(f"Created NP560+ device {config['name']}: {args.create_device.resolve()}")
        print("Resume with --device. NAND changes will use the same journal on every boot.")
        return 0
    if not args.qemu.is_file():
        raise SystemExit(f"QEMU not found: {args.qemu}")
    if not args.firmware.is_file():
        raise SystemExit(f"Firmware not found: {args.firmware}")
    if args.mask_rom is not None and not args.mask_rom.is_file():
        raise SystemExit(f"Mask ROM not found: {args.mask_rom}")
    if args.soc_rom is not None and not args.soc_rom.is_file():
        raise SystemExit(f"SoC ROM not found: {args.soc_rom}")
    if args.soc_rom is not None and args.mask_rom is not None:
        raise SystemExit("--soc-rom and --mask-rom cannot be used together")
    if args.soc_rom_skeleton and args.soc_rom is None:
        raise SystemExit("--soc-rom-skeleton requires --soc-rom")
    if args.usb_loader is not None and not args.usb_loader.is_file():
        raise SystemExit(f"USB loader not found: {args.usb_loader}")
    if args.burn_code is not None and not args.burn_code.is_file():
        raise SystemExit(f"Burn code not found: {args.burn_code}")
    if args.driver_code is not None and not args.driver_code.is_file():
        raise SystemExit(f"Driver code not found: {args.driver_code}")
    if args.nand_image is not None and not args.nand_image.is_file():
        raise SystemExit(f"NAND image not found: {args.nand_image}")
    if args.nand_checkpoint is not None and not args.nand_checkpoint.is_file():
        raise SystemExit(f"NAND checkpoint not found: {args.nand_checkpoint}")
    for _address, path in args.debug_program_load:
        if not path.is_file():
            raise SystemExit(f"Debug program load not found: {path}")
    if args.nand_image is not None and args.nand_checkpoint is not None:
        raise SystemExit("--nand-image and --nand-checkpoint cannot be used together")
    if args.nand_journal is not None:
        args.nand_journal = args.nand_journal.resolve()
        args.nand_journal.parent.mkdir(parents=True, exist_ok=True)
    if args.nand_save_on_exit is not None:
        args.nand_save_on_exit = args.nand_save_on_exit.resolve()
        args.nand_save_on_exit.parent.mkdir(parents=True, exist_ok=True)
    if args.boot_mode == "usb" and args.usb_loader is None:
        raise SystemExit("--boot-mode usb requires --usb-loader")
    if args.boot_mode == "burn" and args.burn_code is None:
        raise SystemExit("--boot-mode burn requires --burn-code")
    if args.boot_mode == "driver" and args.driver_code is None:
        raise SystemExit("--boot-mode driver requires --driver-code")
    return run_server(args)


def run_server(args: argparse.Namespace) -> int:
    journal = RunJournal(args.run_log_dir, host=args.host, port=args.port,
                         boot_mode=args.boot_mode,
                         device=getattr(args, "device_identity", None))
    print(f"Lifecycle records: {journal.directory}", flush=True)
    lease = None

    def close_runtime():
        try:
            # QMP shutdown releases any request holding the input-lease lock.
            emulator.close()
        finally:
            if lease is not None:
                lease.close()

    try:
        with ExitStack() as cleanup:
            # Reserve the port before starting QEMU. A duplicate launch must
            # neither boot another guest nor touch the existing instance.
            server = ThreadingHTTPServer((args.host, args.port), RequestHandler)
            cleanup.callback(server.server_close)
            server.daemon_threads = True
            server.block_on_close = False
            artifacts = {}
            for name in ("qemu", "firmware", "soc_rom", "mask_rom", "usb_loader",
                         "burn_code", "driver_code", "nand_image", "nand_checkpoint"):
                path = getattr(args, name)
                if path is not None:
                    size, digest = artifact_identity(path)
                    artifacts[name] = {
                        "path": str(path.resolve()), "size": size, "sha256": digest,
                    }
            for name in ("np560_web.py", "device_config.py", "app.js", "keyboard_input.js", "audio_output.js", "index.html"):
                size, digest = artifact_identity(ROOT / name)
                artifacts[name] = {"size": size, "sha256": digest}
            journal.record("artifacts_identified", artifacts=artifacts,
                           host=server.server_address[0], port=server.server_port)
            emulator = start_emulator(args, journal)
            cleanup.callback(close_runtime)
            emulator.device_identity = getattr(args, "device_identity", None)
            for address, path in args.debug_program_load:
                emulator.load_program(address, path.resolve())
            if args.initial_key_matrix_low or args.initial_key_matrix_high:
                emulator.set_key(
                    0, 0, args.initial_key_matrix_low & 0xFFFFFFFF,
                    args.initial_key_matrix_high & 0xFFFFFFFF,
                )
            if (args.debug_program_load or args.initial_key_matrix_low or
                    args.initial_key_matrix_high):
                emulator.qmp.execute("cont")
            lease = KeyInputLease(emulator)
            server.emulator = emulator
            server.key_lease = lease
            server.shutdown_token = args.shutdown_token
            server.journal = journal
            stopping = threading.Event()

            def stop(signum=None, _frame=None):
                if not stopping.is_set():
                    stopping.set()
                    def shutdown():
                        journal.record("shutdown_requested", reason="signal", signal=signum)
                        server.shutdown()
                    threading.Thread(target=shutdown, daemon=True).start()

            signals = [signal.SIGINT, signal.SIGTERM]
            if hasattr(signal, "SIGHUP"):
                signals.append(signal.SIGHUP)
            for signum in signals:
                previous = signal.signal(signum, stop)
                cleanup.callback(signal.signal, signum, previous)
            journal.record("web_serving", phase="serving")
            print(f"NP560+ Web frontend: http://{args.host}:{server.server_port}", flush=True)
            print(f"QEMU log: {emulator.log_path}", flush=True)
            server.serve_forever()
            returncode = 0 if emulator.process.poll() is None else 1
        journal.record("bridge_stopped", phase="stopped", bridge_returncode=returncode)
        return returncode
    except BaseException as error:
        journal.record("bridge_failed", phase="failed", bridge_returncode=1,
                       error=str(error), traceback=traceback.format_exc())
        raise


def start_emulator(args: argparse.Namespace, journal: RunJournal) -> Emulator:
    instruction_clock = getattr(args, "instruction_clock", False)
    realtime = getattr(args, 'realtime', False)
    minimal_observers = not (getattr(args, "full_control_observers", False) or
                            args.rom_hle or args.hle_ui)
    if instruction_clock and args.icount_shift != 0:
        raise ValueError("--instruction-clock requires --icount-shift 0")
    if realtime and not instruction_clock:
        raise ValueError('--realtime requires --instruction-clock')
    emulator = Emulator(
        qemu=args.qemu, firmware=args.firmware,
        mask_rom=args.mask_rom, soc_rom=args.soc_rom,
        usb_loader=args.usb_loader, burn_code=args.burn_code,
        driver_code=args.driver_code, nand_image=args.nand_image,
        nand_checkpoint=args.nand_checkpoint,
        nand_journal=getattr(args, "nand_journal", None),
        boot_mode=args.boot_mode,
        rom_hle=args.rom_hle or args.hle_ui,
        hle_ui=args.hle_ui,
        rom_mp3_hle_base=getattr(args, "rom_mp3_hle_base", 0),
        rom_mp3_arena_image=getattr(args, "rom_mp3_arena_image", 0),
        startup_context=args.startup_context,
        adc_level=args.adc_level,
        external_power=args.external_power,
        soc_rom_skeleton=args.soc_rom_skeleton,
        log_unimp=args.log_unimp,
        icount_shift=args.icount_shift,
        icount_align=realtime,
        nand_save_on_exit=args.nand_save_on_exit,
        start_paused=bool(
            instruction_clock or minimal_observers or args.debug_program_load or args.initial_key_matrix_low or
            args.initial_key_matrix_high
        ),
        journal=journal,
    )
    if instruction_clock or minimal_observers:
        try:
            if instruction_clock:
                emulator.qmp.execute("qom-set", {"path": "/machine", "property": "instruction-clock", "value": True})
            if minimal_observers:
                emulator.qmp.execute("qom-set", {"path": "/machine", "property": "control-observers-minimal", "value": True})
            if not (args.debug_program_load or args.initial_key_matrix_low or args.initial_key_matrix_high):
                emulator.qmp.execute("cont")
        except BaseException:
            emulator.close()
            raise
    return emulator


if __name__ == "__main__":
    raise SystemExit(main())
