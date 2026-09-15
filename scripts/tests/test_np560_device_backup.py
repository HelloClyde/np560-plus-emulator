#!/usr/bin/env python3
"""Backup data preservation and refusal boundaries; no emulated game claims."""

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from web.device_backup import backup_device, restore_device, publish_new
from web.device_config import create_device, load_device
from web.np560_web import parse_args


@unittest.skipUnless(os.name == "posix", "The production entry uses WSL/POSIX locks")
class DeviceBackupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="np560-backup-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "device workspace 中文"
        self.root.mkdir()
        self.args = parse_args([])
        for key in ("qemu", "firmware", "soc_rom", "nand_checkpoint"):
            path = self.root / (key + ".bin")
            path.write_bytes(key.encode() * 3)
            setattr(self.args, key, path)
        header = bytearray(64)
        header[:8] = b"NP560N1\0"
        struct.pack_into("<6I2Q", header, 8, 1, 64, 2048, 64, 2, 2, 8192, 256)
        payload = bytes(range(256)) * 33
        self.args.nand_checkpoint.write_bytes(header + payload)
        self.args.boot_mode = "firmware-vma03"
        self.args.soc_rom_skeleton = True
        self.config = self.root / "source" / "device.json"
        create_device(self.config, self.args)
        self.journal = self.config.with_suffix(".npj")
        self.journal.write_bytes(b"NP560J1\0" + struct.pack("<6I", 1, 2048, 64, 4, 2, 0) + hashlib.sha256(payload).digest())
        self.lock = Path(str(self.journal) + ".lock")
        self.lock.touch()
        self.archive = self.root / "device.zip"
        self.destination = self.root / "restored"

    def make_backup(self):
        return backup_device(self.config, self.archive)

    def restore(self):
        return restore_device(self.archive, self.destination, qemu=self.args.qemu)

    def rewrite_archive(self, mutate):
        with zipfile.ZipFile(self.archive) as incoming:
            entries = {i.filename: incoming.read(i) for i in incoming.infolist()}
        mutate(entries)
        with zipfile.ZipFile(self.archive, "w", zipfile.ZIP_DEFLATED) as outgoing:
            for name, data in entries.items():
                outgoing.writestr(name, data)

    def test_round_trip_is_portable_and_preserves_every_source_byte(self):
        original = {p: p.read_bytes() for p in (self.config, self.journal, self.lock,
                    *(getattr(self.args, k) for k in ("qemu", "firmware", "soc_rom", "nand_checkpoint")))}
        result = self.make_backup()
        restored = self.restore()
        args = SimpleNamespace()
        identity = load_device(Path(restored["device"]), args)
        self.assertEqual(identity["id"], result["device_id"])
        self.assertEqual(args.nand_journal.read_bytes(), original[self.journal])
        self.assertEqual(args.qemu, self.args.qemu)
        self.assertEqual(args.soc_rom_skeleton, True)
        for key in ("firmware", "soc_rom", "nand_checkpoint"):
            self.assertEqual(getattr(args, key).read_bytes(), original[getattr(self.args, key)])
            self.assertEqual(getattr(args, key).parent, self.destination / "media")
        for path, data in original.items():
            self.assertEqual(path.read_bytes(), data)

    def test_existing_archive_or_device_is_never_overwritten(self):
        self.archive.write_bytes(b"keep archive")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.make_backup()
        self.assertEqual(self.archive.read_bytes(), b"keep archive")
        self.archive.unlink()
        self.make_backup()
        self.destination.mkdir()
        (self.destination / "important").write_bytes(b"keep device")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.restore()
        self.assertEqual((self.destination / "important").read_bytes(), b"keep device")

    def test_publication_race_cannot_replace_an_existing_directory(self):
        self.make_backup()
        def race(source, destination):
            destination.mkdir()
            (destination / "important").write_bytes(b"concurrent owner")
            publish_new(source, destination)
        with patch("web.device_backup.publish_new", side_effect=race), self.assertRaises(FileExistsError):
            self.restore()
        self.assertEqual((self.destination / "important").read_bytes(), b"concurrent owner")
        self.assertFalse((self.destination / "device.json").exists())
        self.assertFalse(list(self.root.glob(".np560-restore-*")))

    def test_active_record_lock_refuses_before_archive_creation(self):
        for path in (self.lock, self.journal):
            code = "import fcntl,sys; f=open(sys.argv[1],'r+b'); fcntl.lockf(f,fcntl.LOCK_EX); print('locked',flush=True); sys.stdin.read()"
            child = subprocess.Popen([sys.executable, "-c", code, str(path)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), "locked")
                self.assertIsNone(child.poll())
                with self.assertRaisesRegex(ValueError, "in use"):
                    self.make_backup()
                self.assertFalse(self.archive.exists())
            finally:
                child.communicate(timeout=5)
            self.assertEqual(child.returncode, 0)

    def test_missing_journal_or_lock_does_not_create_a_false_used_device(self):
        self.lock.unlink()
        self.journal.unlink()
        with self.assertRaisesRegex(ValueError, "initialized"):
            self.make_backup()
        self.assertFalse(self.lock.exists())
        self.assertFalse(self.journal.exists())
        self.assertFalse(self.archive.exists())

    def test_wrong_base_and_source_changes_are_not_packaged(self):
        data = self.journal.read_bytes()
        self.journal.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, "base identity"):
            self.make_backup()
        self.assertFalse(self.archive.exists())
        self.journal.write_bytes(data)
        self.args.firmware.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            self.make_backup()

    def test_member_corruption_is_rejected_without_publishing_partial_device(self):
        self.make_backup()
        self.rewrite_archive(lambda e: e.update({"firmware.prg": bytes([e["firmware.prg"][0] ^ 1]) + e["firmware.prg"][1:]}))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.restore()
        self.assertFalse(self.destination.exists())
        self.assertFalse(list(self.root.glob(".np560-restore-*")))

    def test_hash_consistent_wrong_journal_base_is_also_rejected(self):
        self.make_backup()
        def change(entries):
            data = entries["device.npj"]
            entries["device.npj"] = data[:-1] + bytes([data[-1] ^ 1])
            manifest = json.loads(entries["manifest.json"])
            manifest["journal"]["sha256"] = hashlib.sha256(entries["device.npj"]).hexdigest()
            entries["manifest.json"] = json.dumps(manifest).encode()
        self.rewrite_archive(change)
        with self.assertRaisesRegex(ValueError, "does not belong"):
            self.restore()
        self.assertFalse(self.destination.exists())

    def test_archive_paths_and_manifest_paths_cannot_escape_destination(self):
        self.make_backup()
        original = self.archive.read_bytes()
        self.rewrite_archive(lambda e: e.update({"../escape": b"no"}))
        with self.assertRaisesRegex(ValueError, "archive member"):
            self.restore()
        self.assertFalse((self.root / "escape").exists())
        self.archive.write_bytes(original)
        def change(entries):
            manifest = json.loads(entries["manifest.json"])
            manifest["device"]["inputs"]["firmware"]["path"] = "../escape"
            entries["manifest.json"] = json.dumps(manifest).encode()
        self.rewrite_archive(change)
        with self.assertRaisesRegex(ValueError, "portable input path"):
            self.restore()
        self.assertFalse(self.destination.exists())

    def test_symlink_and_duplicate_zip_members_are_rejected(self):
        self.make_backup()
        original = self.archive.read_bytes()
        with zipfile.ZipFile(self.archive, "a") as outgoing:
            outgoing.writestr("device.npj", b"duplicate")
        with self.assertRaisesRegex(ValueError, "archive member"):
            self.restore()
        self.archive.write_bytes(original)
        with zipfile.ZipFile(self.archive) as incoming:
            entries = {i.filename: incoming.read(i) for i in incoming.infolist()}
        with zipfile.ZipFile(self.archive, "w") as outgoing:
            for name, data in entries.items():
                info = zipfile.ZipInfo(name)
                if name == "device.npj":
                    info.external_attr = 0o120777 << 16
                outgoing.writestr(info, data)
        with self.assertRaisesRegex(ValueError, "links"):
            self.restore()


if __name__ == "__main__":
    unittest.main()
