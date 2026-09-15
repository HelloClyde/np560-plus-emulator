"""Offline, byte-preserving device backups; never boot or modify a guest."""

from __future__ import annotations

from contextlib import contextmanager, ExitStack
import ctypes
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import zipfile

from .device_config import INPUTS, file_identity, load_device, stored_path


SCHEMA = "np560-device-backup-v1"
FILES = {"firmware": "firmware.prg", "soc_rom": "soc_rom.bin",
         "nand_checkpoint": "nand.nand", "journal": "device.npj"}
CHUNK = 1024 * 1024


def require_posix():
    if os.name != "posix":
        raise ValueError("Use the Windows PowerShell entry point (WSL); POSIX locks are required")


def publish_new(source: Path, destination: Path):
    """Atomic publication, with NO replacement even if the destination races us."""
    require_posix()
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameat2", None)
    if rename is None:
        raise ValueError("Atomic no-replace publication requires Linux renameat2")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                       ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1):
        code = ctypes.get_errno()
        if code not in (errno.EINVAL, errno.ENOTSUP, errno.ENOSYS):
            raise OSError(code, os.strerror(code), str(destination))
        # DrvFS does not implement RENAME_NOREPLACE. Hard-link publication
        # is exclusive for files. For directories use Windows' native,
        # no-overwrite Directory.Move on the same Windows volume.
        if source.is_file():
            os.link(source, destination)
            source.unlink()
            return
        powershell = shutil.which("powershell.exe")
        if not powershell:
            raise ValueError("This filesystem needs Windows Directory.Move for safe restore publication")
        helper = Path(__file__).resolve().parent.parent / "move-np560-restored-device.ps1"
        paths = [subprocess.check_output(["wslpath", "-w", str(p)], text=True).strip()
                 for p in (helper, source, destination)]
        if any(not re.match(r"^[A-Za-z]:\\", p) for p in paths):
            raise ValueError("Windows publication is limited to local Windows drive paths")
        result = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", paths[0],
                                 "-Source", paths[1], "-Destination", paths[2]], capture_output=True, text=True)
        if result.returncode:
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(errno.EEXIST, "Restore destination appeared during publication", str(destination))
            raise ValueError("Windows restore publication failed: " + result.stderr.strip())


