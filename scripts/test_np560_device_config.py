#!/usr/bin/env python3
"""Check persistent-device selection and input protections, without guest writes."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web import np560_web as web
from web.device_config import create_device, load_device


class DeviceConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.inputs = {}
        for key in ("qemu", "firmware", "soc_rom", "nand_checkpoint"):
            path = self.root / (key + ".bin")
            path.write_bytes((key + " fixture").encode())
            self.inputs[key] = path
        self.config = self.root / "my device" / "device.json"

    def create(self):
        args = web.parse_args([])
        for key, value in self.inputs.items():
            setattr(args, key, value)
        args.boot_mode = "firmware-vma03"
        args.soc_rom_skeleton = True
        args.icount_shift = 5
        create_device(self.config, args)
        return args

    def update(self, mutate):
        data = json.loads(self.config.read_text(encoding="utf-8"))
        mutate(data)
        self.config.write_text(json.dumps(data), encoding="utf-8")

    def test_create_is_small_and_never_copies_or_changes_seed(self):
        self.create()
        self.assertEqual([p.name for p in self.config.parent.iterdir()], ["device.json"])
        self.assertLess(self.config.stat().st_size, 4096)
        self.assertEqual(self.inputs["nand_checkpoint"].read_bytes(), b"nand_checkpoint fixture")
        data = json.loads(self.config.read_text())
        self.assertEqual(data["inputs"]["nand_checkpoint"]["path"], "../nand_checkpoint.bin")

    def test_same_device_reuses_journal_across_launches_and_working_directories(self):
        self.create()
        first = web.parse_args(["--device", str(self.config), "--port", "0"])
        first.nand_journal.write_bytes(b"journal fixture")
        previous_directory = Path.cwd()
        try:
            os.chdir(self.root.parent)
            second = web.parse_args(["--device=" + str(self.config), "--port", "8911"])
        finally:
            os.chdir(previous_directory)
        self.assertEqual(first.nand_journal, second.nand_journal)
        self.assertEqual(first.device_identity, second.device_identity)
        self.assertEqual(second.nand_checkpoint, self.inputs["nand_checkpoint"])
        self.assertEqual(second.nand_journal.read_bytes(), b"journal fixture")
        self.assertEqual(second.boot_mode, "firmware-vma03")
        self.assertEqual(second.icount_shift, 5)
        self.assertFalse(second.rom_hle)
        self.assertFalse(second.hle_ui)
        self.assertIsNone(second.nand_save_on_exit)

    def test_create_refuses_to_replace_existing_configuration_or_journal(self):
        args = self.create()
        original = self.config.read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            create_device(self.config, args)
        self.assertEqual(self.config.read_bytes(), original)
        other = self.root / "other.json"
        other.with_suffix(".npj").write_bytes(b"existing")
        with self.assertRaisesRegex(ValueError, "unused journal"):
            create_device(other, args)
        self.assertFalse(other.exists())
        self.assertEqual(other.with_suffix(".npj").read_bytes(), b"existing")

    def test_device_rejects_explicit_bound_options_even_if_value_is_default(self):
        self.create()
        for extra in (["--rom-hle"], ["--adc-level=8"], ["--nand-journal", "other"],
                      ["--boot-mode", "firmware"], ["--startup-context", "0"],
                      ["--nand-save-on-exit", str(self.config)],
                      ["--initial-key-matrix-low", "0"]):
            with self.subTest(extra=extra), patch.object(web.sys, "stderr"), \
                    self.assertRaises(SystemExit) as error:
                web.parse_args(["--device", str(self.config)] + extra)
            self.assertEqual(error.exception.code, 2)

    def test_all_immutable_input_hashes_checked_before_starting_guest(self):
        self.create()
        for key in ("firmware", "soc_rom", "nand_checkpoint"):
            original = self.inputs[key].read_bytes()
            self.inputs[key].write_bytes(bytes([original[0] ^ 1]) + original[1:])
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_device(self.config, web.parse_args([]))
            self.inputs[key].write_bytes(original)

    def test_explicit_core_upgrade_does_not_change_saved_device(self):
        self.create()
        original = self.config.read_bytes()
        replacement = self.root / "new-qemu"
        replacement.write_bytes(b"new core")
        args = web.parse_args(["--device", str(self.config), "--qemu", str(replacement)])
        self.assertEqual(args.qemu, replacement)
        self.assertEqual(self.config.read_bytes(), original)

    def test_journal_and_lock_cannot_alias_any_input_or_config(self):
        self.create()
        original = self.config.read_bytes()
        for target in (*self.inputs.values(), self.config):
            self.config.write_bytes(original)
            self.update(lambda data: data.update(journal=str(target)))
            with self.assertRaisesRegex(ValueError, "must not overwrite"):
                load_device(self.config, web.parse_args([]))
        self.config.write_bytes(original)
        alias = self.config.with_suffix(".npj")
        try:
            os.link(self.inputs["nand_checkpoint"], alias)
        except OSError:
            self.skipTest("hard links unavailable")
        with self.assertRaisesRegex(ValueError, "must not overwrite"):
            load_device(self.config, web.parse_args([]))

    def test_missing_used_journal_does_not_silently_boot_from_seed(self):
        self.create()
        self.config.with_suffix(".npj.lock").touch()
        with self.assertRaisesRegex(ValueError, "journal is missing"):
            load_device(self.config, web.parse_args([]))

    def test_stable_lock_cannot_be_a_hardlink_to_an_input(self):
        self.create()
        try:
            os.link(self.inputs["firmware"], self.config.with_suffix(".npj.lock"))
        except OSError:
            self.skipTest("hard links unavailable")
        with self.assertRaisesRegex(ValueError, "must not overwrite"):
            load_device(self.config, web.parse_args([]))

    def test_invalid_schema_settings_and_partial_json_fail_closed(self):
        self.create()
        original = self.config.read_bytes()
        for mutate in (lambda d: d.update(schema="future"),
                       lambda d: d.update(extra="unexpected"),
                       lambda d: d["settings"].update(adc_level=True),
                       lambda d: d["settings"].update(boot_mode="burn"),
                       lambda d: d["inputs"]["firmware"].update(path="x,y")):
            self.config.write_bytes(original)
            self.update(mutate)
            with self.assertRaises(ValueError):
                load_device(self.config, web.parse_args([]))
        self.config.write_bytes(b'{"schema":')
        with self.assertRaises(ValueError):
            load_device(self.config, web.parse_args([]))

    def test_config_creation_exits_without_spawning_qemu(self):
        args = self.create()
        args.create_device = self.root / "second.json"
        with patch.object(web, "parse_args", return_value=args), \
                patch.object(web, "run_server") as server:
            self.assertEqual(web.main(), 0)
        server.assert_not_called()


if __name__ == "__main__":
    unittest.main()
