from __future__ import annotations

import unittest

from scripts import analyse_np560_app_catalog as catalog


class AppCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.program = catalog.DEFAULT_PROGRAM.read_bytes()
        cls.result = catalog.analyse(cls.program)

    def test_catalogue_has_exact_v380_shape(self) -> None:
        recovered = self.result["catalogue"]
        self.assertEqual(recovered["source"], "3D:1142..3D:161A")
        self.assertEqual(recovered["destination"], "20:1142..20:161A")
        self.assertEqual(recovered["entry_words"], 5)
        self.assertEqual(recovered["entry_count"], 124)

        entries = recovered["entries"]
        self.assertEqual(
            [entry["name"] for entry in entries[:5]],
            ["娱乐", "时间", "计算", "翻译", "资料"],
        )
        self.assertEqual(
            [entries[index]["field3"] for index in range(3)],
            [6, 7, 8],
        )
        self.assertTrue(all(entries[index]["submenu_flag"]
                            for index in range(3)))
        self.assertEqual(entries[3]["field4"], 0x7B)
        self.assertEqual(entries[4]["field4"], 0x7A)

    def test_catalogue_is_a_maximal_discovered_record_run(self) -> None:
        runs = self.result["descriptor_runs"]
        matching = [run for run in runs if run["source"] == "3D:1142"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["count"], 124)

    def test_event_jump_table_and_actions_are_exact(self) -> None:
        dispatcher = self.result["event_dispatcher"]
        self.assertEqual(dispatcher["destination"], "18:9A58..18:A510")
        self.assertEqual(dispatcher["jump_table"]["82"], "18:9EBA")
        self.assertEqual(dispatcher["jump_table"]["83"], "18:9FB0")
        self.assertEqual(dispatcher["jump_table"]["84"], "18:9F00")
        self.assertEqual(dispatcher["jump_table"]["85"], "18:A020")
        self.assertEqual(dispatcher["catalogue_helper_actions"]["82"], [1])
        self.assertEqual(
            dispatcher["catalogue_helper_actions"]["84 when item type is 8"],
            [7],
        )
        self.assertEqual(
            dispatcher["catalogue_helper_actions"]["84 when item type is 6"],
            [9],
        )

    def test_menu_page_table_recovers_root_and_all_subgroups(self) -> None:
        recovered = self.result["menu_pages"]
        self.assertEqual(recovered["source"], "39:9748..39:9DBA")
        self.assertEqual(recovered["destination"], "1C:9748..1C:9DBA")
        self.assertEqual(recovered["record_bytes"], 0x42)
        self.assertEqual(recovered["page_count"], 25)

        pages = recovered["pages"]
        self.assertEqual(
            [item["name"] for item in pages[0]["items"]],
            ["娱乐", "时间", "计算", "翻译", "资料"],
        )
        self.assertEqual(
            [item["name"] for item in pages[6]["items"]],
            ["MP3 播放", "游戏世界", "动漫欣赏", "数码录音"],
        )
        self.assertEqual(pages[7]["item_count"], 7)
        self.assertEqual(pages[8]["item_count"], 9)
        self.assertEqual(
            [item["name"] for item in pages[24]["items"]],
            ["词头", "词尾"],
        )

    def test_exact_relocation_chain_is_present(self) -> None:
        self.assertEqual(
            self.result["catalogue_helper"]["destination"],
            "20:0B82..20:1142",
        )
        self.assertEqual(
            self.result["event_wrapper"]["destination"],
            "31:138C..31:145A",
        )
        self.assertEqual(
            self.result["event_wrapper"]["resident_call"], "18:9A58"
        )

    def test_application_registry_and_binary_lookup_are_exact(self) -> None:
        recovered = self.result["application_registry"]
        self.assertEqual(recovered["source"], "47:0514..47:079C")
        self.assertEqual(recovered["destination"], "2A:0514..2A:079C")
        self.assertEqual(recovered["entry_words"], 4)
        self.assertEqual(recovered["entry_count"], 81)
        self.assertEqual(recovered["entries"][0]["application_code_hex"],
                         "0100")
        self.assertEqual(recovered["entries"][0]["entry_point"], "28:EEE8")
        self.assertEqual(recovered["entries"][59]["application_code_hex"],
                         "1203")
        self.assertEqual(recovered["entries"][59]["entry_point"], "2C:C9E8")
        self.assertEqual(recovered["entries"][-1]["application_code_hex"],
                         "2000")
        self.assertEqual(recovered["lookup"]["destination"],
                         "2F:E4C8..2F:E5EC")
        self.assertEqual(recovered["lookup"]["algorithm"], "binary search")
        self.assertEqual(recovered["lookup"]["direct_caller_source"],
                         "35:24A6")
        self.assertEqual(
            recovered["launch_manager"]["destination"],
            "18:21F4..18:2D22",
        )
        self.assertEqual(recovered["launch_manager"]["registry_call"],
                         "18:24A6 -> 2F:E4C8")


if __name__ == "__main__":
    unittest.main()
