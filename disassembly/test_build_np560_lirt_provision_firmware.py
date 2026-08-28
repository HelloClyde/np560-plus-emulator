from __future__ import annotations

import unittest

import build_np560_lirt_provision_firmware as provision
import build_np560_minimal_nwf as nwf


class LirtProvisionFirmwareTests(unittest.TestCase):
    def fixture_program(self) -> bytes:
        image = bytearray(b"\x00" * provision.PROGRAM_SIZE)
        wrapper_offset = provision.file_offset(provision.PROVISION_WRAPPER)
        image[wrapper_offset:] = b"\xFF" * (len(image) - wrapper_offset)
        provision.put_words(
            image,
            provision.PROVISION_TRIGGER_CALL,
            list(provision.PROVISION_TRIGGER_CALL_WORDS),
        )
        provision.put_words(
            image,
            provision.LATE_PROVISION_TRIGGER_CALL,
            list(provision.LATE_PROVISION_TRIGGER_CALL_WORDS),
        )
        return bytes(image)

    def test_wrapper_calls_only_guest_resident_apis(self) -> None:
        words = provision.provision_wrapper_words()
        pairs = set(zip(words, words[1:]))
        for target in (
            provision.RESOURCE_STAT,
            provision.RESIDENT_FILE_OPEN,
            provision.RESIDENT_FILE_CLOSE,
            provision.PROVISION_WRITER,
            provision.ORIGINAL_TRIGGER_TARGET,
        ):
            self.assertIn((0xBD00 | (target >> 16), target & 0xFFFF), pairs)

        writer = provision.provision_writer_words(nwf.build_candidate())
        self.assertEqual(
            sum(
                pair == (0xBD17, 0xE3EE)
                for pair in zip(writer, writer[1:])
            ),
            len(nwf.build_candidate()) // provision.PROVISION_CHUNK_BYTES,
        )

    def test_wrapper_materialises_resource_path_in_near_ram(self) -> None:
        words = provision.provision_wrapper_words()
        for index, path_word in enumerate(provision.PROVISION_PATH_WORDS):
            offset = (
                provision.PROVISION_PATH_FP_OFFSET + index * 2
            ) & 0xFFFF
            self.assertIn(
                [0x68F0, path_word, 0x6A0B, offset],
                [words[start:start + 4] for start in range(len(words) - 3)],
            )
        self.assertIn(
            [
                0x081B,
                0x70F1,
                provision.PROVISION_PATH_FP_OFFSET & 0xFFFF,
                0x4800,
            ],
            [words[start:start + 4] for start in range(len(words) - 3)],
        )
        open_call = next(
            index for index in range(len(words) - 1)
            if words[index:index + 2] == [0xBD1F, 0x1F1A]
        )
        self.assertEqual(
            words[open_call - 8:open_call + 2],
            [
                0x4800, 0x58F0,  # mode 0: create if missing
                0x081B, 0x70F1,
                provision.PROVISION_PATH_FP_OFFSET & 0xFFFF,
                0x4800, 0x58F1, 0x58F0,
                0xBD1F, 0x1F1A,
            ],
        )

    def test_guest_path_encoder_supports_root_path_and_rejects_overflow(self) -> None:
        words = provision.encode_guest_path_words(r"0:\lirt.nwf")
        self.assertEqual(words[:6], (0x303A, 0x5C6C, 0x6972, 0x742E, 0x6E77, 0x6600))
        self.assertEqual(words[6:], (0, 0, 0, 0))
        with self.assertRaisesRegex(ValueError, "limit"):
            provision.encode_guest_path_words("x" * provision.PROVISION_PATH_BYTES)

    def test_writer_materialises_guest_bytes_and_uses_exact_write_abi(self) -> None:
        candidate = nwf.build_candidate()
        words = provision.provision_writer_words(candidate)
        self.assertEqual(words[0], 0x2E80)
        self.assertEqual(
            words[1:9],
            [
                0x68F0,
                int.from_bytes(candidate[:2], "big"),
                0x6A0B,
                provision.PROVISION_BUFFER_FP_OFFSET & 0xFFFF,
                0x68F0,
                int.from_bytes(candidate[2:4], "big"),
                0x6A0B,
                (provision.PROVISION_BUFFER_FP_OFFSET + 2) & 0xFFFF,
            ],
        )
        first_write = words.index(0xBD17)
        self.assertEqual(
            words[first_write:first_write + 3],
            [0xBD17, 0xE3EE, 0x50FC],
        )
        self.assertEqual(
            words[first_write - 17:first_write - 13],
            [0x68F1, 0x0100, 0x4800, 0x58F1],
        )

    def test_writer_delta_preprocessing_keeps_all_native_writes(self) -> None:
        candidate = nwf.build_candidate()
        words = provision.provision_writer_words(candidate)
        full_words = len(candidate) // 2
        materialized = provision.delta_materialized_word_count(candidate)
        self.assertLess(materialized, full_words // 10)
        self.assertLess(len(words) * 2, 0xC000)
        self.assertEqual(
            sum(
                pair == (0xBD17, 0xE3EE)
                for pair in zip(words, words[1:])
            ),
            32,
        )

    def test_build_patches_call_and_compiles_guest_data(self) -> None:
        candidate = nwf.build_candidate()
        result, manifest = provision.build_firmware(
            self.fixture_program(), candidate
        )
        self.assertEqual(
            provision.read_words(result, provision.PROVISION_TRIGGER_CALL, 2),
            (
                0xBD00 | (provision.PROVISION_WRAPPER >> 16),
                provision.PROVISION_WRAPPER & 0xFFFF,
            ),
        )
        self.assertEqual(manifest["provision_trigger_call_runtime"], "2D:7F66")
        self.assertEqual(
            manifest["provision_trigger_original_target"], "33:6F30"
        )
        self.assertEqual(manifest["resident_open_path"], "near copy at FP-0018")
        self.assertEqual(manifest["writer_chunks"], 32)
        self.assertEqual(manifest["writer_chunk_bytes"], 0x100)
        self.assertEqual(manifest["writer_unique_chunks"], 4)
        self.assertEqual(
            manifest["writer_materialized_words"],
            provision.delta_materialized_word_count(candidate),
        )
        writer = provision.read_words(
            result,
            provision.PROVISION_WRITER,
            len(provision.provision_writer_words(candidate)),
        )
        self.assertEqual(writer[1], 0x68F0)
        self.assertEqual(writer[2], int.from_bytes(candidate[:2], "big"))
        self.assertFalse(manifest["host_filesystem_service"])
        self.assertFalse(manifest["scall_interception"])

    def test_late_trigger_forwards_main_resource_arguments(self) -> None:
        candidate = nwf.build_candidate()
        result, manifest = provision.build_firmware(
            self.fixture_program(), candidate,
            r"0:\多媒体\lirt.nwf", "main-resource",
        )
        self.assertEqual(
            provision.read_words(
                result, provision.LATE_PROVISION_TRIGGER_CALL, 2
            ),
            (
                0xBD00 | (provision.PROVISION_WRAPPER >> 16),
                provision.PROVISION_WRAPPER & 0xFFFF,
            ),
        )
        self.assertEqual(manifest["provision_trigger"], "main-resource")
        self.assertEqual(manifest["provision_trigger_call_runtime"], "22:5582")
        self.assertEqual(manifest["provision_trigger_original_target"], "32:512C")
        self.assertEqual(manifest["provision_trigger_forwarded_far_args"], 2)

        wrapper = provision.provision_wrapper_words(
            provision.encode_guest_path_words(r"0:\多媒体\lirt.nwf"),
            original_target=provision.LATE_ORIGINAL_TRIGGER_TARGET,
            forward_far_args=2,
        )
        call = next(
            index for index in range(len(wrapper) - 1)
            if wrapper[index:index + 2] == [0xBD32, 0x512C]
        )
        self.assertEqual(
            wrapper[call - 12:call + 3],
            [
                0x780B, 0x000A, 0x781B, 0x000C, 0x58F1, 0x58F0,
                0x780B, 0x0006, 0x781B, 0x0008, 0x58F1, 0x58F0,
                0xBD32, 0x512C, 0x50F8,
            ],
        )

    def test_refuses_to_overwrite_non_erased_injection_region(self) -> None:
        candidate = nwf.build_candidate()
        program = bytearray(self.fixture_program())
        program[provision.file_offset(provision.PROVISION_WRAPPER)] = 0
        with self.assertRaisesRegex(ValueError, "not erased"):
            provision.build_firmware(bytes(program), candidate)

    def test_rearms_exact_inactive_payload_with_a_new_path(self) -> None:
        candidate = nwf.build_candidate()
        root_path = r"0:\lirt.nwf"
        media_path = r"0:\多媒体\lirt.nwf"
        provisioned, _ = provision.build_firmware(
            self.fixture_program(), candidate, root_path, "main-resource",
        )
        finalized = bytearray(provisioned)
        provision.put_words(
            finalized,
            provision.LATE_PROVISION_TRIGGER_CALL,
            list(provision.LATE_PROVISION_TRIGGER_CALL_WORDS),
        )

        result, manifest = provision.build_firmware(
            bytes(finalized), candidate, media_path, "main-resource",
            rearm_existing_path=root_path,
        )

        self.assertEqual(
            provision.read_words(
                result, provision.LATE_PROVISION_TRIGGER_CALL, 2
            ),
            (
                0xBD00 | (provision.PROVISION_WRAPPER >> 16),
                provision.PROVISION_WRAPPER & 0xFFFF,
            ),
        )
        self.assertTrue(manifest["rearmed_existing_payload"])
        self.assertEqual(manifest["previous_guest_path"], root_path)
        self.assertEqual(manifest["guest_path"], media_path)

    def test_rearms_legacy_64k_writer_with_boundary_safe_candidate(self) -> None:
        legacy_candidate = nwf.build_candidate(
            record_offset=nwf.LEGACY_RECORD_OFFSET,
            record_storage_size=nwf.LEGACY_RECORD_STORAGE_SIZE,
        )
        candidate = nwf.build_candidate()
        root_path = r"0:\lirt.nwf"
        provisioned, _ = provision.build_firmware(
            self.fixture_program(), legacy_candidate, root_path,
            "main-resource",
        )
        finalized = bytearray(provisioned)
        provision.put_words(
            finalized,
            provision.LATE_PROVISION_TRIGGER_CALL,
            list(provision.LATE_PROVISION_TRIGGER_CALL_WORDS),
        )

        result, manifest = provision.build_firmware(
            bytes(finalized), candidate, root_path, "main-resource",
            rearm_existing_path=root_path,
            rearm_existing_candidate=legacy_candidate,
        )

        writer = provision.read_words(
            result,
            provision.PROVISION_WRITER,
            len(provision.provision_writer_words(candidate)),
        )
        self.assertEqual(
            writer,
            tuple(provision.provision_writer_words(candidate)),
        )
        self.assertEqual(manifest["writer_chunks"], 32)
        self.assertEqual(
            manifest["previous_nwf_sha256"],
            __import__("hashlib").sha256(legacy_candidate).hexdigest(),
        )

    def test_rearm_refuses_a_payload_from_a_different_path(self) -> None:
        candidate = nwf.build_candidate()
        provisioned, _ = provision.build_firmware(
            self.fixture_program(), candidate, r"0:\lirt.nwf",
            "main-resource",
        )
        finalized = bytearray(provisioned)
        provision.put_words(
            finalized,
            provision.LATE_PROVISION_TRIGGER_CALL,
            list(provision.LATE_PROVISION_TRIGGER_CALL_WORDS),
        )
        with self.assertRaisesRegex(ValueError, "existing provision wrapper"):
            provision.build_firmware(
                bytes(finalized), candidate, r"0:\多媒体\lirt.nwf",
                "main-resource", rearm_existing_path=r"0:\missing.nwf",
            )

    def test_rearms_an_existing_payload_for_a_different_trigger_abi(self) -> None:
        candidate = nwf.build_candidate()
        root_path = r"0:\lirt.nwf"
        media_path = r"0:\多媒体\lirt.nwf"
        provisioned, _ = provision.build_firmware(
            self.fixture_program(), candidate, root_path, "main-resource",
        )
        finalized = bytearray(provisioned)
        provision.put_words(
            finalized,
            provision.LATE_PROVISION_TRIGGER_CALL,
            list(provision.LATE_PROVISION_TRIGGER_CALL_WORDS),
        )

        result, manifest = provision.build_firmware(
            bytes(finalized), candidate, media_path, "initializer",
            rearm_existing_path=root_path,
            rearm_existing_trigger="main-resource",
        )

        self.assertEqual(
            provision.read_words(
                result, provision.PROVISION_TRIGGER_CALL, 2
            ),
            (
                0xBD00 | (provision.PROVISION_WRAPPER >> 16),
                provision.PROVISION_WRAPPER & 0xFFFF,
            ),
        )
        self.assertEqual(
            manifest["previous_provision_trigger"], "main-resource"
        )
        self.assertEqual(manifest["provision_trigger"], "initializer")


if __name__ == "__main__":
    unittest.main()
