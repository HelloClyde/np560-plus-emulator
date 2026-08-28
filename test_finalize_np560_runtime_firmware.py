#!/usr/bin/env python3
"""Tests for converting one-shot provisioning PRGs into runtime PRGs."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qemu-dmcu"))

import finalize_np560_runtime_firmware as finalize  # noqa: E402


class FinalizeRuntimeFirmwareTests(unittest.TestCase):
    def provisioned_program(self) -> bytes:
        program = bytearray([0xFF]) * finalize.provision.PROGRAM_SIZE
        finalize.provision.put_words(
            program,
            finalize.provision.LATE_PROVISION_TRIGGER_CALL,
            [
                0xBD00 | (finalize.provision.PROVISION_WRAPPER >> 16),
                finalize.provision.PROVISION_WRAPPER & 0xFFFF,
            ],
        )
        return bytes(program)

    def test_restores_main_resource_call_and_is_idempotent(self) -> None:
        output, manifest = finalize.restore_trigger(
            self.provisioned_program(), "main-resource"
        )
        self.assertTrue(manifest["changed"])
        self.assertEqual(
            finalize.provision.read_words(
                output,
                finalize.provision.LATE_PROVISION_TRIGGER_CALL,
                2,
            ),
            finalize.provision.LATE_PROVISION_TRIGGER_CALL_WORDS,
        )
        second, second_manifest = finalize.restore_trigger(
            output, "main-resource"
        )
        self.assertEqual(second, output)
        self.assertFalse(second_manifest["changed"])
        self.assertFalse(second_manifest["hardware_rom_service"])
        self.assertFalse(second_manifest["host_filesystem_service"])

    def test_rejects_an_unrecognized_trigger_body(self) -> None:
        program = bytearray(self.provisioned_program())
        finalize.provision.put_words(
            program,
            finalize.provision.LATE_PROVISION_TRIGGER_CALL,
            [0xBD01, 0x2345],
        )
        with self.assertRaisesRegex(ValueError, "signature changed"):
            finalize.restore_trigger(bytes(program), "main-resource")


if __name__ == "__main__":
    unittest.main()
