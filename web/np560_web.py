#!/usr/bin/env python3
"""Local Web bridge for the QEMU NP560+ machine."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import signal
import socket
import subprocess
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent.parent
DEFAULT_FIRMWARE = PROJECT / "NP560+V3.80版系统升级程序" / "NP560.PRG"
DEFAULT_QEMU = Path("/mnt/e/qemu-dmcu-build/qemu-system-dmcu")


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
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(str(self.socket_path))
                self.sock = sock
                self.stream = sock.makefile("rwb", buffering=0)
                greeting = self._read_message()
                if "QMP" not in greeting:
                    raise QMPError("QMP greeting is missing")
                self.execute("qmp_capabilities")
                return
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.05)
        raise QMPError("QEMU did not open its QMP socket")

    def close(self) -> None:
        if self.stream:
            self.stream.close()
        if self.sock:
            self.sock.close()
        self.stream = None
        self.sock = None

    def _read_message(self) -> dict:
        if not self.stream:
            raise QMPError("QMP is not connected")
        while True:
            line = self.stream.readline()
            if not line:
                raise QMPError("QMP connection closed")
            message = json.loads(line)
            if "event" not in message:
                return message

    def execute(self, command: str, arguments: dict | None = None):
        with self.lock:
            self.sequence += 1
            request = {"execute": command, "id": self.sequence}
            if arguments:
                request["arguments"] = arguments
            if not self.stream:
                raise QMPError("QMP is not connected")
            self.stream.write(json.dumps(request).encode("utf-8") + b"\r\n")
            while True:
                response = self._read_message()
                if response.get("id") != self.sequence:
                    continue
                if "error" in response:
                    detail = response["error"].get("desc", str(response["error"]))
                    raise QMPError(f"{command}: {detail}")
                return response.get("return")

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
                 hle_ui: bool = False,
                 startup_context: int = 0,
                 adc_level: int = 8,
                 external_power: int = 0,
                 soc_rom_skeleton: bool = False,
                 log_unimp: bool = False,
                 icount_shift: int | None = None,
                 nand_save_on_exit: Path | None = None,
                 start_paused: bool = False):
        if nand_image is not None and nand_checkpoint is not None:
            raise ValueError("nand_image and nand_checkpoint are mutually exclusive")
        tag = f"np560-{os.getpid()}"
        self.qmp_path = Path(tempfile.gettempdir()) / f"{tag}.qmp"
        self.frame_path = Path(tempfile.gettempdir()) / f"{tag}.frame"
        # Multiple independent Web instances must not truncate or contend for
        # one shared log.  This is especially important while an interactive
        # frontend remains open and an integration test starts on another
        # port.
        self.log_path = Path(tempfile.gettempdir()) / f"{tag}.log"
        self.qmp = QMPClient(self.qmp_path)
        self.log = self.log_path.open("wb")
        self.legacy_key_latch = rom_hle
        self.nand_save_on_exit = nand_save_on_exit
        self.soc_rom_size, self.soc_rom_sha256 = artifact_identity(soc_rom)
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
        machine = ",".join(machine_options)
        command = [
            str(qemu), "-M", machine, "-bios", str(firmware),
            "-nographic", "-monitor", "none", "-no-reboot",
            "-qmp", f"unix:{self.qmp_path},server=on,wait=off",
        ]
        if start_paused:
            command.append("-S")
        if icount_shift is not None:
            command.extend((
                "-icount", f"shift={icount_shift},align=off,sleep=off",
            ))
        if log_unimp:
            command.extend(("-d", "unimp"))
        self.process = subprocess.Popen(command, stdout=self.log, stderr=self.log)
        self.qmp.connect()

    def close(self) -> None:
        save_error: Exception | None = None
        try:
            if (self.nand_save_on_exit is not None and
                    self.process.poll() is None):
                self.save_nand(self.nand_save_on_exit)
        except (OSError, QMPError) as exc:
            save_error = exc
        finally:
            self.qmp.close()
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            self.log.close()
            for path in (self.qmp_path, self.frame_path):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        if save_error is not None:
            raise save_error

    def save_nand(self, path: Path | None = None) -> Path:
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
        })
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

    def snapshot(self, source: str, base: int, size: int) -> dict:
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
        elif source in ("memory", "data"):
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
            else:
                self.qmp.execute("qom-set", {
                    "path": "/machine", "property": "debug-data-save",
                    "value": f"0x{base:x}:0x{size:x}@{self.frame_path}",
                })
                lcd_state = "Raw NP560 data-RAM diagnostic view"
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
        })
        nand_state = self.qmp.execute("qom-get", {
            "path": "/machine", "property": "nand-state",
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
            "nand_save_enabled": self.nand_save_on_exit is not None,
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
        # Strict hardware mode exposes only the evidenced F010 GPIO and
        # F160/F164 matrix.  F340 is retained solely for the explicitly
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


class RequestHandler(SimpleHTTPRequestHandler):
    server_version = "NP560Web/0.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    @property
    def emulator(self) -> Emulator:
        return self.server.emulator  # type: ignore[attr-defined]

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _json(self, data: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, exc: Exception) -> None:
        self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/diagnostics":
            try:
                self._json(self.emulator.diagnostics())
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
            self._json(self.emulator.snapshot(source, base, size))
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
                self.emulator.set_key(state, code, matrix_low, matrix_high)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--firmware", type=Path, default=DEFAULT_FIRMWARE)
    parser.add_argument("--mask-rom", type=Path)
    parser.add_argument("--soc-rom", type=Path)
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
        "--nand-save-on-exit", type=Path,
        help=("save the complete live NAND data/OOB checkpoint on exit and "
              "enable the Web save button"),
    )
    parser.add_argument(
        "--boot-mode", choices=("firmware", "usb", "burn", "driver"),
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
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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
    if args.nand_save_on_exit is not None:
        args.nand_save_on_exit = args.nand_save_on_exit.resolve()
        args.nand_save_on_exit.parent.mkdir(parents=True, exist_ok=True)
    if args.boot_mode == "usb" and args.usb_loader is None:
        raise SystemExit("--boot-mode usb requires --usb-loader")
    if args.boot_mode == "burn" and args.burn_code is None:
        raise SystemExit("--boot-mode burn requires --burn-code")
    if args.boot_mode == "driver" and args.driver_code is None:
        raise SystemExit("--boot-mode driver requires --driver-code")
    emulator = Emulator(
        qemu=args.qemu, firmware=args.firmware,
        mask_rom=args.mask_rom, soc_rom=args.soc_rom,
        usb_loader=args.usb_loader, burn_code=args.burn_code,
        driver_code=args.driver_code, nand_image=args.nand_image,
        nand_checkpoint=args.nand_checkpoint,
        boot_mode=args.boot_mode,
        rom_hle=args.rom_hle or args.hle_ui,
        hle_ui=args.hle_ui,
        startup_context=args.startup_context,
        adc_level=args.adc_level,
        external_power=args.external_power,
        soc_rom_skeleton=args.soc_rom_skeleton,
        log_unimp=args.log_unimp,
        icount_shift=args.icount_shift,
        nand_save_on_exit=args.nand_save_on_exit,
        start_paused=bool(
            args.debug_program_load or args.initial_key_matrix_low or
            args.initial_key_matrix_high
        ),
    )
    for address, path in args.debug_program_load:
        emulator.load_program(address, path.resolve())
    if args.initial_key_matrix_low or args.initial_key_matrix_high:
        emulator.set_key(
            0, 0,
            args.initial_key_matrix_low & 0xFFFFFFFF,
            args.initial_key_matrix_high & 0xFFFFFFFF,
        )
    if (args.debug_program_load or args.initial_key_matrix_low or
            args.initial_key_matrix_high):
        emulator.qmp.execute("cont")
    server = ThreadingHTTPServer((args.host, args.port), RequestHandler)
    server.emulator = emulator  # type: ignore[attr-defined]
    server.shutdown_token = args.shutdown_token  # type: ignore[attr-defined]

    stopping = threading.Event()

    def stop(_signum=None, _frame=None):
        if not stopping.is_set():
            stopping.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    print(f"NP560+ Web frontend: http://{args.host}:{args.port}")
    print(f"QEMU log: {emulator.log_path}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        emulator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
