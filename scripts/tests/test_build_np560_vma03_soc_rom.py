from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_np560_vma03_soc_rom import (
    EXPECTED_PREFIX,
    LEGACY_ROM01_LOADER_WORDS,
    PROVISIONAL_AUDIO_RETURNS,
    RETS,
    ROM01_POST_CLOCK_ADDRESS,
    SKELETON_HOLE,
    VMA03_CAPACITY_INSTALLER_ADDRESS,
    VMA03_CAPACITY_WRAPPER_ADDRESS,
    VMA03_FILE_CALLBACK_CHILD_ADDRESS,
    VMA03_FILE_CALLBACK_INSTALLER_ADDRESS,
    VMA03_FILE_CALLBACK_WRAPPER_ADDRESS,
    VMA03_NAND_PACK_SPARE_ADDRESS,
    VMA03_NAND_PREPARE_READ_ADDRESS,
    VMA03_NAND_UNPACK_FULL_ADDRESS,
    VMA03_NAND_UNPACK_SPARE_ADDRESS,
    VMA03_PIM_PATH,
    VMA03_PIM_PATH_FP_OFFSET,
    VMA03_PIM_PATH_LOOKUP_VENEER_ADDRESS,
    VMA03_PIM_PROVISION_FILTER_ADDRESS,
    VMA03_PIM_PROVISION_WRAPPER_ADDRESS,
    VMA03_PIM_PROVISION_WRITER_ADDRESS,
    VMA03_PIM_PROVISION_TRIGGER_ADDRESS,
    build,
    retire_legacy_source_repair,
    vma03_bootstrap_words,
    vma03_capacity_installer_words,
    vma03_pim_path_lookup_veneer_words,
    vma03_pim_provision_filter_words,
    vma03_pim_provision_wrapper_words,
    vma03_pim_provision_writer_words,
    words_to_bytes,
)
from scripts import build_np560_reconstructed_rom as reconstructed
from scripts.inject_np560_minimal_pim import MINIMAL_PIM


