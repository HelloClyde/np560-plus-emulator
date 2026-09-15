from __future__ import annotations

import hashlib
import unittest

from scripts import build_np560_reconstructed_rom as rom
from scripts import patch_np560_rom01_modal_callback_closure as modal_patch


def words_at(image: bytes, address: int, count: int) -> list[int]:
    return [
        int.from_bytes(image[offset : offset + 2], "little")
        for offset in range(address, address + count * 2, 2)
    ]


class ReconstructedRomTests(unittest.TestCase):
    def test_main_action_buffer_prepare_is_exact_closed_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_MAIN_ACTION_BUFFER_PREPARE_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_ACTION_BUFFER_PREPARE_OVERLAY_SIZE,
        )
        self.assertEqual(
            source[:5], [0x2E03, 0x58F0, 0x58F1, 0x58F2, 0x58F3]
        )
        self.assertEqual(
            source[-8:],
            [0xBD31, 0x4BAC, 0x383F, 0x382F,
             0x381F, 0x380F, 0x2F00, rom.RETS],
        )

        expected = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MAIN_ACTION_BUFFER_PREPARE_OVERLAY_DESTINATION,
            rom.APPLICATION_MAIN_ACTION_BUFFER_PREPARE_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_ACTION_BUFFER_PREPARE_OVERLAY_SIZE,
        )
        installer = rom.install_application_main_chain_words()
        self.assertIn(
            expected,
            [installer[index:index + len(expected)]
             for index in range(len(installer) - len(expected) + 1)],
        )

    def test_npe_loader_context_init_fills_exact_flat_collision_gap(
        self,
    ) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_NPE_LOADER_CONTEXT_INIT_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_LOADER_CONTEXT_INIT_OVERLAY_SIZE,
        )
        flat = rom.program_source_words(
            rom.APPLICATION_NPE_LOADER_CONTEXT_INIT_OVERLAY_DESTINATION,
            rom.APPLICATION_NPE_LOADER_CONTEXT_INIT_OVERLAY_SIZE,
        )

        self.assertEqual(
            (rom.APPLICATION_NPE_LOADER_CONTEXT_INIT_OVERLAY_DESTINATION +
             rom.APPLICATION_NPE_LOADER_CONTEXT_INIT_OVERLAY_SIZE),
            rom.APPLICATION_MAIN_ACTION_RENDER_LINE_LINKED_DESTINATION,
        )
        self.assertEqual(
            rom.APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_DESTINATION,
            0x5FCF38,
        )
        self.assertEqual(source[:3], [0x2E00, 0x58F0, 0x58F1])
        self.assertEqual(source[-4:], [0x381F, 0x380F, 0x2F00, rom.RETS])
        self.assertEqual(
            [(source[index], source[index + 1])
             for index in range(len(source) - 1)
             if source[index] >> 8 == 0xBD],
            [(0xBD03, 0x406C), (0xBD2E, 0xCDB4)],
        )
        self.assertNotEqual(flat[0], 0x2E00)

        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_NPE_LOADER_CONTEXT_INIT_OVERLAY_DESTINATION,
            rom.APPLICATION_NPE_LOADER_CONTEXT_INIT_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_LOADER_CONTEXT_INIT_OVERLAY_SIZE,
        )
        installer = rom.install_application_main_chain_words()
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        modules = {
            item["destination"]: item
            for item in rom.manifest(b"")["application_main_chain"]
        }
        self.assertEqual(modules["32:CEEE"]["source"], "4F:CEEE")
        self.assertEqual(modules["32:CEEE"]["bytes"], 0x004A)
        self.assertEqual(
            modules["32:CEEE"]["status"],
            "exact same-PC guest function",
        )

    def test_npe_post_context_loader_closure_uses_exact_same_pc_bodies(
        self,
    ) -> None:
        specs = (
            (
                rom.APPLICATION_NPE_LOADER_PREPARE_OVERLAY_DESTINATION,
                rom.APPLICATION_NPE_LOADER_PREPARE_OVERLAY_SOURCE,
                rom.APPLICATION_NPE_LOADER_PREPARE_OVERLAY_SIZE,
                [0x2E0C, 0x58F1, 0x58F2, 0x58F3],
                [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
            ),
            (
                rom.APPLICATION_NPE_LOADER_MODE_OVERLAY_DESTINATION,
                rom.APPLICATION_NPE_LOADER_MODE_OVERLAY_SOURCE,
                rom.APPLICATION_NPE_LOADER_MODE_OVERLAY_SIZE,
                [0x2E02, 0x58F0, 0x58F1, 0x58F2],
                [0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
            ),
            (
                rom.APPLICATION_NPE_OPERATION7_OVERLAY_DESTINATION,
                rom.APPLICATION_NPE_OPERATION7_OVERLAY_SOURCE,
                rom.APPLICATION_NPE_OPERATION7_OVERLAY_SIZE,
                [0x2E16, 0x58F0, 0x58F1, 0x780B],
                [0x2FF2, 0x381F, 0x380F, 0x2F00, rom.RETS],
            ),
            (
                rom.APPLICATION_NPE_OPERATION7_DECODE_OVERLAY_DESTINATION,
                rom.APPLICATION_NPE_OPERATION7_DECODE_OVERLAY_SOURCE,
                rom.APPLICATION_NPE_OPERATION7_DECODE_OVERLAY_SIZE,
                [0x2E13, 0x58F2, 0x58F3, 0x58F4],
                [0x384F, 0x383F, 0x382F, 0x2F00, rom.RETS],
            ),
        )

        installer = rom.install_application_main_chain_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(b"")["application_main_chain"]
        }

        for destination, source_address, size, prefix, suffix in specs:
            source = rom.program_source_words(source_address, size)
            flat = rom.program_source_words(destination, size)
            self.assertEqual(source[:len(prefix)], prefix)
            self.assertEqual(source[-len(suffix):], suffix)
            self.assertNotEqual(flat[0], prefix[0])

            descriptor = rom.copy_code_to_overlay_words(
                destination, source_address, size,
            )
            self.assertIn(
                descriptor,
                [installer[index:index + len(descriptor)]
                 for index in range(len(installer) - len(descriptor) + 1)],
            )

            key = f"{destination >> 16:02X}:{destination & 0xFFFF:04X}"
            self.assertEqual(
                modules[key]["source"],
                f"{source_address >> 16:02X}:{source_address & 0xFFFF:04X}",
            )
            self.assertEqual(modules[key]["bytes"], size)

        table_index = (0x034154 - rom.ROM03_JUMP_TABLE_ADDRESS) // 2
        self.assertEqual(
            rom.resident_rom03_jump_table_words()[table_index:table_index + 2],
            [0xAD31, 0x71D2],
        )

    def test_npe_bitmap_decoder_is_closed_and_relocated(self) -> None:
        state_dispatch = rom.program_source_words(
            rom.APPLICATION_NPE_STATE_DISPATCH_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_STATE_DISPATCH_OVERLAY_SIZE,
        )
        self.assertEqual(
            state_dispatch[:4], [0x2E07, 0x58F1, 0x58F2, 0x58F3],
        )
        self.assertEqual(
            state_dispatch[-6:],
            [0x4800, 0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_NPE_STATE_DISPATCH_LINKED_DESTINATION, 2,
            )[0],
            0x2E49,
        )
        state_dispatch_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_NPE_STATE_DISPATCH_OVERLAY_DESTINATION,
            rom.APPLICATION_NPE_STATE_DISPATCH_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_STATE_DISPATCH_OVERLAY_SIZE,
        )
        installer = rom.install_application_main_chain_words()
        self.assertIn(
            state_dispatch_descriptor,
            [installer[index:index + len(state_dispatch_descriptor)]
             for index in range(
                 len(installer) - len(state_dispatch_descriptor) + 1
             )],
        )

        classifier = rom.program_source_words(
            rom.APPLICATION_NPE_STREAM_CLASSIFY_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_STREAM_CLASSIFY_OVERLAY_SIZE,
        )
        self.assertEqual(classifier[:2], [0x2E01, 0x58F1])
        self.assertEqual(
            classifier[-3:], [0x381F, 0x2F00, rom.RETS],
        )
        self.assertNotEqual(
            rom.program_source_words(
                rom.APPLICATION_NPE_STREAM_CLASSIFY_LINKED_DESTINATION, 2,
            )[0],
            0x2E01,
        )
        classifier_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_NPE_STREAM_CLASSIFY_OVERLAY_DESTINATION,
            rom.APPLICATION_NPE_STREAM_CLASSIFY_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_STREAM_CLASSIFY_OVERLAY_SIZE,
        )
        self.assertIn(
            classifier_descriptor,
            [installer[index:index + len(classifier_descriptor)]
             for index in range(
                 len(installer) - len(classifier_descriptor) + 1
             )],
        )

        source = rom.program_source_words(
            rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_OVERLAY_SIZE,
        )
        self.assertEqual(source[:3], [0x2E1C, 0x58F2, 0x58F3])
        self.assertEqual(
            source[-8:],
            [0x780B, 0xFFD4, 0x781B, 0xFFD6,
             0x383F, 0x382F, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_OVERLAY_DESTINATION,
            0x5F716C,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_OVERLAY_DESTINATION,
            rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_OVERLAY_SIZE,
        )
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )

        child = rom.program_source_words(
            rom.APPLICATION_NPE_BITMAP_CONTEXT_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_BITMAP_CONTEXT_OVERLAY_SIZE,
        )
        self.assertEqual(child[:4], [0x2E03, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(
            child[-5:], [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
        )

        node_transfer = rom.program_source_words(
            rom.APPLICATION_NPE_NODE_TRANSFER_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_NODE_TRANSFER_OVERLAY_SIZE,
        )
        self.assertEqual(
            node_transfer[:6],
            [0x2E08, 0x58F1, 0x58F2, 0x58F3, 0x58F4, 0x58F5],
        )
        self.assertEqual(
            node_transfer[-7:],
            [0x385F, 0x384F, 0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_NPE_NODE_TRANSFER_OVERLAY_DESTINATION,
            rom.APPLICATION_NPE_NODE_TRANSFER_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_NODE_TRANSFER_OVERLAY_SIZE,
        )
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )

    def test_resident_root_desktop_policy_is_guest_side_and_opt_in(self) -> None:
        strict = rom.install_application_main_chain_words()
        reconstructed = rom.install_application_main_chain_words(
            reconstruct_resident_root_desktop=True,
        )

        for destination, source in rom.RESIDENT_ROOT_DESKTOP_PATH_WRITES:
            self.assertEqual(rom.program_source_words(source, 2), [0x4801])
            patch = rom.write_program_words(destination, (0x4800,))
            self.assertFalse(any(
                strict[index:index + len(patch)] == patch
                for index in range(len(strict) - len(patch) + 1)
            ))
            self.assertTrue(any(
                reconstructed[index:index + len(patch)] == patch
                for index in range(len(reconstructed) - len(patch) + 1)
            ))

    def test_resident_application_guard_forwards_event_far_pointers(self) -> None:
        guard = rom.resident_application_state_guard_words()

        self.assertEqual(guard, [
            0x2E05, 0x58F1, 0x58F3,
            0x6810, 0x00A2,
            0x88F0, 0x2AA4,
            0x5600,
            0xAC02, 0xF76E,
            0x780B, 0x000A,
            0x781B, 0x000C,
            0x58F1, 0x58F0,
            0x780B, 0x0006,
            0x781B, 0x0008,
            0x58F1, 0x58F0,
            0xBD46, 0x3DD2,
            0x50F8,
            0x383F, 0x381F, 0x2F00, rom.RETS,
            0x383F, 0x381F, 0x2F00,
            0xAD3B, 0xF734,
        ])

    def test_known_entries_and_reserved_gaps(self) -> None:
        image = rom.build_image()

        self.assertEqual(words_at(image, 0x02B9E2, 1), [rom.RETS])
        self.assertEqual(words_at(image, 0x02BAC4, 1), [rom.RETS])
        self.assertEqual(words_at(image, 0x02BAC6, 1), [rom.RESERVED])
        self.assertEqual(words_at(image, 0x02BAC8, 1), [rom.RETS])
        self.assertEqual(words_at(image, 0x02BB1E, 1), [0x4804])
        self.assertEqual(words_at(image, 0x02BBF6, 2), [0x780F, 0x0004])
        self.assertEqual(words_at(image, 0x02BCC6, 2), [0x780F, 0x0004])
        self.assertEqual(words_at(image, 0x02BDD6, 2), [0x781F, 0x0004])
        self.assertEqual(words_at(image, 0x02BE5C, 2), [0x780F, 0x0004])
        self.assertEqual(words_at(image, 0x02BF56, 2), [0x780F, 0x0004])
        self.assertEqual(
            words_at(image, 0x02C04C, 2),
            rom.mov_gpr_from_mmio(0, rom.NAND_ERROR)[:2],
        )
        self.assertEqual(words_at(image, 0x030030, 2), [0xAD03, 0x0100])
        self.assertEqual(
            words_at(image, 0x030080, 2),
            rom.resident_event_loop_words()[:2],
        )
        self.assertEqual(words_at(image, 0x030100, 2), [
            0xBD00 | (rom.DEFAULT_OVERLAY_INSTALLER_ADDRESS >> 16),
            rom.DEFAULT_OVERLAY_INSTALLER_ADDRESS & 0xFFFF,
        ])
        installer = rom.default_overlay_installer_words()
        self.assertEqual(
            words_at(image, rom.DEFAULT_OVERLAY_INSTALLER_ADDRESS,
                     len(installer)),
            installer,
        )
        self.assertEqual(installer[-1], rom.RETS)
        self.assertEqual(
            words_at(image, rom.CLEAR_OVERLAY_ADDRESS, 2),
            [0x780F, 0x0004],
        )
        self.assertEqual(
            # The exact relocated 33:5ABA leaf occupies 06:1CF0..1CFD.
            # Its one-word alignment gap immediately before the clear helper
            # remains reserved.
            words_at(image, rom.CLEAR_OVERLAY_ADDRESS - 0x0002, 1),
            [rom.RESERVED],
        )

    def test_rom0b_ccd2_zero_status_probe_is_opt_in(self) -> None:
        flow = {
            "initializer_overlay_probe": True,
            "probe_rom_08_return": True,
            "probe_rom_01_return": True,
            "probe_system_main": True,
            "probe_resident_app_state_guard": True,
            "probe_storage_global_templates": True,
        }
        strict = rom.build_image(**flow)
        probe = rom.build_image(**flow, probe_rom_0b_ccd2_zero=True)

        self.assertEqual(
            words_at(strict, rom.RESIDENT_ROM0B_CCD2_ADDRESS, 3),
            [rom.RESERVED, rom.RESERVED, rom.RESERVED],
        )
        self.assertEqual(
            words_at(probe, rom.RESIDENT_ROM0B_CCD2_ADDRESS, 3),
            [0x4800, 0x4810, rom.RETS],
        )
        description = rom.manifest(
            probe, **flow, probe_rom_0b_ccd2_zero=True
        )["resident_rom0b_ccd2_probe"]
        self.assertEqual(description["result"], "RB1=0")

    def test_storage_record_callback_is_exact_embedded_overlay(self) -> None:
        source = rom.program_source_words(
            rom.STORAGE_RECORD_CALLBACK_OVERLAY_SOURCE,
            rom.STORAGE_RECORD_CALLBACK_OVERLAY_SIZE,
        )
        self.assertEqual(source[0], 0x2E00)
        self.assertEqual(source[-3:], [0x381F, 0x2F00, rom.RETS])

        service = rom.program_source_words(
            rom.STORAGE_RECORD_CALLBACK_SERVICE_OVERLAY_SOURCE,
            rom.STORAGE_RECORD_CALLBACK_SERVICE_OVERLAY_SIZE,
        )
        self.assertEqual(service, [0x2E00, 0x2F00, rom.RETS])

        capacity_service = rom.storage_record_capacity_service_words()
        self.assertEqual(capacity_service[:3], [0x2E00, 0x58F2, 0x58F3])
        self.assertEqual(capacity_service[3:5], [
            0xBD00 | (
                rom.STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_DESTINATION >> 16
            ),
            rom.STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_DESTINATION & 0xFFFF,
        ])
        self.assertEqual(
            capacity_service[-4:], [0x383F, 0x382F, 0x2F00, rom.RETS]
        )
        capacity_wrapper = rom.storage_record_capacity_wrapper_words()
        self.assertEqual(capacity_wrapper[:3], [0x2E00, 0xBD5F, 0x13F8])
        self.assertEqual(capacity_wrapper[-2:], [0x2F00, rom.RETS])
        capacity_child = rom.program_source_words(
            rom.STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_SOURCE,
            rom.STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_SIZE,
        )
        self.assertEqual(
            capacity_child[:5], [0x2E00, 0x58F1, 0x58F3, 0x58F6, 0x58F7]
        )
        self.assertEqual(
            capacity_child[-6:],
            [0x387F, 0x386F, 0x383F, 0x381F, 0x2F00, rom.RETS],
        )

        post_lookup = rom.program_source_words(
            rom.STORAGE_RECORD_POST_LOOKUP_OVERLAY_SOURCE,
            rom.STORAGE_RECORD_POST_LOOKUP_OVERLAY_SIZE,
        )
        self.assertEqual(post_lookup[:3], [0x2E00, 0x58F0, 0x58F1])
        self.assertIn(
            [0xBD28, 0x1F08],
            [post_lookup[index:index + 2]
             for index in range(len(post_lookup) - 1)],
        )
        self.assertEqual(post_lookup[-2:], [0x2F00, rom.RETS])

        worker = rom.program_source_words(
            rom.STORAGE_UNIT_WORKER_OVERLAY_SOURCE,
            rom.STORAGE_UNIT_WORKER_OVERLAY_SIZE,
        )
        self.assertEqual(worker[:4], [0x2E04, 0x58F1, 0x58F2, 0x58F3])
        self.assertIn(
            [0xBD31, 0xCBE8],
            [worker[index:index + 2]
             for index in range(len(worker) - 1)],
        )
        self.assertEqual(
            worker[-5:], [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS]
        )
        packed = rom.program_source_words(
            rom.STORAGE_PACKED_FIELD_OVERLAY_SOURCE,
            rom.STORAGE_PACKED_FIELD_OVERLAY_SIZE,
        )
        self.assertEqual(packed[:3], [0x2E04, 0x58F2, 0x58F3])
        self.assertEqual(packed[-4:], [0x383F, 0x382F, 0x2F00, rom.RETS])

        for source_address, size, link in (
            (rom.STORAGE_SECONDARY_DRIVER_OVERLAY_SOURCE,
             rom.STORAGE_SECONDARY_DRIVER_OVERLAY_SIZE, 0x2E01),
            (rom.STORAGE_PRIMARY_READER_OVERLAY_SOURCE,
             rom.STORAGE_PRIMARY_READER_OVERLAY_SIZE, 0x2E01),
            (rom.STORAGE_TRANSFER_WORKER_OVERLAY_SOURCE,
             rom.STORAGE_TRANSFER_WORKER_OVERLAY_SIZE, 0x2E05),
            (rom.STORAGE_PRIMARY_TRANSFER_OVERLAY_SOURCE,
             rom.STORAGE_PRIMARY_TRANSFER_OVERLAY_SIZE, 0x2E05),
            (rom.STORAGE_PRIMARY_SECTOR_READ_OVERLAY_SOURCE,
             rom.STORAGE_PRIMARY_SECTOR_READ_OVERLAY_SIZE, 0x2E07),
            (rom.STORAGE_NAND_STATUS_OVERLAY_SOURCE,
             rom.STORAGE_NAND_STATUS_OVERLAY_SIZE, 0x2E01),
            (rom.STORAGE_BLOCK_TRANSFER_OVERLAY_SOURCE,
             rom.STORAGE_BLOCK_TRANSFER_OVERLAY_SIZE, 0x2E08),
        ):
            source_words = rom.program_source_words(source_address, size)
            self.assertEqual(source_words[0], link)
            self.assertEqual(
                source_words[-5:],
                [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
            )

        installer = rom.application_region_extra_installer_words()
        for destination, source_address, size in (
            (rom.STORAGE_RECORD_CALLBACK_OVERLAY_DESTINATION,
             rom.STORAGE_RECORD_CALLBACK_OVERLAY_SOURCE,
             rom.STORAGE_RECORD_CALLBACK_OVERLAY_SIZE),
            (rom.STORAGE_RECORD_CALLBACK_SERVICE_OVERLAY_DESTINATION,
             rom.STORAGE_RECORD_CALLBACK_SERVICE_OVERLAY_SOURCE,
             rom.STORAGE_RECORD_CALLBACK_SERVICE_OVERLAY_SIZE),
            (rom.STORAGE_RECORD_POST_LOOKUP_OVERLAY_DESTINATION,
             rom.STORAGE_RECORD_POST_LOOKUP_OVERLAY_SOURCE,
             rom.STORAGE_RECORD_POST_LOOKUP_OVERLAY_SIZE),
        ):
            embedded = rom.embed_program_overlay_words(
                destination, source_address, size
            )
            self.assertIn(
                embedded,
                [installer[index:index + len(embedded)]
                 for index in range(len(installer) - len(embedded) + 1)],
            )

        capacity_installer_call = [
            0xBD00 | (rom.STORAGE_RECORD_CAPACITY_INSTALLER_ADDRESS >> 16),
            rom.STORAGE_RECORD_CAPACITY_INSTALLER_ADDRESS & 0xFFFF,
        ]
        loader = rom.rom01_application_loader_words()
        first_capacity_call = next(
            index for index in range(len(loader) - 1)
            if loader[index:index + 2] == capacity_installer_call
        )
        first_storage_call = next(
            index for index in range(len(loader) - 1)
            if loader[index:index + 2] == [0xBD25, 0x5858]
        )
        self.assertLess(first_capacity_call, first_storage_call)
        capacity_installer = rom.storage_record_capacity_installer_words()
        capacity_child_install = rom.copy_code_to_overlay_words(
            rom.STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_DESTINATION,
            rom.STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_SOURCE,
            rom.STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_SIZE,
        )
        self.assertIn(
            capacity_child_install,
            [capacity_installer[index:index + len(capacity_child_install)]
             for index in range(
                 len(capacity_installer) - len(capacity_child_install) + 1
             )],
        )
        capacity_service_install = rom.write_program_words(
            rom.STORAGE_RECORD_CAPACITY_SERVICE_OVERLAY_DESTINATION,
            capacity_service,
        )
        self.assertIn(
            capacity_service_install,
            [capacity_installer[index:index + len(capacity_service_install)]
             for index in range(
                 len(capacity_installer) - len(capacity_service_install) + 1
             )],
        )
        capacity_wrapper_install = rom.write_program_words(
            rom.STORAGE_RECORD_CAPACITY_WRAPPER_OVERLAY_DESTINATION,
            capacity_wrapper,
        )
        self.assertIn(
            capacity_wrapper_install,
            [capacity_installer[index:index + len(capacity_wrapper_install)]
             for index in range(
                 len(capacity_installer) - len(capacity_wrapper_install) + 1
            )],
        )
        unit_open_wrapper = rom.storage_unit_open_capacity_wrapper_words()
        self.assertEqual(unit_open_wrapper[:6], [
            0x2E00, 0x58F1, 0x1F10, 0x780B, 0x0006, 0x5600,
        ])
        self.assertIn(
            [0xBD30, 0xA3C2],
            [unit_open_wrapper[index:index + 2]
             for index in range(len(unit_open_wrapper) - 1)],
        )
        self.assertEqual(
            unit_open_wrapper[-4:],
            [0x1F90, 0x381F, 0x2F00, rom.RETS],
        )
        unit_open_patch = rom.write_program_words(
            rom.STORAGE_UNIT_OPEN_CAPACITY_CALL,
            [
                0xBD00 | (rom.STORAGE_UNIT_OPEN_CAPACITY_WRAPPER_ADDRESS >> 16),
                rom.STORAGE_UNIT_OPEN_CAPACITY_WRAPPER_ADDRESS & 0xFFFF,
            ],
        )
        self.assertIn(
            unit_open_patch,
            [capacity_installer[index:index + len(unit_open_patch)]
             for index in range(
                 len(capacity_installer) - len(unit_open_patch) + 1
            )],
        )
        self.assertEqual(capacity_installer[-1], rom.RETS)

        for destination, source_address, size in (
            (rom.STORAGE_PRIMARY_READER_OVERLAY_DESTINATION,
             rom.STORAGE_PRIMARY_READER_OVERLAY_SOURCE,
             rom.STORAGE_PRIMARY_READER_OVERLAY_SIZE),
            (rom.STORAGE_PRIMARY_TRANSFER_OVERLAY_DESTINATION,
             rom.STORAGE_PRIMARY_TRANSFER_OVERLAY_SOURCE,
             rom.STORAGE_PRIMARY_TRANSFER_OVERLAY_SIZE),
            (rom.STORAGE_PRIMARY_SECTOR_READ_OVERLAY_DESTINATION,
             rom.STORAGE_PRIMARY_SECTOR_READ_OVERLAY_SOURCE,
             rom.STORAGE_PRIMARY_SECTOR_READ_OVERLAY_SIZE),
            (rom.STORAGE_NAND_STATUS_OVERLAY_DESTINATION,
             rom.STORAGE_NAND_STATUS_OVERLAY_SOURCE,
             rom.STORAGE_NAND_STATUS_OVERLAY_SIZE),
        ):
            embedded = rom.embed_program_overlay_words(
                destination, source_address, size
            )
            self.assertIn(
                embedded,
                [installer[index:index + len(embedded)]
                 for index in range(len(installer) - len(embedded) + 1)],
            )

        runtime_installer = rom.install_runtime_overlay_words()
        for destination, source_address, size in (
            (rom.STORAGE_UNIT_WORKER_OVERLAY_DESTINATION,
             rom.STORAGE_UNIT_WORKER_OVERLAY_SOURCE,
             rom.STORAGE_UNIT_WORKER_OVERLAY_SIZE),
            (rom.STORAGE_PACKED_FIELD_OVERLAY_DESTINATION,
             rom.STORAGE_PACKED_FIELD_OVERLAY_SOURCE,
             rom.STORAGE_PACKED_FIELD_OVERLAY_SIZE),
            (rom.STORAGE_SECONDARY_DRIVER_OVERLAY_DESTINATION,
             rom.STORAGE_SECONDARY_DRIVER_OVERLAY_SOURCE,
             rom.STORAGE_SECONDARY_DRIVER_OVERLAY_SIZE),
            (rom.STORAGE_PRIMARY_READER_OVERLAY_DESTINATION,
             rom.STORAGE_PRIMARY_READER_OVERLAY_SOURCE,
             rom.STORAGE_PRIMARY_READER_OVERLAY_SIZE),
            (rom.STORAGE_TRANSFER_WORKER_OVERLAY_DESTINATION,
             rom.STORAGE_TRANSFER_WORKER_OVERLAY_SOURCE,
             rom.STORAGE_TRANSFER_WORKER_OVERLAY_SIZE),
            (rom.STORAGE_PRIMARY_TRANSFER_OVERLAY_DESTINATION,
             rom.STORAGE_PRIMARY_TRANSFER_OVERLAY_SOURCE,
             rom.STORAGE_PRIMARY_TRANSFER_OVERLAY_SIZE),
            (rom.STORAGE_PRIMARY_SECTOR_READ_OVERLAY_DESTINATION,
             rom.STORAGE_PRIMARY_SECTOR_READ_OVERLAY_SOURCE,
             rom.STORAGE_PRIMARY_SECTOR_READ_OVERLAY_SIZE),
            (rom.STORAGE_NAND_STATUS_OVERLAY_DESTINATION,
             rom.STORAGE_NAND_STATUS_OVERLAY_SOURCE,
             rom.STORAGE_NAND_STATUS_OVERLAY_SIZE),
            (rom.STORAGE_BLOCK_TRANSFER_OVERLAY_DESTINATION,
             rom.STORAGE_BLOCK_TRANSFER_OVERLAY_SOURCE,
             rom.STORAGE_BLOCK_TRANSFER_OVERLAY_SIZE),
        ):
            copied = rom.copy_code_to_overlay_words(
                destination, source_address, size
            )
            self.assertIn(
                copied,
                [runtime_installer[index:index + len(copied)]
                 for index in range(
                     len(runtime_installer) - len(copied) + 1
                 )],
            )

        modules = {
            item["destination"]: item
            for item in rom.manifest(b"")["nested_system_overlays"]
        }
        self.assertEqual(modules["33:091C"]["source"], "50:091C")
        self.assertEqual(modules["33:091C"]["bytes"], 0x34)
        self.assertEqual(modules["33:6E5E"]["source"], "50:6E5E")
        self.assertEqual(modules["33:6E5E"]["bytes"], 0x06)
        self.assertEqual(modules["33:0070"]["source"], "50:0070")
        self.assertEqual(modules["33:0070"]["bytes"], 0x38)
        self.assertEqual(modules["2C:FE08"]["source"], "49:FE08")
        self.assertEqual(modules["2C:FE08"]["bytes"], 0x1D8)
        self.assertEqual(modules["31:CBE8"]["source"], "4E:CBE8")
        self.assertEqual(modules["31:CBE8"]["bytes"], 0x9C)
        self.assertEqual(modules["32:6EA8"]["source"], "4F:6EA8")
        self.assertEqual(modules["32:6EA8"]["bytes"], 0x6A)
        self.assertEqual(modules["2E:BF9A"]["source"], "4B:BF9A")
        self.assertEqual(modules["2E:BF9A"]["bytes"], 0x16A)
        self.assertEqual(modules["29:05B0"]["source"], "46:05B0")
        self.assertEqual(modules["29:05B0"]["bytes"], 0x2D6)

    def test_storage_driver_overlay_is_retired_after_unit_init(self) -> None:
        cleanup = rom.storage_driver_retire_words()
        copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_DESTINATION,
            rom.STORAGE_DRIVER_RETIRE_PAYLOAD_ADDRESS,
            rom.APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_SIZE,
        )
        self.assertEqual(cleanup[:len(copy)], copy)
        self.assertEqual(
            cleanup[-5:], [0x6810, 0x00A2, 0x88F0, 0x2AE0, rom.RETS]
        )
        self.assertEqual(
            rom.STORAGE_DRIVER_RETIRE_ADDRESS + (len(cleanup) - 1) * 2,
            0x065912,
        )
        self.assertLess(
            rom.STORAGE_DRIVER_RETIRE_ADDRESS + len(cleanup) * 2,
            rom.STORAGE_DRIVER_RETIRE_PAYLOAD_ADDRESS,
        )

        routines = rom.make_routines()
        self.assertEqual(
            routines[rom.STORAGE_DRIVER_RETIRE_ADDRESS][1], cleanup
        )
        self.assertEqual(
            routines[rom.STORAGE_DRIVER_RETIRE_PAYLOAD_ADDRESS][1],
            rom.program_source_words(
                rom.APPLICATION_STORAGE_DRIVER_RESOLVE_ORIGINAL_SOURCE,
                rom.APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_SIZE,
            ),
        )

        installer = rom.install_runtime_overlay_words()
        patch = rom.write_program_words(
            rom.APPLICATION_STORAGE_UNIT_OPEN_RETIRE_CALL_ADDRESS,
            (0xBD00 | (rom.STORAGE_DRIVER_RETIRE_ADDRESS >> 16),
             rom.STORAGE_DRIVER_RETIRE_ADDRESS & 0xFFFF),
        )
        patch_at = next(
            index for index in range(len(installer) - len(patch) + 1)
            if installer[index:index + len(patch)] == patch
        )
        unit_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_STORAGE_UNIT_OPEN_OVERLAY_DESTINATION,
            rom.APPLICATION_STORAGE_UNIT_OPEN_OVERLAY_SOURCE,
            rom.APPLICATION_STORAGE_UNIT_OPEN_OVERLAY_SIZE,
        )
        unit_copy_at = next(
            index for index in range(len(installer) - len(unit_copy) + 1)
            if installer[index:index + len(unit_copy)] == unit_copy
        )
        self.assertGreater(patch_at, unit_copy_at)

    def test_storage_sector_probe_is_relocated_away_from_live_fallthrough(
            self) -> None:
        self.assertEqual(
            rom.APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION,
            0x20F928,
        )
        self.assertEqual(
            rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION,
            0x5FF928,
        )
        old_call = [0xBD20, 0xF928]
        new_call = [0xBD5F, 0xF928]

        routines = rom.make_routines()
        for routine_address, source_address, call_source in (
            (rom.RESIDENT_TRANSFORM_1B_ADDRESS,
             rom.RESIDENT_TRANSFORM_1B_SOURCE,
             rom.RESIDENT_TRANSFORM_1B_SECTOR_PROBE_CALL_SOURCE),
            (rom.RESIDENT_TRANSFORM_1C_ADDRESS,
             rom.RESIDENT_TRANSFORM_1C_SOURCE,
             rom.RESIDENT_TRANSFORM_1C_SECTOR_PROBE_CALL_SOURCE),
            (rom.RESIDENT_RESULT_RECORD_BUILD_ADDRESS,
             rom.RESIDENT_RESULT_RECORD_BUILD_SOURCE,
             rom.RESIDENT_RESULT_RECORD_BUILD_SECTOR_PROBE_CALL_SOURCE),
        ):
            self.assertEqual(
                rom.program_source_words(call_source, 4), old_call
            )
            offset = (call_source - source_address) // 2
            self.assertEqual(
                routines[routine_address][1][offset:offset + 2], new_call
            )

        main_installer = rom.install_application_main_chain_words()
        relocated_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION,
            rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_SOURCE,
            rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_SIZE,
        )
        old_collision = rom.copy_code_to_overlay_words(
            rom.APPLICATION_STORAGE_SECTOR_PROBE_LINKED_DESTINATION,
            rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_SOURCE,
            rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_SIZE,
        )
        self.assertIn(
            relocated_copy,
            [main_installer[i:i + len(relocated_copy)]
             for i in range(len(main_installer) - len(relocated_copy) + 1)],
        )
        self.assertNotIn(
            old_collision,
            [main_installer[i:i + len(old_collision)]
             for i in range(len(main_installer) - len(old_collision) + 1)],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_STORAGE_SECTOR_PROBE_MUL_DIV_CALL_SOURCE, 4
            ),
            [0xBD31, 0xB1FA],
        )
        closed_child_patch = rom.write_program_words(
            rom.APPLICATION_STORAGE_SECTOR_PROBE_MUL_DIV_CALL,
            (0xBD00 | (rom.RESIDENT_STORAGE_MUL_DIV_ADDRESS >> 16),
             rom.RESIDENT_STORAGE_MUL_DIV_ADDRESS & 0xFFFF),
        )
        self.assertIn(
            closed_child_patch,
            [main_installer[i:i + len(closed_child_patch)]
             for i in range(len(main_installer) - len(closed_child_patch) + 1)],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_STORAGE_SECTOR_PROBE_CALLBACK_RETURN_PC_LOAD_SOURCE,
                4,
            ),
            [0x68FE, rom.APPLICATION_STORAGE_SECTOR_PROBE_CALLBACK_RETURN_PC],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_STORAGE_SECTOR_PROBE_CALLBACK_RETURN_SEGMENT_LOAD_SOURCE,
                4,
            ),
            [
                0x68FE,
                rom.APPLICATION_STORAGE_SECTOR_PROBE_CALLBACK_RETURN_SEGMENT,
            ],
        )
        callback_return_segment_patch = rom.write_program_words(
            rom.APPLICATION_STORAGE_SECTOR_PROBE_CALLBACK_RETURN_SEGMENT_LOAD,
            (
                0x68FE,
                rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION >> 16,
            ),
        )
        self.assertIn(
            callback_return_segment_patch,
            [
                main_installer[i:i + len(callback_return_segment_patch)]
                for i in range(
                    len(main_installer) - len(callback_return_segment_patch) + 1
                )
            ],
        )
        self.assertEqual(
            rom.APPLICATION_STORAGE_SECTOR_PROBE_CACHE_LOOKUP_CALLS,
            (
                (0x5FFA1E, 0x3DFA1E),
                (0x5FFB44, 0x3DFB44),
                (0x5FFBB8, 0x3DFBB8),
            ),
        )
        for destination, source in (
                rom.APPLICATION_STORAGE_SECTOR_PROBE_CACHE_LOOKUP_CALLS):
            self.assertEqual(
                rom.program_source_words(source, 4),
                [0xBD33, 0x525E],
            )
            experimental_result_patch = rom.write_program_words(
                destination,
                (0xBD00 | (rom.RESIDENT_STORAGE_RESULT_LEAF_ADDRESS >> 16),
                 rom.RESIDENT_STORAGE_RESULT_LEAF_ADDRESS & 0xFFFF),
            )
            self.assertIn(
                experimental_result_patch,
                [main_installer[i:i + len(experimental_result_patch)]
                 for i in range(
                     len(main_installer) - len(experimental_result_patch) + 1)],
            )

        late_installer = rom.application_region_extra_installer_words()
        for destination, source in (
            (rom.APPLICATION_STORAGE_CAPACITY_SECTOR_PROBE_CALL,
             rom.APPLICATION_STORAGE_CAPACITY_SECTOR_PROBE_CALL_SOURCE),
            (rom.APPLICATION_LAUNCH_RECORD_APPLY_SECTOR_PROBE_CALL,
             rom.APPLICATION_LAUNCH_RECORD_APPLY_SECTOR_PROBE_CALL_SOURCE),
            (rom.APPLICATION_FILE_RECORD_RESOLVE_SECTOR_PROBE_CALL,
             rom.APPLICATION_FILE_RECORD_RESOLVE_SECTOR_PROBE_CALL_SOURCE),
        ):
            self.assertEqual(rom.program_source_words(source, 4), old_call)
            patch = rom.write_program_words(destination, new_call)
            self.assertIn(
                patch,
                [late_installer[i:i + len(patch)]
                 for i in range(len(late_installer) - len(patch) + 1)],
            )

        module = next(
            item for item in rom.manifest(b"")["application_main_chain"]
            if item["destination"] == "5F:F928"
        )
        self.assertEqual(module["linked_destination"], "20:F928")
        self.assertEqual(len(module["caller_patches"]), 6)

    def test_foreground_object_update_is_relocated_from_flat_fallthrough(
            self) -> None:
        self.assertEqual(
            rom.APPLICATION_FOREGROUND_OBJECT_UPDATE_LINKED_DESTINATION,
            0x20E914,
        )
        self.assertEqual(
            rom.APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_DESTINATION,
            0x5FE914,
        )
        source_words = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_SIZE,
        )
        self.assertEqual(source_words[0], 0x2E07)
        self.assertEqual(source_words[-2:], [0x2F00, rom.RETS])

        main_installer = rom.install_application_main_chain_words()
        relocated_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_DESTINATION,
            rom.APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_OBJECT_UPDATE_OVERLAY_SIZE,
        )
        self.assertIn(
            relocated_copy,
            [main_installer[i:i + len(relocated_copy)]
             for i in range(len(main_installer) - len(relocated_copy) + 1)],
        )

        old_call = [0xBD20, 0xE914]
        new_call = [0xBD5F, 0xE914]
        late_installer = rom.application_region_extra_installer_words()
        for destination, source in zip(
            rom.APPLICATION_FOREGROUND_OBJECT_UPDATE_CALLS,
            rom.APPLICATION_FOREGROUND_OBJECT_UPDATE_CALL_SOURCES,
        ):
            self.assertEqual(rom.program_source_words(source, 4), old_call)
            patch = rom.write_program_words(destination, new_call)
            self.assertIn(
                patch,
                [late_installer[i:i + len(patch)]
                 for i in range(len(late_installer) - len(patch) + 1)],
            )

        module = next(
            item for item in rom.manifest(b"")["application_main_chain"]
            if item["destination"] == "5F:E914"
        )
        self.assertEqual(module["linked_destination"], "20:E914")
        self.assertEqual(len(module["caller_patches"]), 3)

    def test_foreground_cursor_range_uses_complete_same_pc_function(
            self) -> None:
        source_words = rom.program_source_words(
            rom.APPLICATION_CURSOR_RANGE_OVERLAY_SOURCE,
            rom.APPLICATION_CURSOR_RANGE_OVERLAY_SIZE,
        )
        self.assertEqual(source_words[0], 0x2E02)
        self.assertEqual(source_words[-2:], [0x2F00, rom.RETS])

        copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_CURSOR_RANGE_OVERLAY_DESTINATION,
            rom.APPLICATION_CURSOR_RANGE_OVERLAY_SOURCE,
            rom.APPLICATION_CURSOR_RANGE_OVERLAY_SIZE,
        )
        installer = rom.install_application_main_chain_words()
        self.assertIn(
            copy,
            [installer[i:i + len(copy)]
             for i in range(len(installer) - len(copy) + 1)],
        )
        module = next(
            item for item in rom.manifest(b"")["application_main_chain"]
            if item["destination"] == "2E:A8B6"
        )
        self.assertEqual(module["source"], "4B:A8B6")
        self.assertEqual(module["bytes"], 0x0170)

    def test_top_level_overlay_includes_adjacent_result_default_selector(
            self) -> None:
        self.assertEqual(rom.APPLICATION_TOP_LEVEL_DISPATCH_SIZE, 0x01B6)
        self.assertEqual(
            rom.APPLICATION_RESULT_DEFAULT_SELECTOR_OFFSET,
            rom.APPLICATION_TOP_LEVEL_DISPATCH_SIZE,
        )
        self.assertEqual(rom.APPLICATION_RESULT_DEFAULT_SELECTOR_SIZE, 0x01B6)
        self.assertEqual(rom.APPLICATION_TOP_LEVEL_OVERLAY_SIZE, 0x036C)

        words = rom.program_source_words(
            rom.APPLICATION_TOP_LEVEL_OVERLAY_SOURCE,
            rom.APPLICATION_TOP_LEVEL_OVERLAY_SIZE,
        )
        selector = rom.APPLICATION_RESULT_DEFAULT_SELECTOR_OFFSET // 2
        self.assertEqual(words[selector], 0x2E1A)
        self.assertEqual(words[-3:], [0x381F, 0x2F00, rom.RETS])

        copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_TOP_LEVEL_OVERLAY_DESTINATION,
            rom.APPLICATION_TOP_LEVEL_OVERLAY_SOURCE,
            rom.APPLICATION_TOP_LEVEL_OVERLAY_SIZE,
        )
        installer = rom.install_application_main_chain_words()
        self.assertIn(
            copy,
            [installer[i:i + len(copy)]
             for i in range(len(installer) - len(copy) + 1)],
        )

    def test_post_modal_state_uses_complete_source_50_wrapper(self) -> None:
        source_words = rom.program_source_words(
            rom.APPLICATION_POST_MODAL_STATE_OVERLAY_SOURCE,
            rom.APPLICATION_POST_MODAL_STATE_OVERLAY_SIZE,
        )
        self.assertEqual(source_words[:3], [0x2E00, 0x58F0, 0x58F1])
        self.assertEqual(source_words[-4:], [0x381F, 0x380F, 0x2F00, rom.RETS])
        flat_words = rom.program_source_words(
            rom.APPLICATION_POST_MODAL_STATE_OVERLAY_DESTINATION,
            rom.APPLICATION_POST_MODAL_STATE_OVERLAY_SIZE,
        )
        self.assertNotEqual(flat_words[0] >> 8, 0x2E)

        installer = rom.application_region_extra_installer_words()
        embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_POST_MODAL_STATE_OVERLAY_DESTINATION,
            rom.APPLICATION_POST_MODAL_STATE_OVERLAY_SOURCE,
            rom.APPLICATION_POST_MODAL_STATE_OVERLAY_SIZE,
        )
        self.assertIn(
            embedded,
            [installer[i:i + len(embedded)]
             for i in range(len(installer) - len(embedded) + 1)],
        )

        module = next(
            item for item in rom.manifest(b"")["application_main_chain"]
            if item["destination"] == "33:21EE"
        )
        self.assertEqual(module["source"], "50:21EE")
        self.assertEqual(module["bytes"], 0x2A)

    def test_far_query_uses_complete_source_50_wrapper(self) -> None:
        source_words = rom.program_source_words(
            rom.APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_SOURCE,
            rom.APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_SIZE,
        )
        self.assertEqual(source_words[:2], [0x2E00, 0x58F1])
        self.assertEqual(source_words[-3:], [0x381F, 0x2F00, rom.RETS])
        self.assertIn(
            [0xBD31, 0xAED0],
            [source_words[i:i + 2] for i in range(len(source_words) - 1)],
        )
        flat_words = rom.program_source_words(
            rom.APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_DESTINATION,
            rom.APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_SIZE,
        )
        self.assertNotEqual(flat_words[0] >> 8, 0x2E)

        installer = rom.application_region_extra_installer_words()
        embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_DESTINATION,
            rom.APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_SOURCE,
            rom.APPLICATION_FAR_QUERY_WRAPPER_OVERLAY_SIZE,
        )
        self.assertIn(
            embedded,
            [installer[i:i + len(embedded)]
             for i in range(len(installer) - len(embedded) + 1)],
        )

    def test_register_quad_convert_uses_complete_source_4e_body(self) -> None:
        source_words = rom.program_source_words(
            rom.APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_SOURCE,
            rom.APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_SIZE,
        )
        self.assertEqual(source_words[:4], [0x0E04, 0x0E15, 0x0E26, 0x0E37])
        self.assertEqual(source_words[4:6], [0xAD31, 0xE286])
        self.assertEqual(
            source_words[-6:],
            [0x386F, 0x385F, 0x384F, 0x383F, 0x382F, rom.RETS],
        )
        flat_words = rom.program_source_words(
            rom.APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_DESTINATION,
            rom.APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_SIZE,
        )
        self.assertNotEqual(flat_words[:4], source_words[:4])

        installer = rom.application_region_extra_installer_words()
        copied = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FLAG_NUMERIC_CHAIN_OVERLAY_DESTINATION,
            rom.APPLICATION_FLAG_NUMERIC_CHAIN_OVERLAY_SOURCE,
            rom.APPLICATION_FLAG_NUMERIC_CHAIN_OVERLAY_SIZE,
        )
        self.assertIn(
            copied,
            [installer[i:i + len(copied)]
             for i in range(len(installer) - len(copied) + 1)],
        )

    def test_flag_report_uses_closed_source_4e_body(self) -> None:
        source_words = rom.program_source_words(
            rom.APPLICATION_FLAG_REPORT_OVERLAY_SOURCE,
            rom.APPLICATION_FLAG_REPORT_OVERLAY_SIZE,
        )
        self.assertEqual(source_words[:4], [0x2E00, 0x58F2, 0xBD33, 0x65D4])
        self.assertEqual(source_words[-3:], [0x382F, 0x2F00, rom.RETS])
        self.assertEqual(
            rom.APPLICATION_FLAG_REPORT_OVERLAY_DESTINATION +
            rom.APPLICATION_FLAG_REPORT_OVERLAY_SIZE,
            rom.APPLICATION_REGISTER_QUAD_CONVERT_OVERLAY_DESTINATION,
        )
        flat_words = rom.program_source_words(
            rom.APPLICATION_FLAG_REPORT_OVERLAY_DESTINATION,
            rom.APPLICATION_FLAG_REPORT_OVERLAY_SIZE,
        )
        self.assertNotEqual(flat_words[:4], source_words[:4])

        installer = rom.application_region_extra_installer_words()
        copied = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FLAG_NUMERIC_CHAIN_OVERLAY_DESTINATION,
            rom.APPLICATION_FLAG_NUMERIC_CHAIN_OVERLAY_SOURCE,
            rom.APPLICATION_FLAG_NUMERIC_CHAIN_OVERLAY_SIZE,
        )
        self.assertIn(
            copied,
            [installer[i:i + len(copied)]
             for i in range(len(installer) - len(copied) + 1)],
        )

    def test_post_modal_refresh_uses_complete_source_4d_body(self) -> None:
        source_words = rom.program_source_words(
            rom.APPLICATION_POST_MODAL_REFRESH_OVERLAY_SOURCE,
            rom.APPLICATION_POST_MODAL_REFRESH_OVERLAY_SIZE,
        )
        self.assertEqual(source_words[:4], [0x2E03, 0x58F1, 0xBD32, 0xCC9C])
        self.assertEqual(
            source_words[-6:], [0xBD30, 0x1EAA, 0x4801, 0x381F, 0x2F00, rom.RETS]
        )
        flat_words = rom.program_source_words(
            rom.APPLICATION_POST_MODAL_REFRESH_OVERLAY_DESTINATION,
            rom.APPLICATION_POST_MODAL_REFRESH_OVERLAY_SIZE,
        )
        self.assertEqual(flat_words[:2], [0xFFD4, 0x782B])
        self.assertNotEqual(flat_words[:4], source_words[:4])

        installer = rom.application_region_extra_installer_words()
        copied = rom.copy_code_to_overlay_words(
            rom.APPLICATION_POST_MODAL_REFRESH_OVERLAY_DESTINATION,
            rom.APPLICATION_POST_MODAL_REFRESH_OVERLAY_SOURCE,
            rom.APPLICATION_POST_MODAL_REFRESH_OVERLAY_SIZE,
        )
        self.assertIn(
            copied,
            [installer[i:i + len(copied)]
             for i in range(len(installer) - len(copied) + 1)],
        )

    def test_signed_value_convert_uses_complete_source_4f_body(self) -> None:
        source_words = rom.program_source_words(
            rom.APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_SOURCE,
            rom.APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_SIZE,
        )
        self.assertEqual(source_words[:3], [0x2E00, 0x58F5, 0x58F6])
        self.assertEqual(source_words[-4:], [0x386F, 0x385F, 0x2F00, rom.RETS])
        flat_words = rom.program_source_words(
            rom.APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_DESTINATION,
            rom.APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_SIZE,
        )
        self.assertNotEqual(flat_words[:3], source_words[:3])

        installer = rom.application_region_extra_installer_words()
        copied = rom.copy_code_to_overlay_words(
            rom.APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_DESTINATION,
            rom.APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_SOURCE,
            rom.APPLICATION_SIGNED_VALUE_CONVERT_OVERLAY_SIZE,
        )
        self.assertIn(
            copied,
            [installer[i:i + len(copied)]
             for i in range(len(installer) - len(copied) + 1)],
        )

    def test_wide_result_normalize_uses_complete_source_4b_body(self) -> None:
        source_words = rom.program_source_words(
            rom.APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_SOURCE,
            rom.APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_SIZE,
        )
        self.assertEqual(source_words[:4], [0x2E0D, 0x1F10, 0x58F7, 0x58F6])
        self.assertEqual(
            source_words[0x12E // 2:0x134 // 2],
            [0x1F90, 0x2F00, rom.RETS],
        )
        self.assertEqual(source_words[-2:], [0xAC00, 0x2FA0])

        flat_words = rom.program_source_words(
            rom.APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_DESTINATION,
            rom.APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_SIZE,
        )
        self.assertEqual(flat_words[:4], [0x382F, 0x381F, 0x2F00, rom.RETS])
        self.assertNotEqual(flat_words[:4], source_words[:4])

        installer = rom.application_region_extra_installer_words()
        copied = rom.copy_code_to_overlay_words(
            rom.APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_DESTINATION,
            rom.APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_SOURCE,
            rom.APPLICATION_WIDE_RESULT_NORMALIZE_OVERLAY_SIZE,
        )
        self.assertIn(
            copied,
            [installer[i:i + len(copied)]
             for i in range(len(installer) - len(copied) + 1)],
        )

    def test_wide_accumulate_leaf_is_relocated_and_all_calls_are_patched(
            self) -> None:
        source_words = rom.program_source_words(
            rom.WIDE_ACCUMULATE_OVERLAY_SOURCE,
            rom.WIDE_ACCUMULATE_OVERLAY_SIZE,
        )
        self.assertEqual(source_words[:4], [0x084B, 0x5248, 0x5058, 0xF201])
        self.assertEqual(source_words[-3:], [0x5853, 0x380F, rom.RETS])
        flat_words = rom.program_source_words(
            rom.WIDE_ACCUMULATE_LINKED_DESTINATION,
            rom.WIDE_ACCUMULATE_OVERLAY_SIZE,
        )
        self.assertNotEqual(flat_words, source_words)

        main_installer = rom.application_region_extra_installer_words()
        self.assertIn([
            0xBD00 | (rom.WIDE_ACCUMULATE_INSTALLER_ADDRESS >> 16),
            rom.WIDE_ACCUMULATE_INSTALLER_ADDRESS & 0xFFFF,
        ], [main_installer[i:i + 2]
            for i in range(len(main_installer) - 1)])
        installer = rom.wide_accumulate_installer_words()
        embedded = rom.embed_program_overlay_words(
            rom.WIDE_ACCUMULATE_OVERLAY_DESTINATION,
            rom.WIDE_ACCUMULATE_OVERLAY_SOURCE,
            rom.WIDE_ACCUMULATE_OVERLAY_SIZE,
        )
        self.assertIn(
            embedded,
            [installer[i:i + len(embedded)]
             for i in range(len(installer) - len(embedded) + 1)],
        )
        self.assertEqual(
            rom.WIDE_ACCUMULATE_CALL_SOURCES,
            (0x4B2F20, 0x4B2F28, 0x4B2F2E),
        )
        for destination in rom.WIDE_ACCUMULATE_CALLS:
            patch = rom.write_program_words(
                destination,
                (0xBD00 | (rom.WIDE_ACCUMULATE_OVERLAY_DESTINATION >> 16),
                 rom.WIDE_ACCUMULATE_OVERLAY_DESTINATION & 0xFFFF),
            )
            self.assertIn(
                patch,
                [installer[i:i + len(patch)]
                 for i in range(len(installer) - len(patch) + 1)],
            )

    def test_shared_numeric_helper_uses_complete_source_4c_body(self) -> None:
        source_words = rom.program_source_words(
            rom.APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_SOURCE,
            rom.APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_SIZE,
        )
        self.assertEqual(
            source_words[:5], [0x2E15, 0x58F0, 0x58F1, 0x58F2, 0x58F3]
        )
        self.assertIn(
            [0xBD03, 0x407C],
            [source_words[i:i + 2] for i in range(len(source_words) - 1)],
        )
        self.assertEqual(
            source_words[-6:], [0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS]
        )

        flat_words = rom.program_source_words(
            rom.APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_DESTINATION,
            rom.APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_SIZE,
        )
        self.assertNotEqual(flat_words[:5], source_words[:5])
        self.assertEqual(flat_words[-1], 0xBD2E)

        installer = rom.application_region_extra_installer_words()
        copied = rom.copy_code_to_overlay_words(
            rom.APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_DESTINATION,
            rom.APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_SOURCE,
            rom.APPLICATION_SHARED_NUMERIC_HELPER_OVERLAY_SIZE,
        )
        self.assertIn(
            copied,
            [installer[i:i + len(copied)]
             for i in range(len(installer) - len(copied) + 1)],
        )

    def test_wide_register_sign_toggle_uses_exact_source_50_leaf(self) -> None:
        source_words = rom.program_source_words(
            rom.WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_SOURCE,
            rom.WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_SIZE,
        )
        self.assertEqual(source_words, [
            0x5000, 0xD206, 0x5010, 0xD204, 0x5020, 0xD202,
            0x5030, 0xD102, 0x77F0, 0x8000, rom.RETS,
        ])
        flat_words = rom.program_source_words(
            rom.WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_DESTINATION,
            rom.WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_SIZE,
        )
        self.assertNotEqual(flat_words, source_words)

        installer = rom.application_region_extra_installer_words()
        embedded = rom.embed_program_overlay_words(
            rom.WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_DESTINATION,
            rom.WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_SOURCE,
            rom.WIDE_REGISTER_SIGN_TOGGLE_OVERLAY_SIZE,
        )
        self.assertIn(
            embedded,
            [installer[i:i + len(embedded)]
             for i in range(len(installer) - len(embedded) + 1)],
        )

    def test_operation_context_test_uses_complete_same_pc_wrapper(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_SIZE,
        )
        self.assertEqual(source[:2], [0x2E8E, 0x58F1])
        self.assertIn(
            [0xBD25, 0x5460],
            [source[i:i + 2] for i in range(len(source) - 1)],
        )
        self.assertEqual(source[-3:], [0x381F, 0x2F00, rom.RETS])

        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_DESTINATION,
            rom.APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_TEST_OVERLAY_SIZE,
        )
        installer = rom.install_application_main_chain_words()
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        module = next(
            item for item in rom.manifest(b"")["application_main_chain"]
            if item["destination"] == "32:FA06"
        )
        self.assertEqual(module["source"], "4F:FA06")
        self.assertEqual(module["bytes"], 0x3A)

    def test_storage_context_uses_complete_same_pc_initializer(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_STORAGE_CONTEXT_OVERLAY_SOURCE,
            rom.APPLICATION_STORAGE_CONTEXT_OVERLAY_SIZE,
        )
        self.assertEqual(source[:4], [0x2E05, 0x58F1, 0x58F2, 0x58F3])
        self.assertIn(
            [0xBD31, 0xE022],
            [source[i:i + 2] for i in range(len(source) - 1)],
        )
        self.assertEqual(source[-5:], [0x383F, 0x382F, 0x381F, 0x2F00,
                                      rom.RETS])

        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_STORAGE_CONTEXT_OVERLAY_DESTINATION,
            rom.APPLICATION_STORAGE_CONTEXT_OVERLAY_SOURCE,
            rom.APPLICATION_STORAGE_CONTEXT_OVERLAY_SIZE,
        )
        installer = rom.install_runtime_overlay_words()
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        module = next(
            item for item in rom.manifest(b"")["nested_system_overlays"]
            if item["destination"] == "25:5460"
        )
        self.assertEqual(module["source"], "42:5460")
        self.assertEqual(module["bytes"], 0x3F8)

    def test_resource_storage_lifecycle_graph_uses_exact_prg_modules(self) -> None:
        installer = rom.application_region_extra_installer_words()
        self.assertEqual(len(rom.APPLICATION_RESOURCE_STORAGE_COPY_OVERLAYS), 27)
        self.assertEqual(
            len(rom.APPLICATION_RESOURCE_STORAGE_EMBEDDED_OVERLAYS), 5
        )
        self.assertEqual(
            len(rom.APPLICATION_FILE_DRIVER_CALLBACK_ROM_MODULES), 2
        )

        for destination, source, size in (
                rom.APPLICATION_RESOURCE_STORAGE_COPY_OVERLAYS):
            self.assertEqual(source - destination, 0x1D0000)
            shipped = rom.program_source_words(source, size)
            self.assertEqual(shipped[0] & 0xFF00, 0x2E00)
            self.assertEqual(shipped[-1], rom.RETS)
            descriptor = rom.copy_code_to_overlay_words(
                destination, source, size
            )
            self.assertIn(
                descriptor,
                [installer[i:i + len(descriptor)]
                 for i in range(len(installer) - len(descriptor) + 1)],
            )

        for destination, source, size in (
                rom.APPLICATION_RESOURCE_STORAGE_EMBEDDED_OVERLAYS):
            self.assertEqual(source - destination, 0x1D0000)
            shipped = rom.program_source_words(source, size)
            self.assertEqual(shipped[0] & 0xFF00, 0x2E00)
            self.assertEqual(shipped[-1], rom.RETS)
            embedded = rom.embed_program_overlay_words(
                destination, source, size
            )
            self.assertIn(
                embedded,
                [installer[i:i + len(embedded)]
                 for i in range(len(installer) - len(embedded) + 1)],
            )

        callback_installer = rom.file_driver_callback_installer_words()
        self.assertEqual(callback_installer[-1], rom.RETS)
        application_loader = rom.rom01_application_loader_words()
        self.assertIn([
            0xBD00 | (
                rom.APPLICATION_FILE_DRIVER_CALLBACK_INSTALLER_ADDRESS >> 16
            ),
            rom.APPLICATION_FILE_DRIVER_CALLBACK_INSTALLER_ADDRESS & 0xFFFF,
        ], [
            application_loader[i:i + 2]
            for i in range(len(application_loader) - 1)
        ])
        image = rom.build_image()
        for destination, source, size in (
            (rom.RESIDENT_RESOURCE_STORAGE_UNIT_ADDRESS,
             rom.RESIDENT_RESOURCE_STORAGE_UNIT_SOURCE,
             rom.RESIDENT_RESOURCE_STORAGE_UNIT_SIZE),
            (rom.RESIDENT_RESOURCE_STORAGE_SCAN_ADDRESS,
             rom.RESIDENT_RESOURCE_STORAGE_SCAN_SOURCE,
             rom.RESIDENT_RESOURCE_STORAGE_SCAN_SIZE),
        ):
            self.assertEqual(source - destination, 0x1D0000)
            self.assertEqual(
                words_at(image, destination, size // 2),
                rom.program_source_words(source, size),
            )

        unit = words_at(
            image,
            rom.RESIDENT_RESOURCE_STORAGE_UNIT_ADDRESS,
            rom.RESIDENT_RESOURCE_STORAGE_UNIT_SIZE // 2,
        )
        jump_offset = (0x8110 - 0x7FFE) // 2
        self.assertEqual(unit[jump_offset:jump_offset + 2], [0xAC00, 0x873C])
        info = rom.manifest(image)
        modules = info["resource_storage_lifecycle_overlays"]
        self.assertEqual(len(modules), 34)
        self.assertEqual(modules[0]["destination"], "2E:A00C")
        self.assertEqual(modules[-1]["destination"], "1A:F040")

        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_SOURCE,
                rom.APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_SIZE,
            ),
            [0x2E00, 0xBD33, 0x244A, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_SOURCE,
                rom.APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_SIZE,
            )[:4],
            [0x2E01, 0x58F1, 0xE28D, 0xBD29],
        )
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_DESTINATION,
                rom.APPLICATION_FILE_DRIVER_CALLBACK_CHILD_OVERLAY_SIZE // 2,
            ),
            rom.file_driver_callback_child_words(),
        )
        wrapper = rom.file_driver_callback_wrapper_words()
        self.assertEqual(wrapper, [
            0x2E00, 0xBD1A, 0xF000, 0x2F00, rom.RETS,
        ])
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_FILE_DRIVER_CALLBACK_OVERLAY_DESTINATION,
                len(wrapper),
            ),
            wrapper,
        )
        self.assertIn([
            0x6810, 0x00A2, 0xC700,
            0x68F0, 0x001A, 0xA8F0, 0x27B4,
            0x68F0, 0xF040, 0xA8F0, 0x27B6,
        ], [
            callback_installer[i:i + 11]
            for i in range(len(callback_installer) - 10)
        ])

    def test_resource_persistence_writer_is_exact_closed_overlay(self) -> None:
        copy_modules = {
            destination: (source, size)
            for destination, source, size in
            rom.APPLICATION_RESOURCE_STORAGE_COPY_OVERLAYS
        }
        embedded_modules = {
            destination: (source, size)
            for destination, source, size in
            rom.APPLICATION_RESOURCE_STORAGE_EMBEDDED_OVERLAYS
        }
        self.assertEqual(
            copy_modules[
                rom.APPLICATION_RESOURCE_PERSIST_WRAPPER_OVERLAY_DESTINATION
            ],
            (rom.APPLICATION_RESOURCE_PERSIST_WRAPPER_OVERLAY_SOURCE, 0x40),
        )
        self.assertEqual(
            embedded_modules[
                rom.APPLICATION_RESOURCE_PERSIST_BRIDGE_OVERLAY_DESTINATION
            ],
            (rom.APPLICATION_RESOURCE_PERSIST_BRIDGE_OVERLAY_SOURCE, 0x32),
        )
        self.assertEqual(
            copy_modules[
                rom.APPLICATION_RESOURCE_PERSIST_PAGE_WRITE_OVERLAY_DESTINATION
            ],
            (rom.APPLICATION_RESOURCE_PERSIST_PAGE_WRITE_OVERLAY_SOURCE, 0x312),
        )
        persistence_modules = (
            (
                rom.APPLICATION_RESOURCE_PERSIST_WRAPPER_OVERLAY_DESTINATION,
                *copy_modules[
                    rom.APPLICATION_RESOURCE_PERSIST_WRAPPER_OVERLAY_DESTINATION
                ],
            ),
            (
                rom.APPLICATION_RESOURCE_PERSIST_BRIDGE_OVERLAY_DESTINATION,
                *embedded_modules[
                    rom.APPLICATION_RESOURCE_PERSIST_BRIDGE_OVERLAY_DESTINATION
                ],
            ),
            (
                rom.APPLICATION_RESOURCE_PERSIST_PAGE_WRITE_OVERLAY_DESTINATION,
                *copy_modules[
                    rom.APPLICATION_RESOURCE_PERSIST_PAGE_WRITE_OVERLAY_DESTINATION
                ],
            ),
        )
        for destination, source, size in persistence_modules:
            self.assertEqual(source - destination, 0x1D0000)
            shipped = rom.program_source_words(source, size)
            self.assertEqual(shipped[0] & 0xFF00, 0x2E00)
            self.assertEqual(shipped[-1], rom.RETS)

    def test_game_world_browser_confirm_field_uses_exact_embedded_leaf(
        self,
    ) -> None:
        self.assertEqual(
            rom.program_source_words(0x38276C, 4),
            [0xBD33, 0x384E],
        )
        shipped = rom.program_source_words(
            rom.APPLICATION_FILE_BROWSER_CONFIRM_FIELD_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_BROWSER_CONFIRM_FIELD_OVERLAY_SIZE,
        )
        self.assertEqual(
            shipped,
            [
                0x2E00, 0x780B, 0x0006, 0x781B, 0x0008,
                0x70F1, 0x0010, 0x5100, 0x4C11, 0x5C01,
                0x58F0, 0x1F90, 0x4D11, 0x3801, 0x2811,
                0x2F00, rom.RETS,
            ],
        )
        self.assertNotEqual(
            rom.program_source_words(
                rom.APPLICATION_FILE_BROWSER_CONFIRM_FIELD_OVERLAY_DESTINATION,
                rom.APPLICATION_FILE_BROWSER_CONFIRM_FIELD_OVERLAY_SIZE,
            ),
            shipped,
        )
        embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_FILE_BROWSER_CONFIRM_FIELD_OVERLAY_DESTINATION,
            rom.APPLICATION_FILE_BROWSER_CONFIRM_FIELD_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_BROWSER_CONFIRM_FIELD_OVERLAY_SIZE,
        )
        installer = rom.application_region_extra_installer_words()
        self.assertIn(
            embedded,
            [installer[index:index + len(embedded)]
             for index in range(len(installer) - len(embedded) + 1)],
        )
        module = rom.manifest(b"")["game_world_browser_event_dependency"]
        self.assertEqual(module["destination"], "33:384E")
        self.assertEqual(module["source"], "50:384E")
        self.assertEqual(module["bytes"], 0x22)

    def test_game_world_browser_path_range_uses_exact_framed_worker(
        self,
    ) -> None:
        for call in (0x382886, 0x3828E8):
            self.assertEqual(
                rom.program_source_words(call, 4),
                [0xBD25, 0xF992],
            )
        shipped = rom.program_source_words(
            rom.APPLICATION_FILE_BROWSER_PATH_RANGE_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_BROWSER_PATH_RANGE_OVERLAY_SIZE,
        )
        self.assertEqual(
            shipped[:6],
            [0x2E0E, 0x58F1, 0x58F2, 0x58F3, 0x58F4, 0x58F5],
        )
        self.assertEqual(shipped[-7:], [
            0x385F, 0x384F, 0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_FILE_BROWSER_PATH_RANGE_OVERLAY_SOURCE
                + rom.APPLICATION_FILE_BROWSER_PATH_RANGE_OVERLAY_SIZE,
                2,
            ),
            [0x2E0A],
        )
        self.assertNotEqual(
            rom.program_source_words(
                rom.APPLICATION_FILE_BROWSER_PATH_RANGE_OVERLAY_DESTINATION,
                2,
            ),
            [0x2E0E],
        )
        for target, count in (
            (0x3340A8, 1),
            (0x331894, 1),
            (0x27CBE4, 3),
            (0x336C0A, 3),
            (0x33443E, 2),
        ):
            call_words = [0xBD00 | (target >> 16), target & 0xFFFF]
            self.assertEqual(sum(
                shipped[index:index + 2] == call_words
                for index in range(len(shipped) - 1)
            ), count)
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FILE_BROWSER_PATH_RANGE_OVERLAY_DESTINATION,
            rom.APPLICATION_FILE_BROWSER_PATH_RANGE_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_BROWSER_PATH_RANGE_OVERLAY_SIZE,
        )
        installer = rom.application_region_extra_installer_words()
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        module = rom.manifest(b"")["game_world_browser_path_dependency"]
        self.assertEqual(module["destination"], "25:F992")
        self.assertEqual(module["source"], "42:F992")
        self.assertEqual(module["bytes"], 0x03BA)

    def test_game_world_renderer_retargets_colliding_mode_pair_helper(
        self,
    ) -> None:
        source_offset = (
            rom.APPLICATION_MAIN_ROM_RENDER_MODE_PAIR_CALL_SOURCE
            - rom.APPLICATION_MAIN_ROM_RENDER_SOURCE
        ) // 2
        source = rom.program_source_words(
            rom.APPLICATION_MAIN_ROM_RENDER_SOURCE,
            rom.APPLICATION_MAIN_ROM_RENDER_SIZE,
        )
        self.assertEqual(
            source[source_offset:source_offset + 2],
            [0xBD33, 0x1BBA],
        )
        restored = rom.application_main_rom_render_words()
        self.assertEqual(
            restored[source_offset:source_offset + 2],
            [0xBD5F, 0x1BBA],
        )
        self.assertEqual(
            sum(restored[index:index + 2] == [0xBD5F, 0x1BBA]
                for index in range(len(restored) - 1)),
            1,
        )
        helper = rom.program_source_words(
            rom.APPLICATION_RESULT_MODE_PAIR_OVERLAY_SOURCE,
            rom.APPLICATION_RESULT_MODE_PAIR_OVERLAY_SIZE,
        )
        self.assertEqual(helper[0], 0x2E00)
        self.assertEqual(helper[-2:], [0x2F00, rom.RETS])
        image = rom.build_image()
        destination_offset = (
            rom.APPLICATION_MAIN_ROM_RENDER_MODE_PAIR_CALL
            - rom.APPLICATION_MAIN_ROM_RENDER_DESTINATION
        ) // 2
        resident = words_at(
            image,
            rom.APPLICATION_MAIN_ROM_RENDER_DESTINATION,
            rom.APPLICATION_MAIN_ROM_RENDER_SIZE // 2,
        )
        self.assertEqual(
            resident[destination_offset:destination_offset + 2],
            [0xBD5F, 0x1BBA],
        )
        module = rom.manifest(image)["application_main_render_mode_pair_call"]
        self.assertEqual(module["destination"], "1D:83DC")
        self.assertEqual(module["linked_target"], "33:1BBA")
        self.assertEqual(module["relocated_target"], "5F:1BBA")

    def test_rom06_keyboard_boundary_uses_guest_matrix_pipeline(self) -> None:
        release = rom.rom06_key_release_words()
        read = rom.rom06_key_read_words()

        self.assertEqual(release, [rom.RETS])
        self.assertEqual(read, [
            0xBD2E, 0x5F28,
            0x58F0,
            0xBD28, 0xF4A4,
            0x50F2,
            0x5600,
            0xAC01, 0xB126,
            rom.RETS,
        ])
        image = rom.build_image()
        self.assertEqual(
            words_at(image, rom.ROM06_KEY_RELEASE_ADDRESS, len(release)),
            release,
        )
        self.assertEqual(
            words_at(image, rom.ROM06_KEY_READ_ADDRESS, len(read)),
            read,
        )
        metadata = rom.manifest(image)["resident_rom06_keyboard"]
        self.assertEqual(
            metadata["release_contract"],
            "no arguments; return value ignored at all four callers",
        )
        self.assertEqual(metadata["scanner"],
                         "2E:5F28 (exact updater relocation; 06:B126 only)")
        self.assertEqual(metadata["mapper"],
                         "28:F4A4 (exact updater relocation)")

    def test_read_page_uses_original_seven_word_abi(self) -> None:
        words = rom.read_page_words()

        for offset, address in (
            (4, rom.NAND_PAGE_HI),
            (6, rom.NAND_PAGE_LO),
            (8, rom.NAND_COLUMN),
            (10, rom.NAND_BUFFER_HI),
            (12, rom.NAND_BUFFER_LO),
            (16, rom.NAND_FLAGS),
        ):
            load = rom.mov_gpr_from_sp(0, offset)
            store = rom.mov_mmio_from_gpr(address, 0)
            index = next(
                i for i in range(len(words) - len(load + store) + 1)
                if words[i : i + len(load + store)] == load + store
            )
            self.assertGreaterEqual(index, 0)
        self.assertIn(
            rom.mov_gpr_from_sp(0, 14) +
            rom.mov_mmio_from_gpr(rom.NAND_LENGTH, 0),
            [words[i:i + 5] for i in range(len(words) - 4)],
        )
        self.assertNotIn(0x0210, words)
        self.assertEqual(words[-1], rom.RETS)
        self.assertEqual(words.count(rom.IGNDS_ONE), 11)

    def test_read_and_program_page_use_guest_side_codec_hooks(self) -> None:
        read = rom.read_page_words()
        program = rom.program_page_words()

        self.assertIn([
            0xBD00 | (rom.NAND_PREPARE_READ_ADDRESS >> 16),
            rom.NAND_PREPARE_READ_ADDRESS & 0xFFFF,
        ],
                      [read[i:i + 2] for i in range(len(read) - 1)])
        self.assertIn([
            0xBD00 | (rom.NAND_UNPACK_SPARE_ADDRESS >> 16),
            rom.NAND_UNPACK_SPARE_ADDRESS & 0xFFFF,
        ],
                      [read[i:i + 2] for i in range(len(read) - 1)])
        self.assertIn([
            0xBD00 | (rom.NAND_PACK_SPARE_ADDRESS >> 16),
            rom.NAND_PACK_SPARE_ADDRESS & 0xFFFF,
        ],
                      [program[i:i + 2] for i in range(len(program) - 1)])
        self.assertIn(
            [0x4801, *rom.mov_mmio_from_gpr(rom.NAND_COMMAND, 0)],
            [read[i:i + 4] for i in range(len(read) - 3)],
        )
        self.assertIn(
            [0x4802, *rom.mov_mmio_from_gpr(rom.NAND_COMMAND, 0)],
            [program[i:i + 4] for i in range(len(program) - 3)],
        )

    def test_logical_status_probe_is_translated_by_guest_rom(self) -> None:
        prepare = rom.prepare_logical_read_words()
        unpack = rom.unpack_logical_spare_words()

        self.assertIn(
            [0x68F1, 0x0236, 0x1601],
            [prepare[i:i + 3] for i in range(len(prepare) - 2)],
        )
        self.assertIn(
            [0x68F0, 0x0204, *rom.mov_mmio_from_gpr(rom.NAND_COLUMN, 0)],
            [prepare[i:i + 5] for i in range(len(prepare) - 4)],
        )
        compare = next(
            i for i in range(len(unpack) - 4)
            if unpack[i:i + 2] == [0x66F3, 0x00FF]
        )
        self.assertEqual(unpack[compare + 2] & 0xFF00, 0xD100)
        self.assertEqual(unpack[compare + 3:compare + 5], [0x4930, 0x0B13])

        image = rom.build_image()
        self.assertEqual(
            words_at(image, rom.NAND_PREPARE_READ_ADDRESS, len(prepare)),
            prepare,
        )

    def test_full_page_read_expands_compact_oob_in_guest_rom(self) -> None:
        dispatch = rom.unpack_logical_spare_words()
        expand = rom.unpack_full_logical_page_words()

        self.assertIn(
            [0x68F3, rom.NAND_SMALL_PAGE_TOTAL, 0x1603],
            [dispatch[i:i + 3] for i in range(len(dispatch) - 2)],
        )
        self.assertIn(
            [0xBD00 | (rom.NAND_UNPACK_FULL_ADDRESS >> 16),
             rom.NAND_UNPACK_FULL_ADDRESS & 0xFFFF],
            [dispatch[i:i + 2] for i in range(len(dispatch) - 1)],
        )
        self.assertIn(
            [0x68F0, 0x6979, 0x0A30],
            [expand[i:i + 3] for i in range(len(expand) - 2)],
        )
        self.assertIn(
            [0x2942, 0x66F4, 0x00FF],
            [expand[i:i + 3] for i in range(len(expand) - 2)],
        )
        self.assertIn(0x0B34, expand)

        image = rom.build_image()
        self.assertEqual(
            words_at(image, rom.NAND_UNPACK_FULL_ADDRESS, len(expand)),
            expand,
        )

    def test_erase_converts_block_to_page_and_returns_error(self) -> None:
        words = rom.erase_block_words()

        self.assertIn(0x4C16, words)
        self.assertIn(0x5C06, words)
        self.assertIn(rom.NAND_ERROR, words)
        self.assertEqual(words[-1], rom.RETS)

    def test_metadata_block_probe_only_suppresses_post_format_812c_block_one_erase(self) -> None:
        strict = rom.erase_block_words()
        probe = rom.erase_block_words(preserve_block_one_probe=True)
        load_argument = rom.mov_gpr_from_sp(1, 4)
        guard = [
            0x5611, 0xD212,
            *rom.mov_gpr_from_sp(0, 2),
            0x68F2, 0x8130, 0x1602, 0xD20C,
            0x1F10, 0x6810, 0x00A0,
            0x88F0, 0x0008, 0x1F90, 0x560B, 0xD102,
            0x5602, 0xD202,
            0x4800, rom.RETS,
        ]

        self.assertEqual(probe[:len(load_argument)], load_argument)
        self.assertEqual(
            probe[len(load_argument):len(load_argument) + len(guard)],
            guard,
        )
        self.assertEqual(probe[len(load_argument) + len(guard):],
                         strict[len(load_argument):])

        image = rom.build_image(preserve_metadata_block_probe=True)
        self.assertEqual(
            words_at(image, 0x02BDD6,
                     len(load_argument) + len(guard)),
            load_argument + guard,
        )

    def test_copy_back_uses_source_then_destination_page_abi(self) -> None:
        words = rom.copy_page_words()

        for offset, address in (
            (4, rom.NAND_PAGE_HI),
            (6, rom.NAND_PAGE_LO),
            (8, rom.NAND_BUFFER_HI),
            (10, rom.NAND_BUFFER_LO),
        ):
            fragment = (
                rom.mov_gpr_from_sp(0, offset) +
                rom.mov_mmio_from_gpr(address, 0)
            )
            self.assertIn(
                fragment,
                [words[i:i + len(fragment)]
                 for i in range(len(words) - len(fragment) + 1)],
            )
        self.assertIn([0x68F0, rom.NAND_PAGE_TOTAL],
                      [words[i:i + 2] for i in range(len(words) - 1)])
        self.assertIn(0x4805, words)
        self.assertEqual(words[-1], rom.RETS)

    def test_nand_completion_returns_controller_error(self) -> None:
        self.assertEqual(
            rom.nand_completion_words(),
            [*rom.mov_gpr_from_mmio(0, rom.NAND_ERROR), rom.RETS],
        )

    def test_cold_boot_builds_outer_frame_and_jumps_to_continuation(self) -> None:
        words = rom.cold_boot_words()

        self.assertEqual(words[:2], [
            0xBD00 | (rom.DEFAULT_OVERLAY_INSTALLER_ADDRESS >> 16),
            rom.DEFAULT_OVERLAY_INSTALLER_ADDRESS & 0xFFFF,
        ])
        self.assertIn([0xBD20, 0x0030],
                      [words[i:i + 2] for i in range(len(words) - 1)])
        self.assertNotIn([0xBD20, 0x026A],
                         [words[i:i + 2] for i in range(len(words) - 1)])
        for address in (0xFFF4, 0xFFF6, 0xFFF8, 0xFFFA, 0xFFFC):
            store = rom.mov_mmio_from_gpr(address, 0)
            index = next(
                i for i in range(len(words) - len(store) + 1)
                if words[i : i + len(store)] == store
            )
            self.assertGreater(index, 0)
        self.assertIn([0x4803, *rom.mov_mmio_from_gpr(0xFFFA, 0)],
                      [words[i:i + 4] for i in range(len(words) - 3)])
        self.assertIn([0x68F0, 0x0080,
                       *rom.mov_mmio_from_gpr(0xFFFC, 0)],
                      [words[i:i + 5] for i in range(len(words) - 4)])
        self.assertIn(0x4C11, words)
        self.assertEqual(words[-2:], [0xAD20, 0x0004])

    def test_cold_boot_context_is_embedded_in_guest_state(self) -> None:
        words = rom.cold_boot_words(0x526A1E)

        expected_fragments = (
            [0x68F0, 0x0052, *rom.mov_mmio_from_gpr(0xFFF4, 0)],
            [0x68F0, 0x6A1E, *rom.mov_mmio_from_gpr(0xFFF6, 0)],
            [0x68F0, 0x0052, 0x68F1, 0x6A56],
            [0x68F2, 0x0052, 0x68F3, 0x6A4E],
        )
        for fragment in expected_fragments:
            self.assertTrue(any(
                words[index:index + len(fragment)] == fragment
                for index in range(len(words) - len(fragment) + 1)
            ), fragment)

    def test_event_loop_polls_without_repeating_activation(self) -> None:
        words = rom.resident_event_loop_words(0x526A1E)

        self.assertEqual(words[0], 0x3F03)
        self.assertEqual(words[1:4], rom.mov_gpr_from_mmio(
            0, rom.KEYBOARD_EVENT))
        self.assertIn([0x68F0, 0x0052, 0x3F02, 0x58F0],
                      [words[i:i + 4] for i in range(len(words) - 3)])
        self.assertIn([0xBD33, 0x4510, 0x50F6],
                      [words[i:i + 3] for i in range(len(words) - 2)])
        self.assertIn(rom.mov_gpr_from_mmio(0, rom.KEYBOARD_EVENT),
                      [words[i:i + 3] for i in range(len(words) - 2)])
        self.assertEqual(words.count(0xBD33), 1)
        self.assertEqual(words[-2], 0xAD03)
        call = words.index(0xBD33)
        self.assertEqual(words[call - 10:call + 2], [
            0x3F03, 0x0810,
            0x68F0, 0x6A1E, 0x58F0,
            0x68F0, 0x0052, 0x3F02,
            0x58F0, 0x58F1,
        ] + [0xBD33, 0x4510])

    def test_native_scheduler_loops_complete_system_main_without_f340(self) -> None:
        words = rom.native_application_scheduler_words()

        self.assertEqual(words, [
            0xBD20, 0x026A,
            0xAD03, rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS & 0xFFFF,
        ])
        self.assertNotIn(rom.KEYBOARD_EVENT, words)
        self.assertNotIn([0xBD33, 0x4510], [
            words[index:index + 2]
            for index in range(len(words) - 1)
        ])

    def test_native_scheduler_can_hold_exact_post_return_state(self) -> None:
        words = rom.native_application_scheduler_words(
            stop_after_return=True
        )

        self.assertEqual(words, [
            0xBD20, 0x026A,
            0xAD03,
            (rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS + 4) & 0xFFFF,
        ])
        image = rom.build_image(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_rom_01_return=True,
            probe_stop_after_scheduler_return=True,
        )
        self.assertEqual(
            words_at(image, rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS, 4),
            words,
        )
        routines = rom.make_routines(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_rom_01_return=True,
            probe_stop_after_scheduler_return=True,
        )
        self.assertEqual(
            routines[rom.ROM01_POST_CLOCK_ADDRESS][1],
            rom.rom01_application_loader_words(
                return_after_first_main_cycle=True
            ),
        )

    def test_factory_scheduler_reenters_linked_system_main(self) -> None:
        words = rom.native_application_scheduler_words(
            factory_linked_startup=True,
        )

        self.assertEqual(words, [
            0x68F0, 0x0200,
            0x6810, 0x00A2,
            0xC700,
            0xA8F0, 0x28E0,
            0xBD03, 0x026A,
            0xAD03, rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS & 0xFFFF,
        ])

    def test_rom01_initializes_storage_after_system_main_bss_clear(
        self,
    ) -> None:
        words = rom.rom01_application_loader_words()
        capacity_call = [
            0xBD00 | (rom.STORAGE_RECORD_CAPACITY_INSTALLER_ADDRESS >> 16),
            rom.STORAGE_RECORD_CAPACITY_INSTALLER_ADDRESS & 0xFFFF,
        ]
        registry_call = [
            0xBD00 | (
                rom.APPLICATION_STORAGE_REGISTRY_OVERLAY_DESTINATION >> 16
            ),
            rom.APPLICATION_STORAGE_REGISTRY_OVERLAY_DESTINATION & 0xFFFF,
        ]
        capacity_index = next(
            index for index in range(len(words) - 1)
            if words[index:index + 2] == capacity_call
        )
        registry_index = next(
            index for index in range(len(words) - 1)
            if words[index:index + 2] == registry_call
        )
        self.assertLess(capacity_index, registry_index)
        self.assertEqual(words[registry_index + 2:registry_index + 4], [
            0xBD00 | (
                rom.APPLICATION_FILE_DRIVER_CALLBACK_INSTALLER_ADDRESS >> 16
            ),
            rom.APPLICATION_FILE_DRIVER_CALLBACK_INSTALLER_ADDRESS & 0xFFFF,
        ])
        self.assertEqual(words[registry_index + 4:registry_index + 6], [
            0xBD14, rom.LCD_POWER_INIT_ADDRESS & 0xFFFF,
        ])
        self.assertEqual(
            rom.native_application_scheduler_words(),
            [0xBD20, 0x026A,
             0xAD03, rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS & 0xFFFF],
        )

    def test_native_scheduler_can_hold_first_bootstrap_return_state(self) -> None:
        image = rom.build_image(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_rom_01_return=True,
            probe_stop_before_scheduler_entry=True,
        )
        self.assertEqual(
            words_at(image, rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS, 2),
            [0xAD03, rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS & 0xFFFF],
        )
        name, words = rom.make_routines(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_rom_01_return=True,
            probe_stop_before_scheduler_entry=True,
        )[rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS]
        self.assertEqual(
            name, "inferred_native_application_scheduler_entry_stop"
        )
        self.assertEqual(words, [0xAD03, 0x0080])
        self.assertEqual(
            rom.make_routines(
                initializer_overlay_probe=True,
                probe_rom_08_return=True,
                probe_system_main=True,
                probe_rom_01_return=True,
                probe_stop_before_scheduler_entry=True,
            )[rom.ROM01_POST_CLOCK_ADDRESS][1],
            rom.rom01_application_loader_words(
                return_after_first_main_cycle=True
            ),
        )

    def test_legacy_main_menu_probe_reproduces_rejected_adjacent_wrappers(self) -> None:
        words = rom.generic_main_menu_probe_words()
        self.assertEqual(words[:20], [
            0xBD00 | (rom.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS >> 16),
            rom.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS & 0xFFFF,
            0xBD25, 0x5858,
            0xBD30, 0x8C1C,
            0xBD00 | (rom.RESIDENT_FIXED_LAUNCH_INSTALLER_ADDRESS >> 16),
            rom.RESIDENT_FIXED_LAUNCH_INSTALLER_ADDRESS & 0xFFFF,
            0xBD33, 0x3CA6,
            0xBD00 | (rom.MENU_RUNTIME_OVERLAY_INSTALLER_ADDRESS >> 16),
            rom.MENU_RUNTIME_OVERLAY_INSTALLER_ADDRESS & 0xFFFF,
            0xBD00 | (rom.MENU_POINTER_INDEX_INSTALLER_ADDRESS >> 16),
            rom.MENU_POINTER_INDEX_INSTALLER_ADDRESS & 0xFFFF,
            0xBD06, 0x6A02,
            0xBD30, 0xD350,
            0xBD2F, 0xC216,
        ])
        pointer_index = rom.generic_main_menu_pointer_index_logical_bytes()
        self.assertEqual(len(pointer_index), 2 + 26 * 3)
        self.assertEqual(
            int.from_bytes(pointer_index[:2], "little"),
            rom.RESIDENT_MENU_PAGE_COUNT - 1,
        )
        pointers = [
            int.from_bytes(pointer_index[2 + index * 3:5 + index * 3],
                           "little")
            for index in range(rom.RESIDENT_MENU_PAGE_COUNT + 1)
        ]
        self.assertEqual(pointers, [
            rom.RESIDENT_MENU_PAGE_TABLE_ADDRESS +
            index * rom.RESIDENT_MENU_PAGE_RECORD_SIZE
            for index in range(rom.RESIDENT_MENU_PAGE_COUNT + 1)
        ])
        self.assertEqual(words[20:28], [
            0x4800,
            0x6810, 0x00A2,
            0xC700,
            0xA8F0, 0x2A88,
            0xA8F0, 0x2A90,
        ])
        self.assertEqual(words[28:33], [
            0x4800,
            0x58F0,
            0xBD31, 0xB014,
            0x50F2,
        ])
        index_installer = (
            rom.generic_main_menu_pointer_index_installer_words()
        )
        self.assertEqual(words[-4:-2], [0xBD33, 0x3CC6])
        self.assertEqual(words[-2:], [
            0xAD03,
            (rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS +
             (len(words) - 2) * 2) & 0xFFFF,
        ])
        image = rom.build_image(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_rom_01_return=True,
            probe_storage_global_templates=True,
            probe_generic_main_menu=True,
        )
        self.assertEqual(
            words_at(image, rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS,
                     len(words)),
            words,
        )
        self.assertEqual(
            words_at(image, rom.MENU_POINTER_INDEX_INSTALLER_ADDRESS,
                     len(index_installer)),
            index_installer,
        )
        name, _ = rom.make_routines(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_rom_01_return=True,
            probe_storage_global_templates=True,
            probe_generic_main_menu=True,
        )[rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS]
        self.assertEqual(name, "probe_rejected_adjacent_resource_wrappers")

    def test_direct_generic_menu_probe_calls_exact_vendor_entry(self) -> None:
        words = rom.direct_generic_menu_probe_words()
        ui_prepare_call = [0xBD2F, 0x5B98]
        color_prepare_call = [0xBD30, 0xD6D0]
        menu_call = [0xBD2C, 0xC9E8]
        ui_prepare_index = next(
            index for index in range(len(words) - 1)
            if words[index:index + 2] == ui_prepare_call
        )
        menu_index = next(
            index for index in range(len(words) - 1)
            if words[index:index + 2] == menu_call
        )
        color_prepare_index = next(
            index for index in range(len(words) - 1)
            if words[index:index + 2] == color_prepare_call
        )
        self.assertNotIn([0xBD33, 0x3CC6], [
            words[index:index + 2] for index in range(len(words) - 1)
        ])
        self.assertIn(menu_call, [
            words[index:index + 2] for index in range(len(words) - 1)
        ])
        self.assertLess(ui_prepare_index, menu_index)
        self.assertLess(ui_prepare_index, color_prepare_index)
        self.assertLess(color_prepare_index, menu_index)
        self.assertEqual(words[ui_prepare_index - 3:ui_prepare_index + 3], [
            0x68F0, 0x00F0,
            0x58F0,
            0xBD2F, 0x5B98,
            0x50F2,
        ])
        self.assertEqual(
            words[color_prepare_index - 4:color_prepare_index + 3],
            [
                0x4800,
                0x58F0,
                0x480F,
                0x58F0,
                0xBD30, 0xD6D0,
                0x50F4,
            ],
        )
        self.assertIn([
            0x4800,
            0x58F0,
            0xBD31, 0xB014,
            0x50F2,
        ], [
            words[index:index + 5] for index in range(len(words) - 4)
        ])
        self.assertNotIn([
            0x4801,
            0x58F0,
            0xBD31, 0xB014,
            0x50F2,
        ], [
            words[index:index + 5] for index in range(len(words) - 4)
        ])
        self.assertIn([
            0x4800,
            0x6810, 0x00A2,
            0xC700,
            0xA8F0, 0x2A6C,
            0xA8F0, 0x2A76,
            0xA8F0, 0x2A88,
            0xA8F0, 0x2A90,
            0xA8F0, 0x2A92,
            0xA8F0, 0x2AA6,
            0xA8F0, 0x2ABA,
            0x68F0, 0x00FF,
            0xA8F0, 0x2AA4,
        ], [
            words[index:index + 22] for index in range(len(words) - 21)
        ])
        self.assertIn([
            0xA8F0, 0x70BA,
            0xA8F0, 0x70BC,
            0xA8F0, 0x7CB2,
            0xA8F0, 0x7CB4,
        ], [
            words[index:index + 8] for index in range(len(words) - 7)
        ])
        self.assertEqual(words[-2:], [
            0xAD00 | (rom.DIRECT_GENERIC_MENU_PROBE_ADDRESS >> 16),
            (rom.DIRECT_GENERIC_MENU_PROBE_ADDRESS +
             (len(words) - 2) * 2) & 0xFFFF,
        ])

        flow = dict(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_rom_01_return=True,
            probe_storage_global_templates=True,
            probe_direct_generic_menu=True,
        )
        image = rom.build_image(**flow)
        self.assertEqual(
            words_at(image, rom.DIRECT_GENERIC_MENU_PROBE_ADDRESS,
                     len(words)),
            words,
        )
        routines = rom.make_routines(**flow)
        self.assertEqual(
            routines[rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS][1],
            [0xAD00 | (rom.DIRECT_GENERIC_MENU_PROBE_ADDRESS >> 16),
             rom.DIRECT_GENERIC_MENU_PROBE_ADDRESS & 0xFFFF],
        )
        name, _ = routines[rom.DIRECT_GENERIC_MENU_PROBE_ADDRESS]
        self.assertEqual(name, "probe_direct_recovered_generic_menu")
        logical_stream = rom.direct_generic_menu_text_stream_logical_bytes()
        self.assertEqual(
            logical_stream.split(b"\r\n")[:-1],
            [label.encode("gb18030")
             for label in rom.DIRECT_GENERIC_MENU_TEXT_STREAM_LABELS[:-1]],
        )
        self.assertTrue(logical_stream.endswith(
            rom.DIRECT_GENERIC_MENU_TEXT_STREAM_LABELS[-1].encode(
                "gb18030"
            ) + b"\x00"
        ))
        direct_index = rom.generic_main_menu_pointer_index_logical_bytes(
            direct_text_stream=True,
        )
        direct_pointers = [
            int.from_bytes(direct_index[2 + index * 3:5 + index * 3],
                           "little")
            for index in range(rom.RESIDENT_MENU_PAGE_COUNT + 1)
        ]
        self.assertEqual(
            direct_pointers[0],
            rom.DIRECT_GENERIC_MENU_TEXT_STREAM_ADDRESS,
        )
        self.assertEqual(
            direct_pointers[1:],
            [rom.DIRECT_GENERIC_MENU_TEXT_STREAM_ADDRESS +
             len(logical_stream)] * rom.RESIDENT_MENU_PAGE_COUNT,
        )
        stored_stream = rom.initializer_probe_storage_bytes(
            logical_stream + (b"\x00" if len(logical_stream) & 1 else b""),
        )
        self.assertEqual(
            words_at(
                image,
                rom.DIRECT_GENERIC_MENU_TEXT_STREAM_ADDRESS,
                len(stored_stream) // 2,
            ),
            [int.from_bytes(stored_stream[offset:offset + 2], "little")
             for offset in range(0, len(stored_stream), 2)],
        )
        self.assertTrue(rom.manifest(image, **flow)[
            "probe_direct_generic_menu"
        ])

        factory_flow = dict(flow, factory_linked_startup=True)
        factory_image = rom.build_image(**factory_flow)
        factory_loader = rom.post_initializer_overlay_words(
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_storage_global_templates=True,
            factory_linked_startup=True,
            probe_direct_generic_menu=True,
        )
        # Storage initialization now belongs to ROM 01:0200 after BSS clear;
        # this direct-menu tail only publishes the resource window and enters
        # the exact linked system main.
        self.assertEqual(factory_loader[-9:], [
            0x68F0, 0x0200,
            0x6810, 0x00A2,
            0xC700,
            0xA8F0, 0x28E0,
            0xAD03, rom.FACTORY_SYSTEM_MAIN_DESTINATION & 0xFFFF,
        ])
        self.assertNotIn(
            [0xBD03, rom.FACTORY_SYSTEM_MAIN_DESTINATION & 0xFFFF],
            [factory_loader[index:index + 2]
             for index in range(len(factory_loader) - 1)],
        )
        self.assertEqual(
            words_at(
                factory_image,
                rom.POST_INITIALIZER_LOADER_ADDRESS,
                len(factory_loader),
            ),
            factory_loader,
        )
        linked_main = rom.factory_system_main_words(True)
        exact_main = rom.factory_system_main_words(False)
        terminal_index = (
            0x031C -
            (rom.FACTORY_SYSTEM_MAIN_DESTINATION & 0xFFFF)
        ) // 2
        self.assertEqual(linked_main[:terminal_index],
                         exact_main[:terminal_index])
        self.assertEqual(linked_main[terminal_index:terminal_index + 6], [
            0x4800, 0x381F, 0x2F00,
            0xAD03,
            rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS & 0xFFFF,
            rom.RESERVED,
        ])
        self.assertEqual(
            words_at(
                factory_image,
                rom.FACTORY_SYSTEM_MAIN_DESTINATION,
                len(linked_main),
            ),
            linked_main,
        )

    def test_factory_default_catalogue_probe_calls_exact_guest_routine(
            self) -> None:
        flow = dict(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_rom_01_return=True,
            probe_storage_global_templates=True,
            probe_factory_default_catalogue=True,
            factory_linked_startup=True,
        )
        expected = [0xBD2A, 0xA952, 0xAD03, 0x0084]
        self.assertEqual(
            rom.factory_default_catalogue_probe_words(),
            expected,
        )
        routines = rom.make_routines(**flow)
        name, words = routines[rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS]
        self.assertEqual(name, "probe_exact_factory_default_catalogue")
        self.assertEqual(words, expected)

        image = rom.build_image(**flow)
        self.assertEqual(
            words_at(
                image,
                rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS,
                len(expected),
            ),
            expected,
        )
        linked_main = rom.factory_system_main_words(True)
        self.assertEqual(
            words_at(
                image,
                rom.FACTORY_SYSTEM_MAIN_DESTINATION,
                len(linked_main),
            ),
            linked_main,
        )
        info = rom.manifest(image, **flow)
        self.assertTrue(info["probe_factory_default_catalogue"])
        self.assertFalse(info["probe_direct_generic_menu"])

        invalid = dict(flow, factory_linked_startup=False)
        with self.assertRaisesRegex(ValueError, "factory-linked startup"):
            rom.build_image(**invalid)

    def test_direct_menu_resource_context_is_guest_side_and_published(self) -> None:
        context = rom.direct_resource_context_words()
        self.assertEqual(context[:3], [0x6810, 0x5127A0 >> 15, 0xC700])
        windows = [
            context[index:index + 4]
            for index in range(len(context) - 3)
        ]
        self.assertIn([
            0x68F0, rom.DIRECT_RESOURCE_READ_CALLBACK_ADDRESS >> 16,
            0xA8F0, 0x27A4,
        ], windows)
        self.assertIn([
            0x68F0, rom.DIRECT_RESOURCE_POST_READ_ADDRESS >> 16,
            0xA8F0, 0x27A8,
        ], windows)
        self.assertIn([
            0x68F0, rom.DIRECT_RESOURCE_SECTOR_BUFFER_ADDRESS >> 16,
            0xA8F0, 0x27B8,
        ], windows)
        self.assertIn([
            0x68F0, rom.DIRECT_RESOURCE_DEVICE_ADDRESS >> 16,
            0xA8F0, 0x27C2,
        ], windows)
        self.assertIn([
            0x68F0, rom.DIRECT_RESOURCE_FILE_ADDRESS >> 16,
            0xA8F0, 0x7DEE,
        ], windows)
        self.assertEqual(context[-4:], [
            0x68F0, rom.DIRECT_RESOURCE_FILE_ADDRESS & 0xFFFF,
            0xA8F0, 0x7DF0,
        ])

        callback = rom.direct_resource_read_callback_words()
        self.assertIn([
            0x6810, rom.DIRECT_RESOURCE_FILE_ADDRESS >> 15, 0xC700,
        ], [
            callback[index:index + 3]
            for index in range(len(callback) - 2)
        ])
        self.assertIn(0x74F1, callback)
        self.assertNotIn([
            0x70F0, 0x001D,
        ], [
            callback[index:index + 2]
            for index in range(len(callback) - 1)
        ])
        self.assertIn([0xBD08, 0x43A6], [
            callback[index:index + 2]
            for index in range(len(callback) - 1)
        ])
        self.assertLessEqual(
            rom.DIRECT_RESOURCE_READ_CALLBACK_ADDRESS + len(callback) * 2,
            rom.DIRECT_RESOURCE_POST_READ_ADDRESS,
        )
        diagnostic_offset = rom.DIRECT_RESOURCE_DIAGNOSTIC_ADDRESS & 0xFFFF
        self.assertIn([
            0x68F0, 0x6840,
            0xA8F0, diagnostic_offset,
        ], [
            callback[index:index + 4]
            for index in range(len(callback) - 3)
        ])

        probe = rom.direct_generic_menu_probe_words()
        self.assertIn([
            0x6810, rom.DIRECT_GENERIC_MENU_DESCRIPTOR_ADDRESS >> 15,
            0xC700,
        ], [
            probe[index:index + 3]
            for index in range(len(probe) - 2)
        ])

    def test_direct_menu_resource_callbacks_do_not_replace_boot_storage_calls(
            self) -> None:
        flow = dict(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_rom_01_return=True,
            probe_storage_global_templates=True,
            probe_direct_generic_menu=True,
        )
        routines = rom.make_routines(**flow)
        self.assertEqual(
            routines[rom.DIRECT_RESOURCE_NEXT_CLUSTER_ADDRESS][0],
            "probe_direct_resource_next_cluster",
        )
        self.assertEqual(
            routines[rom.DIRECT_RESOURCE_READ_CALLBACK_ADDRESS][0],
            "probe_direct_resource_read_callback",
        )
        self.assertEqual(
            routines[rom.DIRECT_RESOURCE_POST_READ_ADDRESS],
            ("probe_direct_resource_post_read",
             rom.direct_resource_post_read_words()),
        )
        original_storage_relocation = [
            0xBD00 | (
                rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION >> 16
            ),
            rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION & 0xFFFF,
        ]
        for routine_address, source_address, call_source in (
            (rom.RESIDENT_TRANSFORM_1B_ADDRESS,
             rom.RESIDENT_TRANSFORM_1B_SOURCE,
             rom.RESIDENT_TRANSFORM_1B_SECTOR_PROBE_CALL_SOURCE),
            (rom.RESIDENT_TRANSFORM_1C_ADDRESS,
             rom.RESIDENT_TRANSFORM_1C_SOURCE,
             rom.RESIDENT_TRANSFORM_1C_SECTOR_PROBE_CALL_SOURCE),
        ):
            offset = (call_source - source_address) // 2
            self.assertEqual(
                routines[routine_address][1][offset:offset + 2],
                original_storage_relocation,
            )

    def test_resident_transform_1c_retargets_recovered_storage_pair(
            self) -> None:
        routines = rom.make_routines()
        self.assertEqual(
            rom.program_source_words(
                rom.RESIDENT_TRANSFORM_1C_STORAGE_PAIR_CALL_SOURCE, 4
            ),
            [0xBD30, 0x6E9E],
        )
        offset = (
            rom.RESIDENT_TRANSFORM_1C_STORAGE_PAIR_CALL_SOURCE -
            rom.RESIDENT_TRANSFORM_1C_SOURCE
        ) // 2
        expected = [
            0xBD00 | (rom.RESIDENT_STORAGE_PAIR_ADDRESS >> 16),
            rom.RESIDENT_STORAGE_PAIR_ADDRESS & 0xFFFF,
        ]
        self.assertEqual(
            routines[rom.RESIDENT_TRANSFORM_1C_ADDRESS][1][offset:offset + 2],
            expected,
        )

        # Guard the serialized artifact as well as the intermediate routine
        # table.  The v107/v108 patch chain predated this retarget and left
        # the stale 30:6E9E call in the image even though later source builds
        # contained the recovered 07:4500 helper.
        image = rom.build_image(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_rom_01_return=True,
            probe_storage_global_templates=True,
            probe_direct_generic_menu=True,
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_TRANSFORM_1C_ADDRESS + offset * 2,
                2,
            ),
            expected,
        )

    def test_out_of_line_storage_helpers_relocate_internal_ajmps(
            self) -> None:
        modules = (
            (rom.RESIDENT_STORAGE_DRIVER_SOURCE,
             rom.RESIDENT_STORAGE_DRIVER_ADDRESS,
             rom.RESIDENT_STORAGE_DRIVER_SIZE,
             rom.RESIDENT_STORAGE_DRIVER_INTERNAL_AJMPS,
             rom.resident_storage_driver_words),
            (rom.RESIDENT_STORAGE_SELECT_SOURCE,
             rom.RESIDENT_STORAGE_SELECT_ADDRESS,
             rom.RESIDENT_STORAGE_SELECT_SIZE,
             rom.RESIDENT_STORAGE_SELECT_INTERNAL_AJMPS,
             rom.resident_storage_select_words),
            (rom.RESIDENT_STORAGE_PAIR_SOURCE,
             rom.RESIDENT_STORAGE_PAIR_ADDRESS,
             rom.RESIDENT_STORAGE_PAIR_SIZE,
             rom.RESIDENT_STORAGE_PAIR_INTERNAL_AJMPS,
             rom.resident_storage_pair_words),
            (rom.RESIDENT_STORAGE_PROBE_WRAPPER_SOURCE,
             rom.RESIDENT_STORAGE_PROBE_WRAPPER_ADDRESS,
             rom.RESIDENT_STORAGE_PROBE_WRAPPER_SIZE,
             rom.RESIDENT_STORAGE_PROBE_WRAPPER_INTERNAL_AJMPS,
             rom.resident_storage_probe_wrapper_words),
            (rom.RESIDENT_STORAGE_MUL_DIV_SOURCE,
             rom.RESIDENT_STORAGE_MUL_DIV_ADDRESS,
             rom.RESIDENT_STORAGE_MUL_DIV_SIZE,
             rom.RESIDENT_STORAGE_MUL_DIV_INTERNAL_AJMPS,
             rom.resident_storage_mul_div_words),
            (rom.RESIDENT_STORAGE_SCAN_SOURCE,
             rom.RESIDENT_STORAGE_SCAN_ADDRESS,
             rom.RESIDENT_STORAGE_SCAN_SIZE,
             rom.RESIDENT_STORAGE_SCAN_INTERNAL_AJMPS,
             rom.resident_storage_scan_words),
        )
        for source, destination, size, patches, builder in modules:
            original = rom.program_source_words(source, size)
            relocated = builder()
            for branch_address, old_target_pc in patches:
                index = (branch_address - source) // 2
                self.assertEqual(
                    original[index:index + 2],
                    [relocated[index], old_target_pc],
                )
                source_target = (
                    (branch_address & 0xFF0000) | old_target_pc
                )
                expected_target = (
                    destination + source_target - source
                ) & 0xFFFF
                self.assertEqual(relocated[index] >> 8, 0xAC)
                self.assertEqual(relocated[index + 1], expected_target)

        driver = rom.resident_storage_driver_words()
        for pc_load, segment_load, return_pc, _return_segment in (
                rom.RESIDENT_STORAGE_DRIVER_CALLBACK_RETURN_FRAMES):
            pc_index = (
                pc_load - rom.RESIDENT_STORAGE_DRIVER_SOURCE
            ) // 2
            segment_index = (
                segment_load - rom.RESIDENT_STORAGE_DRIVER_SOURCE
            ) // 2
            source_return = (pc_load & 0xFF0000) | return_pc
            relocated_return = (
                rom.RESIDENT_STORAGE_DRIVER_ADDRESS + source_return -
                rom.RESIDENT_STORAGE_DRIVER_SOURCE
            ) & 0xFFFF
            self.assertEqual(
                driver[pc_index:pc_index + 2], [0x68FE, relocated_return]
            )
            self.assertEqual(
                driver[segment_index:segment_index + 2], [0x68FE, 0x0007]
            )

    def test_exact_fixed_launch_wrapper_is_reinstalled_at_manager_boundary(self) -> None:
        exact = rom.program_source_words(
            rom.RESIDENT_FIXED_LAUNCH_WRAPPER_SOURCE,
            rom.RESIDENT_FIXED_LAUNCH_WRAPPER_SIZE,
        )
        self.assertEqual(exact, [
            0x2E00, 0x58F0, 0x58F1,
            0x4810, 0x4800, 0x58F1, 0x58F0, 0x480B, 0x58F0,
            0xBD1B, 0x23B8, 0x50F6,
            0x381F, 0x380F, 0x2F00, 0xC620,
            0x2E00, 0x58F0, 0x58F1,
            0x68F1, 0xF5E2, 0x68F0, 0x0031,
            0x58F1, 0x58F0, 0xBD2E, 0xD34A, 0x50F4,
            0x381F, 0x380F, 0x2F00, 0xC620,
        ])
        copy = rom.embed_program_overlay_words(
            rom.RESIDENT_FIXED_LAUNCH_WRAPPER_DESTINATION,
            rom.RESIDENT_FIXED_LAUNCH_WRAPPER_SOURCE,
            rom.RESIDENT_FIXED_LAUNCH_WRAPPER_SIZE,
        )
        installer = rom.fixed_launch_wrapper_installer_words()
        self.assertEqual(installer[:len(copy)], copy)
        self.assertEqual(installer[-5:], [
            0x6810, 0x0000, 0x6811, 0x0001, rom.RETS,
        ])
        self.assertEqual(
            rom.RESIDENT_FIXED_LAUNCH_INSTALLER_ADDRESS +
            (len(installer) - 1) * 2,
            0x061C36,
        )
        words = rom.fixed_launch_wrapper_probe_words()
        self.assertEqual(words, [
            0xBD06, 0x1B00,
            0xBD33, 0x3CC6,
            0xAD03, 0x0088,
        ])
        preloader = rom.post_initializer_overlay_words(
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_fixed_launch_wrapper=True,
        )
        prepare = [
            0xBD00 | (rom.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS >> 16),
            rom.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS & 0xFFFF,
            0xBD25, 0x5858,
            0xBD30, 0x8C1C,
            0xBD06, 0x1B00,
            0xBD33, 0x3CA6,
            0xBD20, 0x026A,
        ]
        self.assertIn(
            prepare,
            [preloader[i:i + len(prepare)]
             for i in range(len(preloader) - len(prepare) + 1)],
        )
        image = rom.build_image(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_rom_01_return=True,
            probe_fixed_launch_wrapper=True,
        )
        self.assertEqual(
            words_at(image, rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS,
                     len(words)),
            words,
        )
        self.assertEqual(
            words_at(image, rom.RESIDENT_FIXED_LAUNCH_INSTALLER_ADDRESS,
                     len(installer)),
            installer,
        )
        template_replay = rom.storage_global_template_probe_words()
        self.assertEqual(
            words_at(image, rom.STORAGE_GLOBAL_TEMPLATE_PROBE_ADDRESS,
                     len(template_replay)),
            template_replay,
        )

    def test_system_bits_helper_is_exact_resident_guest_code(self) -> None:
        image = rom.build_image()
        name, routine = rom.make_routines()[rom.SYSTEM_BITS_RESIDENT_ADDRESS]

        self.assertEqual(name, "resident_exact_system_bits_50_5906")
        self.assertEqual(routine, list(rom.SYSTEM_BITS_OVERLAY_WORDS))
        self.assertEqual(
            words_at(image, rom.SYSTEM_BITS_RESIDENT_ADDRESS, len(routine)),
            routine,
        )
        self.assertEqual(
            rom.program_source_words(
                rom.SYSTEM_BITS_OVERLAY_SOURCE,
                rom.SYSTEM_BITS_OVERLAY_SIZE,
            ),
            routine,
        )
        flat_words = rom.program_source_words(
            rom.SYSTEM_BITS_OVERLAY_COLLISION_ADDRESS,
            rom.SYSTEM_BITS_OVERLAY_SIZE,
        )
        self.assertEqual(flat_words[:2], [0x780B, 0x0012])
        self.assertNotEqual(flat_words, routine)

    def test_system_flag_query_family_is_exact_relocated_guest_code(
            self) -> None:
        image = rom.build_image()
        name, routine = rom.make_routines()[
            rom.SYSTEM_FLAG_QUERY_RESIDENT_ADDRESS
        ]
        source = rom.program_source_words(
            rom.SYSTEM_FLAG_QUERY_SOURCE,
            rom.SYSTEM_FLAG_QUERY_SIZE,
        )

        self.assertEqual(name, "resident_exact_system_flag_queries_50_58a6")
        self.assertEqual(routine, source)
        self.assertEqual(
            words_at(
                image,
                rom.SYSTEM_FLAG_QUERY_RESIDENT_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(source, [
            0x2E00, 0x6810, 0x00A2, 0x88F0, 0x2A4E, 0x5408, 0x2F00, rom.RETS,
            0x2E00, 0x6810, 0x00A2, 0x88F0, 0x2A4E, 0x5404, 0x2F00, rom.RETS,
            0x2E00, 0x6810, 0x00A2, 0x88F0, 0x2A4E, 0x5402, 0x2F00, rom.RETS,
        ])
        flat = rom.program_source_words(
            rom.SYSTEM_FLAG_QUERY_COLLISION_ADDRESS,
            rom.SYSTEM_FLAG_QUERY_SIZE,
        )
        self.assertNotEqual(flat, source)
        self.assertEqual(flat[:4], [0x781B, 0x0010, 0x782B, 0xFFEA])

        # The current foreground loop is source-pinned by QEMU, so its
        # 3D:308E call is rewritten by mirror_np560_runtime_patches rather
        # than expanding this fixed-size resident installer.  The ROM itself
        # must never publish the helper over the active segment-33 worker.
        self.assertNotEqual(
            words_at(image, 0x3358A6, len(source)),
            source,
        )

    def test_event_e0_handler_is_exact_factory_linked_resident_code(
            self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_EVENT_E0_HANDLER_SOURCE,
            rom.RESIDENT_EVENT_E0_HANDLER_SIZE,
        )
        name, routine = rom.make_routines()[
            rom.RESIDENT_EVENT_E0_HANDLER_ADDRESS
        ]
        callback_name, callback = rom.make_routines()[
            rom.RESIDENT_EVENT_E0_CALLBACK_ADDRESS
        ]

        self.assertEqual(name, "resident_event_e0_handler_15_f0ee")
        self.assertEqual(routine, rom.resident_event_e0_handler_words())
        self.assertEqual(source[0], 0x2E57)
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        pointer = (
            rom.RESIDENT_EVENT_E0_CALLBACK_POINTER_SOURCE -
            rom.RESIDENT_EVENT_E0_HANDLER_SOURCE
        ) // 2
        self.assertEqual(
            source[pointer:pointer + 4],
            [0x68F1, 0x5896, 0x68F0, 0x0033],
        )
        self.assertEqual(
            routine[pointer:pointer + 4],
            [0x68F1, 0x1E30, 0x68F0, 0x0006],
        )
        call = (
            rom.RESIDENT_EVENT_E0_MODE_PAIR_CALL_SOURCE -
            rom.RESIDENT_EVENT_E0_HANDLER_SOURCE
        ) // 2
        self.assertEqual(source[call:call + 2], [0xBD33, 0x1BBA])
        self.assertEqual(routine[call:call + 2], [0xBD5F, 0x1BBA])
        self.assertEqual(
            rom.RESIDENT_EVENT_E0_MODE_PAIR_CALL_ADDRESS,
            0x15F31A,
        )
        self.assertEqual(
            rom.RESIDENT_EVENT_E0_MODE_PAIR_OVERLAY_ADDRESS,
            rom.APPLICATION_RESULT_MODE_PAIR_OVERLAY_DESTINATION,
        )
        expected = source.copy()
        expected[pointer:pointer + 4] = [
            0x68F1, 0x1E30, 0x68F0, 0x0006,
        ]
        expected[call:call + 2] = [0xBD5F, 0x1BBA]
        self.assertEqual(routine, expected)
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_EVENT_E0_HANDLER_ADDRESS,
                len(routine),
            ),
            routine,
        )
        table_pointer = (0x32F346 - rom.RESIDENT_EVENT_E0_HANDLER_SOURCE) // 2
        self.assertEqual(
            routine[table_pointer:table_pointer + 4],
            [0x68F3, 0xF362, 0x68F2, 0x0015],
        )
        self.assertEqual(callback_name, "resident_event_e0_callback_50_5896")
        self.assertEqual(callback, [
            0x2E00, 0x780B, 0x000A, 0x6B1B, 0x000A,
            0x4800, 0x2F00, rom.RETS,
        ])
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_EVENT_E0_CALLBACK_ADDRESS,
                len(callback),
            ),
            callback,
        )
        self.assertEqual(
            rom.RESIDENT_EVENT_E0_HANDLER_TABLE_ADDRESS,
            0x15F362,
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_EVENT_E0_HANDLER_TABLE_ADDRESS,
                rom.RESIDENT_EVENT_E0_HANDLER_TABLE_SIZE // 2,
            ),
            [0xF36E, 0xF556, 0xF73A, 0xF8AA, 0xFB8A, 0xFA1A],
        )
        for caller in (0x3BF886, 0x3D309E):
            self.assertEqual(
                rom.program_source_words(caller, 4),
                [0xBD15, 0xF0EE],
            )
        info = rom.manifest(image)["resident_event_e0_handler_15_f0ee"]
        self.assertEqual(info["callers"], ["1E:F886", "20:309E"])
        self.assertEqual(info["computed_table"], "15:F362")
        self.assertEqual(info["dependency"], "06:1E30 <- 50:5896")
        self.assertEqual(
            info["retargeted_pointer"],
            "15:F26C: 33:5896 -> 06:1E30",
        )
        self.assertEqual(
            info["retargeted_call"],
            "15:F31A: 33:1BBA -> 5F:1BBA",
        )
        self.assertIn("no host HLE", info["status"])
        callback_info = rom.manifest(image)[
            "resident_event_e0_callback_06_1e30"
        ]
        self.assertEqual(callback_info["consumer"],
                         "11:1886 synthetic far call")
        self.assertEqual(callback_info["producer_patch"], "15:F26C")

    def test_activation_probe_dispatches_once_then_polls(self) -> None:
        words = rom.resident_event_loop_words(0x000100, 0x008E)
        expected_prefix = [
            0x3F03,
            0x68F1, 0x008E,
            0x68F0, 0x0100, 0x58F0,
            0x68F0, 0x0000, 0x3F02, 0x58F0,
            0x58F1, 0xBD33, 0x4510, 0x50F6,
        ]

        self.assertEqual(words[:len(expected_prefix)], expected_prefix)
        poll_pc = 0x0080 + len(expected_prefix) * 2
        self.assertEqual(words[-2:], [0xAD03, poll_pc])
        with self.assertRaisesRegex(ValueError, "activation dispatch"):
            rom.build_image(probe_dispatch_activation=True)

    def test_zero_context_is_a_valid_bank_zero_pointer(self) -> None:
        words = rom.resident_event_loop_words(0)

        self.assertIn([0x68F0, 0x0000, 0x58F0,
                       0x68F0, 0x0000, 0x3F02, 0x58F0, 0x58F1],
                      [words[i:i + 8] for i in range(len(words) - 7)])
        self.assertIn([0xBD33, 0x4510, 0x50F6],
                      [words[i:i + 3] for i in range(len(words) - 2)])

    def test_memory_initializer_is_relocated_out_of_game_world_tail(
        self,
    ) -> None:
        system_main = rom.factory_system_main_words()
        call_index = (
            rom.MEMORY_INIT_SYSTEM_MAIN_CALL_DESTINATION -
            rom.FACTORY_SYSTEM_MAIN_DESTINATION
        ) // 2

        self.assertEqual(
            system_main[call_index:call_index + 2],
            list(rom.MEMORY_INIT_RELOCATED_CALL_WORDS),
        )
        self.assertEqual(
            rom.program_source_words(
                rom.MEMORY_INIT_OVERLAY_SOURCE,
                rom.MEMORY_INIT_OVERLAY_SIZE,
            )[:2],
            [0x2E00, 0x58F0],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.MEMORY_INIT_OVERLAY_SOURCE,
                rom.MEMORY_INIT_OVERLAY_SIZE,
            )[-2:],
            [0x2F00, rom.RETS],
        )
        self.assertNotEqual(
            rom.MEMORY_INIT_OVERLAY_DESTINATION,
            rom.MEMORY_INIT_OVERLAY_COLLISION_ADDRESS,
        )
        self.assertEqual(
            rom.MEMORY_INIT_OVERLAY_DESTINATION & 0xFFFF,
            rom.MEMORY_INIT_OVERLAY_SOURCE & 0xFFFF,
        )

    def test_overlay_utilities_are_installed_and_run_in_guest(self) -> None:
        patch = rom.install_overlay_patch_words()
        clear = rom.clear_buffer_words()
        multiply = rom.multiply_u32_words()

        for address, value in (
            (0x6042, 0xAD00 | (rom.CLEAR_OVERLAY_ADDRESS >> 16)),
            (0x6044, rom.CLEAR_OVERLAY_TARGET_PC),
        ):
            self.assertIn([0x68F0, value, 0xA8F0, address],
                          [patch[i:i + 4] for i in range(len(patch) - 3)])
        self.assertIn([0x6810, 0x004A],
                      [patch[i:i + 2] for i in range(len(patch) - 1)])
        self.assertIn([0x6810, 0x0066],
                      [patch[i:i + 2] for i in range(len(patch) - 1)])
        self.assertIn(
            [0x68F0, 0x2E00, 0xA8F0, 0x07B0,
             0x68F0, 0x58F2, 0xA8F0, 0x07B2],
            [patch[i:i + 8] for i in range(len(patch) - 7)],
        )
        self.assertIn([0x6810, 0x0065, 0x6811, 0x009F,
                       0x68F1, 0x7786, 0x68F3, 0xF786,
                       0x68F4, 0x003C],
                      [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertNotIn([
            0x6810, 0x0059, 0x6811, 0x0093,
            0x68F1, 0x1A7C, 0x68F3, 0x9A7C,
            0x68F4, rom.MEMORY_INIT_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertNotIn([
            0x6810, 0x000D, 0x6811, 0x0093,
            0x68F1, 0x1A7C, 0x68F3, 0x9A7C,
            0x68F4, rom.MEMORY_INIT_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        source_call_patch = rom.write_program_words(
            rom.MEMORY_INIT_SYSTEM_MAIN_CALL_SOURCE,
            list(rom.MEMORY_INIT_RELOCATED_CALL_WORDS),
        )
        self.assertIn(
            source_call_patch,
            [patch[i:i + len(source_call_patch)]
             for i in range(len(patch) - len(source_call_patch) + 1)],
        )
        self.assertIn([
            0x6810, 0x005C, 0x6811, 0x0096,
            0x68F1, 0x5316, 0x68F3, 0xD316,
            0x68F4, rom.TEXT_DRAW_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        for destination, source_words in (
            (rom.MODE_INIT_OVERLAY_DESTINATION,
             rom.MODE_INIT_OVERLAY_WORDS),
            (rom.MODE_MASK_OVERLAY_DESTINATION,
             rom.MODE_MASK_OVERLAY_WORDS),
            (rom.SYSTEM_INIT_OVERLAY_DESTINATION,
             rom.SYSTEM_INIT_RELOCATED_OVERLAY_WORDS),
            (rom.APPLICATION_STATE_BYTE_OVERLAY_DESTINATION,
             rom.APPLICATION_STATE_BYTE_OVERLAY_WORDS),
            (rom.GLOBAL_RESET_OVERLAY_DESTINATION,
             rom.GLOBAL_RESET_OVERLAY_WORDS),
            (rom.SYSTEM_MODE_OVERLAY_DESTINATION,
             rom.SYSTEM_MODE_OVERLAY_WORDS),
            (rom.STARTUP_TABLE_SERVICE_OVERLAY_DESTINATION,
             rom.STARTUP_TABLE_SERVICE_OVERLAY_WORDS),
            (rom.STARTUP_REGION_SERVICE_OVERLAY_DESTINATION,
             rom.STARTUP_REGION_SERVICE_OVERLAY_WORDS),
        ):
            logical = destination & 0x7FFF
            for index, value in enumerate(source_words):
                self.assertIn(
                    [0x68F0, value, 0xA8F0, logical + index * 2],
                    [patch[i:i + 4] for i in range(len(patch) - 3)],
                )
        collision_install = rom.write_program_words(
            rom.SYSTEM_BITS_OVERLAY_COLLISION_ADDRESS,
            rom.SYSTEM_BITS_OVERLAY_WORDS,
        )
        self.assertNotIn(
            collision_install,
            [patch[i:i + len(collision_install)]
             for i in range(len(patch) - len(collision_install) + 1)],
        )
        relocated_resource_call = rom.write_program_words(
            rom.APPLICATION_RESOURCE_LOOP_OVERLAY_DESTINATION +
            rom.APPLICATION_RESOURCE_LOOP_SYSTEM_BITS_CALL_OFFSET,
            (0xBD06, 0x1CE0),
        )
        self.assertIn(
            relocated_resource_call,
            [patch[i:i + len(relocated_resource_call)]
             for i in range(len(patch) - len(relocated_resource_call) + 1)],
        )
        for destination, source, size in (
            (rom.POINTER_STATE_OVERLAY_DESTINATION,
             rom.POINTER_STATE_OVERLAY_SOURCE,
             rom.POINTER_STATE_OVERLAY_SIZE),
            (rom.POINTER_FLAG_OVERLAY_DESTINATION,
             rom.POINTER_FLAG_OVERLAY_SOURCE,
             rom.POINTER_FLAG_OVERLAY_SIZE),
            (rom.POINTER_NORMALIZE_OVERLAY_DESTINATION,
             rom.POINTER_NORMALIZE_OVERLAY_SOURCE,
             rom.POINTER_NORMALIZE_OVERLAY_SIZE),
            (rom.UINT32_MULTIPLY_OVERLAY_DESTINATION,
             rom.UINT32_MULTIPLY_OVERLAY_SOURCE,
             rom.UINT32_MULTIPLY_OVERLAY_SIZE),
            (rom.STORAGE_UNIT_SELECT_OVERLAY_DESTINATION,
             rom.STORAGE_UNIT_SELECT_OVERLAY_SOURCE,
             rom.STORAGE_UNIT_SELECT_OVERLAY_SIZE),
            (rom.APPLICATION_EVENT_GATE_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_GATE_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_GATE_OVERLAY_SIZE),
            (rom.APPLICATION_EVENT_ENABLE_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_ENABLE_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_ENABLE_OVERLAY_SIZE),
            (rom.APPLICATION_KEY_COUNTER_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_COUNTER_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_COUNTER_OVERLAY_SIZE),
            (rom.APPLICATION_KEY_SYNC_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_SYNC_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_SYNC_OVERLAY_SIZE),
            (rom.APPLICATION_HW_STATE_OVERLAY_DESTINATION,
             rom.APPLICATION_HW_STATE_OVERLAY_SOURCE,
             rom.APPLICATION_HW_STATE_OVERLAY_SIZE),
            (rom.APPLICATION_POWER_STATE_OVERLAY_DESTINATION,
             rom.APPLICATION_POWER_STATE_OVERLAY_SOURCE,
             rom.APPLICATION_POWER_STATE_OVERLAY_SIZE),
            (rom.APPLICATION_DEVICE_QUERY_OVERLAY_DESTINATION,
             rom.APPLICATION_DEVICE_QUERY_OVERLAY_SOURCE,
             rom.APPLICATION_DEVICE_QUERY_OVERLAY_SIZE),
            (rom.APPLICATION_DEVICE_APPLY_OVERLAY_DESTINATION,
             rom.APPLICATION_DEVICE_APPLY_OVERLAY_SOURCE,
             rom.APPLICATION_DEVICE_APPLY_OVERLAY_SIZE),
            (rom.APPLICATION_STATE_MODE_OVERLAY_DESTINATION,
             rom.APPLICATION_STATE_MODE_OVERLAY_SOURCE,
             rom.APPLICATION_STATE_MODE_OVERLAY_SIZE),
            (rom.APPLICATION_EVENT_INDEX_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_INDEX_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_INDEX_OVERLAY_SIZE),
            (rom.APPLICATION_EVENT_CONTROL_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_CONTROL_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_CONTROL_OVERLAY_SIZE),
            (rom.APPLICATION_OBJECT_RELEASE_OVERLAY_DESTINATION,
             rom.APPLICATION_OBJECT_RELEASE_OVERLAY_SOURCE,
             rom.APPLICATION_OBJECT_RELEASE_OVERLAY_SIZE),
            (rom.APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_DESTINATION,
             rom.APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SOURCE,
             rom.APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SIZE),
            (rom.APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_DESTINATION,
             rom.APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SOURCE,
             rom.APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SIZE),
            (rom.APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_DESTINATION,
             rom.APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SOURCE,
             rom.APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SIZE),
            (rom.APPLICATION_ASCII_WHITESPACE_OVERLAY_DESTINATION,
             rom.APPLICATION_ASCII_WHITESPACE_OVERLAY_SOURCE,
             rom.APPLICATION_ASCII_WHITESPACE_OVERLAY_SIZE),
            (rom.UINT32_MODULO_WRAPPER_OVERLAY_DESTINATION,
             rom.UINT32_MODULO_WRAPPER_OVERLAY_SOURCE,
             rom.UINT32_MODULO_WRAPPER_OVERLAY_SIZE),
            (rom.INT32_MODULO_WRAPPER_OVERLAY_DESTINATION,
             rom.INT32_MODULO_WRAPPER_OVERLAY_SOURCE,
             rom.INT32_MODULO_WRAPPER_OVERLAY_SIZE),
            (rom.UINT32_DIVIDE_WRAPPER_OVERLAY_DESTINATION,
             rom.UINT32_DIVIDE_WRAPPER_OVERLAY_SOURCE,
             rom.UINT32_DIVIDE_WRAPPER_OVERLAY_SIZE),
            (rom.UINT32_MSB_INDEX_OVERLAY_DESTINATION,
             rom.UINT32_MSB_INDEX_OVERLAY_SOURCE,
             rom.UINT32_MSB_INDEX_OVERLAY_SIZE),
            (rom.UINT32_NORMALIZE_OVERLAY_DESTINATION,
             rom.UINT32_NORMALIZE_OVERLAY_SOURCE,
             rom.UINT32_NORMALIZE_OVERLAY_SIZE),
            (rom.APPLICATION_RECORD_DISPATCH_OVERLAY_DESTINATION,
             rom.APPLICATION_RECORD_DISPATCH_OVERLAY_SOURCE,
             rom.APPLICATION_RECORD_DISPATCH_OVERLAY_SIZE),
        ):
            logical = destination & 0x7FFF
            source_words = rom.program_source_words(source, size)
            for index, value in enumerate(source_words):
                self.assertIn(
                    [0x68F0, value, 0xA8F0, logical + index * 2],
                    [patch[i:i + 4] for i in range(len(patch) - 3)],
                )
        # These sources are in immutable program banks, so the guest loader
        # installs them with the recovered far-copy helper instead of
        # expanding every source word into immediate writes.
        for destination, source, size in (
            (rom.APPLICATION_DISPATCH_POLL_OVERLAY_DESTINATION,
             rom.APPLICATION_DISPATCH_POLL_OVERLAY_SOURCE,
             rom.APPLICATION_DISPATCH_POLL_OVERLAY_SIZE),
            (rom.APPLICATION_KEY_GPIO_SCAN_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_GPIO_SCAN_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_GPIO_SCAN_OVERLAY_SIZE),
            (rom.APPLICATION_KEY_ACTIVITY_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_ACTIVITY_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_ACTIVITY_OVERLAY_SIZE),
            (rom.APPLICATION_NPE_TABLE_MODE_INIT_OVERLAY_DESTINATION,
             rom.APPLICATION_NPE_TABLE_MODE_INIT_OVERLAY_SOURCE,
             rom.APPLICATION_NPE_TABLE_MODE_INIT_OVERLAY_SIZE),
        ):
            descriptor = [
                0x6810, destination >> 15,
                0x6811, source >> 15,
                0x68F1, destination & 0x7FFF,
                0x68F3, 0x8000 | (source & 0x7FFF),
                0x68F4, size,
            ]
            self.assertIn(
                descriptor,
                [patch[i:i + len(descriptor)]
                 for i in range(len(patch) - len(descriptor) + 1)],
            )

        npe_table_mode_init = rom.program_source_words(
            rom.APPLICATION_NPE_TABLE_MODE_INIT_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_TABLE_MODE_INIT_OVERLAY_SIZE,
        )
        self.assertEqual(
            npe_table_mode_init[:9],
            [0x2E01, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
             0x58F4, 0x58F5, 0x58F6, 0x58F7],
        )
        self.assertEqual(
            npe_table_mode_init[-10:],
            [0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
             0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )

        ui_state = rom.program_source_words(
            rom.APPLICATION_UI_STATE_OVERLAY_SOURCE,
            rom.APPLICATION_UI_STATE_OVERLAY_SIZE,
        )
        self.assertEqual(ui_state[:7],
                         [0x2E04, 0x58F0, 0x58F1, 0x58F2,
                          0x58F3, 0x58F4, 0x58F5])
        self.assertEqual(ui_state[-8:],
                         [0x385F, 0x384F, 0x383F, 0x382F,
                          0x381F, 0x380F, 0x2F00, rom.RETS])
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_UI_PREPARE_OVERLAY_SOURCE,
                rom.APPLICATION_UI_PREPARE_OVERLAY_SIZE,
            ),
            [0x2E00, 0xBD2F, 0xD266, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_OPERATION_UI_PREPARE_OVERLAY_SOURCE,
                rom.APPLICATION_OPERATION_UI_PREPARE_OVERLAY_SIZE,
            ),
            [0x2E00, 0xBD2F, 0xD266, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_UI_PROPERTY_OVERLAY_SOURCE,
                rom.APPLICATION_UI_PROPERTY_OVERLAY_SIZE,
            )[:5],
            [0x2E00, 0x58F0, 0x780B, 0x0006, 0x58F0],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_UI_COMMIT_OVERLAY_SOURCE,
                rom.APPLICATION_UI_COMMIT_OVERLAY_SIZE,
            ),
            [0x2E00, 0xBD31, 0x4BAC, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.ROM03_FAR_MEMCPY_THUNK_SOURCE,
                rom.ROM03_FAR_MEMCPY_THUNK_SIZE,
            ),
            [0xAD18, 0x6D56],
        )
        state_pointer = rom.program_source_words(
            rom.APPLICATION_MAIN_STATE_POINTER_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_STATE_POINTER_OVERLAY_SIZE,
        )
        self.assertEqual(state_pointer[:3], [0x2E02, 0x68F1, 0x4A40])
        self.assertEqual(state_pointer[-2:], [0x2F00, rom.RETS])
        self.assertIn([
            0x6810, 0x0063, 0x6811, 0x009D,
            0x68F1, 0x2F72, 0x68F3, 0xAF72,
            0x68F4, rom.MEMORY_RESET_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0063, 0x6811, 0x009D,
            0x68F1, 0x3014, 0x68F3, 0xB014,
            0x68F4, rom.MEMORY_MODE_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0064, 0x6811, 0x009E,
            0x68F1, 0x4218, 0x68F3, 0xC218,
            0x68F4, rom.STARTUP_TABLE_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0065, 0x6811, 0x009F,
            0x68F1, 0x4C9C, 0x68F3, 0xCC9C,
            0x68F4, rom.STARTUP_POINTER_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0065, 0x6811, 0x009F,
            0x68F1, 0x0EBE, 0x68F3, 0x8EBE,
            0x68F4, rom.STARTUP_ARRAY_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0062, 0x6811, 0x009C,
            0x68F1, 0x4BAC, 0x68F3, 0xCBAC,
            0x68F4, rom.STARTUP_RUNTIME_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0063, 0x6811, 0x009D,
            0x68F1, 0x2914, 0x68F3, 0xA914,
            0x68F4, rom.APPLICATION_LCD_INIT_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0049, 0x6811, 0x0083,
            0x68F1, 0x1BD4, 0x68F3, 0x9BD4,
            0x68F4, rom.PERIPHERAL_INIT_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0061, 0x6811, 0x009B,
            0x68F1, 0x1E30, 0x68F3, 0x9E30,
            0x68F4, rom.ACTIVATION_CONTEXT_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0065, 0x6811, 0x009F,
            0x68F1, 0x5530, 0x68F3, 0xD530,
            0x68F4, rom.POINTER_SERVICE_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0063, 0x6811, 0x009D,
            0x68F1, 0x7282, 0x68F3, 0xF282,
            0x68F4, rom.POINTER_RESOLVE_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        for descriptor in (
            [0x6810, 0x005E, 0x6811, 0x0098,
             0x68F1, 0x5B98, 0x68F3, 0xDB98,
             0x68F4, rom.APPLICATION_COMMAND_OVERLAY_SIZE],
            [0x6810, 0x0062, 0x6811, 0x009C,
             0x68F1, 0x5BB8, 0x68F3, 0xDBB8,
             0x68F4, rom.COMMAND_TABLE_PRIMARY_OVERLAY_SIZE],
            [0x6810, 0x0062, 0x6811, 0x009C,
             0x68F1, 0x5A44, 0x68F3, 0xDA44,
             0x68F4, rom.COMMAND_TABLE_SECONDARY_OVERLAY_SIZE],
            [0x6810, 0x0062, 0x6811, 0x009C,
             0x68F1, 0x598A, 0x68F3, 0xD98A,
             0x68F4, rom.COMMAND_TABLE_TERTIARY_OVERLAY_SIZE],
            [0x6810, 0x005E, 0x6811, 0x0098,
             0x68F1, 0x6BFA, 0x68F3, 0xEBFA,
             0x68F4, rom.COMMAND_TABLE_TEMPLATE_OVERLAY_SIZE],
            [0x6810, 0x0061, 0x6811, 0x009B,
             0x68F1, 0x56D0, 0x68F3, 0xD6D0,
             0x68F4, rom.COMMAND_MATRIX_OVERLAY_SIZE],
            [0x6810, 0x0065, 0x6811, 0x009F,
             0x68F1, 0x4A88, 0x68F3, 0xCA88,
             0x68F4, rom.APPLICATION_MODE_OVERLAY_SIZE],
            [0x6810, 0x0065, 0x6811, 0x009F,
             0x68F1, 0x1D22, 0x68F3, 0x9D22,
             0x68F4, rom.APPLICATION_SLOT_OVERLAY_SIZE],
            [0x6810, 0x0064, 0x6811, 0x009E,
             0x68F1, 0x2102, 0x68F3, 0xA102,
             0x68F4, rom.APPLICATION_TRIPLE_OVERLAY_SIZE],
            [0x6810, 0x0052, 0x6811, 0x008C,
             0x68F1, 0x13DC, 0x68F3, 0x93DC,
             0x68F4, rom.APPLICATION_PAGE_SETUP_OVERLAY_SIZE],
            [0x6810, 0x0050, 0x6811, 0x008A,
             0x68F1, 0x1F08, 0x68F3, 0x9F08,
             0x68F4, rom.APPLICATION_TEXT_LOOP_OVERLAY_SIZE],
            [0x6810, 0x004B, 0x6811, 0x0085,
             0x68F1, 0x4C94, 0x68F3, 0xCC94,
             0x68F4, rom.APPLICATION_RESOURCE_LOOP_OVERLAY_SIZE],
            [0x6810, 0x004A, 0x6811, 0x0084,
             0x68F1, 0x5858, 0x68F3, 0xD858,
             0x68F4, rom.APPLICATION_STORAGE_REGISTRY_OVERLAY_SIZE],
            [0x6810, 0x0048, 0x6811, 0x0082,
             0x68F1, 0x236A, 0x68F3, 0xA36A,
             0x68F4, rom.STORAGE_BAD_BLOCK_STATUS_OVERLAY_SIZE],
            [0x6810, 0x0061, 0x6811, 0x009B,
             0x68F1, 0x23C2, 0x68F3, 0xA3C2,
             0x68F4, rom.APPLICATION_STORAGE_UNIT_OPEN_OVERLAY_SIZE],
            [0x6810, 0x0059, 0x6811, 0x0093,
             0x68F1, 0x76A6, 0x68F3, 0xF6A6,
             0x68F4, rom.STORAGE_ASYNC_RANGE_OVERLAY_SIZE],
            [0x6810, 0x0065, 0x6811, 0x009F,
             0x68F1, 0x6C6E, 0x68F3, 0xEC6E,
             0x68F4, rom.STORAGE_RANGE_DISPATCH_OVERLAY_SIZE],
            [0x6810, 0x0058, 0x6811, 0x0092,
             0x68F1, 0x38C0, 0x68F3, 0xB8C0,
             0x68F4, rom.STORAGE_FIELD_PARSE_OVERLAY_SIZE],
            [0x6810, 0x0061, 0x6811, 0x009B,
             0x68F1, 0x5A48, 0x68F3, 0xDA48,
             0x68F4, rom.STORAGE_BUFFER_DECODE_OVERLAY_SIZE],
            [0x6810, 0x0064, 0x6811, 0x009E,
             0x68F1, 0x0B6A, 0x68F3, 0x8B6A,
             0x68F4, rom.STORAGE_EVENT_POLL_OVERLAY_SIZE],
            [0x6810, 0x0041, 0x6811, 0x007B,
             0x68F1, 0x01E0, 0x68F3, 0x81E0,
             0x68F4, rom.APPLICATION_RESULT_RECORD_PARSE_OVERLAY_SIZE],
            [0x6810, 0x0065, 0x6811, 0x009F,
             0x68F1, 0x0524, 0x68F3, 0x8524,
             0x68F4, rom.APPLICATION_RESULT_REGION_PREPARE_OVERLAY_SIZE],
            [0x6810, 0x0063, 0x6811, 0x009D,
             0x68F1, 0x47A4, 0x68F3, 0xC7A4,
             0x68F4, rom.APPLICATION_RESULT_DISPLAY_SETUP_OVERLAY_SIZE],
            [0x6810, 0x0065, 0x6811, 0x009F,
             0x68F1, 0x3B60, 0x68F3, 0xBB60,
             0x68F4, rom.APPLICATION_RESULT_RESOURCE_RESET_OVERLAY_SIZE],
            [0x6810, 0x0050, 0x6811, 0x008A,
             0x68F1, 0x5902, 0x68F3, 0xD902,
             0x68F4, rom.APPLICATION_RESULT_BUILD_OVERLAY_SIZE],
            [0x6810, 0x0058, 0x6811, 0x0092,
             0x68F1, 0x48A8, 0x68F3, 0xC8A8,
             0x68F4, rom.FAR_NORMALIZED_MEMORY_COMPARE_OVERLAY_SIZE],
            [0x6810, 0x004B, 0x6811, 0x0085,
             0x68F1, 0x6324, 0x68F3, 0xE324,
             0x68F4, rom.APPLICATION_STORAGE_ENTRY_ATTACH_OVERLAY_SIZE],
            [0x6810, 0x0063, 0x6811, 0x009D,
             0x68F1, 0x7670, 0x68F3, 0xF670,
             0x68F4, rom.APPLICATION_POINTER_UPDATE_OVERLAY_SIZE],
            [0x6810, 0x0065, 0x6811, 0x009F,
             0x68F1, 0x2FEE, 0x68F3, 0xAFEE,
             0x68F4, rom.STORAGE_RUNTIME_STATE_RESET_OVERLAY_SIZE],
            [0x6810, 0x0065, 0x6811, 0x009F,
             0x68F1, 0x7A40, 0x68F3, 0xFA40,
             0x68F4, rom.STORAGE_RUNTIME_TABLE_RESET_OVERLAY_SIZE],
            [0x6810, 0x0049, 0x6811, 0x0083,
             0x68F1, 0x3D76, 0x68F3, 0xBD76,
             0x68F4, rom.APPLICATION_STORAGE_MAINTENANCE_OVERLAY_SIZE],
            [0x6810, 0x004E, 0x6811, 0x0088,
             0x68F1, 0x0000, 0x68F3, 0x8000,
             0x68F4, rom.APPLICATION_STORAGE_BLOCK_OVERLAY_SIZE],
            [0x6810, 0x0056, 0x6811, 0x0090,
             0x68F1, 0x4C0A, 0x68F3, 0xCC0A,
             0x68F4, rom.APPLICATION_STORAGE_VERIFY_OVERLAY_SIZE],
            [0x6810, 0x0063, 0x6811, 0x009D,
             0x68F1, 0x0C18, 0x68F3, 0x8C18,
             0x68F4, rom.APPLICATION_STORAGE_TRANSFER_OVERLAY_SIZE],
            [0x6810, 0x0051, 0x6811, 0x008B,
             0x68F1, 0x4C5A, 0x68F3, 0xCC5A,
             0x68F4, rom.APPLICATION_STORAGE_MAP_OVERLAY_SIZE],
            [0x6810, 0x0060, 0x6811, 0x009A,
             0x68F1, 0x3E86, 0x68F3, 0xBE86,
             0x68F4, rom.APPLICATION_STATE_DISPATCH_OVERLAY_SIZE],
            [0x6810, 0x0051, 0x6811, 0x008B,
             0x68F1, 0x02F4, 0x68F3, 0x82F4,
             0x68F4, rom.APPLICATION_STATE_PREPARE_OVERLAY_SIZE],
            [0x6810, 0x0053, 0x6811, 0x008D,
             0x68F1, 0x0CAA, 0x68F3, 0x8CAA,
             0x68F4, rom.APPLICATION_STATE_POINTER_OVERLAY_SIZE],
            [0x6810, 0x0052, 0x6811, 0x008C,
             0x68F1, 0x24C6, 0x68F3, 0xA4C6,
             0x68F4, rom.APPLICATION_STATE_RECORD_OVERLAY_SIZE],
            [0x6810, 0x0063, 0x6811, 0x009D,
             0x68F1, 0x1C1E, 0x68F3, 0x9C1E,
             0x68F4, rom.APPLICATION_STATE_CLASSIFY_OVERLAY_SIZE],
            [0x6810, 0x005E, 0x6811, 0x0098,
             0x68F1, 0x3A48, 0x68F3, 0xBA48,
             0x68F4, rom.APPLICATION_STATE_SERVICE_OVERLAY_SIZE],
            [0x6810, 0x0045, 0x6811, 0x007F,
             0x68F1, 0x7D9E, 0x68F3, 0xFD9E,
             0x68F4, rom.APPLICATION_STATE_TRANSFORM_OVERLAY_SIZE],
            [0x6810, 0x0063, 0x6811, 0x009D,
             0x68F1, 0x59AA, 0x68F3, 0xD9AA,
             0x68F4, rom.APPLICATION_STATE_FLAGS_OVERLAY_SIZE],
            [0x6810, 0x005A, 0x6811, 0x0094,
             0x68F1, 0x2D40, 0x68F3, 0xAD40,
             0x68F4, rom.APPLICATION_STATE_POWER_OVERLAY_SIZE],
            [0x6810, 0x005F, 0x6811, 0x0099,
             0x68F1, 0x7A32, 0x68F3, 0xFA32,
             0x68F4, rom.APPLICATION_STATE_TICK_OVERLAY_SIZE],
            [0x6810, 0x0045, 0x6811, 0x007F,
             0x68F1, 0x740C, 0x68F3, 0xF40C,
             0x68F4, rom.APPLICATION_STATE_UI_OVERLAY_SIZE],
        ):
            self.assertIn(
                descriptor,
                [patch[i:i + 10] for i in range(len(patch) - 9)],
            )
        self.assertIn(
            [0x6810, 0x0031,
             0x68F0, 0x2E09, 0xA8F0, 0x797C,
             0x68F0, 0x58F1, 0xA8F0, 0x797E],
            [patch[i:i + 10] for i in range(len(patch) - 9)],
        )
        self.assertIn(
            [0x6810, 0x00BF, 0x6811, 0x009F,
             0x68F1, 0x4336, 0x68F3, 0xC336,
             0x68F4, rom.APPLICATION_STATE_ADC_OVERLAY_SIZE],
            [patch[i:i + 10] for i in range(len(patch) - 9)],
        )
        self.assertIn(
            [0x6810, 0x0064, 0x6811, 0x009E,
             0x68F1, 0x136C, 0x68F3, 0x936C,
             0x68F4, rom.APPLICATION_COMPARE_MODE_OVERLAY_SIZE],
            [patch[i:i + 10] for i in range(len(patch) - 9)],
        )
        self.assertIn(
            [0x6810, 0x004E, 0x6811, 0x0088,
             0x68F1, 0x287C, 0x68F3, 0xA87C,
             0x68F4, rom.APPLICATION_STORAGE_SCAN_OVERLAY_SIZE],
            [patch[i:i + 10] for i in range(len(patch) - 9)],
        )
        self.assertIn(
            [0x6810, 0x0065, 0x6811, 0x009F,
             0x68F1, 0x0E5C, 0x68F3, 0x8E5C,
             0x68F4, rom.APPLICATION_DISPLAY_RESET_OVERLAY_SIZE],
            [patch[i:i + 10] for i in range(len(patch) - 9)],
        )
        self.assertIn(
            [0x6810, 0x0045,
             0x68F0, 0xBD5F, 0xA8F0, 0x7430,
             0x68F0, 0xC336, 0xA8F0, 0x7432],
            [patch[i:i + 10] for i in range(len(patch) - 9)],
        )
        self.assertIn([
            0x6810, 0x004E, 0x6811, 0x0088,
            0x68F1, 0x507C, 0x68F3, 0xD07C,
            0x68F4, rom.ACTIVATION_DISPATCH_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0063, 0x6811, 0x009D,
            0x68F1, 0x40E8, 0x68F3, 0xC0E8,
            0x68F4, rom.APPLICATION_PROPERTY_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0062, 0x6811, 0x009C,
            0x68F1, 0x4D24, 0x68F3, 0xCD24,
            0x68F4, rom.PROPERTY_SETTER_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x004A, 0x6811, 0x0084,
            0x68F1, 0x206E, 0x68F3, 0xA06E,
            0x68F4, rom.LCD_RESOURCE_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0061, 0x6811, 0x009B,
            0x68F1, 0x5350, 0x68F3, 0xD350,
            0x68F4, rom.LCD_TIMING_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0061, 0x6811, 0x009B,
            0x68F1, 0x0C1C, 0x68F3, 0x8C1C,
            0x68F4, rom.APPLICATION_STATE_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0061, 0x6811, 0x009B,
            0x68F1, 0x7E0E, 0x68F3, 0xFE0E,
            0x68F4, rom.MEMORY_FILL_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        self.assertIn([
            0x6810, 0x0065, 0x6811, 0x009F,
            0x68F1, 0x1B56, 0x68F3, 0x9B56,
            0x68F4, rom.APPLICATION_RANGE_OVERLAY_SIZE,
        ], [patch[i:i + 10] for i in range(len(patch) - 9)])
        for descriptor in (
            [0x6810, 0x0062, 0x6811, 0x009C,
             0x68F1, 0x5EA0, 0x68F3, 0xDEA0,
             0x68F4, rom.APPLICATION_TABLE_INIT_OVERLAY_SIZE],
            [0x6810, 0x0064, 0x6811, 0x009E,
             0x68F1, 0x6358, 0x68F3, 0xE358,
             0x68F4, rom.APPLICATION_TABLE_CLEAR_OVERLAY_SIZE],
            [0x6810, 0x0064, 0x6811, 0x009E,
             0x68F1, 0x2520, 0x68F3, 0xA520,
             0x68F4, rom.APPLICATION_BUFFER_COPY_OVERLAY_SIZE],
        ):
            self.assertIn(
                descriptor,
                [patch[i:i + 10] for i in range(len(patch) - 9)],
            )
        self.assertIn([0x5640, 0xD105, 0x2B13, 0x5011,
                       0x5031, 0x5241, 0xD0F9],
                      [patch[i:i + 7] for i in range(len(patch) - 6)])
        self.assertEqual(patch[-4:], [0x6810, 0x0000, 0x6811, 0x0001])
        self.assertIn(0x1B23, clear)
        self.assertIn([0x4C21, 0x5C11, 0x58F1, 0x1F90, 0x4D21],
                      [clear[i:i + 5] for i in range(len(clear) - 4)])
        self.assertEqual(clear[-1], rom.RETS)
        self.assertEqual(multiply[:8], [
            0x780F, 4, 0x781F, 6, 0x782F, 8, 0x783F, 10,
        ])
        self.assertEqual(multiply.count(0xC113), 1)
        self.assertEqual(multiply.count(0xC103), 1)
        self.assertEqual(multiply.count(0xC112), 1)
        self.assertEqual(multiply[-3:], [0x381F, 0x0804, rom.RETS])

    def test_overlay_copy_uses_distinct_data_selectors(self) -> None:
        words = rom.copy_code_to_overlay_words(0x2C9A7C, 0x499A7C, 0x01EA)

        self.assertEqual(words[:10], [
            0x6810, 0x0059,
            0x6811, 0x0093,
            0x68F1, 0x1A7C,
            0x68F3, 0x9A7C,
            0x68F4, 0x01EA,
        ])
        self.assertEqual(words[-4:], [0x6810, 0, 0x6811, 1])

        with self.assertRaisesRegex(ValueError, "overlay length"):
            rom.copy_code_to_overlay_words(0x2C9A7C, 0x499A7C, 0)

    def test_overlay_copy_splits_at_both_32k_data_bank_edges(self) -> None:
        words = rom.copy_code_to_overlay_words(
            rom.APPLICATION_TOP_LEVEL_OVERLAY_DESTINATION,
            rom.APPLICATION_TOP_LEVEL_OVERLAY_SOURCE,
            rom.APPLICATION_TOP_LEVEL_OVERLAY_SIZE,
        )
        descriptors = [
            words[index:index + 10]
            for index in range(len(words) - 9)
            if words[index] == 0x6810 and words[index + 2] == 0x6811
            and words[index + 4] == 0x68F1 and words[index + 6] == 0x68F3
            and words[index + 8] == 0x68F4
        ]
        self.assertEqual(descriptors, [
            [0x6810, 0x005A, 0x6811, 0x0094,
             0x68F1, 0x7DD2, 0x68F3, 0xFDD2, 0x68F4, 0x022E],
            [0x6810, 0x005B, 0x6811, 0x0095,
             0x68F1, 0x0000, 0x68F3, 0x8000, 0x68F4, 0x013E],
        ])
        self.assertEqual(words[-4:], [0x6810, 0, 0x6811, 1])

    def test_command_table_template_is_exact_data_overlay(self) -> None:
        words = rom.program_source_words(
            rom.COMMAND_TABLE_TEMPLATE_OVERLAY_SOURCE,
            rom.COMMAND_TABLE_TEMPLATE_OVERLAY_SIZE,
        )

        self.assertEqual(len(words), 32 * 5)
        self.assertEqual(words[:5], [0x0000, 0x0000, 0x0020, 0x0006, 0x000C])
        self.assertEqual(words[2 * 5:3 * 5],
                         [0x0000, 0x2000, 0x0020, 0x0006, 0x000C])
        self.assertEqual(words[-5:],
                         [0x0007, 0xB7F0, 0x000C, 0x0008, 0x000C])

    def test_storage_geometry_defaults_are_embedded_exactly(self) -> None:
        self.assertEqual(
            rom.STORAGE_GEOMETRY_DEFAULT_WORDS,
            (0x0040, 0x0800, 0x0040, 0x00DC, 0x1000),
        )
        expected = rom.install_initializer_data_overlay_words()
        patch = rom.post_initializer_overlay_words(
            probe_stop_after_overlay_install=True,
        )
        self.assertIn(
            expected,
            [patch[i:i + len(expected)]
             for i in range(len(patch) - len(expected) + 1)],
        )

    def test_keyboard_matrix_and_event_tables_are_exact_data_overlays(self) -> None:
        matrix = rom.program_source_words(
            rom.KEY_MATRIX_TABLE_SOURCE,
            rom.KEY_MATRIX_TABLE_SIZE,
        )
        self.assertEqual(matrix[:8], [
            0x0004, 0x0008, 0x0010, 0x0020,
            0x0040, 0x0080, 0x4000, 0x8000,
        ])
        self.assertEqual(matrix[8:], [
            0x0001, 0x0002, 0x0004, 0x0008,
            0x0010, 0x0020, 0x0040, 0x0080,
        ])
        alpha = rom.program_source_words(
            rom.KEY_EVENT_TABLES_SOURCE + 0x100,
            0x0080,
        )
        self.assertEqual(
            [alpha[index] for index in (61, 37, 28, 20)],
            [0x0082, 0x0083, 0x0084, 0x0085],
        )
        patch = rom.install_initializer_data_overlay_words()
        matrix_install = rom.embed_program_data_words(
            rom.KEY_MATRIX_TABLE_DESTINATION,
            rom.KEY_MATRIX_TABLE_SOURCE,
            rom.KEY_MATRIX_TABLE_SIZE,
        )
        event_install = rom.copy_code_to_overlay_words(
            rom.KEY_EVENT_TABLES_DESTINATION,
            rom.KEY_EVENT_TABLES_SOURCE,
            rom.KEY_EVENT_TABLES_SIZE,
        )
        self.assertIn(
            matrix_install,
            [patch[i:i + len(matrix_install)]
             for i in range(len(patch) - len(matrix_install) + 1)],
        )
        self.assertIn(
            event_install,
            [patch[i:i + len(event_install)]
             for i in range(len(patch) - len(event_install) + 1)],
        )

    def test_far_memcpy_uses_exact_same_pc_source(self) -> None:
        words = rom.far_memcpy_words()

        self.assertEqual(
            words,
            rom.program_source_words(rom.FAR_MEMCPY_SOURCE,
                                     rom.FAR_MEMCPY_SIZE),
        )
        self.assertEqual(words[:16], [
            0x2E02, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4,
            0x58F5, 0x58F6, 0x58F7, 0x1F10, 0x1F11, 0x58FB,
            0x1F0A, 0x1F02, 0x785B, 0x000E,
        ])
        self.assertIn(
            [0x3F10, 0x8810, 0xF2E0, 0x783B, 0x000A,
             0x784B, 0x000C, 0x0803, 0x4C41, 0x5C01,
             0x4D41, 0x3F10, 0x8811, 0xF2E0],
            [words[i:i + 14] for i in range(len(words) - 13)],
        )
        self.assertIn(
            [0xCF05, 0x5B24],
            [words[i:i + 2] for i in range(len(words) - 1)],
        )
        self.assertEqual(
            words[-9:],
            [0x385F, 0x384F, 0x383F, 0x382F, 0x381F, 0x380F,
             0x2F00, 0x3F00, rom.RETS],
        )

    def test_reverse_far_memmove_is_guest_executable_overlay(self) -> None:
        words = rom.reverse_far_memmove_words()

        self.assertEqual(len(words) * 2, 0x00A0)
        self.assertEqual(words[:12], [
            0x2E02,
            0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4, 0x58F5,
            0x1F10, 0x1F11, 0x58FB, 0x1F0A, 0x1F02,
        ])
        self.assertIn(
            [0x781B, 0x0006, 0x782B, 0x0008,
             0x783B, 0x000A, 0x784B, 0x000C,
             0x785B, 0x000E],
            [words[index:index + 10]
             for index in range(len(words) - 9)],
        )
        self.assertIn(
            [0x3F10, 0x8810, 0xF2E0,
             0x0803, 0x4C41, 0x5C01, 0x4D41,
             0x3F10, 0x8811, 0xF2E0, 0x75F4, 0x8000],
            [words[index:index + 12]
             for index in range(len(words) - 11)],
        )
        self.assertIn(
            [0x2B24, 0x5251, 0x5650],
            [words[index:index + 3]
             for index in range(len(words) - 2)],
        )
        self.assertIn(
            [0x5221, 0x76F2, 0x8000, 0xAC05],
            [words[index:index + 4]
             for index in range(len(words) - 3)],
        )
        self.assertIn(
            [0x5241, 0x76F4, 0x8000, 0xAC06],
            [words[index:index + 4]
             for index in range(len(words) - 3)],
        )
        self.assertEqual(words[-14:], [
            0x1F82, 0x1F8A, 0x38BF, 0x1F91, 0x1F90,
            0x385F, 0x384F, 0x383F, 0x382F, 0x381F, 0x380F,
            0x2F00, 0x3F00, rom.RETS,
        ])

        guest_install = rom.write_program_words(
            rom.REVERSE_FAR_MEMMOVE_OVERLAY_DESTINATION, words
        )
        installer = rom.install_runtime_overlay_words()
        self.assertIn(
            guest_install,
            [installer[index:index + len(guest_install)]
             for index in range(len(installer) - len(guest_install) + 1)],
        )

    def test_relocated_rom08_module_and_far_memcpy_are_exact_guest_code(self) -> None:
        image = rom.build_image()
        module = rom.program_source_words(
            rom.ROM08_MODULE_SOURCE, rom.ROM08_MODULE_SIZE
        )
        body_08 = rom.program_source_words(0x2543A6, 0x74)
        body_18 = rom.far_memcpy_words()

        self.assertEqual(
            words_at(image, rom.ROM08_MODULE_ADDRESS, len(module)),
            module,
        )
        self.assertEqual(
            words_at(image, rom.FAR_MEMCPY_08_ADDRESS, len(body_08)),
            body_08,
        )
        self.assertEqual(
            words_at(image, rom.FAR_MEMCPY_ADDRESS, len(body_18)),
            body_18,
        )
        # Both entries are exact original guest implementations of the same
        # five-word ABI, recovered from their respective +0x1D sources.
        self.assertEqual(body_08[:6],
                         [0x2E02, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4])
        self.assertNotEqual(body_08, body_18)

    def test_rom01_post_clock_installs_the_late_application_chain(self) -> None:
        strict = rom.build_image()
        probe = rom.build_image(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_rom_01_return=True,
        )

        self.assertEqual(
            words_at(strict, rom.ROM01_POST_CLOCK_ADDRESS, 1),
            [rom.RESERVED],
        )
        self.assertEqual(
            words_at(
                probe,
                rom.ROM01_POST_CLOCK_ADDRESS,
                len(rom.rom01_application_loader_words()),
            ),
            rom.rom01_application_loader_words(),
        )
        loader = rom.rom01_application_loader_words()
        state4e_wrapper = rom.embed_program_overlay_words(
            rom.APPLICATION_FOREGROUND_STATE4E_WRAPPER_OVERLAY_DESTINATION,
            rom.APPLICATION_FOREGROUND_STATE4E_WRAPPER_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_STATE4E_WRAPPER_OVERLAY_SIZE,
        )
        start_state_mask = rom.embed_program_overlay_words(
            rom.APPLICATION_START_STATE_MASK_OVERLAY_DESTINATION,
            rom.APPLICATION_START_STATE_MASK_OVERLAY_SOURCE,
            rom.APPLICATION_START_STATE_MASK_OVERLAY_SIZE,
        )
        operation_context = rom.copy_code_to_overlay_words(
            rom.APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_DESTINATION,
            rom.APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_SIZE,
        )
        operation_child = rom.copy_code_to_overlay_words(
            rom.APPLICATION_OPERATION_CONTEXT_CHILD_OVERLAY_DESTINATION,
            rom.APPLICATION_OPERATION_CONTEXT_CHILD_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_CHILD_OVERLAY_SIZE,
        )
        operation_predicate = rom.embed_program_overlay_words(
            rom.APPLICATION_OPERATION_CONTEXT_PREDICATE_OVERLAY_DESTINATION,
            rom.APPLICATION_OPERATION_CONTEXT_PREDICATE_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_PREDICATE_OVERLAY_SIZE,
        )
        layout_range = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FILE_BROWSER_LAYOUT_RANGE_OVERLAY_DESTINATION,
            rom.APPLICATION_FILE_BROWSER_LAYOUT_RANGE_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_BROWSER_LAYOUT_RANGE_OVERLAY_SIZE,
        )
        range_accumulate = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FILE_BROWSER_RANGE_ACCUMULATE_OVERLAY_DESTINATION,
            rom.APPLICATION_FILE_BROWSER_RANGE_ACCUMULATE_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_BROWSER_RANGE_ACCUMULATE_OVERLAY_SIZE,
        )
        character_classify = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FILE_BROWSER_CHARACTER_CLASSIFY_OVERLAY_DESTINATION,
            rom.APPLICATION_FILE_BROWSER_CHARACTER_CLASSIFY_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_BROWSER_CHARACTER_CLASSIFY_OVERLAY_SIZE,
        )
        lazy_call_patch = rom.npe_browser_lazy_call_patch_words()
        foreground_lazy_call_patch = (
            rom.foreground_event_state_lazy_call_patch_words()
        )
        expected_tail = [
            0xBD00 | (
                rom.APPLICATION_MAIN_FAR_BYTE_SEARCH_INSTALLER_ADDRESS >> 16
            ),
            rom.APPLICATION_MAIN_FAR_BYTE_SEARCH_INSTALLER_ADDRESS & 0xFFFF,
            *operation_context,
            *operation_child,
            *operation_predicate,
            *layout_range,
            *range_accumulate,
            *character_classify,
            *start_state_mask,
            *state4e_wrapper,
            *lazy_call_patch,
            *foreground_lazy_call_patch,
            0xBD00 | (
                rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_INSTALLER_ADDRESS
                >> 16
            ),
            rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_INSTALLER_ADDRESS &
            0xFFFF,
            rom.RETS,
        ]
        self.assertEqual(
            loader[-len(expected_tail):],
            expected_tail,
        )
        self.assertEqual(loader[-1], rom.RETS)
        entries = {
            item["address"]: item
            for item in rom.manifest(
                probe,
                initializer_overlay_probe=True,
                probe_rom_08_return=True,
                probe_rom_01_return=True,
            )["entries"]
        }
        self.assertEqual(
            entries["01:0200"]["name"],
            "reconstructed_rom01_application_loader",
        )

    def test_segment14_lcd_entries_use_complete_same_pc_prg_sources(self) -> None:
        image = rom.build_image()

        for destination, source, size in (
            (rom.LCD_BUS_INIT_ADDRESS,
             rom.LCD_BUS_INIT_SOURCE, rom.LCD_BUS_INIT_SIZE),
            (rom.LCD_BUS_WRITE_ADDRESS,
             rom.LCD_BUS_WRITE_SOURCE, rom.LCD_BUS_WRITE_SIZE),
            (rom.LCD_POWER_INIT_ADDRESS,
             rom.LCD_POWER_INIT_SOURCE, rom.LCD_POWER_INIT_SIZE),
            (rom.LCD_CONTROLLER_INIT_ADDRESS,
             rom.LCD_CONTROLLER_INIT_SOURCE, rom.LCD_CONTROLLER_INIT_SIZE),
            (rom.LCD_CLEAR_ADDRESS,
             rom.LCD_CLEAR_SOURCE, rom.LCD_CLEAR_SIZE),
            (rom.LCD_REGION_INIT_ADDRESS,
             rom.LCD_REGION_INIT_SOURCE, rom.LCD_REGION_INIT_SIZE),
            (rom.LCD_BITMAP_INIT_ADDRESS,
             rom.LCD_BITMAP_INIT_SOURCE, rom.LCD_BITMAP_INIT_SIZE),
            (rom.LCD_DELAY_ADDRESS,
             rom.LCD_DELAY_SOURCE, rom.LCD_DELAY_SIZE),
        ):
            source_words = rom.program_source_words(source, size)
            self.assertEqual(
                words_at(image, destination, len(source_words)),
                source_words,
            )

        self.assertEqual(
            words_at(image, rom.LCD_REGION_INIT_ADDRESS, 1), [0x2E02]
        )
        self.assertEqual(
            words_at(image,
                     rom.LCD_REGION_INIT_ADDRESS + rom.LCD_REGION_INIT_SIZE - 2,
                     1),
            [rom.RETS],
        )
        self.assertEqual(
            words_at(image, rom.LCD_BITMAP_INIT_ADDRESS, 1), [0x2E02]
        )
        self.assertEqual(
            words_at(image,
                     rom.LCD_BITMAP_INIT_ADDRESS + rom.LCD_BITMAP_INIT_SIZE - 2,
                     1),
            [rom.RETS],
        )

    def test_resident_1a_dispatch_uses_complete_same_pc_prg_source(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_DISPATCH_1A_SOURCE,
            rom.RESIDENT_DISPATCH_1A_SIZE,
        )

        self.assertEqual(
            words_at(image, rom.RESIDENT_DISPATCH_1A_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(source[:7],
                         [0x2E41, 0x58F0, 0x58F1, 0x58F2,
                          0x58F3, 0x58F4, 0x58F5])
        self.assertEqual(source[-8:],
                         [0x385F, 0x384F, 0x383F, 0x382F,
                          0x381F, 0x380F, 0x2F00, rom.RETS])
        self.assertEqual(
            words_at(image, rom.LCD_DELAY_ADDRESS, 8),
            [0xC700, 0x2E00, 0xBF00, 0x0014,
             0xC700, 0x2F00, 0x3F00, rom.RETS],
        )

    def test_resident_1a_wide_arithmetic_uses_complete_same_pc_source(
            self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_WIDE_ARITHMETIC_1A_SOURCE,
            rom.RESIDENT_WIDE_ARITHMETIC_1A_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_WIDE_ARITHMETIC_1A_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(source[:7],
                         [0x2E24, 0x58F4, 0x58F5, 0x58F6,
                          0x58F7, 0x68F0, 0x8000])
        self.assertEqual(source[-6:],
                         [0x387F, 0x386F, 0x385F,
                          0x384F, 0x2F00, rom.RETS])
        self.assertEqual(
            info["resident_wide_arithmetic_1a"]["bytes"],
            rom.RESIDENT_WIDE_ARITHMETIC_1A_SIZE,
        )

    def test_resident_0e_application_loop_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_APPLICATION_LOOP_0E_SOURCE,
            rom.RESIDENT_APPLICATION_LOOP_0E_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_APPLICATION_LOOP_0E_ADDRESS,
                     len(source)),
            source,
        )
        self.assertEqual(source[:7],
                         [0x2E8E, 0x58F0, 0x58F1, 0x58F2,
                          0x58F3, 0x58F6, 0x58F7])
        self.assertEqual(source[-8:],
                         [0x387F, 0x386F, 0x383F, 0x382F,
                          0x381F, 0x380F, 0x2F00, rom.RETS])
        self.assertEqual(info["resident_application_loop_0e"]["bytes"],
                         rom.RESIDENT_APPLICATION_LOOP_0E_SIZE)

    def test_resident_font_lookup_is_exact_guest_code(self) -> None:
        strict = rom.build_image()
        probe = rom.build_image(probe_font_lookup=True)
        info = rom.manifest(probe, probe_font_lookup=True)
        source = rom.program_source_words(
            rom.RESIDENT_FONT_LOOKUP_SOURCE,
            rom.RESIDENT_FONT_LOOKUP_SIZE,
        )

        self.assertEqual(
            words_at(strict, rom.RESIDENT_FONT_LOOKUP_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(
            words_at(probe, rom.RESIDENT_FONT_LOOKUP_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(source[:9], [
            0x2E07, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7,
        ])
        self.assertEqual(source[-10:], [
            0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(info["probe_placeholders"], [])
        self.assertEqual(info["resident_font_lookup"]["bytes"],
                         rom.RESIDENT_FONT_LOOKUP_SIZE)

    def test_font_lookup_table_builder_is_exact_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_FONT_TABLE_OVERLAY_SOURCE,
            rom.APPLICATION_FONT_TABLE_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FONT_TABLE_OVERLAY_DESTINATION,
            rom.APPLICATION_FONT_TABLE_OVERLAY_SOURCE,
            rom.APPLICATION_FONT_TABLE_OVERLAY_SIZE,
        )
        installer = rom.install_runtime_overlay_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:5], [
            0x2E26, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
        ])
        self.assertIn(
            [0xBD30, 0x6490],
            [source[index:index + 2] for index in range(len(source) - 1)],
        )
        self.assertEqual(source[-6:], [
            0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(modules["29:C3C0"]["bytes"], 0x029A)

    def test_application_context_launch_selector_is_exact_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_CONTEXT_LAUNCH_OVERLAY_SOURCE,
            rom.APPLICATION_CONTEXT_LAUNCH_OVERLAY_SIZE,
        )
        flat = rom.program_source_words(
            rom.APPLICATION_CONTEXT_LAUNCH_OVERLAY_DESTINATION,
            rom.APPLICATION_CONTEXT_LAUNCH_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_CONTEXT_LAUNCH_OVERLAY_DESTINATION,
            rom.APPLICATION_CONTEXT_LAUNCH_OVERLAY_SOURCE,
            rom.APPLICATION_CONTEXT_LAUNCH_OVERLAY_SIZE,
        )
        installer = rom.install_runtime_overlay_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["nested_system_overlays"]
        }

        self.assertNotEqual(flat, source)
        self.assertEqual(source[:8], [
            0x2E22, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7,
        ])
        call_windows = [
            source[index:index + 2] for index in range(len(source) - 1)
        ]
        self.assertEqual(call_windows.count([0xBD18, 0x21F4]), 1)
        self.assertEqual(call_windows.count([0xBD30, 0xC8C0]), 2)
        self.assertEqual(call_windows.count([0xBD33, 0x048A]), 2)
        self.assertEqual(call_windows.count([0xBD31, 0x3A72]), 2)
        self.assertEqual(source[-9:], [
            0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["23:A38C"]["source"], "40:A38C"
        )
        self.assertEqual(
            modules["23:A38C"]["bytes"],
            rom.APPLICATION_CONTEXT_LAUNCH_OVERLAY_SIZE,
        )

    def test_resident_resource_initializer_calls_context_selector(self) -> None:
        source = rom.program_source_words(
            rom.RESIDENT_RESOURCE_INIT_1BCE3C_SOURCE,
            rom.RESIDENT_RESOURCE_INIT_1BCE3C_SIZE,
        )
        image = rom.build_image()
        call_word = (0xD48E - 0xCE3C) // 2

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_RESOURCE_INIT_1BCE3C_ADDRESS,
                len(source),
            ),
            source,
        )
        # Exact source 38:CE3C pushes four far pointers, calls linked
        # selector 23:A38C at 38:D48E, and consumes all eight argument words.
        # This closes the parent edge of the native
        # 1B:CE3C -> 23:A38C -> 18:21F4 launch chain; merely restoring the
        # child without proving this call site could hide an unrelated copy.
        self.assertEqual(source[call_word - 24:call_word + 4], [
            0x780B, 0xFFFA, 0x781B, 0xFFFC, 0x58F1, 0x58F0,
            0x081B, 0x70F1, 0xFFF6, 0x4800, 0x58F1, 0x58F0,
            0x081B, 0x70F1, 0xFFF4, 0x4800, 0x58F1, 0x58F0,
            0x081B, 0x70F1, 0xFFF5, 0x4800, 0x58F1, 0x58F0,
            0xBD23, 0xA38C, 0x70FF, 0x0010,
        ])
        info = rom.manifest(image)["resident_resource_init_1b_ce3c"]
        self.assertEqual(info, {
            "destination": "1B:CE3C",
            "source": "38:CE3C",
            "bytes": rom.RESIDENT_RESOURCE_INIT_1BCE3C_SIZE,
            "status": "exact same-PC resident resource initialization body",
        })

    def test_application_launch_sequence_and_closure_are_exact_overlays(
            self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_LAUNCH_SEQUENCE_OVERLAY_SOURCE,
            rom.APPLICATION_LAUNCH_SEQUENCE_OVERLAY_SIZE,
        )
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:3], [0x2E00, 0x58F0, 0x58F1])
        self.assertIn(
            [0xBD18, 0x21F4],
            [source[index:index + 2] for index in range(len(source) - 1)],
        )
        self.assertEqual(
            source[-4:], [0x381F, 0x380F, 0x2F00, rom.RETS]
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_LAUNCH_RESOURCE_RELEASE_OVERLAY_SOURCE,
                rom.APPLICATION_LAUNCH_RESOURCE_RELEASE_OVERLAY_SIZE,
            ),
            [0xAD24, 0xEAEC],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_LAUNCH_POST_STATE_OVERLAY_SOURCE,
                rom.APPLICATION_LAUNCH_POST_STATE_OVERLAY_SIZE,
            ),
            [0x2E00, 0x2F00, rom.RETS],
        )
        start_context = rom.program_source_words(
            rom.APPLICATION_START_CONTEXT_INIT_OVERLAY_SOURCE,
            rom.APPLICATION_START_CONTEXT_INIT_OVERLAY_SIZE,
        )
        self.assertEqual(start_context[:4], [0x2E02, 0x58F0, 0x58F1, 0x58F3])
        self.assertEqual(
            start_context[-4:], [0x381F, 0x380F, 0x2F00, rom.RETS]
        )
        start_context_descriptor = rom.embed_program_overlay_words(
            rom.APPLICATION_START_CONTEXT_INIT_OVERLAY_DESTINATION,
            rom.APPLICATION_START_CONTEXT_INIT_OVERLAY_SOURCE,
            rom.APPLICATION_START_CONTEXT_INIT_OVERLAY_SIZE,
        )
        late_installer = rom.rom01_application_loader_words()
        self.assertIn(
            start_context_descriptor,
            [late_installer[index:index + len(start_context_descriptor)]
             for index in range(
                 len(late_installer) - len(start_context_descriptor) + 1
             )],
        )
        self.assertEqual(
            modules["30:E662"]["bytes"],
            rom.APPLICATION_START_CONTEXT_INIT_OVERLAY_SIZE,
        )
        start_callback = rom.program_source_words(
            rom.APPLICATION_START_CALLBACK_OVERLAY_SOURCE,
            rom.APPLICATION_START_CALLBACK_OVERLAY_SIZE,
        )
        self.assertEqual(start_callback[:3], [0x2E02, 0x58F0, 0x58F1])
        self.assertIn(
            [0xBD2B, 0x593E],
            [start_callback[index:index + 2]
             for index in range(len(start_callback) - 1)],
        )
        self.assertEqual(
            start_callback[-4:], [0x381F, 0x380F, 0x2F00, rom.RETS]
        )
        start_callback_descriptor = rom.embed_program_overlay_words(
            rom.APPLICATION_START_CALLBACK_OVERLAY_DESTINATION,
            rom.APPLICATION_START_CALLBACK_OVERLAY_SOURCE,
            rom.APPLICATION_START_CALLBACK_OVERLAY_SIZE,
        )
        self.assertIn(
            start_callback_descriptor,
            [late_installer[index:index + len(start_callback_descriptor)]
             for index in range(
                 len(late_installer) - len(start_callback_descriptor) + 1
             )],
        )
        self.assertEqual(
            modules["32:F15C"]["bytes"],
            rom.APPLICATION_START_CALLBACK_OVERLAY_SIZE,
        )
        start_record_handler = rom.program_source_words(
            rom.APPLICATION_START_RECORD_HANDLER_OVERLAY_SOURCE,
            rom.APPLICATION_START_RECORD_HANDLER_OVERLAY_SIZE,
        )
        self.assertEqual(
            start_record_handler[:5],
            [0x2E07, 0x58F0, 0x58F1, 0x58F2, 0x58F3],
        )
        self.assertEqual(
            start_record_handler[-6:],
            [0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        start_record_descriptor = rom.embed_program_overlay_words(
            rom.APPLICATION_START_RECORD_HANDLER_OVERLAY_DESTINATION,
            rom.APPLICATION_START_RECORD_HANDLER_OVERLAY_SOURCE,
            rom.APPLICATION_START_RECORD_HANDLER_OVERLAY_SIZE,
        )
        wide_installer = rom.wide_accumulate_installer_words()
        self.assertIn(
            start_record_descriptor,
            [wide_installer[index:index + len(start_record_descriptor)]
             for index in range(
                 len(wide_installer) - len(start_record_descriptor) + 1
             )],
        )
        self.assertEqual(
            modules["2B:593E"]["bytes"],
            rom.APPLICATION_START_RECORD_HANDLER_OVERLAY_SIZE,
        )
        start_state_mask = rom.program_source_words(
            rom.APPLICATION_START_STATE_MASK_OVERLAY_SOURCE,
            rom.APPLICATION_START_STATE_MASK_OVERLAY_SIZE,
        )
        self.assertEqual(
            start_state_mask[:4],
            [0x2E04, 0x58F1, 0x58F2, 0x58F3],
        )
        self.assertIn(
            [0x68F3, 0x26F4, 0x68F2, 0x0051],
            [start_state_mask[index:index + 4]
             for index in range(len(start_state_mask) - 3)],
        )
        self.assertEqual(
            start_state_mask[-5:],
            [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        start_state_mask_descriptor = rom.embed_program_overlay_words(
            rom.APPLICATION_START_STATE_MASK_OVERLAY_DESTINATION,
            rom.APPLICATION_START_STATE_MASK_OVERLAY_SOURCE,
            rom.APPLICATION_START_STATE_MASK_OVERLAY_SIZE,
        )
        self.assertIn(
            start_state_mask_descriptor,
            [late_installer[
                index:index + len(start_state_mask_descriptor)
            ] for index in range(
                len(late_installer) - len(start_state_mask_descriptor) + 1
            )],
        )
        state_mask_index = next(
            index for index in range(
                len(late_installer) - len(start_state_mask_descriptor) + 1
            ) if late_installer[
                index:index + len(start_state_mask_descriptor)
            ] == start_state_mask_descriptor
        )
        lcd_call_index = max(
            index for index in range(len(late_installer) - 1)
            if late_installer[index:index + 2] == [
                0xBD14, rom.LCD_POWER_INIT_ADDRESS & 0xFFFF,
            ]
        )
        self.assertGreater(state_mask_index, lcd_call_index)
        self.assertEqual(
            modules["31:6518"]["bytes"],
            rom.APPLICATION_START_STATE_MASK_OVERLAY_SIZE,
        )
        start_release = rom.program_source_words(
            rom.APPLICATION_START_RELEASE_OVERLAY_SOURCE,
            rom.APPLICATION_START_RELEASE_OVERLAY_SIZE,
        )
        self.assertEqual(
            start_release[:8],
            [0x2E00, 0x58F1, 0x58F2, 0x58F3,
             0x58F4, 0x58F5, 0x58F6, 0x58F7],
        )
        self.assertIn(
            [0x6810, 0x00A2, 0xB2F0, 0x2250],
            [start_release[index:index + 4]
             for index in range(len(start_release) - 3)],
        )
        self.assertEqual(
            start_release[-9:],
            [0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
             0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        start_release_descriptor = rom.embed_program_overlay_words(
            rom.APPLICATION_START_RELEASE_OVERLAY_DESTINATION,
            rom.APPLICATION_START_RELEASE_OVERLAY_SOURCE,
            rom.APPLICATION_START_RELEASE_OVERLAY_SIZE,
        )
        self.assertIn(
            start_release_descriptor,
            [wide_installer[index:index + len(start_release_descriptor)]
             for index in range(
                 len(wide_installer) - len(start_release_descriptor) + 1
             )],
        )
        self.assertEqual(
            modules["2C:79B8"]["bytes"],
            rom.APPLICATION_START_RELEASE_OVERLAY_SIZE,
        )
        start_resource_bind = rom.program_source_words(
            rom.APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SIZE,
        )
        self.assertEqual(
            start_resource_bind[:7],
            [0x2E04, 0x58F0, 0x58F1, 0x58F2,
             0x58F3, 0x58F4, 0x58F5],
        )
        self.assertEqual(
            start_resource_bind[-8:],
            [0x385F, 0x384F, 0x383F, 0x382F,
             0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        start_resource_bind_descriptor = rom.embed_program_overlay_words(
            rom.APPLICATION_MENU_RESOURCE_BIND_OVERLAY_DESTINATION,
            rom.APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SIZE,
        )
        self.assertIn(
            start_resource_bind_descriptor,
            [wide_installer[
                index:index + len(start_resource_bind_descriptor)
            ] for index in range(
                len(wide_installer) - len(start_resource_bind_descriptor) + 1
            )],
        )
        start_resource_bind_wrapper = rom.program_source_words(
            rom.APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SIZE,
        )
        self.assertEqual(start_resource_bind_wrapper[:2], [0x2E00, 0x780B])
        self.assertEqual(start_resource_bind_wrapper[-2:], [0x2F00, rom.RETS])
        start_resource_bind_wrapper_descriptor = (
            rom.embed_program_overlay_words(
                rom.APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_DESTINATION,
                rom.APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SOURCE,
                rom.APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SIZE,
            )
        )
        self.assertIn(
            start_resource_bind_wrapper_descriptor,
            [wide_installer[
                index:index + len(start_resource_bind_wrapper_descriptor)
            ] for index in range(
                len(wide_installer) -
                len(start_resource_bind_wrapper_descriptor) + 1
            )],
        )
        start_result_range = rom.program_source_words(
            rom.APPLICATION_MENU_RESULT_RANGE_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RESULT_RANGE_OVERLAY_SIZE,
        )
        self.assertEqual(
            start_result_range[:7],
            [0x2E04, 0x58F0, 0x58F1, 0x58F2,
             0x58F3, 0x58F4, 0x58F5],
        )
        self.assertEqual(
            start_result_range[-8:],
            [0x385F, 0x384F, 0x383F, 0x382F,
             0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        start_result_range_descriptor = rom.embed_program_overlay_words(
            rom.APPLICATION_MENU_RESULT_RANGE_OVERLAY_DESTINATION,
            rom.APPLICATION_MENU_RESULT_RANGE_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RESULT_RANGE_OVERLAY_SIZE,
        )
        self.assertIn(
            start_result_range_descriptor,
            [wide_installer[
                index:index + len(start_result_range_descriptor)
            ] for index in range(
                len(wide_installer) - len(start_result_range_descriptor) + 1
            )],
        )

        property_set = rom.program_source_words(
            rom.APPLICATION_UI_PROPERTY_SET_OVERLAY_SOURCE,
            rom.APPLICATION_UI_PROPERTY_SET_OVERLAY_SIZE,
        )
        self.assertEqual(
            property_set,
            [0x2E00, 0x58F0, 0x780B, 0x0006, 0x58F0,
             0xBD31, 0x5014, 0x50F2, 0x380F, 0x2F00, rom.RETS],
        )
        property_set_descriptor = rom.embed_program_overlay_words(
            rom.APPLICATION_UI_PROPERTY_SET_OVERLAY_DESTINATION,
            rom.APPLICATION_UI_PROPERTY_SET_OVERLAY_SOURCE,
            rom.APPLICATION_UI_PROPERTY_SET_OVERLAY_SIZE,
        )
        self.assertIn(
            property_set_descriptor,
            [late_installer[index:index + len(property_set_descriptor)]
             for index in range(
                 len(late_installer) - len(property_set_descriptor) + 1
             )],
        )
        self.assertEqual(
            modules["33:4D14"]["bytes"],
            rom.APPLICATION_UI_PROPERTY_SET_OVERLAY_SIZE,
        )

        for destination, overlay_source, size in (
                rom.APPLICATION_LAUNCH_COPY_OVERLAYS):
            descriptor = rom.copy_code_to_overlay_words(
                destination, overlay_source, size
            )
            self.assertIn(
                descriptor,
                [installer[index:index + len(descriptor)]
                 for index in range(len(installer) - len(descriptor) + 1)],
            )
            key = f"{destination >> 16:02X}:{destination & 0xFFFF:04X}"
            self.assertEqual(modules[key]["bytes"], size)

        for destination, overlay_source, size in (
                rom.APPLICATION_LAUNCH_EMBEDDED_OVERLAYS):
            embedded = rom.embed_program_overlay_words(
                destination, overlay_source, size
            )
            self.assertIn(
                embedded,
                [installer[index:index + len(embedded)]
                 for index in range(len(installer) - len(embedded) + 1)],
            )
            key = f"{destination >> 16:02X}:{destination & 0xFFFF:04X}"
            self.assertEqual(modules[key]["bytes"], size)

    def test_native_result_scanner_closure_and_resident_children_are_exact(
            self) -> None:
        image = rom.build_image()
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(image)["application_main_chain"]
        }
        scanner = rom.program_source_words(
            rom.APPLICATION_MAIN_RESULT_SCAN_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_RESULT_SCAN_OVERLAY_SIZE,
        )

        self.assertEqual(scanner[:2], [0x2E31, 0x58F1])
        self.assertIn(
            [0xBD2E, 0xD34A],
            [scanner[index:index + 2] for index in range(len(scanner) - 1)],
        )
        self.assertEqual(scanner[-3:], [0x381F, 0x2F00, rom.RETS])

        path_resolve = rom.program_source_words(
            rom.APPLICATION_FILE_PATH_RESOLVE_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_PATH_RESOLVE_OVERLAY_SIZE,
        )
        self.assertEqual(path_resolve[:6], [
            0x2E01, 0x58F1, 0x58F2, 0x58F3, 0xBD31, 0xB83C,
        ])
        self.assertIn([0xBD2F, 0x2FE0], [
            path_resolve[index:index + 2]
            for index in range(len(path_resolve) - 1)
        ])
        self.assertIn([0xBD33, 0x0B24], [
            path_resolve[index:index + 2]
            for index in range(len(path_resolve) - 1)
        ])
        self.assertEqual(path_resolve[-5:], [
            0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS,
        ])
        root_lookup = rom.program_source_words(
            rom.APPLICATION_FILE_ROOT_LOOKUP_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_ROOT_LOOKUP_OVERLAY_SIZE,
        )
        self.assertEqual(root_lookup[:2], [0x2E02, 0x58F3])
        self.assertEqual(root_lookup[-3:], [0x383F, 0x2F00, rom.RETS])
        self.assertNotIn(0xBD31, root_lookup)

        object_release = rom.program_source_words(
            rom.APPLICATION_FILE_OBJECT_RELEASE_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_OBJECT_RELEASE_OVERLAY_SIZE,
        )
        self.assertEqual(object_release[:4], [
            0x2E00, 0x58F0, 0x58F1, 0x58F3,
        ])
        self.assertEqual(object_release[-5:], [
            0x383F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        object_release_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FILE_OBJECT_RELEASE_OVERLAY_DESTINATION,
            rom.APPLICATION_FILE_OBJECT_RELEASE_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_OBJECT_RELEASE_OVERLAY_SIZE,
        )
        self.assertIn(
            object_release_copy,
            [installer[index:index + len(object_release_copy)]
             for index in range(
                 len(installer) - len(object_release_copy) + 1)],
        )

        for destination, source, size in rom.APPLICATION_RESULT_SCAN_COPY_OVERLAYS:
            descriptor = rom.copy_code_to_overlay_words(destination, source, size)
            self.assertIn(
                descriptor,
                [installer[index:index + len(descriptor)]
                 for index in range(len(installer) - len(descriptor) + 1)],
            )
            key = f"{destination >> 16:02X}:{destination & 0xFFFF:04X}"
            self.assertEqual(modules[key]["bytes"], size)

        for destination, source, size in (
                rom.APPLICATION_RESULT_SCAN_EMBEDDED_OVERLAYS):
            embedded = rom.embed_program_overlay_words(destination, source, size)
            self.assertIn(
                embedded,
                [installer[index:index + len(embedded)]
                 for index in range(len(installer) - len(embedded) + 1)],
            )
            key = f"{destination >> 16:02X}:{destination & 0xFFFF:04X}"
            self.assertEqual(modules[key]["bytes"], size)

        for destination, source, size in (
            (rom.RESIDENT_RESULT_OBJECT_ALLOC_ADDRESS,
             rom.RESIDENT_RESULT_OBJECT_ALLOC_SOURCE,
             rom.RESIDENT_RESULT_OBJECT_ALLOC_SIZE),
            (rom.RESIDENT_RESULT_TYPE_QUERY_ADDRESS,
             rom.RESIDENT_RESULT_TYPE_QUERY_SOURCE,
             rom.RESIDENT_RESULT_TYPE_QUERY_SIZE),
            (rom.RESIDENT_RESULT_RECORD_BUILD_ADDRESS,
             rom.RESIDENT_RESULT_RECORD_BUILD_SOURCE,
             rom.RESIDENT_RESULT_RECORD_BUILD_SIZE),
            (rom.RESIDENT_RESULT_RECORD_COMPARE_ADDRESS,
             rom.RESIDENT_RESULT_RECORD_COMPARE_SOURCE,
             rom.RESIDENT_RESULT_RECORD_COMPARE_SIZE),
        ):
            source_words = rom.program_source_words(source, size)
            installed_words = rom.make_routines()[destination][1]
            self.assertEqual(
                words_at(image, destination, len(installed_words)),
                installed_words,
            )
            if destination != rom.RESIDENT_RESULT_RECORD_BUILD_ADDRESS:
                self.assertEqual(installed_words, source_words)
            self.assertEqual(source_words[0] & 0xFF00, 0x2E00)
            self.assertEqual(source_words[-2:], [0x2F00, rom.RETS])

    def test_one_shot_application_task_is_exact_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_INIT_TASK_OVERLAY_SOURCE,
            rom.APPLICATION_INIT_TASK_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_INIT_TASK_OVERLAY_DESTINATION,
            rom.APPLICATION_INIT_TASK_OVERLAY_SOURCE,
            rom.APPLICATION_INIT_TASK_OVERLAY_SIZE,
        )
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:3], [0x2E16, 0x58F0, 0x58F1])
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(modules["2B:939A"]["bytes"], 0x0222)

    def test_validation_checksum_is_exact_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_VALIDATION_CHECKSUM_OVERLAY_SOURCE,
            rom.APPLICATION_VALIDATION_CHECKSUM_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_VALIDATION_CHECKSUM_OVERLAY_DESTINATION,
            rom.APPLICATION_VALIDATION_CHECKSUM_OVERLAY_SOURCE,
            rom.APPLICATION_VALIDATION_CHECKSUM_OVERLAY_SIZE,
        )
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:4], [0x2E00, 0x58F1, 0x58F2, 0x58F3])
        self.assertIn([0xBD31, 0xF162],
                      [source[i:i + 2] for i in range(len(source) - 1)])
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(modules["32:5ACC"]["bytes"], 0x006E)

    def test_resident_event_helper_is_exact_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_RESIDENT_EVENT_OVERLAY_SOURCE,
            rom.APPLICATION_RESIDENT_EVENT_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_RESIDENT_EVENT_OVERLAY_DESTINATION,
            rom.APPLICATION_RESIDENT_EVENT_OVERLAY_SOURCE,
            rom.APPLICATION_RESIDENT_EVENT_OVERLAY_SIZE,
        )
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:3], [0x2E00, 0x58F1, 0x58F3])
        self.assertEqual(source[-4:], [0x383F, 0x381F, 0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(modules["29:3DD2"]["bytes"], 0x02C4)

    def test_ascii_digit_predicate_is_exact_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_ASCII_DIGIT_OVERLAY_SOURCE,
            rom.APPLICATION_ASCII_DIGIT_OVERLAY_SIZE,
        )
        descriptor = rom.embed_program_overlay_words(
            rom.APPLICATION_ASCII_DIGIT_OVERLAY_DESTINATION,
            rom.APPLICATION_ASCII_DIGIT_OVERLAY_SOURCE,
            rom.APPLICATION_ASCII_DIGIT_OVERLAY_SIZE,
        )
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:4], [0x2E00, 0x780B, 0x0006, 0x76F0])
        self.assertIn(0x0030, source)
        self.assertIn(0x0039, source)
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(modules["33:4342"]["bytes"], 0x001C)

    def test_event_postprocess_is_exact_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_EVENT_POSTPROCESS_OVERLAY_SOURCE,
            rom.APPLICATION_EVENT_POSTPROCESS_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_EVENT_POSTPROCESS_OVERLAY_DESTINATION,
            rom.APPLICATION_EVENT_POSTPROCESS_OVERLAY_SOURCE,
            rom.APPLICATION_EVENT_POSTPROCESS_OVERLAY_SIZE,
        )
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:3], [0x2E02, 0x58F0, 0x58F1])
        self.assertIn([0xBD30, 0x8B26],
                      [source[i:i + 2] for i in range(len(source) - 1)])
        self.assertIn([0xBD31, 0x4BAC],
                      [source[i:i + 2] for i in range(len(source) - 1)])
        self.assertEqual(source[-4:], [0x381F, 0x380F, 0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(modules["32:C476"]["bytes"], 0x0050)

    def test_validation_crc16_is_exact_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_VALIDATION_CRC16_OVERLAY_SOURCE,
            rom.APPLICATION_VALIDATION_CRC16_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_VALIDATION_CRC16_OVERLAY_DESTINATION,
            rom.APPLICATION_VALIDATION_CRC16_OVERLAY_SOURCE,
            rom.APPLICATION_VALIDATION_CRC16_OVERLAY_SIZE,
        )
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:3], [0x2E02, 0x58F1, 0x781B])
        self.assertIn(0x1021, source)
        self.assertEqual(source[-3:], [0x381F, 0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(modules["31:F162"]["bytes"], 0x0090)

    def test_main_rom_compositor_is_static_exact_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.APPLICATION_MAIN_ROM_COMPOSITOR_SOURCE,
            rom.APPLICATION_MAIN_ROM_COMPOSITOR_SIZE,
        )
        modules = {
            item["destination"]: item
            for item in rom.manifest(image)["application_main_chain"]
        }

        self.assertEqual(source[:5],
                         [0x2E12, 0x58F0, 0x58F1, 0x58F2, 0x58F3])
        self.assertIn([0xBD1C, 0x188E],
                      [source[i:i + 2] for i in range(len(source) - 1)])
        self.assertEqual(source[-10:], [
            0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(
            words_at(image, rom.APPLICATION_MAIN_ROM_COMPOSITOR_DESTINATION,
                     len(source)),
            source,
        )
        self.assertEqual(modules["13:9444"]["bytes"], 0x11BE)

    def test_main_far_byte_search_is_exact_five_word_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_MAIN_FAR_BYTE_SEARCH_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_FAR_BYTE_SEARCH_OVERLAY_SIZE,
        )
        descriptor = rom.embed_program_overlay_words(
            rom.APPLICATION_MAIN_FAR_BYTE_SEARCH_OVERLAY_DESTINATION,
            rom.APPLICATION_MAIN_FAR_BYTE_SEARCH_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_FAR_BYTE_SEARCH_OVERLAY_SIZE,
        )
        installer = rom.application_main_far_byte_search_installer_words()
        application_loader = rom.rom01_application_loader_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(b"")["application_main_chain"]
        }

        # LINK #0 followed by the complete saved-register set.  The routine
        # reads all five words at FP+6..FP+0E and ends before the next LINK.
        self.assertEqual(source[:7], [
            0x2E00, 0x1F10, 0x1F11, 0x1F09, 0x1F0B, 0x1F0C, 0x58F2,
        ])
        for displacement in (0x0006, 0x0008, 0x000A, 0x000C, 0x000E):
            self.assertIn(displacement, source)
        self.assertEqual(source[-14:], [
            0x388F, 0x387F, 0x386F, 0x385F, 0x384F, 0x383F, 0x382F,
            0x1F8C, 0x1F8B, 0x1F89, 0x1F91, 0x1F90, 0x2F00, rom.RETS,
        ])
        self.assertEqual(installer[-1], rom.RETS)
        self.assertEqual(
            rom.APPLICATION_MAIN_FAR_BYTE_SEARCH_INSTALLER_ADDRESS +
            (len(installer) - 1) * 2,
            0x1AF4CC,
        )
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        call = [
            0xBD00 |
            (rom.APPLICATION_MAIN_FAR_BYTE_SEARCH_INSTALLER_ADDRESS >> 16),
            rom.APPLICATION_MAIN_FAR_BYTE_SEARCH_INSTALLER_ADDRESS & 0xFFFF,
        ]
        self.assertIn(
            call,
            [application_loader[index:index + len(call)]
             for index in range(len(application_loader) - len(call) + 1)],
        )
        self.assertEqual(modules["30:9794"]["bytes"], 0x00F2)

    def test_main_rom_resource_helpers_are_static_exact_code(self) -> None:
        image = rom.build_image()
        modules = {
            item["destination"]: item
            for item in rom.manifest(image)["application_main_chain"]
        }
        helpers = (
            (rom.APPLICATION_MAIN_ROM_RESOURCE_STATE_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_STATE_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_STATE_SIZE,
             "07:7136", 0x00F0),
            (rom.APPLICATION_MAIN_ROM_RESOURCE_PROBE_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_PROBE_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_PROBE_SIZE,
             "07:A496", 0x003C),
            (rom.APPLICATION_MAIN_ROM_RESOURCE_TEST_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_TEST_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_TEST_SIZE,
             "07:A5A6", 0x002A),
        )

        for destination, source_address, size, name, expected_size in helpers:
            source = rom.program_source_words(source_address, size)
            self.assertEqual(source[0], 0x2E00)
            self.assertEqual(source[-2:], [0x2F00, rom.RETS])
            self.assertEqual(words_at(image, destination, len(source)), source)
            self.assertEqual(modules[name]["bytes"], expected_size)

        state = rom.program_source_words(
            rom.APPLICATION_MAIN_ROM_RESOURCE_STATE_SOURCE,
            rom.APPLICATION_MAIN_ROM_RESOURCE_STATE_SIZE,
        )
        self.assertIn([0xBD07, 0xA496],
                      [state[i:i + 2] for i in range(len(state) - 1)])
        self.assertIn([0xBD07, 0xA5A6],
                      [state[i:i + 2] for i in range(len(state) - 1)])

    def test_main_rom_resource_scan_and_check_are_static(self) -> None:
        image = rom.build_image()
        modules = {
            item["destination"]: item
            for item in rom.manifest(image)["application_main_chain"]
        }
        helpers = (
            (rom.APPLICATION_MAIN_ROM_RESOURCE_SCAN_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_SCAN_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_SCAN_SIZE,
             "05:89EC", 0x078A, 0x2E07),
            (rom.APPLICATION_MAIN_ROM_RESOURCE_CHECK_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_CHECK_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_CHECK_SIZE,
             "06:1138", 0x044C, 0x2E04),
        )

        for destination, source_address, size, name, expected_size, link in helpers:
            source = rom.program_source_words(source_address, size)
            self.assertEqual(source[0], link)
            self.assertEqual(source[-2:], [0x2F00, rom.RETS])
            self.assertEqual(words_at(image, destination, len(source)), source)
            self.assertEqual(modules[name]["bytes"], expected_size)

        scan = rom.program_source_words(
            rom.APPLICATION_MAIN_ROM_RESOURCE_SCAN_SOURCE,
            rom.APPLICATION_MAIN_ROM_RESOURCE_SCAN_SIZE,
        )
        self.assertIn([0xBD07, 0x3734],
                      [scan[i:i + 2] for i in range(len(scan) - 1)])

    def test_05_2286_callee_is_restored_after_loader_passes_it(self) -> None:
        # 21:C076 is a real returning three-far-pointer call, not a loader
        # entry or a reason to add a CPU instruction/HLE service.
        self.assertEqual(
            rom.program_source_words(0x21C076, 8),
            [0xBD05, 0x2286, 0x50FC, 0x5600],
        )

        source = rom.program_source_words(
            rom.APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SIZE,
        )
        self.assertEqual(source[:4], [0x2E1D, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(
            source[-8:],
            [0xAC00, 0x2C86, 0x4800, 0x383F,
             0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SOURCE
                + rom.APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SIZE,
                8,
            )[:2],
            [0x2EA0, 0x58F2],
        )

        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MAIN_RECORD_LOAD_OVERLAY_DESTINATION,
            rom.APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SIZE,
        )
        runtime = rom.install_runtime_overlay_words()
        self.assertEqual(runtime[-len(descriptor):], descriptor)

        loader = rom.post_initializer_overlay_words(
            probe_system_main=True,
            factory_linked_startup=True,
        )
        loader_start = rom.POST_INITIALIZER_LOADER_ADDRESS
        loader_end = loader_start + len(loader) * 2
        overlay_start = rom.APPLICATION_MAIN_RECORD_LOAD_OVERLAY_DESTINATION
        overlay_end = (
            overlay_start + rom.APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SIZE
        )
        self.assertEqual(loader_start >> 16, (loader_end - 1) >> 16)
        self.assertTrue(
            loader_end <= overlay_start or loader_start >= overlay_end,
            "post-initializer loader must not execute through a future "
            "executable-RAM overlay window",
        )
        matches = [
            index
            for index in range(len(loader) - len(descriptor) + 1)
            if loader[index:index + len(descriptor)] == descriptor
        ]
        self.assertEqual(len(matches), 1)
        install_pc = rom.POST_INITIALIZER_LOADER_ADDRESS + matches[0] * 2
        self.assertGreaterEqual(
            install_pc,
            rom.APPLICATION_MAIN_RECORD_LOAD_OVERLAY_DESTINATION
            + rom.APPLICATION_MAIN_RECORD_LOAD_OVERLAY_SIZE,
        )

        resource_installer_start = (
            rom.APPLICATION_MENU_RESOURCE_DECODER_INSTALLER_ADDRESS
        )
        resource_installer_end = resource_installer_start + len(
            rom.application_menu_resource_decoder_installer_words()
        ) * 2
        text_installer_start = (
            rom.APPLICATION_MENU_TEXT_STREAM_INSTALLER_ADDRESS
        )
        text_installer_end = text_installer_start + len(
            rom.application_menu_text_stream_installer_words()
        ) * 2
        self.assertLessEqual(loader_end, text_installer_start)
        self.assertLessEqual(resource_installer_end,
                             rom.RESIDENT_WIDE_ARITHMETIC_1A_ADDRESS)
        self.assertEqual(resource_installer_start >> 16, 0x1A)
        self.assertEqual(loader_start >> 16, text_installer_start >> 16)
        self.assertEqual(loader_start >> 16, (text_installer_end - 1) >> 16)

        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }
        self.assertEqual(modules["05:2286"], {
            "destination": "05:2286",
            "source": "22:2286",
            "bytes": 0x0A0A,
            "status": "exact same-PC guest function",
        })

    def test_main_rom_resource_conversion_leaves_are_static(self) -> None:
        image = rom.build_image()
        modules = {
            item["destination"]: item
            for item in rom.manifest(image)["application_main_chain"]
        }
        helpers = (
            (rom.APPLICATION_MAIN_ROM_RESOURCE_XOR_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_XOR_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_XOR_SIZE,
             "07:367E", 0x0056, [0x58F2], [0x382F, rom.RETS]),
            (rom.APPLICATION_MAIN_ROM_RESOURCE_HEX_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_HEX_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_HEX_SIZE,
             "07:3734", 0x006C, [0x2E00], [0x2F00, rom.RETS]),
            (rom.APPLICATION_MAIN_ROM_RESOURCE_FORMAT_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_FORMAT_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_FORMAT_SIZE,
             "07:37A0", 0x0070, [0x2E00], [0x2F00, rom.RETS]),
        )

        for destination, source_address, size, name, expected_size, head, tail in helpers:
            source = rom.program_source_words(source_address, size)
            self.assertEqual(source[:len(head)], head)
            self.assertEqual(source[-len(tail):], tail)
            self.assertEqual(words_at(image, destination, len(source)), source)
            self.assertEqual(modules[name]["bytes"], expected_size)

    def test_main_rom_layout_builder_is_static_exact_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.APPLICATION_MAIN_ROM_LAYOUT_BUILD_SOURCE,
            rom.APPLICATION_MAIN_ROM_LAYOUT_BUILD_SIZE,
        )
        embedded = rom.retarget_program_source_calls(
            rom.APPLICATION_MAIN_ROM_LAYOUT_BUILD_SOURCE,
            rom.APPLICATION_MAIN_ROM_LAYOUT_BUILD_SIZE,
            ((
                0x2F54C8,
                rom.APPLICATION_NPE_STATE_DISPATCH_LINKED_DESTINATION,
                rom.APPLICATION_NPE_STATE_DISPATCH_OVERLAY_DESTINATION,
            ), (
                0x2F5A1A,
                rom.APPLICATION_NPE_STATE_DISPATCH_LINKED_DESTINATION,
                rom.APPLICATION_NPE_STATE_DISPATCH_OVERLAY_DESTINATION,
            )),
        )
        modules = {
            item["destination"]: item
            for item in rom.manifest(image)["application_main_chain"]
        }

        self.assertEqual(source[:6],
                         [0x2E0E, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4])
        self.assertIn([0xBD22, 0xC370],
                      [source[i:i + 2] for i in range(len(source) - 1)])
        self.assertEqual(source[-8:], [
            0x385F, 0x384F, 0x383F, 0x382F,
            0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(
            words_at(image, rom.APPLICATION_MAIN_ROM_LAYOUT_BUILD_DESTINATION,
                     len(embedded)),
            embedded,
        )
        call_index = (0x2F54C8 - rom.APPLICATION_MAIN_ROM_LAYOUT_BUILD_SOURCE) // 2
        self.assertEqual(source[call_index:call_index + 2], [0xBD2B, 0x0000])
        self.assertEqual(embedded[call_index:call_index + 2], [0xBD5F, 0x0000])
        call_index = (0x2F5A1A - rom.APPLICATION_MAIN_ROM_LAYOUT_BUILD_SOURCE) // 2
        self.assertEqual(source[call_index:call_index + 2], [0xBD2B, 0x0000])
        self.assertEqual(embedded[call_index:call_index + 2], [0xBD5F, 0x0000])
        self.assertEqual(modules["12:5434"]["bytes"], 0x146E)

    def test_resident_application_selector_17_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_APPLICATION_SELECTOR_17_SOURCE,
            rom.RESIDENT_APPLICATION_SELECTOR_17_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_APPLICATION_SELECTOR_17_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(source[:5], [
            0x2E17, 0x58F2, 0x58F3, 0x58F6, 0x58F7,
        ])
        self.assertEqual(source[-6:], [
            0x387F, 0x386F, 0x383F, 0x382F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(
            info["resident_application_selector_17"]["bytes"],
            rom.RESIDENT_APPLICATION_SELECTOR_17_SIZE,
        )

    def test_resident_resource_dispatch_segment14_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        editor = rom.program_source_words(
            rom.RESIDENT_RESOURCE_EDITOR_14_SOURCE,
            rom.RESIDENT_RESOURCE_EDITOR_14_SIZE,
        )
        source = rom.program_source_words(
            rom.RESIDENT_RESOURCE_DISPATCH_14_SOURCE,
            rom.RESIDENT_RESOURCE_DISPATCH_14_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            rom.RESIDENT_RESOURCE_EDITOR_14_ADDRESS +
            rom.RESIDENT_RESOURCE_EDITOR_14_SIZE,
            rom.RESIDENT_RESOURCE_DISPATCH_14_ADDRESS,
        )
        self.assertEqual(
            words_at(image, rom.RESIDENT_RESOURCE_EDITOR_14_ADDRESS,
                     len(editor)),
            editor,
        )
        self.assertEqual(
            editor[:5], [0x2E07, 0x58F1, 0x58F2, 0x58F3, 0x58F4],
        )
        self.assertEqual(
            editor[-6:], [0x384F, 0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        rectangle_bottom_write = (
            rom.RESIDENT_RESOURCE_EDITOR_14_SOURCE + 0x0414
        )
        self.assertEqual(
            rom.program_source_words(rectangle_bottom_write, 14),
            [0x68F0, 0x0055, 0x6810, 0x00A4, 0xC700, 0xA8F0, 0x539C],
        )
        self.assertEqual(
            info["resident_resource_editor_14"]["bytes"],
            rom.RESIDENT_RESOURCE_EDITOR_14_SIZE,
        )
        self.assertEqual(
            words_at(image, rom.RESIDENT_RESOURCE_DISPATCH_14_ADDRESS,
                     len(source)),
            source,
        )
        self.assertEqual(
            source[:5], [0x2E07, 0x58F0, 0x58F1, 0x58F2, 0x58F3],
        )
        self.assertIn(0xC600, source)
        self.assertEqual(
            source[-6:], [0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            info["resident_resource_dispatch_14"]["bytes"],
            rom.RESIDENT_RESOURCE_DISPATCH_14_SIZE,
        )
        self.assertEqual(
            rom.RESIDENT_RESOURCE_DISPATCH_14_EVENT_TABLE_POINTER,
            0x14B716,
        )
        event_table = rom.program_source_words(
            rom.RESIDENT_RESOURCE_DISPATCH_14_EVENT_TABLE_SOURCE,
            rom.RESIDENT_RESOURCE_DISPATCH_14_EVENT_TABLE_SIZE,
        )
        self.assertEqual(
            event_table,
            [0xC11A, 0xC300, 0xC4E6, 0xC4E6, 0xC762, 0xC762, 0xB868],
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_RESOURCE_DISPATCH_14_EVENT_TABLE_ADDRESS,
                len(event_table),
            ),
            event_table,
        )
        kind_table = rom.program_source_words(
            rom.RESIDENT_RESOURCE_DISPATCH_14_KIND_TABLE_SOURCE,
            rom.RESIDENT_RESOURCE_DISPATCH_14_KIND_TABLE_SIZE,
        )
        self.assertEqual(
            kind_table,
            [
                0xBDB2, 0xBA5C, 0xB95A, 0xBAC4,
                0xBB28, 0xBD58, 0xBA06, 0xBE18,
            ],
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_RESOURCE_DISPATCH_14_KIND_TABLE_ADDRESS,
                len(kind_table),
            ),
            kind_table,
        )

    def test_resident_sound_effect_switch_segment1b_is_exact_guest_code(
        self,
    ) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_SOUND_EFFECT_SWITCH_1B_SOURCE,
            rom.RESIDENT_SOUND_EFFECT_SWITCH_1B_SIZE,
        )
        info = rom.manifest(image)["resident_sound_effect_switch_1b"]

        self.assertEqual(
            rom.RESIDENT_SOUND_EFFECT_SWITCH_1B_ADDRESS +
            rom.RESIDENT_SOUND_EFFECT_SWITCH_1B_SIZE,
            rom.APPLICATION_FOREGROUND_STATE50_WORKSPACE_ROM_DESTINATION,
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_SOUND_EFFECT_SWITCH_1B_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(
            source[:7],
            [0x2E08, 0x58F1, 0x58F2, 0x58F3, 0x58F4, 0x58F5, 0x081B],
        )
        self.assertEqual(
            rom.program_source_words(0x38A6BC, 0x22),
            [
                0xA866, 0xA866, 0xA7B2, 0xA80C, 0xA8FC, 0xA926,
                0xA9B0, 0xACAE, 0xACAE, 0xACAE, 0xACAE, 0xACAE,
                0xACAE, 0xA79E, 0xAC7A, 0xACAE, 0xA6EE,
            ],
        )
        self.assertEqual(
            source[-7:],
            [0x385F, 0x384F, 0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        self.assertEqual(info["bytes"], rom.RESIDENT_SOUND_EFFECT_SWITCH_1B_SIZE)

    def test_resident_settings_object_and_controller_are_exact_guest_code(
        self,
    ) -> None:
        image = rom.build_image()
        info = rom.manifest(image)

        modules = (
            (
                rom.RESIDENT_SETTINGS_OBJECT_1C_ADDRESS,
                rom.RESIDENT_SETTINGS_OBJECT_1C_SOURCE,
                rom.RESIDENT_SETTINGS_OBJECT_1C_SIZE,
                [0x2E04, 0x58F0, 0x58F1, 0x58F2, 0x58F3],
                [0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
            ),
            (
                rom.RESIDENT_SETTINGS_CONTROLLER_1C_ADDRESS,
                rom.RESIDENT_SETTINGS_CONTROLLER_1C_SOURCE,
                rom.RESIDENT_SETTINGS_CONTROLLER_1C_SIZE,
                [0x2E0C, 0x58F0, 0x58F1, 0x58F2, 0x58F3],
                [0x385F, 0x384F, 0x383F, 0x382F, 0x381F, 0x380F,
                 0x2F00, rom.RETS],
            ),
        )
        for destination, source_address, size, prefix, suffix in modules:
            self.assertEqual(source_address - destination, 0x1D0000)
            source = rom.program_source_words(source_address, size)
            self.assertEqual(source[:len(prefix)], prefix)
            self.assertEqual(source[-len(suffix):], suffix)
            self.assertEqual(
                words_at(image, destination, len(source)),
                source,
            )

        self.assertEqual(
            rom.RESIDENT_SETTINGS_OBJECT_1C_ADDRESS +
            rom.RESIDENT_SETTINGS_OBJECT_1C_SIZE,
            rom.RESIDENT_SETTINGS_CONTROLLER_1C_ADDRESS,
        )
        self.assertEqual(
            rom.RESIDENT_SETTINGS_CONTROLLER_1C_ADDRESS +
            rom.RESIDENT_SETTINGS_CONTROLLER_1C_SIZE,
            rom.RESIDENT_RESOURCE_STORAGE_UNIT_ADDRESS,
        )
        self.assertEqual(
            info["resident_settings_object_1c"],
            {
                "destination": "1C:7052",
                "source": "39:7052",
                "bytes": 0x07DE,
                "status": (
                    "exact same-PC resident settings object constructor, "
                    "including the D016 sound-effect record"
                ),
            },
        )
        self.assertEqual(
            info["resident_settings_controller_1c"],
            {
                "destination": "1C:7830",
                "source": "39:7830",
                "bytes": 0x07CE,
                "status": "exact same-PC resident settings event controller",
            },
        )

    def test_resident_npe_loader_service_segment14_is_exact_guest_code(
        self,
    ) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_NPE_LOADER_SERVICE_14_SOURCE,
            rom.RESIDENT_NPE_LOADER_SERVICE_14_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_NPE_LOADER_SERVICE_14_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(
            source[:5], [0x2E0F, 0x58F0, 0x58F1, 0x58F6, 0x4860],
        )
        self.assertEqual(
            source[-6:], [0x50FA, 0x386F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        entry = info["resident_npe_loader_service_14"]
        self.assertEqual(entry["destination"], "14:E742")
        self.assertEqual(entry["source"], "31:E742")
        self.assertEqual(entry["bytes"], 0x0FC6)
        self.assertEqual(entry["reachable_instructions"], 1404)
        self.assertEqual(entry["call_instructions"], 106)
        self.assertEqual(entry["unknown_frontiers"], 0)

    def test_resident_recursive_segment16_body_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_RECURSIVE_16_SOURCE,
            rom.RESIDENT_RECURSIVE_16_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_RECURSIVE_16_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(source[:9], [
            0x2E1A, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7,
        ])
        self.assertIn([0xBD16, 0x52AA],
                      [source[i:i + 2] for i in range(len(source) - 1)])
        self.assertEqual(source[-10:], [
            0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(info["resident_recursive_16"]["bytes"],
                         rom.RESIDENT_RECURSIVE_16_SIZE)

    def test_resident_font_blit_module_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_FONT_BLIT_SOURCE,
            rom.RESIDENT_FONT_BLIT_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_FONT_BLIT_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(source[:6],
                         [0x58F0, 0x58F1, 0x58F2,
                          0x58F3, 0x58F4, 0x58F5])
        self.assertEqual(
            words_at(image, 0x18657A, 6),
            [0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4, 0x58F5],
        )
        self.assertEqual(
            words_at(image, 0x18660A, 7),
            [0x58F0, 0x58F1, 0x58F2, 0x58F3,
             0x58F4, 0x58F6, 0x58F7],
        )
        self.assertEqual(source[-8:], [
            0x386F, 0x384F, 0x383F, 0x382F,
            0x381F, 0x380F, 0x3F00, rom.RETS,
        ])
        self.assertEqual(info["resident_font_blit_module"]["bytes"],
                         rom.RESIDENT_FONT_BLIT_SIZE)

    def test_resident_region_compose_18_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_REGION_COMPOSE_18_SOURCE,
            rom.RESIDENT_REGION_COMPOSE_18_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_REGION_COMPOSE_18_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(source[:7], [
            0x2E01, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F6, 0x58F7,
        ])
        self.assertEqual(source[-8:], [
            0x387F, 0x386F, 0x383F, 0x382F,
            0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(
            info["resident_region_compose_18"]["bytes"],
            rom.RESIDENT_REGION_COMPOSE_18_SIZE,
        )

    def test_resident_region_mask_18_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_REGION_MASK_18_SOURCE,
            rom.RESIDENT_REGION_MASK_18_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_REGION_MASK_18_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(source[:7], [
            0x2E52, 0x58F0, 0x58F1, 0x58F2,
            0x58F3, 0x58F6, 0x58F7,
        ])
        self.assertEqual(source[-8:], [
            0x387F, 0x386F, 0x383F, 0x382F,
            0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(info["resident_region_mask_18"], {
            "destination": "18:A510",
            "source": "35:A510",
            "bytes": 0x0AAA,
            "status": "exact same-PC resident pixel/region mask compositor",
        })

    def test_resident_operation_context_18_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_OPERATION_CONTEXT_18_SOURCE,
            rom.RESIDENT_OPERATION_CONTEXT_18_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_OPERATION_CONTEXT_18_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(source[:4], [0x2EB3, 0x58F1, 0x58F2, 0x58F3])
        self.assertIn(
            [0xBD33, 0x51E0],
            [source[i:i + 2] for i in range(len(source) - 1)],
        )
        self.assertIn(
            [0xBD30, 0xC9A2],
            [source[i:i + 2] for i in range(len(source) - 1)],
        )
        self.assertEqual(
            source[-5:], [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS]
        )
        self.assertEqual(
            info["resident_operation_context_18"]["bytes"],
            rom.RESIDENT_OPERATION_CONTEXT_18_SIZE,
        )

    def test_resident_menu_event_dispatch_is_exact_guest_code_and_table(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_MENU_EVENT_DISPATCH_SOURCE,
            rom.RESIDENT_MENU_EVENT_DISPATCH_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_MENU_EVENT_DISPATCH_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(source[:3], [0x2E20, 0x58F0, 0x58F1])
        self.assertEqual(source[-6:], [
            0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(
            words_at(image, 0x189BDA, 15),
            [
                0x9D7C, 0x9D7C, 0x9EBA, 0x9FB0, 0x9F00,
                0xA020, 0x9C8C, 0xA4F8, 0x9D50, 0x9D66,
                0xA4F8, 0xA4F8, 0xA4F8, 0x9C78, 0xA4FC,
            ],
        )
        self.assertEqual(info["resident_menu_event_dispatch_18"], {
            "destination": "18:9A58",
            "source": "35:9A58",
            "bytes": 0x0AB8,
            "status": (
                "exact same-PC resident 0x80..0x8e menu event dispatcher "
                "and jump table"
            ),
        })

    def test_resident_root_menu_modules_are_exact_guest_code(self) -> None:
        image = rom.build_image()
        renderer = rom.program_source_words(
            rom.RESIDENT_ROOT_MENU_RENDER_SOURCE,
            rom.RESIDENT_ROOT_MENU_RENDER_SIZE,
        )
        bitmap_blit = rom.program_source_words(
            rom.RESIDENT_ROOT_BITMAP_BLIT_SOURCE,
            rom.RESIDENT_ROOT_BITMAP_BLIT_SIZE,
        )
        controller = rom.program_source_words(
            rom.RESIDENT_ROOT_MENU_CONTROLLER_SOURCE,
            rom.RESIDENT_ROOT_MENU_CONTROLLER_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_ROOT_MENU_RENDER_ADDRESS,
                len(renderer),
            ),
            renderer,
        )
        self.assertEqual(renderer[:9], [
            0x2E10, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7,
        ])
        self.assertEqual(renderer[-10:], [
            0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(sum(
            renderer[index:index + 2] == [0xBD17, 0x9244]
            for index in range(len(renderer) - 1)
        ), 2)
        self.assertEqual(sum(
            renderer[index:index + 2] == [0xBD18, 0xA510]
            for index in range(len(renderer) - 1)
        ), 8)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_ROOT_BITMAP_BLIT_ADDRESS,
                len(bitmap_blit),
            ),
            bitmap_blit,
        )
        self.assertEqual(bitmap_blit[:7], [
            0x2E45, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F6, 0x58F7,
        ])
        self.assertEqual(bitmap_blit[-8:], [
            0x387F, 0x386F, 0x383F, 0x382F,
            0x381F, 0x380F, 0x2F00, rom.RETS,
        ])

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_ROOT_MENU_CONTROLLER_ADDRESS,
                len(controller),
            ),
            controller,
        )
        self.assertEqual(controller[:9], [
            0x2E05, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7,
        ])
        self.assertEqual(controller[-10:], [
            0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        table_index = (0x1DF3DA - rom.RESIDENT_ROOT_MENU_CONTROLLER_ADDRESS) // 2
        self.assertEqual(controller[table_index:table_index + 6], [
            0xF4F4, 0xF3E6, 0xF41C, 0xF452, 0xF488, 0xF4BE,
        ])
        self.assertEqual(sum(
            controller[index:index + 2] == [0xBD10, 0xE4AA]
            for index in range(len(controller) - 1)
        ), 3)
        self.assertEqual(info["resident_root_menu_render_10_e4aa"], {
            "destination": "10:E4AA",
            "source": "2D:E4AA",
            "bytes": 0x1764,
            "status": (
                "exact same-PC hierarchy-aware root-menu rendering body"
            ),
        })
        self.assertEqual(info["resident_root_bitmap_blit_17_18e6"], {
            "destination": "17:18E6",
            "source": "34:18E6",
            "bytes": 0x0C5A,
            "status": (
                "exact same-PC packed bitmap and mask compositor used by "
                "root-menu resources"
            ),
        })
        self.assertEqual(info["resident_root_menu_controller_1d_f2ec"], {
            "destination": "1D:F2EC",
            "source": "3A:F2EC",
            "bytes": 0x06D0,
            "status": (
                "exact same-PC resident root-menu controller reached through "
                "the recovered 20:2DE0 foreground wrapper"
            ),
        })

    def test_resident_menu_record_decoder_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_MENU_RECORD_DECODE_11_SOURCE,
            rom.RESIDENT_MENU_RECORD_DECODE_11_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_MENU_RECORD_DECODE_11_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(source[:3], [0x2E39, 0x58F1, 0x58F2])
        self.assertEqual(source[-8:], [
            0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(
            words_at(image, rom.RESIDENT_MENU_RECORD_DECODE_11_ADDRESS, 1),
            [0x2E39],
        )
        self.assertEqual(info["resident_menu_record_decode_11"], {
            "destination": "11:5C12",
            "source": "2E:5C12",
            "bytes": 0x16A4,
            "status": (
                "exact same-PC resident menu-page record decoder with "
                "30:FE0E memory-fill dependency"
            ),
        })

    def test_resident_npe_runtime_table_init_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_NPE_RUNTIME_TABLE_INIT_SOURCE,
            rom.RESIDENT_NPE_RUNTIME_TABLE_INIT_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_NPE_RUNTIME_TABLE_INIT_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(source[:12], [
            0x2E04, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4,
            0x58F5, 0x4810, 0x4800, 0x6A0B, 0xFFFA, 0x6A1B,
        ])
        self.assertEqual(source[-12:], [
            0x1901, 0x5603, 0xAC09, 0x72DA, 0x385F, 0x384F,
            0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(
            rom.RESIDENT_MENU_RECORD_DECODE_11_ADDRESS
            + rom.RESIDENT_MENU_RECORD_DECODE_11_SIZE,
            rom.RESIDENT_NPE_RUNTIME_TABLE_INIT_ADDRESS,
        )
        self.assertEqual(info["resident_npe_runtime_table_init_11_72b6"], {
            "destination": "11:72B6",
            "source": "2E:72B6",
            "bytes": rom.RESIDENT_NPE_RUNTIME_TABLE_INIT_SIZE,
            "caller": "46:D1C4; loaded NPE module maps to 29:D1C4",
            "argument_bytes": 0x00,
            "reachable_instructions": 2151,
            "direct_calls": 135,
            "dependencies": ["33:07B0", "03:4010", "03:401C", "1C:188E"],
            "status": "exact same-PC resident NPE runtime-table constructor",
        })

    def test_resident_runtime_table_populate_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_RUNTIME_TABLE_POPULATE_1C_SOURCE,
            rom.RESIDENT_RUNTIME_TABLE_POPULATE_1C_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_RUNTIME_TABLE_POPULATE_1C_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(source[:12], [
            0x2E05, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4,
            0x58F5, 0x780B, 0x0008, 0x781B, 0x000A, 0x5210,
        ])
        self.assertEqual(source[-12:], [
            0x1949, 0x5644, 0xAC09, 0x1FBC, 0x385F, 0x384F,
            0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(info["resident_runtime_table_populate_1c_188e"], {
            "destination": "1C:188E",
            "source": "39:188E",
            "bytes": rom.RESIDENT_RUNTIME_TABLE_POPULATE_1C_SIZE,
            "callers": ["2E:88C8", "30:A5E8", "38:E158", "38:F8EA"],
            "argument_bytes": 0x06,
            "reachable_instructions": 789,
            "direct_calls": 19,
            "dependencies": ["33:07B0", "22:C370"],
            "status": "exact same-PC resident runtime-table population body",
        })

    def test_resident_menu_page_table_is_exact_guest_data(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_MENU_PAGE_TABLE_SOURCE,
            rom.RESIDENT_MENU_PAGE_TABLE_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_MENU_PAGE_TABLE_ADDRESS, len(source)),
            source,
        )
        # Page zero: four layout/style fields, five items, then five far
        # pointers to 20:1142..20:116A.
        self.assertEqual(source[:15], [
            0x0004, 0x0023, 0x001E, 0x0062, 0x0005,
            0x0020, 0x1142,
            0x0020, 0x114C,
            0x0020, 0x1156,
            0x0020, 0x1160,
            0x0020, 0x116A,
        ])
        self.assertEqual(info["resident_menu_page_table_1c"], {
            "destination": "1C:9748",
            "source": "39:9748",
            "bytes": 0x0672,
            "status": "exact 25-record resident menu hierarchy table",
        })

    def test_resident_application_launch_manager_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_APPLICATION_LAUNCH_MANAGER_SOURCE,
            rom.RESIDENT_APPLICATION_LAUNCH_MANAGER_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image,
                     rom.RESIDENT_APPLICATION_LAUNCH_MANAGER_ADDRESS,
                     len(source)),
            source,
        )
        self.assertEqual(source[:4], [0x2E0F, 0x58F1, 0x58F2, 0x58F3])
        self.assertIn(
            [0xBD2F, 0xE4C8],
            [source[index:index + 2]
             for index in range(len(source) - 1)],
        )
        self.assertEqual(source[-7:], [
            0x385F, 0x384F, 0x383F, 0x382F,
            0x381F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(info["resident_application_launch_manager_18"], {
            "destination": "18:21F4",
            "source": "35:21F4",
            "bytes": 0x0B2E,
            "status": (
                "exact same-PC resident application selector/launcher with "
                "2F:E4C8 registry lookup"
            ),
        })

    def test_application_launch_context_modules_are_exact_guest_code(self) -> None:
        image = rom.build_image()
        info = rom.manifest(image)

        for address, source_address, size, first_words, last_words in (
            (
                rom.RESIDENT_APPLICATION_RECORD_LOADER_ADDRESS,
                rom.RESIDENT_APPLICATION_RECORD_LOADER_SOURCE,
                rom.RESIDENT_APPLICATION_RECORD_LOADER_SIZE,
                [0x2E15, 0x58F1, 0x58F2, 0x58F3],
                [0x385F, 0x384F, 0x383F, 0x382F,
                 0x381F, 0x2F00, rom.RETS],
            ),
            (
                rom.RESIDENT_APPLICATION_RESOURCE_OPEN_ADDRESS,
                rom.RESIDENT_APPLICATION_RESOURCE_OPEN_SOURCE,
                rom.RESIDENT_APPLICATION_RESOURCE_OPEN_SIZE,
                [0x2E18, 0x58F1, 0x58F2, 0x58F3],
                [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
            ),
        ):
            source = rom.program_source_words(source_address, size)
            self.assertEqual(words_at(image, address, len(source)), source)
            self.assertEqual(source[:len(first_words)], first_words)
            self.assertEqual(source[-len(last_words):], last_words)

        loader = rom.program_source_words(
            rom.RESIDENT_APPLICATION_RECORD_LOADER_SOURCE,
            rom.RESIDENT_APPLICATION_RECORD_LOADER_SIZE,
        )
        self.assertIn([0xBD31, 0xAA5C], [
            loader[index:index + 2] for index in range(len(loader) - 1)
        ])
        resource_open = rom.program_source_words(
            rom.RESIDENT_APPLICATION_RESOURCE_OPEN_SOURCE,
            rom.RESIDENT_APPLICATION_RESOURCE_OPEN_SIZE,
        )
        self.assertIn([0xBD02, 0xDEA6], [
            resource_open[index:index + 2]
            for index in range(len(resource_open) - 1)
        ])
        self.assertEqual(info["resident_application_record_loader_1d_0eea"], {
            "destination": "1D:0EEA",
            "source": "3A:0EEA",
            "bytes": 0x0770,
            "status": "exact same-PC application-record storage window loader",
        })
        self.assertEqual(info["resident_application_resource_open_1d_668a"], {
            "destination": "1D:668A",
            "source": "3A:668A",
            "bytes": 0x0730,
            "status": "exact same-PC application resource validation/open body",
        })

    def test_resident_des_is_guest_code_with_recovered_six_word_abi(self) -> None:
        image = rom.build_image()
        words = rom.des_transform_words()
        info = rom.manifest(image)

        self.assertEqual(len(words) * 2, 0x03F0)
        self.assertEqual(
            words_at(image, rom.RESIDENT_DES_TRANSFORM_ADDRESS, len(words)),
            words,
        )
        self.assertEqual(words[:4], [0x58FB, 0x08BF, 0x58F1, 0x58F2])
        self.assertNotIn(0xBD02, words)
        self.assertIn([0x4800, 0x38BF, rom.RETS], [
            words[index:index + 3] for index in range(len(words) - 2)
        ])

        program = rom.program_source_bytes(0x200000, 0x400000)
        call = bytes.fromhex("02bda6de")
        self.assertEqual(program.count(call), 24)
        self.assertEqual(program.count(call + bytes.fromhex("fc50")), 24)

        tables = rom.des_table_bytes()
        self.assertEqual(len(tables), 840)
        self.assertEqual(tables[:8], bytes(rom.DES_IP[:8]))
        self.assertEqual(
            tables[rom.DES_TABLE_SBOX - rom.DES_TABLE_IP:][0:16],
            bytes(rom.DES_SBOXES[0][:16]),
        )
        installer = rom.menu_runtime_overlay_installer_words()
        self.assertEqual(installer[:2], [
            0xBD00 | (rom.DES_TABLE_INITIALIZER_ADDRESS >> 16),
            rom.DES_TABLE_INITIALIZER_ADDRESS & 0xFFFF,
        ])
        self.assertEqual(info["resident_des_transform_02_dea6"]["call_sites"], 24)
        self.assertEqual(
            info["resident_des_transform_02_dea6"]["triple_des_use"],
            "two-key E-D-E over consecutive 8-byte keys",
        )

    def test_menu_catalogue_and_wrapper_are_installed_from_exact_prg_copies(
        self,
    ) -> None:
        installer = rom.menu_runtime_overlay_installer_words()
        main_installer = rom.install_application_main_chain_words()
        loader = rom.rom01_application_loader_words()

        self.assertEqual(installer[2:4], [
            0xBD00 | (
                rom.APPLICATION_MENU_RESOURCE_DECODER_INSTALLER_ADDRESS >> 16
            ),
            rom.APPLICATION_MENU_RESOURCE_DECODER_INSTALLER_ADDRESS & 0xFFFF,
        ])

        # The catalogue now has an early data-only publication step because
        # the bootstrap root renderer consumes it before executable menu
        # overlays are safe to install.  DES initialization remains covered
        # by menu_runtime_overlay_installer_words() above.
        self.assertEqual(main_installer[:2], [
            0xBD00 | (rom.MENU_CATALOG_EARLY_INSTALLER_ADDRESS >> 16),
            rom.MENU_CATALOG_EARLY_INSTALLER_ADDRESS & 0xFFFF,
        ])
        resolver_patch = rom.write_program_words(
            rom.APPLICATION_STORAGE_RECORD_LOOKUP_DRIVER_CALL,
            (0xBD00 | (rom.RESIDENT_STORAGE_DRIVER_ADDRESS >> 16),
             rom.RESIDENT_STORAGE_DRIVER_ADDRESS & 0xFFFF),
        )
        self.assertIn(
            resolver_patch,
            [installer[index:index + len(resolver_patch)]
             for index in range(len(installer) - len(resolver_patch) + 1)],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_STORAGE_RECORD_LOOKUP_DRIVER_CALL_SOURCE, 4
            ),
            [0xBD2D, 0x3460],
        )
        extra_installer = rom.application_region_extra_installer_words()
        self.assertIn(
            resolver_patch,
            [
                extra_installer[index:index + len(resolver_patch)]
                for index in range(
                    len(extra_installer) - len(resolver_patch) + 1
                )
            ],
        )
        text_stream_source = rom.program_source_words(
            rom.APPLICATION_MENU_TEXT_STREAM_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_TEXT_STREAM_OVERLAY_SIZE,
        )
        self.assertEqual(text_stream_source[:2], [0x2E05, 0x58F0])
        self.assertEqual(text_stream_source[-2:], [0x2F00, rom.RETS])
        self.assertEqual(
            rom.application_menu_text_stream_installer_words(),
            [
                *rom.embed_program_overlay_words(
                    rom.APPLICATION_MENU_TEXT_STREAM_OVERLAY_DESTINATION,
                    rom.APPLICATION_MENU_TEXT_STREAM_OVERLAY_SOURCE,
                    rom.APPLICATION_MENU_TEXT_STREAM_OVERLAY_SIZE,
                ),
                rom.RETS,
            ],
        )
        text_stream_installer_call = [
            0xBD00 | (rom.APPLICATION_MENU_TEXT_STREAM_INSTALLER_ADDRESS >> 16),
            rom.APPLICATION_MENU_TEXT_STREAM_INSTALLER_ADDRESS & 0xFFFF,
        ]
        self.assertIn(
            text_stream_installer_call,
            [installer[index:index + 2]
             for index in range(len(installer) - 1)],
        )
        self.assertNotIn(
            [0xBD00 | (rom.MENU_RUNTIME_OVERLAY_INSTALLER_ADDRESS >> 16),
             rom.MENU_RUNTIME_OVERLAY_INSTALLER_ADDRESS & 0xFFFF],
            [main_installer[index:index + 2]
             for index in range(len(main_installer) - 1)],
        )

        storage_dispatch = rom.copy_code_to_overlay_words(
            rom.STORAGE_RECORD_DISPATCH_OVERLAY_DESTINATION,
            rom.STORAGE_RECORD_DISPATCH_OVERLAY_SOURCE,
            rom.STORAGE_RECORD_DISPATCH_OVERLAY_SIZE,
        )
        for lifecycle_installer in (main_installer, installer):
            self.assertIn(
                storage_dispatch,
                [lifecycle_installer[index:index + len(storage_dispatch)]
                 for index in range(
                     len(lifecycle_installer) - len(storage_dispatch) + 1
                 )],
            )
        for destination, source, size, embedded in (
            (rom.APPLICATION_TEXT_LOOP_OVERLAY_DESTINATION,
             rom.APPLICATION_TEXT_LOOP_OVERLAY_SOURCE,
             rom.APPLICATION_TEXT_LOOP_OVERLAY_SIZE, False),
            (rom.APPLICATION_GLYPH_DRAW_OVERLAY_DESTINATION,
             rom.APPLICATION_GLYPH_DRAW_OVERLAY_SOURCE,
             rom.APPLICATION_GLYPH_DRAW_OVERLAY_SIZE, False),
            (rom.COMMAND_MATRIX_OVERLAY_DESTINATION,
             rom.COMMAND_MATRIX_OVERLAY_SOURCE,
             rom.COMMAND_MATRIX_OVERLAY_SIZE, False),
            (rom.ROM03_FAR_MEMCPY_THUNK_DESTINATION,
             rom.ROM03_FAR_MEMCPY_THUNK_SOURCE,
             rom.ROM03_FAR_MEMCPY_THUNK_SIZE, True),
            (rom.APPLICATION_RESULT_MODE_PAIR_OVERLAY_DESTINATION,
             rom.APPLICATION_RESULT_MODE_PAIR_OVERLAY_SOURCE,
             rom.APPLICATION_RESULT_MODE_PAIR_OVERLAY_SIZE, True),
            (rom.APPLICATION_TEXT_DISPATCH_OVERLAY_DESTINATION,
             rom.APPLICATION_TEXT_DISPATCH_OVERLAY_SOURCE,
             rom.APPLICATION_TEXT_DISPATCH_OVERLAY_SIZE, True),
            (rom.APPLICATION_TEXT_DISPATCH_F0_OVERLAY_DESTINATION,
             rom.APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SOURCE,
             rom.APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SIZE, True),
        ):
            descriptor = (
                rom.embed_program_overlay_words(destination, source, size)
                if embedded else
                rom.copy_code_to_overlay_words(destination, source, size)
            )
            self.assertIn(
                descriptor,
                [installer[index:index + len(descriptor)]
                 for index in range(len(installer) - len(descriptor) + 1)],
            )
            if destination in {
                rom.APPLICATION_TEXT_LOOP_OVERLAY_DESTINATION,
                rom.APPLICATION_GLYPH_DRAW_OVERLAY_DESTINATION,
            }:
                self.assertIn(
                    descriptor,
                    [main_installer[index:index + len(descriptor)]
                     for index in range(
                         len(main_installer) - len(descriptor) + 1
                     )],
                )

        for destination, source, size in (
            (rom.APPLICATION_MENU_CATALOG_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_CATALOG_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_CATALOG_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_SIZE),
            (rom.APPLICATION_REGISTRY_OVERLAY_DESTINATION,
             rom.APPLICATION_REGISTRY_OVERLAY_SOURCE,
             rom.APPLICATION_REGISTRY_OVERLAY_SIZE),
            (rom.APPLICATION_REGISTRY_LOOKUP_OVERLAY_DESTINATION,
             rom.APPLICATION_REGISTRY_LOOKUP_OVERLAY_SOURCE,
             rom.APPLICATION_REGISTRY_LOOKUP_OVERLAY_SIZE),
            (rom.APPLICATION_UNALIGNED_U16_OVERLAY_DESTINATION,
             rom.APPLICATION_UNALIGNED_U16_OVERLAY_SOURCE,
             rom.APPLICATION_UNALIGNED_U16_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_TEXT_INPUT_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_TEXT_INPUT_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_TEXT_INPUT_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_UI_ADAPTER_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_UI_ADAPTER_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_UI_ADAPTER_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_POSITION_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_POSITION_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_POSITION_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_COORDINATE_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_COORDINATE_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_COORDINATE_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_RENDER_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_RENDER_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_RENDER_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_RESOURCE_BIND_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_RESULT_ATTACH_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_RESULT_ATTACH_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_RESULT_ATTACH_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_RESULT_LIST_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_RESULT_LIST_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_RESULT_LIST_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_RESULT_RANGE_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_RESULT_RANGE_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_RESULT_RANGE_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_RESULT_PROCESS_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_RESULT_PROCESS_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_RESULT_PROCESS_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_PAGE_POPULATE_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_PAGE_POPULATE_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_PAGE_POPULATE_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_TEXT_EXPAND_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_TEXT_EXPAND_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_TEXT_EXPAND_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_SIZE),
            (rom.APPLICATION_FOREGROUND_EVENT_OVERLAY_DESTINATION,
             rom.APPLICATION_FOREGROUND_EVENT_OVERLAY_SOURCE,
             rom.APPLICATION_FOREGROUND_EVENT_OVERLAY_SIZE),
            (rom.APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_DESTINATION,
             rom.APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_SOURCE,
             rom.APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_POWER_STATE_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_POWER_STATE_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_POWER_STATE_OVERLAY_SIZE),
            (rom.APPLICATION_GENERIC_MENU_OVERLAY_DESTINATION,
             rom.APPLICATION_GENERIC_MENU_OVERLAY_SOURCE,
             rom.APPLICATION_GENERIC_MENU_OVERLAY_SIZE),
            (rom.APPLICATION_CONTEXT_GATE_OVERLAY_DESTINATION,
             rom.APPLICATION_CONTEXT_GATE_OVERLAY_SOURCE,
             rom.APPLICATION_CONTEXT_GATE_OVERLAY_SIZE),
            (rom.APPLICATION_RECORD_XOR_OVERLAY_DESTINATION,
             rom.APPLICATION_RECORD_XOR_OVERLAY_SOURCE,
             rom.APPLICATION_RECORD_XOR_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_TABLE_BUILD_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_TABLE_BUILD_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_TABLE_BUILD_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_XOR_U16_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_XOR_U16_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_XOR_U16_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_RESOURCE_POINTER_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_RESOURCE_POINTER_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_RESOURCE_POINTER_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_RESOURCE_TYPE3_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_RESOURCE_TYPE3_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_RESOURCE_TYPE3_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_RESOURCE_TYPE4_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_RESOURCE_TYPE4_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_RESOURCE_TYPE4_OVERLAY_SIZE),
        ):
            descriptor = rom.copy_code_to_overlay_words(
                destination, source, size,
            )
            self.assertIn(
                descriptor,
                [installer[index:index + len(descriptor)]
                 for index in range(len(installer) - len(descriptor) + 1)],
            )

        page_layout = rom.program_source_words(
            rom.APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SIZE,
        )
        self.assertEqual(page_layout[:2], [0x2E0C, 0x58F1])
        for call in (
            [0xBD32, 0x9D22], [0xBD33, 0x07B0],
            [0xBD33, 0x1E7A], [0xBD25, 0x77DA],
            [0xBD31, 0x5300], [0xBD24, 0x1F02],
            [0xBD30, 0x8B26],
        ):
            self.assertIn(call, [
                page_layout[index:index + 2]
                for index in range(len(page_layout) - 1)
            ])
        for address in (0x9748, 0x974A, 0x974C):
            self.assertIn(address, page_layout)
        self.assertEqual(page_layout[-9:], [
            0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, 0x2F00, rom.RETS,
        ])

        for source_address, size in (
            (rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_PAGE_OBJECTS_CONDITIONAL_OVERLAY_SIZE),
        ):
            page_objects = rom.program_source_words(source_address, size)
            self.assertEqual(page_objects[:2], [0x2E0B, 0x58F0])
            self.assertIn([0xBD29, 0x6C7C], [
                page_objects[index:index + 2]
                for index in range(len(page_objects) - 1)
            ])
            self.assertEqual(page_objects[-10:], [
                0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
                0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
            ])

        # The natural bootstrap root controller reaches the ordinary builder
        # before the later resident-manager overlay exchange.  Its computed
        # near-jump table must therefore arrive in the early foreground
        # installer together with the rest of the exact source-44 body.
        page_objects = rom.program_source_words(
            rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SIZE,
        )
        table_index = (
            0x4458C2 - rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SOURCE
        ) // 2
        self.assertEqual(page_objects[table_index:table_index + 6], [
            0x596E, 0x58CE, 0x58EE, 0x590E, 0x592E, 0x594E,
        ])
        early_page_objects = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_DESTINATION,
            rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SIZE,
        )
        early_installer = (
            rom.application_foreground_state_handler_installer_words()
        )
        self.assertIn(
            early_page_objects,
            [early_installer[index:index + len(early_page_objects)]
             for index in range(
                 len(early_installer) - len(early_page_objects) + 1
             )],
        )
        early_page_layout = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_DESTINATION,
            rom.APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SIZE,
        )
        self.assertIn(
            early_page_layout,
            [early_installer[index:index + len(early_page_layout)]
             for index in range(
                 len(early_installer) - len(early_page_layout) + 1
             )],
        )

        event_state = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_SIZE,
        )
        self.assertEqual(event_state[:4], [0x2E00, 0x58F1, 0x780B, 0x0006])
        self.assertEqual(event_state[-3:], [0x381F, 0x2F00, rom.RETS])

        embedded_finalize = rom.embed_program_overlay_words(
            rom.APPLICATION_UI_FINALIZE_OVERLAY_DESTINATION,
            rom.APPLICATION_UI_FINALIZE_OVERLAY_SOURCE,
            rom.APPLICATION_UI_FINALIZE_OVERLAY_SIZE,
        )
        self.assertIn(
            embedded_finalize,
            [installer[index:index + len(embedded_finalize)]
             for index in range(len(installer) - len(embedded_finalize) + 1)],
        )

        self.assertIn(
            [0xBD00 | (
                rom.MENU_ARITHMETIC_WRAPPER_INSTALLER_ADDRESS >> 16
             ), rom.MENU_ARITHMETIC_WRAPPER_INSTALLER_ADDRESS & 0xFFFF],
            [installer[index:index + 2]
             for index in range(len(installer) - 1)],
        )
        arithmetic_installer = rom.menu_arithmetic_wrapper_installer_words()
        self.assertEqual(arithmetic_installer[-1], rom.RETS)
        for destination, source, size in (
            (rom.APPLICATION_OBJECT_RELEASE_OVERLAY_DESTINATION,
             rom.APPLICATION_OBJECT_RELEASE_OVERLAY_SOURCE,
             rom.APPLICATION_OBJECT_RELEASE_OVERLAY_SIZE),
            (rom.APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_DESTINATION,
             rom.APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SOURCE,
             rom.APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SIZE),
            (rom.APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_DESTINATION,
             rom.APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SOURCE,
             rom.APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SIZE),
            (rom.APPLICATION_ASCII_WHITESPACE_OVERLAY_DESTINATION,
             rom.APPLICATION_ASCII_WHITESPACE_OVERLAY_SOURCE,
             rom.APPLICATION_ASCII_WHITESPACE_OVERLAY_SIZE),
            (rom.WIDE_FROM_INT16_OVERLAY_DESTINATION,
             rom.WIDE_FROM_INT16_OVERLAY_SOURCE,
             rom.WIDE_FROM_INT16_OVERLAY_SIZE),
            (rom.UINT32_MODULO_WRAPPER_OVERLAY_DESTINATION,
             rom.UINT32_MODULO_WRAPPER_OVERLAY_SOURCE,
             rom.UINT32_MODULO_WRAPPER_OVERLAY_SIZE),
            (rom.INT32_MODULO_WRAPPER_OVERLAY_DESTINATION,
             rom.INT32_MODULO_WRAPPER_OVERLAY_SOURCE,
             rom.INT32_MODULO_WRAPPER_OVERLAY_SIZE),
        ):
            embedded = rom.embed_program_overlay_words(
                destination, source, size,
            )
            self.assertIn(
                embedded,
                [arithmetic_installer[index:index + len(embedded)]
                 for index in range(
                     len(arithmetic_installer) - len(embedded) + 1
                 )],
            )
        self.assertIn(
            [0xBD00 | (
                rom.MENU_DECIMAL_PARSE_ENGINE_INSTALLER_ADDRESS >> 16
             ), rom.MENU_DECIMAL_PARSE_ENGINE_INSTALLER_ADDRESS & 0xFFFF],
            [arithmetic_installer[index:index + 2]
             for index in range(len(arithmetic_installer) - 1)],
        )
        decimal_engine_installer = (
            rom.menu_decimal_parse_engine_installer_words()
        )
        self.assertEqual(decimal_engine_installer[-1], rom.RETS)
        embedded_decimal_engine = rom.embed_program_overlay_words(
            rom.APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_DESTINATION,
            rom.APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SOURCE,
            rom.APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SIZE,
        )
        self.assertIn(
            embedded_decimal_engine,
            [decimal_engine_installer[index:
                                      index + len(embedded_decimal_engine)]
             for index in range(
                 len(decimal_engine_installer) -
                 len(embedded_decimal_engine) + 1
             )],
        )

        result_table_installer = rom.menu_result_table_installer_words()
        self.assertIn(
            [0xBD00 | (rom.MENU_RESULT_TABLE_INSTALLER_ADDRESS >> 16),
             rom.MENU_RESULT_TABLE_INSTALLER_ADDRESS & 0xFFFF],
            [installer[index:index + 2]
             for index in range(len(installer) - 1)],
        )
        for destination, source, size in (
            (rom.APPLICATION_RESULT_TABLE_ALLOC_OVERLAY_DESTINATION,
             rom.APPLICATION_RESULT_TABLE_ALLOC_OVERLAY_SOURCE,
             rom.APPLICATION_RESULT_TABLE_ALLOC_OVERLAY_SIZE),
            (rom.APPLICATION_RESULT_TABLE_POINTER_OVERLAY_DESTINATION,
             rom.APPLICATION_RESULT_TABLE_POINTER_OVERLAY_SOURCE,
             rom.APPLICATION_RESULT_TABLE_POINTER_OVERLAY_SIZE),
        ):
            embedded = rom.embed_program_overlay_words(
                destination, source, size,
            )
            self.assertIn(
                embedded,
                [result_table_installer[index:index + len(embedded)]
                 for index in range(
                     len(result_table_installer) - len(embedded) + 1
                 )],
            )

        for destination, source, size in (
            (rom.APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_STORAGE_MASK_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STORAGE_MASK_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STORAGE_MASK_OVERLAY_SIZE),
            (rom.APPLICATION_CONTEXT_LOOKUP_OVERLAY_DESTINATION,
             rom.APPLICATION_CONTEXT_LOOKUP_OVERLAY_SOURCE,
             rom.APPLICATION_CONTEXT_LOOKUP_OVERLAY_SIZE),
        ):
            descriptor = rom.copy_code_to_overlay_words(
                destination, source, size,
            )
            self.assertIn(
                descriptor,
                [result_table_installer[index:index + len(descriptor)]
                 for index in range(
                     len(result_table_installer) - len(descriptor) + 1
                )],
            )

        self.assertIn(
            [0xBD00 | (rom.MENU_SERVICE_INIT_INSTALLER_ADDRESS >> 16),
             rom.MENU_SERVICE_INIT_INSTALLER_ADDRESS & 0xFFFF],
            [result_table_installer[index:index + 2]
             for index in range(len(result_table_installer) - 1)],
        )
        service_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MAIN_SERVICE_INIT_OVERLAY_DESTINATION,
            rom.APPLICATION_MAIN_SERVICE_INIT_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_SERVICE_INIT_OVERLAY_SIZE,
        )
        self.assertEqual(
            rom.menu_service_init_installer_words(),
            [*service_descriptor, rom.RETS],
        )

        embedded_flag = rom.embed_program_overlay_words(
            rom.APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_DESTINATION,
            rom.APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_SIZE,
        )
        self.assertIn(
            embedded_flag,
            [result_table_installer[index:index + len(embedded_flag)]
             for index in range(
                 len(result_table_installer) - len(embedded_flag) + 1
             )],
        )

        for destination, source, size in (
            (rom.APPLICATION_MENU_STATE_CLEAR_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_STATE_CLEAR_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_STATE_CLEAR_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_SIZE),
            (rom.APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_DESTINATION,
             rom.APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_SOURCE,
             rom.APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_SIZE),
        ):
            embedded = rom.embed_program_overlay_words(
                destination, source, size,
            )
            self.assertIn(
                embedded,
                [result_table_installer[index:index + len(embedded)]
                 for index in range(
                     len(result_table_installer) - len(embedded) + 1
                 )],
            )

        dependency_installer = rom.menu_event_state_installer_words()
        menu_buffer_setup = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MENU_BUFFER_SETUP_OVERLAY_DESTINATION,
            rom.APPLICATION_MENU_BUFFER_SETUP_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_BUFFER_SETUP_OVERLAY_SIZE,
        )
        self.assertIn(
            menu_buffer_setup,
            [dependency_installer[index:index + len(menu_buffer_setup)]
             for index in range(
                 len(dependency_installer) - len(menu_buffer_setup) + 1
             )],
        )
        menu_buffer_words = rom.program_source_words(
            rom.APPLICATION_MENU_BUFFER_SETUP_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_BUFFER_SETUP_OVERLAY_SIZE,
        )
        self.assertEqual(menu_buffer_words[:5],
                         [0x2E04, 0x58F0, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(menu_buffer_words[-6:],
                         [0x383F, 0x382F, 0x381F, 0x380F,
                          0x2F00, rom.RETS])

        menu_layout_build = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MENU_LAYOUT_BUILD_OVERLAY_DESTINATION,
            rom.APPLICATION_MENU_LAYOUT_BUILD_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_LAYOUT_BUILD_OVERLAY_SIZE,
        )
        self.assertIn(
            menu_layout_build,
            [dependency_installer[index:index + len(menu_layout_build)]
             for index in range(
                 len(dependency_installer) - len(menu_layout_build) + 1
             )],
        )
        menu_layout_words = rom.program_source_words(
            rom.APPLICATION_MENU_LAYOUT_BUILD_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_LAYOUT_BUILD_OVERLAY_SIZE,
        )
        self.assertEqual(menu_layout_words[:6],
                         [0x2E09, 0x58F1, 0x58F2, 0x58F3, 0x58F4, 0x58F5])
        self.assertEqual(menu_layout_words[-7:],
                         [0x385F, 0x384F, 0x383F, 0x382F, 0x381F,
                          0x2F00, rom.RETS])

        menu_event_gateway = rom.copy_code_to_overlay_words(
            rom.APPLICATION_WIDE_GATE_OVERLAY_DESTINATION,
            rom.APPLICATION_WIDE_GATE_OVERLAY_SOURCE,
            rom.APPLICATION_WIDE_GATE_OVERLAY_SIZE,
        )
        self.assertIn(
            menu_event_gateway,
            [dependency_installer[index:index + len(menu_event_gateway)]
             for index in range(
                 len(dependency_installer) - len(menu_event_gateway) + 1
             )],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_WIDE_GATE_OVERLAY_SOURCE,
                rom.APPLICATION_WIDE_GATE_OVERLAY_SIZE,
            ),
            [0xAD2F, 0xC216],
        )

        for destination, source, size in (
            (rom.APPLICATION_STATE_TICK_SAMPLE_OVERLAY_DESTINATION,
             rom.APPLICATION_STATE_TICK_SAMPLE_OVERLAY_SOURCE,
             rom.APPLICATION_STATE_TICK_SAMPLE_OVERLAY_SIZE),
            (rom.APPLICATION_STATE_TICK_COMMIT_OVERLAY_DESTINATION,
             rom.APPLICATION_STATE_TICK_COMMIT_OVERLAY_SOURCE,
             rom.APPLICATION_STATE_TICK_COMMIT_OVERLAY_SIZE),
        ):
            descriptor = rom.copy_code_to_overlay_words(
                destination, source, size,
            )
            self.assertIn(
                descriptor,
                [dependency_installer[index:index + len(descriptor)]
                 for index in range(
                     len(dependency_installer) - len(descriptor) + 1
                 )],
            )
        tick_sample = rom.program_source_words(
            rom.APPLICATION_STATE_TICK_SAMPLE_OVERLAY_SOURCE,
            rom.APPLICATION_STATE_TICK_SAMPLE_OVERLAY_SIZE,
        )
        self.assertEqual(tick_sample[:7],
                         [0x2E01, 0x58F0, 0x58F1, 0x58F2,
                          0x58F3, 0x58F4, 0x58F5])
        self.assertEqual(tick_sample[-8:],
                         [0x385F, 0x384F, 0x383F, 0x382F,
                          0x381F, 0x380F, 0x2F00, rom.RETS])
        tick_commit = rom.program_source_words(
            rom.APPLICATION_STATE_TICK_COMMIT_OVERLAY_SOURCE,
            rom.APPLICATION_STATE_TICK_COMMIT_OVERLAY_SIZE,
        )
        self.assertEqual(tick_commit[:4], [0x2E02, 0x58F1, 0xBD33, 0x5CB2])
        self.assertEqual(tick_commit[-3:], [0x381F, 0x2F00, rom.RETS])

        catalogue = rom.program_source_words(
            rom.APPLICATION_MENU_CATALOG_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_CATALOG_OVERLAY_SIZE,
        )
        self.assertEqual(catalogue[:2], [0x2E25, 0x58F2])
        self.assertEqual(catalogue[0x5C0 // 2:0x5C0 // 2 + 5], [
            0x0033, 0x6D5C, 0x8000, 0x0006, 0x0000,
        ])
        wrapper = rom.program_source_words(
            rom.APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_EVENT_WRAPPER_OVERLAY_SIZE,
        )
        registry = rom.program_source_words(
            rom.APPLICATION_REGISTRY_OVERLAY_SOURCE,
            rom.APPLICATION_REGISTRY_OVERLAY_SIZE,
        )
        self.assertEqual(registry[:4], [
            0x0100, 0xFF00, 0x0028, 0xEEE8,
        ])
        self.assertEqual(registry[-4:], [
            0x2000, 0xFF00, 0x0016, 0xA20A,
        ])
        lookup = rom.program_source_words(
            rom.APPLICATION_REGISTRY_LOOKUP_OVERLAY_SOURCE,
            rom.APPLICATION_REGISTRY_LOOKUP_OVERLAY_SIZE,
        )
        self.assertEqual(lookup[:4], [0x2E07, 0x58F1, 0x58F2, 0x58F3])
        self.assertIn(
            [0x68F5, 0x0514, 0x68F4, 0x002A],
            [lookup[index:index + 4]
             for index in range(len(lookup) - 3)],
        )
        self.assertEqual(
            lookup[-7:],
            [0x385F, 0x384F, 0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        unaligned_u16 = rom.program_source_words(
            rom.APPLICATION_UNALIGNED_U16_OVERLAY_SOURCE,
            rom.APPLICATION_UNALIGNED_U16_OVERLAY_SIZE,
        )
        self.assertEqual(unaligned_u16[:4],
                         [0x2E01, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(unaligned_u16[-5:],
                         [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS])
        text_input = rom.program_source_words(
            rom.APPLICATION_MENU_TEXT_INPUT_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_TEXT_INPUT_OVERLAY_SIZE,
        )
        self.assertEqual(text_input[:5],
                         [0x2E01, 0x58F1, 0x58F2, 0x58F3, 0x58F4])
        self.assertEqual(text_input[-5:],
                         [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS])
        ui_adapter = rom.program_source_words(
            rom.APPLICATION_MENU_UI_ADAPTER_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_UI_ADAPTER_OVERLAY_SIZE,
        )
        self.assertEqual(ui_adapter[:4],
                         [0x2E07, 0x58F1, 0x780B, 0x0010])
        self.assertEqual(ui_adapter[-3:], [0x381F, 0x2F00, rom.RETS])
        menu_position = rom.program_source_words(
            rom.APPLICATION_MENU_POSITION_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_POSITION_OVERLAY_SIZE,
        )
        self.assertEqual(menu_position[:4],
                         [0x2E08, 0x58F2, 0x58F3, 0x4810])
        self.assertEqual(menu_position[-4:],
                         [0x383F, 0x382F, 0x2F00, rom.RETS])
        menu_coordinate = rom.program_source_words(
            rom.APPLICATION_MENU_COORDINATE_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_COORDINATE_OVERLAY_SIZE,
        )
        self.assertEqual(menu_coordinate[:4],
                         [0x2E06, 0x58F2, 0x58F3, 0x4810])
        self.assertEqual(menu_coordinate[-4:],
                         [0x383F, 0x382F, 0x2F00, rom.RETS])
        menu_render = rom.program_source_words(
            rom.APPLICATION_MENU_RENDER_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RENDER_OVERLAY_SIZE,
        )
        self.assertEqual(menu_render[:5],
                         [0x2E38, 0x58F1, 0x58F2, 0x58F3, 0x780B])
        self.assertEqual(menu_render[-5:],
                         [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS])
        resource_format = rom.program_source_words(
            rom.APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RESOURCE_FORMAT_OVERLAY_SIZE,
        )
        self.assertEqual(resource_format[:5],
                         [0x2E03, 0x58F0, 0x58F1, 0x780B, 0x0006])
        self.assertEqual(resource_format[-4:],
                         [0x381F, 0x380F, 0x2F00, rom.RETS])
        resource_bind = rom.program_source_words(
            rom.APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RESOURCE_BIND_OVERLAY_SIZE,
        )
        self.assertEqual(resource_bind[:7],
                         [0x2E04, 0x58F0, 0x58F1, 0x58F2,
                          0x58F3, 0x58F4, 0x58F5])
        self.assertEqual(
            resource_bind[-8:],
            [0x385F, 0x384F, 0x383F, 0x382F,
             0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        result_attach = rom.program_source_words(
            rom.APPLICATION_MENU_RESULT_ATTACH_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RESULT_ATTACH_OVERLAY_SIZE,
        )
        self.assertEqual(result_attach[:4],
                         [0x2E02, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(
            result_attach[-8:],
            [0x1A12, 0x0A13, 0x4801, 0x383F,
             0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        result_list = rom.program_source_words(
            rom.APPLICATION_MENU_RESULT_LIST_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RESULT_LIST_OVERLAY_SIZE,
        )
        self.assertEqual(result_list[:4],
                         [0x2E12, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(
            result_list[-8:],
            [0x50F2, 0x780B, 0xFFE4, 0x383F,
             0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        result_process = rom.program_source_words(
            rom.APPLICATION_MENU_RESULT_PROCESS_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RESULT_PROCESS_OVERLAY_SIZE,
        )
        self.assertEqual(result_process[:5],
                         [0x2E01, 0x58F0, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(
            result_process[-8:],
            [0xBD31, 0x4BAC, 0x383F, 0x382F,
             0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        page_populate = rom.program_source_words(
            rom.APPLICATION_MENU_PAGE_POPULATE_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_PAGE_POPULATE_OVERLAY_SIZE,
        )
        self.assertEqual(page_populate[:7],
                         [0x2E07, 0x58F0, 0x58F1, 0x58F2,
                          0x58F3, 0x58F6, 0x58F7])
        self.assertEqual(
            page_populate[-8:],
            [0x387F, 0x386F, 0x383F, 0x382F,
             0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        text_expand = rom.program_source_words(
            rom.APPLICATION_MENU_TEXT_EXPAND_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_TEXT_EXPAND_OVERLAY_SIZE,
        )
        self.assertEqual(text_expand[:7],
                         [0x2E0C, 0x58F0, 0x58F1, 0x58F2,
                          0x58F3, 0x58F6, 0x58F7])
        self.assertEqual(
            text_expand[-8:],
            [0x387F, 0x386F, 0x383F, 0x382F,
             0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        resource_bind_wrapper = rom.program_source_words(
            rom.APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SIZE,
        )
        self.assertEqual(resource_bind_wrapper[:4],
                         [0x2E00, 0x780B, 0x0008, 0x58F0])
        self.assertEqual(resource_bind_wrapper[-3:],
                         [0x50F4, 0x2F00, rom.RETS])
        embedded_resource_bind_wrapper = rom.embed_program_overlay_words(
            rom.APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_DESTINATION,
            rom.APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RESOURCE_BIND_WRAPPER_OVERLAY_SIZE,
        )
        self.assertIn(
            embedded_resource_bind_wrapper,
            [installer[index:index + len(embedded_resource_bind_wrapper)]
             for index in range(
                 len(installer) - len(embedded_resource_bind_wrapper) + 1
             )],
        )
        resource_index = rom.program_source_words(
            rom.APPLICATION_RESOURCE_INDEX_OVERLAY_SOURCE,
            rom.APPLICATION_RESOURCE_INDEX_OVERLAY_SIZE,
        )
        self.assertEqual(resource_index[:5],
                         [0x2E09, 0x58F1, 0x58F2, 0x58F3, 0x58F4])
        self.assertEqual(
            resource_index[-9:],
            [0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
             0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        resource_index_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_RESOURCE_INDEX_OVERLAY_DESTINATION,
            rom.APPLICATION_RESOURCE_INDEX_OVERLAY_SOURCE,
            rom.APPLICATION_RESOURCE_INDEX_OVERLAY_SIZE,
        )
        extra_installer = rom.application_region_extra_installer_words()
        self.assertIn(
            resource_index_copy,
            [extra_installer[index:index + len(resource_index_copy)]
             for index in range(
                 len(extra_installer) - len(resource_index_copy) + 1
             )],
        )
        resource_decoder = rom.program_source_words(
            rom.APPLICATION_MENU_RESOURCE_DECODER_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_RESOURCE_DECODER_OVERLAY_SIZE,
        )
        self.assertEqual(resource_decoder[:5],
                         [0x2E35, 0x58F0, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(
            resource_decoder[-10:],
            [0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
             0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        decoder_installer = (
            rom.application_menu_resource_decoder_installer_words()
        )
        self.assertEqual(decoder_installer[-1], rom.RETS)
        self.assertEqual(
            len(decoder_installer),
            3 + 2 * rom.APPLICATION_MENU_RESOURCE_DECODER_OVERLAY_SIZE,
        )
        power_state = rom.program_source_words(
            rom.APPLICATION_MENU_POWER_STATE_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_POWER_STATE_OVERLAY_SIZE,
        )
        self.assertEqual(power_state[:6],
                         [0x2E1E, 0x58F1, 0x6810, 0x00A2,
                          0x88F1, 0x2A76])
        self.assertEqual(power_state[-3:], [0x381F, 0x2F00, rom.RETS])
        generic_menu = rom.program_source_words(
            rom.APPLICATION_GENERIC_MENU_OVERLAY_SOURCE,
            rom.APPLICATION_GENERIC_MENU_OVERLAY_SIZE,
        )
        self.assertEqual(generic_menu[:2], [0x2E01, 0x58F1])
        self.assertIn([0xBD2A, 0x322A], [
            generic_menu[index:index + 2]
            for index in range(len(generic_menu) - 1)
        ])
        self.assertIn([0xBD31, 0x138C], [
            generic_menu[index:index + 2]
            for index in range(len(generic_menu) - 1)
        ])
        self.assertEqual(generic_menu[-3:], [0x381F, 0x2F00, rom.RETS])
        context_gate = rom.program_source_words(
            rom.APPLICATION_CONTEXT_GATE_OVERLAY_SOURCE,
            rom.APPLICATION_CONTEXT_GATE_OVERLAY_SIZE,
        )
        self.assertEqual(context_gate[:4],
                         [0x2E02, 0x58F1, 0x58F2, 0x58F3])
        self.assertIn([0xBD2C, 0xC07E], [
            context_gate[index:index + 2]
            for index in range(len(context_gate) - 1)
        ])
        self.assertEqual(context_gate[-5:],
                         [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS])
        record_xor = rom.program_source_words(
            rom.APPLICATION_RECORD_XOR_OVERLAY_SOURCE,
            rom.APPLICATION_RECORD_XOR_OVERLAY_SIZE,
        )
        self.assertEqual(record_xor[:5],
                         [0x2E03, 0x58F0, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(record_xor[-6:],
                         [0x383F, 0x382F, 0x381F, 0x380F,
                          0x2F00, rom.RETS])
        table_build = rom.program_source_words(
            rom.APPLICATION_MENU_TABLE_BUILD_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_TABLE_BUILD_OVERLAY_SIZE,
        )
        self.assertEqual(table_build[:5],
                         [0x2E07, 0x58F1, 0x58F2, 0x58F3, 0x58F4])
        for call in ([0xBD32, 0xAF98], [0xBD32, 0x6F7C],
                     [0xBD32, 0x125C]):
            self.assertIn(call, [
                table_build[index:index + 2]
                for index in range(len(table_build) - 1)
            ])
        self.assertIn([0xBD18, 0x9A58], [
            wrapper[index:index + 2]
            for index in range(len(wrapper) - 1)
        ])
        self.assertEqual(wrapper[-4:], [0x381F, 0x380F, 0x2F00, rom.RETS])

    def test_menu_glyph_dispatch_keeps_exact_chinese_font_path(self) -> None:
        text_stream = rom.program_source_words(
            rom.APPLICATION_MENU_TEXT_STREAM_OVERLAY_SOURCE,
            rom.APPLICATION_MENU_TEXT_STREAM_OVERLAY_SIZE,
        )
        glyph_dispatch = rom.program_source_words(
            rom.APPLICATION_RESULT_GLYPH_RENDER_ALT_OVERLAY_SOURCE,
            rom.APPLICATION_RESULT_GLYPH_RENDER_ALT_OVERLAY_SIZE,
        )
        installer = rom.application_region_extra_installer_words()
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_RESULT_GLYPH_RENDER_ALT_OVERLAY_DESTINATION,
            rom.APPLICATION_RESULT_GLYPH_RENDER_ALT_OVERLAY_SOURCE,
            rom.APPLICATION_RESULT_GLYPH_RENDER_ALT_OVERLAY_SIZE,
        )

        self.assertEqual(
            sum(text_stream[index:index + 2] == [0xBD32, 0x7B42]
                for index in range(len(text_stream) - 1)),
            2,
        )
        self.assertEqual(glyph_dispatch[:3], [0x2E00, 0x58F0, 0x58F1])
        self.assertIn(
            [0xBD17, 0x9244],
            [glyph_dispatch[index:index + 2]
             for index in range(len(glyph_dispatch) - 1)],
        )
        self.assertIn(
            [0xBD28, 0xFD38],
            [glyph_dispatch[index:index + 2]
             for index in range(len(glyph_dispatch) - 1)],
        )
        self.assertEqual(glyph_dispatch[-3:], [0x380F, 0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )

    def test_resident_application_state_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_APPLICATION_STATE_SOURCE,
            rom.RESIDENT_APPLICATION_STATE_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_APPLICATION_STATE_ADDRESS,
                     len(source)),
            source,
        )
        self.assertEqual(source[:4], [0x2E05, 0x58F1, 0x58F3, 0xBD28])
        self.assertEqual(source[-4:],
                         [0x383F, 0x381F, 0x2F00, rom.RETS])
        self.assertEqual(info["resident_application_state"]["bytes"],
                         rom.RESIDENT_APPLICATION_STATE_SIZE)

    def test_resident_event_packet_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_EVENT_PACKET_SOURCE,
            rom.RESIDENT_EVENT_PACKET_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_EVENT_PACKET_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(source[:4], [0x2E14, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(source[-5:],
                         [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS])
        self.assertEqual(info["resident_event_packet_1c_f28a"]["bytes"],
                         rom.RESIDENT_EVENT_PACKET_SIZE)

    def test_resident_event_state_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_EVENT_STATE_SOURCE,
            rom.RESIDENT_EVENT_STATE_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_EVENT_STATE_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(source[:7],
                         [0x2E08, 0x58F0, 0x58F1, 0x58F2,
                          0x58F3, 0x58F6, 0x58F7])
        self.assertEqual(source[-8:],
                         [0x387F, 0x386F, 0x383F, 0x382F,
                          0x381F, 0x380F, 0x2F00, rom.RETS])
        self.assertEqual(info["resident_event_state_19_f8b8"]["bytes"],
                         rom.RESIDENT_EVENT_STATE_SIZE)

    def test_resident_event_render_10_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_EVENT_RENDER_10_SOURCE,
            rom.RESIDENT_EVENT_RENDER_10_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_EVENT_RENDER_10_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(source[:6],
                         [0x2E0B, 0x58F1, 0x58F2,
                          0x58F3, 0x58F4, 0x58F5])
        self.assertEqual(source[-7:],
                         [0x385F, 0x384F, 0x383F, 0x382F,
                          0x381F, 0x2F00, rom.RETS])
        self.assertEqual(info["resident_event_render_10_5090"]["bytes"],
                         rom.RESIDENT_EVENT_RENDER_10_SIZE)

    def test_resident_state_import_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_STATE_IMPORT_SOURCE,
            rom.RESIDENT_STATE_IMPORT_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_STATE_IMPORT_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(source[:5],
                         [0x2E07, 0x58F2, 0x58F3, 0x780B, 0x0006])
        self.assertEqual(source[-4:],
                         [0x383F, 0x382F, 0x2F00, rom.RETS])
        self.assertEqual(info["resident_state_import"]["bytes"],
                         rom.RESIDENT_STATE_IMPORT_SIZE)

    def test_resident_service_0f0000_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_SERVICE_0F0000_SOURCE,
            rom.RESIDENT_SERVICE_0F0000_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_SERVICE_0F0000_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(
            source[:9],
            [
                0x2E46, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
                0x58F4, 0x58F5, 0x58F6, 0x58F7,
            ],
        )
        self.assertEqual(
            source[-10:],
            [
                0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
                0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
            ],
        )
        self.assertEqual(
            rom.RESIDENT_SERVICE_0F0000_ADDRESS +
            rom.RESIDENT_SERVICE_0F0000_SIZE,
            rom.RESIDENT_ROOT_EVENT_HANDLER_ADDRESS,
        )
        entry = info["resident_service_0f_0000"]
        self.assertEqual(entry["destination"], "0F:0000")
        self.assertEqual(entry["source"], "2C:0000")
        self.assertEqual(entry["bytes"], 0x2094)
        self.assertEqual(entry["reachable_instructions"], 2234)
        self.assertEqual(entry["call_instructions"], 174)
        self.assertEqual(entry["unknown_frontiers"], 0)

    def test_resident_root_event_handler_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_ROOT_EVENT_HANDLER_SOURCE,
            rom.RESIDENT_ROOT_EVENT_HANDLER_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image, rom.RESIDENT_ROOT_EVENT_HANDLER_ADDRESS, len(source),
            ),
            source,
        )
        self.assertEqual(
            source[:9],
            [0x2E0C, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
             0x58F4, 0x58F5, 0x58F6, 0x58F7],
        )
        self.assertEqual(
            source[-10:],
            [0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
             0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_ROOT_EVENT_TABLE_80_ADDRESS,
                rom.RESIDENT_ROOT_EVENT_TABLE_80_SIZE // 2,
            ),
            [0x21A4, 0x249E, 0x2984, 0x31C2,
             0x409E, 0x409E, 0x3906],
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_ROOT_EVENT_TABLE_8E_ADDRESS,
                rom.RESIDENT_ROOT_EVENT_TABLE_8E_SIZE // 2,
            ),
            [0x3E96, 0x409E, 0x409E, 0x409E,
             0x3906, 0x409E, 0x2984, 0x31C2],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.RESIDENT_ROOT_EVENT_TABLE_80_SOURCE,
                rom.RESIDENT_ROOT_EVENT_TABLE_80_SIZE,
            ),
            [0x21A4, 0x249E, 0x2984, 0x31C2,
             0x409E, 0x409E, 0x3906],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.RESIDENT_ROOT_EVENT_TABLE_8E_SOURCE,
                rom.RESIDENT_ROOT_EVENT_TABLE_8E_SIZE,
            ),
            [0x3E96, 0x409E, 0x409E, 0x409E,
             0x3906, 0x409E, 0x2984, 0x31C2],
        )
        self.assertEqual(info["resident_root_event_handler_0f_2094"], {
            "destination": "0F:2094",
            "source": "2C:2094",
            "bytes": rom.RESIDENT_ROOT_EVENT_HANDLER_SIZE,
            "pointer_source": "50:1436",
            "status": "exact same-PC resident root-event handler",
        })

    def test_resident_main_action_event_table_is_exact_harvard_data(self) -> None:
        image = rom.build_image()
        expected = [
            0x0E32, 0x0F0A, 0x0DBA, 0x0DF4, 0x0FFE, 0x1100,
            0x0A86, 0x120E, 0x120E, 0x120E, 0x120E, 0x120E,
            0x120E, 0x0A60, 0x12DE, 0x120E, 0x0A86,
        ]

        self.assertEqual(
            rom.program_source_words(
                rom.RESIDENT_MAIN_ACTION_EVENT_TABLE_SOURCE,
                rom.RESIDENT_MAIN_ACTION_EVENT_TABLE_SIZE,
            ),
            expected,
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_MAIN_ACTION_EVENT_TABLE_ADDRESS,
                len(expected),
            ),
            expected,
        )
        self.assertEqual(
            rom.manifest(image)["resident_main_action_event_table_13_0a3e"],
            {
                "destination": "13:0A3E",
                "source": "30:0A3E",
                "bytes": 0x22,
                "events": "80..90",
                "status": "exact linked Harvard data dispatch table",
            },
        )

    def test_resident_storage_init_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_STORAGE_INIT_SOURCE,
            rom.RESIDENT_STORAGE_INIT_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_STORAGE_INIT_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(
            source[:12],
            [
                0x2E08, 0x58F1, 0x58F2, 0x58F3,
                0x58F4, 0x58F5, 0x58F6, 0x58F7,
                0xBD02, 0xBAC4, 0xBD02, 0xBAC8,
            ],
        )
        self.assertEqual(
            source[-14:],
            [
                0xBD32, 0xAFEE, 0xBD32, 0xFA40,
                0x4800, 0x387F, 0x386F, 0x385F,
                0x384F, 0x383F, 0x382F, 0x381F,
                0x2F00, rom.RETS,
            ],
        )
        self.assertEqual(
            info["resident_storage_init"]["bytes"],
            rom.RESIDENT_STORAGE_INIT_SIZE,
        )

    def test_resident_application_config_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_APPLICATION_CONFIG_SOURCE,
            rom.RESIDENT_APPLICATION_CONFIG_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_APPLICATION_CONFIG_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(source[:4], [0x2E20, 0x58F1, 0x4912, 0x6810])
        self.assertEqual(source[-4:], [0x1901, 0x381F, 0x2F00, rom.RETS])
        for dependency in (
            [0xBD1A, 0x4B9C],
            [0xBD1D, 0x49A2],
            [0xBD13, 0xDA56],
            [0xBD19, 0xA154],
        ):
            self.assertIn(
                dependency,
                [source[index:index + 2] for index in range(len(source) - 1)],
            )
        self.assertEqual(
            info["resident_application_config"]["bytes"],
            rom.RESIDENT_APPLICATION_CONFIG_SIZE,
        )

    def test_resident_record_status_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_RECORD_STATUS_SOURCE,
            rom.RESIDENT_RECORD_STATUS_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            rom.RESIDENT_RESULT_TYPE_QUERY_ADDRESS
            + rom.RESIDENT_RESULT_TYPE_QUERY_SIZE,
            rom.RESIDENT_RECORD_STATUS_ADDRESS,
        )
        self.assertEqual(
            words_at(image, rom.RESIDENT_RECORD_STATUS_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(
            source[:8],
            [
                0x2E18, 0x58F1, 0x58F2, 0x58F3,
                0x58F4, 0x58F5, 0x58F6, 0x58F7,
            ],
        )
        self.assertIn(0x4801, source)
        self.assertIn(0x4804, source)
        self.assertIn(0x4805, source)
        self.assertEqual(
            source[-9:],
            [
                0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
                0x382F, 0x381F, 0x2F00, rom.RETS,
            ],
        )
        self.assertEqual(
            info["resident_record_status"]["bytes"],
            rom.RESIDENT_RECORD_STATUS_SIZE,
        )

    def test_resident_object_table_update_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_OBJECT_TABLE_UPDATE_SOURCE,
            rom.RESIDENT_OBJECT_TABLE_UPDATE_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_OBJECT_TABLE_UPDATE_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(source[:7], [
            0x2E03, 0x58F0, 0x58F1, 0x58F2,
            0x58F3, 0x58F4, 0x58F5,
        ])
        self.assertEqual(source[-8:], [
            0x385F, 0x384F, 0x383F, 0x382F,
            0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertNotIn(
            0xBD00,
            [word & 0xFF00 for word in source],
        )
        self.assertEqual(
            info["resident_object_table_update"]["bytes"],
            rom.RESIDENT_OBJECT_TABLE_UPDATE_SIZE,
        )

    def test_resident_configuration_variants_are_exact_guest_code(self) -> None:
        image = rom.build_image()
        info = rom.manifest(image)

        self.assertEqual(
            [(address, source, size) for address, source, size, _name
             in rom.RESIDENT_CONFIGURATION_VARIANTS],
            [
                (0x1A4B9C, 0x374B9C, 0x095A),
                (0x1D49A2, 0x3A49A2, 0x0742),
                (0x13DA56, 0x30DA56, 0x1140),
                (0x19A154, 0x36A154, 0x09D4),
            ],
        )
        for address, source_address, size, _name in (
                rom.RESIDENT_CONFIGURATION_VARIANTS):
            source = rom.program_source_words(source_address, size)
            installed = rom.resident_configuration_variant_words(
                address, source_address, size
            )
            self.assertEqual(
                words_at(image, address, len(installed)),
                installed,
            )
            self.assertEqual(source[0] >> 8, 0x2E)
            self.assertEqual(source[-1], rom.RETS)
            patches = [
                relocation
                for relocation in rom.SYSTEM_FLAG_QUERY_CALL_RELOCATIONS
                if source_address <= relocation[0] < source_address + size
            ]
            if not patches:
                self.assertEqual(installed, source)
                continue
            self.assertEqual(source_address, 0x36A154)
            for call_source, old_target, new_target in patches:
                index = (call_source - source_address) // 2
                self.assertEqual(
                    source[index:index + 2],
                    [0xBD00 | (old_target >> 16), old_target & 0xFFFF],
                )
                self.assertEqual(
                    installed[index:index + 2],
                    [0xBD00 | (new_target >> 16), new_target & 0xFFFF],
                )
        self.assertEqual(
            [item["bytes"] for item in info["resident_configuration_variants"]],
            [0x095A, 0x0742, 0x1140, 0x09D4],
        )

    def test_resident_storage_metadata_init_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_STORAGE_METADATA_INIT_SOURCE,
            rom.RESIDENT_STORAGE_METADATA_INIT_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_STORAGE_METADATA_INIT_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(
            source[:8],
            [
                0x2E11, 0x58F1, 0x58F2, 0x58F3,
                0x58F4, 0x58F5, 0x58F6, 0x58F7,
            ],
        )
        self.assertEqual(
            source[-10:],
            [
                0x4800, 0x387F, 0x386F, 0x385F, 0x384F,
                0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS,
            ],
        )
        self.assertEqual(
            info["resident_storage_metadata_init"]["bytes"],
            rom.RESIDENT_STORAGE_METADATA_INIT_SIZE,
        )

    def test_resident_handler_1f12b4_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_HANDLER_1F12B4_SOURCE,
            rom.RESIDENT_HANDLER_1F12B4_SIZE,
        )
        installed = rom.retarget_program_source_calls(
            rom.RESIDENT_HANDLER_1F12B4_SOURCE,
            rom.RESIDENT_HANDLER_1F12B4_SIZE,
            (
                (rom.RESIDENT_HANDLER_1F12B4_BITMAP_DECODE_CALL_SOURCE,
                 rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_LINKED_DESTINATION,
                 rom.APPLICATION_NPE_LOADER_BITMAP_DECODE_OVERLAY_DESTINATION),
                (0x3C131A,
                 rom.APPLICATION_NPE_BITMAP_CONTEXT_LINKED_DESTINATION,
                 rom.APPLICATION_NPE_BITMAP_CONTEXT_OVERLAY_DESTINATION),
                (0x3C150E,
                 rom.APPLICATION_NPE_BITMAP_CONTEXT_LINKED_DESTINATION,
                 rom.APPLICATION_NPE_BITMAP_CONTEXT_OVERLAY_DESTINATION),
                (0x3C15E2,
                 rom.APPLICATION_NPE_BITMAP_CONTEXT_LINKED_DESTINATION,
                 rom.APPLICATION_NPE_BITMAP_CONTEXT_OVERLAY_DESTINATION),
            ),
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_HANDLER_1F12B4_ADDRESS, len(source)),
            installed,
        )
        call_index = (
            rom.RESIDENT_HANDLER_1F12B4_BITMAP_DECODE_CALL_SOURCE -
            rom.RESIDENT_HANDLER_1F12B4_SOURCE
        ) // 2
        self.assertEqual(source[call_index:call_index + 2], [0xBD27, 0x716C])
        self.assertEqual(installed[call_index:call_index + 2], [0xBD5F, 0x716C])
        for call_source in (0x3C131A, 0x3C150E, 0x3C15E2):
            index = (call_source - rom.RESIDENT_HANDLER_1F12B4_SOURCE) // 2
            self.assertEqual(source[index:index + 2], [0xBD29, 0x8202])
            self.assertEqual(installed[index:index + 2], [0xBD5F, 0x8202])
        self.assertEqual(source[:4], [0x2E12, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(source[-5:],
                         [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS])
        self.assertEqual(info["resident_handler_1f_12b4"]["bytes"],
                         rom.RESIDENT_HANDLER_1F12B4_SIZE)

    def test_resident_application_object_mask_is_exact_closed_guest_code(
            self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_APPLICATION_OBJECT_MASK_SOURCE,
            rom.RESIDENT_APPLICATION_OBJECT_MASK_SIZE,
        )
        installed = rom.retarget_program_source_call(
            rom.RESIDENT_APPLICATION_OBJECT_MASK_SOURCE,
            rom.RESIDENT_APPLICATION_OBJECT_MASK_SIZE,
            rom.RESIDENT_APPLICATION_OBJECT_MASK_BYTE_QUERY_CALL_SOURCE,
            rom.APPLICATION_RUNTIME_BYTE_QUERY_LINKED_DESTINATION,
            rom.APPLICATION_RUNTIME_BYTE_QUERY_RESIDENT_ADDRESS,
        )
        info = rom.manifest(image)[
            "resident_application_object_mask_1f_5bfa"
        ]

        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_APPLICATION_OBJECT_MASK_ADDRESS,
                len(source),
            ),
            installed,
        )
        self.assertEqual(source[:8], [
            0x2E04, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7,
        ])
        self.assertEqual(source[-9:], [
            0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, 0x2F00, rom.RETS,
        ])
        calls = [source[index:index + 2]
                 for index in range(len(source) - 1)]
        self.assertEqual(calls.count([0xBD33, 0x5ABA]), 1)
        self.assertEqual(calls.count([0xBD33, 0x07B0]), 10)
        self.assertEqual(calls.count([0xBD33, 0x5B70]), 2)
        self.assertEqual(sum(call[0] & 0xFF00 == 0xBD00
                             for call in calls), 13)
        call_index = (
            rom.RESIDENT_APPLICATION_OBJECT_MASK_BYTE_QUERY_CALL_SOURCE
            - rom.RESIDENT_APPLICATION_OBJECT_MASK_SOURCE
        ) // 2
        self.assertEqual(source[call_index:call_index + 2], [0xBD33, 0x5ABA])
        self.assertEqual(installed[call_index:call_index + 2], [0xBD06, 0x1CF0])
        self.assertEqual(
            [index for index, pair in enumerate(zip(source, installed))
             if pair[0] != pair[1]],
            [call_index, call_index + 1],
        )
        self.assertEqual(
            rom.RESIDENT_APPLICATION_OBJECT_MASK_ADDRESS
            + (rom.RESIDENT_APPLICATION_OBJECT_MASK_BYTE_QUERY_CALL_SOURCE
               - rom.RESIDENT_APPLICATION_OBJECT_MASK_SOURCE),
            rom.RESIDENT_APPLICATION_OBJECT_MASK_BYTE_QUERY_CALL_ADDRESS,
        )

        for call_address in rom.RESIDENT_APPLICATION_OBJECT_MASK_CALL_SOURCES:
            self.assertEqual(
                rom.program_source_words(call_address - 4, 0x0A),
                [0x58F1, 0x58F0, 0xBD1F, 0x5BFA, 0x50F4],
            )
        self.assertEqual(info["argument_bytes"], 0x04)
        self.assertEqual(info["reachable_instructions"], 607)
        self.assertEqual(info["call_instructions"], 13)
        self.assertEqual(info["unknown_frontiers"], 0)
        self.assertEqual(info["overlapping_decode_targets"], 0)

    def test_application_runtime_byte_query_is_relocated_from_live_branch(
            self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.APPLICATION_RUNTIME_BYTE_QUERY_OVERLAY_SOURCE,
            rom.APPLICATION_RUNTIME_BYTE_QUERY_OVERLAY_SIZE,
        )
        flat = rom.program_source_words(
            rom.APPLICATION_RUNTIME_BYTE_QUERY_LINKED_DESTINATION,
            rom.APPLICATION_RUNTIME_BYTE_QUERY_OVERLAY_SIZE,
        )
        worker = rom.program_source_words(
            rom.RESIDENT_RECURSIVE_16_SOURCE,
            rom.RESIDENT_RECURSIVE_16_SIZE,
        )
        installer = rom.install_runtime_overlay_words()
        forbidden_same_pc_install = rom.write_program_words(
            rom.APPLICATION_RUNTIME_BYTE_QUERY_LINKED_DESTINATION,
            source,
        )
        module = rom.manifest(image)["application_runtime_byte_query_06_1cf0"]

        self.assertEqual(
            source,
            list(rom.APPLICATION_RUNTIME_BYTE_QUERY_OVERLAY_WORDS),
        )
        self.assertNotEqual(flat, source)
        self.assertEqual(source, [
            0x2E00, 0x6810, 0x00A1, 0x99F0,
            0x3886, 0x2F00, rom.RETS,
        ])
        worker_branch = (
            rom.APPLICATION_RUNTIME_BYTE_QUERY_LINKED_DESTINATION - 8
            - rom.RESIDENT_RECURSIVE_16_SOURCE
        ) // 2
        self.assertEqual(
            worker[worker_branch:worker_branch + 2],
            [0xAC0C, 0x5ABA],
        )
        self.assertEqual(
            words_at(image, rom.RESIDENT_RECURSIVE_16_ADDRESS, len(worker)),
            worker,
        )
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_RUNTIME_BYTE_QUERY_RESIDENT_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertNotIn(
            forbidden_same_pc_install,
            [installer[index:index + len(forbidden_same_pc_install)]
             for index in range(
                 len(installer) - len(forbidden_same_pc_install) + 1
             )],
        )
        self.assertLessEqual(
            rom.MENU_EVENT_DEPENDENCY_INSTALLER_ADDRESS
            + len(rom.menu_event_dependency_installer_words()) * 2,
            rom.SYSTEM_BITS_RESIDENT_ADDRESS,
        )
        self.assertEqual(
            rom.SYSTEM_BITS_RESIDENT_ADDRESS
            + len(rom.SYSTEM_BITS_OVERLAY_WORDS) * 2,
            rom.APPLICATION_RUNTIME_BYTE_QUERY_RESIDENT_ADDRESS,
        )
        self.assertLessEqual(
            rom.APPLICATION_RUNTIME_BYTE_QUERY_RESIDENT_ADDRESS
            + rom.APPLICATION_RUNTIME_BYTE_QUERY_OVERLAY_SIZE,
            rom.CLEAR_OVERLAY_ADDRESS,
        )

        program = rom.PROGRAM_SOURCE.read_bytes()
        words = [
            int.from_bytes(program[index:index + 2], "little")
            for index in range(0, len(program), 2)
        ]
        target_calls = sum(
            words[index:index + 2] == [0xBD33, 0x5ABA]
            for index in range(len(words) - 1)
        )
        source_calls = sum(
            words[index:index + 2] == [0xBD50, 0x5ABA]
            for index in range(len(words) - 1)
        )
        self.assertEqual(target_calls, 12)
        self.assertEqual(source_calls, 0)
        self.assertEqual(sum(
            words[index:index + 2] == [0xBD33, 0x52AA]
            for index in range(len(words) - 1)
        ), 0)
        self.assertEqual(sum(
            words[index:index + 2] == [0xBD16, 0x52AA]
            for index in range(len(words) - 1)
        ), 2)
        self.assertEqual(module["destination"], "06:1CF0")
        self.assertEqual(module["linked_destination"], "33:5ABA")
        self.assertEqual(module["caller_patch"], "1F:5C16")
        self.assertEqual(module["target_call_sites"], target_calls)
        self.assertEqual(module["source_call_sites"], source_calls)

    def test_resident_application_event_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_APPLICATION_EVENT_SOURCE,
            rom.RESIDENT_APPLICATION_EVENT_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_APPLICATION_EVENT_ADDRESS,
                     len(source)),
            source,
        )
        self.assertEqual(source[:7],
                         [0x2E0C, 0x58F1, 0x58F2, 0x58F3,
                          0x58F6, 0x58F7, 0x4800])
        self.assertEqual(source[-8:],
                         [0xFFF6, 0x387F, 0x386F, 0x383F,
                          0x382F, 0x381F, 0x2F00, rom.RETS])
        self.assertEqual(info["resident_application_event_1f_b496"], {
            "destination": "1F:B496",
            "source": "3C:B496",
            "bytes": rom.RESIDENT_APPLICATION_EVENT_SIZE,
            "status": "exact same-PC resident application-event dispatcher",
        })

    def test_resident_application_page_render_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_APPLICATION_PAGE_RENDER_SOURCE,
            rom.RESIDENT_APPLICATION_PAGE_RENDER_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_APPLICATION_PAGE_RENDER_ADDRESS,
                     len(source)),
            source,
        )
        self.assertEqual(
            source[:10],
            [0x2E4A, 0x58F1, 0x58F2, 0x58F3, 0x58F4,
             0x58F5, 0x58F6, 0x58F7, 0x4910, 0x6B1B],
        )
        self.assertEqual(
            source[-10:],
            [0xFFAA, 0x387F, 0x386F, 0x385F, 0x384F,
             0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        self.assertEqual(info["resident_application_page_render_18_4e62"], {
            "destination": "18:4E62",
            "source": "35:4E62",
            "bytes": rom.RESIDENT_APPLICATION_PAGE_RENDER_SIZE,
            "caller": "1A:DF80",
            "argument_bytes": 0x0A,
            "reachable_instructions": 804,
            "direct_calls": 44,
            "status": "exact same-PC resident application-page renderer",
        })
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_APPLICATION_PAGE_MODE_TABLE_ADDRESS,
                rom.RESIDENT_APPLICATION_PAGE_MODE_TABLE_SIZE // 2,
            ),
            [0x57B0, 0x57E4, 0x594E, 0x58B4, 0x584C],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.RESIDENT_APPLICATION_PAGE_MODE_TABLE_SOURCE,
                rom.RESIDENT_APPLICATION_PAGE_MODE_TABLE_SIZE,
            ),
            [0x57B0, 0x57E4, 0x594E, 0x58B4, 0x584C],
        )
        self.assertEqual(info["resident_application_page_mode_table"], {
            "destination": "18:57A6",
            "source": "35:57A6",
            "bytes": rom.RESIDENT_APPLICATION_PAGE_MODE_TABLE_SIZE,
            "targets": ["18:57B0", "18:57E4", "18:594E",
                        "18:58B4", "18:584C"],
            "status": "exact inline RET-dispatch table; Harvard data alias",
        })

    def test_application_page_raster_is_exact_embedded_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.APPLICATION_PAGE_RASTER_OVERLAY_SOURCE,
            rom.APPLICATION_PAGE_RASTER_OVERLAY_SIZE,
        )
        installer = rom.application_page_raster_installer_words()
        expected_installer = rom.embed_program_overlay_words(
            rom.APPLICATION_PAGE_RASTER_OVERLAY_DESTINATION,
            rom.APPLICATION_PAGE_RASTER_OVERLAY_SOURCE,
            rom.APPLICATION_PAGE_RASTER_OVERLAY_SIZE,
        ) + [rom.RETS]

        self.assertEqual(source[:6],
                         [0x2E09, 0x58F1, 0x58F2,
                          0x58F3, 0x58F6, 0x58F7])
        self.assertEqual(source[-8:],
                         [0x4801, 0x387F, 0x386F, 0x383F,
                          0x382F, 0x381F, 0x2F00, rom.RETS])
        self.assertEqual(installer, expected_installer)
        self.assertLessEqual(
            rom.APPLICATION_PAGE_RASTER_INSTALLER_ADDRESS +
            len(installer) * 2,
            0x1ADEAA,
        )
        self.assertEqual(
            rom.application_region_extra_installer_words()[-3:],
            [0xBD1A, 0xCC80, rom.RETS],
        )
        modules = {
            item["destination"]: item
            for item in rom.manifest(image)["nested_system_overlays"]
        }
        self.assertEqual(modules["24:1F02"], {
            "destination": "24:1F02",
            "source": "41:1F02",
            "bytes": rom.APPLICATION_PAGE_RASTER_OVERLAY_SIZE,
            "caller": "18:5178",
            "arguments": 6,
            "reachable_instructions": 398,
            "direct_calls": 0,
            "status": "exact same-PC call-free page raster copier",
        })

    def test_application_compare_mode_table_is_exact_guest_data(self) -> None:
        image = rom.build_image()
        expected = [0xE040, 0xE6CE, 0xE6B6, 0xE6C6]
        info = rom.manifest(image)

        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_COMPARE_MODE_TABLE_ADDRESS,
                rom.APPLICATION_COMPARE_MODE_TABLE_SIZE // 2,
            ),
            expected,
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_COMPARE_MODE_TABLE_SOURCE,
                rom.APPLICATION_COMPARE_MODE_TABLE_SIZE,
            ),
            expected,
        )
        self.assertEqual(info["resident_application_compare_mode_table"], {
            "destination": "1A:E038",
            "source": "37:E038",
            "bytes": rom.APPLICATION_COMPARE_MODE_TABLE_SIZE,
            "targets": ["1A:E040", "1A:E6CE", "1A:E6B6", "1A:E6C6"],
            "status": "exact inline RET-dispatch table; Harvard data alias",
        })

    def test_application_compare_inner_tables_are_exact_guest_data(self) -> None:
        image = rom.build_image()
        info = rom.manifest(image)

        self.assertEqual(rom.APPLICATION_REGION_EXTRA_INSTALLER_ADDRESS >> 16,
                         0x0A)

        expected_tables = []
        for destination, source, targets in rom.APPLICATION_COMPARE_INNER_TABLES:
            self.assertEqual(
                rom.program_source_words(
                    source,
                    rom.APPLICATION_COMPARE_INNER_TABLE_SIZE,
                ),
                list(targets),
            )
            self.assertEqual(
                words_at(
                    image,
                    destination,
                    rom.APPLICATION_COMPARE_INNER_TABLE_SIZE // 2,
                ),
                list(targets),
            )
            expected_tables.append({
                "destination": f"{destination >> 16:02X}:{destination & 0xFFFF:04X}",
                "source": f"{source >> 16:02X}:{source & 0xFFFF:04X}",
                "bytes": rom.APPLICATION_COMPARE_INNER_TABLE_SIZE,
                "targets": [f"1A:{target:04X}" for target in targets],
                "status": "exact inline RET-dispatch table; Harvard data alias",
            })
        self.assertEqual(
            info["resident_application_compare_inner_tables"],
            expected_tables,
        )

    def test_resident_application_worker_1a0000_is_complete_exact_function(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_APPLICATION_WORKER_1A0000_SOURCE,
            rom.RESIDENT_APPLICATION_WORKER_1A0000_SIZE,
        )

        self.assertEqual(source[:2], [0x2E04, 0x58F3])
        self.assertEqual(source[-3:], [0x383F, 0x2F00, rom.RETS])
        self.assertEqual(
            rom.program_source_words(
                rom.RESIDENT_APPLICATION_WORKER_1A0000_CALL_SOURCE,
                4,
            ),
            [0xBD1A, 0x0000],
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_APPLICATION_WORKER_1A0000_ADDRESS,
                rom.RESIDENT_APPLICATION_WORKER_1A0000_SIZE // 2,
            ),
            source,
        )
        self.assertEqual(
            rom.manifest(image)["resident_application_worker_1a_0000"],
            {
                "destination": "1A:0000",
                "source": "37:0000",
                "bytes": rom.RESIDENT_APPLICATION_WORKER_1A0000_SIZE,
                "caller": "49:6ED6 -> 1A:0000",
                "argument_bytes": 0x0C,
                "status": "exact independent resident function; complete LINK/RETS body",
            },
        )

    def test_dictionary_foreground_state4e_is_exact_guest_code(self) -> None:
        wrapper = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_STATE4E_WRAPPER_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_STATE4E_WRAPPER_OVERLAY_SIZE,
        )
        body = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_STATE4E_ROM_SOURCE,
            rom.APPLICATION_FOREGROUND_STATE4E_ROM_SIZE,
        )
        body_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FOREGROUND_STATE4E_ROM_DESTINATION,
            rom.APPLICATION_FOREGROUND_STATE4E_ROM_SOURCE,
            rom.APPLICATION_FOREGROUND_STATE4E_ROM_SIZE,
        )
        wrapper_embed = rom.embed_program_overlay_words(
            rom.APPLICATION_FOREGROUND_STATE4E_WRAPPER_OVERLAY_DESTINATION,
            rom.APPLICATION_FOREGROUND_STATE4E_WRAPPER_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_STATE4E_WRAPPER_OVERLAY_SIZE,
        )
        ready_leaf = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_READY_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_READY_OVERLAY_SIZE,
        )
        ready_leaf_embed = rom.embed_program_overlay_words(
            rom.APPLICATION_FOREGROUND_READY_OVERLAY_DESTINATION,
            rom.APPLICATION_FOREGROUND_READY_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_READY_OVERLAY_SIZE,
        )
        installer = rom.application_foreground_state4e_installer_words()
        late_installer = rom.rom01_application_loader_words()
        parent = rom.application_foreground_state_handler_installer_words()
        routines = rom.make_routines()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(wrapper, [
            0x2E00, 0x58F0, 0x58F1, 0x4810, 0x4800, 0x58F1, 0x58F0,
            0xBD0D, 0x2F30, 0x50F4, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(body[:9], [
            0x2E16, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7,
        ])
        self.assertEqual(body[-10:], [
            0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        calls = [
            body[index:index + 2]
            for index in range(len(body) - 1)
            if (body[index] & 0xFF00) == 0xBD00
        ]
        self.assertEqual(calls.count([0xBD2A, 0xECE0]), 3)
        self.assertEqual(calls.count([0xBD2A, 0x20C2]), 1)
        self.assertEqual(calls.count([0xBD33, 0x6BE2]), 2)
        self.assertEqual(ready_leaf, [0x2E00, 0x4801, 0x2F00, rom.RETS])
        self.assertIn(
            body_copy,
            [installer[index:index + len(body_copy)]
             for index in range(len(installer) - len(body_copy) + 1)],
        )
        self.assertIn(
            wrapper_embed,
            [
                late_installer[index:index + len(wrapper_embed)]
                for index in range(
                    len(late_installer) - len(wrapper_embed) + 1
                )
            ],
        )
        self.assertIn(
            ready_leaf_embed,
            [installer[index:index + len(ready_leaf_embed)]
             for index in range(
                 len(installer) - len(ready_leaf_embed) + 1
             )],
        )
        for destination, _source in (
                rom.APPLICATION_FOREGROUND_STATE4E_READY_CALLS):
            patch = rom.write_program_words(
                destination,
                (0xBD00 | (
                    rom.APPLICATION_FOREGROUND_READY_OVERLAY_DESTINATION >> 16
                 ),
                 rom.APPLICATION_FOREGROUND_READY_OVERLAY_DESTINATION & 0xFFFF),
            )
            self.assertIn(
                patch,
                [installer[index:index + len(patch)]
                 for index in range(len(installer) - len(patch) + 1)],
            )
        self.assertEqual(late_installer[-1], rom.RETS)
        self.assertEqual(installer[-1], rom.RETS)
        self.assertIn(
            [0xBD00 | (
                 rom.APPLICATION_FOREGROUND_STATE4E_INSTALLER_ADDRESS >> 16
             ),
             rom.APPLICATION_FOREGROUND_STATE4E_INSTALLER_ADDRESS & 0xFFFF],
            [parent[index:index + 2]
             for index in range(len(parent) - 1)],
        )
        self.assertEqual(
            routines[rom.APPLICATION_FOREGROUND_STATE4E_INSTALLER_ADDRESS],
            ("application_foreground_state4e_overlay_installer", installer),
        )
        self.assertLessEqual(
            rom.APPLICATION_FOREGROUND_STATE4E_INSTALLER_ADDRESS
            + len(installer) * 2,
            0x1A8000,
        )
        self.assertEqual(
            modules["33:44AE"]["bytes"],
            rom.APPLICATION_FOREGROUND_STATE4E_WRAPPER_OVERLAY_SIZE,
        )
        self.assertEqual(
            modules["0D:2F30"]["bytes"],
            rom.APPLICATION_FOREGROUND_STATE4E_ROM_SIZE,
        )
        self.assertEqual(
            modules["5F:6BE2"]["source"],
            "50:6BE2",
        )
        self.assertEqual(
            modules["5F:6BE2"]["bytes"],
            rom.APPLICATION_FOREGROUND_READY_OVERLAY_SIZE,
        )

    def test_resident_npe_region_move_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_NPE_REGION_MOVE_SOURCE,
            rom.RESIDENT_NPE_REGION_MOVE_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_NPE_REGION_MOVE_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(
            source[:10],
            [
                0x2E0A, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
                0x58F4, 0x58F5, 0x58F6, 0x58F7, 0x58F8,
            ],
        )
        self.assertEqual(
            source[-8:],
            [
                0x384F, 0x383F, 0x382F, 0x381F,
                0x380F, 0x2F00, 0x3F00, rom.RETS,
            ],
        )
        self.assertEqual(info["resident_npe_region_move_0d_78d2"], {
            "destination": "0D:78D2",
            "source": "2A:78D2",
            "bytes": rom.RESIDENT_NPE_REGION_MOVE_SIZE,
            "caller": "03:4268; loaded NPE redraw path",
            "argument_bytes": 0x0C,
            "reachable_instructions": 210,
            "direct_calls": 0,
            "status": "exact same-PC resident NPE pixel-region move/copy",
        })

    def test_resident_packed_nibble_blit_family_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        mode0 = rom.program_source_words(
            rom.RESIDENT_PACKED_NIBBLE_BLIT_MODE0_SOURCE,
            rom.RESIDENT_PACKED_NIBBLE_BLIT_MODE0_SIZE,
        )
        mode1 = rom.program_source_words(
            rom.RESIDENT_PACKED_NIBBLE_BLIT_MODE1_SOURCE,
            rom.RESIDENT_PACKED_NIBBLE_BLIT_MODE1_SIZE,
        )
        source = rom.program_source_words(
            rom.RESIDENT_PACKED_NIBBLE_BLIT_SOURCE,
            rom.RESIDENT_PACKED_NIBBLE_BLIT_SIZE,
        )
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.RESIDENT_PACKED_NIBBLE_BLIT_MODE0_ADDRESS,
                     len(mode0)),
            mode0,
        )
        self.assertEqual(
            words_at(image, rom.RESIDENT_PACKED_NIBBLE_BLIT_MODE1_ADDRESS,
                     len(mode1)),
            mode1,
        )
        self.assertEqual(
            words_at(image, rom.RESIDENT_PACKED_NIBBLE_BLIT_ADDRESS,
                     len(source)),
            source,
        )
        common_entry = [
            0x2E14, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7, 0x58F8,
        ]
        common_exit = [
            0x386F, 0x385F, 0x384F, 0x383F, 0x382F,
            0x381F, 0x380F, 0x2F00, 0x3F00, rom.RETS,
        ]
        self.assertEqual(mode0[:10], common_entry)
        self.assertEqual(mode0[-10:], common_exit)
        self.assertEqual(mode1[:10], common_entry)
        self.assertEqual(mode1[-10:], common_exit)
        self.assertEqual(
            source[:10],
            common_entry,
        )
        self.assertEqual(
            source[-10:],
            common_exit,
        )
        self.assertEqual(info["resident_packed_nibble_blit_mode0_0d_7c34"], {
            "destination": "0D:7C34",
            "source": "2A:7C34",
            "bytes": rom.RESIDENT_PACKED_NIBBLE_BLIT_MODE0_SIZE,
            "caller": "03:42C0; loaded NPE mode 0",
            "argument_bytes": 0x08,
            "reachable_instructions": 248,
            "direct_calls": 0,
            "status": "exact same-PC resident packed-nibble compositor mode 0",
        })
        self.assertEqual(info["resident_packed_nibble_blit_mode1_0d_7ece"], {
            "destination": "0D:7ECE",
            "source": "2A:7ECE",
            "bytes": rom.RESIDENT_PACKED_NIBBLE_BLIT_MODE1_SIZE,
            "caller": "03:42C4; loaded NPE mode 1",
            "argument_bytes": 0x08,
            "reachable_instructions": 417,
            "shared_tail": "0D:845A within resident 0D:8232 body",
            "direct_calls": 0,
            "status": "exact same-PC resident packed-nibble compositor mode 1",
        })
        self.assertEqual(info["resident_packed_nibble_blit_0d_8232"], {
            "destination": "0D:8232",
            "source": "2A:8232",
            "bytes": rom.RESIDENT_PACKED_NIBBLE_BLIT_SIZE,
            "caller": "18:5616",
            "argument_bytes": 0x08,
            "reachable_instructions": 298,
            "direct_calls": 0,
            "status": "exact same-PC resident packed-nibble compositor",
        })

    def test_file_construction_chain_uses_exact_guest_code(self) -> None:
        image = rom.build_image()
        info = rom.manifest(image)

        state_descriptor = rom.program_source_words(
            rom.APPLICATION_STATE_DESCRIPTOR_OVERLAY_SOURCE,
            rom.APPLICATION_STATE_DESCRIPTOR_OVERLAY_SIZE,
        )
        self.assertEqual(
            state_descriptor[:4], [0x2E02, 0x58F1, 0x58F2, 0x58F3]
        )
        self.assertEqual(state_descriptor[-2:], [0x2F00, rom.RETS])
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_STATE_DESCRIPTOR_OVERLAY_SOURCE +
                rom.APPLICATION_STATE_DESCRIPTOR_OVERLAY_SIZE,
                2,
            ),
            [0x2E02],
        )
        state_descriptor_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_STATE_DESCRIPTOR_OVERLAY_DESTINATION,
            rom.APPLICATION_STATE_DESCRIPTOR_OVERLAY_SOURCE,
            rom.APPLICATION_STATE_DESCRIPTOR_OVERLAY_SIZE,
        )
        application_installer = rom.install_application_main_chain_words()
        self.assertIn(
            state_descriptor_copy,
            [application_installer[index:index + len(state_descriptor_copy)]
             for index in range(
                 len(application_installer) - len(state_descriptor_copy) + 1
             )],
        )
        self.assertEqual(
            [item for item in info["application_main_chain"]
             if item["destination"] == "31:345E"],
            [{
                "destination": "31:345E",
                "source": "4E:345E",
                "bytes": 0x00C4,
                "status": "exact same-PC guest function",
            }],
        )

        resident_open = words_at(
            image,
            rom.RESIDENT_FILE_OPEN_1F1F1A_ADDRESS,
            rom.RESIDENT_FILE_OPEN_1F1F1A_SIZE // 2,
        )
        status_call = (
            0x1F221E - rom.RESIDENT_FILE_OPEN_1F1F1A_ADDRESS
        ) // 2
        self.assertEqual(
            rom.program_source_words(0x3C221E, 4),
            [0xBD2F, 0x5CDC],
        )
        self.assertEqual(
            resident_open[status_call:status_call + 2],
            [0xBD5D, 0x5CDC],
        )
        for call in rom.APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_CALLS:
            call_index = (call - rom.RESIDENT_FILE_OPEN_1F1F1A_ADDRESS) // 2
            self.assertEqual(
                resident_open[call_index:call_index + 2],
                [0xBD5F, 0x02D8],
            )

        attribute_source = rom.program_source_words(
            rom.APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_OVERLAY_SIZE,
        )
        self.assertEqual(attribute_source[:6], [
            0x2E00, 0x58F1, 0x780B, 0x0006, 0x781B, 0x0008,
        ])
        self.assertEqual(attribute_source[-3:], [0x381F, 0x2F00, rom.RETS])
        self.assertEqual(info["application_file_record_attribute_test"], {
            "destination": "5F:02D8",
            "linked_destination": "33:02D8",
            "source": "50:02D8",
            "bytes": rom.APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_OVERLAY_SIZE,
            "callers": ["1F:218E", "1F:21DE"],
            "status": (
                "exact source-50 file-record attribute test relocated around "
                "a live segment-33 code collision"
            ),
        })

        state50_source = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_STATE50_ROM_SOURCE,
            rom.APPLICATION_FOREGROUND_STATE50_ROM_SIZE,
        )
        state50_rom = rom.application_foreground_state50_rom_words()
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_FOREGROUND_STATE50_ROM_DESTINATION,
                len(state50_rom),
            ),
            state50_rom,
        )
        self.assertEqual(
            state50_rom[:8],
            [0x2ED8, 0x58F1, 0x58F2, 0x58F3,
             0x58F4, 0x58F5, 0x58F6, 0x58F7],
        )
        self.assertEqual(state50_rom[-2:], [0x2F00, rom.RETS])
        self.assertEqual(
            len(rom.APPLICATION_FOREGROUND_STATE50_ROM_SELF_CALL_OFFSETS),
            19,
        )
        for offset in rom.APPLICATION_FOREGROUND_STATE50_ROM_SELF_CALL_OFFSETS:
            index = offset // 2
            self.assertEqual(state50_source[index:index + 2],
                             [0xBD29, 0x0000])
            self.assertEqual(state50_rom[index:index + 2],
                             [0xBD0C, 0x0000])
        self.assertNotIn(
            [0xBD29, 0x0000],
            [state50_rom[index:index + 2]
             for index in range(len(state50_rom) - 1)],
        )
        mode_pair_index = (
            rom.APPLICATION_FOREGROUND_STATE50_MODE_PAIR_CALL_SOURCE -
            rom.APPLICATION_FOREGROUND_STATE50_ROM_SOURCE
        ) // 2
        self.assertEqual(
            state50_source[mode_pair_index:mode_pair_index + 2],
            [0xBD33, 0x1BBA],
        )
        self.assertEqual(
            state50_rom[mode_pair_index:mode_pair_index + 2],
            [0xBD5F, 0x1BBA],
        )
        self.assertEqual(
            len(rom.APPLICATION_FOREGROUND_STATE50_SETTING_CALL_SOURCES), 2
        )
        for source, destination in zip(
            rom.APPLICATION_FOREGROUND_STATE50_SETTING_CALL_SOURCES,
            rom.APPLICATION_FOREGROUND_STATE50_SETTING_CALLS,
        ):
            source_index = (
                source - rom.APPLICATION_FOREGROUND_STATE50_ROM_SOURCE
            ) // 2
            destination_index = (
                destination - rom.APPLICATION_FOREGROUND_STATE50_ROM_DESTINATION
            ) // 2
            self.assertEqual(
                state50_source[source_index:source_index + 2],
                [0xBD33, 0x4D6C],
            )
            self.assertEqual(source_index, destination_index)
            self.assertEqual(
                state50_rom[destination_index:destination_index + 2],
                [0xBD5F, 0x4D6C],
            )
        setting_source = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_STATE50_SETTING_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_STATE50_SETTING_OVERLAY_SIZE,
        )
        setting = rom.application_foreground_state50_setting_words()
        setting_child_index = (
            rom.APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_CALL_SOURCE -
            rom.APPLICATION_FOREGROUND_STATE50_SETTING_OVERLAY_SOURCE
        ) // 2
        self.assertEqual(setting_source[:2], [0x2E00, 0x58F0])
        self.assertEqual(setting_source[-2:], [0x2F00, rom.RETS])
        self.assertEqual(
            setting_source[setting_child_index:setting_child_index + 2],
            [0xBD32, 0xB9C6],
        )
        self.assertEqual(
            setting[setting_child_index:setting_child_index + 2],
            [0xBD5F, 0xB9C6],
        )
        setting_child_source = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_OVERLAY_SIZE,
        )
        setting_child = rom.application_foreground_state50_setting_child_words()
        setting_commit_index = (
            rom.APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_CALL_SOURCE -
            rom.APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_OVERLAY_SOURCE
        ) // 2
        self.assertEqual(setting_child_source[:2], [0x2E00, 0x58F0])
        self.assertEqual(setting_child_source[-2:], [0x2F00, rom.RETS])
        self.assertEqual(
            setting_child_source[
                setting_commit_index:setting_commit_index + 2
            ],
            [0xBD30, 0x6C9E],
        )
        self.assertEqual(
            setting_child[setting_commit_index:setting_commit_index + 2],
            [0xBD5F, 0x6C9E],
        )
        setting_commit = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_OVERLAY_SIZE,
        )
        self.assertEqual(setting_commit[:2], [0x2E01, 0x58F0])
        self.assertEqual(setting_commit[-2:], [0x2F00, rom.RETS])
        # 0C:3DD2 is part of this large function and must not be replaced by
        # the independent event helper installed at run-time at 29:3DD2.
        event_body_index = 0x3DD2 // 2
        self.assertEqual(
            state50_rom[event_body_index:event_body_index + 8],
            state50_source[event_body_index:event_body_index + 8],
        )
        self.assertIn(
            [0xBD33, 0x2020],
            [state50_rom[index:index + 2]
             for index in range(len(state50_rom) - 1)],
        )
        self.assertEqual(
            next(
                entry for entry in info["entries"]
                if entry["address"] == "0C:0000"
            ),
            {
                "address": "0C:0000",
                "name": "resident_application_state50_rom_0c_0000",
                "words": rom.APPLICATION_FOREGROUND_STATE50_ROM_SIZE // 2,
            },
        )
        cleanup_installer = [
            *rom.embed_program_overlay_words(
                rom.APPLICATION_FOREGROUND_STATE50_CLEANUP_OVERLAY_DESTINATION,
                rom.APPLICATION_FOREGROUND_STATE50_CLEANUP_OVERLAY_SOURCE,
                rom.APPLICATION_FOREGROUND_STATE50_CLEANUP_OVERLAY_SIZE,
            ),
            *rom.embed_program_overlay_words(
                rom.APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_DESTINATION,
                rom.APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_SOURCE,
                rom.APPLICATION_MENU_HANDLE_RELEASE_OVERLAY_SIZE,
            ),
            *rom.embed_program_overlay_words(
                rom.APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_DESTINATION,
                rom.APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_SOURCE,
                rom.APPLICATION_MENU_CONTEXT_RELEASE_OVERLAY_SIZE,
            ),
            *rom.write_program_words(
                rom.APPLICATION_FOREGROUND_STATE50_SETTING_OVERLAY_DESTINATION,
                setting,
            ),
            *rom.write_program_words(
                rom.APPLICATION_FOREGROUND_STATE50_SETTING_CHILD_OVERLAY_DESTINATION,
                setting_child,
            ),
            *rom.embed_program_overlay_words(
                rom.APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_OVERLAY_DESTINATION,
                rom.APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_OVERLAY_SOURCE,
                rom.APPLICATION_FOREGROUND_STATE50_SETTING_COMMIT_OVERLAY_SIZE,
            ),
            rom.RETS,
        ]
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_FOREGROUND_STATE50_CLEANUP_INSTALLER_ADDRESS,
                len(cleanup_installer),
            ),
            cleanup_installer,
        )
        state50_rom_data = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_STATE50_ROM_DATA_SOURCE,
            rom.APPLICATION_FOREGROUND_STATE50_ROM_DATA_SIZE,
        )
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_FOREGROUND_STATE50_ROM_DATA_DESTINATION,
                len(state50_rom_data),
            ),
            state50_rom_data,
        )
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_POST_MODAL_TEXT_ROM_DATA_DESTINATION,
                rom.APPLICATION_POST_MODAL_TEXT_ROM_DATA_SIZE // 2,
            ),
            rom.program_source_words(
                rom.APPLICATION_POST_MODAL_TEXT_ROM_DATA_SOURCE,
                rom.APPLICATION_POST_MODAL_TEXT_ROM_DATA_SIZE,
            ),
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_POST_MODAL_TEXT_ROM_DATA_SOURCE,
                rom.APPLICATION_POST_MODAL_TEXT_ROM_DATA_SIZE,
            ),
            [0x5553, 0x4220, 0x4445, 0x4D4F, 0x0000],
        )
        self.assertEqual(
            rom.program_source_words(0x3B49E4, 2),
            [0x2E01],
        )
        state50_workspace = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_STATE50_WORKSPACE_ROM_SOURCE,
            rom.APPLICATION_FOREGROUND_STATE50_WORKSPACE_ROM_SIZE,
        )
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_FOREGROUND_STATE50_WORKSPACE_ROM_DESTINATION,
                len(state50_workspace),
            ),
            state50_workspace,
        )
        self.assertEqual(
            state50_workspace[:9],
            [0x2E0C, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
             0x58F4, 0x58F5, 0x58F6, 0x58F7],
        )
        self.assertEqual(
            state50_workspace[-10:],
            [0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
             0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            next(
                entry for entry in info["entries"]
                if entry["address"] == "1B:ACC0"
            ),
            {
                "address": "1B:ACC0",
                "name": "resident_application_state50_workspace_1b_acc0",
                "words": (
                    rom.APPLICATION_FOREGROUND_STATE50_WORKSPACE_ROM_SIZE // 2
                ),
            },
        )
        state50_format = rom.application_foreground_state50_format_rom_words()
        format_source = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_STATE50_FORMAT_ROM_SOURCE,
            rom.APPLICATION_FOREGROUND_STATE50_FORMAT_ROM_SIZE,
        )
        sector_index = (
            rom.APPLICATION_FOREGROUND_STATE50_FORMAT_SECTOR_CALL_SOURCE -
            rom.APPLICATION_FOREGROUND_STATE50_FORMAT_ROM_SOURCE
        ) // 2
        self.assertEqual(format_source[sector_index:sector_index + 2],
                         [0xBD20, 0xF928])
        self.assertEqual(
            state50_format[sector_index:sector_index + 2],
            [0xBD00 | (
                rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION >> 16
             ),
             rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION & 0xFFFF],
        )
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_FOREGROUND_STATE50_FORMAT_ROM_DESTINATION,
                len(state50_format),
            ),
            state50_format,
        )
        state50_child = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_STATE50_CHILD_ROM_SOURCE,
            rom.APPLICATION_FOREGROUND_STATE50_CHILD_ROM_SIZE,
        )
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_FOREGROUND_STATE50_CHILD_ROM_DESTINATION,
                len(state50_child),
            ),
            state50_child,
        )
        self.assertEqual(state50_child[:6],
                         [0x2E0E, 0x58F1, 0x58F2, 0x58F3,
                          0x58F4, 0x58F5])
        self.assertEqual(state50_child[-8:],
                         [0x4800, 0x385F, 0x384F, 0x383F,
                          0x382F, 0x381F, 0x2F00, rom.RETS])

        xor_copy = rom.program_source_words(
            rom.RESIDENT_XOR_COPY_07_SOURCE,
            rom.RESIDENT_XOR_COPY_07_SIZE,
        )
        self.assertEqual(
            words_at(image, rom.RESIDENT_XOR_COPY_07_ADDRESS, len(xor_copy)),
            xor_copy,
        )
        self.assertEqual(xor_copy[:4], [0x2E00, 0x58F0, 0x58F1, 0x58F2])
        self.assertEqual(xor_copy[-2:], [0x2F00, rom.RETS])
        self.assertEqual(
            info["resident_xor_copy_07_36d4"]["bytes"],
            rom.RESIDENT_XOR_COPY_07_SIZE,
        )

        record_lookup = rom.program_source_words(
            rom.RESIDENT_RECORD_INDEX_LOOKUP_07_SOURCE,
            rom.RESIDENT_RECORD_INDEX_LOOKUP_07_SIZE,
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_RECORD_INDEX_LOOKUP_07_ADDRESS,
                len(record_lookup),
            ),
            record_lookup,
        )
        self.assertEqual(
            record_lookup[:5],
            [0x2E01, 0x58F1, 0x58F2, 0x58F3, 0x4800],
        )
        self.assertIn(
            [0xBD33, 0x07B0],
            [record_lookup[index:index + 2]
             for index in range(len(record_lookup) - 1)],
        )
        self.assertEqual(
            record_lookup[-5:],
            [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            info["resident_record_index_lookup_07_912e"],
            {
                "destination": "07:912E",
                "source": "24:912E",
                "bytes": rom.RESIDENT_RECORD_INDEX_LOOKUP_07_SIZE,
                "arguments": [
                    "two-word far pointer to record descriptor"
                ],
                "result": "matching record index, or -1",
                "status": "exact same-PC resident record-index lookup",
            },
        )

        closure_info = {
            item["destination"]: item
            for item in info["resident_record_materialization_closure"]
        }
        for address, source_address, size, name in (
                rom.RESIDENT_RECORD_MATERIALIZATION_CLOSURE):
            source = rom.program_source_words(source_address, size)
            self.assertEqual(words_at(image, address, len(source)), source)
            self.assertEqual(source[0] >> 8, 0x2E)
            self.assertEqual(source[-2:], [0x2F00, rom.RETS])
            destination = f"{address >> 16:02X}:{address & 0xFFFF:04X}"
            self.assertEqual(closure_info[destination], {
                "destination": destination,
                "source": (
                    f"{source_address >> 16:02X}:"
                    f"{source_address & 0xFFFF:04X}"
                ),
                "bytes": size,
                "routine": name,
                "status": "exact same-PC resident guest function",
            })

        delimited_copy = rom.program_source_words(
            rom.RESIDENT_DELIMITED_FIELD_COPY_06_SOURCE,
            rom.RESIDENT_DELIMITED_FIELD_COPY_06_SIZE,
        )
        self.assertEqual(
            delimited_copy[:6],
            [0x2E00, 0x58F2, 0x58F3, 0x58F4, 0x58F5, 0x780B],
        )
        self.assertIn(
            [0x793B, 0x000E, 0x1813],
            [delimited_copy[index:index + 3]
             for index in range(len(delimited_copy) - 2)],
        )
        self.assertIn(
            [0x793B, 0x0010, 0x1813],
            [delimited_copy[index:index + 3]
             for index in range(len(delimited_copy) - 2)],
        )
        self.assertFalse(any(word >> 8 == 0xBD for word in delimited_copy))
        self.assertEqual(
            delimited_copy[-10:-2],
            [0x780B, 0x000A, 0x781B, 0x000C,
             0x385F, 0x384F, 0x383F, 0x382F],
        )
        self.assertEqual(
            delimited_copy[-2:],
            [0x2F00, rom.RETS],
        )

        suffix_replace = rom.program_source_words(
            rom.RESIDENT_SUFFIX_REPLACE_07_SOURCE,
            rom.RESIDENT_SUFFIX_REPLACE_07_SIZE,
        )
        self.assertEqual(
            suffix_replace[:8],
            [0x2E02, 0x58F0, 0x58F1, 0x58F2,
             0x58F3, 0x58F4, 0x58F5, 0x780B],
        )
        self.assertEqual(
            {(suffix_replace[index], suffix_replace[index + 1])
             for index in range(len(suffix_replace) - 1)
             if suffix_replace[index] >> 8 == 0xBD},
            {(0xBD31, 0xAED0), (0xBD32, 0x8204)},
        )
        self.assertEqual(suffix_replace[-2:], [0x2F00, rom.RETS])

        materialize = rom.program_source_words(
            rom.RESIDENT_RECORD_MATERIALIZE_07_SOURCE,
            rom.RESIDENT_RECORD_MATERIALIZE_07_SIZE,
        )
        materialize_calls = {
            tuple(materialize[index:index + 2])
            for index in range(len(materialize) - 1)
            if materialize[index] >> 8 == 0xBD
        }
        self.assertTrue({
            (0xBD07, 0x399C), (0xBD05, 0xFFCA),
            (0xBD07, 0xA100), (0xBD07, 0x3350),
            (0xBD07, 0x94CE), (0xBD06, 0xD816),
            (0xBD07, 0x6748), (0xBD04, 0xFFD8),
        }.issubset(materialize_calls))

        for address, source_address, size, manifest_key, first_word in (
            (rom.RESIDENT_FILE_OPEN_1F1F1A_ADDRESS,
             rom.RESIDENT_FILE_OPEN_1F1F1A_SOURCE,
             rom.RESIDENT_FILE_OPEN_1F1F1A_SIZE,
             "resident_file_open_1f_1f1a", 0x2E05),
            (rom.RESIDENT_RESOURCE_INIT_1BCE3C_ADDRESS,
             rom.RESIDENT_RESOURCE_INIT_1BCE3C_SOURCE,
             rom.RESIDENT_RESOURCE_INIT_1BCE3C_SIZE,
             "resident_resource_init_1b_ce3c", 0x2E2A),
        ):
            source = rom.program_source_words(source_address, size)
            expected = list(source)
            if address == rom.RESIDENT_FILE_OPEN_1F1F1A_ADDRESS:
                for call_address in (
                        rom.APPLICATION_FILE_RECORD_ATTRIBUTE_TEST_CALL_SOURCES):
                    call_index = (call_address -
                                  rom.RESIDENT_FILE_OPEN_1F1F1A_SOURCE) // 2
                    expected[call_index:call_index + 2] = [0xBD5F, 0x02D8]
                call_index = (0x1F221E - address) // 2
                expected[call_index:call_index + 2] = [0xBD5D, 0x5CDC]
                call_index = (0x1F225A - address) // 2
                expected[call_index:call_index + 2] = [0xBD5D, 0x7584]
                call_index = (0x1F22D6 - address) // 2
                expected[call_index:call_index + 2] = [0xBD5D, 0x6D9E]
                call_index = (0x1F2334 - address) // 2
                expected[call_index:call_index + 2] = [0xBD5D, 0x06C4]
                call_index = (0x1F2358 - address) // 2
                expected[call_index:call_index + 2] = [0xBD07, 0x4000]
            self.assertEqual(words_at(image, address, len(source)), expected)
            self.assertEqual(source[0], first_word)
            self.assertEqual(source[-2:], [0x2F00, rom.RETS])
            self.assertEqual(info[manifest_key]["bytes"], size)

        patch = (
            rom.install_runtime_overlay_words()
            + rom.menu_runtime_overlay_installer_words()
            + rom.install_application_main_chain_words()
            + rom.application_region_extra_installer_words()
            + rom.application_cursor_refresh_installer_words()
        )
        for destination, source, size in (
            (rom.APPLICATION_TOP_LEVEL_OVERLAY_DESTINATION,
             rom.APPLICATION_TOP_LEVEL_OVERLAY_SOURCE,
             rom.APPLICATION_TOP_LEVEL_OVERLAY_SIZE),
            (rom.APPLICATION_UI_STATE_OVERLAY_DESTINATION,
             rom.APPLICATION_UI_STATE_OVERLAY_SOURCE,
             rom.APPLICATION_UI_STATE_OVERLAY_SIZE),
            (rom.APPLICATION_GLOBAL_STATE_INIT_OVERLAY_DESTINATION,
             rom.APPLICATION_GLOBAL_STATE_INIT_OVERLAY_SOURCE,
             rom.APPLICATION_GLOBAL_STATE_INIT_OVERLAY_SIZE),
            (rom.APPLICATION_GLOBAL_STATE_TABLE_CLEAR_OVERLAY_DESTINATION,
             rom.APPLICATION_GLOBAL_STATE_TABLE_CLEAR_OVERLAY_SOURCE,
             rom.APPLICATION_GLOBAL_STATE_TABLE_CLEAR_OVERLAY_SIZE),
            (rom.APPLICATION_GLOBAL_STATE_BYTE_FILL_OVERLAY_DESTINATION,
             rom.APPLICATION_GLOBAL_STATE_BYTE_FILL_OVERLAY_SOURCE,
             rom.APPLICATION_GLOBAL_STATE_BYTE_FILL_OVERLAY_SIZE),
            (rom.APPLICATION_POST_REGISTRY_OVERLAY_DESTINATION,
             rom.APPLICATION_POST_REGISTRY_OVERLAY_SOURCE,
             rom.APPLICATION_POST_REGISTRY_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_STATE_INIT_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STATE_INIT_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STATE_INIT_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_STATE_BUILD_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STATE_BUILD_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STATE_BUILD_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_STATE_POINTER_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STATE_POINTER_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STATE_POINTER_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_STORAGE_CONTEXT_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STORAGE_CONTEXT_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STORAGE_CONTEXT_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_MODE_DISPATCH_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_MODE_DISPATCH_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_MODE_DISPATCH_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_CONFIG_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_CONFIG_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_CONFIG_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_CONFIG_BUILD_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_CONFIG_BUILD_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_CONFIG_BUILD_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_CONDITIONAL_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_CONDITIONAL_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_CONDITIONAL_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_INPUT_STATE_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_INPUT_STATE_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_INPUT_STATE_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_STATUS_SCAN_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STATUS_SCAN_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STATUS_SCAN_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_STATE_TICK_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STATE_TICK_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STATE_TICK_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_STATE_SYNC_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STATE_SYNC_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STATE_SYNC_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_ACTION_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_ACTION_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_ACTION_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_ACTION_RENDER_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_ACTION_RENDER_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_ACTION_RENDER_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_ACTION_RENDER_CLEAR_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_ACTION_RENDER_CLEAR_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_ACTION_RENDER_CLEAR_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_ACTION_RENDER_LINE_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_RESULT_SCAN_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_RESULT_SCAN_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_RESULT_SCAN_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_LAYOUT_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_LAYOUT_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_LAYOUT_OVERLAY_SIZE),
            (rom.APPLICATION_FOREGROUND_LOOP_OVERLAY_DESTINATION,
             rom.APPLICATION_FOREGROUND_LOOP_OVERLAY_SOURCE,
             rom.APPLICATION_FOREGROUND_LOOP_OVERLAY_SIZE),
            (rom.APPLICATION_FOREGROUND_STATE_OVERLAY_DESTINATION,
             rom.APPLICATION_FOREGROUND_STATE_OVERLAY_SOURCE,
             rom.APPLICATION_FOREGROUND_STATE_OVERLAY_SIZE),
            (rom.APPLICATION_FOREGROUND_COPY_OVERLAY_DESTINATION,
             rom.APPLICATION_FOREGROUND_COPY_OVERLAY_SOURCE,
             rom.APPLICATION_FOREGROUND_COPY_OVERLAY_SIZE),
            (rom.APPLICATION_FOREGROUND_EVENT_OVERLAY_DESTINATION,
             rom.APPLICATION_FOREGROUND_EVENT_OVERLAY_SOURCE,
             rom.APPLICATION_FOREGROUND_EVENT_OVERLAY_SIZE),
            (rom.APPLICATION_FOREGROUND_PARENT_OVERLAY_DESTINATION,
             rom.APPLICATION_FOREGROUND_PARENT_OVERLAY_SOURCE,
             rom.APPLICATION_FOREGROUND_PARENT_OVERLAY_SIZE),
            (rom.APPLICATION_FOREGROUND_DISPATCH_PREPARE_OVERLAY_DESTINATION,
             rom.APPLICATION_FOREGROUND_DISPATCH_PREPARE_OVERLAY_SOURCE,
             rom.APPLICATION_FOREGROUND_DISPATCH_PREPARE_OVERLAY_SIZE),
            (rom.APPLICATION_FOREGROUND_DISPATCH_TABLE_DESTINATION,
             rom.APPLICATION_FOREGROUND_DISPATCH_TABLE_SOURCE,
             rom.APPLICATION_FOREGROUND_DISPATCH_TABLE_SIZE),
            (rom.APPLICATION_FOREGROUND_STATE_DISPATCH_OVERLAY_DESTINATION,
             rom.APPLICATION_FOREGROUND_STATE_DISPATCH_OVERLAY_SOURCE,
             rom.APPLICATION_FOREGROUND_STATE_DISPATCH_OVERLAY_SIZE),
            (rom.APPLICATION_FOREGROUND_STATE50_OVERLAY_DESTINATION,
             rom.APPLICATION_FOREGROUND_STATE50_OVERLAY_SOURCE,
             rom.APPLICATION_FOREGROUND_STATE50_OVERLAY_SIZE),
            (rom.APPLICATION_FOREGROUND_STATE50_PREDICATE_OVERLAY_DESTINATION,
             rom.APPLICATION_FOREGROUND_STATE50_PREDICATE_OVERLAY_SOURCE,
             rom.APPLICATION_FOREGROUND_STATE50_PREDICATE_OVERLAY_SIZE),
            (rom.APPLICATION_INPUT_MODE_OVERLAY_DESTINATION,
             rom.APPLICATION_INPUT_MODE_OVERLAY_SOURCE,
             rom.APPLICATION_INPUT_MODE_OVERLAY_SIZE),
            (rom.APPLICATION_EVENT_PACKET_DECODE_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_PACKET_DECODE_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_PACKET_DECODE_OVERLAY_SIZE),
            (rom.APPLICATION_EVENT_PACKET_COPY_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_PACKET_COPY_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_PACKET_COPY_OVERLAY_SIZE),
            (rom.APPLICATION_EVENT_TEXT_DATA_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_TEXT_DATA_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_TEXT_DATA_OVERLAY_SIZE),
            (rom.APPLICATION_EVENT_RENDER_HELPER_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_RENDER_HELPER_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_RENDER_HELPER_OVERLAY_SIZE),
            (rom.APPLICATION_EVENT_READY_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_READY_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_READY_OVERLAY_SIZE),
            (rom.APPLICATION_FOREGROUND_OBJECT_RELINK_OVERLAY_DESTINATION,
             rom.APPLICATION_FOREGROUND_OBJECT_RELINK_OVERLAY_SOURCE,
             rom.APPLICATION_FOREGROUND_OBJECT_RELINK_OVERLAY_SIZE),
            (rom.APPLICATION_TIMER_CALLBACK_OVERLAY_DESTINATION,
             rom.APPLICATION_TIMER_CALLBACK_OVERLAY_SOURCE,
             rom.APPLICATION_TIMER_CALLBACK_OVERLAY_SIZE),
            (rom.APPLICATION_KEY_DEBOUNCE_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_DEBOUNCE_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_DEBOUNCE_OVERLAY_SIZE),
            (rom.APPLICATION_KEY_MATRIX_SCAN_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_MATRIX_SCAN_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_MATRIX_SCAN_OVERLAY_SIZE),
            (rom.APPLICATION_TIMER_POWER_OVERLAY_DESTINATION,
             rom.APPLICATION_TIMER_POWER_OVERLAY_SOURCE,
             rom.APPLICATION_TIMER_POWER_OVERLAY_SIZE),
            (rom.APPLICATION_TIMER_IDLE_OVERLAY_DESTINATION,
             rom.APPLICATION_TIMER_IDLE_OVERLAY_SOURCE,
             rom.APPLICATION_TIMER_IDLE_OVERLAY_SIZE),
            (rom.APPLICATION_TIMER_CALENDAR_OVERLAY_DESTINATION,
             rom.APPLICATION_TIMER_CALENDAR_OVERLAY_SOURCE,
             rom.APPLICATION_TIMER_CALENDAR_OVERLAY_SIZE),
            (rom.APPLICATION_TIMER_COMMIT_OVERLAY_DESTINATION,
             rom.APPLICATION_TIMER_COMMIT_OVERLAY_SOURCE,
             rom.APPLICATION_TIMER_COMMIT_OVERLAY_SIZE),
            (rom.APPLICATION_EVENT_DECODE_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_DECODE_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_DECODE_OVERLAY_SIZE),
            (rom.APPLICATION_LOADING_TASK_OVERLAY_DESTINATION,
             rom.APPLICATION_LOADING_TASK_OVERLAY_SOURCE,
             rom.APPLICATION_LOADING_TASK_OVERLAY_SIZE),
            (rom.APPLICATION_SYSTEM_REGISTRY_OVERLAY_DESTINATION,
             rom.APPLICATION_SYSTEM_REGISTRY_OVERLAY_SOURCE,
             rom.APPLICATION_SYSTEM_REGISTRY_OVERLAY_SIZE),
            (rom.APPLICATION_STORAGE_CAPACITY_OVERLAY_DESTINATION,
             rom.APPLICATION_STORAGE_CAPACITY_OVERLAY_SOURCE,
             rom.APPLICATION_STORAGE_CAPACITY_OVERLAY_SIZE),
            (rom.APPLICATION_STORAGE_RECORD_LOOKUP_OVERLAY_DESTINATION,
             rom.APPLICATION_STORAGE_RECORD_LOOKUP_OVERLAY_SOURCE,
             rom.APPLICATION_STORAGE_RECORD_LOOKUP_OVERLAY_SIZE),
            (rom.APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_DESTINATION,
             rom.APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_SOURCE,
             rom.APPLICATION_STORAGE_DRIVER_RESOLVE_OVERLAY_SIZE),
            (rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION,
             rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_SOURCE,
             rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_SIZE),
            (rom.STARTUP_TICK_INIT_OVERLAY_DESTINATION,
             rom.STARTUP_TICK_INIT_OVERLAY_SOURCE,
             rom.STARTUP_TICK_INIT_OVERLAY_SIZE),
            (rom.STARTUP_TIMER_CONFIG_OVERLAY_DESTINATION,
             rom.STARTUP_TIMER_CONFIG_OVERLAY_SOURCE,
             rom.STARTUP_TIMER_CONFIG_OVERLAY_SIZE),
            (rom.APPLICATION_FAR_BLOCK_COPY_OVERLAY_DESTINATION,
             rom.APPLICATION_FAR_BLOCK_COPY_OVERLAY_SOURCE,
             rom.APPLICATION_FAR_BLOCK_COPY_OVERLAY_SIZE),
            (rom.LCD_RESOURCE_DISPATCH_THUNK_DESTINATION,
             rom.LCD_RESOURCE_DISPATCH_THUNK_SOURCE,
             rom.LCD_RESOURCE_DISPATCH_THUNK_SIZE),
            (rom.LCD_RESOURCE_TRANSFER_OVERLAY_DESTINATION,
             rom.LCD_RESOURCE_TRANSFER_OVERLAY_SOURCE,
             rom.LCD_RESOURCE_TRANSFER_OVERLAY_SIZE),
            (rom.APPLICATION_RESOURCE_PAGE_READ_OVERLAY_DESTINATION,
             rom.APPLICATION_RESOURCE_PAGE_READ_OVERLAY_SOURCE,
             rom.APPLICATION_RESOURCE_PAGE_READ_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_ENTRY_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_ENTRY_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_ENTRY_OVERLAY_SIZE),
            (rom.APPLICATION_CLOCK_VALIDATE_OVERLAY_DESTINATION,
             rom.APPLICATION_CLOCK_VALIDATE_OVERLAY_SOURCE,
             rom.APPLICATION_CLOCK_VALIDATE_OVERLAY_SIZE),
            (rom.APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_DESTINATION,
             rom.APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_SOURCE,
             rom.APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_SIZE),
            (rom.APPLICATION_SERVICE_LATCH_INIT_OVERLAY_DESTINATION,
             rom.APPLICATION_SERVICE_LATCH_INIT_OVERLAY_SOURCE,
             rom.APPLICATION_SERVICE_LATCH_INIT_OVERLAY_SIZE),
            (rom.APPLICATION_LOCALE_DEFAULT_INIT_OVERLAY_DESTINATION,
             rom.APPLICATION_LOCALE_DEFAULT_INIT_OVERLAY_SOURCE,
             rom.APPLICATION_LOCALE_DEFAULT_INIT_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_31_1528_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_31_1528_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_31_1528_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_08_2EDC_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_08_2EDC_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_08_2EDC_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_33_356E_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_33_356E_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_33_356E_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_33_3406_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_33_3406_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_33_3406_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_08_3324_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_08_3324_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_08_3324_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_33_3FD6_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_33_3FD6_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_33_3FD6_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_29_C126_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_29_C126_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_29_C126_OVERLAY_SIZE),
            (rom.APPLICATION_OPERATION_UI_INIT_OVERLAY_DESTINATION,
             rom.APPLICATION_OPERATION_UI_INIT_OVERLAY_SOURCE,
             rom.APPLICATION_OPERATION_UI_INIT_OVERLAY_SIZE),
            (rom.APPLICATION_OPERATION_MODE_ROUTER_OVERLAY_DESTINATION,
             rom.APPLICATION_OPERATION_MODE_ROUTER_OVERLAY_SOURCE,
             rom.APPLICATION_OPERATION_MODE_ROUTER_OVERLAY_SIZE),
            (rom.APPLICATION_OPERATION_NUMBER_DISPATCH_OVERLAY_DESTINATION,
             rom.APPLICATION_OPERATION_NUMBER_DISPATCH_OVERLAY_SOURCE,
             rom.APPLICATION_OPERATION_NUMBER_DISPATCH_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_33_09B8_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_33_09B8_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_33_09B8_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_32_4D1C_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_32_4D1C_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_32_4D1C_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_32_3232_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_32_3232_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_32_3232_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_31_C3FC_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_31_C3FC_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_31_C3FC_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_32_519E_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_32_519E_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_32_519E_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_32_F3C6_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_32_F3C6_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_32_F3C6_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_31_B6FC_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_31_B6FC_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_31_B6FC_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_31_CC84_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_31_CC84_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_31_CC84_OVERLAY_SIZE),
            (rom.APPLICATION_INIT_32_C514_OVERLAY_DESTINATION,
             rom.APPLICATION_INIT_32_C514_OVERLAY_SOURCE,
             rom.APPLICATION_INIT_32_C514_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_LOOP_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_LOOP_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_LOOP_OVERLAY_SIZE),
            (rom.APPLICATION_RESOURCE_DRIVER_OVERLAY_DESTINATION,
             rom.APPLICATION_RESOURCE_DRIVER_OVERLAY_SOURCE,
             rom.APPLICATION_RESOURCE_DRIVER_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_ATTACH_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_ATTACH_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_ATTACH_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_WRAPPER_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_WRAPPER_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_WRAPPER_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_OBJECT_OPEN_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_OBJECT_OPEN_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_OBJECT_OPEN_OVERLAY_SIZE),
            (rom.APPLICATION_STATE_DESCRIPTOR_OVERLAY_DESTINATION,
             rom.APPLICATION_STATE_DESCRIPTOR_OVERLAY_SOURCE,
             rom.APPLICATION_STATE_DESCRIPTOR_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_OBJECT_RESOLVE_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_OBJECT_RESOLVE_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_OBJECT_RESOLVE_OVERLAY_SIZE),
            (rom.APPLICATION_POINTER_CLASSIFY_OVERLAY_DESTINATION,
             rom.APPLICATION_POINTER_CLASSIFY_OVERLAY_SOURCE,
             rom.APPLICATION_POINTER_CLASSIFY_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_RECORD_SCAN_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_RECORD_SCAN_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_RECORD_SCAN_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_RECORD_RESOLVE_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_RECORD_RESOLVE_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_RECORD_RESOLVE_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_CREATE_STATE_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_CREATE_STATE_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_CREATE_STATE_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_CREATE_RECORD_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_CREATE_RECORD_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_CREATE_RECORD_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_CREATE_VALIDATE_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_CREATE_VALIDATE_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_CREATE_VALIDATE_OVERLAY_SIZE),
            (rom.APPLICATION_STORAGE_CONTEXT_RESOLVE_OVERLAY_DESTINATION,
             rom.APPLICATION_STORAGE_CONTEXT_RESOLVE_OVERLAY_SOURCE,
             rom.APPLICATION_STORAGE_CONTEXT_RESOLVE_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_ENTRY_BUILD_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_ENTRY_BUILD_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_ENTRY_BUILD_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_RECORD_STATUS_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_RECORD_STATUS_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_RECORD_STATUS_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_RECORD_APPLY_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_RECORD_APPLY_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_RECORD_APPLY_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_CLOSE_STATE_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_CLOSE_STATE_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_CLOSE_STATE_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_CLOSE_RECORD_SYNC_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_CLOSE_RECORD_SYNC_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_CLOSE_RECORD_SYNC_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_METADATA_UPDATE_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_METADATA_UPDATE_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_METADATA_UPDATE_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_RECORD_CONTEXT_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_RECORD_CONTEXT_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_RECORD_CONTEXT_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_RECORD_BUILD_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_RECORD_BUILD_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_RECORD_BUILD_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_RECORD_QUERY_A_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_RECORD_QUERY_A_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_RECORD_QUERY_A_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_RECORD_QUERY_B_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_RECORD_QUERY_B_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_RECORD_QUERY_B_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_RECORD_QUERY_C_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_RECORD_QUERY_C_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_RECORD_QUERY_C_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_RECORD_LEAF_50A4_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_RECORD_LEAF_50A4_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_RECORD_LEAF_50A4_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_RECORD_LEAF_507C_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_RECORD_LEAF_507C_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_RECORD_LEAF_507C_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_RECORD_LEAF_66EC_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_RECORD_LEAF_66EC_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_RECORD_LEAF_66EC_OVERLAY_SIZE),
            (rom.APPLICATION_ROOT_OBJECT_FIELD_OVERLAY_DESTINATION,
             rom.APPLICATION_ROOT_OBJECT_FIELD_OVERLAY_SOURCE,
             rom.APPLICATION_ROOT_OBJECT_FIELD_OVERLAY_SIZE),
            (rom.APPLICATION_FILE_RECORD_LEAF_673C_OVERLAY_DESTINATION,
             rom.APPLICATION_FILE_RECORD_LEAF_673C_OVERLAY_SOURCE,
             rom.APPLICATION_FILE_RECORD_LEAF_673C_OVERLAY_SIZE),
            (rom.APPLICATION_RESOURCE_RECORD_PARSE_OVERLAY_DESTINATION,
             rom.APPLICATION_RESOURCE_RECORD_PARSE_OVERLAY_SOURCE,
             rom.APPLICATION_RESOURCE_RECORD_PARSE_OVERLAY_SIZE),
            (rom.APPLICATION_BYTE_CLASSIFY_OVERLAY_DESTINATION,
             rom.APPLICATION_BYTE_CLASSIFY_OVERLAY_SOURCE,
             rom.APPLICATION_BYTE_CLASSIFY_OVERLAY_SIZE),
            (rom.APPLICATION_ASCII_LOWER_OVERLAY_DESTINATION,
             rom.APPLICATION_ASCII_LOWER_OVERLAY_SOURCE,
             rom.APPLICATION_ASCII_LOWER_OVERLAY_SIZE),
        ):
            if destination == rom.APPLICATION_OPERATION_UI_INIT_OVERLAY_DESTINATION:
                descriptor = [
                    0xBD00 | (
                        rom.APPLICATION_OPERATION_UI_INIT_INSTALLER_ADDRESS >> 16
                    ),
                    rom.APPLICATION_OPERATION_UI_INIT_INSTALLER_ADDRESS & 0xFFFF,
                ]
            elif (destination in
                    rom.APPLICATION_INITIALIZER_FOLLOWUP_EMBEDDED_DESTINATIONS or
                    destination in rom.APPLICATION_FILE_RECORD_EMBEDDED_DESTINATIONS):
                descriptor = rom.embed_program_overlay_words(
                    destination, source, size
                )
            else:
                descriptor = rom.copy_code_to_overlay_words(
                    destination, source, size
                )
            self.assertIn(
                descriptor,
                [patch[i:i + len(descriptor)]
                 for i in range(len(patch) - len(descriptor) + 1)],
                f"missing runtime overlay {destination:06X} <- {source:06X}",
            )
        classify_table = rom.embed_program_overlay_words(
            rom.APPLICATION_BYTE_CLASSIFY_TABLE_OVERLAY_DESTINATION,
            rom.APPLICATION_BYTE_CLASSIFY_TABLE_OVERLAY_SOURCE,
            rom.APPLICATION_BYTE_CLASSIFY_TABLE_OVERLAY_SIZE,
        )
        self.assertIn(
            classify_table,
            [patch[i:i + len(classify_table)]
             for i in range(len(patch) - len(classify_table) + 1)],
        )
        for address, target in (
            (rom.APPLICATION_FILE_CREATE_VALIDATE_REGISTRY_ENTRY_CALL,
             rom.APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_DESTINATION),
            (rom.APPLICATION_STORAGE_CONTEXT_RESOLVE_SECTOR_PROBE_CALL,
             rom.APPLICATION_STORAGE_SECTOR_PROBE_OVERLAY_DESTINATION),
            (rom.APPLICATION_FILE_ENTRY_BUILD_CALL,
             rom.APPLICATION_FILE_ENTRY_BUILD_OVERLAY_DESTINATION),
            *(
                (address,
                 rom.APPLICATION_FILE_RECORD_STATUS_OVERLAY_DESTINATION)
                for address, _source in
                rom.APPLICATION_FILE_RECORD_STATUS_CALLS
            ),
            (rom.APPLICATION_FILE_RECORD_STATUS_SELECT_CALL,
             rom.RESIDENT_STORAGE_SELECT_ADDRESS),
            (rom.APPLICATION_FILE_RECORD_APPLY_CALL,
             rom.APPLICATION_FILE_RECORD_APPLY_OVERLAY_DESTINATION),
            (rom.APPLICATION_FILE_RECORD_APPLY_PAIR_CALL,
             rom.RESIDENT_STORAGE_PAIR_ADDRESS),
            (rom.APPLICATION_FILE_RECORD_APPLY_DRIVER_CALL,
             rom.RESIDENT_STORAGE_DRIVER_ADDRESS),
            (rom.APPLICATION_FILE_CLOSE_STATE_CALL,
             rom.APPLICATION_FILE_CLOSE_STATE_OVERLAY_DESTINATION),
            (rom.APPLICATION_FILE_CLOSE_RECORD_SYNC_CALL,
             rom.APPLICATION_FILE_CLOSE_RECORD_SYNC_OVERLAY_DESTINATION),
            (rom.APPLICATION_FILE_CLOSE_DRIVER_CALL,
             rom.RESIDENT_STORAGE_DRIVER_ADDRESS),
            *(
                (address,
                 rom.APPLICATION_FILE_METADATA_UPDATE_OVERLAY_DESTINATION)
                for address, _source in
                rom.APPLICATION_FILE_METADATA_UPDATE_CALLS
            ),
        ):
            descriptor = rom.write_program_words(
                address,
                (0xBD00 | (target >> 16), target & 0xFFFF),
            )
            self.assertIn(
                descriptor,
                [patch[i:i + len(descriptor)]
                 for i in range(len(patch) - len(descriptor) + 1)],
            )
        resident_file_open = rom.retarget_program_source_calls(
            rom.RESIDENT_FILE_OPEN_1F1F1A_SOURCE,
            rom.RESIDENT_FILE_OPEN_1F1F1A_SIZE,
            (
                (0x3C221E,
                 rom.APPLICATION_FILE_RECORD_STATUS_LINKED_DESTINATION,
                 rom.APPLICATION_FILE_RECORD_STATUS_OVERLAY_DESTINATION),
                (0x3C225A,
                 rom.APPLICATION_FILE_METADATA_UPDATE_LINKED_DESTINATION,
                 rom.APPLICATION_FILE_METADATA_UPDATE_OVERLAY_DESTINATION),
                (0x3C22D6,
                 rom.APPLICATION_FILE_CLOSE_STATE_LINKED_DESTINATION,
                 rom.APPLICATION_FILE_CLOSE_STATE_OVERLAY_DESTINATION),
                (0x3C2334,
                 rom.APPLICATION_FILE_CLOSE_RECORD_SYNC_LINKED_DESTINATION,
                 rom.APPLICATION_FILE_CLOSE_RECORD_SYNC_OVERLAY_DESTINATION),
                (0x3C2358,
                 0x2D3460,
                 rom.RESIDENT_STORAGE_DRIVER_ADDRESS),
            ),
        )
        metadata_call_index = (
            0x1F225A - rom.RESIDENT_FILE_OPEN_1F1F1A_ADDRESS
        ) // 2
        self.assertEqual(
            resident_file_open[metadata_call_index:metadata_call_index + 2],
            [0xBD00 |
             (rom.APPLICATION_FILE_METADATA_UPDATE_OVERLAY_DESTINATION >> 16),
             rom.APPLICATION_FILE_METADATA_UPDATE_OVERLAY_DESTINATION & 0xFFFF],
        )
        callback_segment = rom.write_program_words(
            rom.APPLICATION_FILE_ENTRY_BUILD_CALLBACK_SEGMENT,
            (rom.APPLICATION_FILE_ENTRY_BUILD_OVERLAY_DESTINATION >> 16,),
        )
        self.assertIn(
            callback_segment,
            [patch[i:i + len(callback_segment)]
             for i in range(len(patch) - len(callback_segment) + 1)],
        )
        for address, _source in (
                rom.APPLICATION_FILE_RECORD_APPLY_CALLBACK_SEGMENTS):
            callback_segment = rom.write_program_words(
                address,
                (rom.APPLICATION_FILE_RECORD_APPLY_OVERLAY_DESTINATION >> 16,),
            )
            self.assertIn(
                callback_segment,
                [patch[i:i + len(callback_segment)]
                 for i in range(len(patch) - len(callback_segment) + 1)],
            )
        for address, _source in (
                rom.APPLICATION_FILE_METADATA_UPDATE_CALLBACK_SEGMENTS):
            callback_segment = rom.write_program_words(
                address,
                (rom.APPLICATION_FILE_METADATA_UPDATE_OVERLAY_DESTINATION >> 16,),
            )
            self.assertIn(
                callback_segment,
                [patch[i:i + len(callback_segment)]
                 for i in range(len(patch) - len(callback_segment) + 1)],
            )
        entry_copy = rom.embed_program_overlay_words(
            rom.APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_DESTINATION,
            rom.APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_SOURCE,
            rom.APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_SIZE,
        )
        entry_call_patch = rom.write_program_words(
            rom.APPLICATION_FILE_ENTRY_BUILD_CALL,
            (0xBD00 | (rom.APPLICATION_FILE_ENTRY_BUILD_OVERLAY_DESTINATION >> 16),
             rom.APPLICATION_FILE_ENTRY_BUILD_OVERLAY_DESTINATION & 0xFFFF),
        )
        copy_index = next(
            index for index in range(len(patch) - len(entry_copy) + 1)
            if patch[index:index + len(entry_copy)] == entry_copy
        )
        call_patch_index = next(
            index for index in range(len(patch) - len(entry_call_patch) + 1)
            if patch[index:index + len(entry_call_patch)] == entry_call_patch
        )
        self.assertGreater(call_patch_index, copy_index)
        cursor_descriptor = rom.embed_program_overlay_words(
            rom.APPLICATION_CURSOR_REFRESH_OVERLAY_DESTINATION,
            rom.APPLICATION_CURSOR_REFRESH_OVERLAY_SOURCE,
            rom.APPLICATION_CURSOR_REFRESH_OVERLAY_SIZE,
        )
        self.assertIn(
            cursor_descriptor,
            [patch[i:i + len(cursor_descriptor)]
             for i in range(len(patch) - len(cursor_descriptor) + 1)],
        )
        foreground_object_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MODAL_FOREGROUND_OBJECT_OVERLAY_DESTINATION,
            rom.APPLICATION_MODAL_FOREGROUND_OBJECT_OVERLAY_SOURCE,
            rom.APPLICATION_MODAL_FOREGROUND_OBJECT_OVERLAY_SIZE,
        )
        cursor_installer = rom.application_cursor_refresh_installer_words()
        self.assertIn(
            foreground_object_descriptor,
            [cursor_installer[i:i + len(foreground_object_descriptor)]
             for i in range(
                 len(cursor_installer) - len(foreground_object_descriptor) + 1
             )],
        )
        self.assertLessEqual(
            rom.APPLICATION_CURSOR_REFRESH_INSTALLER_ADDRESS
            + 2 * len(rom.application_cursor_refresh_installer_words()),
            rom.APPLICATION_MAIN_CURSOR_REFRESH_WRAPPER_ADDRESS,
        )

        late_patch = rom.install_application_main_chain_words()
        for destination, source, size in (
            (rom.APPLICATION_EVENT_GATE_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_GATE_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_GATE_OVERLAY_SIZE),
            (rom.APPLICATION_EVENT_GATE_POWER_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_GATE_POWER_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_GATE_POWER_OVERLAY_SIZE),
        ):
            live_copy = rom.copy_code_to_overlay_words(
                destination, source, size,
            )
            self.assertNotIn(
                live_copy,
                [late_patch[i:i + len(live_copy)]
                 for i in range(len(late_patch) - len(live_copy) + 1)],
            )

        for destination, source, size in (
            (rom.APPLICATION_EVENT_GATE_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_GATE_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_GATE_OVERLAY_SIZE),
            (rom.APPLICATION_EVENT_GATE_POWER_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_GATE_POWER_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_GATE_POWER_OVERLAY_SIZE),
            (rom.ROM03_FAR_MEMCPY_THUNK_DESTINATION,
             rom.ROM03_FAR_MEMCPY_THUNK_SOURCE,
             rom.ROM03_FAR_MEMCPY_THUNK_SIZE),
            (rom.APPLICATION_UI_PREPARE_OVERLAY_DESTINATION,
             rom.APPLICATION_UI_PREPARE_OVERLAY_SOURCE,
             rom.APPLICATION_UI_PREPARE_OVERLAY_SIZE),
            (rom.APPLICATION_UI_PROPERTY_OVERLAY_DESTINATION,
             rom.APPLICATION_UI_PROPERTY_OVERLAY_SOURCE,
             rom.APPLICATION_UI_PROPERTY_OVERLAY_SIZE),
            (rom.APPLICATION_UI_PROPERTY_SET_OVERLAY_DESTINATION,
             rom.APPLICATION_UI_PROPERTY_SET_OVERLAY_SOURCE,
             rom.APPLICATION_UI_PROPERTY_SET_OVERLAY_SIZE),
            (rom.APPLICATION_UI_COMMIT_OVERLAY_DESTINATION,
             rom.APPLICATION_UI_COMMIT_OVERLAY_SOURCE,
             rom.APPLICATION_UI_COMMIT_OVERLAY_SIZE),
        ):
            embedded = rom.embed_program_overlay_words(
                destination, source, size
            )
            self.assertIn(
                embedded,
                [patch[i:i + len(embedded)]
                 for i in range(len(patch) - len(embedded) + 1)],
            )
        cleanup_call = [
            0xBD00 | (
                rom.APPLICATION_FOREGROUND_STATE50_CLEANUP_INSTALLER_ADDRESS
                >> 16
            ),
            rom.APPLICATION_FOREGROUND_STATE50_CLEANUP_INSTALLER_ADDRESS
            & 0xFFFF,
        ]
        self.assertIn(
            cleanup_call,
            [patch[i:i + len(cleanup_call)]
             for i in range(len(patch) - len(cleanup_call) + 1)],
        )
        state_handler_call = [
            0xBD00 | (
                rom.APPLICATION_FOREGROUND_STATE_HANDLER_INSTALLER_ADDRESS
                >> 16
            ),
            rom.APPLICATION_FOREGROUND_STATE_HANDLER_INSTALLER_ADDRESS
            & 0xFFFF,
        ]
        self.assertIn(
            state_handler_call,
            [patch[i:i + len(state_handler_call)]
             for i in range(len(patch) - len(state_handler_call) + 1)],
        )
        state_handler_installer = (
            rom.application_foreground_state_handler_installer_words()
        )
        self.assertEqual(
            state_handler_installer,
            [
                *rom.copy_code_to_overlay_words(
                    rom.APPLICATION_FOREGROUND_MODE_OVERLAY_DESTINATION,
                    rom.APPLICATION_FOREGROUND_MODE_OVERLAY_SOURCE,
                    rom.APPLICATION_FOREGROUND_MODE_OVERLAY_SIZE,
                ),
                *rom.copy_code_to_overlay_words(
                    rom.APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_DESTINATION,
                    rom.APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_SOURCE,
                    rom.APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_SIZE,
                ),
                *rom.copy_code_to_overlay_words(
                    rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_DESTINATION,
                    rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SOURCE,
                    rom.APPLICATION_MENU_PAGE_OBJECTS_OVERLAY_SIZE,
                ),
                *rom.copy_code_to_overlay_words(
                    rom.APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_DESTINATION,
                    rom.APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SOURCE,
                    rom.APPLICATION_MENU_PAGE_LAYOUT_OVERLAY_SIZE,
                ),
                *rom.copy_code_to_overlay_words(
                    rom.APPLICATION_ROOT_STATIC_DISPLAY_OVERLAY_DESTINATION,
                    rom.APPLICATION_ROOT_STATIC_DISPLAY_OVERLAY_SOURCE,
                    rom.APPLICATION_ROOT_STATIC_DISPLAY_OVERLAY_SIZE,
                ),
                0xBD00 | (
                    rom.APPLICATION_ROOT_STREAM_INSTALLER_ADDRESS >> 16
                ),
                rom.APPLICATION_ROOT_STREAM_INSTALLER_ADDRESS & 0xFFFF,
                *rom.copy_code_to_overlay_words(
                    rom.APPLICATION_ROOT_ITEM_MASK_OVERLAY_DESTINATION,
                    rom.APPLICATION_ROOT_ITEM_MASK_OVERLAY_SOURCE,
                    rom.APPLICATION_ROOT_ITEM_MASK_OVERLAY_SIZE,
                ),
                *rom.copy_code_to_overlay_words(
                    rom.APPLICATION_ROOT_HARDWARE_RESET_OVERLAY_DESTINATION,
                    rom.APPLICATION_ROOT_HARDWARE_RESET_OVERLAY_SOURCE,
                    rom.APPLICATION_ROOT_HARDWARE_RESET_OVERLAY_SIZE,
                ),
                *rom.copy_code_to_overlay_words(
                    rom.APPLICATION_ROOT_BITMAP_RENDER_OVERLAY_DESTINATION,
                    rom.APPLICATION_ROOT_BITMAP_RENDER_OVERLAY_SOURCE,
                    rom.APPLICATION_ROOT_BITMAP_RENDER_OVERLAY_SIZE,
                ),
                *rom.embed_program_overlay_words(
                    rom.APPLICATION_FOREGROUND_STATE_HANDLER_OVERLAY_DESTINATION,
                    rom.APPLICATION_FOREGROUND_STATE_HANDLER_OVERLAY_SOURCE,
                    rom.APPLICATION_FOREGROUND_STATE_HANDLER_OVERLAY_SIZE,
                ),
                0xBD00 | (
                    rom.APPLICATION_FOREGROUND_STATE4E_INSTALLER_ADDRESS >> 16
                ),
                rom.APPLICATION_FOREGROUND_STATE4E_INSTALLER_ADDRESS & 0xFFFF,
                rom.RETS,
            ],
        )
        self.assertEqual(
            rom.APPLICATION_FOREGROUND_STATE_HANDLER_INSTALLER_ADDRESS
            + (len(state_handler_installer) - 1) * 2,
            0x1A5FDC,
        )
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_ROOT_STREAM_INSTALLER_ADDRESS,
                len(rom.application_root_stream_installer_words()),
            ),
            rom.application_root_stream_installer_words(),
        )
        self.assertEqual(
            rom.application_root_stream_installer_words(),
            [
                *rom.copy_code_to_overlay_words(
                    rom.APPLICATION_ROOT_STREAM_WRITE_OVERLAY_DESTINATION,
                    rom.APPLICATION_ROOT_STREAM_WRITE_OVERLAY_SOURCE,
                    rom.APPLICATION_ROOT_STREAM_WRITE_OVERLAY_SIZE,
                ),
                *rom.copy_code_to_overlay_words(
                    rom.APPLICATION_ROOT_STREAM_DISPATCH_OVERLAY_DESTINATION,
                    rom.APPLICATION_ROOT_STREAM_DISPATCH_OVERLAY_SOURCE,
                    rom.APPLICATION_ROOT_STREAM_DISPATCH_OVERLAY_SIZE,
                ),
                *rom.embed_program_overlay_words(
                    rom.APPLICATION_ROOT_STREAM_MOVE_OVERLAY_DESTINATION,
                    rom.APPLICATION_ROOT_STREAM_MOVE_OVERLAY_SOURCE,
                    rom.APPLICATION_ROOT_STREAM_MOVE_OVERLAY_SIZE,
                ),
                *rom.copy_code_to_overlay_words(
                    rom.APPLICATION_ROOT_FORMAT_SCAN_OVERLAY_DESTINATION,
                    rom.APPLICATION_ROOT_FORMAT_SCAN_OVERLAY_SOURCE,
                    rom.APPLICATION_ROOT_FORMAT_SCAN_OVERLAY_SIZE,
                ),
                rom.RETS,
            ],
        )
        self.assertLess(
            rom.APPLICATION_ROOT_STREAM_INSTALLER_ADDRESS
            + len(rom.application_root_stream_installer_words()) * 2,
            0x1A8000,
        )
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_FOREGROUND_STATE_HANDLER_INSTALLER_ADDRESS,
                len(state_handler_installer),
            ),
            state_handler_installer,
        )

        post_registry_state = rom.embed_program_overlay_words(
            rom.APPLICATION_POST_REGISTRY_STATE_OVERLAY_DESTINATION,
            rom.APPLICATION_POST_REGISTRY_STATE_OVERLAY_SOURCE,
            rom.APPLICATION_POST_REGISTRY_STATE_OVERLAY_SIZE,
        )
        self.assertIn(
            post_registry_state,
            [patch[i:i + len(post_registry_state)]
             for i in range(len(patch) - len(post_registry_state) + 1)],
        )
        post_registry_bindings = rom.embed_program_overlay_words(
            rom.APPLICATION_POST_REGISTRY_BINDINGS_OVERLAY_DESTINATION,
            rom.APPLICATION_POST_REGISTRY_BINDINGS_OVERLAY_SOURCE,
            rom.APPLICATION_POST_REGISTRY_BINDINGS_OVERLAY_SIZE,
        )
        self.assertIn(
            post_registry_bindings,
            [patch[i:i + len(post_registry_bindings)]
             for i in range(len(patch) - len(post_registry_bindings) + 1)],
        )
        post_registry_bind_target = rom.embed_program_overlay_words(
            rom.APPLICATION_POST_REGISTRY_BIND_TARGET_OVERLAY_DESTINATION,
            rom.APPLICATION_POST_REGISTRY_BIND_TARGET_OVERLAY_SOURCE,
            rom.APPLICATION_POST_REGISTRY_BIND_TARGET_OVERLAY_SIZE,
        )
        self.assertIn(
            post_registry_bind_target,
            [patch[i:i + len(post_registry_bind_target)]
             for i in range(len(patch) - len(post_registry_bind_target) + 1)],
        )
        post_registry_hook = rom.embed_program_overlay_words(
            rom.APPLICATION_POST_REGISTRY_HOOK_OVERLAY_DESTINATION,
            rom.APPLICATION_POST_REGISTRY_HOOK_OVERLAY_SOURCE,
            rom.APPLICATION_POST_REGISTRY_HOOK_OVERLAY_SIZE,
        )
        self.assertIn(
            post_registry_hook,
            [patch[i:i + len(post_registry_hook)]
             for i in range(len(patch) - len(post_registry_hook) + 1)],
        )
        for destination, source, size in (
            (rom.APPLICATION_MAIN_PREPARE_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_PREPARE_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_PREPARE_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_BIT_CLEAR_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_BIT_CLEAR_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_BIT_CLEAR_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_OBJECT_BIND_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_OBJECT_BIND_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_OBJECT_BIND_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_SERVICES_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_SERVICES_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_SERVICES_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_STATE_CLEAR_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STATE_CLEAR_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STATE_CLEAR_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_STATUS_GET_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STATUS_GET_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STATUS_GET_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_RESULT_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_RESULT_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_RESULT_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_ACTION_QUERY_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_ACTION_QUERY_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_ACTION_QUERY_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_SIZE),
            (rom.APPLICATION_FOREGROUND_STATUS_OVERLAY_DESTINATION,
             rom.APPLICATION_FOREGROUND_STATUS_OVERLAY_SOURCE,
             rom.APPLICATION_FOREGROUND_STATUS_OVERLAY_SIZE),
            (rom.APPLICATION_EVENT_FETCH_OVERLAY_DESTINATION,
             rom.APPLICATION_EVENT_FETCH_OVERLAY_SOURCE,
             rom.APPLICATION_EVENT_FETCH_OVERLAY_SIZE),
        ):
            embedded = rom.embed_program_overlay_words(
                destination, source, size
            )
            self.assertIn(
                embedded,
                [patch[i:i + len(embedded)]
                 for i in range(len(patch) - len(embedded) + 1)],
            )

        for call, target in (
            (rom.APPLICATION_MAIN_RESOURCE_CREATE_CALL,
             rom.APPLICATION_MAIN_RESOURCE_CREATE_OVERLAY_DESTINATION),
            (rom.APPLICATION_FOREGROUND_STATUS_CALL,
             rom.APPLICATION_FOREGROUND_STATUS_OVERLAY_DESTINATION),
        ):
            self.assertEqual(target >> 16, 0x5F)
            call_patch = rom.write_program_words(
                call, (0xBD00 | (target >> 16), target & 0xFFFF)
            )
            self.assertIn(
                call_patch,
                [patch[i:i + len(call_patch)]
                 for i in range(len(patch) - len(call_patch) + 1)],
            )

        self.assertEqual(
            rom.APPLICATION_RESULT_MODE_PAIR_OVERLAY_DESTINATION >> 16,
            0x5F,
        )
        for call, source in (
            (rom.APPLICATION_STORAGE_SCAN_MODE_PAIR_CALL,
             rom.APPLICATION_STORAGE_SCAN_MODE_PAIR_CALL_SOURCE),
            (rom.APPLICATION_RESULT_ITEM_RENDER_MODE_PAIR_CALL,
             rom.APPLICATION_RESULT_ITEM_RENDER_MODE_PAIR_CALL_SOURCE),
        ):
            self.assertEqual(
                rom.program_source_words(source, 4), [0xBD33, 0x1BBA]
            )
            call_patch = rom.write_program_words(call, [0xBD5F, 0x1BBA])
            self.assertIn(
                call_patch,
                [patch[i:i + len(call_patch)]
                 for i in range(len(patch) - len(call_patch) + 1)],
            )

        # These two destinations are inside the 2-MiB internal code ROM.
        # They are reconstructed as static ROM bytes, not writable overlays
        # installed by the late guest loader.
        for destination, source, size in (
            (rom.APPLICATION_MAIN_ROM_STATE_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_ROM_STATE_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_ROM_STATE_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_ROM_MENU_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_ROM_MENU_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_ROM_MENU_OVERLAY_SIZE),
            (rom.APPLICATION_MAIN_ROM_COMPOSITOR_DESTINATION,
             rom.APPLICATION_MAIN_ROM_COMPOSITOR_SOURCE,
             rom.APPLICATION_MAIN_ROM_COMPOSITOR_SIZE),
            (rom.APPLICATION_MAIN_ROM_RESOURCE_STATE_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_STATE_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_STATE_SIZE),
            (rom.APPLICATION_MAIN_ROM_RESOURCE_PROBE_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_PROBE_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_PROBE_SIZE),
            (rom.APPLICATION_MAIN_ROM_RESOURCE_TEST_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_TEST_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_TEST_SIZE),
            (rom.APPLICATION_MAIN_ROM_RESOURCE_SCAN_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_SCAN_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_SCAN_SIZE),
            (rom.APPLICATION_MAIN_ROM_RESOURCE_CHECK_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_CHECK_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_CHECK_SIZE),
            (rom.APPLICATION_MAIN_ROM_RESOURCE_XOR_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_XOR_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_XOR_SIZE),
            (rom.APPLICATION_MAIN_ROM_RESOURCE_HEX_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_HEX_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_HEX_SIZE),
            (rom.APPLICATION_MAIN_ROM_RESOURCE_FORMAT_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RESOURCE_FORMAT_SOURCE,
             rom.APPLICATION_MAIN_ROM_RESOURCE_FORMAT_SIZE),
            (rom.APPLICATION_MAIN_ROM_LAYOUT_BUILD_DESTINATION,
             rom.APPLICATION_MAIN_ROM_LAYOUT_BUILD_SOURCE,
             rom.APPLICATION_MAIN_ROM_LAYOUT_BUILD_SIZE),
            (rom.APPLICATION_MAIN_ROM_RENDER_DESTINATION,
             rom.APPLICATION_MAIN_ROM_RENDER_SOURCE,
             rom.APPLICATION_MAIN_ROM_RENDER_SIZE),
            (rom.APPLICATION_COMPARE_ROM_DESTINATION,
             rom.APPLICATION_COMPARE_ROM_SOURCE,
             rom.APPLICATION_COMPARE_ROM_SIZE),
            (rom.APPLICATION_FOREGROUND_ROM_WORKER_DESTINATION,
             rom.APPLICATION_FOREGROUND_ROM_WORKER_SOURCE,
             rom.APPLICATION_FOREGROUND_ROM_WORKER_SIZE),
            (rom.APPLICATION_FOREGROUND_ROM_DISPATCH_DESTINATION,
             rom.APPLICATION_FOREGROUND_ROM_DISPATCH_SOURCE,
             rom.APPLICATION_FOREGROUND_ROM_DISPATCH_SIZE),
        ):
            if destination == rom.APPLICATION_MAIN_ROM_RENDER_DESTINATION:
                expected = rom.application_main_rom_render_words()
            elif destination == rom.APPLICATION_MAIN_ROM_LAYOUT_BUILD_DESTINATION:
                expected = rom.retarget_program_source_calls(
                    source,
                    size,
                    ((
                        0x2F54C8,
                        rom.APPLICATION_NPE_STATE_DISPATCH_LINKED_DESTINATION,
                        rom.APPLICATION_NPE_STATE_DISPATCH_OVERLAY_DESTINATION,
                    ), (
                        0x2F5A1A,
                        rom.APPLICATION_NPE_STATE_DISPATCH_LINKED_DESTINATION,
                        rom.APPLICATION_NPE_STATE_DISPATCH_OVERLAY_DESTINATION,
                    )),
                )
            else:
                expected = rom.program_source_words(source, size)
            self.assertEqual(
                words_at(image, destination, len(expected)), expected
            )

        relocated_input = rom.application_main_rom_input_words()
        self.assertEqual(
            words_at(image, rom.APPLICATION_MAIN_ROM_INPUT_DESTINATION,
                     len(relocated_input)),
            relocated_input,
        )
        self.assertEqual(sum(
            relocated_input[index:index + 2] == [0xBD11, 0x2B6E]
            for index in range(len(relocated_input) - 1)
        ), 18)
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_MAIN_ACTION_RENDER_INPUT_CALL_SOURCE, 4
            ),
            [0xBD2E, 0x2B6E],
        )
        helper = rom.program_source_words(
            rom.APPLICATION_MAIN_ACTION_RENDER_HELPER_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_ACTION_RENDER_HELPER_OVERLAY_SIZE,
        )
        self.assertEqual(helper[:1], [0x2E03])
        self.assertEqual(helper[-2:], [0x2F00, rom.RETS])
        self.assertEqual(sum(
            helper[index:index + 2] in ([0xBD32, 0xEC6E],
                                        [0xBD33, 0x66E2])
            for index in range(len(helper) - 1)
        ), 2)
        helper_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MAIN_ACTION_RENDER_HELPER_OVERLAY_DESTINATION,
            rom.APPLICATION_MAIN_ACTION_RENDER_HELPER_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_ACTION_RENDER_HELPER_OVERLAY_SIZE,
        )
        wrong_renderer_call_patch = rom.write_program_words(
            rom.APPLICATION_MAIN_ACTION_RENDER_INPUT_CALL,
            [0xBD11, 0x2B6E],
        )
        main_installer = rom.install_application_main_chain_words()
        self.assertIn(
            helper_descriptor,
            [main_installer[i:i + len(helper_descriptor)]
             for i in range(
                len(main_installer) - len(helper_descriptor) + 1
             )],
        )
        self.assertNotIn(
            wrong_renderer_call_patch,
            [main_installer[i:i + len(wrong_renderer_call_patch)]
             for i in range(
                len(main_installer) - len(wrong_renderer_call_patch) + 1
             )],
        )

        # The apparent 2C collision is an original ROM lifecycle: the complete
        # 2C:7E18 source controller first belongs at its 13 callers' resident
        # 0F:7E18 target.  The source subrange can then receive the exact
        # same-PC 49:8744 renderer layout overlay without losing the controller.
        controller = rom.program_source_words(
            rom.RESIDENT_GAME_WORLD_CONTROLLER_SOURCE,
            rom.RESIDENT_GAME_WORLD_CONTROLLER_SIZE,
        )
        self.assertEqual(
            controller[:8],
            [0x2E16, 0x58F1, 0x58F2, 0x58F3,
             0x58F4, 0x58F5, 0x58F6, 0x58F7],
        )
        self.assertEqual(controller[-2:], [0x2F00, rom.RETS])
        controller_calls = (
            (0x2C83D4, 0x2D0B00),
            (0x2C87F8, 0x1CD462),
            (0x2C8944, 0x1CD462),
            (0x2C8B82, 0x1CD462),
            (0x2C8C58, 0x335B70),
            (0x2C8C64, 0x328E5C),
            (0x2C8C9E, 0x3009F2),
            (0x2C8CEC, 0x3307B0),
            (0x2C8D46, 0x2E6822),
            (0x2C8D64, 0x0DB1C0),
            (0x2C8DB6, 0x3307B0),
            (0x2C8F06, 0x1CD462),
            (0x2C9066, 0x31AED0),
            (0x2C9094, 0x1CD462),
            (0x2C9124, 0x1E9E66),
            (0x2C91C0, 0x2BDB86),
            (0x2C920E, 0x3307B0),
            (0x2C92F6, 0x1CD462),
            (0x2C9428, 0x31AED0),
            (0x2C9456, 0x1CD462),
            (0x2C9550, 0x3307B0),
            (0x2C97F6, 0x3307B0),
            (0x2C98B4, 0x3307B0),
            (0x2C99A4, 0x1CD462),
            (0x2C9ADE, 0x31AED0),
            (0x2C9B0C, 0x1CD462),
        )
        self.assertEqual(len(controller_calls), 26)
        for call_address, target in controller_calls:
            self.assertEqual(
                rom.program_source_words(call_address, 4),
                [0xBD00 | (target >> 16), target & 0xFFFF],
            )
        self.assertEqual(
            words_at(image, rom.RESIDENT_GAME_WORLD_CONTROLLER_ADDRESS,
                     len(controller)),
            controller,
        )
        controller_table = rom.program_source_words(
            rom.RESIDENT_GAME_WORLD_CONTROLLER_TABLE_SOURCE,
            rom.RESIDENT_GAME_WORLD_CONTROLLER_TABLE_SIZE,
        )
        self.assertEqual(
            controller_table,
            [0x834E, 0x83DE, 0x7EC0, 0x7FB2, 0x81B4,
             0x80D4, 0x8452, 0x9B80, 0x9B80, 0x9B80,
             0x9B80, 0x9B80, 0x9B80, 0x9B80, 0x82BC],
        )
        self.assertEqual(
            words_at(image,
                     rom.RESIDENT_GAME_WORLD_CONTROLLER_TABLE_ADDRESS,
                     len(controller_table)),
            controller_table,
        )
        self.assertEqual(
            rom.PROGRAM_SOURCE.read_bytes().count(b"\x0f\xbd\x18\x7e"),
            13,
        )
        controller_info = rom.manifest(image)["resident_game_world_controller"]
        self.assertEqual(controller_info["destination"], "0F:7E18")
        self.assertEqual(controller_info["source"], "2C:7E18")
        self.assertEqual(controller_info["bytes"], 0x1D7E)

        # The controller's two missing resident callees are complete linked
        # functions, not application RAM overlays.  The event dispatcher also
        # owns a ten-entry computed-RET table that must be present in the SoC
        # ROM image for QEMU's narrow Harvard data alias.
        event_dispatch = rom.program_source_words(
            rom.RESIDENT_GAME_WORLD_EVENT_DISPATCH_SOURCE,
            rom.RESIDENT_GAME_WORLD_EVENT_DISPATCH_SIZE,
        )
        self.assertEqual(
            event_dispatch[:8],
            [0x2E73, 0x58F1, 0x58F2, 0x58F3,
             0x58F4, 0x58F5, 0x58F6, 0x58F7],
        )
        self.assertEqual(event_dispatch[-2:], [0x2F00, rom.RETS])
        self.assertEqual(
            words_at(image, rom.RESIDENT_GAME_WORLD_EVENT_DISPATCH_ADDRESS,
                     len(event_dispatch)),
            event_dispatch,
        )
        self.assertEqual(
            rom.program_source_words(
                rom.RESIDENT_GAME_WORLD_EVENT_DISPATCH_SOURCE
                + rom.RESIDENT_GAME_WORLD_EVENT_DISPATCH_SIZE,
                2,
            ),
            [0x2E57],
        )
        event_table = rom.program_source_words(
            rom.RESIDENT_GAME_WORLD_EVENT_DISPATCH_TABLE_SOURCE,
            rom.RESIDENT_GAME_WORLD_EVENT_DISPATCH_TABLE_SIZE,
        )
        self.assertEqual(
            event_table,
            [0xB434, 0xB6D4, 0xBA7E, 0xBE16, 0xD80C,
             0xD80C, 0xC68E, 0xC68E, 0xC68E, 0xC196],
        )
        self.assertEqual(
            words_at(image,
                     rom.RESIDENT_GAME_WORLD_EVENT_DISPATCH_TABLE_ADDRESS,
                     len(event_table)),
            event_table,
        )

        object_service = rom.program_source_words(
            rom.RESIDENT_GAME_WORLD_OBJECT_SERVICE_SOURCE,
            rom.RESIDENT_GAME_WORLD_OBJECT_SERVICE_SIZE,
        )
        self.assertEqual(
            object_service[:5],
            [0x2E09, 0x58F0, 0x58F1, 0x58F2, 0x58F3],
        )
        self.assertEqual(object_service[-2:], [0x2F00, rom.RETS])
        self.assertEqual(
            words_at(image, rom.RESIDENT_GAME_WORLD_OBJECT_SERVICE_ADDRESS,
                     len(object_service)),
            object_service,
        )
        self.assertEqual(
            rom.program_source_words(
                rom.RESIDENT_GAME_WORLD_OBJECT_SERVICE_SOURCE
                + rom.RESIDENT_GAME_WORLD_OBJECT_SERVICE_SIZE,
                2,
            ),
            [0x2E0F],
        )

        for destination, source, size in (
                rom.GAME_WORLD_CONTROLLER_APPLICATION_OVERLAYS):
            shipped = rom.program_source_words(source, size)
            self.assertEqual(shipped[0] & 0xFF00, 0x2E00)
            self.assertEqual(shipped[-1], rom.RETS)
            descriptor = rom.copy_code_to_overlay_words(
                destination, source, size
            )
            self.assertIn(
                descriptor,
                [main_installer[i:i + len(descriptor)]
                 for i in range(len(main_installer) - len(descriptor) + 1)],
            )

        self.assertEqual(
            controller_info["resident_dependencies"],
            [
                {
                    "destination": "0D:B1C0",
                    "source": "2A:B1C0",
                    "bytes": 0x2892,
                    "harvard_data_table": "0D:B420+0x14",
                },
                {
                    "destination": "1E:9E66",
                    "source": "3B:9E66",
                    "bytes": 0x0668,
                },
            ],
        )
        self.assertEqual(len(controller_info["application_dependencies"]), 9)

        for _destination_call, source_call in (
                rom.APPLICATION_MAIN_RENDER_LAYOUT_CALLS):
            self.assertEqual(
                rom.program_source_words(source_call, 4),
                [0xBD2C, 0x8744],
            )
        self.assertNotEqual(
            rom.program_source_words(
                rom.APPLICATION_MAIN_RENDER_LAYOUT_OVERLAY_DESTINATION, 2
            ),
            [0x2E00],
        )
        render_layout = rom.program_source_words(
            rom.APPLICATION_MAIN_RENDER_LAYOUT_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_RENDER_LAYOUT_OVERLAY_SIZE,
        )
        self.assertEqual(render_layout[:1], [0x2E00])
        self.assertEqual(render_layout[-2:], [0x2F00, rom.RETS])
        self.assertEqual(sum(
            render_layout[index:index + 2] == [0xBD32, 0xB922]
            for index in range(len(render_layout) - 1)
        ), 1)
        self.assertEqual(sum(
            render_layout[index:index + 2] == [0xBD32, 0xDB08]
            for index in range(len(render_layout) - 1)
        ), 10)
        render_layout_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MAIN_RENDER_LAYOUT_OVERLAY_DESTINATION,
            rom.APPLICATION_MAIN_RENDER_LAYOUT_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_RENDER_LAYOUT_OVERLAY_SIZE,
        )
        self.assertIn(
            render_layout_descriptor,
            [main_installer[i:i + len(render_layout_descriptor)]
             for i in range(
                 len(main_installer) - len(render_layout_descriptor) + 1
             )],
        )
        main_modules = {
            item["destination"]: item
            for item in rom.manifest(image)["application_main_chain"]
        }
        self.assertEqual(main_modules["2C:8744"]["source"], "49:8744")
        self.assertEqual(main_modules["2C:8744"]["bytes"], 0x01EE)

        # 30:6082 is a linked application entry, not the flat mid-function
        # bytes at that address.  The exact source is a closed LINK #0 body
        # ending immediately before the next 4D:6186 function.
        self.assertNotEqual(
            rom.program_source_words(
                rom.APPLICATION_MAIN_RENDER_FINALIZE_OVERLAY_DESTINATION, 2
            ),
            [0x2E00],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_MAIN_RENDER_FINALIZE_OVERLAY_SOURCE, 2
            ),
            [0x2E00],
        )
        render_finalize_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MAIN_RENDER_FINALIZE_OVERLAY_DESTINATION,
            rom.APPLICATION_MAIN_RENDER_FINALIZE_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_RENDER_FINALIZE_OVERLAY_SIZE,
        )
        self.assertIn(
            render_finalize_descriptor,
            [main_installer[i:i + len(render_finalize_descriptor)]
             for i in range(
                 len(main_installer) - len(render_finalize_descriptor) + 1
             )],
        )
        self.assertEqual(main_modules["30:6082"]["source"], "4D:6082")
        self.assertEqual(main_modules["30:6082"]["bytes"], 0x0104)

        loader = rom.post_initializer_overlay_words(
            probe_system_main=True
        )
        top_level_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_TOP_LEVEL_OVERLAY_DESTINATION,
            rom.APPLICATION_TOP_LEVEL_OVERLAY_SOURCE,
            rom.APPLICATION_TOP_LEVEL_OVERLAY_SIZE,
        )
        self.assertEqual(
            sum(loader[i:i + len(top_level_descriptor)] ==
                top_level_descriptor
                for i in range(len(loader) - len(top_level_descriptor) + 1)),
            1,
        )
        rom01_loader = rom.rom01_application_loader_words()
        self.assertIn(
            top_level_descriptor,
            [rom01_loader[i:i + len(top_level_descriptor)]
             for i in range(
                 len(rom01_loader) - len(top_level_descriptor) + 1)],
        )
        startup_call = next(
            i for i in range(len(loader) - 1)
            if loader[i:i + 2] == [0xBD20, 0x026A]
        )
        self.assertEqual(loader[startup_call:startup_call + 2], [
            0xBD20, 0x026A,
        ])
        self.assertEqual(startup_call, len(loader) - 4)
        self.assertEqual(loader[-4:], [
            0xBD20, 0x026A, 0xAD03, rom.POST_INITIALIZER_HANDOFF_PC,
        ])
        self.assertNotIn(rom.RESERVED, loader[startup_call:])
        probe = rom.build_image(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_rom_01_return=True,
            probe_system_main=True,
        )
        probe_info = rom.manifest(
            probe,
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_rom_01_return=True,
            probe_system_main=True,
        )
        self.assertTrue(probe_info["probe_system_main"])
        handoff = rom.boot_frame_handoff_words()
        self.assertEqual(words_at(
            probe, 0x030000 | rom.POST_INITIALIZER_HANDOFF_PC, len(handoff)
        ), handoff)
        self.assertEqual(handoff[-2:], [0xAD20, 0x0004])
        self.assertEqual(
            len(probe_info["application_main_chain"]),
            364 + len(rom.APPLICATION_FACTORY_DEFAULT_COPY_OVERLAYS) +
            len(rom.APPLICATION_FACTORY_DEFAULT_EMBEDDED_OVERLAYS),
        )
        self.assertEqual(
            [module for module in probe_info["application_main_chain"]
             if module["destination"] in ("20:0B82", "31:138C")],
            [
                {
                    "destination": "20:0B82",
                    "source": "3D:0B82",
                    "bytes": 0x0A98,
                    "status": "exact same-PC guest function",
                },
                {
                    "destination": "31:138C",
                    "source": "4E:138C",
                    "bytes": 0x00CE,
                    "status": "exact same-PC guest function",
                },
            ],
        )
        self.assertEqual(len(probe_info["lcd_resource_dispatch_chain"]), 3)
        thunk_source = rom.program_source_words(
            rom.LCD_RESOURCE_DISPATCH_THUNK_SOURCE,
            rom.LCD_RESOURCE_DISPATCH_THUNK_SIZE,
        )
        self.assertEqual(thunk_source, [0xAD29, 0xAC4E])
        transfer_source = rom.program_source_words(
            rom.LCD_RESOURCE_TRANSFER_OVERLAY_SOURCE,
            rom.LCD_RESOURCE_TRANSFER_OVERLAY_SIZE,
        )
        self.assertEqual(transfer_source[:7],
                         [0x2E06, 0x58F0, 0x58F1, 0x58F2,
                          0x58F3, 0x58F4, 0x58F5])
        self.assertEqual(transfer_source[-8:],
                         [0x385F, 0x384F, 0x383F, 0x382F,
                          0x381F, 0x380F, 0x2F00, rom.RETS])
        page_source = rom.program_source_words(
            rom.APPLICATION_RESOURCE_PAGE_READ_OVERLAY_SOURCE,
            rom.APPLICATION_RESOURCE_PAGE_READ_OVERLAY_SIZE,
        )
        self.assertEqual(
            rom.APPLICATION_RESOURCE_PAGE_READ_LINKED_DESTINATION,
            0x2D261C,
        )
        self.assertEqual(
            rom.APPLICATION_RESOURCE_PAGE_READ_OVERLAY_DESTINATION,
            0x5F261C,
        )
        self.assertEqual(page_source[:5],
                         [0x2E05, 0x58F1, 0x58F2, 0x58F3, 0x58F5])
        self.assertIn([0xBD2C, 0x2EBA],
                      [page_source[i:i + 2]
                       for i in range(len(page_source) - 1)])
        self.assertEqual(page_source[-6:],
                         [0x385F, 0x383F, 0x382F, 0x381F,
                          0x2F00, rom.RETS])
        expected_call_retargets = []
        for source, destination in zip(
                rom.APPLICATION_RESOURCE_PAGE_READ_CALL_SOURCES,
                rom.APPLICATION_RESOURCE_PAGE_READ_CALL_DESTINATIONS,
                strict=True):
            self.assertEqual(
                rom.program_source_words(source, 4),
                [0xBD2D, 0x261C],
            )
            expected_call_retargets.extend(rom.write_program_words(
                destination,
                [0xBD5F, 0x261C],
            ))
        self.assertEqual(
            rom.application_resource_page_read_call_retarget_words(),
            expected_call_retargets,
        )
        copy_source = rom.program_source_words(
            rom.APPLICATION_FAR_BLOCK_COPY_OVERLAY_SOURCE,
            rom.APPLICATION_FAR_BLOCK_COPY_OVERLAY_SIZE,
        )
        self.assertEqual(copy_source[:5],
                         [0x2E08, 0x58F0, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(copy_source[-6:],
                         [0x383F, 0x382F, 0x381F, 0x380F,
                          0x2F00, rom.RETS])
        with self.assertRaisesRegex(ValueError, "system-main"):
            rom.build_image(probe_system_main=True)

    def test_application_main_input_event_table_is_exact_harvard_data(
            self) -> None:
        image = rom.build_image()
        input_event_targets = [
            0x1E36, 0x2016, 0x196A, 0x1BDA, 0x21AC, 0x23A6, 0x2A1A,
            0x2A1A, 0x2A1A, 0x26DC, 0x2A1A, 0x2A1A, 0x2A1A, 0x29C8,
        ]

        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_MAIN_ROM_INPUT_EVENT_TABLE_ADDRESS,
                len(input_event_targets),
            ),
            input_event_targets,
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_MAIN_ROM_INPUT_EVENT_TABLE_SOURCE,
                rom.APPLICATION_MAIN_ROM_INPUT_EVENT_TABLE_SIZE,
            ),
            input_event_targets,
        )
        self.assertEqual(
            rom.manifest(image)["resident_application_main_input_event_table"],
            {
                "destination": "11:18D4",
                "source": "2E:18D4",
                "bytes": 0x1C,
                "events": "80..8D",
                "targets": [
                    "11:1E36", "11:2016", "11:196A", "11:1BDA",
                    "11:21AC", "11:23A6", "11:2A1A", "11:2A1A",
                    "11:2A1A", "11:26DC", "11:2A1A", "11:2A1A",
                    "11:2A1A", "11:29C8",
                ],
                "status": (
                    "exact inline RET-dispatch table; Harvard data alias"
                ),
            },
        )

    def test_initializer_clock_validator_replaces_flat_shared_epilogue(self) -> None:
        initializer = rom.program_source_words(
            rom.APPLICATION_INIT_ENTRY_OVERLAY_SOURCE,
            rom.APPLICATION_INIT_ENTRY_OVERLAY_SIZE,
        )
        call_index = (0x3F99BC - rom.APPLICATION_INIT_ENTRY_OVERLAY_SOURCE) // 2
        self.assertEqual(initializer[call_index:call_index + 2],
                         [0xBD2F, 0x4D94])

        validator = rom.program_source_words(
            rom.APPLICATION_CLOCK_VALIDATE_OVERLAY_SOURCE,
            rom.APPLICATION_CLOCK_VALIDATE_OVERLAY_SIZE,
        )
        self.assertEqual(validator[:3], [0x2E08, 0x58F0, 0x58F1])
        self.assertEqual(validator[-4:], [0x381F, 0x380F, 0x2F00, rom.RETS])

        call_index = (0x3F99C0 - rom.APPLICATION_INIT_ENTRY_OVERLAY_SOURCE) // 2
        self.assertEqual(initializer[call_index:call_index + 2],
                         [0xBD31, 0x6010])
        global_init = rom.program_source_words(
            rom.APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_SOURCE,
            rom.APPLICATION_SYSTEM_GLOBAL_INIT_OVERLAY_SIZE,
        )
        self.assertEqual(global_init[:5],
                         [0x2E00, 0x58F0, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(global_init[-6:],
                         [0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS])

        call_index = (0x3F99C4 - rom.APPLICATION_INIT_ENTRY_OVERLAY_SOURCE) // 2
        self.assertEqual(initializer[call_index:call_index + 2],
                         [0xBD32, 0xBA18])
        latch_init = rom.program_source_words(
            rom.APPLICATION_SERVICE_LATCH_INIT_OVERLAY_SOURCE,
            rom.APPLICATION_SERVICE_LATCH_INIT_OVERLAY_SIZE,
        )
        self.assertEqual(latch_init[:3], [0x2E00, 0x58F0, 0x58F1])
        self.assertEqual(latch_init[-4:],
                         [0x381F, 0x380F, 0x2F00, rom.RETS])

        for prefix in (
            "APPLICATION_LOCALE_DEFAULT_INIT",
            "APPLICATION_INIT_31_1528",
            "APPLICATION_INIT_08_2EDC",
            "APPLICATION_INIT_33_356E",
            "APPLICATION_INIT_33_3406",
            "APPLICATION_INIT_08_3324",
            "APPLICATION_INIT_33_3FD6",
            "APPLICATION_INIT_29_C126",
            "APPLICATION_OPERATION_UI_INIT",
            "APPLICATION_INIT_33_09B8",
            "APPLICATION_INIT_32_4D1C",
            "APPLICATION_INIT_32_3232",
            "APPLICATION_INIT_31_C3FC",
            "APPLICATION_INIT_32_519E",
            "APPLICATION_INIT_32_F3C6",
            "APPLICATION_INIT_31_B6FC",
            "APPLICATION_INIT_31_CC84",
        ):
            words = rom.program_source_words(
                getattr(rom, f"{prefix}_OVERLAY_SOURCE"),
                getattr(rom, f"{prefix}_OVERLAY_SIZE"),
            )
            self.assertEqual(words[0] & 0xFF00, 0x2E00, prefix)
            self.assertEqual(words[-2:], [0x2F00, rom.RETS], prefix)

    def test_rom_03_407c_uses_exact_string_copy_overlay_chain(self) -> None:
        image = rom.build_image()
        self.assertEqual(words_at(image, 0x03407C, 2), [0xAD32, 0x945C])

        installer = rom.install_runtime_overlay_words()
        info = rom.manifest(image)
        modules = {
            item["destination"]: item
            for item in info["nested_system_overlays"]
        }
        for destination, source, size, label in (
            (rom.FAR_STRING_COPY_OVERLAY_DESTINATION,
             rom.FAR_STRING_COPY_OVERLAY_SOURCE,
             rom.FAR_STRING_COPY_OVERLAY_SIZE, "32:945C"),
            (rom.FAR_MEMORY_COPY_OVERLAY_DESTINATION,
             rom.FAR_MEMORY_COPY_OVERLAY_SOURCE,
             rom.FAR_MEMORY_COPY_OVERLAY_SIZE, "2E:4572"),
        ):
            source_words = rom.program_source_words(source, size)
            self.assertEqual(source_words[0] & 0xFF00, 0x2E00)
            self.assertEqual(source_words[-1], rom.RETS)
            descriptor = rom.copy_code_to_overlay_words(
                destination, source, size
            )
            self.assertIn(
                descriptor,
                [installer[i:i + len(descriptor)]
                 for i in range(len(installer) - len(descriptor) + 1)],
            )
            self.assertEqual(modules[label]["bytes"], size)

    def test_event_packet_uses_exact_static_label_data(self) -> None:
        image = rom.build_image()
        installer = rom.install_runtime_overlay_words()
        source = rom.program_source_bytes(
            rom.APPLICATION_EVENT_TEXT_DATA_OVERLAY_SOURCE,
            rom.APPLICATION_EVENT_TEXT_DATA_OVERLAY_SIZE,
        )
        modules = {
            item["destination"]: item
            for item in rom.manifest(image)["application_main_chain"]
        }

        self.assertEqual(source[0x08:0x0F], b"KK[ ] \x00")
        self.assertEqual(source[0x10:0x17], b"PI A [\x00")
        self.assertEqual(source[0x18:0x1D], b"KK[ \x00")
        self.assertEqual(source[0x3A:0x3F], b"PI A\x00")
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_EVENT_TEXT_DATA_OVERLAY_DESTINATION,
            rom.APPLICATION_EVENT_TEXT_DATA_OVERLAY_SOURCE,
            rom.APPLICATION_EVENT_TEXT_DATA_OVERLAY_SIZE,
        )
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(modules["32:E86E"]["bytes"],
                         rom.APPLICATION_EVENT_TEXT_DATA_OVERLAY_SIZE)

    def test_userinfo_path_literals_are_exact_embedded_data(self) -> None:
        image = rom.build_image()
        installer = rom.install_application_main_chain_words()
        source = rom.program_source_bytes(
            rom.APPLICATION_USERINFO_LITERAL_OVERLAY_SOURCE,
            rom.APPLICATION_USERINFO_LITERAL_OVERLAY_SIZE,
        )
        visible = b"".join(
            word.to_bytes(2, "big")
            for word in rom.program_source_words(
                rom.APPLICATION_USERINFO_LITERAL_OVERLAY_SOURCE,
                rom.APPLICATION_USERINFO_LITERAL_OVERLAY_SIZE,
            )
        )
        descriptor = rom.embed_program_data_words(
            rom.APPLICATION_USERINFO_LITERAL_OVERLAY_DESTINATION,
            rom.APPLICATION_USERINFO_LITERAL_OVERLAY_SOURCE,
            rom.APPLICATION_USERINFO_LITERAL_OVERLAY_SIZE,
        )
        info = rom.manifest(image)["application_userinfo_literals"]

        self.assertIn(b"0:\\USERINFO.SYS\x00", visible)
        self.assertIn(b"NP560+\x00\x00", visible)
        self.assertTrue(visible.endswith(b"NP560+\x00\x00"))
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(info["destination"], "31:937C")
        self.assertEqual(info["bytes"], len(source))

    def test_event_renderer_uses_exact_helper_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_EVENT_RENDER_HELPER_OVERLAY_SOURCE,
            rom.APPLICATION_EVENT_RENDER_HELPER_OVERLAY_SIZE,
        )
        installer = rom.install_application_main_chain_words()
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_EVENT_RENDER_HELPER_OVERLAY_DESTINATION,
            rom.APPLICATION_EVENT_RENDER_HELPER_OVERLAY_SOURCE,
            rom.APPLICATION_EVENT_RENDER_HELPER_OVERLAY_SIZE,
        )

        self.assertEqual(source[:4], [0x2E06, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(source[-5:],
                         [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )

    def test_text_loop_uses_exact_glyph_draw_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_GLYPH_DRAW_OVERLAY_SOURCE,
            rom.APPLICATION_GLYPH_DRAW_OVERLAY_SIZE,
        )
        installer = rom.install_runtime_overlay_words()
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_GLYPH_DRAW_OVERLAY_DESTINATION,
            rom.APPLICATION_GLYPH_DRAW_OVERLAY_SOURCE,
            rom.APPLICATION_GLYPH_DRAW_OVERLAY_SIZE,
        )
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["nested_system_overlays"]
        }

        self.assertEqual(source[0], 0x2E05)
        self.assertEqual(source[-1], rom.RETS)
        self.assertEqual(len(source) * 2, 0x02C8)
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["28:FD38"]["bytes"],
            rom.APPLICATION_GLYPH_DRAW_OVERLAY_SIZE,
        )

    def test_page_renderer_uses_exact_wrapped_text_draw_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_WRAPPED_TEXT_DRAW_OVERLAY_SOURCE,
            rom.APPLICATION_WRAPPED_TEXT_DRAW_OVERLAY_SIZE,
        )
        installer = rom.install_runtime_overlay_words()
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_WRAPPED_TEXT_DRAW_OVERLAY_DESTINATION,
            rom.APPLICATION_WRAPPED_TEXT_DRAW_OVERLAY_SOURCE,
            rom.APPLICATION_WRAPPED_TEXT_DRAW_OVERLAY_SIZE,
        )
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["nested_system_overlays"]
        }

        self.assertEqual(source[:4], [0x2E04, 0x58F0, 0x58F1, 0x58F3])
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        self.assertEqual(len(source) * 2, 0x0158)
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(modules["2F:0000"]["bytes"], 0x0158)

    def test_character_draw_dispatcher_is_exact_overlay(self) -> None:
        source = rom.program_source_words(
            rom.CHARACTER_DRAW_OVERLAY_SOURCE,
            rom.CHARACTER_DRAW_OVERLAY_SIZE,
        )
        installer = rom.install_runtime_overlay_words()
        descriptor = rom.copy_code_to_overlay_words(
            rom.CHARACTER_DRAW_OVERLAY_DESTINATION,
            rom.CHARACTER_DRAW_OVERLAY_SOURCE,
            rom.CHARACTER_DRAW_OVERLAY_SIZE,
        )
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["nested_system_overlays"]
        }

        self.assertEqual(source[:2], [0x2E00, 0x58F0])
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(modules["32:7C0E"]["bytes"], 0x0066)

    def test_far_string_concat_is_exact_overlay(self) -> None:
        source = rom.program_source_words(
            rom.FAR_STRING_CONCAT_OVERLAY_SOURCE,
            rom.FAR_STRING_CONCAT_OVERLAY_SIZE,
        )
        installer = rom.install_runtime_overlay_words()
        descriptor = rom.copy_code_to_overlay_words(
            rom.FAR_STRING_CONCAT_OVERLAY_DESTINATION,
            rom.FAR_STRING_CONCAT_OVERLAY_SOURCE,
            rom.FAR_STRING_CONCAT_OVERLAY_SIZE,
        )
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["nested_system_overlays"]
        }

        self.assertEqual(source[:2], [0x2E00, 0x1F10])
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(modules["32:8204"]["bytes"], 0x0064)

    def test_record_layout_path_is_exact_overlay(self) -> None:
        installer = rom.install_runtime_overlay_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["nested_system_overlays"]
        }

        for destination, source_address, size, first_word in (
            (rom.RECORD_LAYOUT_WRAPPER_OVERLAY_DESTINATION,
             rom.RECORD_LAYOUT_WRAPPER_OVERLAY_SOURCE,
             rom.RECORD_LAYOUT_WRAPPER_OVERLAY_SIZE,
             0x2E07),
            (rom.RECORD_LAYOUT_BUILD_OVERLAY_DESTINATION,
             rom.RECORD_LAYOUT_BUILD_OVERLAY_SOURCE,
             rom.RECORD_LAYOUT_BUILD_OVERLAY_SIZE,
             0x2E02),
        ):
            source = rom.program_source_words(source_address, size)
            descriptor = rom.copy_code_to_overlay_words(
                destination, source_address, size,
            )
            self.assertEqual(source[0], first_word)
            self.assertEqual(source[-2:], [0x2F00, rom.RETS])
            self.assertIn(
                descriptor,
                [installer[i:i + len(descriptor)]
                 for i in range(len(installer) - len(descriptor) + 1)],
            )

        self.assertEqual(modules["32:8268"]["bytes"], 0x0064)
        self.assertEqual(modules["22:FD9E"]["bytes"], 0x0260)

    def test_application_input_mask_path_is_exact_overlay(self) -> None:
        installer = rom.install_runtime_overlay_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["nested_system_overlays"]
        }

        for destination, source_address, size, first_word in (
            (rom.APPLICATION_INPUT_MASK_OVERLAY_DESTINATION,
             rom.APPLICATION_INPUT_MASK_OVERLAY_SOURCE,
             rom.APPLICATION_INPUT_MASK_OVERLAY_SIZE,
             0x2E00),
            (rom.INPUT_MASK_APPLY_OVERLAY_DESTINATION,
             rom.INPUT_MASK_APPLY_OVERLAY_SOURCE,
             rom.INPUT_MASK_APPLY_OVERLAY_SIZE,
             0x2E04),
        ):
            source = rom.program_source_words(source_address, size)
            descriptor = rom.copy_code_to_overlay_words(
                destination, source_address, size,
            )
            self.assertEqual(source[0], first_word)
            self.assertEqual(source[-2:], [0x2F00, rom.RETS])
            self.assertIn(
                descriptor,
                [installer[i:i + len(descriptor)]
                 for i in range(len(installer) - len(descriptor) + 1)],
            )

        self.assertEqual(modules["31:C224"]["bytes"], 0x009E)
        self.assertEqual(modules["31:5014"]["bytes"], 0x00BC)

    def test_application_display_state_is_exact_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_DISPLAY_STATE_OVERLAY_SOURCE,
            rom.APPLICATION_DISPLAY_STATE_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_DISPLAY_STATE_OVERLAY_DESTINATION,
            rom.APPLICATION_DISPLAY_STATE_OVERLAY_SOURCE,
            rom.APPLICATION_DISPLAY_STATE_OVERLAY_SIZE,
        )
        installer = rom.install_runtime_overlay_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["nested_system_overlays"]
        }

        self.assertEqual(source[0], 0x2E03)
        self.assertIn(
            [0xA8F2, 0x27EA],
            [source[i:i + 2] for i in range(len(source) - 1)],
        )
        self.assertIn(
            [0xA8F0, 0x29A0, 0xA8F1, 0x29A2],
            [source[i:i + 4] for i in range(len(source) - 3)],
        )
        self.assertIn(
            [0xBD30, 0xFE0E],
            [source[i:i + 2] for i in range(len(source) - 1)],
        )
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(modules["30:8C1C"]["bytes"], 0x00F6)

    def test_foreground_mode_installer_replaces_flat_branch_tail(self) -> None:
        flat = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_MODE_OVERLAY_DESTINATION,
            0x0004,
        )
        source = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_MODE_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_MODE_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FOREGROUND_MODE_OVERLAY_DESTINATION,
            rom.APPLICATION_FOREGROUND_MODE_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_MODE_OVERLAY_SIZE,
        )
        installer = rom.application_foreground_state_handler_installer_words()
        region_installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        # The flat entry is the middle of the preceding signed-extension
        # diamond, not a framed callable function.
        self.assertEqual(flat, [0xD001, 0x4820])
        self.assertEqual(source[:7], [
            0x2E03, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4, 0x58F5,
        ])
        self.assertEqual(source[-8:], [
            0x385F, 0x384F, 0x383F, 0x382F,
            0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        calls = [
            source[index:index + 2]
            for index in range(len(source) - 1)
            if (source[index] & 0xFF00) == 0xBD00
        ]
        self.assertEqual(calls.count([0xBD03, 0x4010]), 20)
        self.assertEqual(calls.count([0xBD03, 0x401C]), 2)
        self.assertEqual(calls.count([0xBD03, 0x406C]), 1)
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertIn(
            [0xBD00 | (
                 rom.APPLICATION_FOREGROUND_STATE_HANDLER_INSTALLER_ADDRESS
                 >> 16
             ),
             rom.APPLICATION_FOREGROUND_STATE_HANDLER_INSTALLER_ADDRESS
             & 0xFFFF],
            [region_installer[index:index + 2]
             for index in range(len(region_installer) - 1)],
        )
        self.assertEqual(
            modules["22:23C4"]["bytes"],
            rom.APPLICATION_FOREGROUND_MODE_OVERLAY_SIZE,
        )

    def test_root_menu_mode_query_replaces_flat_unframed_entry(self) -> None:
        flat = rom.program_source_words(
            rom.APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_DESTINATION,
            0x0004,
        )
        source = rom.program_source_words(
            rom.APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_SOURCE,
            rom.APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_DESTINATION,
            rom.APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_SOURCE,
            rom.APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_SIZE,
        )
        installer = rom.application_foreground_state_handler_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(flat, [0x6469, 0x68F2])
        self.assertEqual(source[:4], [0x2E00, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(source[-5:], [
            0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS,
        ])
        calls = [
            source[index:index + 2]
            for index in range(len(source) - 1)
            if (source[index] & 0xFF00) == 0xBD00
        ]
        self.assertEqual(calls, [[0xBD33, 0x07B0]])
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["32:D964"]["bytes"],
            rom.APPLICATION_ROOT_MENU_MODE_QUERY_OVERLAY_SIZE,
        )

    def test_root_object_selector_replaces_flat_raster_continuation(self) -> None:
        flat = rom.program_source_words(
            rom.APPLICATION_ROOT_OBJECT_SELECT_OVERLAY_DESTINATION,
            0x0008,
        )
        source = rom.program_source_words(
            rom.APPLICATION_ROOT_OBJECT_SELECT_OVERLAY_SOURCE,
            rom.APPLICATION_ROOT_OBJECT_SELECT_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_ROOT_OBJECT_SELECT_OVERLAY_DESTINATION,
            rom.APPLICATION_ROOT_OBJECT_SELECT_OVERLAY_SOURCE,
            rom.APPLICATION_ROOT_OBJECT_SELECT_OVERLAY_SIZE,
        )
        installer = rom.wide_accumulate_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(flat, [0x70F0, 0x8000, 0x6A0B, 0xFFB0])
        self.assertEqual(source[:4], [0x2E04, 0x58F3, 0x68F1, 0x4A40])
        self.assertIn(
            [0x68F0, 0x0051],
            [source[index:index + 2] for index in range(len(source) - 1)],
        )
        self.assertIn(
            [0x75F3, 0x8000],
            [source[index:index + 2] for index in range(len(source) - 1)],
        )
        self.assertEqual(source[-3:], [0x383F, 0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [installer[index:index + len(descriptor)]
             for index in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["31:5300"]["bytes"],
            rom.APPLICATION_ROOT_OBJECT_SELECT_OVERLAY_SIZE,
        )

    def test_late_wide_and_text_entries_replace_flat_mid_functions(self) -> None:
        installer = rom.install_runtime_overlay_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["nested_system_overlays"]
        }

        wide = rom.program_source_words(
            rom.APPLICATION_WIDE_CONVERT_OVERLAY_SOURCE,
            rom.APPLICATION_WIDE_CONVERT_OVERLAY_SIZE,
        )
        wide_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_WIDE_CONVERT_OVERLAY_DESTINATION,
            rom.APPLICATION_WIDE_CONVERT_OVERLAY_SOURCE,
            rom.APPLICATION_WIDE_CONVERT_OVERLAY_SIZE,
        )
        self.assertEqual(wide[:5], [0x58F1, 0x58F2, 0x58F3, 0x58F4, 0x58F5])
        self.assertEqual(wide[-6:], [
            0x385F, 0x384F, 0x383F, 0x382F, 0x381F, rom.RETS,
        ])
        self.assertIn(
            wide_copy,
            [installer[i:i + len(wide_copy)]
             for i in range(len(installer) - len(wide_copy) + 1)],
        )

        wide_gate = rom.program_source_words(
            rom.APPLICATION_WIDE_GATE_OVERLAY_SOURCE,
            rom.APPLICATION_WIDE_GATE_OVERLAY_SIZE,
        )
        wide_gate_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_WIDE_GATE_OVERLAY_DESTINATION,
            rom.APPLICATION_WIDE_GATE_OVERLAY_SOURCE,
            rom.APPLICATION_WIDE_GATE_OVERLAY_SIZE,
        )
        self.assertEqual(wide_gate, [0xAD2F, 0xC216])
        self.assertIn(
            wide_gate_copy,
            [installer[i:i + len(wide_gate_copy)]
             for i in range(len(installer) - len(wide_gate_copy) + 1)],
        )

        text_dispatch = rom.program_source_words(
            rom.APPLICATION_TEXT_DISPATCH_OVERLAY_SOURCE,
            rom.APPLICATION_TEXT_DISPATCH_OVERLAY_SIZE,
        )
        embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_TEXT_DISPATCH_OVERLAY_DESTINATION,
            rom.APPLICATION_TEXT_DISPATCH_OVERLAY_SOURCE,
            rom.APPLICATION_TEXT_DISPATCH_OVERLAY_SIZE,
        )
        self.assertEqual(text_dispatch[:3], [0x2E00, 0x58F0, 0x58F1])
        self.assertEqual(text_dispatch[-4:], [0x381F, 0x380F, 0x2F00, rom.RETS])
        self.assertIn(
            embedded,
            [installer[i:i + len(embedded)]
             for i in range(len(installer) - len(embedded) + 1)],
        )

        index_action = rom.program_source_words(
            rom.APPLICATION_INDEX_ACTION_OVERLAY_SOURCE,
            rom.APPLICATION_INDEX_ACTION_OVERLAY_SIZE,
        )
        index_action_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_INDEX_ACTION_OVERLAY_DESTINATION,
            rom.APPLICATION_INDEX_ACTION_OVERLAY_SOURCE,
            rom.APPLICATION_INDEX_ACTION_OVERLAY_SIZE,
        )
        flat_index_action = rom.program_source_words(
            rom.APPLICATION_INDEX_ACTION_OVERLAY_DESTINATION,
            rom.APPLICATION_INDEX_ACTION_OVERLAY_SIZE,
        )
        self.assertEqual(flat_index_action[0], 0x0008)
        self.assertEqual(index_action[:7], [
            0x2E00, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F6, 0x58F7,
        ])
        self.assertEqual(index_action[-8:], [
            0x387F, 0x386F, 0x383F, 0x382F,
            0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            index_action_copy,
            [installer[i:i + len(index_action_copy)]
             for i in range(len(installer) - len(index_action_copy) + 1)],
        )
        page_index = rom.program_source_words(
            rom.APPLICATION_PAGE_INDEX_OVERLAY_SOURCE,
            rom.APPLICATION_PAGE_INDEX_OVERLAY_SIZE,
        )
        page_index_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_PAGE_INDEX_OVERLAY_DESTINATION,
            rom.APPLICATION_PAGE_INDEX_OVERLAY_SOURCE,
            rom.APPLICATION_PAGE_INDEX_OVERLAY_SIZE,
        )
        flat_page_index = rom.program_source_words(
            rom.APPLICATION_PAGE_INDEX_OVERLAY_DESTINATION,
            rom.APPLICATION_PAGE_INDEX_OVERLAY_SIZE,
        )
        self.assertEqual(flat_page_index[0], 0x64D2)
        self.assertEqual(page_index[:5], [
            0x2E00, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
        ])
        self.assertEqual(page_index[-6:], [
            0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            page_index_copy,
            [installer[i:i + len(page_index_copy)]
             for i in range(len(installer) - len(page_index_copy) + 1)],
        )
        page_fetch = rom.program_source_words(
            rom.APPLICATION_PAGE_FETCH_OVERLAY_SOURCE,
            rom.APPLICATION_PAGE_FETCH_OVERLAY_SIZE,
        )
        page_fetch_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_PAGE_FETCH_OVERLAY_DESTINATION,
            rom.APPLICATION_PAGE_FETCH_OVERLAY_SOURCE,
            rom.APPLICATION_PAGE_FETCH_OVERLAY_SIZE,
        )
        flat_page_fetch = rom.program_source_words(
            rom.APPLICATION_PAGE_FETCH_OVERLAY_DESTINATION,
            rom.APPLICATION_PAGE_FETCH_OVERLAY_SIZE,
        )
        self.assertEqual(flat_page_fetch[0], 0x5C01)
        self.assertEqual(page_fetch[:5], [
            0x2E02, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
        ])
        self.assertEqual(page_fetch[-6:], [
            0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            page_fetch_copy,
            [installer[i:i + len(page_fetch_copy)]
             for i in range(len(installer) - len(page_fetch_copy) + 1)],
        )
        rect_draw = rom.program_source_words(
            rom.APPLICATION_RECT_DRAW_OVERLAY_SOURCE,
            rom.APPLICATION_RECT_DRAW_OVERLAY_SIZE,
        )
        rect_draw_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_RECT_DRAW_OVERLAY_DESTINATION,
            rom.APPLICATION_RECT_DRAW_OVERLAY_SOURCE,
            rom.APPLICATION_RECT_DRAW_OVERLAY_SIZE,
        )
        flat_rect_draw = rom.program_source_words(
            rom.APPLICATION_RECT_DRAW_OVERLAY_DESTINATION,
            rom.APPLICATION_RECT_DRAW_OVERLAY_SIZE,
        )
        self.assertEqual(flat_rect_draw[0], 0xFFF0)
        self.assertEqual(rect_draw[:5], [
            0x2E4A, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
        ])
        self.assertEqual(rect_draw[-6:], [
            0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            rect_draw_copy,
            [installer[i:i + len(rect_draw_copy)]
             for i in range(len(installer) - len(rect_draw_copy) + 1)],
        )
        image_window = rom.program_source_words(
            rom.APPLICATION_IMAGE_WINDOW_OVERLAY_SOURCE,
            rom.APPLICATION_IMAGE_WINDOW_OVERLAY_SIZE,
        )
        image_window_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_IMAGE_WINDOW_OVERLAY_DESTINATION,
            rom.APPLICATION_IMAGE_WINDOW_OVERLAY_SOURCE,
            rom.APPLICATION_IMAGE_WINDOW_OVERLAY_SIZE,
        )
        flat_image_window = rom.program_source_words(
            rom.APPLICATION_IMAGE_WINDOW_OVERLAY_DESTINATION,
            rom.APPLICATION_IMAGE_WINDOW_OVERLAY_SIZE,
        )
        self.assertEqual(flat_image_window[0], 0x51A8)
        self.assertEqual(image_window[:5], [
            0x2E1A, 0x58F1, 0x58F3, 0x58F6, 0x58F7,
        ])
        self.assertEqual(image_window[-6:], [
            0x387F, 0x386F, 0x383F, 0x381F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            image_window_copy,
            [installer[i:i + len(image_window_copy)]
             for i in range(len(installer) - len(image_window_copy) + 1)],
        )
        state_commit = rom.program_source_words(
            rom.APPLICATION_STATE_COMMIT_OVERLAY_SOURCE,
            rom.APPLICATION_STATE_COMMIT_OVERLAY_SIZE,
        )
        state_commit_embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_STATE_COMMIT_OVERLAY_DESTINATION,
            rom.APPLICATION_STATE_COMMIT_OVERLAY_SOURCE,
            rom.APPLICATION_STATE_COMMIT_OVERLAY_SIZE,
        )
        flat_state_commit = rom.program_source_words(
            rom.APPLICATION_STATE_COMMIT_OVERLAY_DESTINATION,
            rom.APPLICATION_STATE_COMMIT_OVERLAY_SIZE,
        )
        self.assertEqual(flat_state_commit[0], 0x0002)
        self.assertEqual(state_commit, [
            0x2E00, 0xBD32, 0xCC9C, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            state_commit_embedded,
            [installer[i:i + len(state_commit_embedded)]
             for i in range(
                 len(installer) - len(state_commit_embedded) + 1
             )],
        )
        image_dispatch = rom.program_source_words(
            rom.APPLICATION_IMAGE_DISPATCH_OVERLAY_SOURCE,
            rom.APPLICATION_IMAGE_DISPATCH_OVERLAY_SIZE,
        )
        image_dispatch_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_IMAGE_DISPATCH_OVERLAY_DESTINATION,
            rom.APPLICATION_IMAGE_DISPATCH_OVERLAY_SOURCE,
            rom.APPLICATION_IMAGE_DISPATCH_OVERLAY_SIZE,
        )
        flat_image_dispatch = rom.program_source_words(
            rom.APPLICATION_IMAGE_DISPATCH_OVERLAY_DESTINATION,
            rom.APPLICATION_IMAGE_DISPATCH_OVERLAY_SIZE,
        )
        self.assertEqual(flat_image_dispatch[0], 0x3777)
        self.assertEqual(image_dispatch[:5], [
            0x2E03, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
        ])
        self.assertEqual(image_dispatch[-6:], [
            0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            image_dispatch_copy,
            [installer[i:i + len(image_dispatch_copy)]
             for i in range(len(installer) - len(image_dispatch_copy) + 1)],
        )
        context_lookup = rom.program_source_words(
            rom.APPLICATION_CONTEXT_LOOKUP_OVERLAY_SOURCE,
            rom.APPLICATION_CONTEXT_LOOKUP_OVERLAY_SIZE,
        )
        context_lookup_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_CONTEXT_LOOKUP_OVERLAY_DESTINATION,
            rom.APPLICATION_CONTEXT_LOOKUP_OVERLAY_SOURCE,
            rom.APPLICATION_CONTEXT_LOOKUP_OVERLAY_SIZE,
        )
        self.assertEqual(context_lookup[:4], [
            0x2E04, 0x58F3, 0x68F1, 0x4A40,
        ])
        self.assertEqual(context_lookup[-3:], [0x383F, 0x2F00, rom.RETS])
        self.assertIn(
            context_lookup_copy,
            [installer[i:i + len(context_lookup_copy)]
             for i in range(
                 len(installer) - len(context_lookup_copy) + 1
             )],
        )
        self.assertEqual(modules["31:5300"]["bytes"], 0x00BA)
        context_property = rom.program_source_words(
            rom.APPLICATION_CONTEXT_PROPERTY_OVERLAY_SOURCE,
            rom.APPLICATION_CONTEXT_PROPERTY_OVERLAY_SIZE,
        )
        context_property_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_CONTEXT_PROPERTY_OVERLAY_DESTINATION,
            rom.APPLICATION_CONTEXT_PROPERTY_OVERLAY_SOURCE,
            rom.APPLICATION_CONTEXT_PROPERTY_OVERLAY_SIZE,
        )
        self.assertEqual(context_property[:4], [
            0x2E00, 0x780B, 0x0006, 0x560F,
        ])
        self.assertEqual(context_property[-3:], [0x4800, 0x2F00, rom.RETS])
        self.assertIn(
            context_property_copy,
            [installer[i:i + len(context_property_copy)]
             for i in range(
                 len(installer) - len(context_property_copy) + 1
             )],
        )
        self.assertEqual(modules["32:2396"]["bytes"], 0x0084)
        event_classify = rom.program_source_words(
            rom.APPLICATION_EVENT_CLASSIFY_OVERLAY_SOURCE,
            rom.APPLICATION_EVENT_CLASSIFY_OVERLAY_SIZE,
        )
        event_classify_copy = rom.embed_program_overlay_words(
            rom.APPLICATION_EVENT_CLASSIFY_OVERLAY_DESTINATION,
            rom.APPLICATION_EVENT_CLASSIFY_OVERLAY_SOURCE,
            rom.APPLICATION_EVENT_CLASSIFY_OVERLAY_SIZE,
        )
        self.assertEqual(event_classify[:4], [
            0x2E00, 0x780B, 0x0006, 0x76F0,
        ])
        self.assertEqual(event_classify[-3:], [0x4801, 0x2F00, rom.RETS])
        self.assertIn(
            event_classify_copy,
            [installer[i:i + len(event_classify_copy)]
             for i in range(
                 len(installer) - len(event_classify_copy) + 1
             )],
        )
        self.assertEqual(modules["33:1A02"]["bytes"], 0x002C)
        self.assertEqual(modules["32:78DE"]["bytes"], 0x0066)
        self.assertEqual(modules["32:773A"]["bytes"], 0x0004)
        self.assertEqual(modules["33:0070"]["bytes"], 0x0038)
        self.assertEqual(modules["30:0C24"]["bytes"], 0x0118)
        self.assertEqual(modules["30:14E4"]["bytes"], 0x0118)
        self.assertEqual(modules["30:15FC"]["bytes"], 0x0116)
        self.assertEqual(modules["30:1A54"]["bytes"], 0x0116)
        self.assertEqual(modules["26:0000"]["bytes"], 0x03BA)
        self.assertEqual(modules["33:65FC"]["bytes"], 0x000A)
        self.assertEqual(modules["27:A8B6"]["bytes"], 0x0336)

    def test_modal_validation_closure_replaces_flat_data_and_mid_functions(self) -> None:
        installer = rom.install_runtime_overlay_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["nested_system_overlays"]
        }
        overlays = (
            (
                "32:2728",
                rom.APPLICATION_MODAL_VALIDATION_OVERLAY_DESTINATION,
                rom.APPLICATION_MODAL_VALIDATION_OVERLAY_SOURCE,
                rom.APPLICATION_MODAL_VALIDATION_OVERLAY_SIZE,
                [0x2E00, 0x58F1, 0x780B, 0x0006],
                [0x381F, 0x2F00, rom.RETS],
            ),
            (
                "27:4330",
                rom.APPLICATION_MODAL_MODE_DISPATCH_OVERLAY_DESTINATION,
                rom.APPLICATION_MODAL_MODE_DISPATCH_OVERLAY_SOURCE,
                rom.APPLICATION_MODAL_MODE_DISPATCH_OVERLAY_SIZE,
                [0x2E0A, 0x58F0, 0x58F1, 0x58F2],
                [0x381F, 0x380F, 0x2F00, rom.RETS],
            ),
            (
                "2F:4EDC",
                rom.APPLICATION_MODAL_TEXT_NORMALIZE_OVERLAY_DESTINATION,
                rom.APPLICATION_MODAL_TEXT_NORMALIZE_OVERLAY_SOURCE,
                rom.APPLICATION_MODAL_TEXT_NORMALIZE_OVERLAY_SIZE,
                [0x2E01, 0x58F1, 0x58F2, 0x58F3],
                [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
            ),
            (
                "2F:9844",
                rom.APPLICATION_MODAL_TEXT_FILTER_OVERLAY_DESTINATION,
                rom.APPLICATION_MODAL_TEXT_FILTER_OVERLAY_SOURCE,
                rom.APPLICATION_MODAL_TEXT_FILTER_OVERLAY_SIZE,
                [0x2E02, 0x58F1, 0x58F2, 0x58F3],
                [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
            ),
            (
                "30:409E",
                rom.APPLICATION_MODAL_BUFFER_READ_OVERLAY_DESTINATION,
                rom.APPLICATION_MODAL_BUFFER_READ_OVERLAY_SOURCE,
                rom.APPLICATION_MODAL_BUFFER_READ_OVERLAY_SIZE,
                [0x2E05, 0x58F1, 0x68F1, 0xC144],
                [0x381F, 0x2F00, rom.RETS],
            ),
        )

        flat_root = rom.program_source_words(
            rom.APPLICATION_MODAL_VALIDATION_OVERLAY_DESTINATION,
            rom.APPLICATION_MODAL_VALIDATION_OVERLAY_SIZE,
        )
        self.assertNotEqual(flat_root[0], 0x2E00)
        for name, destination, source, size, prologue, epilogue in overlays:
            exact = rom.program_source_words(source, size)
            descriptor = rom.copy_code_to_overlay_words(
                destination, source, size,
            )
            self.assertEqual(exact[:len(prologue)], prologue)
            self.assertEqual(exact[-len(epilogue):], epilogue)
            self.assertIn(
                descriptor,
                [installer[i:i + len(descriptor)]
                 for i in range(len(installer) - len(descriptor) + 1)],
            )
            self.assertEqual(modules[name]["bytes"], size)

        root = rom.program_source_words(
            rom.APPLICATION_MODAL_VALIDATION_OVERLAY_SOURCE,
            rom.APPLICATION_MODAL_VALIDATION_OVERLAY_SIZE,
        )
        for call in (
            [0xBD27, 0x4330],
            [0xBD2F, 0x9844],
            [0xBD31, 0xAED0],
            [0xBD2F, 0x4EDC],
        ):
            self.assertIn(
                call,
                [root[i:i + 2] for i in range(len(root) - 1)],
            )

    def test_factory_default_catalogue_closure_is_exact_and_installed(self) -> None:
        bootstrap = rom.install_runtime_overlay_words()
        installer = rom.application_factory_default_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }
        copy_overlays = rom.APPLICATION_FACTORY_DEFAULT_COPY_OVERLAYS
        embedded_overlays = rom.APPLICATION_FACTORY_DEFAULT_EMBEDDED_OVERLAYS

        self.assertEqual(len(copy_overlays), 29)
        self.assertEqual(len(embedded_overlays), 20)
        self.assertIn(
            [0xBD00 | (rom.APPLICATION_FACTORY_DEFAULT_INSTALLER_ADDRESS >> 16),
             rom.APPLICATION_FACTORY_DEFAULT_INSTALLER_ADDRESS & 0xFFFF],
            [bootstrap[i:i + 2] for i in range(len(bootstrap) - 1)],
        )
        self.assertEqual(copy_overlays[0], (0x2AA952, 0x47A952, 0x025C))
        root = rom.program_source_words(*copy_overlays[0][1:])
        flat_root = rom.program_source_words(
            copy_overlays[0][0], copy_overlays[0][2],
        )
        self.assertEqual(root[:3], [0x2E8F, 0x58F1, 0xBD33])
        self.assertEqual(root[-3:], [0x381F, 0x2F00, rom.RETS])
        self.assertNotEqual(flat_root[:8], root[:8])
        for call in (
            [0xBD33, 0x5FC4],
            [0xBD32, 0x12E4],
            [0xBD2E, 0xE3DC],
            [0xBD24, 0x0D50],
            [0xBD32, 0xCA88],
        ):
            self.assertIn(call, [root[i:i + 2] for i in range(len(root) - 1)])

        destinations = set()
        for embedded, overlays in (
            (False, copy_overlays),
            (True, embedded_overlays),
        ):
            for destination, source, size in overlays:
                self.assertNotIn(destination, destinations)
                destinations.add(destination)
                exact = rom.program_source_words(source, size)
                self.assertEqual(len(exact) * 2, size)
                descriptor = (
                    rom.embed_program_overlay_words(destination, source, size)
                    if embedded else
                    rom.copy_code_to_overlay_words(destination, source, size)
                )
                self.assertIn(
                    descriptor,
                    [installer[i:i + len(descriptor)]
                     for i in range(len(installer) - len(descriptor) + 1)],
                )
                name = f"{destination >> 16:02X}:{destination & 0xFFFF:04X}"
                self.assertEqual(modules[name]["source"],
                                 f"{source >> 16:02X}:{source & 0xFFFF:04X}")
                self.assertEqual(modules[name]["bytes"], size)

        state50_setup = rom.program_source_words(0x4B12BC, 0x018E)
        self.assertEqual(state50_setup[:5],
                         [0x2E00, 0x58F0, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(state50_setup[-6:],
                         [0x383F, 0x382F, 0x381F, 0x380F,
                          0x2F00, rom.RETS])
        self.assertEqual(
            rom.program_source_words(0x2E12BC, 2), [0x480F]
        )
        state50_setup_calls = [
            state50_setup[index:index + 2]
            for index in range(len(state50_setup) - 1)
        ]
        for call in (
            [0xBD33, 0x5FC4], [0xBD33, 0x1C12],
            [0xBD33, 0x5FD0], [0xBD33, 0x5FDC],
            [0xBD32, 0x2186], [0xBD32, 0x974C],
            [0xBD33, 0x5CA4], [0xBD33, 0x5D30],
            [0xBD33, 0x5C0A], [0xBD33, 0x415C],
        ):
            self.assertIn(call, state50_setup_calls)
        self.assertEqual(
            rom.program_source_words(0x50415C, 0x001E)[-2:],
            [0x2F00, rom.RETS],
        )
        state50_cell = rom.program_source_words(0x4FAE96, 0x0056)
        self.assertEqual(state50_cell[:2], [0x2E00, 0x58F0])
        self.assertEqual(state50_cell[-3:], [0x380F, 0x2F00, rom.RETS])
        self.assertIn(
            [0xBD11, 0x0000],
            [state50_cell[index:index + 2]
             for index in range(len(state50_cell) - 1)],
        )
        storage_pair_patch = rom.write_program_words(
            rom.APPLICATION_FOREGROUND_STATE50_STORAGE_PAIR_CALL,
            (0xBD00 | (rom.RESIDENT_STORAGE_PAIR_ADDRESS >> 16),
             rom.RESIDENT_STORAGE_PAIR_ADDRESS & 0xFFFF),
        )
        self.assertIn(
            storage_pair_patch,
            [installer[index:index + len(storage_pair_patch)]
             for index in range(
                 len(installer) - len(storage_pair_patch) + 1
             )],
        )

    def test_compositor_layout_item_is_exact_complete_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_DESTINATION,
            rom.APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_SIZE,
        )
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:7], [
            0x2E03, 0x58F0, 0x58F1, 0x58F2,
            0x58F3, 0x58F4, 0x58F5,
        ])
        self.assertIn([0xBD03, 0x406C], [
            source[i:i + 2] for i in range(len(source) - 1)
        ])
        self.assertIn([0xBD03, 0x4010], [
            source[i:i + 2] for i in range(len(source) - 1)
        ])
        self.assertEqual(source[-8:], [
            0x385F, 0x384F, 0x383F, 0x382F,
            0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["22:C370"]["bytes"],
            rom.APPLICATION_MAIN_LAYOUT_ITEM_OVERLAY_SIZE,
        )

    def test_resource_open_wrapper_dependency_is_exact(self) -> None:
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["nested_system_overlays"]
        }

        wrapper = rom.program_source_words(
            rom.APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_SOURCE,
            rom.APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_SIZE,
        )
        wrapper_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_DESTINATION,
            rom.APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_SOURCE,
            rom.APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_SIZE,
        )
        self.assertEqual(wrapper[:4], [0x2E00, 0x58F1, 0x58F2, 0x58F3])
        self.assertIn([0xBD2E, 0xAB96], [
            wrapper[i:i + 2] for i in range(len(wrapper) - 1)
        ])
        self.assertEqual(wrapper[-5:], [
            0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            wrapper_descriptor,
            [installer[i:i + len(wrapper_descriptor)] for i in range(
                len(installer) - len(wrapper_descriptor) + 1
            )],
        )
        self.assertEqual(
            modules["5F:B63C"]["bytes"],
            rom.APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_SIZE,
        )
        self.assertEqual(
            rom.APPLICATION_RESOURCE_OPEN_WRAPPER_LINKED_DESTINATION,
            0x32B63C,
        )
        self.assertEqual(
            rom.APPLICATION_RESOURCE_OPEN_WRAPPER_OVERLAY_DESTINATION,
            0x5FB63C,
        )
        for source in rom.APPLICATION_RESOURCE_OPEN_WRAPPER_CALL_SOURCES:
            self.assertEqual(
                rom.program_source_words(source, 4),
                [0xBD32, 0xB63C],
            )

        factory = rom.program_source_words(
            rom.APPLICATION_DRAW_CONTEXT_FACTORY_OVERLAY_SOURCE,
            rom.APPLICATION_DRAW_CONTEXT_FACTORY_OVERLAY_SIZE,
        )
        factory_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_DRAW_CONTEXT_FACTORY_OVERLAY_DESTINATION,
            rom.APPLICATION_DRAW_CONTEXT_FACTORY_OVERLAY_SOURCE,
            rom.APPLICATION_DRAW_CONTEXT_FACTORY_OVERLAY_SIZE,
        )
        self.assertEqual(factory[:3], [0x2E02, 0x58F1, 0xBD33])
        self.assertIn([0xBD21, 0xFD80], [
            factory[i:i + 2] for i in range(len(factory) - 1)
        ])
        self.assertEqual(factory[-3:], [0x381F, 0x2F00, rom.RETS])
        self.assertIn(
            factory_descriptor,
            [installer[i:i + len(factory_descriptor)] for i in range(
                len(installer) - len(factory_descriptor) + 1
            )],
        )
        self.assertEqual(
            modules["32:DA7C"]["bytes"],
            rom.APPLICATION_DRAW_CONTEXT_FACTORY_OVERLAY_SIZE,
        )

        coordinate = rom.program_source_words(
            rom.APPLICATION_RESOURCE_COORDINATE_OVERLAY_SOURCE,
            rom.APPLICATION_RESOURCE_COORDINATE_OVERLAY_SIZE,
        )
        coordinate_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_RESOURCE_COORDINATE_OVERLAY_DESTINATION,
            rom.APPLICATION_RESOURCE_COORDINATE_OVERLAY_SOURCE,
            rom.APPLICATION_RESOURCE_COORDINATE_OVERLAY_SIZE,
        )
        self.assertEqual(coordinate[:7], [
            0x2E07, 0x58F2, 0x58F3, 0x58F4,
            0x58F5, 0x58F6, 0x58F7,
        ])
        self.assertIn([0xBD33, 0x07B0], [
            coordinate[i:i + 2] for i in range(len(coordinate) - 1)
        ])
        self.assertEqual(coordinate[-8:], [
            0x387F, 0x386F, 0x385F, 0x384F,
            0x383F, 0x382F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            coordinate_descriptor,
            [installer[i:i + len(coordinate_descriptor)] for i in range(
                len(installer) - len(coordinate_descriptor) + 1
            )],
        )
        self.assertEqual(
            modules["2E:AB96"]["bytes"],
            rom.APPLICATION_RESOURCE_COORDINATE_OVERLAY_SIZE,
        )

    def test_storage_bitmap_builder_is_exact_complete_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_DESTINATION,
            rom.APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_SIZE,
        )
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:5], [
            0x2E06, 0x58F1, 0x58F2, 0x58F3, 0x4820,
        ])
        self.assertNotIn(0xBD00, [word & 0xFF00 for word in source])
        self.assertEqual(source[-5:], [
            0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["2F:4350"]["bytes"],
            rom.APPLICATION_MAIN_STORAGE_BITMAP_OVERLAY_SIZE,
        )

    def test_storage_record_dependency_closure_is_exact(self) -> None:
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }
        overlays = (
            (rom.APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STORAGE_RECORD_OVERLAY_SIZE,
             "25:77DA", 0x2E0B),
            (rom.APPLICATION_MAIN_STORAGE_MASK_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STORAGE_MASK_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STORAGE_MASK_OVERLAY_SIZE,
             "30:251E", 0x2E05),
            (rom.APPLICATION_MAIN_SERVICE_INIT_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_SERVICE_INIT_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_SERVICE_INIT_OVERLAY_SIZE,
             "30:2630", 0x2E00),
            (rom.APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_DESTINATION,
             rom.APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_SOURCE,
             rom.APPLICATION_MAIN_STORAGE_FLAG_OVERLAY_SIZE,
             "33:197A", 0x2E00),
        )

        for destination, source_address, size, address, first_word in overlays:
            source = rom.program_source_words(source_address, size)
            descriptor = rom.copy_code_to_overlay_words(
                destination, source_address, size,
            )
            self.assertEqual(source[0], first_word)
            self.assertEqual(source[-2:], [0x2F00, rom.RETS])
            self.assertIn(
                descriptor,
                [installer[i:i + len(descriptor)]
                 for i in range(len(installer) - len(descriptor) + 1)],
            )
            self.assertEqual(modules[address]["bytes"], size)

    def test_resident_work_table_creator_uses_complete_same_pc_source(self) -> None:
        source = rom.program_source_words(
            rom.RESIDENT_WORK_TABLE_CREATE_OVERLAY_SOURCE,
            rom.RESIDENT_WORK_TABLE_CREATE_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.RESIDENT_WORK_TABLE_CREATE_OVERLAY_DESTINATION,
            rom.RESIDENT_WORK_TABLE_CREATE_OVERLAY_SOURCE,
            rom.RESIDENT_WORK_TABLE_CREATE_OVERLAY_SIZE,
        )
        installer = rom.fixed_launch_wrapper_installer_words()
        main_installer = rom.install_application_main_chain_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(
            rom.RESIDENT_WORK_TABLE_CREATE_OVERLAY_SOURCE -
            rom.RESIDENT_WORK_TABLE_CREATE_OVERLAY_DESTINATION,
            0x1D0000,
        )
        self.assertEqual(source[:4], [0x2E02, 0x58F1, 0x58F2, 0x58F3])
        self.assertIn([0xBD33, 0x51E0], [source[i:i + 2]
                                        for i in range(len(source) - 1)])
        self.assertIn([0xBD33, 0x51F2], [source[i:i + 2]
                                        for i in range(len(source) - 1)])
        self.assertEqual(
            source[-5:], [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS]
        )
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertIn(
            descriptor,
            [main_installer[i:i + len(descriptor)]
             for i in range(
                 len(main_installer) - len(descriptor) + 1
             )],
        )
        self.assertEqual(
            modules["31:4974"]["bytes"],
            rom.RESIDENT_WORK_TABLE_CREATE_OVERLAY_SIZE,
        )

    def test_operation_context_builder_uses_complete_same_pc_source(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_DESTINATION,
            rom.APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_SIZE,
        )
        loader = rom.rom01_application_loader_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(
            rom.APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_SOURCE -
            rom.APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_DESTINATION,
            0x1D0000,
        )
        self.assertEqual(source[:5], [0x2EAF, 0x58F2, 0x58F3, 0x58F4, 0x58F5])
        for call in (
            [0xBD33, 0x40A8],
            [0xBD33, 0x46A2],
            [0xBD33, 0x1894],
            [0xBD27, 0xCBE4],
            [0xBD33, 0x6C0A],
            [0xBD33, 0x443E],
        ):
            self.assertIn(
                call,
                [source[i:i + 2] for i in range(len(source) - 1)],
            )
        self.assertEqual(
            source[-6:], [0x385F, 0x384F, 0x383F, 0x382F, 0x2F00, rom.RETS]
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_SOURCE +
                rom.APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_SIZE,
                2,
            ),
            [0x2E0C],
        )
        self.assertIn(
            descriptor,
            [loader[i:i + len(descriptor)]
             for i in range(len(loader) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["29:9746"]["bytes"],
            rom.APPLICATION_OPERATION_CONTEXT_BUILD_OVERLAY_SIZE,
        )

    def test_operation_context_child_uses_complete_same_pc_source(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_OPERATION_CONTEXT_CHILD_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_CHILD_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_OPERATION_CONTEXT_CHILD_OVERLAY_DESTINATION,
            rom.APPLICATION_OPERATION_CONTEXT_CHILD_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_CHILD_OVERLAY_SIZE,
        )
        loader = rom.rom01_application_loader_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(
            rom.APPLICATION_OPERATION_CONTEXT_CHILD_OVERLAY_SOURCE -
            rom.APPLICATION_OPERATION_CONTEXT_CHILD_OVERLAY_DESTINATION,
            0x1D0000,
        )
        self.assertEqual(source[:5], [0x2E05, 0x58F1, 0x58F2, 0x58F3, 0x780B])
        for call in (
            [0xBD33, 0x2652],
            [0xBD31, 0x5246],
            [0xBD2C, 0xC07E],
            [0xBD33, 0x40A8],
        ):
            self.assertIn(
                call,
                [source[i:i + 2] for i in range(len(source) - 1)],
            )
        self.assertEqual(
            source[-5:], [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS]
        )
        self.assertIn(
            descriptor,
            [loader[i:i + len(descriptor)]
             for i in range(len(loader) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["27:CBE4"]["bytes"],
            rom.APPLICATION_OPERATION_CONTEXT_CHILD_OVERLAY_SIZE,
        )

    def test_operation_context_casefold_closure_uses_exact_sources(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_OPERATION_CONTEXT_CASEFOLD_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_CASEFOLD_OVERLAY_SIZE,
        )
        loader = rom.rom01_application_loader_words()
        wrapper = rom.npe_browser_casefold_lazy_wrapper_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(
            rom.APPLICATION_OPERATION_CONTEXT_CASEFOLD_OVERLAY_SOURCE -
            rom.APPLICATION_OPERATION_CONTEXT_CASEFOLD_OVERLAY_DESTINATION,
            0x1D0000,
        )
        self.assertEqual(
            source[:7],
            [0x2E00, 0x1F10, 0x1F11, 0x58F2, 0x58F3, 0x58F4, 0x58F5],
        )
        for call in (
            [0xBD31, 0xAED0],
            [0xBD33, 0x430A],
            [0xBD33, 0x45A2],
        ):
            self.assertIn(
                call,
                [source[index:index + 2]
                 for index in range(len(source) - 1)],
            )
        self.assertEqual(source[-4:], [0x1F91, 0x1F90, 0x2F00, rom.RETS])
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_OPERATION_CONTEXT_CASEFOLD_OVERLAY_SOURCE +
                rom.APPLICATION_OPERATION_CONTEXT_CASEFOLD_OVERLAY_SIZE,
                2,
            ),
            [0x2E04],
        )

        closures = (
            (rom.APPLICATION_OPERATION_CONTEXT_CASEFOLD_OVERLAY_DESTINATION,
             rom.APPLICATION_OPERATION_CONTEXT_CASEFOLD_OVERLAY_SOURCE,
             rom.APPLICATION_OPERATION_CONTEXT_CASEFOLD_OVERLAY_SIZE,
             rom.copy_code_to_overlay_words),
            (rom.APPLICATION_OPERATION_CONTEXT_UPPER_PREDICATE_OVERLAY_DESTINATION,
             rom.APPLICATION_OPERATION_CONTEXT_UPPER_PREDICATE_OVERLAY_SOURCE,
             rom.APPLICATION_OPERATION_CONTEXT_UPPER_PREDICATE_OVERLAY_SIZE,
             rom.embed_program_overlay_words),
            (rom.APPLICATION_OPERATION_CONTEXT_TOLOWER_OVERLAY_DESTINATION,
             rom.APPLICATION_OPERATION_CONTEXT_TOLOWER_OVERLAY_SOURCE,
             rom.APPLICATION_OPERATION_CONTEXT_TOLOWER_OVERLAY_SIZE,
             rom.embed_program_overlay_words),
        )
        for destination, closure_source, size, installer in closures:
            descriptor = installer(destination, closure_source, size)
            self.assertIn(
                descriptor,
                [wrapper[index:index + len(descriptor)]
                 for index in range(len(wrapper) - len(descriptor) + 1)],
            )
            key = f"{destination >> 16:02X}:{destination & 0xFFFF:04X}"
            self.assertEqual(modules[key]["bytes"], size)

        upper = rom.program_source_words(
            rom.APPLICATION_OPERATION_CONTEXT_UPPER_PREDICATE_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_UPPER_PREDICATE_OVERLAY_SIZE,
        )
        tolower = rom.program_source_words(
            rom.APPLICATION_OPERATION_CONTEXT_TOLOWER_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_TOLOWER_OVERLAY_SIZE,
        )
        self.assertEqual(upper[:3], [0x2E00, 0x780B, 0x0006])
        self.assertEqual(upper[-3:], [0x4800, 0x2F00, rom.RETS])
        self.assertEqual(tolower[:3], [0x2E00, 0x780B, 0x0006])
        self.assertEqual(tolower[-4:], [0x70F0, 0x0020, 0x2F00, rom.RETS])
        self.assertEqual(wrapper[-2:], [0xAD1B, 0x23B8])
        self.assertLessEqual(
            rom.NPE_BROWSER_CASEFOLD_LAZY_WRAPPER_ADDRESS + len(wrapper) * 2,
            rom.MENU_DECIMAL_PARSE_ENGINE_INSTALLER_ADDRESS,
        )

        call_patch = rom.npe_browser_lazy_call_patch_words()
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_NPE_BROWSER_LAZY_CALL_OVERLAY_SOURCE,
                rom.APPLICATION_NPE_BROWSER_LAZY_CALL_OVERLAY_SIZE,
            ),
            [0xBD1B, 0x23B8],
        )
        self.assertIn(
            call_patch,
            [loader[index:index + len(call_patch)]
             for index in range(len(loader) - len(call_patch) + 1)],
        )
        self.assertEqual(
            modules["33:3DB8"]["bytes"],
            rom.APPLICATION_NPE_BROWSER_LAZY_CALL_OVERLAY_SIZE,
        )

    def test_operation_context_predicate_uses_exact_source_50_leaf(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_OPERATION_CONTEXT_PREDICATE_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_PREDICATE_OVERLAY_SIZE,
        )
        descriptor = rom.embed_program_overlay_words(
            rom.APPLICATION_OPERATION_CONTEXT_PREDICATE_OVERLAY_DESTINATION,
            rom.APPLICATION_OPERATION_CONTEXT_PREDICATE_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_CONTEXT_PREDICATE_OVERLAY_SIZE,
        )
        loader = rom.rom01_application_loader_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source, [0x2E00, 0x4801, 0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [loader[i:i + len(descriptor)]
             for i in range(len(loader) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["33:6C0A"]["bytes"],
            rom.APPLICATION_OPERATION_CONTEXT_PREDICATE_OVERLAY_SIZE,
        )

    def test_file_browser_layout_range_uses_complete_same_pc_source(
        self,
    ) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_FILE_BROWSER_LAYOUT_RANGE_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_BROWSER_LAYOUT_RANGE_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FILE_BROWSER_LAYOUT_RANGE_OVERLAY_DESTINATION,
            rom.APPLICATION_FILE_BROWSER_LAYOUT_RANGE_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_BROWSER_LAYOUT_RANGE_OVERLAY_SIZE,
        )
        loader = rom.rom01_application_loader_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:5], [0x2E06, 0x58F1, 0x58F2, 0x58F3, 0x4800])
        self.assertEqual(
            sum(source[i:i + 2] == [0xBD1D, 0x7C00]
                for i in range(len(source) - 1)),
            2,
        )
        self.assertEqual(
            source[-5:], [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS]
        )
        self.assertIn(
            descriptor,
            [loader[i:i + len(descriptor)]
             for i in range(len(loader) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["2E:393A"]["bytes"],
            rom.APPLICATION_FILE_BROWSER_LAYOUT_RANGE_OVERLAY_SIZE,
        )

    def test_file_browser_range_accumulator_uses_complete_same_pc_source(
        self,
    ) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_FILE_BROWSER_RANGE_ACCUMULATE_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_BROWSER_RANGE_ACCUMULATE_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FILE_BROWSER_RANGE_ACCUMULATE_OVERLAY_DESTINATION,
            rom.APPLICATION_FILE_BROWSER_RANGE_ACCUMULATE_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_BROWSER_RANGE_ACCUMULATE_OVERLAY_SIZE,
        )
        loader = rom.rom01_application_loader_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:2], [0x2E02, 0x58F1])
        self.assertEqual(
            sum(source[i:i + 2] == [0xBD1D, 0x7C00]
                for i in range(len(source) - 1)),
            1,
        )
        self.assertEqual(
            source[-3:], [0x381F, 0x2F00, rom.RETS]
        )
        self.assertIn(
            descriptor,
            [loader[i:i + len(descriptor)]
             for i in range(len(loader) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["31:4200"]["bytes"],
            rom.APPLICATION_FILE_BROWSER_RANGE_ACCUMULATE_OVERLAY_SIZE,
        )

    def test_file_browser_character_classifier_uses_complete_same_pc_source(
        self,
    ) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_FILE_BROWSER_CHARACTER_CLASSIFY_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_BROWSER_CHARACTER_CLASSIFY_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FILE_BROWSER_CHARACTER_CLASSIFY_OVERLAY_DESTINATION,
            rom.APPLICATION_FILE_BROWSER_CHARACTER_CLASSIFY_OVERLAY_SOURCE,
            rom.APPLICATION_FILE_BROWSER_CHARACTER_CLASSIFY_OVERLAY_SIZE,
        )
        loader = rom.rom01_application_loader_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:2], [0x2E00, 0x780B])
        self.assertNotIn(0xBD00, [word & 0xFF00 for word in source])
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            descriptor,
            [loader[i:i + len(descriptor)]
             for i in range(len(loader) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["32:E5E4"]["bytes"],
            rom.APPLICATION_FILE_BROWSER_CHARACTER_CLASSIFY_OVERLAY_SIZE,
        )

    def test_operation_action_mode_predicate_is_exact_final_rom01_overlay(
        self,
    ) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_OVERLAY_SIZE,
        )
        embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_OVERLAY_DESTINATION,
            rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_OVERLAY_SIZE,
        )
        installer = (
            rom.application_operation_action_mode_predicate_installer_words()
        )
        loader = rom.rom01_application_loader_words()
        image = rom.build_image(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_rom_01_return=True,
        )
        modules = {
            item["destination"]: item
            for item in rom.manifest(
                image,
                initializer_overlay_probe=True,
                probe_rom_08_return=True,
                probe_rom_01_return=True,
            )["application_main_chain"]
        }

        self.assertEqual(len(source) * 2, 0x0112)
        self.assertEqual(source[:4], [0x2E05, 0x58F1, 0x780B, 0x0006])
        self.assertEqual(
            source[-4:], [0x4801, 0x381F, 0x2F00, rom.RETS]
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_OVERLAY_SOURCE +
                rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_OVERLAY_SIZE,
                2,
            ),
            [0x2E00],
        )
        calls = [
            (source[index] & 0xFF, source[index + 1])
            for index in range(len(source) - 1)
            if source[index] & 0xFF00 == 0xBD00
        ]
        self.assertEqual(calls, [
            (0x33, 0x269E),
            (0x25, 0x206E),
            (0x33, 0x1A02),
            (0x33, 0x4342),
        ])
        self.assertNotIn((0x2A, 0xCA24), calls)
        self.assertNotIn((0x31, 0x4200), calls)
        self.assertEqual(
            installer[:1 + len(embedded)], [0x1F10, *embedded]
        )
        self.assertEqual(installer[-2:], [0x1F90, rom.RETS])
        self.assertEqual(len(installer) * 2, 0x09DE)
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_INSTALLER_ADDRESS,
                len(installer),
            ),
            installer,
        )
        self.assertEqual(loader[-3:], [
            0xBD00 | (
                rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_INSTALLER_ADDRESS
                >> 16
            ),
            rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_INSTALLER_ADDRESS &
            0xFFFF,
            rom.RETS,
        ])
        self.assertEqual(modules["30:2966"]["source"], "4D:2966")
        self.assertEqual(modules["30:2966"]["bytes"], 0x0112)

    def test_resident_operation_descriptor_table_is_exact_embedded_data(self) -> None:
        source = rom.program_source_words(
            rom.RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SOURCE,
            rom.RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SIZE,
        )
        descriptor = rom.embed_program_data_words(
            rom.RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_DESTINATION,
            rom.RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SOURCE,
            rom.RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SIZE,
        )
        installer = rom.install_application_main_chain_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(
            rom.RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SIZE,
            20 * 14,
        )
        self.assertEqual(source[:7], [
            0x0000, 0x0027, 0xE1F6, 0x0027, 0xE1EE, 0x0027, 0xE1EC,
        ])
        self.assertEqual(source[10 * 7:11 * 7], [
            0x0000, 0x0027, 0xE132, 0x0027, 0xE12A, 0x0027, 0xE1EC,
        ])
        self.assertEqual(source[-7:], [
            0x0000, 0x0027, 0xE086, 0x0027, 0xE07E, 0x0027, 0xE1EC,
        ])
        self.assertEqual(
            rom.program_source_words(
                rom.RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SOURCE +
                rom.RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SIZE,
                4,
            ),
            [0x2E00, 0x58F0],
        )
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["30:0B0C"]["bytes"],
            rom.RESIDENT_OPERATION_DESCRIPTOR_TABLE_OVERLAY_SIZE,
        )
        self.assertEqual(
            modules["30:0B0C"]["status"],
            "exact 20-record resident operation descriptor table",
        )

    def test_resident_operation_string_pool_is_exact_embedded_data(self) -> None:
        source = rom.program_source_words(
            rom.RESIDENT_OPERATION_STRING_POOL_OVERLAY_SOURCE,
            rom.RESIDENT_OPERATION_STRING_POOL_OVERLAY_SIZE,
        )
        descriptor = rom.embed_program_data_words(
            rom.RESIDENT_OPERATION_STRING_POOL_OVERLAY_DESTINATION,
            rom.RESIDENT_OPERATION_STRING_POOL_OVERLAY_SOURCE,
            rom.RESIDENT_OPERATION_STRING_POOL_OVERLAY_SIZE,
        )
        installer = rom.install_application_main_chain_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:6], [
            0x5C2A, 0x2E74, 0x6E74, 0x0000, 0x303A, 0x5CD2,
        ])
        self.assertEqual(
            source[(0xE12A - 0xE07E) // 2:
                   (0xE12A - 0xE07E) // 2 + 4],
            [0x5C2A, 0x2E6E, 0x6466, 0x0000],
        )
        self.assertEqual(
            source[(0xE132 - 0xE07E) // 2:
                   (0xE132 - 0xE07E) // 2 + 6],
            [0x303A, 0x5CB6, 0xAFC2, 0xFEB4, 0xCAB5, 0xE400],
        )
        self.assertEqual(source[-6:], [
            0x303A, 0x5CB6, 0xAFC2, 0xFED0, 0xC0C9, 0xCD00,
        ])
        self.assertEqual(
            rom.program_source_words(
                rom.RESIDENT_OPERATION_STRING_POOL_OVERLAY_SOURCE +
                rom.RESIDENT_OPERATION_STRING_POOL_OVERLAY_SIZE,
                4,
            ),
            [0x2EFF, 0x72FF],
        )
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["27:E07E"]["bytes"],
            rom.RESIDENT_OPERATION_STRING_POOL_OVERLAY_SIZE,
        )
        self.assertEqual(
            modules["27:E07E"]["status"],
            "exact resident operation path/filter string pool",
        )

    def test_operation_ui_builder_is_preserved_before_source_29_reuse(self) -> None:
        builder = rom.program_source_words(
            rom.RESIDENT_OPERATION_UI_BUILD_OVERLAY_SOURCE,
            rom.RESIDENT_OPERATION_UI_BUILD_OVERLAY_SIZE,
        )
        action = rom.program_source_words(
            rom.APPLICATION_OPERATION_ONE_ACTION_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_ONE_ACTION_OVERLAY_SIZE,
        )
        initializer = rom.program_source_words(
            rom.APPLICATION_OPERATION_UI_INIT_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_UI_INIT_OVERLAY_SIZE,
        )
        self.assertEqual(
            builder[:9],
            [0x2E1D, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
             0x58F4, 0x58F5, 0x58F6, 0x58F7],
        )
        self.assertEqual(
            builder[-10:],
            [0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
             0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.RESIDENT_OPERATION_UI_BUILD_OVERLAY_SOURCE
                + rom.RESIDENT_OPERATION_UI_BUILD_OVERLAY_SIZE,
                2,
            ),
            [0x2E03],
        )
        self.assertEqual(
            rom.program_source_words(0x37141E, 4),
            [0xBD29, 0xCE22],
        )
        self.assertEqual(
            action[:6],
            [0x2E05, 0x58F1, 0x58F2, 0x58F3, 0x58F4, 0x58F5],
        )
        self.assertEqual(action[-2:], [0x2F00, rom.RETS])
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_OPERATION_ONE_ACTION_OVERLAY_SOURCE
                + rom.APPLICATION_OPERATION_ONE_ACTION_OVERLAY_SIZE,
                2,
            ),
            [0x2E07],
        )
        call_index = (
            0x46D284 - rom.APPLICATION_OPERATION_UI_INIT_OVERLAY_SOURCE
        ) // 2
        self.assertEqual(initializer[:5],
                         [0x2E07, 0x58F0, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(initializer[call_index:call_index + 2],
                         [0xBD0C, 0xBDBE])
        self.assertEqual(
            initializer[-6:],
            [0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )

        early_copy = rom.copy_code_to_overlay_words(
            rom.RESIDENT_OPERATION_UI_BUILD_OVERLAY_DESTINATION,
            rom.RESIDENT_OPERATION_UI_BUILD_OVERLAY_SOURCE,
            rom.RESIDENT_OPERATION_UI_BUILD_OVERLAY_SIZE,
        )
        initializer_installer = (
            rom.application_operation_ui_init_installer_words()
        )
        initializer_call = [
            0xBD00 | (
                rom.APPLICATION_OPERATION_UI_INIT_INSTALLER_ADDRESS >> 16
            ),
            rom.APPLICATION_OPERATION_UI_INIT_INSTALLER_ADDRESS & 0xFFFF,
        ]
        installer = rom.install_application_main_chain_words()
        self.assertEqual(installer[2:2 + len(early_copy)], early_copy)
        self.assertIn(
            initializer_call,
            [installer[index:index + len(initializer_call)]
             for index in range(len(installer) - len(initializer_call) + 1)],
        )
        self.assertEqual(
            initializer_installer,
            rom.embed_program_overlay_words(
                rom.APPLICATION_OPERATION_ONE_ACTION_OVERLAY_DESTINATION,
                rom.APPLICATION_OPERATION_ONE_ACTION_OVERLAY_SOURCE,
                rom.APPLICATION_OPERATION_ONE_ACTION_OVERLAY_SIZE,
            ) + rom.embed_program_overlay_words(
                rom.APPLICATION_OPERATION_UI_INIT_OVERLAY_DESTINATION,
                rom.APPLICATION_OPERATION_UI_INIT_OVERLAY_SOURCE,
                rom.APPLICATION_OPERATION_UI_INIT_OVERLAY_SIZE,
            ) + [rom.RETS],
        )
        self.assertEqual(
            rom.APPLICATION_OPERATION_UI_INIT_INSTALLER_ADDRESS
            + (len(initializer_installer) - 1) * 2,
            0x09F4C0,
        )
        self.assertIn(
            rom.APPLICATION_OPERATION_UI_INIT_OVERLAY_DESTINATION,
            rom.APPLICATION_INITIALIZER_FOLLOWUP_EMBEDDED_DESTINATIONS,
        )

        info = rom.manifest(rom.build_image())
        modules = {
            item["destination"]: item
            for item in info["application_main_chain"]
        }
        self.assertEqual(modules["0C:BDBE"]["source"], "29:BDBE")
        self.assertEqual(modules["0C:BDBE"]["bytes"], 0x349A)
        self.assertEqual(modules["29:CE22"]["source"], "46:CE22")
        self.assertEqual(modules["29:CE22"]["bytes"], 0x0298)
        self.assertEqual(modules["29:D0BA"]["source"], "46:D0BA")
        self.assertEqual(modules["29:D0BA"]["bytes"], 0x0296)
        self.assertEqual(
            words_at(
                rom.build_image(),
                rom.RESIDENT_OPERATION_UI_BUILD_OVERLAY_DESTINATION,
                len(builder),
            ),
            builder,
        )
        self.assertEqual(
            info["resident_operation_ui_build_0c_bdbe"]
                ["reachable_instructions"],
            5052,
        )

    def test_operation_browser_upstream_closure_is_exact_and_installed(self) -> None:
        router = rom.program_source_words(
            rom.APPLICATION_OPERATION_MODE_ROUTER_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_MODE_ROUTER_OVERLAY_SIZE,
        )
        dispatch = rom.program_source_words(
            rom.APPLICATION_OPERATION_NUMBER_DISPATCH_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_NUMBER_DISPATCH_OVERLAY_SIZE,
        )
        mode2 = rom.program_source_words(
            rom.RESIDENT_OPERATION_MODE2_CONTROLLER_SOURCE,
            rom.RESIDENT_OPERATION_MODE2_CONTROLLER_SIZE,
        )
        controller = rom.resident_operation_ui_controller_words()

        self.assertEqual(router[:3], [0x2E03, 0x58F0, 0x58F1])
        self.assertEqual(router[-2:], [0x2F00, rom.RETS])
        action_call = (
            0x4CB6AA - rom.APPLICATION_OPERATION_MODE_ROUTER_OVERLAY_SOURCE
        ) // 2
        self.assertEqual(
            router[action_call:action_call + 3],
            [0xBD23, 0x70E0, 0x50F2],
        )
        router_mode2 = (
            0x4CB726 - rom.APPLICATION_OPERATION_MODE_ROUTER_OVERLAY_SOURCE
        ) // 2
        self.assertEqual(router[router_mode2:router_mode2 + 2],
                         [0xBD1F, 0xD1A6])

        dispatch_table = (
            0x4AF4CA -
            rom.APPLICATION_OPERATION_NUMBER_DISPATCH_OVERLAY_SOURCE
        ) // 2
        self.assertEqual(
            dispatch[dispatch_table:dispatch_table + 8],
            [0xF4FA, 0xF502, 0xF50A, 0xF512,
             0xF51A, 0xF522, 0xF52A, 0xF532],
        )
        dispatch_operation7 = (
            0x4AF52A -
            rom.APPLICATION_OPERATION_NUMBER_DISPATCH_OVERLAY_SOURCE
        ) // 2
        self.assertEqual(
            dispatch[dispatch_operation7:dispatch_operation7 + 2],
            [0xBD1D, 0x8A3A],
        )
        self.assertEqual(dispatch[-2:], [0x2F00, rom.RETS])

        self.assertEqual(mode2[:3], [0x2E0E, 0x58F0, 0x58F1])
        mode2_dispatch = (
            0x3CD760 - rom.RESIDENT_OPERATION_MODE2_CONTROLLER_SOURCE
        ) // 2
        self.assertEqual(mode2[mode2_dispatch:mode2_dispatch + 2],
                         [0xBD2D, 0xF47C])
        self.assertEqual(mode2[-2:], [0x2F00, rom.RETS])

        self.assertEqual(controller[:3], [0x2E03, 0x58F0, 0x58F1])
        for call_address in (0x3A8EF0, 0x3A9000):
            call_index = (
                call_address - rom.RESIDENT_OPERATION_UI_CONTROLLER_SOURCE
            ) // 2
            self.assertEqual(controller[call_index:call_index + 2],
                             [0xBD29, 0xD0BA])
        builder_call = (
            0x3A90FA - rom.RESIDENT_OPERATION_UI_CONTROLLER_SOURCE
        ) // 2
        self.assertEqual(controller[builder_call:builder_call + 2],
                         [0xBD0C, 0xBDBE])
        self.assertEqual(controller[-2:], [0x2F00, rom.RETS])

        image = rom.build_image()
        self.assertEqual(
            words_at(image, rom.RESIDENT_OPERATION_MODE2_CONTROLLER_ADDRESS,
                     len(mode2)),
            mode2,
        )
        self.assertEqual(
            words_at(image, rom.RESIDENT_OPERATION_UI_CONTROLLER_ADDRESS,
                     len(controller)),
            controller,
        )

        installer = rom.install_application_main_chain_words()
        for destination, source, size in (
            (rom.APPLICATION_OPERATION_MODE_ROUTER_OVERLAY_DESTINATION,
             rom.APPLICATION_OPERATION_MODE_ROUTER_OVERLAY_SOURCE,
             rom.APPLICATION_OPERATION_MODE_ROUTER_OVERLAY_SIZE),
            (rom.APPLICATION_OPERATION_NUMBER_DISPATCH_OVERLAY_DESTINATION,
             rom.APPLICATION_OPERATION_NUMBER_DISPATCH_OVERLAY_SOURCE,
             rom.APPLICATION_OPERATION_NUMBER_DISPATCH_OVERLAY_SIZE),
        ):
            descriptor = rom.copy_code_to_overlay_words(
                destination, source, size
            )
            self.assertIn(
                descriptor,
                [installer[index:index + len(descriptor)]
                 for index in range(len(installer) - len(descriptor) + 1)],
            )

        info = rom.manifest(image)
        modules = {
            item["destination"]: item
            for item in info["application_main_chain"]
        }
        self.assertEqual(modules["2F:B644"]["source"], "4C:B644")
        self.assertEqual(modules["2D:F47C"]["source"], "4A:F47C")
        self.assertEqual(
            info["resident_operation_mode2_controller_1f_d1a6"]
                ["reachable_instructions"],
            509,
        )
        self.assertEqual(
            info["resident_operation_ui_controller_1d_8a3a"]
                ["reachable_instructions"],
            572,
        )

    def test_operation_grid_update_closure_is_exact_and_lifecycle_bound(self) -> None:
        new_journey_controller = rom.program_source_words(
            rom.RESIDENT_OPERATION_NEW_JOURNEY_CONTROLLER_SOURCE,
            rom.RESIDENT_OPERATION_NEW_JOURNEY_CONTROLLER_SIZE,
        )
        self.assertEqual(new_journey_controller[:9], [
            0x2E12, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7,
        ])
        self.assertEqual(new_journey_controller[-2:], [0x2F00, rom.RETS])
        for call, target in (
            (0x3717CE, 0x29BBF2),
            (0x3718CE, 0x1D5820),
            (0x3719B4, 0x03422C),
            (0x371C78, 0x2B21E0),
        ):
            index = (call - rom.RESIDENT_OPERATION_NEW_JOURNEY_CONTROLLER_SOURCE) // 2
            self.assertEqual(
                new_journey_controller[index:index + 2],
                [0xBD00 | (target >> 16), target & 0xFFFF],
            )
        self.assertEqual(
            rom.program_source_words(0x4AF4FA, 4),
            [0xBD1A, 0x1312],
        )
        input_controller = rom.program_source_words(
            rom.RESIDENT_OPERATION_INPUT_CONTROLLER_SOURCE,
            rom.RESIDENT_OPERATION_INPUT_CONTROLLER_SIZE,
        )
        self.assertEqual(
            input_controller[:5],
            [0x2E03, 0x58F0, 0x58F1, 0x58F2, 0x58F3],
        )
        self.assertEqual(
            input_controller[-6:],
            [0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        child_call = (
            0x3B1462 - rom.RESIDENT_OPERATION_INPUT_CONTROLLER_SOURCE
        ) // 2
        self.assertEqual(
            input_controller[child_call:child_call + 2],
            [0xBD1D, 0x0000],
        )
        input_state_update = rom.program_source_words(
            rom.RESIDENT_OPERATION_INPUT_STATE_UPDATE_SOURCE,
            rom.RESIDENT_OPERATION_INPUT_STATE_UPDATE_SIZE,
        )
        self.assertEqual(input_state_update[:9], [
            0x2E04, 0x58F1, 0x58F2, 0x58F3, 0x58F4,
            0x58F5, 0x58F6, 0x58F7, 0x4800,
        ])
        self.assertEqual(input_state_update[-9:], [
            0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, 0x2F00, rom.RETS,
        ])
        redraw_source = rom.program_source_words(
            rom.RESIDENT_GAME_REDRAW_SERVICE_SOURCE,
            rom.RESIDENT_GAME_REDRAW_SERVICE_SIZE,
        )
        self.assertEqual(redraw_source[:8], [
            0x2E01, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7,
        ])
        self.assertEqual(redraw_source[-9:], [
            0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, 0x2F00, rom.RETS,
        ])
        redraw = rom.resident_game_redraw_service_words()
        for call, linked, target in (
                rom.RESIDENT_GAME_REDRAW_SERVICE_CALL_REPAIRS):
            index = (call - rom.RESIDENT_GAME_REDRAW_SERVICE_SOURCE) // 2
            self.assertEqual(
                redraw_source[index:index + 2],
                [0xBD00 | (linked >> 16), linked & 0xFFFF],
            )
            self.assertEqual(
                redraw[index:index + 2],
                [0xBD00 | (target >> 16), target & 0xFFFF],
            )
        transition_callback = rom.program_source_words(
            rom.APPLICATION_OPERATION_TRANSITION_CALLBACK_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_TRANSITION_CALLBACK_OVERLAY_SIZE,
        )
        self.assertEqual(transition_callback[:7], [
            0x2E00, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4, 0x58F5,
        ])
        self.assertEqual(transition_callback[-2:], [0x2F00, rom.RETS])
        self.assertEqual(
            rom.program_source_words(0x371340, 4),
            [0xBD31, 0xA3F4],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_OPERATION_TRANSITION_CALLBACK_OVERLAY_DESTINATION,
                2,
            ),
            [0x6A1B],
        )
        transition_service = rom.program_source_words(
            rom.APPLICATION_OPERATION_TRANSITION_SERVICE_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_TRANSITION_SERVICE_OVERLAY_SIZE,
        )
        self.assertEqual(
            transition_service[:5],
            [0x2E00, 0x58F1, 0x6810, 0x00A1, 0x88F0],
        )
        self.assertEqual(
            transition_service[-5:],
            [0x70FF, 0x0018, 0x381F, 0x2F00, rom.RETS],
        )
        transition_service_child = rom.program_source_words(
            rom.APPLICATION_OPERATION_TRANSITION_SERVICE_CHILD_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_TRANSITION_SERVICE_CHILD_OVERLAY_SIZE,
        )
        self.assertEqual(
            transition_service_child[:5],
            [0x2E00, 0x58F1, 0x4800, 0x58F0, 0x780B],
        )
        self.assertEqual(
            transition_service_child[-5:],
            [0x70FF, 0x0016, 0x381F, 0x2F00, rom.RETS],
        )
        transition_service_leaf = rom.program_source_words(
            rom.APPLICATION_OPERATION_TRANSITION_SERVICE_LEAF_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_TRANSITION_SERVICE_LEAF_OVERLAY_SIZE,
        )
        self.assertEqual(
            transition_service_leaf[:5],
            [0x2E03, 0x58F1, 0x58F2, 0x58F3, 0x780B],
        )
        self.assertEqual(
            transition_service_leaf[-5:],
            [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
        )

        source = rom.program_source_words(
            rom.RESIDENT_OPERATION_GRID_UPDATE_SOURCE,
            rom.RESIDENT_OPERATION_GRID_UPDATE_SIZE,
        )
        resident = rom.resident_operation_grid_update_words()
        self.assertEqual(source[:9], [
            0x2E07, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7,
        ])
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        state_call = (
            0x3A5F26 - rom.RESIDENT_OPERATION_GRID_UPDATE_SOURCE
        ) // 2
        self.assertEqual(source[state_call:state_call + 2], [0xBD2B, 0x0000])
        self.assertEqual(resident[state_call:state_call + 2], [0xBD5F, 0x0000])
        child_call = (
            0x3A5BAA - rom.RESIDENT_OPERATION_GRID_UPDATE_SOURCE
        ) // 2
        self.assertEqual(resident[child_call:child_call + 2], [0xBD22, 0x4C58])

        image = rom.build_image()
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_OPERATION_NEW_JOURNEY_CONTROLLER_ADDRESS,
                len(new_journey_controller),
            ),
            new_journey_controller,
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_OPERATION_INPUT_CONTROLLER_ADDRESS,
                len(input_controller),
            ),
            input_controller,
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_OPERATION_INPUT_STATE_UPDATE_ADDRESS,
                len(input_state_update),
            ),
            input_state_update,
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_GAME_REDRAW_SERVICE_ADDRESS,
                len(redraw),
            ),
            redraw,
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_OPERATION_GRID_UPDATE_ADDRESS,
                len(resident),
            ),
            resident,
        )

        helper = rom.program_source_words(
            rom.APPLICATION_OPERATION_GRID_REPOSITION_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_GRID_REPOSITION_OVERLAY_SIZE,
        )
        self.assertEqual(helper[:9], [
            0x2E07, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7,
        ])
        self.assertEqual(helper[-2:], [0x2F00, rom.RETS])
        expected_installer = rom.copy_code_to_overlay_words(
            rom.APPLICATION_OPERATION_GRID_REPOSITION_OVERLAY_DESTINATION,
            rom.APPLICATION_OPERATION_GRID_REPOSITION_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_GRID_REPOSITION_OVERLAY_SIZE,
        )
        for source_call in (
                rom.APPLICATION_OPERATION_GRID_REPOSITION_STATE_CALL_SOURCES):
            source_index = (
                source_call -
                rom.APPLICATION_OPERATION_GRID_REPOSITION_OVERLAY_SOURCE
            ) // 2
            self.assertEqual(
                helper[source_index:source_index + 2],
                [0xBD2B, 0x0000],
            )
            destination_call = (
                rom.APPLICATION_OPERATION_GRID_REPOSITION_OVERLAY_DESTINATION +
                source_call -
                rom.APPLICATION_OPERATION_GRID_REPOSITION_OVERLAY_SOURCE
            )
            expected_installer.extend(
                rom.write_program_words(destination_call, (0xBD5F, 0x0000))
            )
        installer = rom.application_operation_grid_reposition_installer_words()
        self.assertEqual(installer, expected_installer)

        scroll_renderer = rom.program_source_words(
            rom.APPLICATION_OPERATION_SCROLL_RENDERER_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_SCROLL_RENDERER_OVERLAY_SIZE,
        )
        self.assertEqual(scroll_renderer[:9], [
            0x2E1D, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7,
        ])
        self.assertEqual(scroll_renderer[-10:], [
            0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
            0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_OPERATION_SCROLL_RENDERER_OVERLAY_DESTINATION,
                12,
            ),
            [0x76F0, 0x005A, 0xAC02, 0xD7FE, 0xAC00, 0xD738],
        )
        scroll_installer = (
            rom.application_operation_scroll_renderer_installer_words()
        )
        self.assertEqual(
            scroll_installer,
            rom.copy_code_to_overlay_words(
                rom.APPLICATION_OPERATION_SCROLL_RENDERER_OVERLAY_DESTINATION,
                rom.APPLICATION_OPERATION_SCROLL_RENDERER_OVERLAY_SOURCE,
                rom.APPLICATION_OPERATION_SCROLL_RENDERER_OVERLAY_SIZE,
            ),
        )

        wrapper = rom.npe_runtime_state_table_wrapper_words()
        self.assertIn(
            installer,
            [wrapper[index:index + len(installer)]
             for index in range(len(wrapper) - len(installer) + 1)],
        )

        new_journey_installer: list[int] = []
        entry_words = (0x2E05, 0x2E04, 0x2E06, 0x2E01,
                       0x2E07, 0x2E04, 0x2E00, 0x2E00, 0x2E00,
                       0x2E03, 0x2E01, 0x2E75, 0x2E05)
        for (destination, source_address, size), entry_word in zip(
                rom.APPLICATION_OPERATION_NEW_JOURNEY_OVERLAYS,
                entry_words,
                strict=True):
            body = rom.program_source_words(source_address, size)
            self.assertEqual(body[0], entry_word)
            self.assertEqual(body[-2:], [0x2F00, rom.RETS])
            new_journey_installer.extend(
                rom.copy_code_to_overlay_words(
                    destination, source_address, size
                )
            )
        for (source_base, destination_base, source_call,
             old_target, new_target) in (
                rom.APPLICATION_OPERATION_NEW_JOURNEY_CALL_PATCHES):
            self.assertEqual(
                rom.program_source_words(source_call, 4),
                [0xBD00 | (old_target >> 16), old_target & 0xFFFF],
            )
            destination_call = destination_base + source_call - source_base
            new_journey_installer.extend(rom.write_program_words(
                destination_call,
                (0xBD00 | (new_target >> 16), new_target & 0xFFFF),
            ))
        new_journey_installer.extend(scroll_installer)
        actual_new_journey = (
            rom.application_operation_new_journey_installer_words()
        )
        self.assertEqual(actual_new_journey, new_journey_installer)
        self.assertIn(
            [0xBD00 | (
                rom.APPLICATION_OPERATION_NEW_JOURNEY_INSTALLER_ADDRESS >> 16
            ), rom.APPLICATION_OPERATION_NEW_JOURNEY_INSTALLER_ADDRESS & 0xFFFF],
            [wrapper[index:index + 2]
             for index in range(len(wrapper) - 1)],
        )
        self.assertEqual(
            words_at(
                image,
                rom.APPLICATION_OPERATION_NEW_JOURNEY_INSTALLER_ADDRESS,
                len(actual_new_journey) + 1,
            ),
            actual_new_journey + [rom.RETS],
        )
        self.assertLessEqual(
            len(wrapper) * 2,
            0x7000 - (rom.NPE_RUNTIME_STATE_TABLE_WRAPPER_ADDRESS & 0xFFFF),
        )
        self.assertNotEqual(
            rom.APPLICATION_OPERATION_NEW_JOURNEY_INSTALLER_ADDRESS,
            rom.APPLICATION_FOREGROUND_STATE4E_INSTALLER_ADDRESS,
        )
        self.assertGreaterEqual(
            rom.APPLICATION_OPERATION_NEW_JOURNEY_INSTALLER_ADDRESS,
            rom.APPLICATION_FOREGROUND_STATE4E_INSTALLER_ADDRESS
            + len(rom.application_foreground_state4e_installer_words()) * 2,
        )
        self.assertLessEqual(
            rom.APPLICATION_OPERATION_NEW_JOURNEY_INSTALLER_ADDRESS
            + (len(actual_new_journey) + 1) * 2,
            0x1A8000,
        )

        info = rom.manifest(image)
        self.assertEqual(
            info["resident_operation_grid_update_1d_5820"]
                ["reachable_instructions"],
            704,
        )
        self.assertEqual(
            info["resident_operation_new_journey_controller_1a_1312"]
                ["reachable_instructions"],
            827,
        )
        self.assertEqual(
            info["application_operation_grid_reposition_22_4c58"]
                ["retargeted_calls"]["3F:5144"],
            "5F:0000",
        )
        self.assertEqual(
            info["application_operation_new_journey_closure"]
                ["retargeted_call_count"],
            8,
        )
        self.assertEqual(
            info["application_operation_new_journey_closure"]
                ["modules"][-1]["destination"],
            "5F:0248",
        )
        transition_module = next(
            module
            for module in info["application_operation_new_journey_closure"]
                ["modules"]
            if module["destination"] == "31:A3F4"
        )
        self.assertEqual(transition_module["source"], "4E:A3F4")
        self.assertEqual(transition_module["reachable_instructions"], 69)

    def test_operation_modal_closure_is_complete_and_installed_last(self) -> None:
        proven = tuple(
            (destination, source, size)
            for destination, source, size, _name in modal_patch.OVERLAYS
        ) + tuple(
            (destination, source, len(payload))
            for destination, source, payload, _name in modal_patch.RAW_OVERLAYS
        ) + tuple(
            (destination, source, len(payload))
            for destination, source, payload, _name
            in modal_patch.EMBEDDED_OVERLAYS
            if _name != "operation_action_mode_predicate"
        )
        closure = rom.operation_modal_closure_installer_words()
        source_repairs = sum((
            rom.embed_program_overlay_words(destination, source, size)
            for destination, source, size in
            rom.APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_OVERLAYS
        ), []) + [rom.RETS]
        clock_format = rom.embed_program_data_words(
            rom.APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_DESTINATION,
            rom.APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_SOURCE,
            rom.APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_SIZE,
        )
        padding_table = rom.embed_program_data_words(
            rom.APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_DESTINATION,
            rom.APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_SOURCE,
            rom.APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_SIZE,
        )
        start_context = rom.embed_program_overlay_words(
            rom.APPLICATION_START_CONTEXT_INIT_OVERLAY_DESTINATION,
            rom.APPLICATION_START_CONTEXT_INIT_OVERLAY_SOURCE,
            rom.APPLICATION_START_CONTEXT_INIT_OVERLAY_SIZE,
        )
        start_callback = rom.embed_program_overlay_words(
            rom.APPLICATION_START_CALLBACK_OVERLAY_DESTINATION,
            rom.APPLICATION_START_CALLBACK_OVERLAY_SOURCE,
            rom.APPLICATION_START_CALLBACK_OVERLAY_SIZE,
        )
        installer = rom.install_application_main_chain_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(
            rom.APPLICATION_OPERATION_MODAL_CLOSURE_OVERLAYS,
            proven,
        )
        self.assertEqual(
            rom.program_source_words(0x4E7772, 8),
            [0x2E2D, 0x58F1, 0x58F3, 0x68F0],
        )
        self.assertEqual(
            rom.program_source_words(0x4E7822, 2),
            [rom.RETS],
        )
        self.assertEqual(
            installer[-len(
                closure + start_context + start_callback
                + clock_format + padding_table
            ):],
            closure + start_context + start_callback
            + clock_format + padding_table,
        )
        self.assertEqual(
            closure[-2:],
            [
                0xBD00 | (
                    rom.APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_INSTALLER_ADDRESS
                    >> 16
                ),
                (rom.APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_INSTALLER_ADDRESS
                 & 0xFFFF),
            ],
        )
        self.assertEqual(
            rom.operation_modal_source_repair_installer_words(),
            source_repairs,
        )
        self.assertEqual(
            rom.APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_OVERLAYS,
            (
                (0x0C8CAA, 0x298CAA,
                 rom.APPLICATION_STATE_POINTER_OVERLAY_SIZE),
                (0x0CAC4E, 0x29AC4E,
                 rom.LCD_RESOURCE_TRANSFER_OVERLAY_SIZE),
            ),
        )
        self.assertEqual(modules["31:7772"]["source"], "4E:7772")
        self.assertEqual(modules["31:7772"]["bytes"], 0x00B2)
        self.assertEqual(modules["23:70E0"]["source"], "40:70E0")
        self.assertEqual(modules["23:70E0"]["bytes"], 0x04A4)
        action = rom.program_source_words(
            rom.APPLICATION_OPERATION_ACTION_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_ACTION_OVERLAY_SIZE,
        )
        self.assertEqual(action[:3], [0x2E09, 0x58F1, 0x780B])
        self.assertEqual(action[-2:], [0x2F00, rom.RETS])
        self.assertEqual(rom.program_source_words(0x407584, 2), [0x2E08])
        action_install = rom.copy_code_to_overlay_words(
            rom.APPLICATION_OPERATION_ACTION_OVERLAY_DESTINATION,
            rom.APPLICATION_OPERATION_ACTION_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_ACTION_OVERLAY_SIZE,
        )
        self.assertIn(
            action_install,
            [closure[index:index + len(action_install)]
             for index in range(len(closure) - len(action_install) + 1)],
        )
        self.assertEqual(modules["15:FF04"]["source"], "32:FF04")
        self.assertEqual(modules["33:5EE0"]["source"], "50:5EE0")
        self.assertEqual(
            modules["33:5EE0"]["status"],
            "exact root desktop clock format string",
        )
        self.assertEqual(
            rom.program_source_bytes(
                rom.APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_SOURCE,
                rom.APPLICATION_DESKTOP_CLOCK_FORMAT_OVERLAY_SIZE,
            ),
            bytes.fromhex("25 20 32 30 3a 69 30 25 69 32 00 00"),
        )
        self.assertEqual(modules["33:2390"]["source"], "50:2390")
        self.assertEqual(
            modules["33:2390"]["status"],
            "exact formatter space/zero padding table",
        )
        self.assertEqual(
            rom.program_source_bytes(
                rom.APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_SOURCE,
                rom.APPLICATION_FORMAT_PADDING_TABLE_OVERLAY_SIZE,
            ),
            b" " * 10 + b"0" * 16,
        )
        self.assertEqual(modules["0C:8622"]["bytes"], 0x379C)
        self.assertEqual(modules["17:CCD0"]["source"], "34:CCD0")
        self.assertEqual(modules["17:CCD0"]["bytes"], 0x0B90)
        self.assertEqual(
            rom.modal_media_browser_installer_words(),
            [
                *rom.embed_program_overlay_words(0x17CCD0, 0x34CCD0, 0x0B90),
                rom.RETS,
            ],
        )
        for destination, source, size in proven:
            descriptor = rom.operation_modal_overlay_install_words(
                destination, source, size,
            )
            self.assertIn(
                descriptor,
                [closure[i:i + len(descriptor)]
                 for i in range(len(closure) - len(descriptor) + 1)],
            )

    def test_operation_input_callback_uses_complete_same_pc_source(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_DESTINATION,
            rom.APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_SIZE,
        )
        installer = rom.install_application_main_chain_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:4], [0x2E8F, 0x58F1, 0x58F2, 0x58F3])
        self.assertIn([0xBD33, 0x315A], [
            source[i:i + 2] for i in range(len(source) - 1)
        ])
        self.assertIn([0xBD28, 0xDAC4], [
            source[i:i + 2] for i in range(len(source) - 1)
        ])
        self.assertEqual(
            source[-6:],
            [0x4800, 0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["28:DDA6"]["bytes"],
            rom.APPLICATION_OPERATION_INPUT_CALLBACK_OVERLAY_SIZE,
        )

    def test_game_world_item_callback_closure_is_exact_and_bounded(
        self,
    ) -> None:
        installer = rom.install_application_main_chain_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(b"")["application_main_chain"]
        }
        expected = (
            (
                rom.APPLICATION_MAIN_ITEM_CALLBACK_OVERLAY_DESTINATION,
                rom.APPLICATION_MAIN_ITEM_CALLBACK_OVERLAY_SOURCE,
                rom.APPLICATION_MAIN_ITEM_CALLBACK_OVERLAY_SIZE,
                [
                    0x2EFF, 0x72FF, 0x0030, 0x58F0, 0x58F1,
                    0x58F2, 0x58F3, 0x58F4, 0x58F5,
                ],
                [
                    0xBD33, 0x66E2, 0x385F, 0x384F, 0x383F,
                    0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
                ],
                0x2E0A,
            ),
            (
                rom.APPLICATION_MAIN_ITEM_CALLBACK_RANGE_OVERLAY_DESTINATION,
                rom.APPLICATION_MAIN_ITEM_CALLBACK_RANGE_OVERLAY_SOURCE,
                rom.APPLICATION_MAIN_ITEM_CALLBACK_RANGE_OVERLAY_SIZE,
                [0x2E20, 0x58F1, 0x4800, 0x58F0, 0x4801, 0x58F0],
                [
                    0xFFFC, 0x781B, 0xFFFE, 0x58F1, 0x58F0,
                    0xBD32, 0xAA26, 0x50F4, 0x4801, 0x381F,
                    0x2F00, rom.RETS,
                ],
                0x2E05,
            ),
            (
                rom.APPLICATION_MAIN_ITEM_CALLBACK_FINALIZE_OVERLAY_DESTINATION,
                rom.APPLICATION_MAIN_ITEM_CALLBACK_FINALIZE_OVERLAY_SOURCE,
                rom.APPLICATION_MAIN_ITEM_CALLBACK_FINALIZE_OVERLAY_SIZE,
                [
                    0x2E00, 0x58F0, 0x58F1, 0x68F0, 0x00F1,
                    0x58F0, 0xBD33, 0x4492, 0x50F2,
                ],
                [
                    0xBD2F, 0x0000, 0x50FA, 0x381F, 0x380F,
                    0x2F00, rom.RETS,
                ],
                0x2E00,
            ),
        )

        for destination, source, size, prefix, suffix, next_word in expected:
            body = rom.program_source_words(source, size)
            descriptor = rom.copy_code_to_overlay_words(
                destination, source, size,
            )
            self.assertEqual(body[:len(prefix)], prefix)
            self.assertEqual(body[-len(suffix):], suffix)
            self.assertEqual(
                rom.program_source_words(source + size, 2),
                [next_word],
            )
            self.assertIn(
                descriptor,
                [installer[i:i + len(descriptor)]
                 for i in range(len(installer) - len(descriptor) + 1)],
            )
            key = f"{destination >> 16:02X}:{destination & 0xFFFF:04X}"
            self.assertEqual(modules[key]["source"],
                             f"{source >> 16:02X}:{source & 0xFFFF:04X}")
            self.assertEqual(modules[key]["bytes"], size)

        # The callback reads this 19-word near-target table through Harvard
        # data space at its destination address, so it must stay inside the
        # same coherent writable code/data overlay.
        self.assertEqual(
            rom.program_source_words(0x3F175A, 0x26),
            [
                0x1834, 0x1930, 0x1930, 0x1930, 0x1930,
                0x1930, 0x1930, 0x1930, 0x1930, 0x1780,
                0x1834, 0x1834, 0x1834, 0x1834, 0x1834,
                0x1834, 0x1834, 0x1834, 0x1834,
            ],
        )
        self.assertLessEqual(
            rom.APPLICATION_MAIN_ITEM_CALLBACK_OVERLAY_DESTINATION,
            0x22175A,
        )
        self.assertGreaterEqual(
            rom.APPLICATION_MAIN_ITEM_CALLBACK_OVERLAY_DESTINATION
            + rom.APPLICATION_MAIN_ITEM_CALLBACK_OVERLAY_SIZE,
            0x221780,
        )

    def test_state_builder_callback_is_exact_complete_overlay(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_SIZE,
        )
        descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_DESTINATION,
            rom.APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_SIZE,
        )
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(source[:5], [
            0x2E00, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
        ])
        self.assertFalse(any((word & 0xFF00) == 0xBD00 for word in source))
        self.assertEqual(source[-6:], [
            0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            descriptor,
            [installer[i:i + len(descriptor)]
             for i in range(len(installer) - len(descriptor) + 1)],
        )
        self.assertEqual(
            modules["2C:A03A"]["bytes"],
            rom.APPLICATION_MAIN_STATE_CALLBACK_OVERLAY_SIZE,
        )

    def test_region_digit_dependency_closure_is_exact(self) -> None:
        installer = rom.application_region_extra_installer_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        value = rom.program_source_words(
            rom.APPLICATION_REGION_VALUE_OVERLAY_SOURCE,
            rom.APPLICATION_REGION_VALUE_OVERLAY_SIZE,
        )
        value_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_REGION_VALUE_OVERLAY_DESTINATION,
            rom.APPLICATION_REGION_VALUE_OVERLAY_SOURCE,
            rom.APPLICATION_REGION_VALUE_OVERLAY_SIZE,
        )
        self.assertEqual(value[:4], [0x2E04, 0x1F10, 0x58F4, 0x58F6])
        self.assertIn([0xBD32, 0x60D0], [
            value[i:i + 2] for i in range(len(value) - 1)
        ])
        self.assertEqual(value[-6:], [
            0x387F, 0x386F, 0x384F, 0x1F90, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            value_descriptor,
            [installer[i:i + len(value_descriptor)]
             for i in range(len(installer) - len(value_descriptor) + 1)],
        )
        self.assertEqual(
            modules["32:52F2"]["bytes"],
            rom.APPLICATION_REGION_VALUE_OVERLAY_SIZE,
        )

        normalize = rom.program_source_words(
            rom.APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_SOURCE,
            rom.APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_SIZE,
        )
        normalize_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_DESTINATION,
            rom.APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_SOURCE,
            rom.APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_SIZE,
        )
        self.assertEqual(normalize[:4], [0x4800, 0x107B, 0x106B, 0x3817])
        self.assertIn(rom.RETS, normalize)
        self.assertEqual(normalize[-5:], [
            0x0010, 0x0C2A, 0x0C3A, 0x5C20, 0xAC00,
        ])
        self.assertIn(
            normalize_descriptor,
            [installer[i:i + len(normalize_descriptor)]
             for i in range(
                 len(installer) - len(normalize_descriptor) + 1
             )],
        )
        self.assertEqual(
            modules["32:60D0"]["bytes"],
            rom.APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_SIZE,
        )

    def test_npe_direction_event_helper_is_exact_complete_overlay(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.APPLICATION_NPE_DIRECTION_EVENT_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_DIRECTION_EVENT_OVERLAY_SIZE,
        )
        relocated = rom.resident_npe_direction_event_words()
        info = rom.manifest(image)["resident_npe_direction_event_1a_7b00"]

        self.assertEqual(source[:8], [
            0x2E02, 0x58F0, 0x58F1, 0x780B,
            0x0006, 0x58F0, 0xBD33, 0x463E,
        ])
        self.assertIn([0xBD1E, 0xF734], [
            source[i:i + 2] for i in range(len(source) - 1)
        ])
        self.assertEqual(source[-4:], [0x381F, 0x380F, 0x2F00, rom.RETS])
        self.assertEqual(
            rom.APPLICATION_NPE_DIRECTION_EVENT_LINKED_DESTINATION
            + rom.APPLICATION_NPE_DIRECTION_EVENT_OVERLAY_SIZE,
            rom.APPLICATION_REGION_VALUE_NORMALIZE_OVERLAY_DESTINATION,
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_NPE_DIRECTION_EVENT_ADDRESS,
                len(relocated),
            ),
            relocated,
        )
        for branch_address, old_target in (
                rom.APPLICATION_NPE_DIRECTION_EVENT_INTERNAL_AJMPS):
            index = (
                branch_address
                - rom.APPLICATION_NPE_DIRECTION_EVENT_OVERLAY_SOURCE
            ) // 2
            expected_target = (
                rom.RESIDENT_NPE_DIRECTION_EVENT_ADDRESS
                + ((branch_address & 0xFF0000) | old_target)
                - rom.APPLICATION_NPE_DIRECTION_EVENT_OVERLAY_SOURCE
            ) & 0xFFFF
            self.assertEqual(relocated[index], source[index])
            self.assertEqual(relocated[index + 1], expected_target)
        source_call = 0x46BDDC
        self.assertNotIn(
            (rom.APPLICATION_OPERATION_NEW_JOURNEY_DRAW_OVERLAY_SOURCE,
             rom.APPLICATION_OPERATION_NEW_JOURNEY_DRAW_OVERLAY_DESTINATION,
             source_call,
             rom.RESIDENT_ROM03_NPE_DIRECTION_EVENT_TRAMPOLINE_ADDRESS,
             rom.RESIDENT_NPE_DIRECTION_EVENT_ADDRESS),
            rom.APPLICATION_OPERATION_NEW_JOURNEY_CALL_PATCHES,
        )
        self.assertEqual(
            rom.program_source_words(source_call, 4),
            [0xBD00 | (
                rom.RESIDENT_ROM03_NPE_DIRECTION_EVENT_TRAMPOLINE_ADDRESS >> 16
             ),
             rom.RESIDENT_ROM03_NPE_DIRECTION_EVENT_TRAMPOLINE_ADDRESS & 0xFFFF],
        )
        table_index = (0x03411C - rom.ROM03_JUMP_TABLE_ADDRESS) // 2
        self.assertEqual(
            rom.resident_rom03_jump_table_words()[table_index:table_index + 2],
            [0xAD00 | (rom.RESIDENT_NPE_DIRECTION_EVENT_ADDRESS >> 16),
             rom.RESIDENT_NPE_DIRECTION_EVENT_ADDRESS & 0xFFFF],
        )
        self.assertEqual(info["source"], "4F:6062")
        self.assertEqual(info["linked_destination"], "32:6062")
        self.assertEqual(info["retargeted_internal_ajmps"], 8)

    def test_application_list_state_dependency_closure_is_exact(self) -> None:
        installer = rom.install_runtime_overlay_words()
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["nested_system_overlays"]
        }
        normal = (
            (rom.APPLICATION_LIST_STATE_OVERLAY_DESTINATION,
             rom.APPLICATION_LIST_STATE_OVERLAY_SOURCE,
             rom.APPLICATION_LIST_STATE_OVERLAY_SIZE, "30:8B26", 0x2E04),
            (rom.APPLICATION_LIST_ITEM_SET_OVERLAY_DESTINATION,
             rom.APPLICATION_LIST_ITEM_SET_OVERLAY_SOURCE,
             rom.APPLICATION_LIST_ITEM_SET_OVERLAY_SIZE, "30:3A56", 0x2E04),
            (rom.APPLICATION_TABLE_MASK_OVERLAY_DESTINATION,
             rom.APPLICATION_TABLE_MASK_OVERLAY_SOURCE,
             rom.APPLICATION_TABLE_MASK_OVERLAY_SIZE, "31:8ABC", 0x2E04),
            (rom.APPLICATION_LIST_COMPACT_OVERLAY_DESTINATION,
             rom.APPLICATION_LIST_COMPACT_OVERLAY_SOURCE,
             rom.APPLICATION_LIST_COMPACT_OVERLAY_SIZE, "27:6100", 0x2E12),
            (rom.APPLICATION_LIST_CURSOR_OVERLAY_DESTINATION,
             rom.APPLICATION_LIST_CURSOR_OVERLAY_SOURCE,
             rom.APPLICATION_LIST_CURSOR_OVERLAY_SIZE, "30:699A", 0x2E01),
            (rom.APPLICATION_RANGE_FLAG_OVERLAY_DESTINATION,
             rom.APPLICATION_RANGE_FLAG_OVERLAY_SOURCE,
             rom.APPLICATION_RANGE_FLAG_OVERLAY_SIZE, "32:3332", 0x2E00),
            (rom.APPLICATION_DEVICE_VALIDATION_OVERLAY_DESTINATION,
             rom.APPLICATION_DEVICE_VALIDATION_OVERLAY_SOURCE,
             rom.APPLICATION_DEVICE_VALIDATION_OVERLAY_SIZE, "2A:A6F6", 0x2E04),
            (rom.APPLICATION_RESOURCE_LOOKUP_OVERLAY_DESTINATION,
             rom.APPLICATION_RESOURCE_LOOKUP_OVERLAY_SOURCE,
             rom.APPLICATION_RESOURCE_LOOKUP_OVERLAY_SIZE, "24:EAEC", 0x2E02),
            (rom.APPLICATION_RESOURCE_DECODE_OVERLAY_DESTINATION,
             rom.APPLICATION_RESOURCE_DECODE_OVERLAY_SOURCE,
             rom.APPLICATION_RESOURCE_DECODE_OVERLAY_SIZE, "2A:6852", 0x2E87),
            (rom.APPLICATION_RESOURCE_OPEN_OVERLAY_DESTINATION,
             rom.APPLICATION_RESOURCE_OPEN_OVERLAY_SOURCE,
             rom.APPLICATION_RESOURCE_OPEN_OVERLAY_SIZE, "32:DB08", 0x2E00),
            (rom.INT32_DIVIDE_OVERLAY_DESTINATION,
             rom.INT32_DIVIDE_OVERLAY_SOURCE,
             rom.INT32_DIVIDE_OVERLAY_SIZE, "32:1BD8", 0x2E00),
            (rom.WIDE_FROM_INT16_OVERLAY_DESTINATION,
             rom.WIDE_FROM_INT16_OVERLAY_SOURCE,
             rom.WIDE_FROM_INT16_OVERLAY_SIZE, "32:86B4", 0x2E00),
            (rom.WIDE_COMPARE_OVERLAY_DESTINATION,
             rom.WIDE_COMPARE_OVERLAY_SOURCE,
             rom.WIDE_COMPARE_OVERLAY_SIZE, "32:8716", 0x2E00),
            (rom.APPLICATION_PAIR_STORE_OVERLAY_DESTINATION,
             rom.APPLICATION_PAIR_STORE_OVERLAY_SOURCE,
             rom.APPLICATION_PAIR_STORE_OVERLAY_SIZE, "32:81D4", 0x2E00),
            (rom.APPLICATION_DRAW_CONTEXT_OVERLAY_DESTINATION,
             rom.APPLICATION_DRAW_CONTEXT_OVERLAY_SOURCE,
             rom.APPLICATION_DRAW_CONTEXT_OVERLAY_SIZE, "21:FD80", 0x2E0E),
            (rom.APPLICATION_FAR_COMPARE_ADAPTER_OVERLAY_DESTINATION,
             rom.APPLICATION_FAR_COMPARE_ADAPTER_OVERLAY_SOURCE,
             rom.APPLICATION_FAR_COMPARE_ADAPTER_OVERLAY_SIZE, "32:A922", 0x2E00),
            (rom.APPLICATION_KEY_MODE_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_MODE_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_MODE_OVERLAY_SIZE, "32:7050", 0x2E00),
            (rom.APPLICATION_KEY_ITEM_REFRESH_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_ITEM_REFRESH_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_ITEM_REFRESH_OVERLAY_SIZE, "32:E0F4", 0x2E00),
            (rom.APPLICATION_KEY_SPECIAL_ACTION_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_SPECIAL_ACTION_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_SPECIAL_ACTION_OVERLAY_SIZE, "32:C736", 0x2E00),
            (rom.APPLICATION_KEY_SPECIAL_WORKER_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_SPECIAL_WORKER_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_SPECIAL_WORKER_OVERLAY_SIZE, "25:C140", 0x2E01),
            (rom.APPLICATION_KEY_SPECIAL_RESET_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_SPECIAL_RESET_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_SPECIAL_RESET_OVERLAY_SIZE, "32:08B8", 0x2E00),
            (rom.APPLICATION_KEY_INPUT_STATE_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_INPUT_STATE_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_INPUT_STATE_OVERLAY_SIZE, "32:CEA4", 0x2E00),
            (rom.APPLICATION_KEY_DISPATCH_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_DISPATCH_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_DISPATCH_OVERLAY_SIZE, "31:4E9C", 0x2E01),
            (rom.APPLICATION_KEY_COMPLETION_WORKER_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_COMPLETION_WORKER_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_COMPLETION_WORKER_OVERLAY_SIZE,
             "28:F4A4", 0x2E03),
            (rom.APPLICATION_BIT_OR_OVERLAY_DESTINATION,
             rom.APPLICATION_BIT_OR_OVERLAY_SOURCE,
             rom.APPLICATION_BIT_OR_OVERLAY_SIZE, "31:4D24", 0x2E04),
            (rom.APPLICATION_BIT_AND_OVERLAY_DESTINATION,
             rom.APPLICATION_BIT_AND_OVERLAY_SOURCE,
             rom.APPLICATION_BIT_AND_OVERLAY_SIZE, "31:5014", 0x2E04),
        )
        for destination, source_address, size, key, first_word in normal:
            source = rom.program_source_words(source_address, size)
            descriptor = rom.copy_code_to_overlay_words(
                destination, source_address, size,
            )
            self.assertEqual(source[0], first_word)
            if key == "32:86B4":
                self.assertEqual(
                    source[39:43], [0x385F, 0x384F, 0x2F00, rom.RETS],
                )
                self.assertEqual(
                    source[-4:], [0x4810, 0x4820, 0x4830, 0xD0F6],
                )
            else:
                self.assertEqual(source[-2:], [0x2F00, rom.RETS])
            self.assertIn(
                descriptor,
                [installer[i:i + len(descriptor)]
                 for i in range(len(installer) - len(descriptor) + 1)],
            )
            self.assertEqual(modules[key]["bytes"], size)

        arithmetic_prefix = rom.program_source_words(
            rom.WIDE_ARITHMETIC_PREFIX_OVERLAY_SOURCE,
            rom.WIDE_ARITHMETIC_PREFIX_OVERLAY_SIZE,
        )
        arithmetic_prefix_descriptor = rom.copy_code_to_overlay_words(
            rom.WIDE_ARITHMETIC_PREFIX_OVERLAY_DESTINATION,
            rom.WIDE_ARITHMETIC_PREFIX_OVERLAY_SOURCE,
            rom.WIDE_ARITHMETIC_PREFIX_OVERLAY_SIZE,
        )
        self.assertEqual(arithmetic_prefix[:2], [0x2E0C, 0x1F10])
        self.assertEqual(arithmetic_prefix[-2:], [0xAD2A, 0x7C12])
        self.assertIn(
            arithmetic_prefix_descriptor,
            [installer[i:i + len(arithmetic_prefix_descriptor)]
             for i in range(
                 len(installer) - len(arithmetic_prefix_descriptor) + 1
             )],
        )
        self.assertEqual(
            modules["32:E72E"]["bytes"],
            rom.WIDE_ARITHMETIC_PREFIX_OVERLAY_SIZE,
        )

        text_dispatch_f0 = rom.program_source_words(
            rom.APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SOURCE,
            rom.APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SIZE,
        )
        text_dispatch_f0_embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_TEXT_DISPATCH_F0_OVERLAY_DESTINATION,
            rom.APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SOURCE,
            rom.APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SIZE,
        )
        self.assertEqual(text_dispatch_f0[0], 0x2E00)
        self.assertEqual(text_dispatch_f0[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            text_dispatch_f0_embedded,
            [installer[i:i + len(text_dispatch_f0_embedded)]
             for i in range(
                 len(installer) - len(text_dispatch_f0_embedded) + 1
             )],
        )
        self.assertEqual(
            modules["33:00A8"]["bytes"],
            rom.APPLICATION_TEXT_DISPATCH_F0_OVERLAY_SIZE,
        )

        extra_installer = rom.application_region_extra_installer_words()
        conditional_worker = rom.program_source_words(
            rom.APPLICATION_MAIN_CONDITIONAL_WORKER_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_CONDITIONAL_WORKER_OVERLAY_SIZE,
        )
        conditional_worker_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_MAIN_CONDITIONAL_WORKER_OVERLAY_DESTINATION,
            rom.APPLICATION_MAIN_CONDITIONAL_WORKER_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_CONDITIONAL_WORKER_OVERLAY_SIZE,
        )
        self.assertEqual(conditional_worker[:4], [
            0x2E03, 0x58F0, 0x58F1, 0x58F2,
        ])
        self.assertIn([0xBD33, 0x4C7A], [
            conditional_worker[i:i + 2]
            for i in range(len(conditional_worker) - 1)
        ])
        self.assertEqual(conditional_worker[-8:], [
            0x385F, 0x384F, 0x383F, 0x382F,
            0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            conditional_worker_descriptor,
            [extra_installer[i:i + len(conditional_worker_descriptor)]
             for i in range(
                 len(extra_installer) - len(conditional_worker_descriptor) + 1
             )],
        )
        self.assertEqual(
            modules["2C:7BA8"]["bytes"],
            rom.APPLICATION_MAIN_CONDITIONAL_WORKER_OVERLAY_SIZE,
        )

        flag_clear = rom.program_source_words(
            rom.APPLICATION_MAIN_FLAG_CLEAR_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_FLAG_CLEAR_OVERLAY_SIZE,
        )
        flag_clear_embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_MAIN_FLAG_CLEAR_OVERLAY_DESTINATION,
            rom.APPLICATION_MAIN_FLAG_CLEAR_OVERLAY_SOURCE,
            rom.APPLICATION_MAIN_FLAG_CLEAR_OVERLAY_SIZE,
        )
        self.assertEqual(flag_clear, [
            0x2E00, 0x58F1, 0x68F1, 0xFFFE,
            0x6810, 0x00A2, 0xB4F1, 0x2A4E,
            0x381F, 0x2F00, rom.RETS,
        ])
        self.assertIn(
            flag_clear_embedded,
            [extra_installer[i:i + len(flag_clear_embedded)]
             for i in range(
                 len(extra_installer) - len(flag_clear_embedded) + 1
             )],
        )
        self.assertEqual(
            modules["33:4C7A"]["bytes"],
            rom.APPLICATION_MAIN_FLAG_CLEAR_OVERLAY_SIZE,
        )

        value_operator = rom.program_source_words(
            rom.WIDE_VALUE_OPERATOR_OVERLAY_SOURCE,
            rom.WIDE_VALUE_OPERATOR_OVERLAY_SIZE,
        )
        divide_step = rom.program_source_words(
            rom.WIDE_DIVIDE_STEP_OVERLAY_SOURCE,
            rom.WIDE_DIVIDE_STEP_OVERLAY_SIZE,
        )
        shift_right = rom.program_source_words(
            rom.WIDE_SHIFT_RIGHT_OVERLAY_SOURCE,
            rom.WIDE_SHIFT_RIGHT_OVERLAY_SIZE,
        )
        self.assertEqual(value_operator[:2], [0x2E0C, 0x1F10])
        self.assertEqual(value_operator[-2:], [0xAC00, 0x793A])
        self.assertIn([0x2F00, rom.RETS], [
            value_operator[i:i + 2]
            for i in range(len(value_operator) - 1)
        ])
        self.assertEqual(divide_step[:2], [0x787B, 0xFFF4])
        self.assertEqual(divide_step[-1], rom.RETS)
        self.assertEqual(shift_right, [
            0x0D4B, 0x0D3B, 0x5D40, 0x0D2B, 0x5D30,
            0x0D1B, 0x5D20, 0x0D0B, 0x5D10, rom.RETS,
        ])
        for destination, source_address, size, key in (
            (rom.WIDE_VALUE_OPERATOR_OVERLAY_DESTINATION,
             rom.WIDE_VALUE_OPERATOR_OVERLAY_SOURCE,
             rom.WIDE_VALUE_OPERATOR_OVERLAY_SIZE, "2C:77C8"),
            (rom.WIDE_DIVIDE_STEP_OVERLAY_DESTINATION,
             rom.WIDE_DIVIDE_STEP_OVERLAY_SOURCE,
             rom.WIDE_DIVIDE_STEP_OVERLAY_SIZE, "2F:B3E4"),
        ):
            descriptor = rom.copy_code_to_overlay_words(
                destination, source_address, size,
            )
            self.assertIn(
                descriptor,
                [installer[i:i + len(descriptor)]
                 for i in range(len(installer) - len(descriptor) + 1)],
            )
            self.assertEqual(modules[key]["bytes"], size)
        shift_embedded = rom.embed_program_overlay_words(
            rom.WIDE_SHIFT_RIGHT_OVERLAY_DESTINATION,
            rom.WIDE_SHIFT_RIGHT_OVERLAY_SOURCE,
            rom.WIDE_SHIFT_RIGHT_OVERLAY_SIZE,
        )
        self.assertIn(
            shift_embedded,
            [installer[i:i + len(shift_embedded)]
             for i in range(len(installer) - len(shift_embedded) + 1)],
        )
        self.assertEqual(
            modules["33:5004"]["bytes"],
            rom.WIDE_SHIFT_RIGHT_OVERLAY_SIZE,
        )

        for destination, source_address, size, key, child in (
            (rom.APPLICATION_KEY_ITEM_CLEAR_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_ITEM_CLEAR_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_ITEM_CLEAR_OVERLAY_SIZE,
             "33:468C", [0xBD30, 0x8B26]),
            (rom.APPLICATION_KEY_ITEM_SET_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_ITEM_SET_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_ITEM_SET_OVERLAY_SIZE,
             "33:4D2A", [0xBD30, 0x3A56]),
        ):
            source = rom.program_source_words(source_address, size)
            embedded = rom.embed_program_overlay_words(
                destination, source_address, size,
            )
            self.assertEqual(source[:2], [0x2E00, 0x58F0])
            self.assertIn(child, [
                source[i:i + 2] for i in range(len(source) - 1)
            ])
            self.assertEqual(source[-2:], [0x2F00, rom.RETS])
            self.assertIn(
                embedded,
                [installer[i:i + len(embedded)]
                 for i in range(len(installer) - len(embedded) + 1)],
            )
            self.assertEqual(modules[key]["bytes"], size)

        key_hw_clear = rom.program_source_words(
            rom.APPLICATION_KEY_HW_CLEAR_OVERLAY_SOURCE,
            rom.APPLICATION_KEY_HW_CLEAR_OVERLAY_SIZE,
        )
        key_hw_clear_embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_KEY_HW_CLEAR_OVERLAY_DESTINATION,
            rom.APPLICATION_KEY_HW_CLEAR_OVERLAY_SOURCE,
            rom.APPLICATION_KEY_HW_CLEAR_OVERLAY_SIZE,
        )
        self.assertEqual(key_hw_clear[:4], [
            0x2E00, 0x58F0, 0x68F0, 0xFFFB,
        ])
        self.assertEqual(key_hw_clear[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            key_hw_clear_embedded,
            [extra_installer[i:i + len(key_hw_clear_embedded)]
             for i in range(
                 len(extra_installer) - len(key_hw_clear_embedded) + 1
             )],
        )
        self.assertEqual(
            modules["33:391A"]["bytes"],
            rom.APPLICATION_KEY_HW_CLEAR_OVERLAY_SIZE,
        )

        for destination, source_address, size, key, mask_word in (
            (rom.APPLICATION_KEY_HW_PATH_A_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_HW_PATH_A_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_HW_PATH_A_OVERLAY_SIZE,
             "33:393C", 0xBFFF),
            (rom.APPLICATION_KEY_HW_PATH_B_OVERLAY_DESTINATION,
             rom.APPLICATION_KEY_HW_PATH_B_OVERLAY_SOURCE,
             rom.APPLICATION_KEY_HW_PATH_B_OVERLAY_SIZE,
             "33:395E", 0xFF7F),
        ):
            source = rom.program_source_words(source_address, size)
            embedded = rom.embed_program_overlay_words(
                destination, source_address, size,
            )
            self.assertEqual(source[:3], [0x2E00, 0x58F0, 0x68F0])
            self.assertEqual(source[3], mask_word)
            self.assertEqual(source[-2:], [0x2F00, rom.RETS])
            self.assertIn(
                embedded,
                [installer[i:i + len(embedded)]
                 for i in range(len(installer) - len(embedded) + 1)],
            )
            self.assertEqual(modules[key]["bytes"], size)

        key_completion = rom.program_source_words(
            rom.APPLICATION_KEY_COMPLETION_OVERLAY_SOURCE,
            rom.APPLICATION_KEY_COMPLETION_OVERLAY_SIZE,
        )
        key_completion_embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_KEY_COMPLETION_OVERLAY_DESTINATION,
            rom.APPLICATION_KEY_COMPLETION_OVERLAY_SOURCE,
            rom.APPLICATION_KEY_COMPLETION_OVERLAY_SIZE,
        )
        self.assertEqual(key_completion[:2], [0x2E00, 0x4800])
        self.assertIn([0xBD28, 0xF4A4], [
            key_completion[i:i + 2]
            for i in range(len(key_completion) - 1)
        ])
        self.assertEqual(key_completion[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            key_completion_embedded,
            [installer[i:i + len(key_completion_embedded)]
             for i in range(
                 len(installer) - len(key_completion_embedded) + 1
             )],
        )
        self.assertEqual(
            modules["33:38F8"]["bytes"],
            rom.APPLICATION_KEY_COMPLETION_OVERLAY_SIZE,
        )

        crc = rom.program_source_words(
            rom.APPLICATION_KEY_SPECIAL_CRC_OVERLAY_SOURCE,
            rom.APPLICATION_KEY_SPECIAL_CRC_OVERLAY_SIZE,
        )
        crc_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_KEY_SPECIAL_CRC_OVERLAY_DESTINATION,
            rom.APPLICATION_KEY_SPECIAL_CRC_OVERLAY_SOURCE,
            rom.APPLICATION_KEY_SPECIAL_CRC_OVERLAY_SIZE,
        )
        self.assertEqual(crc[:2], [0x2E14, 0x58F0])
        self.assertEqual(crc[-3:], [0x2F00, 0x3F00, rom.RETS])
        self.assertIn(
            crc_descriptor,
            [installer[i:i + len(crc_descriptor)]
             for i in range(len(installer) - len(crc_descriptor) + 1)],
        )
        crc_table = rom.program_source_words(
            rom.APPLICATION_KEY_SPECIAL_CRC_TABLE_SOURCE,
            rom.APPLICATION_KEY_SPECIAL_CRC_TABLE_SIZE,
        )
        crc_table_descriptor = rom.copy_code_to_overlay_words(
            rom.APPLICATION_KEY_SPECIAL_CRC_TABLE_DESTINATION,
            rom.APPLICATION_KEY_SPECIAL_CRC_TABLE_SOURCE,
            rom.APPLICATION_KEY_SPECIAL_CRC_TABLE_SIZE,
        )
        self.assertEqual(len(crc_table), 256)
        self.assertEqual(crc_table[:4], [0x0000, 0x1021, 0x2042, 0x3063])
        self.assertEqual(crc_table[-4:], [0x2E93, 0x3EB2, 0x0ED1, 0x1EF0])
        self.assertIn(
            crc_table_descriptor,
            [installer[i:i + len(crc_table_descriptor)]
             for i in range(
                 len(installer) - len(crc_table_descriptor) + 1
             )],
        )
        self.assertEqual(
            modules["0D:8552"]["bytes"],
            rom.APPLICATION_KEY_SPECIAL_CRC_OVERLAY_SIZE,
        )
        self.assertEqual(
            modules["1B:860E"]["bytes"],
            rom.APPLICATION_KEY_SPECIAL_CRC_TABLE_SIZE,
        )

        wide_dispatch = rom.program_source_words(
            rom.WIDE_OPERATION_DISPATCH_OVERLAY_SOURCE,
            rom.WIDE_OPERATION_DISPATCH_OVERLAY_SIZE,
        )
        wide_dispatch_descriptor = rom.copy_code_to_overlay_words(
            rom.WIDE_OPERATION_DISPATCH_OVERLAY_DESTINATION,
            rom.WIDE_OPERATION_DISPATCH_OVERLAY_SOURCE,
            rom.WIDE_OPERATION_DISPATCH_OVERLAY_SIZE,
        )
        self.assertEqual(wide_dispatch, [
            0x2E0C, 0x1F10,
            0x58F0, 0x58F1, 0x58F2, 0x58F3,
            0x58F4, 0x58F5, 0x58F6, 0x58F7,
            0xBD33, 0x11A0, 0xD202, 0xAD2A, 0x7E28,
            0xBD33, 0x1188, 0xD206,
            0x68F0, 0x8000, 0x6A0B, 0xFFE8, 0xAD2A, 0x7E02,
            0x6810, 0x0000, 0xBD2A, 0x7BD2,
            0x68F0, 0x8000, 0x6A0B, 0xFFE8,
            0x77F4, 0x8000, 0xAD2A, 0x7C12,
        ])
        self.assertIn(
            wide_dispatch_descriptor,
            [installer[i:i + len(wide_dispatch_descriptor)]
             for i in range(len(installer) - len(wide_dispatch_descriptor) + 1)],
        )
        self.assertEqual(
            modules["32:D218"]["bytes"],
            rom.WIDE_OPERATION_DISPATCH_OVERLAY_SIZE,
        )
        wide_arithmetic = rom.program_source_words(
            rom.WIDE_ARITHMETIC_OVERLAY_SOURCE,
            rom.WIDE_ARITHMETIC_OVERLAY_SIZE,
        )
        wide_arithmetic_descriptor = rom.copy_code_to_overlay_words(
            rom.WIDE_ARITHMETIC_OVERLAY_DESTINATION,
            rom.WIDE_ARITHMETIC_OVERLAY_SOURCE,
            rom.WIDE_ARITHMETIC_OVERLAY_SIZE,
        )
        self.assertEqual(len(wide_arithmetic), 0x0136)
        self.assertEqual(
            wide_arithmetic[:7],
            [0x58F4, 0x58F5, 0x0850, 0xBD33, 0x2AA2, 0x9B75, 0x0F0C],
        )
        self.assertEqual(
            wide_arithmetic[0x0040 // 2:0x0040 // 2 + 5],
            [0x0804, 0x0815, 0x0826, 0x0837, 0x0854],
        )
        self.assertEqual(
            wide_arithmetic[0x0230 // 2:0x0230 // 2 + 4],
            [0x383F, 0x382F, 0x381F, 0x280F],
        )
        self.assertEqual(wide_arithmetic[-3:], [0x1F90, 0x2F00, rom.RETS])
        self.assertIn(
            wide_arithmetic_descriptor,
            [installer[i:i + len(wide_arithmetic_descriptor)]
             for i in range(len(installer) - len(wide_arithmetic_descriptor) + 1)],
        )
        self.assertEqual(
            modules["2A:7BD2"]["bytes"],
            rom.WIDE_ARITHMETIC_OVERLAY_SIZE,
        )

        object_release = rom.program_source_words(
            rom.APPLICATION_OBJECT_RELEASE_OVERLAY_SOURCE,
            rom.APPLICATION_OBJECT_RELEASE_OVERLAY_SIZE,
        )
        object_release_embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_OBJECT_RELEASE_OVERLAY_DESTINATION,
            rom.APPLICATION_OBJECT_RELEASE_OVERLAY_SOURCE,
            rom.APPLICATION_OBJECT_RELEASE_OVERLAY_SIZE,
        )
        self.assertEqual(object_release[0], 0x2E00)
        self.assertEqual(
            object_release[10:14], [0xBD33, 0x468C, 0x50F2, 0x780B],
        )
        self.assertEqual(
            object_release[16:20], [0xBD33, 0x4D2A, 0x50F2, 0x380F],
        )
        self.assertEqual(object_release[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            object_release_embedded,
            [installer[i:i + len(object_release_embedded)]
             for i in range(
                 len(installer) - len(object_release_embedded) + 1
             )],
        )
        self.assertEqual(
            modules["33:1DF6"]["bytes"],
            rom.APPLICATION_OBJECT_RELEASE_OVERLAY_SIZE,
        )

        decimal_parse = rom.program_source_words(
            rom.APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SOURCE,
            rom.APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SIZE,
        )
        decimal_parse_embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_DESTINATION,
            rom.APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SOURCE,
            rom.APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SIZE,
        )
        self.assertEqual(decimal_parse[0], 0x2E00)
        self.assertEqual(decimal_parse[2:4], [0x481A, 0x58F1])
        self.assertEqual(decimal_parse[14:16], [0xBD32, 0xF7FC])
        self.assertEqual(decimal_parse[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            decimal_parse_embedded,
            [installer[i:i + len(decimal_parse_embedded)]
             for i in range(
                 len(installer) - len(decimal_parse_embedded) + 1
             )],
        )
        self.assertEqual(
            modules["33:1F4E"]["bytes"],
            rom.APPLICATION_DECIMAL_PARSE_WRAPPER_OVERLAY_SIZE,
        )

        decimal_parse_core = rom.program_source_words(
            rom.APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SOURCE,
            rom.APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SIZE,
        )
        decimal_parse_core_embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_DESTINATION,
            rom.APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SOURCE,
            rom.APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SIZE,
        )
        self.assertEqual(decimal_parse_core[0], 0x2E00)
        self.assertEqual(
            decimal_parse_core[24:26], [0xBD24, 0x2C32],
        )
        self.assertEqual(decimal_parse_core[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            decimal_parse_core_embedded,
            [installer[i:i + len(decimal_parse_core_embedded)]
             for i in range(
                 len(installer) - len(decimal_parse_core_embedded) + 1
             )],
        )
        self.assertEqual(
            modules["32:F7FC"]["bytes"],
            rom.APPLICATION_DECIMAL_PARSE_CORE_OVERLAY_SIZE,
        )

        decimal_parse_engine = rom.program_source_words(
            rom.APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SOURCE,
            rom.APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SIZE,
        )
        decimal_parse_engine_embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_DESTINATION,
            rom.APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SOURCE,
            rom.APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SIZE,
        )
        self.assertEqual(decimal_parse_engine[0], 0x2E10)
        self.assertIn(
            [0xBD33, 0x249A],
            [decimal_parse_engine[i:i + 2]
             for i in range(len(decimal_parse_engine) - 1)],
        )
        self.assertIn(
            [0xBD33, 0x24EA],
            [decimal_parse_engine[i:i + 2]
             for i in range(len(decimal_parse_engine) - 1)],
        )
        self.assertEqual(decimal_parse_engine[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            decimal_parse_engine_embedded,
            [installer[i:i + len(decimal_parse_engine_embedded)]
             for i in range(
                 len(installer) - len(decimal_parse_engine_embedded) + 1
             )],
        )
        self.assertEqual(
            modules["24:2C32"]["bytes"],
            rom.APPLICATION_DECIMAL_PARSE_ENGINE_OVERLAY_SIZE,
        )

        ascii_whitespace = rom.program_source_words(
            rom.APPLICATION_ASCII_WHITESPACE_OVERLAY_SOURCE,
            rom.APPLICATION_ASCII_WHITESPACE_OVERLAY_SIZE,
        )
        ascii_whitespace_embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_ASCII_WHITESPACE_OVERLAY_DESTINATION,
            rom.APPLICATION_ASCII_WHITESPACE_OVERLAY_SOURCE,
            rom.APPLICATION_ASCII_WHITESPACE_OVERLAY_SIZE,
        )
        self.assertEqual(ascii_whitespace[0], 0x2E00)
        self.assertEqual(ascii_whitespace[3:5], [0x5609, 0xD908])
        self.assertEqual(ascii_whitespace[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            ascii_whitespace_embedded,
            [installer[i:i + len(ascii_whitespace_embedded)]
             for i in range(
                 len(installer) - len(ascii_whitespace_embedded) + 1
             )],
        )
        self.assertEqual(
            modules["33:3BE6"]["bytes"],
            rom.APPLICATION_ASCII_WHITESPACE_OVERLAY_SIZE,
        )

        for destination, source, size, call in (
            (rom.UINT32_MODULO_WRAPPER_OVERLAY_DESTINATION,
             rom.UINT32_MODULO_WRAPPER_OVERLAY_SOURCE,
             rom.UINT32_MODULO_WRAPPER_OVERLAY_SIZE,
             [0xBD31, 0x6A14]),
            (rom.INT32_MODULO_WRAPPER_OVERLAY_DESTINATION,
             rom.INT32_MODULO_WRAPPER_OVERLAY_SOURCE,
             rom.INT32_MODULO_WRAPPER_OVERLAY_SIZE,
             [0xBD32, 0x1BD8]),
        ):
            modulo_wrapper = rom.program_source_words(source, size)
            modulo_embedded = rom.embed_program_overlay_words(
                destination, source, size,
            )
            self.assertEqual(modulo_wrapper[0], 0x2E00)
            self.assertEqual(modulo_wrapper[13:17], [0x4800, 0x58F0] + call)
            self.assertEqual(modulo_wrapper[-2:], [0x2F00, rom.RETS])
            self.assertIn(
                modulo_embedded,
                [installer[i:i + len(modulo_embedded)]
                 for i in range(len(installer) - len(modulo_embedded) + 1)],
            )
        self.assertEqual(
            modules["33:249A"]["bytes"],
            rom.UINT32_MODULO_WRAPPER_OVERLAY_SIZE,
        )
        self.assertEqual(
            modules["33:24C2"]["bytes"],
            rom.INT32_MODULO_WRAPPER_OVERLAY_SIZE,
        )

        wrapper = rom.program_source_words(
            rom.INT32_DIVIDE_WRAPPER_OVERLAY_SOURCE,
            rom.INT32_DIVIDE_WRAPPER_OVERLAY_SIZE,
        )
        embedded = rom.embed_program_overlay_words(
            rom.INT32_DIVIDE_WRAPPER_OVERLAY_DESTINATION,
            rom.INT32_DIVIDE_WRAPPER_OVERLAY_SOURCE,
            rom.INT32_DIVIDE_WRAPPER_OVERLAY_SIZE,
        )
        self.assertEqual(wrapper[0], 0x2E00)
        self.assertEqual(wrapper[-2:], [0x2F00, rom.RETS])
        self.assertIn(
            embedded,
            [installer[i:i + len(embedded)]
             for i in range(len(installer) - len(embedded) + 1)],
        )
        self.assertEqual(
            modules["33:2512"]["bytes"],
            rom.INT32_DIVIDE_WRAPPER_OVERLAY_SIZE,
        )
        dispatch = rom.program_source_words(
            rom.WIDE_REGISTER_DISPATCH_OVERLAY_SOURCE,
            rom.WIDE_REGISTER_DISPATCH_OVERLAY_SIZE,
        )
        dispatch_embedded = rom.embed_program_overlay_words(
            rom.WIDE_REGISTER_DISPATCH_OVERLAY_DESTINATION,
            rom.WIDE_REGISTER_DISPATCH_OVERLAY_SOURCE,
            rom.WIDE_REGISTER_DISPATCH_OVERLAY_SIZE,
        )
        self.assertEqual(dispatch, [
            0x0E04, 0x0E15, 0x0E26, 0x0E37, 0xAD32, 0xD218,
            0x0804, 0x0815, 0x0826, 0x0837, 0xAD33, 0x4B88,
            0x0E04, 0x0E15, 0x0E26, 0x0E37, 0xAD2C, 0x77C8,
            0x0E04, 0x0E15, 0x0E26, 0x0E37, 0xAD32, 0x8716,
        ])
        self.assertIn(
            dispatch_embedded,
            [installer[i:i + len(dispatch_embedded)]
             for i in range(len(installer) - len(dispatch_embedded) + 1)],
        )
        self.assertEqual(
            modules["33:5DE4"]["bytes"],
            rom.WIDE_REGISTER_DISPATCH_OVERLAY_SIZE,
        )
        sign_normalize = rom.program_source_words(
            rom.WIDE_SIGN_NORMALIZE_OVERLAY_SOURCE,
            rom.WIDE_SIGN_NORMALIZE_OVERLAY_SIZE,
        )
        sign_normalize_embedded = rom.embed_program_overlay_words(
            rom.WIDE_SIGN_NORMALIZE_OVERLAY_DESTINATION,
            rom.WIDE_SIGN_NORMALIZE_OVERLAY_SOURCE,
            rom.WIDE_SIGN_NORMALIZE_OVERLAY_SIZE,
        )
        self.assertEqual(sign_normalize, [
            0xFF70, 0x0840, 0x544F, 0x4D04, 0xD102, 0xE474, rom.RETS,
            0x4C41, 0x4C11, 0x5C40, 0x4C21, 0x5C10, 0x4C31, 0x5C20,
            0x9A74, 0x0402, 0x5201, 0xD0F5, rom.RETS,
        ])
        self.assertIn(
            sign_normalize_embedded,
            [installer[i:i + len(sign_normalize_embedded)]
             for i in range(len(installer) - len(sign_normalize_embedded) + 1)],
        )
        self.assertEqual(
            modules["33:2AA2"]["bytes"],
            rom.WIDE_SIGN_NORMALIZE_OVERLAY_SIZE,
        )
        for destination, source_address, size, key, first_word in (
            (rom.WIDE_LEFT_NONZERO_OVERLAY_DESTINATION,
             rom.WIDE_LEFT_NONZERO_OVERLAY_SOURCE,
             rom.WIDE_LEFT_NONZERO_OVERLAY_SIZE, "33:1188", 0x5630),
            (rom.WIDE_RIGHT_NONZERO_OVERLAY_DESTINATION,
             rom.WIDE_RIGHT_NONZERO_OVERLAY_SOURCE,
             rom.WIDE_RIGHT_NONZERO_OVERLAY_SIZE, "33:11A0", 0x5670),
        ):
            source = rom.program_source_words(source_address, size)
            embedded = rom.embed_program_overlay_words(
                destination, source_address, size,
            )
            self.assertEqual(source[0], first_word)
            self.assertEqual(source[-1], rom.RETS)
            self.assertIn(
                embedded,
                [installer[i:i + len(embedded)]
                 for i in range(len(installer) - len(embedded) + 1)],
            )
            self.assertEqual(modules[key]["bytes"], size)

    def test_resident_transform_modules_are_exact_guest_code(self) -> None:
        image = rom.build_image()
        info = rom.manifest(image)
        routines = rom.make_routines()

        for address, source_address, size, manifest_key, first_word in (
            (rom.RESIDENT_OPERATION_1B23B8_ADDRESS,
             rom.RESIDENT_OPERATION_1B23B8_SOURCE,
             rom.RESIDENT_OPERATION_1B23B8_SIZE,
             "resident_operation_1b_23b8", 0x2EA9),
            (rom.RESIDENT_TRANSFORM_1B_ADDRESS,
             rom.RESIDENT_TRANSFORM_1B_SOURCE,
             rom.RESIDENT_TRANSFORM_1B_SIZE,
             "resident_transform_1b", 0x2E08),
            (rom.RESIDENT_TRANSFORM_1C_ADDRESS,
             rom.RESIDENT_TRANSFORM_1C_SOURCE,
             rom.RESIDENT_TRANSFORM_1C_SIZE,
             "resident_transform_1c", 0x2E13),
        ):
            source = rom.program_source_words(source_address, size)
            installed = routines[address][1]
            self.assertEqual(words_at(image, address, len(installed)), installed)
            if address == rom.RESIDENT_OPERATION_1B23B8_ADDRESS:
                self.assertEqual(installed, source)
            self.assertEqual(source[0], first_word)
            self.assertEqual(source[-2:], [0x2F00, rom.RETS])
            self.assertEqual(info[manifest_key]["bytes"], size)

    def test_resident_operation_dispatch_table_is_exact_harvard_data(
        self,
    ) -> None:
        image = rom.build_image()
        info = rom.manifest(image)
        expected = [
            0x29C2, 0x2A7C, 0x2A7C, 0x2A7C, 0x2A7C,
            0x2A7C, 0x2A7C, 0x2A7C, 0x2A7C, 0x29DC,
            0x2A08, 0x2A3C, 0x2A56, 0x2A56, 0x2A56,
            0x2A56, 0x2A56, 0x2A56, 0x2A22,
        ]
        source = rom.program_source_words(
            rom.RESIDENT_OPERATION_DISPATCH_TABLE_SOURCE,
            rom.RESIDENT_OPERATION_DISPATCH_TABLE_SIZE,
        )
        installed = words_at(
            image,
            rom.RESIDENT_OPERATION_DISPATCH_TABLE_ADDRESS,
            len(expected),
        )

        self.assertEqual(source, expected)
        self.assertEqual(installed, expected)
        self.assertGreaterEqual(
            rom.RESIDENT_OPERATION_DISPATCH_TABLE_ADDRESS,
            rom.RESIDENT_OPERATION_1B23B8_ADDRESS,
        )
        self.assertLessEqual(
            (rom.RESIDENT_OPERATION_DISPATCH_TABLE_ADDRESS +
             rom.RESIDENT_OPERATION_DISPATCH_TABLE_SIZE),
            rom.RESIDENT_OPERATION_1B23B8_ADDRESS +
            rom.RESIDENT_OPERATION_1B23B8_SIZE,
        )
        table = info["resident_operation_dispatch_table_1b_299c"]
        self.assertEqual(table["destination"], "1B:299C")
        self.assertEqual(table["source"], "38:299C")
        self.assertEqual(table["bytes"], 0x26)
        self.assertEqual(table["targets"][0], "1B:29C2")
        self.assertEqual(
            table["status"],
            "exact inline RET-dispatch table; Harvard data alias",
        )

    def test_resident_record_range_worker_is_exact_and_bounded(self) -> None:
        image = rom.build_image()
        source = rom.program_source_words(
            rom.RESIDENT_RECORD_RANGE_WORKER_SOURCE,
            rom.RESIDENT_RECORD_RANGE_WORKER_SIZE,
        )
        installed = rom.make_routines()[
            rom.RESIDENT_RECORD_RANGE_WORKER_ADDRESS
        ][1]
        info = rom.manifest(image)["resident_record_range_worker_1b_2c92"]

        self.assertEqual(source[:4], [0x780B, 0x0006, 0x781B, 0x0008])
        self.assertEqual(
            source[-9:],
            [0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
             0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            rom.program_source_words(
                rom.RESIDENT_RECORD_RANGE_WORKER_SOURCE
                + rom.RESIDENT_RECORD_RANGE_WORKER_SIZE,
                2,
            ),
            [0x2E07],
        )
        self.assertEqual(
            rom.RESIDENT_OPERATION_1B23B8_ADDRESS
            + rom.RESIDENT_OPERATION_1B23B8_SIZE,
            rom.RESIDENT_RECORD_RANGE_WORKER_ADDRESS,
        )
        self.assertEqual(
            rom.program_source_words(0x2F377E, 4),
            [0xBD1B, 0x2C92],
        )
        self.assertEqual(installed, source)
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_RECORD_RANGE_WORKER_ADDRESS,
                len(source),
            ),
            source,
        )
        self.assertEqual(info["source"], "3B:2C92")
        self.assertEqual(info["bytes"], 0x02AA)
        self.assertEqual(info["reachable_instructions"], 240)
        self.assertEqual(info["caller"], "2F:377E")

    def test_npe_format_literal_source_is_exact_and_lifecycle_bound(self) -> None:
        image = rom.build_image()
        info = rom.manifest(image)
        words = rom.program_source_words(
            rom.APPLICATION_NPE_FORMAT_LITERAL_DATA_SOURCE,
            rom.APPLICATION_NPE_FORMAT_LITERAL_DATA_SIZE,
        )
        logical = b"".join(word.to_bytes(2, "big") for word in words)

        self.assertEqual(
            logical,
            b"NP560 RPG\0NP580 Ver1.0\0\0NP560 Ver1.0\0\0",
        )
        self.assertEqual(len(logical), 0x26)
        self.assertEqual(logical[0x00:0x09], b"NP560 RPG")
        self.assertEqual(logical[0x0A:0x16], b"NP580 Ver1.0")
        self.assertEqual(logical[0x18:0x24], b"NP560 Ver1.0")
        entry = info["application_npe_format_literal_data_32_4956"]
        self.assertEqual(entry["destination"], "32:4956")
        self.assertEqual(entry["source"], "4F:4956")
        self.assertEqual(entry["bytes"], 0x26)
        self.assertEqual(entry["wrapper"], "06:6B20")
        self.assertIn("installed on demand", entry["status"])

        self.assertIn("data-only QEMU Harvard RAM window", entry["status"])
        self.assertIn("no source alias or literal seed", entry["status"])
        self.assertIn("code view remains flat PRG", entry["status"])

        wrapper = rom.npe_format_literal_lazy_wrapper_words()
        self.assertEqual(wrapper, [
            0x58F0, 0x58F1,
            0x68F0, 0x0026, 0x58F0,
            0x68F1, 0x4956, 0x68F0, 0x004F, 0x58F1, 0x58F0,
            0x68F1, 0x4956, 0x68F0, 0x0032, 0x58F1, 0x58F0,
            0xBD08, 0x43A6, 0x50FA, 0x381F, 0x380F,
            0xAD2C, 0xC07E,
        ])
        self.assertEqual(
            hashlib.sha256(b"".join(
                word.to_bytes(2, "little") for word in wrapper
            )).hexdigest(),
            "874fb2a0dcc44ec38677a332a9f6b6711018200e559a8d6a4cdf770bf52ae0fc",
        )
        self.assertEqual(
            rom.make_routines()[rom.NPE_FORMAT_LITERAL_LAZY_WRAPPER_ADDRESS][1],
            wrapper,
        )
        self.assertLessEqual(
            (rom.NPE_BROWSER_CASEFOLD_LAZY_WRAPPER_ADDRESS +
             len(rom.npe_browser_casefold_lazy_wrapper_words()) * 2),
            rom.NPE_FORMAT_LITERAL_LAZY_WRAPPER_ADDRESS,
        )
        self.assertLessEqual(
            rom.NPE_FORMAT_LITERAL_LAZY_WRAPPER_ADDRESS + len(wrapper) * 2,
            rom.MENU_DECIMAL_PARSE_ENGINE_INSTALLER_ADDRESS,
        )

    def test_npe_runtime_state_table_is_lifecycle_bound_guest_data(self) -> None:
        image = rom.build_image()
        info = rom.manifest(image)
        expected = [0x08AC, 0x08AC, 0x08BE, 0x08E8, 0x08C4, 0x08EE]

        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_NPE_RUNTIME_STATE_TABLE_SOURCE,
                rom.APPLICATION_NPE_RUNTIME_STATE_TABLE_SIZE,
            ),
            expected,
        )
        wrapper = rom.npe_runtime_state_table_wrapper_words()
        self.assertEqual(
            wrapper,
            [
                0x58F0, 0x1F10,
                *rom.embed_program_data_words(
                    rom.APPLICATION_NPE_OPERATION7_MENU_DATA_DESTINATION,
                    rom.APPLICATION_NPE_OPERATION7_MENU_DATA_SOURCE,
                    rom.APPLICATION_NPE_OPERATION7_MENU_DATA_SIZE,
                ),
                *rom.embed_program_overlay_words(
                    rom.APPLICATION_NPE_LOADER_SLOT_WRITE_LINKED_DESTINATION,
                    rom.APPLICATION_NPE_LOADER_SLOT_WRITE_OVERLAY_SOURCE,
                    rom.APPLICATION_NPE_LOADER_SLOT_WRITE_OVERLAY_SIZE,
                ),
                0x68F0, rom.APPLICATION_NPE_RUNTIME_HELPER_OVERLAY_SIZE,
                0x58F0,
                0x68F1,
                rom.APPLICATION_NPE_RUNTIME_HELPER_OVERLAY_SOURCE & 0xFFFF,
                0x68F0,
                rom.APPLICATION_NPE_RUNTIME_HELPER_OVERLAY_SOURCE >> 16,
                0x58F1, 0x58F0,
                0x68F1,
                rom.APPLICATION_NPE_RUNTIME_HELPER_OVERLAY_DESTINATION & 0xFFFF,
                0x68F0,
                rom.APPLICATION_NPE_RUNTIME_HELPER_OVERLAY_DESTINATION >> 16,
                0x58F1, 0x58F0,
                0xBD00 | (rom.FAR_MEMCPY_08_ADDRESS >> 16),
                rom.FAR_MEMCPY_08_ADDRESS & 0xFFFF,
                0x50FA,
                0x68F0,
                rom.APPLICATION_OPERATION_TABLE_REFRESH_OVERLAY_SIZE,
                0x58F0,
                0x68F1,
                rom.APPLICATION_OPERATION_TABLE_REFRESH_OVERLAY_SOURCE & 0xFFFF,
                0x68F0,
                rom.APPLICATION_OPERATION_TABLE_REFRESH_OVERLAY_SOURCE >> 16,
                0x58F1, 0x58F0,
                0x68F1,
                rom.APPLICATION_OPERATION_TABLE_REFRESH_OVERLAY_DESTINATION & 0xFFFF,
                0x68F0,
                rom.APPLICATION_OPERATION_TABLE_REFRESH_OVERLAY_DESTINATION >> 16,
                0x58F1, 0x58F0,
                0xBD00 | (rom.FAR_MEMCPY_08_ADDRESS >> 16),
                rom.FAR_MEMCPY_08_ADDRESS & 0xFFFF,
                0x50FA,
                0x68F0,
                rom.APPLICATION_OPERATION_NEW_JOURNEY_FRAME_INIT_OVERLAY_SIZE,
                0x58F0,
                0x68F1,
                (rom.APPLICATION_OPERATION_NEW_JOURNEY_FRAME_INIT_OVERLAY_SOURCE &
                 0xFFFF),
                0x68F0,
                (rom.APPLICATION_OPERATION_NEW_JOURNEY_FRAME_INIT_OVERLAY_SOURCE >>
                 16),
                0x58F1, 0x58F0,
                0x68F1,
                (rom.APPLICATION_OPERATION_NEW_JOURNEY_FRAME_INIT_OVERLAY_DESTINATION &
                 0xFFFF),
                0x68F0,
                (rom.APPLICATION_OPERATION_NEW_JOURNEY_FRAME_INIT_OVERLAY_DESTINATION >>
                 16),
                0x58F1, 0x58F0,
                0xBD00 | (rom.FAR_MEMCPY_08_ADDRESS >> 16),
                rom.FAR_MEMCPY_08_ADDRESS & 0xFFFF,
                0x50FA,
                0x68F0, rom.APPLICATION_NPE_OBJECT_UPDATE_OVERLAY_SIZE,
                0x58F0,
                0x68F1,
                rom.APPLICATION_NPE_OBJECT_UPDATE_OVERLAY_SOURCE & 0xFFFF,
                0x68F0,
                rom.APPLICATION_NPE_OBJECT_UPDATE_OVERLAY_SOURCE >> 16,
                0x58F1, 0x58F0,
                0x68F1,
                rom.APPLICATION_NPE_OBJECT_UPDATE_OVERLAY_DESTINATION & 0xFFFF,
                0x68F0,
                rom.APPLICATION_NPE_OBJECT_UPDATE_OVERLAY_DESTINATION >> 16,
                0x58F1, 0x58F0,
                0xBD00 | (rom.FAR_MEMCPY_08_ADDRESS >> 16),
                rom.FAR_MEMCPY_08_ADDRESS & 0xFFFF,
                0x50FA,
                *rom.embed_program_overlay_words(
                    rom.APPLICATION_NPE_TRANSFORM_HELPER_OVERLAY_DESTINATION,
                    rom.APPLICATION_NPE_TRANSFORM_HELPER_OVERLAY_SOURCE,
                    rom.APPLICATION_NPE_TRANSFORM_HELPER_OVERLAY_SIZE,
                ),
                *rom.application_operation_grid_reposition_installer_words(),
                0xBD00 | (
                    rom.APPLICATION_OPERATION_NEW_JOURNEY_INSTALLER_ADDRESS >> 16
                ),
                rom.APPLICATION_OPERATION_NEW_JOURNEY_INSTALLER_ADDRESS & 0xFFFF,
                *rom.embed_program_data_words(
                    rom.APPLICATION_NPE_RUNTIME_STATE_TABLE_DESTINATION,
                    rom.APPLICATION_NPE_RUNTIME_STATE_TABLE_SOURCE,
                    rom.APPLICATION_NPE_RUNTIME_STATE_TABLE_SIZE,
                ),
                0x1F90, 0x380F,
                0xAD2B,
                rom.APPLICATION_NPE_OPERATION7_OVERLAY_DESTINATION & 0xFFFF,
            ],
        )
        self.assertEqual(
            rom.make_routines()[rom.NPE_RUNTIME_STATE_TABLE_WRAPPER_ADDRESS][1],
            wrapper,
        )
        controller = rom.resident_operation_ui_controller_words()
        for destination, source in rom.APPLICATION_NPE_OPERATION7_CALLS:
            self.assertEqual(
                rom.program_source_words(source, 4),
                [
                    0xBD2B,
                    rom.APPLICATION_NPE_OPERATION7_OVERLAY_DESTINATION & 0xFFFF,
                ],
            )
            index = (
                destination - rom.RESIDENT_OPERATION_UI_CONTROLLER_ADDRESS
            ) // 2
            self.assertEqual(
                controller[index:index + 2],
                [
                    0xBD00 | (
                        rom.NPE_RUNTIME_STATE_TABLE_WRAPPER_ADDRESS >> 16
                    ),
                    rom.NPE_RUNTIME_STATE_TABLE_WRAPPER_ADDRESS & 0xFFFF,
                ],
            )
        image = rom.build_image()
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_OPERATION_UI_CONTROLLER_ADDRESS,
                len(controller),
            ),
            controller,
        )
        self.assertLessEqual(
            (rom.NPE_FORMAT_LITERAL_LAZY_WRAPPER_ADDRESS +
             len(rom.npe_format_literal_lazy_wrapper_words()) * 2),
            rom.NPE_RUNTIME_STATE_TABLE_WRAPPER_ADDRESS,
        )
        self.assertLessEqual(
            rom.NPE_RUNTIME_STATE_TABLE_WRAPPER_ADDRESS + len(wrapper) * 2,
            rom.MENU_DECIMAL_PARSE_ENGINE_INSTALLER_ADDRESS,
        )
        table = info["application_npe_runtime_state_table_0e_08a0"]
        self.assertEqual(table["destination"], "0E:08A0")
        self.assertEqual(table["source"], "2B:08A0")
        self.assertEqual(table["bytes"], 0x0C)
        self.assertEqual(table["wrapper"], "06:6B80")
        self.assertEqual(table["call_patches"], ["1D:8A5C", "1D:9140"])
        self.assertEqual(
            table["targets"],
            [
                "2B:08AC", "2B:08AC", "2B:08BE",
                "2B:08E8", "2B:08C4", "2B:08EE",
            ],
        )
        self.assertEqual(
            table["status"],
            "exact inline RET-dispatch table; lifecycle-bound guest RAM "
            "publication before operation 7",
        )
        menu = info["application_npe_operation7_menu_data_2f_aa00"]
        self.assertEqual(menu["destination"], "2F:AA00")
        self.assertEqual(menu["source"], "4C:AA00")
        self.assertEqual(menu["bytes"], 0x54)
        self.assertEqual(menu["consumer"], "2B:0DA2")
        self.assertEqual(menu["wrapper"], "06:6B80")
        self.assertEqual(
            menu["strings"],
            [
                "退出游戏", "再续前缘", "新的征程",
                "RPG系列之－", "非法存档，读入失败!",
            ],
        )
        runtime_overlay = info[
            "application_npe_slot_write_runtime_overlay_32_f38a"
        ]
        self.assertEqual(runtime_overlay["destination"], "32:F38A")
        self.assertEqual(runtime_overlay["source"], "4F:F38A")
        self.assertEqual(runtime_overlay["bytes"], 0x003C)
        self.assertEqual(runtime_overlay["wrapper"], "06:6B80")
        helper_source = rom.program_source_words(
            rom.APPLICATION_NPE_RUNTIME_HELPER_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_RUNTIME_HELPER_OVERLAY_SIZE,
        )
        self.assertEqual(helper_source[:3], [0x2E06, 0x58F2, 0x58F3])
        self.assertEqual(helper_source[-2:], [0x2F00, rom.RETS])
        runtime_helper = info["application_npe_runtime_helper_26_3e5e"]
        self.assertEqual(runtime_helper["destination"], "26:3E5E")
        self.assertEqual(runtime_helper["source"], "43:3E5E")
        self.assertEqual(runtime_helper["bytes"], 0x03A0)
        self.assertEqual(runtime_helper["reachable_instructions"], 352)
        self.assertEqual(runtime_helper["wrapper"], "06:6B80")
        table_refresh_source = rom.program_source_words(
            rom.APPLICATION_OPERATION_TABLE_REFRESH_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_TABLE_REFRESH_OVERLAY_SIZE,
        )
        self.assertEqual(
            table_refresh_source[:5],
            [0x2E04, 0x58F0, 0x58F1, 0x58F2, 0x58F3],
        )
        self.assertEqual(
            table_refresh_source[-5:],
            [0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        table_refresh = info["application_operation_table_refresh_2f_e15a"]
        self.assertEqual(table_refresh["destination"], "2F:E15A")
        self.assertEqual(table_refresh["source"], "4C:E15A")
        self.assertEqual(table_refresh["bytes"], 0x0126)
        self.assertEqual(table_refresh["reachable_instructions"], 105)
        self.assertEqual(table_refresh["call_instructions"], 0)
        self.assertEqual(
            table_refresh["source_callers"],
            [
                "37:1502", "37:D07C", "3A:9100", "3B:18BA",
                "42:3452", "46:D2D8", "48:23E4",
            ],
        )
        self.assertEqual(table_refresh["wrapper"], "06:6B80")
        frame_init_source = rom.program_source_words(
            rom.APPLICATION_OPERATION_NEW_JOURNEY_FRAME_INIT_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_NEW_JOURNEY_FRAME_INIT_OVERLAY_SIZE,
        )
        self.assertEqual(
            frame_init_source[:5],
            [0x2E01, 0x58F0, 0x58F1, 0x58F2, 0x58F3],
        )
        self.assertEqual(
            frame_init_source[-5:],
            [0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        frame_init = info[
            "application_operation_new_journey_init_2f_6ab8"
        ]
        self.assertEqual(frame_init["destination"], "2F:6AB8")
        self.assertEqual(frame_init["source"], "4C:6AB8")
        self.assertEqual(frame_init["bytes"], 0x0142)
        self.assertEqual(frame_init["reachable_instructions"], 123)
        self.assertEqual(frame_init["call_instructions"], 9)
        self.assertEqual(
            frame_init["external_call_targets"],
            [
                "29:5C22", "29:BBF2", "33:07B0", "2E:2546",
                "2E:B2C4", "03:4214", "03:422C",
            ],
        )
        self.assertEqual(
            frame_init["source_callers"],
            [
                "37:1366", "37:1506", "3A:9104", "3C:8B9E",
                "46:D2F4", "47:0298", "48:23E8", "4C:4C62",
            ],
        )
        self.assertEqual(frame_init["wrapper"], "06:6B80")
        frame_clear_source = rom.program_source_words(
            rom.APPLICATION_OPERATION_FRAME_CLEAR_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_FRAME_CLEAR_OVERLAY_SIZE,
        )
        self.assertEqual(
            frame_clear_source[:5],
            [0x2E75, 0x58F0, 0x58F1, 0x58F2, 0x58F3],
        )
        self.assertEqual(
            frame_clear_source[-5:],
            [0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        frame_clear = info["application_operation_frame_clear_29_5c22"]
        self.assertEqual(frame_clear["destination"], "29:5C22")
        self.assertEqual(frame_clear["source"], "46:5C22")
        self.assertEqual(frame_clear["bytes"], 0x02BC)
        self.assertEqual(frame_clear["reachable_instructions"], 243)
        self.assertEqual(frame_clear["call_instructions"], 8)
        self.assertEqual(frame_clear["unknown_frontiers"], 0)
        self.assertEqual(frame_clear["consumer"], "2F:6AC2")
        draw_helper_source = rom.program_source_words(
            rom.APPLICATION_OPERATION_FRAME_CLEAR_DRAW_HELPER_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_FRAME_CLEAR_DRAW_HELPER_OVERLAY_SIZE,
        )
        self.assertEqual(
            draw_helper_source[:5],
            [0x2E05, 0x58F1, 0x58F2, 0x58F3, 0x58F6],
        )
        self.assertEqual(
            draw_helper_source[-5:],
            [0x383F, 0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        draw_helper = info[
            "application_operation_frame_clear_draw_helper_30_7b8c"
        ]
        self.assertEqual(draw_helper["destination"], "30:7B8C")
        self.assertEqual(draw_helper["source"], "4D:7B8C")
        self.assertEqual(draw_helper["bytes"], 0x00FC)
        self.assertEqual(draw_helper["reachable_instructions"], 84)
        self.assertEqual(draw_helper["call_instructions"], 3)
        self.assertEqual(
            draw_helper["external_call_targets"],
            ["03:42C0", "03:42C4", "03:42C8"],
        )
        self.assertEqual(draw_helper["unknown_frontiers"], 0)
        self.assertEqual(draw_helper["consumer"], "29:5E58")
        transition_service = info[
            "application_operation_transition_service_32_5f86"
        ]
        self.assertEqual(transition_service["destination"], "32:5F86")
        self.assertEqual(transition_service["source"], "4F:5F86")
        self.assertEqual(transition_service["bytes"], 0x006E)
        self.assertEqual(transition_service["reachable_instructions"], 37)
        self.assertEqual(transition_service["call_instructions"], 1)
        self.assertEqual(
            transition_service["external_call_targets"], ["32:B974"]
        )
        self.assertEqual(transition_service["unknown_frontiers"], 0)
        self.assertEqual(transition_service["consumer"], "03:438C via 31:A480")
        transition_child = info[
            "application_operation_transition_service_child_32_b974"
        ]
        self.assertEqual(transition_child["destination"], "32:B974")
        self.assertEqual(transition_child["source"], "4F:B974")
        self.assertEqual(transition_child["bytes"], 0x0052)
        self.assertEqual(transition_child["reachable_instructions"], 29)
        self.assertEqual(transition_child["call_instructions"], 1)
        self.assertEqual(transition_child["external_call_targets"], ["25:0000"])
        self.assertEqual(transition_child["unknown_frontiers"], 0)
        self.assertEqual(transition_child["consumer"], "32:5FE6")
        transition_leaf = info[
            "application_operation_transition_service_leaf_25_0000"
        ]
        self.assertEqual(transition_leaf["destination"], "25:0000")
        self.assertEqual(transition_leaf["source"], "42:0000")
        self.assertEqual(transition_leaf["bytes"], 0x0412)
        self.assertEqual(transition_leaf["reachable_instructions"], 331)
        self.assertEqual(transition_leaf["call_instructions"], 15)
        self.assertEqual(transition_leaf["unknown_frontiers"], 0)
        self.assertEqual(transition_leaf["consumer"], "32:B9B8")
        object_update_source = rom.program_source_words(
            rom.APPLICATION_NPE_OBJECT_UPDATE_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_OBJECT_UPDATE_OVERLAY_SIZE,
        )
        self.assertEqual(object_update_source[:3], [0x2E02, 0x58F1, 0x4801])
        self.assertEqual(object_update_source[-2:], [0x2F00, rom.RETS])
        object_update = info["application_npe_object_update_2d_c276"]
        self.assertEqual(object_update["destination"], "2D:C276")
        self.assertEqual(object_update["source"], "4A:C276")
        self.assertEqual(object_update["bytes"], 0x01A4)
        self.assertEqual(object_update["reachable_instructions"], 147)
        self.assertEqual(object_update["call_instructions"], 7)
        self.assertEqual(
            object_update["external_call_targets"],
            ["30:C8C0", "32:136C", "33:03B2"],
        )
        self.assertEqual(object_update["wrapper"], "06:6B80")
        transform_source = rom.program_source_words(
            rom.APPLICATION_NPE_TRANSFORM_HELPER_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_TRANSFORM_HELPER_OVERLAY_SIZE,
        )
        self.assertEqual(transform_source[:3], [0x2E00, 0x58F1, 0x780B])
        self.assertEqual(transform_source[-2:], [0x2F00, rom.RETS])
        transform = info["application_npe_transform_helper_33_03b2"]
        self.assertEqual(transform["destination"], "33:03B2")
        self.assertEqual(transform["source"], "50:03B2")
        self.assertEqual(transform["bytes"], 0x0036)
        self.assertEqual(transform["reachable_instructions"], 21)
        self.assertEqual(transform["call_instructions"], 1)
        self.assertEqual(transform["external_call_targets"], ["1C:CCD4"])
        self.assertEqual(transform["wrapper"], "06:6B80")
        self.assertEqual(
            transform["status"],
            "exact lifecycle-bound code overlay published by guest MOV "
            "writes before operation 7; source segment 50 is outside "
            "the data-visible program-NOR window",
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_NPE_OPERATION7_MENU_DATA_SOURCE,
                rom.APPLICATION_NPE_OPERATION7_MENU_DATA_SIZE,
            )[-1],
            0x0000,
        )
        self.assertEqual(
            rom.program_source_words(
                rom.APPLICATION_NPE_OPERATION7_MENU_DATA_SOURCE +
                rom.APPLICATION_NPE_OPERATION7_MENU_DATA_SIZE,
                2,
            ),
            [0x2E02],
        )

    def test_resident_operation_1b_7a20_closes_colliding_calls(self) -> None:
        image = rom.build_image()
        routines = rom.make_routines()
        info = rom.manifest(image)
        source = rom.program_source_words(
            rom.RESIDENT_OPERATION_1B7A20_SOURCE,
            rom.RESIDENT_OPERATION_1B7A20_SIZE,
        )
        restored = rom.resident_operation_1b7a20_words()

        self.assertEqual(len(source) * 2, 0x0876)
        self.assertEqual(source[0], 0x2E21)
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        self.assertEqual(
            rom.program_source_words(
                rom.RESIDENT_OPERATION_1B7A20_SOURCE +
                rom.RESIDENT_OPERATION_1B7A20_SIZE,
                2,
            ),
            [0x2E03],
        )
        for call_address, old_target, new_target in (
            (rom.RESIDENT_OPERATION_1B7A20_RECORD_ACCESSOR_CALL_SOURCE,
             rom.APPLICATION_OPERATION_RECORD_ACCESSOR_LINKED_DESTINATION,
             rom.APPLICATION_OPERATION_RECORD_ACCESSOR_OVERLAY_DESTINATION),
            (rom.RESIDENT_OPERATION_1B7A20_LITERAL_INSTALL_CALL_SOURCE,
             rom.FAR_MEMORY_COMPARE_OVERLAY_DESTINATION,
             rom.NPE_FORMAT_LITERAL_LAZY_WRAPPER_ADDRESS),
            (rom.RESIDENT_OPERATION_1B7A20_FRAME_DRAW_CALL_SOURCE,
             rom.APPLICATION_OPERATION_FRAME_DRAW_LINKED_DESTINATION,
             rom.APPLICATION_OPERATION_FRAME_DRAW_OVERLAY_DESTINATION),
            (rom.RESIDENT_OPERATION_1B7A20_MODE_PAIR_CALL_SOURCE,
             rom.APPLICATION_RESULT_MODE_PAIR_LINKED_DESTINATION,
             rom.APPLICATION_RESULT_MODE_PAIR_OVERLAY_DESTINATION),
        ):
            index = (
                call_address - rom.RESIDENT_OPERATION_1B7A20_SOURCE
            ) // 2
            self.assertEqual(
                source[index:index + 2],
                [0xBD00 | (old_target >> 16), old_target & 0xFFFF],
            )
            self.assertEqual(
                restored[index:index + 2],
                [0xBD00 | (new_target >> 16), new_target & 0xFFFF],
            )
        self.assertEqual(
            [index for index, (before, after) in enumerate(
                zip(source, restored)) if before != after],
            [
                (rom.RESIDENT_OPERATION_1B7A20_RECORD_ACCESSOR_CALL_SOURCE -
                 rom.RESIDENT_OPERATION_1B7A20_SOURCE) // 2,
                (rom.RESIDENT_OPERATION_1B7A20_LITERAL_INSTALL_CALL_SOURCE -
                 rom.RESIDENT_OPERATION_1B7A20_SOURCE) // 2,
                (rom.RESIDENT_OPERATION_1B7A20_LITERAL_INSTALL_CALL_SOURCE -
                 rom.RESIDENT_OPERATION_1B7A20_SOURCE) // 2 + 1,
                (rom.RESIDENT_OPERATION_1B7A20_FRAME_DRAW_CALL_SOURCE -
                 rom.RESIDENT_OPERATION_1B7A20_SOURCE) // 2,
                (rom.RESIDENT_OPERATION_1B7A20_MODE_PAIR_CALL_SOURCE -
                 rom.RESIDENT_OPERATION_1B7A20_SOURCE) // 2,
            ],
        )
        self.assertEqual(
            routines[rom.RESIDENT_OPERATION_1B7A20_ADDRESS][1], restored
        )
        self.assertEqual(
            words_at(
                image,
                rom.RESIDENT_OPERATION_1B7A20_ADDRESS,
                len(restored),
            ),
            restored,
        )
        self.assertEqual(
            hashlib.sha256(b"".join(
                word.to_bytes(2, "little") for word in restored
            )).hexdigest(),
            "46b915d947a64c121b05c172b2474c123f0a63cf94f7f70f69549033e1e61041",
        )

        accessor = rom.program_source_words(
            rom.APPLICATION_OPERATION_RECORD_ACCESSOR_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_RECORD_ACCESSOR_OVERLAY_SIZE,
        )
        self.assertEqual(accessor[0], 0x2E00)
        self.assertEqual(accessor[-2:], [0x2F00, rom.RETS])
        self.assertFalse(any(
            word & 0xFF00 == 0xBD00 for word in accessor
        ))

        frame_draw = rom.program_source_words(
            rom.APPLICATION_OPERATION_FRAME_DRAW_OVERLAY_SOURCE,
            rom.APPLICATION_OPERATION_FRAME_DRAW_OVERLAY_SIZE,
        )
        self.assertEqual(frame_draw[0], 0x2E00)
        self.assertEqual(frame_draw[-2:], [0x2F00, rom.RETS])
        self.assertEqual(sum(
            frame_draw[index:index + 2] == [0xAC01, 0x6B94]
            for index in range(len(frame_draw) - 1)
        ), 2)
        installer = rom.application_operation_action_mode_predicate_installer_words()
        for destination, source_address, size in (
            (rom.APPLICATION_OPERATION_RECORD_ACCESSOR_OVERLAY_DESTINATION,
             rom.APPLICATION_OPERATION_RECORD_ACCESSOR_OVERLAY_SOURCE,
             rom.APPLICATION_OPERATION_RECORD_ACCESSOR_OVERLAY_SIZE),
            (rom.APPLICATION_OPERATION_FRAME_DRAW_OVERLAY_DESTINATION,
             rom.APPLICATION_OPERATION_FRAME_DRAW_OVERLAY_SOURCE,
             rom.APPLICATION_OPERATION_FRAME_DRAW_OVERLAY_SIZE),
        ):
            embedded = rom.embed_program_overlay_words(
                destination, source_address, size
            )
            self.assertIn(
                embedded,
                [installer[index:index + len(embedded)]
                 for index in range(len(installer) - len(embedded) + 1)],
            )
        self.assertEqual(len(installer) * 2, 0x09DE)
        self.assertLessEqual(
            rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_INSTALLER_ADDRESS +
            len(installer) * 2,
            0x018000,
        )

        metadata = info["resident_operation_1b_7a20"]
        self.assertEqual(metadata["destination"], "1B:7A20")
        self.assertEqual(metadata["source"], "38:7A20")
        self.assertEqual(metadata["bytes"], 0x0876)
        self.assertEqual(metadata["reachable_instructions"], 721)
        self.assertEqual(metadata["call_instructions"], 43)
        self.assertEqual(metadata["retargeted_calls"], {
            "38:7AA2": "5F:380A",
            "38:7E8A": "5F:6A9C",
            "38:7EA2": "5F:1BBA",
        })
        modules = {
            item["destination"]: item
            for item in info["application_main_chain"]
        }
        self.assertEqual(
            modules["5F:380A"]["source"],
            "50:380A",
        )
        self.assertEqual(
            modules["5F:380A"]["bytes"],
            0x0022,
        )
        self.assertEqual(
            modules["5F:6A9C"]["source"],
            "4D:6A9C",
        )
        self.assertEqual(
            modules["5F:6A9C"]["bytes"],
            0x0102,
        )

    def test_npe_loader_slot_write_collision_is_relocated_exactly(self) -> None:
        source = rom.program_source_words(
            rom.APPLICATION_NPE_LOADER_SLOT_WRITE_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_LOADER_SLOT_WRITE_OVERLAY_SIZE,
        )
        installer = (
            rom.application_operation_action_mode_predicate_installer_words()
        )
        embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_NPE_LOADER_SLOT_WRITE_OVERLAY_DESTINATION,
            rom.APPLICATION_NPE_LOADER_SLOT_WRITE_OVERLAY_SOURCE,
            rom.APPLICATION_NPE_LOADER_SLOT_WRITE_OVERLAY_SIZE,
        )
        modules = {
            item["destination"]: item
            for item in rom.manifest(rom.build_image())["application_main_chain"]
        }

        self.assertEqual(len(source) * 2, 0x003C)
        self.assertEqual(source[:5], [0x2E00, 0x58F0, 0x58F1, 0x58F2, 0x58F3])
        self.assertEqual(source[-6:], [
            0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS,
        ])
        self.assertFalse(any(
            word & 0xFF00 in (0xAD00, 0xBD00) for word in source
        ))
        self.assertIn(
            embedded,
            [installer[index:index + len(embedded)]
             for index in range(len(installer) - len(embedded) + 1)],
        )
        table_index = (
            rom.RESIDENT_ROM03_NPE_LOADER_SLOT_WRITE_TRAMPOLINE_ADDRESS -
            rom.ROM03_JUMP_TABLE_ADDRESS
        ) // 2
        self.assertEqual(
            rom.resident_rom03_jump_table_words()[
                table_index:table_index + 2
            ],
            [0xAD5F, 0xF38A],
        )
        self.assertEqual(modules["5F:F38A"]["source"], "4F:F38A")
        self.assertEqual(modules["5F:F38A"]["bytes"], 0x003C)

        registry_index = (
            rom.RESIDENT_ROM03_NPE_LOADER_REGISTRY_ENTRY_TRAMPOLINE_ADDRESS -
            rom.ROM03_JUMP_TABLE_ADDRESS
        ) // 2
        self.assertEqual(
            rom.resident_rom03_jump_table_words()[
                registry_index:registry_index + 2
            ],
            [0xAD5F, 0xC1A6],
        )
        registry_source = rom.program_source_words(
            rom.APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_SOURCE,
            rom.APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_SIZE,
        )
        self.assertEqual(registry_source[0], 0x2E01)
        self.assertEqual(registry_source[-2:], [0x2F00, rom.RETS])
        registry_embed = rom.embed_program_overlay_words(
            rom.APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_DESTINATION,
            rom.APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_SOURCE,
            rom.APPLICATION_SYSTEM_REGISTRY_ENTRY_OVERLAY_SIZE,
        )
        region_installer = rom.application_region_extra_installer_words()
        self.assertIn(
            registry_embed,
            [region_installer[index:index + len(registry_embed)]
             for index in range(
                 len(region_installer) - len(registry_embed) + 1
             )],
        )

    def test_resident_async_resume_02_0fb6_is_exact_guest_code(self) -> None:
        image = rom.build_image()
        info = rom.manifest(image)
        source = rom.program_source_words(
            rom.RESIDENT_ASYNC_RESUME_02_0FB6_SOURCE,
            rom.RESIDENT_ASYNC_RESUME_02_0FB6_SIZE,
        )
        installed = words_at(
            image,
            rom.RESIDENT_ASYNC_RESUME_02_0FB6_ADDRESS,
            len(source),
        )

        self.assertEqual(installed, source)
        self.assertEqual(source[0], 0x4800)
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        self.assertEqual(
            info["resident_async_resume_02_0fb6"]["bytes"],
            rom.RESIDENT_ASYNC_RESUME_02_0FB6_SIZE,
        )
        self.assertEqual(
            info["resident_async_resume_02_0fb6"]["unknown_frontiers"],
            0,
        )

    def test_resident_file_browser_layout_1c_d462_is_exact_guest_code(
        self,
    ) -> None:
        image = rom.build_image()
        info = rom.manifest(image)
        source = rom.program_source_words(
            rom.RESIDENT_FILE_BROWSER_LAYOUT_SOURCE,
            rom.RESIDENT_FILE_BROWSER_LAYOUT_SIZE,
        )
        installed = words_at(
            image,
            rom.RESIDENT_FILE_BROWSER_LAYOUT_ADDRESS,
            len(source),
        )

        self.assertEqual(installed, source)
        self.assertEqual(source[0], 0x2E07)
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        metadata = info["resident_file_browser_layout_1c_d462"]
        self.assertEqual(metadata["bytes"], rom.RESIDENT_FILE_BROWSER_LAYOUT_SIZE)
        self.assertEqual(metadata["reachable_instructions"], 787)
        self.assertEqual(metadata["call_instructions"], 14)
        self.assertEqual(metadata["unknown_frontiers"], 0)

    def test_resident_file_browser_range_worker_1d_7c00_is_exact_guest_code(
        self,
    ) -> None:
        image = rom.build_image()
        info = rom.manifest(image)
        source = rom.program_source_words(
            rom.RESIDENT_FILE_BROWSER_RANGE_WORKER_SOURCE,
            rom.RESIDENT_FILE_BROWSER_RANGE_WORKER_SIZE,
        )
        installed = words_at(
            image,
            rom.RESIDENT_FILE_BROWSER_RANGE_WORKER_ADDRESS,
            len(source),
        )

        self.assertEqual(installed, source)
        self.assertEqual(
            source[:8],
            [0x2E0D, 0x58F1, 0x58F2, 0x58F3,
             0x58F4, 0x58F5, 0x58F6, 0x58F7],
        )
        self.assertEqual(
            source[-9:],
            [0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
             0x382F, 0x381F, 0x2F00, rom.RETS],
        )
        metadata = info["resident_file_browser_range_worker_1d_7c00"]
        self.assertEqual(
            metadata["bytes"], rom.RESIDENT_FILE_BROWSER_RANGE_WORKER_SIZE
        )
        self.assertEqual(metadata["reachable_instructions"], 655)
        self.assertEqual(metadata["call_instructions"], 7)
        self.assertEqual(metadata["unknown_frontiers"], 0)

    def test_resident_file_browser_entry_builder_18_8f9e_is_exact_guest_code(
        self,
    ) -> None:
        image = rom.build_image()
        info = rom.manifest(image)
        source = rom.program_source_words(
            rom.RESIDENT_FILE_BROWSER_ENTRY_BUILDER_SOURCE,
            rom.RESIDENT_FILE_BROWSER_ENTRY_BUILDER_SIZE,
        )
        installed = words_at(
            image,
            rom.RESIDENT_FILE_BROWSER_ENTRY_BUILDER_ADDRESS,
            len(source),
        )

        self.assertEqual(installed, source)
        self.assertEqual(source[0], 0x2E0E)
        self.assertEqual(source[-2:], [0x2F00, rom.RETS])
        metadata = info["resident_file_browser_entry_builder_18_8f9e"]
        self.assertEqual(metadata["bytes"], rom.RESIDENT_FILE_BROWSER_ENTRY_BUILDER_SIZE)
        self.assertEqual(metadata["linear_instructions"], 935)
        self.assertEqual(metadata["call_instructions"], 15)

    def test_resident_modal_resource_apply_18_ef1a_is_exact_guest_code(
        self,
    ) -> None:
        image = rom.build_image()
        info = rom.manifest(image)
        source = rom.program_source_words(
            rom.RESIDENT_MODAL_RESOURCE_APPLY_18_SOURCE,
            rom.RESIDENT_MODAL_RESOURCE_APPLY_18_SIZE,
        )
        installed = words_at(
            image,
            rom.RESIDENT_MODAL_RESOURCE_APPLY_18_ADDRESS,
            len(source),
        )

        self.assertEqual(installed, source)
        self.assertEqual(
            source[:7],
            [0x2E03, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4, 0x58F5],
        )
        self.assertEqual(
            source[-8:],
            [0x385F, 0x384F, 0x383F, 0x382F,
             0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            rom.RESIDENT_MODAL_RESOURCE_APPLY_18_ADDRESS +
            rom.RESIDENT_MODAL_RESOURCE_APPLY_18_SIZE,
            rom.RESIDENT_STORAGE_UNIT_INIT_OVERLAY_DESTINATION,
        )
        metadata = info["resident_modal_resource_apply_18_ef1a"]
        self.assertEqual(
            metadata["bytes"], rom.RESIDENT_MODAL_RESOURCE_APPLY_18_SIZE
        )

    def test_resident_start_record_apply_16_c8a2_is_exact_guest_code(
        self,
    ) -> None:
        image = rom.build_image()
        info = rom.manifest(image)
        source = rom.program_source_words(
            rom.RESIDENT_START_RECORD_APPLY_SOURCE,
            rom.RESIDENT_START_RECORD_APPLY_SIZE,
        )
        installed = words_at(
            image,
            rom.RESIDENT_START_RECORD_APPLY_ADDRESS,
            len(source),
        )

        self.assertEqual(installed, source)
        self.assertEqual(source[:5], [
            0x2E08, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
        ])
        self.assertEqual(
            source[-10:],
            [0x387F, 0x386F, 0x385F, 0x384F, 0x383F,
             0x382F, 0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        metadata = info["resident_start_record_apply_16_c8a2"]
        self.assertEqual(metadata["bytes"], rom.RESIDENT_START_RECORD_APPLY_SIZE)
        self.assertEqual(metadata["reachable_instructions"], 1284)
        self.assertEqual(metadata["call_instructions"], 33)
        self.assertEqual(metadata["unknown_frontiers"], 0)

    def test_rom_08_body_is_exact_and_legacy_probe_only_changes_flow(self) -> None:
        strict = rom.build_image(initializer_overlay_probe=True)
        probe = rom.build_image(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
        )
        info = rom.manifest(
            probe,
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
        )

        exact_427e = [0xFD38, 0xED40, 0xFD48, 0x3F00, rom.RETS]
        self.assertEqual(words_at(strict, 0x08427E, 5), exact_427e)
        self.assertEqual(words_at(probe, 0x08427E, 5), exact_427e)
        self.assertEqual(info["probe_placeholders"], [])
        probe_loader = rom.post_initializer_overlay_words(True)
        self.assertEqual(probe_loader[-3:], [0xBD20, 0x026A, rom.RESERVED])
        trap = (rom.POST_INITIALIZER_LOADER_ADDRESS +
                (len(probe_loader) - 1) * 2)
        self.assertEqual(words_at(probe, trap, 1), [rom.RESERVED])

        with self.assertRaisesRegex(ValueError, "requires initializer-overlay"):
            rom.build_image(probe_rom_08_return=True)

    def test_rom_03_table_is_source_exact_with_proven_npe_retarget(self) -> None:
        probe = rom.build_image(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_rom_03_rand_zero=True,
        )
        info = rom.manifest(
            probe,
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_rom_03_rand_zero=True,
        )

        source_table = rom.program_source_words(
            rom.ROM03_JUMP_TABLE_SOURCE, rom.ROM03_JUMP_TABLE_SIZE
        )
        table = rom.resident_rom03_jump_table_words()
        patches = (
            (rom.RESIDENT_ROM03_NPE_LOADER_REGISTRY_ENTRY_TRAMPOLINE_ADDRESS,
             [0xAD32, 0xC1A6], [0xAD5F, 0xC1A6]),
            (rom.RESIDENT_ROM03_NPE_DIRECTION_EVENT_TRAMPOLINE_ADDRESS,
             [0xAD32, 0x6062], [0xAD1A, 0x7B00]),
            (rom.RESIDENT_ROM03_NPE_LOADER_SLOT_WRITE_TRAMPOLINE_ADDRESS,
             [0xAD32, 0xF38A], [0xAD5F, 0xF38A]),
        )
        normalized = list(table)
        for address, original, relocated in patches:
            patch_index = (address - rom.ROM03_JUMP_TABLE_ADDRESS) // 2
            self.assertEqual(
                source_table[patch_index:patch_index + 2], original
            )
            self.assertEqual(table[patch_index:patch_index + 2], relocated)
            normalized[patch_index:patch_index + 2] = original
        self.assertEqual(source_table, normalized)
        self.assertEqual(
            words_at(probe, rom.ROM03_JUMP_TABLE_ADDRESS, len(table)), table
        )
        self.assertEqual(words_at(probe, 0x034124, 2), [0xAD33, 0x6566])
        self.assertEqual(info["probe_placeholders"], [])
        self.assertEqual(info["resident_rom03_jump_table"]["entries"], 484)
        self.assertIn(
            "03:4024", info["resident_rom03_jump_table"]["status"]
        )
        self.assertIn(
            "03:411C", info["resident_rom03_jump_table"]["status"]
        )
        self.assertIn(
            "03:4128", info["resident_rom03_jump_table"]["status"]
        )
        with self.assertRaisesRegex(ValueError, "requires initializer-overlay"):
            rom.build_image(probe_rom_03_rand_zero=True)

    def test_event_loop_continuation_is_explicit_and_probe_only(self) -> None:
        probe = rom.build_image(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_rom_03_rand_zero=True,
            probe_continue_event_loop=True,
        )
        info = rom.manifest(
            probe,
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_rom_03_rand_zero=True,
            probe_continue_event_loop=True,
        )
        loader = rom.post_initializer_overlay_words(True, True)

        self.assertEqual(loader[-4:], [
            0xBD20, 0x026A, 0xAD03, rom.POST_INITIALIZER_HANDOFF_PC,
        ])
        self.assertEqual(
            words_at(probe, rom.POST_INITIALIZER_LOADER_ADDRESS, len(loader)),
            loader,
        )
        handoff = rom.boot_frame_handoff_words()
        self.assertEqual(
            words_at(
                probe,
                0x030000 | rom.POST_INITIALIZER_HANDOFF_PC,
                len(handoff),
            ),
            handoff,
        )
        self.assertEqual(handoff[-2:], [0xAD20, 0x0004])
        self.assertTrue(info["probe_continue_event_loop"])
        with self.assertRaisesRegex(ValueError, "event-loop continuation"):
            rom.build_image(probe_continue_event_loop=True)

    def test_lcd_power_probe_calls_recovered_guest_wrapper(self) -> None:
        loader = rom.post_initializer_overlay_words(True, True, True)
        image = rom.build_image(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_rom_03_rand_zero=True,
            probe_continue_event_loop=True,
            probe_lcd_power_on=True,
        )
        info = rom.manifest(
            image,
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_rom_03_rand_zero=True,
            probe_continue_event_loop=True,
            probe_lcd_power_on=True,
        )

        self.assertEqual(loader[-6:], [
            0xBD20, 0x026A,
            0xBD14, rom.LCD_POWER_INIT_ADDRESS & 0xFFFF,
            0xAD03, rom.POST_INITIALIZER_HANDOFF_PC,
        ])
        self.assertTrue(info["probe_lcd_power_on"])
        with self.assertRaisesRegex(ValueError, "LCD power-on"):
            rom.build_image(probe_lcd_power_on=True)

    def test_manifest_marks_clean_room_origin(self) -> None:
        image = rom.build_image()
        info = rom.manifest(image)

        self.assertIn("not original", info["warning"].lower())
        self.assertEqual(info["controller_mmio"], "0xF300")
        self.assertIn("1A:423C",
                      [entry["address"] for entry in info["entries"]])
        self.assertEqual(info["resident_dispatch_1a"]["source"], "37:423C")

    def test_initializer_probe_uses_sentinels_and_stops_at_unknown_rom(self) -> None:
        image = rom.build_image(initializer_probe=True)
        info = rom.manifest(image, initializer_probe=True)
        body = rom.initializer_probe_words()

        self.assertEqual(body[-4:], [0xBD20, 0x0030, 0xAD24, 0x7FE4])
        self.assertEqual(words_at(image, 0x030100, len(body)), body)
        self.assertEqual(words_at(image, 0x03026A, 1), [rom.RESERVED])
        for address, data in rom.INITIALIZER_PROBE_SOURCES.items():
            self.assertEqual(
                image[address:address + len(data)],
                rom.initializer_probe_storage_bytes(data),
            )
        self.assertTrue(info["initializer_probe"])
        self.assertEqual(len(info["initializer_probe_sources"]), 3)
        self.assertTrue(all(
            "not recovered" in item["warning"]
            for item in info["initializer_probe_sources"]
        ))

    def test_initializer_overlay_probe_continues_via_guest_code(self) -> None:
        image = rom.build_image(initializer_overlay_probe=True)
        info = rom.manifest(image, initializer_overlay_probe=True)

        self.assertEqual(words_at(image, 0x03026A, 2), [0xAD2E, 0x4560])
        self.assertEqual(words_at(image, 0x077FE4, 2), [
            0xAD00 | (rom.POST_INITIALIZER_LOADER_ADDRESS >> 16),
            rom.POST_INITIALIZER_LOADER_ADDRESS & 0xFFFF,
        ])
        self.assertEqual(
            words_at(image, rom.POST_INITIALIZER_LOADER_ADDRESS,
                     len(rom.post_initializer_overlay_words())),
            rom.post_initializer_overlay_words(),
        )
        self.assertTrue(info["initializer_overlay_probe"])
        self.assertFalse(info["initializer_probe"])
        self.assertEqual(info["memory_init_overlay"], {
            "destination": "06:9A7C",
            "source": "49:9A7C",
            "bytes": 0x01EA,
            "caller_patch": "20:02C0/03:02C0 -> 06:9A7C",
            "preserved_collision": "2C:9A7C Game World controller tail",
            "status": "same-low-PC resident exact vendor function",
        })
        self.assertEqual(info["text_draw_overlay"], {
            "destination": "2E:5316",
            "source": "4B:5316",
            "bytes": 0x0184,
            "status": "same-PC four-argument clean-room reconstruction",
        })
        for address, data in rom.initializer_factory_source_blocks().items():
            self.assertEqual(
                image[address:address + len(data)],
                data,
            )
        self.assertEqual(info["initializer_probe_sources"], [])
        self.assertEqual(info["initializer_factory_sources"], [
            {
                "destination": "04:FFF8",
                "source": "21:FFF8",
                "bytes": 8,
                "storage_hex": "0000000000008002",
                "status": "exact +0x1D linked PRG storage copy",
            },
            {
                "destination": "07:57C8",
                "source": "24:57C8",
                "bytes": 4,
                "storage_hex": "00000000",
                "status": "exact +0x1D linked PRG storage copy",
            },
            {
                "destination": "07:A622",
                "source": "24:A622",
                "bytes": 16,
                "storage_hex": "0000000000000000000020c620c60000",
                "status": "exact +0x1D linked PRG storage copy",
            },
        ])

    def test_factory_initializer_sources_are_bounded_linked_prg_islands(
            self) -> None:
        self.assertEqual(rom.initializer_factory_source_blocks(), {
            0x04FFF8: bytes.fromhex("0000000000008002"),
            0x0757C8: bytes.fromhex("00000000"),
            0x07A622: bytes.fromhex(
                "0000000000000000000020c620c60000"
            ),
        })
        # 21:FFF8 follows a balanced RETS and occupies the final eight bytes
        # of its segment; 24:57C8 is between RETS and the next LINK.  The
        # A622 island also preserves the two callable RETS leaves embedded in
        # the mapped 16-byte window.
        self.assertEqual(
            rom.program_source_words(0x21FFF0, 0x0008),
            [0x381F, 0x380F, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            rom.program_source_words(0x2457C0, 0x0010),
            [0x383F, 0x381F, 0x2F00, rom.RETS,
             0x0000, 0x0000, 0x2E02, 0x58F1],
        )
        self.assertEqual(
            rom.program_source_words(0x24A622, 0x0010),
            [0x0000, 0x0000, 0x0000, 0x0000,
             0x0000, rom.RETS, rom.RETS, 0x0000],
        )

    def test_factory_linked_startup_restores_exact_execution_banks(
            self) -> None:
        flow = {
            "initializer_overlay_probe": True,
            "probe_rom_08_return": True,
            "probe_rom_01_return": True,
            "probe_system_main": True,
            "factory_linked_startup": True,
        }
        image = rom.build_image(**flow)
        info = rom.manifest(image, **flow)

        entry = rom.initializer_overlay_probe_words(True)
        self.assertEqual(entry[-3:], [0xBD20, 0x0030, rom.RETS])
        self.assertEqual(words_at(image, 0x030100, len(entry)), entry)
        self.assertEqual(
            words_at(
                image,
                rom.FACTORY_COMPILER_INITIALIZER_DESTINATION,
                rom.FACTORY_COMPILER_INITIALIZER_SIZE // 2,
            ),
            rom.program_source_words(
                rom.FACTORY_COMPILER_INITIALIZER_SOURCE,
                rom.FACTORY_COMPILER_INITIALIZER_SIZE,
            ),
        )
        linked_constant = words_at(
            image,
            rom.FACTORY_CONSTANT_INITIALIZER_DESTINATION,
            rom.FACTORY_CONSTANT_INITIALIZER_SIZE // 2,
        )
        exact_constant = rom.program_source_words(
            rom.FACTORY_CONSTANT_INITIALIZER_SOURCE,
            rom.FACTORY_CONSTANT_INITIALIZER_SIZE,
        )
        self.assertEqual(linked_constant[:-2], exact_constant[:-2])
        self.assertEqual(exact_constant[-2:], [0xAD03, 0x026A])
        self.assertEqual(linked_constant[-2:], [
            0xAD00 | (rom.POST_INITIALIZER_LOADER_ADDRESS >> 16),
            rom.POST_INITIALIZER_LOADER_ADDRESS & 0xFFFF,
        ])
        self.assertEqual(
            words_at(
                image,
                rom.FACTORY_SYSTEM_MAIN_DESTINATION,
                rom.FACTORY_SYSTEM_MAIN_SIZE // 2,
            ),
            rom.factory_system_main_words(),
        )
        loader = rom.post_initializer_overlay_words(
            probe_system_main=True,
            factory_linked_startup=True,
        )
        self.assertEqual(loader[-11:], [
            0x68F0, 0x0200,
            0x6810, 0x00A2,
            0xC700,
            0xA8F0, 0x28E0,
            0xBD03, 0x026A,
            0xAD03, rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS & 0xFFFF,
        ])
        self.assertNotIn(
            [0xBD20, 0x026A],
            [loader[index:index + 2] for index in range(len(loader) - 1)],
        )
        self.assertEqual(
            words_at(image, rom.NATIVE_APPLICATION_SCHEDULER_ADDRESS, 11),
            [0x68F0, 0x0200,
             0x6810, 0x00A2,
             0xC700,
             0xA8F0, 0x28E0,
             0xBD03, 0x026A,
             0xAD03, 0x0080],
        )
        self.assertTrue(info["factory_linked_startup"])
        self.assertEqual(
            [item["destination"]
             for item in info["factory_linked_startup_modules"]],
            ["11:4560", "07:7FE4", "03:026A"],
        )

    def test_factory_linked_startup_requires_full_system_flow(self) -> None:
        with self.assertRaisesRegex(ValueError, "initializer-overlay"):
            rom.build_image(factory_linked_startup=True)
        with self.assertRaisesRegex(ValueError, "system-main"):
            rom.build_image(
                initializer_overlay_probe=True,
                factory_linked_startup=True,
            )

    def test_dual_initializer_probe_stops_before_runtime_mutates_data(self) -> None:
        image = rom.build_image(dual_initializer_probe=True)
        info = rom.manifest(image, dual_initializer_probe=True)

        self.assertEqual(words_at(image, 0x03026A, 2), [0xAD2E, 0x4560])
        self.assertEqual(words_at(image, 0x077FE4, 1), [rom.RESERVED])
        self.assertTrue(info["dual_initializer_probe"])
        self.assertFalse(info["initializer_overlay_probe"])

    def test_storage_global_template_probe_reapplies_exact_prg_data(self) -> None:
        image = rom.build_image(
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_rom_01_return=True,
            probe_storage_global_templates=True,
        )
        info = rom.manifest(
            image,
            initializer_overlay_probe=True,
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_rom_01_return=True,
            probe_storage_global_templates=True,
        )
        loader = rom.post_initializer_overlay_words(
            probe_rom_08_return=True,
            probe_system_main=True,
            probe_storage_global_templates=True,
        )
        correction = rom.storage_global_template_probe_words()

        self.assertEqual(loader[:2], [
            0xBD00 | (rom.STORAGE_GLOBAL_TEMPLATE_PROBE_ADDRESS >> 16),
            rom.STORAGE_GLOBAL_TEMPLATE_PROBE_ADDRESS & 0xFFFF,
        ])
        self.assertEqual(
            words_at(image, rom.POST_INITIALIZER_LOADER_ADDRESS, len(loader)),
            loader,
        )
        self.assertEqual(
            words_at(
                image,
                rom.STORAGE_GLOBAL_TEMPLATE_PROBE_ADDRESS,
                len(correction),
            ),
            correction,
        )
        self.assertEqual(correction[-1], rom.RETS)
        self.assertTrue(info["probe_storage_global_templates"])
        records = rom.segment33_data_template_records()
        self.assertEqual(len(rom.compiler_initializer_copy_records()), 261)
        self.assertEqual(len(records), 253)
        self.assertEqual(sum(size for _destination, _source, size in records), 1475)
        self.assertTrue(all(source >> 16 == 0x50 for _, source, _ in records))
        by_destination = {
            item["destination"]: item["data"]
            for item in info["storage_global_template_probe"]
        }
        self.assertEqual(
            {
                destination: by_destination[
                    f"{destination >> 16:02X}:{destination & 0xFFFF:04X}"
                ]
                for destination, _source, _size
                in rom.STORAGE_GLOBAL_TEMPLATE_EVIDENCE_COPIES
            },
            {
                0x5129CC: "00000000",
                0x5129B4: "00000000",
                0x5129C0: "00000000",
                0x5129C4: "00000000",
                0x5129B8: "00000000",
                0x5129B0: "500048f9",
            },
        )
        with self.assertRaisesRegex(ValueError, "storage-global template"):
            rom.build_image(probe_storage_global_templates=True)

    def test_rom02_c588_marker_has_unconditional_guest_return(self) -> None:
        image = rom.build_image()
        compatibility_image = rom.build_image(probe_rom_02_c588_return=True)
        info = rom.manifest(image)

        self.assertEqual(
            words_at(image, rom.ROM02_C588_ADDRESS, 1),
            [rom.RETS],
        )
        self.assertEqual(image, compatibility_image)
        self.assertEqual(
            info["resident_rom02_diagnostic_marker"]["address"],
            "02:C588",
        )
        self.assertIn(
            "external diagnostic-byte side effect remains unmodeled",
            info["resident_rom02_diagnostic_marker"]["status"],
        )

    def test_rom00_dynamic_module_uses_exact_prg_guest_code(self) -> None:
        image = rom.build_image()
        info = rom.manifest(image)
        source = rom.program_source_words(
            rom.ROM00_DYNAMIC_MODULE_SOURCE,
            rom.ROM00_DYNAMIC_MODULE_SIZE,
        )
        self.assertEqual(
            words_at(image, rom.ROM00_DYNAMIC_MODULE_ADDRESS, len(source)),
            source,
        )
        self.assertEqual(source[:rom.ROM00_DYNAMIC_PREFIX_SIZE // 2], [
            0x6810, 0x00A4, 0x99F0, 0x7A3E, 0x5601, 0xAC02,
            0x56FA, 0x68F0, 0x0037, 0x6A0B, 0xFFFC, 0x480B,
            0x6A0B, 0xFFFE, 0x4805, 0x58F0, 0x68F1, 0x5932,
            0x68F0, 0x0030, 0x58F1, 0x58F0,
        ])
        self.assertEqual(
            words_at(image, 0x0011EC, 2),
            [0xAC00, 0x5928],
        )
        self.assertEqual(
            words_at(image, 0x005FA6, 6),
            [0x387F, 0x386F, 0x385F, 0x384F, 0x2F00, rom.RETS],
        )
        absolute_epilogue = rom.program_source_words(
            rom.ROM00_DYNAMIC_ABSOLUTE_EPILOGUE_SOURCE,
            rom.ROM00_DYNAMIC_ABSOLUTE_EPILOGUE_SIZE,
        )
        self.assertEqual(
            words_at(
                image,
                rom.ROM00_DYNAMIC_ABSOLUTE_EPILOGUE_ADDRESS,
                len(absolute_epilogue),
            ),
            absolute_epilogue,
        )
        self.assertEqual(
            absolute_epilogue,
            [0x387F, 0x386F, 0x385F, 0x384F, 0x2F00, rom.RETS],
        )
        self.assertEqual(
            words_at(image, 0x003F1C, 2),
            [0xAC00, rom.ROM00_CRITICAL_RETURN_ADDRESS & 0xFFFF],
        )
        self.assertEqual(
            words_at(image, rom.ROM00_CRITICAL_RETURN_ADDRESS,
                     len(rom.ROM00_CRITICAL_RETURN_WORDS)),
            list(rom.ROM00_CRITICAL_RETURN_WORDS),
        )
        self.assertEqual(info["resident_rom00_dynamic_module"], {
            "destination": "00:1002",
            "source": "2F:550C",
            "bytes": 0x4FB0,
            "dynamic_prefix_bytes": 0x2C,
            "status": (
                "exact PRG-resident module; boot rewrites its prefix through "
                "internal executable RAM"
            ),
        })
        self.assertEqual(info["resident_rom00_critical_return"], {
            "address": "00:85B0",
            "words": 2,
            "status": (
                "ABI-constrained CRIT #0 plus RETS epilogue for the exact "
                "00:3F00 zero-byte callback"
            ),
        })
        self.assertEqual(
            info["resident_rom00_dynamic_absolute_epilogue"],
            {
                "destination": "00:A4B0",
                "source": "2F:A4B0",
                "bytes": 0x0C,
                "status": (
                    "exact split pop/UNLINK/RETS tail reached by the module's "
                    "absolute AJMP"
                ),
            },
        )

    def test_foreground_event_state_lazy_exchange_preserves_abi(self) -> None:
        source_call = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_EVENT_STATE_CALL_SOURCE,
            4,
        )
        decoder = rom.program_source_words(
            rom.APPLICATION_FOREGROUND_EVENT_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_EVENT_OVERLAY_SIZE,
        )
        wrapper = rom.foreground_event_state_lazy_wrapper_words()
        embedded = rom.embed_program_overlay_words(
            rom.APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_DESTINATION,
            rom.APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_EVENT_STATE_OVERLAY_SIZE,
        )
        original_copy = rom.copy_code_to_overlay_words(
            rom.APPLICATION_FOREGROUND_EVENT_OVERLAY_DESTINATION,
            rom.APPLICATION_FOREGROUND_EVENT_OVERLAY_SOURCE,
            rom.APPLICATION_FOREGROUND_EVENT_OVERLAY_SIZE,
        )

        self.assertEqual(source_call, [0xBD2C, 0xD350])
        self.assertEqual(
            [
                index for index in range(len(decoder) - 1)
                if decoder[index:index + 2] == [0xBD2C, 0xD350]
            ],
            [
                (
                    rom.APPLICATION_FOREGROUND_EVENT_STATE_CALL_SOURCE -
                    rom.APPLICATION_FOREGROUND_EVENT_OVERLAY_SOURCE
                ) // 2
            ],
        )
        self.assertEqual(wrapper[:len(embedded)], embedded)
        self.assertEqual(
            wrapper[len(embedded):],
            [0x6810, 0x0000, 0xAD2C, 0xD350],
        )
        call_patch = rom.foreground_event_state_lazy_call_patch_words()
        self.assertEqual(
            call_patch,
            rom.write_program_words(
                rom.APPLICATION_FOREGROUND_EVENT_STATE_CALL,
                [0xBD06, 0x4B00],
            ),
        )
        installer = rom.install_application_main_chain_words()
        self.assertIn(
            original_copy,
            [
                installer[index:index + len(original_copy)]
                for index in range(len(installer) - len(original_copy) + 1)
            ],
        )
        self.assertNotIn(
            call_patch,
            [
                installer[index:index + len(call_patch)]
                for index in range(len(installer) - len(call_patch) + 1)
            ],
        )
        loader = rom.rom01_application_loader_words()
        npe_patch = rom.npe_browser_lazy_call_patch_words()
        predicate_installer_call = [
            0xBD00 | (
                rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_INSTALLER_ADDRESS
                >> 16
            ),
            rom.APPLICATION_OPERATION_ACTION_MODE_PREDICATE_INSTALLER_ADDRESS &
            0xFFFF,
        ]
        expected_tail = [
            *npe_patch,
            *call_patch,
            *predicate_installer_call,
            rom.RETS,
        ]
        self.assertEqual(loader[-len(expected_tail):], expected_tail)
        image = rom.build_image()
        self.assertEqual(
            words_at(
                image,
                rom.FOREGROUND_EVENT_STATE_LAZY_WRAPPER_ADDRESS,
                len(wrapper),
            ),
            wrapper,
        )
        modules = {
            item["destination"]: item
            for item in rom.manifest(image)["application_main_chain"]
        }
        self.assertEqual(
            modules["2F:C304"],
            {
                "destination": "2F:C304",
                "source": "4C:C304",
                "bytes": 4,
                "status": (
                    "foreground class-one event call routed through resident "
                    "guest lazy overlay installer"
                ),
            },
        )


if __name__ == "__main__":
    unittest.main()
