"""Persistent device inputs; no guest-state injection or NAND image rewriting."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import uuid

try:
    from .rom_bundle import NPE_ENTRY_OFFSETS
except ImportError:  # Direct scripts/web execution.
    from rom_bundle import NPE_ENTRY_OFFSETS


SCHEMA = "np560-device-v3"
PREVIOUS_SCHEMA = "np560-device-v2"
LEGACY_SCHEMA = "np560-device-v1"
INPUTS = ("firmware", "soc_rom", "nand_checkpoint")
LEGACY_SETTINGS = ("boot_mode", "soc_rom_skeleton", "adc_level", "external_power",
            "icount_shift")
V2_RUNTIME_DEFAULTS = {"rom_mp3_hle_base": 0, "rom_mp3_arena_image": 0,
                       "instruction_clock": False, "realtime": False}
RUNTIME_DEFAULTS = {**V2_RUNTIME_DEFAULTS, "rom_npe_codec_owned": False}
V2_SETTINGS = LEGACY_SETTINGS + tuple(V2_RUNTIME_DEFAULTS)
SETTINGS = LEGACY_SETTINGS + tuple(RUNTIME_DEFAULTS)
# An explicit device binds these options. QEMU upgrades and Web transport/log
# options are still selectable without silently changing the virtual device.
BOUND_FLAGS = {
    "--firmware", "--mask-rom", "--soc-rom", "--soc-rom-skeleton",
    "--usb-loader", "--burn-code", "--driver-code", "--nand-image",
    "--nand-checkpoint", "--nand-journal", "--nand-save-on-exit", "--boot-mode",
    "--rom-hle", "--hle-ui", "--startup-context", "--adc-level",
    "--external-power", "--icount-shift", "--debug-program-load",
    "--initial-key-matrix-low", "--initial-key-matrix-high",
}
RUNTIME_FLAGS = {"--rom-mp3-hle-base", "--rom-mp3-arena-image", "--instruction-clock",
                 "--realtime", "--rom-npe-codec-owned", "--rom-npe-codec-dll",
                 "--rom-npe-codec-socket", "--rom-npe-codec-pythonpath"}


def file_identity(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stat_before = os.fstat(stream.fileno())
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        stat_after = os.fstat(stream.fileno())
    current = path.stat()
    if (stat_before.st_size, stat_before.st_mtime_ns) != (
            stat_after.st_size, stat_after.st_mtime_ns) or (
            current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns
            ) != (stat_after.st_dev, stat_after.st_ino, stat_after.st_size,
                  stat_after.st_mtime_ns):
        raise ValueError(f"Device input changed while hashing: {path}")
    return {"size": stat_after.st_size, "sha256": digest.hexdigest()}


def resolve_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or any(c in value for c in "\x00\r\n,"):
        raise ValueError("Device paths must be nonempty and contain no comma or control newline")
    # Configurations created on Windows can be opened by the WSL bridge.
    # Ask wslpath instead of assuming the distribution's mount layout.
    if os.name != "nt" and PureWindowsPath(value).is_absolute():
        value = subprocess.check_output(
            ["wslpath", "-a", "--", value], text=True).strip()
    path = Path(value)
    return (path if path.is_absolute() else root / path).resolve()


def stored_path(root: Path, path: Path) -> str:
    try:
        return os.path.relpath(path, root).replace("\\", "/")
    except ValueError:  # Different Windows volumes.
        return path.as_posix()


def protect_inputs(config: Path, journal: Path, inputs: list[Path]) -> None:
    for writable in (journal, Path(str(journal) + ".lock")):
        for protected in (config, *inputs):
            if writable.resolve() == protected.resolve() or (
                    writable.exists() and protected.exists() and
                    writable.samefile(protected)):
                raise ValueError(f"Device journal/lock must not overwrite input: {protected}")


def require_npe_gates(path: Path) -> None:
    image = path.read_bytes()
    for entry in NPE_ENTRY_OFFSETS:
        if image[entry:entry + 4] != b"\x00\x0f\x20\xc6":
            raise ValueError(f"NPE-owned device ROM lacks reviewed gate {entry:06x}")


def validate_settings(settings: dict, *, legacy: bool = False,
                      previous: bool = False) -> None:
    expected = LEGACY_SETTINGS if legacy else V2_SETTINGS if previous else SETTINGS
    if not isinstance(settings, dict) or set(settings) != set(expected):
        raise ValueError("Device settings fields do not match schema")
    if settings["boot_mode"] not in ("firmware", "firmware-vma03"):
        raise ValueError("Devices require normal firmware boot, not a diagnostic loader")
    if type(settings["soc_rom_skeleton"]) is not bool:
        raise ValueError("soc_rom_skeleton must be boolean")
    for key, allowed in (("adc_level", range(9)), ("external_power", range(2))):
        if type(settings[key]) is not int or settings[key] not in allowed:
            raise ValueError(f"Invalid device setting: {key}")
    shift = settings["icount_shift"]
    if shift is not None and (type(shift) is not int or shift not in range(21)):
        raise ValueError("Invalid device setting: icount_shift")
    if legacy:
        return
    for key in ("rom_mp3_hle_base", "rom_mp3_arena_image"):
        value = settings[key]
        if type(value) is not int or not 0 <= value <= 0xFFFFFE or value & 1:
            raise ValueError(f"Invalid aligned 24-bit device setting: {key}")
    if settings["rom_mp3_arena_image"] and not settings["rom_mp3_hle_base"]:
        raise ValueError("MP3 arena image requires an HLE base")
    for key in ("instruction_clock", "realtime"):
        if type(settings[key]) is not bool:
            raise ValueError(f"Invalid boolean device setting: {key}")
    if settings["instruction_clock"] and shift != 0:
        raise ValueError("Device instruction_clock requires icount_shift 0")
    if settings["realtime"] and (not settings["instruction_clock"] or shift != 0):
        raise ValueError("Realtime device requires instruction_clock and icount_shift 0")
    if not previous:
        if type(settings["rom_npe_codec_owned"]) is not bool:
            raise ValueError("rom_npe_codec_owned must be boolean")
        if settings["rom_npe_codec_owned"] and not settings["soc_rom_skeleton"]:
            raise ValueError("NPE codec requires a strict SoC ROM skeleton")


def create_device(path: Path, args) -> dict:
    """Create only a small config; the unchanged NAND seed is never copied."""
    path = path.resolve()
    if path.exists() or path.is_symlink():
        raise ValueError(f"Device already exists; use --device to resume: {path}")
    if (args.soc_rom is None or args.nand_checkpoint is None or args.mask_rom or
            args.nand_image or args.nand_save_on_exit or args.usb_loader or
            args.burn_code or args.driver_code or args.rom_hle or args.hle_ui or
            args.startup_context or args.debug_program_load or
            args.initial_key_matrix_low or args.initial_key_matrix_high):
        raise ValueError("Create a device with --soc-rom and --nand-checkpoint; "
                         "diagnostic, HLE, raw NAND and export options are not allowed")
    settings = {key: getattr(args, key) for key in SETTINGS}
    validate_settings(settings)
    qemu = args.qemu.resolve()
    paths = {key: getattr(args, key).resolve() for key in INPUTS}
    if settings["rom_npe_codec_owned"]:
        require_npe_gates(paths["soc_rom"])
    journal = (args.nand_journal or path.with_suffix(".npj")).resolve()
    protect_inputs(path, journal, [qemu, *paths.values()])
    if journal.exists() or journal.is_symlink() or Path(str(journal) + ".lock").exists():
        raise ValueError("A new device requires an unused journal path; "
                         "existing devices must resume with --device")
    for candidate in (qemu, *paths.values()):
        if not candidate.is_file() or candidate.stat().st_size == 0:
            raise ValueError(f"Device input not found: {candidate}")
        resolve_path(path.parent, str(candidate))
    resolve_path(path.parent, str(journal))
    config = {
        "schema": SCHEMA, "id": str(uuid.uuid4()), "name": path.stem,
        "qemu": stored_path(path.parent, qemu),
        "inputs": {key: {"path": stored_path(path.parent, candidate),
                         **file_identity(candidate)}
                   for key, candidate in paths.items()},
        "journal": stored_path(path.parent, journal), "settings": settings,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create never replaces a device or its media. An interrupted
    # config write fails JSON/schema validation on load; it cannot erase NAND.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(config, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return config


def load_device(path: Path, args, *, qemu_override: bool = False,
                runtime_overrides=frozenset()) -> dict:
    """Validate identities before the Web bridge can start a guest or writer."""
    path = path.resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    keys = {"schema", "id", "name", "qemu", "inputs", "journal", "settings"}
    if not isinstance(config, dict) or set(config) != keys or config["schema"] not in (SCHEMA, PREVIOUS_SCHEMA, LEGACY_SCHEMA):
        raise ValueError("Unsupported or incomplete NP560 device configuration")
    if not isinstance(config["id"], str) or str(uuid.UUID(config["id"])) != config["id"]:
        raise ValueError("Device id must be a canonical UUID")
    if not isinstance(config["name"], str) or not config["name"].strip():
        raise ValueError("Device name must be a nonempty string")
    validate_settings(config["settings"], legacy=config["schema"] == LEGACY_SCHEMA,
                      previous=config["schema"] == PREVIOUS_SCHEMA)
    if config["schema"] != LEGACY_SCHEMA and runtime_overrides:
        raise ValueError("Device binds runtime settings; remove overrides: " +
                         ", ".join(sorted(runtime_overrides)))
    if not isinstance(config["inputs"], dict) or set(config["inputs"]) != set(INPUTS):
        raise ValueError("Device requires firmware, SoC ROM and complete NAND checkpoint")
    paths = {}
    for key, entry in config["inputs"].items():
        if (not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"} or
                type(entry["size"]) is not int or entry["size"] <= 0 or
                not isinstance(entry["sha256"], str) or
                re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None):
            raise ValueError(f"Invalid device input identity: {key}")
        candidate = resolve_path(path.parent, entry["path"])
        if not candidate.is_file() or candidate.stat().st_size != entry["size"]:
            raise ValueError(f"Device input missing or changed: {key}: {candidate}")
        if file_identity(candidate)["sha256"] != entry["sha256"]:
            raise ValueError(f"Device input hash mismatch: {key}: {candidate}")
        paths[key] = candidate
    if config["settings"].get("rom_npe_codec_owned"):
        require_npe_gates(paths["soc_rom"])
    qemu = args.qemu.resolve() if qemu_override else resolve_path(path.parent, config["qemu"])
    if not qemu.is_file():
        raise ValueError(f"Device QEMU not found: {qemu}")
    journal = resolve_path(path.parent, config["journal"])
    protect_inputs(path, journal, [qemu, *paths.values()])
    if not journal.exists() and Path(str(journal) + ".lock").exists():
        raise ValueError("Device journal is missing but its lock sidecar remains; "
                         "restore the saved journal instead of resetting this device")
    # V1 never recorded these flags. Preserve its explicit legacy overrides;
    # do not infer or rewrite missing addresses from firmware bytes.
    runtime = {key: getattr(args, key, default) for key, default in RUNTIME_DEFAULTS.items()}
    for key, value in {**paths, **runtime, **config["settings"], "qemu": qemu,
                       "nand_journal": journal}.items():
        setattr(args, key, value)
    return {"id": config["id"], "name": config["name"], "config": str(path),
            "journal": str(journal), "nand_checkpoint": str(paths["nand_checkpoint"])}