class Vma03SocRomTests(unittest.TestCase):
    def test_legacy_rom01_loader_becomes_a_strict_hole_with_bootstrap(self) -> None:
        payload = bytearray([0x5A]) * 0x110000
        payload[
            ROM01_POST_CLOCK_ADDRESS:
            ROM01_POST_CLOCK_ADDRESS + len(EXPECTED_PREFIX)
        ] = EXPECTED_PREFIX
        repair_address = reconstructed.APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_INSTALLER_ADDRESS
        repair = words_to_bytes(reconstructed.operation_modal_source_repair_installer_words())
        payload[repair_address:repair_address + len(repair)] = repair
        capacity_installer = vma03_capacity_installer_words()
        capacity_wrapper = reconstructed.storage_unit_open_capacity_wrapper_words(
            VMA03_CAPACITY_WRAPPER_ADDRESS
        )
        file_callback_installer = (
            reconstructed.file_driver_callback_installer_words(
                VMA03_FILE_CALLBACK_WRAPPER_ADDRESS
            )
        )
        file_callback_child = reconstructed.file_driver_callback_child_words()
        file_callback_wrapper = reconstructed.file_driver_callback_wrapper_words(
            VMA03_FILE_CALLBACK_CHILD_ADDRESS
        )
        nand_prepare = reconstructed.prepare_logical_read_words()
        nand_pack = reconstructed.pack_logical_spare_words()
        nand_unpack = reconstructed.unpack_logical_spare_words(
            VMA03_NAND_UNPACK_FULL_ADDRESS
        )
        nand_unpack_full = reconstructed.unpack_full_logical_page_words()
        for address, words in (
            (VMA03_CAPACITY_INSTALLER_ADDRESS, capacity_installer),
            (VMA03_CAPACITY_WRAPPER_ADDRESS, capacity_wrapper),
            (VMA03_FILE_CALLBACK_INSTALLER_ADDRESS, file_callback_installer),
            (VMA03_FILE_CALLBACK_CHILD_ADDRESS, file_callback_child),
            (VMA03_FILE_CALLBACK_WRAPPER_ADDRESS, file_callback_wrapper),
            (VMA03_NAND_PREPARE_READ_ADDRESS, nand_prepare),
            (VMA03_NAND_PACK_SPARE_ADDRESS, nand_pack),
            (VMA03_NAND_UNPACK_SPARE_ADDRESS, nand_unpack),
            (VMA03_NAND_UNPACK_FULL_ADDRESS, nand_unpack_full),
        ):
            payload[address:address + len(words) * 2] = (
                SKELETON_HOLE * len(words)
            )
        payload[0x02BBF6:0x02BBF6 + len(reconstructed.read_page_words()) * 2] = (
            words_to_bytes(reconstructed.read_page_words())
        )
        payload[0x02BCC6:0x02BCC6 + len(reconstructed.program_page_words()) * 2] = (
            words_to_bytes(reconstructed.program_page_words())
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.bin"
            output = root / "output.bin"
            manifest = root / "output.json"
            source.write_bytes(payload)
            build(source, output, manifest)
            patched = output.read_bytes()

            loader_end = (
                ROM01_POST_CLOCK_ADDRESS + LEGACY_ROM01_LOADER_WORDS * 2
            )
            bootstrap = words_to_bytes(vma03_bootstrap_words())
            expected_loader = bytearray(
                bootstrap
                + SKELETON_HOLE
                * (LEGACY_ROM01_LOADER_WORDS - len(bootstrap) // 2)
            )
            for address in PROVISIONAL_AUDIO_RETURNS:
                relative = address - ROM01_POST_CLOCK_ADDRESS
                expected_loader[relative:relative + 2] = RETS
            expected = bytearray(payload)
            expected[repair_address:repair_address + len(repair)] = (
                SKELETON_HOLE * (len(repair) // 2)
            )
            expected[ROM01_POST_CLOCK_ADDRESS:loader_end] = expected_loader
            expected[
                VMA03_CAPACITY_INSTALLER_ADDRESS:
                VMA03_CAPACITY_INSTALLER_ADDRESS + len(capacity_installer) * 2
            ] = words_to_bytes(capacity_installer)
            expected[
                VMA03_CAPACITY_WRAPPER_ADDRESS:
                VMA03_CAPACITY_WRAPPER_ADDRESS + len(capacity_wrapper) * 2
            ] = words_to_bytes(capacity_wrapper)
            for address, words in (
                (VMA03_FILE_CALLBACK_INSTALLER_ADDRESS,
                 file_callback_installer),
                (VMA03_FILE_CALLBACK_CHILD_ADDRESS, file_callback_child),
                (VMA03_FILE_CALLBACK_WRAPPER_ADDRESS, file_callback_wrapper),
                (VMA03_NAND_PREPARE_READ_ADDRESS, nand_prepare),
                (VMA03_NAND_PACK_SPARE_ADDRESS, nand_pack),
                (VMA03_NAND_UNPACK_SPARE_ADDRESS, nand_unpack),
                (VMA03_NAND_UNPACK_FULL_ADDRESS, nand_unpack_full),
            ):
                expected[address:address + len(words) * 2] = words_to_bytes(words)
            expected[
                0x02BBF6:
                0x02BBF6 + len(reconstructed.read_page_words()) * 2
            ] = words_to_bytes(reconstructed.read_page_words(
                VMA03_NAND_PREPARE_READ_ADDRESS,
                VMA03_NAND_UNPACK_SPARE_ADDRESS,
            ))
            expected[
                0x02BCC6:
                0x02BCC6 + len(reconstructed.program_page_words()) * 2
            ] = words_to_bytes(reconstructed.program_page_words(
                VMA03_NAND_PACK_SPARE_ADDRESS
            ))
            self.assertEqual(patched, expected)
            self.assertEqual(
                patched[
                    VMA03_CAPACITY_INSTALLER_ADDRESS:
                    VMA03_CAPACITY_INSTALLER_ADDRESS + len(capacity_installer) * 2
                ],
                words_to_bytes(capacity_installer),
            )
            self.assertEqual(
                patched[
                    VMA03_CAPACITY_WRAPPER_ADDRESS:
                    VMA03_CAPACITY_WRAPPER_ADDRESS + len(capacity_wrapper) * 2
                ],
                words_to_bytes(capacity_wrapper),
            )
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            retired = metadata["legacy_loader_retirement"]
            self.assertEqual(retired["address"], "01:0200")
            self.assertEqual(retired["end_exclusive"], "01:6B1A")
            self.assertEqual(retired["words"], LEGACY_ROM01_LOADER_WORDS)
            self.assertEqual(
                retired["entry_replacement"],
                "SCALL 25:5858; RETS",
            )
            storage = metadata["vma03_storage_bootstrap"]
            self.assertEqual(storage["storage_registry"], "25:5858")
            self.assertEqual(storage["capacity_installer"], "02:5100")
            self.assertEqual(storage["file_callback_wrapper"], "02:5840")
            nand = metadata["vma03_nand_helpers"]
            self.assertEqual(nand["prepare_read"], "02:6000")
            self.assertEqual(nand["unpack_full"], "02:6400")
            self.assertEqual(
                [item["address"] for item in metadata["provisional_audio_returns"]],
                ["01:4674", "01:46CC", "01:46D0"],
            )
            self.assertFalse(metadata["checkpoint_provisioning"]["enabled"])
            self.assertFalse(metadata["legacy_source_repair_retirement"]["services_implemented"])

    def test_source_repair_retirement_preserves_surroundings_and_missing_entries(self) -> None:
        address = reconstructed.APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_INSTALLER_ADDRESS
        body = words_to_bytes(reconstructed.operation_modal_source_repair_installer_words())
        self.assertEqual(len(body), 5402)
        output = bytearray(b"\x5a" * (address + len(body) + 16))
        output[address:address + len(body)] = body
        before = bytes(output)
        metadata = retire_legacy_source_repair(output)
        self.assertEqual(output[:address], before[:address])
        self.assertEqual(output[address + len(body):], before[address + len(body):])
        self.assertEqual(output[address:address + len(body)], SKELETON_HOLE * (len(body) // 2))
        self.assertEqual(metadata["end_exclusive"], "01:C51A")
        for entry in (0x01B6DE, 0x01B7AA, 0x01B816, 0x01B84E):
            self.assertEqual(output[entry:entry + 2], SKELETON_HOLE)

    def test_source_repair_retirement_refuses_unrecognized_bytes_without_mutation(self) -> None:
        address = reconstructed.APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_INSTALLER_ADDRESS
        body = words_to_bytes(reconstructed.operation_modal_source_repair_installer_words())
        output = bytearray(b"\x5a" * (address + len(body)))
        output[address:] = body
        output[0x01B6DE] ^= 1
        before = bytes(output)
        with self.assertRaisesRegex(ValueError, "source-repair installer signature"):
            retire_legacy_source_repair(output)
        self.assertEqual(output, before)

    def test_one_shot_pim_provisioning_uses_guest_resident_api(self) -> None:
        self.assertEqual(
            vma03_bootstrap_words(provision_minimal_pim=True),
            [
                0xBD25, 0x5858,
                *reconstructed.write_program_words(
                    VMA03_PIM_PROVISION_TRIGGER_ADDRESS,
                    [
                        0xBD00 | (VMA03_PIM_PROVISION_FILTER_ADDRESS >> 16),
                        VMA03_PIM_PROVISION_FILTER_ADDRESS & 0xFFFF,
                    ],
                ),
                reconstructed.RETS,
            ],
        )

        call_filter = vma03_pim_provision_filter_words()
        arm_patch = reconstructed.write_program_words(
            VMA03_PIM_PROVISION_TRIGGER_ADDRESS,
            [
                0xBD00 | (VMA03_PIM_PROVISION_WRAPPER_ADDRESS >> 16),
                VMA03_PIM_PROVISION_WRAPPER_ADDRESS & 0xFFFF,
            ],
        )
        self.assertEqual(call_filter[:5], [
            0x2E00, 0x780B, 0x0006, 0x560E, 0xAC02,
        ])
        self.assertEqual(
            call_filter[5],
            (VMA03_PIM_PROVISION_FILTER_ADDRESS +
             (6 + len(arm_patch)) * 2) & 0xFFFF,
        )
        self.assertIn(
            arm_patch,
            [call_filter[index:index + len(arm_patch)]
             for index in range(len(call_filter) - len(arm_patch) + 1)],
        )

        wrapper = vma03_pim_provision_wrapper_words()
        self.assertEqual(
            wrapper[:5],
            [0x2E10, 0x780B, 0x0006, 0x5608, 0xAC02],
        )
        self.assertEqual(
            wrapper[5],
            (VMA03_PIM_PROVISION_WRAPPER_ADDRESS +
             (len(wrapper) - 11) * 2) & 0xFFFF,
        )
        self.assertIn(
            [0x4800, 0x58F0],
            [wrapper[index:index + 2] for index in range(len(wrapper) - 1)],
        )
        for target in (
            0x1F1F1A,
            VMA03_PIM_PROVISION_WRITER_ADDRESS,
            0x24EAEC,
            0x1E6444,
        ):
            self.assertIn(
                [0xBD00 | (target >> 16), target & 0xFFFF],
                [wrapper[index:index + 2]
                 for index in range(len(wrapper) - 1)],
            )
        path = (VMA03_PIM_PATH.encode("gb18030") + b"\0").ljust(32, b"\0")
        self.assertIn(
            [
                0x68F0, int.from_bytes(path[:2], "big"),
                0x6A0B, VMA03_PIM_PATH_FP_OFFSET & 0xFFFF,
            ],
            [wrapper[index:index + 4]
             for index in range(len(wrapper) - 3)],
        )

        writer = vma03_pim_provision_writer_words()
        self.assertEqual(writer[0], 0x2E25)
        self.assertEqual(
            writer[1:5],
            [
                0x68F0, int.from_bytes(MINIMAL_PIM[:2], "big"),
                0x6A0B, (-len(MINIMAL_PIM)) & 0xFFFF,
            ],
        )
        self.assertIn(
            [0xBD17, 0xE3EE, 0x50FC],
            [writer[index:index + 3]
             for index in range(len(writer) - 2)],
        )
        veneer = vma03_pim_path_lookup_veneer_words()
        self.assertLess(
            VMA03_PIM_PROVISION_FILTER_ADDRESS + len(call_filter) * 2,
            VMA03_PIM_PROVISION_WRITER_ADDRESS,
        )
        self.assertLess(
            VMA03_PIM_PROVISION_WRITER_ADDRESS + len(writer) * 2,
            VMA03_PIM_PATH_LOOKUP_VENEER_ADDRESS,
        )
        self.assertLess(
            VMA03_PIM_PATH_LOOKUP_VENEER_ADDRESS + len(veneer) * 2,
            VMA03_PIM_PROVISION_WRAPPER_ADDRESS,
        )


if __name__ == "__main__":
    unittest.main()
