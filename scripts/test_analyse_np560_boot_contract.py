from __future__ import annotations

import unittest

from scripts import analyse_np560_boot_contract as boot


class BootContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.program = boot.DEFAULT_PROGRAM.read_bytes()
        cls.burner = boot.DEFAULT_BURNER.read_bytes()

    def test_v380_images_satisfy_recovered_contract(self) -> None:
        contract = boot.analyse_contract(self.program, self.burner)
        proven = contract["proven"]

        self.assertEqual(proven["reset"]["resident_call"], "03:0030")
        self.assertEqual(proven["reset"]["continuation"], "33:4F50")
        self.assertFalse(proven["reset"]["flat_image_is_reset_code"])
        self.assertEqual(proven["reset"]["linked_transfer_counts"], {
            "33:603C": 1,
            "11:4560": 1,
            "07:7FE4": 1,
            "03:026A": 1,
        })
        self.assertEqual(proven["reset"]["linked_source_transfer_counts"], {
            "50:603C": 0,
            "2E:4560": 0,
            "24:7FE4": 0,
            "20:026A": 0,
        })
        self.assertEqual(
            [item["source"] for item in proven["reset"]["linked_preambles"]],
            ["50:4F50..50:4F64", "50:603C..50:6048"],
        )
        self.assertEqual(
            proven["fixed_callback_20_0030"]["zeroed_half_open_ranges"],
            [
                "00:0100..00:0FA0",
                "00:0FF0..00:5000",
                "00:8000..00:9000",
                "50:0000..54:0000",
            ],
        )
        self.assertEqual(proven["entry_20_026a"]["first_call"], "2C:9A7C")
        self.assertEqual(
            proven["entry_20_026a"]["application_call"],
            "20:031C -> 2D:7DD2",
        )
        self.assertEqual(
            proven["entry_20_026a"]["application_call_count"], 1
        )
        self.assertEqual(
            proven["entry_20_026a"]["resident_03_0080_reference_count"], 0
        )
        self.assertTrue(
            proven["entry_20_026a"]["returns_immediately_after_application"]
        )
        candidate = proven["entry_20_026a"]["same_pc_overlay_candidate"]
        self.assertEqual(candidate["source"], "49:9A7C..49:9C66")
        self.assertEqual(candidate["destination"], "2C:9A7C..2C:9C66")
        self.assertEqual(candidate["bytes"], 0x1EA)
        self.assertEqual(candidate["direct_calls_to_source_segment"], 0)
        self.assertEqual(candidate["nested_calls"], ["33:6030", "08:427E"])
        self.assertEqual(proven["compiler_runtime"]["startup_copy_count"], 21)
        initializers = proven["program_overlay_initializers"]
        self.assertEqual(initializers["copy_template"], "4F:F786..4F:F7C2")
        self.assertEqual(initializers["overlay_call_target"], "32:F786")
        self.assertEqual(initializers["descriptor_count"], 270)
        self.assertEqual(
            [group["count"] for group in initializers["groups"]], [9, 261]
        )
        self.assertEqual(
            [group["continuation"] for group in initializers["groups"]],
            ["03:026A", "07:7FE4"],
        )
        self.assertEqual(initializers["linked_execution_order"], [
            "11:4560 (source 2E:4560, 261 copies)",
            "07:7FE4 (source 24:7FE4, 9 copies)",
            "03:026A (source 20:026A, system main)",
        ])
        self.assertEqual(initializers["first_factory_sources"], [
            {
                "destination": "04:FFF8",
                "source": "21:FFF8",
                "bytes": 8,
                "storage_hex": "0000000000008002",
            },
            {
                "destination": "07:57C8",
                "source": "24:57C8",
                "bytes": 4,
                "storage_hex": "00000000",
            },
            {
                "destination": "07:A622",
                "source": "24:A622",
                "bytes": 16,
                "storage_hex": "0000000000000000000020c620c60000",
            },
        ])
        rom08 = proven["resident_rom08_module"]
        self.assertEqual(rom08["destination"], "08:2EDC..08:4B8E")
        self.assertEqual(rom08["source"], "25:2EDC..25:4B8E")
        self.assertEqual(rom08["bytes"], 0x1CB2)
        self.assertEqual(rom08["direct_call_count"], 316)
        self.assertEqual(rom08["direct_target_count"], 43)
        self.assertEqual(rom08["source_address_direct_calls"], 0)
        self.assertEqual(rom08["source_internal_calls_to_segment_08"], 27)
        self.assertEqual(rom08["source_internal_calls_to_segment_25"], 0)
        self.assertTrue(rom08["exact_guest_words_recovered"])
        self.assertFalse(rom08["mask_rom_dump_present"])
        far_memcpy = proven["resident_far_memcpy"]
        self.assertEqual(far_memcpy["address"], "18:6D56")
        self.assertEqual(far_memcpy["direct_call_count"], 16)
        self.assertEqual(far_memcpy["stack_words"], 5)
        self.assertEqual(far_memcpy["fixed_zero_expansion"], {
            "destination": "50:3842",
            "source": "50:3840",
            "bytes": 0x383E,
        })
        self.assertFalse(far_memcpy["original_rom_bytes_present"])
        far_memcpy_08 = proven["resident_far_memcpy_08"]
        self.assertEqual(far_memcpy_08["address"], "08:43A6")
        self.assertEqual(far_memcpy_08["direct_call_count"], 9)
        self.assertEqual(far_memcpy_08["stack_words"], 5)
        self.assertEqual(far_memcpy_08["fixed_copy"], {
            "destination": "50:3840",
            "source": "50:0000",
            "bytes": 0x3840,
        })
        self.assertEqual(far_memcpy_08["forward_overlap"], {
            "destination": "source + 2",
            "bytes": 0x383E,
        })
        self.assertEqual(far_memcpy_08["source"], "25:43A6..25:441A")
        self.assertTrue(far_memcpy_08["exact_guest_body_recovered"])
        self.assertFalse(far_memcpy_08["mask_rom_dump_present"])
        resident_dispatch_1a = proven["resident_dispatch_1a"]
        self.assertEqual(resident_dispatch_1a["address"], "1A:423C")
        self.assertEqual(resident_dispatch_1a["source"],
                         "37:423C..37:4B9C")
        self.assertEqual(resident_dispatch_1a["bytes"], 0x960)
        self.assertEqual(resident_dispatch_1a["direct_call_count"], 29)
        self.assertEqual(resident_dispatch_1a["cleanup_count"], 29)
        self.assertEqual(resident_dispatch_1a["source_address_direct_calls"], 0)
        self.assertTrue(resident_dispatch_1a["exact_guest_body_recovered"])
        self.assertFalse(resident_dispatch_1a["mask_rom_dump_present"])
        resident_application_event = proven["resident_application_event"]
        self.assertEqual(resident_application_event["address"], "1F:B496")
        self.assertEqual(resident_application_event["source"],
                         "3C:B496..3C:BA66")
        self.assertEqual(resident_application_event["bytes"], 0x5D0)
        self.assertEqual(resident_application_event["direct_call_count"], 9)
        self.assertEqual(resident_application_event["stack_words"], 1)
        self.assertEqual(resident_application_event["cleanup_count"], 9)
        self.assertEqual(
            resident_application_event["source_address_direct_calls"], 0
        )
        self.assertTrue(
            resident_application_event["exact_guest_body_recovered"]
        )
        self.assertFalse(resident_application_event["mask_rom_dump_present"])
        self.assertEqual(
            proven["resident_lcd_same_pc_sources"],
            [
                {
                    "destination": "14:6622",
                    "source": "31:6622",
                    "bytes": 0x30,
                    "destination_address_direct_calls": 8,
                    "source_address_direct_calls": 0,
                },
                {
                    "destination": "14:665A",
                    "source": "31:665A",
                    "bytes": 0x3A,
                    "destination_address_direct_calls": 1,
                    "source_address_direct_calls": 0,
                },
                {
                    "destination": "14:65CE",
                    "source": "31:65CE",
                    "bytes": 0x1C,
                    "destination_address_direct_calls": 1,
                    "source_address_direct_calls": 0,
                },
                {
                    "destination": "14:68B0",
                    "source": "31:68B0",
                    "bytes": 0x228,
                    "destination_address_direct_calls": 1,
                    "source_address_direct_calls": 0,
                },
                {
                    "destination": "14:6AD8",
                    "source": "31:6AD8",
                    "bytes": 0x14,
                    "destination_address_direct_calls": 1,
                    "source_address_direct_calls": 0,
                },
                {
                    "destination": "14:6AEC",
                    "source": "31:6AEC",
                    "bytes": 0xEA,
                    "destination_address_direct_calls": 2,
                    "source_address_direct_calls": 0,
                },
                {
                    "destination": "14:6E10",
                    "source": "31:6E10",
                    "bytes": 0x120,
                    "destination_address_direct_calls": 1,
                    "source_address_direct_calls": 0,
                },
                {
                    "destination": "14:6F30",
                    "source": "31:6F30",
                    "bytes": 0x10,
                    "destination_address_direct_calls": 37,
                    "source_address_direct_calls": 0,
                },
            ],
        )
        runtime_overlays = proven["runtime_overlay_candidates"]
        self.assertEqual(
            [(item["destination"], item["source"], item["bytes"])
             for item in runtime_overlays],
            [
                ("2C:9A7C..2C:9C66", "49:9A7C..49:9C66", 0x1EA),
                ("2E:5316..2E:549A", "4B:5316..4B:549A", 0x184),
                ("33:6030..33:603C", "50:6030..50:603C", 0x0C),
                ("33:5906..33:5916", "50:5906..50:5916", 0x10),
                ("31:AF72..31:B014", "4E:AF72..4E:B014", 0xA2),
                ("31:B014..31:B0B6", "4E:B014..4E:B0B6", 0xA2),
                ("33:38D6..33:38F8", "50:38D6..50:38F8", 0x22),
                ("33:305E..33:3082", "50:305E..50:3082", 0x24),
                ("33:180A..33:1838", "50:180A..50:1838", 0x2E),
                ("32:4218..32:4290", "4F:4218..4F:4290", 0x78),
                ("32:CC9C..32:CCE8", "4F:CC9C..4F:CCE8", 0x4C),
                ("32:8EBE..32:8F20", "4F:8EBE..4F:8F20", 0x62),
                ("31:4BAC..31:4C68", "4E:4BAC..4E:4C68", 0xBC),
                ("31:A914..31:A9B8", "4E:A914..4E:A9B8", 0xA4),
                ("24:9BD4..24:9BE8", "41:9BD4..41:9BE8", 0x14),
                ("30:9E30..30:9F20", "4D:9E30..4D:9F20", 0xF0),
                ("32:D530..32:D578", "4F:D530..4F:D578", 0x48),
                ("33:5FD0..33:5FDC", "50:5FD0..50:5FDC", 0x0C),
                ("33:5C18..33:5C26", "50:5C18..50:5C26", 0x0E),
                ("33:4492..33:44AE", "50:4492..50:44AE", 0x1C),
                ("31:F282..31:F312", "4E:F282..4E:F312", 0x90),
                ("27:507C..27:53CC", "44:507C..44:53CC", 0x350),
                ("31:C0E8..31:C186", "4E:C0E8..4E:C186", 0x9E),
                ("31:4D24..31:4DE0", "4E:4D24..4E:4DE0", 0xBC),
                ("25:206E..25:2478", "42:206E..42:2478", 0x40A),
                ("33:5CB2..33:5CC0", "50:5CB2..50:5CC0", 0x0E),
                ("33:3C86..33:3CA6", "50:3C86..50:3CA6", 0x20),
                ("33:2FF2..33:3016", "50:2FF2..50:3016", 0x24),
                ("33:5B70..33:5B7E", "50:5B70..50:5B7E", 0x0E),
            ],
        )
        self.assertEqual(runtime_overlays[1]["source_segment_direct_calls"], 0)
        self.assertEqual(runtime_overlays[2]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[3]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[4]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[5]["destination_address_direct_calls"], 130)
        self.assertEqual(runtime_overlays[5]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[6]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[7]["destination_address_direct_calls"], 7)
        self.assertEqual(runtime_overlays[7]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[8]["destination_address_direct_calls"], 1)
        self.assertEqual(runtime_overlays[8]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[9]["destination_address_direct_calls"], 4)
        self.assertEqual(runtime_overlays[9]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[10]["destination_address_direct_calls"], 88)
        self.assertEqual(runtime_overlays[10]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[10]["nested_call"], "18:6D56")
        self.assertEqual(runtime_overlays[11]["destination_address_direct_calls"], 3)
        self.assertEqual(runtime_overlays[11]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[12]["destination_address_direct_calls"], 128)
        self.assertEqual(runtime_overlays[13]["destination_address_direct_calls"], 4)
        self.assertEqual(runtime_overlays[13]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[13]["nested_calls"],
                         ["14:65CE", "14:6622"])
        self.assertEqual(runtime_overlays[14]["destination_address_direct_calls"], 1)
        self.assertEqual(runtime_overlays[14]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[15]["destination_address_direct_calls"], 17)
        self.assertEqual(runtime_overlays[15]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[15]["abi"],
                         "two stack words at FP+6 and FP+8")
        self.assertEqual(runtime_overlays[16]["destination_address_direct_calls"], 306)
        self.assertEqual(runtime_overlays[16]["cleanup_count"], 306)
        self.assertEqual(runtime_overlays[16]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[16]["nested_calls"],
                         ["33:5FD0", "33:4492", "31:F282"])
        self.assertEqual(runtime_overlays[17]["destination_address_direct_calls"], 11)
        self.assertEqual(runtime_overlays[17]["nested_call"], "33:5C18")
        self.assertEqual(runtime_overlays[18]["destination_address_direct_calls"], 13)
        self.assertEqual(runtime_overlays[19]["destination_address_direct_calls"], 56)
        self.assertEqual(runtime_overlays[19]["cleanup_count"], 56)
        self.assertEqual(runtime_overlays[19]["nested_call"], "2F:5B98")
        self.assertEqual(runtime_overlays[20]["destination_address_direct_calls"], 40)
        self.assertEqual(runtime_overlays[20]["cleanup_count"], 40)
        self.assertEqual(runtime_overlays[20]["nested_calls"],
                         ["21:FD80", "33:463E", "32:4C34", "29:3DD2",
                          "32:C476"])
        self.assertEqual(runtime_overlays[21]["destination_address_direct_calls"], 165)
        self.assertEqual(runtime_overlays[21]["cleanup_count"], 165)
        self.assertEqual(runtime_overlays[21]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[22]["destination_address_direct_calls"], 194)
        self.assertEqual(runtime_overlays[22]["cleanup_count"], 194)
        self.assertEqual(runtime_overlays[22]["nested_call"], "31:4D24")
        self.assertEqual(runtime_overlays[23]["destination_address_direct_calls"], 445)
        self.assertEqual(runtime_overlays[23]["cleanup_count"], 445)
        self.assertEqual(runtime_overlays[24]["destination_address_direct_calls"], 100)
        self.assertEqual(runtime_overlays[24]["cleanup_count"], 100)
        self.assertEqual(runtime_overlays[24]["nested_call"], "28:12A8")
        self.assertEqual(runtime_overlays[25]["destination_address_direct_calls"], 35)
        self.assertEqual(runtime_overlays[26]["destination_address_direct_calls"], 29)
        self.assertEqual(runtime_overlays[26]["nested_call"], "14:6E10")
        self.assertEqual(runtime_overlays[27]["destination_address_direct_calls"], 107)
        self.assertEqual(runtime_overlays[27]["nested_call"], "14:6AEC")
        self.assertEqual(runtime_overlays[28]["destination_address_direct_calls"], 36)
        self.assertEqual(runtime_overlays[28]["source_address_direct_calls"], 0)
        self.assertEqual(runtime_overlays[4]["next_call"], "08:427E")
        self.assertEqual(runtime_overlays[6]["previous_call"], "08:427E")

    def test_signature_mismatch_is_not_silently_accepted(self) -> None:
        changed = bytearray(self.program)
        changed[0] ^= 1

        with self.assertRaisesRegex(boot.EvidenceMismatch, "reset resident call"):
            boot.analyse_contract(bytes(changed), self.burner)

    def test_report_separates_proof_from_inference(self) -> None:
        contract = boot.analyse_contract(self.program, self.burner)
        report = boot.render_markdown(contract)

        self.assertIn("Proven from NP560.PRG", report)
        self.assertIn("Consequences for the emulator", report)
        self.assertIn("does not claim to recover", report)
        self.assertIn("Program/NOR bytes and writable external data RAM", report)


if __name__ == "__main__":
    unittest.main()