@contextmanager
def locked_journal(path: Path):
    """Same byte-range locks as QEMU, not the unrelated BSD flock protocol."""
    require_posix()
    import fcntl

    with ExitStack() as stack:
        handles = []
        for candidate in (Path(str(path) + ".lock"), path):
            try:
                fd = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW)
            except FileNotFoundError as error:
                raise ValueError("Backup requires an initialized saved device; "
                                 "start and normally close it first") from error
            stream = stack.enter_context(os.fdopen(fd, "rb"))
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or (
                    candidate != path and (before.st_size or before.st_nlink != 1)):
                raise ValueError("Device journal/sidecar is not a valid regular file")
            try:
                fcntl.lockf(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("Device is in use; close it before backing up") from error
            current = candidate.stat()
            if (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino):
                raise ValueError("Device journal changed while acquiring its lock; retry")
            handles.append(stream)
        # Do not reopen/close either inode while these POSIX locks are held:
        # closing ANY descriptor for an inode drops that process's record lock.
        yield handles[1]


def same_file_state(a, b):
    return (a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns) == (
        b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns)


def pack_file(archive, name, path, stream, *, expected=None, nand=False):
    before = os.fstat(stream.fileno())
    digest = hashlib.sha256()
    payload = hashlib.sha256()
    header = b""
    count = 0
    stream.seek(0)
    with archive.open(name, "w", force_zip64=True) as output:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            digest.update(chunk)
            if nand:
                if not count:
                    header = chunk[:64]
                    payload.update(chunk[64:])
                else:
                    payload.update(chunk)
            output.write(chunk)
            count += len(chunk)
    if not same_file_state(before, os.fstat(stream.fileno())) or not same_file_state(before, path.stat()):
        raise ValueError(f"Device file changed during backup: {path}")
    identity = {"size": count, "sha256": digest.hexdigest()}
    if expected is not None and identity != {k: expected[k] for k in identity}:
        raise ValueError(f"Device input no longer matches its configuration: {path}")
    return identity, header, payload.digest()


def journal_base_header(nand_header, payload_digest, nand_size):
    if len(nand_header) != 64 or nand_header[:8] != b"NP560N1\0":
        raise ValueError("Backup requires a complete NP560 NAND checkpoint")
    version, header_size, data, oob, block_pages, blocks = struct.unpack_from("<6I", nand_header, 8)
    data_size, oob_size = struct.unpack_from("<2Q", nand_header, 32)
    pages = block_pages * blocks
    if (version != 1 or header_size != 64 or not all((data, oob, block_pages, blocks)) or
            pages > 0xFFFFFFFF or data_size != pages * data or oob_size != pages * oob or
            nand_size != 64 + data_size + oob_size):
        raise ValueError("Invalid NAND checkpoint geometry")
    return b"NP560J1\0" + struct.pack("<6I", 1, data, oob, pages, block_pages, 0) + payload_digest


def backup_device(config_path: Path, destination: Path, *, qemu=None):
    require_posix()
    config_path = config_path.resolve()
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Backup destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise ValueError("Backup parent directory must already exist")
    original = config_path.read_bytes()
    if len(original) > 65536:
        raise ValueError("Device configuration is too large")
    args = SimpleNamespace(qemu=qemu)
    load_device(config_path, args, qemu_override=qemu is not None)
    if config_path.read_bytes() != original:
        raise ValueError("Device configuration changed during validation")
    config = json.loads(original.decode("utf-8-sig"))
    core_identity = file_identity(args.qemu)
    # Metadata is normalized to a portable layout; no absolute archive paths.
    for key in INPUTS:
        config["inputs"][key]["path"] = "media/" + FILES[key]
    config["journal"] = "media/" + FILES["journal"]
    manifest = {"schema": SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(),
                "device": config, "source_qemu": core_identity}
    with locked_journal(args.nand_journal) as journal:
        with tempfile.TemporaryDirectory(prefix=".np560-backup-", dir=destination.parent) as temporary:
            partial = Path(temporary) / "device.zip"
            with zipfile.ZipFile(partial, "x", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=3, allowZip64=True) as archive:
                for key in INPUTS:
                    path = getattr(args, key)
                    with path.open("rb") as stream:
                        identity, header, payload = pack_file(
                            archive, FILES[key], path, stream,
                            expected=config["inputs"][key], nand=key == "nand_checkpoint")
                    if key == "nand_checkpoint":
                        expected_header = journal_base_header(header, payload, identity["size"])
                journal.seek(0)
                if journal.read(64) != expected_header:
                    raise ValueError("Journal header/base identity does not match this device")
                manifest["journal"], _, _ = pack_file(
                    archive, FILES["journal"], args.nand_journal, journal)
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            if config_path.read_bytes() != original:
                raise ValueError("Device configuration changed during backup")
            with partial.open("rb") as stream:
                os.fsync(stream.fileno())
            publish_new(partial, destination)
    return {"backup": str(destination), "device_id": config["id"],
            "archive": file_identity(destination), "journal": manifest["journal"]}


def checked_identity(entry):
    if (not isinstance(entry, dict) or type(entry.get("size")) is not int or entry["size"] <= 0 or
            not isinstance(entry.get("sha256"), str) or not re.fullmatch("[0-9a-f]{64}", entry["sha256"])):
        raise ValueError("Invalid backup member identity")
    return {k: entry[k] for k in ("size", "sha256")}


def restore_device(source: Path, destination: Path, *, qemu: Path):
    require_posix()
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Restore destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise ValueError("Restore parent directory must already exist")
    qemu = qemu.resolve()
    if not qemu.is_file():
        raise ValueError("Select an installed QEMU core; backups contain device data, not executables")
    with zipfile.ZipFile(source, "r") as archive:
        members = archive.infolist()
        if len(members) != 5 or {i.filename for i in members} != {*FILES.values(), "manifest.json"}:
            raise ValueError("Unexpected, duplicate or missing archive member")
        if any(i.is_dir() or stat.S_ISLNK(i.external_attr >> 16) or i.flag_bits & 1 for i in members):
            raise ValueError("Encrypted archives, directories and links are not device backups")
        if archive.getinfo("manifest.json").file_size > 65536:
            raise ValueError("Backup manifest is too large")
        manifest = json.loads(archive.read("manifest.json"))
        if (not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA or
                set(manifest) != {"schema", "created_utc", "device", "source_qemu", "journal"}):
            raise ValueError("Unsupported backup manifest")
        config = manifest["device"]
        if (not isinstance(config, dict) or not isinstance(config.get("inputs"), dict) or
                set(config["inputs"]) != set(INPUTS) or config.get("journal") != "media/device.npj"):
            raise ValueError("Invalid portable device layout")
        identities = {}
        for key in INPUTS:
            identities[key] = checked_identity(config["inputs"][key])
            if config["inputs"][key].get("path") != "media/" + FILES[key]:
                raise ValueError("Invalid portable input path")
        identities["journal"] = checked_identity(manifest["journal"])
        for key, identity in identities.items():
            if archive.getinfo(FILES[key]).file_size != identity["size"]:
                raise ValueError("Archive member size does not match manifest")
        needed = sum(i["size"] for i in identities.values()) + 32 * CHUNK
        if needed > shutil.disk_usage(destination.parent).free:
            raise ValueError("Insufficient disk space for a complete restored device")
        with tempfile.TemporaryDirectory(prefix=".np560-restore-", dir=destination.parent) as temporary:
            staging = Path(temporary)
            media = staging / "media"
            media.mkdir()
            for key, identity in identities.items():
                digest = hashlib.sha256()
                count = 0
                # Fixed member names only; never extract a supplied path.
                with archive.open(FILES[key]) as incoming, (media / FILES[key]).open("xb") as output:
                    for chunk in iter(lambda: incoming.read(CHUNK), b""):
                        count += len(chunk)
                        if count > identity["size"]:
                            raise ValueError("Archive member exceeds declared size")
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if count != identity["size"] or digest.hexdigest() != identity["sha256"]:
                    raise ValueError(f"Backup hash mismatch: {key}")
            # A lock is process state, not archived data. Recreate the empty
            # stable sidecar in this NEW device, never in the source device.
            (media / "device.npj.lock").touch(exist_ok=False)
            config["qemu"] = stored_path(destination, qemu)
            config_path = staging / "device.json"
            with config_path.open("x", encoding="utf-8") as output:
                json.dump(config, output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            load_device(config_path, SimpleNamespace(qemu=qemu), qemu_override=True)
            with (media / FILES["nand_checkpoint"]).open("rb") as seed:
                header = seed.read(64)
                digest = hashlib.sha256()
                for chunk in iter(lambda: seed.read(CHUNK), b""):
                    digest.update(chunk)
            expected_header = journal_base_header(header, digest.digest(), identities["nand_checkpoint"]["size"])
            with (media / FILES["journal"]).open("rb") as journal:
                if journal.read(64) != expected_header:
                    raise ValueError("Restored journal does not belong to the included NAND base")
            # No partial configuration becomes visible if validation fails.
            publish_new(staging, destination)
    return {"device": str(destination / "device.json"), "device_id": config["id"],
            "journal": identities["journal"], "source_qemu": manifest["source_qemu"],
            "selected_qemu": file_identity(qemu)}
