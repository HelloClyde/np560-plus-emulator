"""Offline NAND file bridge regression tests (small synthetic FAT16 volume)."""

import binascii
import hashlib
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.inject_np560_npe_fat16 import directory_entry, encode_short_name
from scripts.web.nand_files import FatFiles, _components, rehash_checkpoint
from scripts.web.np560_web import OfflineFileSession
from scripts.replace_np560_mp3_sample import update as replace_mp3_track


class Volume:
    def __init__(self):
        self.layout = {
            "fat_count": 2, "root_start": 2, "root_sectors": 1,
            "data_start": 3, "sectors_per_cluster": 1, "cluster_bytes": 512,
            "total_sectors": 100,
        }
        self.sectors = {2: bytearray(512), 3: bytearray(512)}
        self.sectors[2][:32] = directory_entry(encode_short_name("游戏"), 0x10, 2)
        self.fats = [bytearray(512), bytearray(512)]
        for fat in self.fats:
            struct.pack_into("<H", fat, 4, 0xFFFF)
        self.finalized = False

    def read_sector(self, lba):
        return bytes(self.sectors.get(lba, bytearray(512)))

    def write_sector(self, lba, data):
        self.sectors[lba] = bytearray(data)

    def read_fat(self, copy_index=0):
        return bytearray(self.fats[copy_index])

    def write_fat(self, fat, copy_index):
        self.fats[copy_index] = bytearray(fat)

    def finalize_allocations(self):
        self.finalized = True


class NandFileTests(unittest.TestCase):
    def test_directory_import_readback_and_no_overwrite(self):
        volume = Volume()
        files = FatFiles(volume)
        report = files.import_file("/游戏", "试玩.NPE", b"NP560 test")
        self.assertEqual(report["size"], 10)
        self.assertEqual(files.read_file("/游戏/试玩.NPE"), b"NP560 test")
        self.assertEqual(volume.fats[0], volume.fats[1])
        self.assertTrue(volume.finalized)
        self.assertEqual(files.list_dir("/游戏")[0]["name"], "试玩.NPE")
        with self.assertRaises(FileExistsError):
            files.import_file("/游戏", "试玩.NPE", b"replace")

    def test_paths_cannot_escape_nand(self):
        for bad in ("", "relative", "/..", "/a/../b", "/a//b", "/a\\b"):
            with self.subTest(path=bad), self.assertRaises(ValueError):
                _components(bad)

    def test_delete_frees_file_and_preserves_sibling(self):
        volume = Volume()
        files = FatFiles(volume)
        files.import_file("/游戏", "旧曲.MP3", b"old" * 300)
        files.import_file("/游戏", "保留.MP3", b"keep")
        files.delete_file("/游戏/旧曲.MP3")
        self.assertEqual(files.read_file("/游戏/保留.MP3"), b"keep")
        self.assertEqual([item["name"] for item in files.list_dir("/游戏")], ["保留.MP3"])
        self.assertEqual(volume.fats[0], volume.fats[1])
        files.import_file("/游戏", "新曲.MP3", b"new" * 300)
        self.assertEqual(files.read_file("/游戏/新曲.MP3"), b"new" * 300)

    def test_replace_mp3_track_updates_crc_and_removes_old_file(self):
        volume = Volume()
        volume.sectors[2][:32] = directory_entry(encode_short_name("MP3"), 0x10, 2)
        files = FatFiles(volume)
        files.import_file("/MP3", "旧曲.MP3", b"old")
        files.import_file("/MP3", "新曲.MP3", b"new")
        playlist = bytearray(3074)
        playlist[4:6] = b"\1\2"
        playlist[6:6 + len(b"0:\\MP3\\" + "旧曲.MP3".encode("gb18030"))] = (
            b"0:\\MP3\\" + "旧曲.MP3".encode("gb18030"))
        playlist[-2:] = binascii.crc_hqx(playlist[:-2], 0).to_bytes(2, "big")
        files.import_file("/MP3", "PLAYLIST.LST", bytes(playlist))
        replace_mp3_track(files, "旧曲.MP3", "新曲.MP3", b"new")
        self.assertEqual(files.read_file("/MP3/新曲.MP3"), b"new")
        with self.assertRaises(FileNotFoundError):
            files.read_file("/MP3/旧曲.MP3")
        result = files.read_file("/MP3/PLAYLIST.LST")
        self.assertIn("新曲.MP3".encode("gb18030"), result)
        self.assertEqual(int.from_bytes(result[-2:], "big"),
                         binascii.crc_hqx(result[:-2], 0))

    def test_rehash_matches_reference_fnv(self):
        def fnv(data):
            value = 2166136261
            for byte in data:
                value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
            return value
        data, oob = b"test NAND data", b"oob\xff"
        header = bytearray(64)
        header[:8] = b"NP560N1\0"
        struct.pack_into("<2Q", header, 32, len(data), len(oob))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tiny.nand"
            path.write_bytes(header + data + oob)
            rehash_checkpoint(path)
            image = path.read_bytes()
        self.assertEqual(struct.unpack_from("<2I", image, 48),
                         (fnv(data), fnv(oob)))
        self.assertEqual(hashlib.sha256(image[64:]).digest(),
                         hashlib.sha256(data + oob).digest())

    def test_confirmed_open_exports_then_stops_guest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = []
            guest = Mock()
            guest.qmp.execute.side_effect = lambda command: events.append(command)
            guest.save_nand.side_effect = lambda path, **kw: (path.write_bytes(b"snapshot"), events.append("save"))
            guest.close.side_effect = lambda: events.append("close")
            lease = Mock()
            server = SimpleNamespace(emulator=guest, key_lease=lease)
            args = SimpleNamespace(device=root / "device.json")
            session = OfflineFileSession(server, args, Mock(), None)
            self.assertEqual(session.open()["mode"], "offline")
            self.assertEqual(events, ["stop", "save", "close"])
            self.assertIsNone(server.emulator)
            lease.close.assert_called_once()
            self.assertTrue(session.checkpoint.is_file())

    def test_dirty_resume_switches_config_and_keeps_original_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "device.json"
            original = {"inputs": {"nand_checkpoint": {"path": "seed.nand",
                         "size": 4, "sha256": "0" * 64}}, "journal": "old.npj"}
            config_path.write_text(json.dumps(original), encoding="utf-8")
            work = root / "file-sessions" / "session"
            work.mkdir(parents=True)
            checkpoint = work / "system.nand"
            checkpoint.write_bytes(b"new snapshot")
            args = SimpleNamespace(device=config_path, nand_checkpoint=root / "seed.nand",
                nand_journal=root / "old.npj", device_identity={"id": "test"},
                run_log_dir=root / "runs")
            server = SimpleNamespace(emulator=None, key_lease=None)
            session = OfflineFileSession(server, args, Mock(), None)
            session.mode = "offline"
            session.dirty = True
            session.checkpoint = checkpoint
            session.directory = work
            guest = Mock()
            with patch("scripts.web.np560_web.RunJournal"), \
                    patch("scripts.web.np560_web.start_emulator", return_value=guest), \
                    patch("scripts.web.np560_web.KeyInputLease", return_value=Mock()):
                result = session.resume()
            self.assertEqual(result["mode"], "online")
            self.assertEqual(args.nand_checkpoint, checkpoint)
            self.assertEqual(json.loads(config_path.read_text(encoding="utf-8"))["inputs"]
                             ["nand_checkpoint"]["size"], len(b"new snapshot"))
            backups = list(root.glob("device.json.before-files-*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8")), original)


if __name__ == "__main__":
    unittest.main()
