from __future__ import annotations

import argparse
import unittest

from scripts.monitor_np560_clock import (
    NATIVE_LCD_MAPPING,
    Rect,
    assess_clock_raster_cycle,
    capture_budget_report,
    changed_pixels,
    clock_raster_pipeline_delta,
    coordinate_contract,
    crop,
    diff_bbox,
    layer_mismatch_report,
    map_native_gray4_to_visible_gray5,
    map_native_x_to_lcd,
    mismatch_metrics,
    normalize_gram_com1,
    normalize_lcd,
    normalize_native,
    parse_clock_raster_pipeline,
    parse_rect,
    region_metrics,
    st7529_com_value,
    threshold_transitions,
    unpack_packed,
)


class ClockMonitorTest(unittest.TestCase):
    def test_parses_default_clock_rectangle(self) -> None:
        self.assertEqual(parse_rect("195,100,45,20"), Rect(195, 100, 45, 20))

    def test_rejects_rectangle_outside_lcd(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_rect("200,100,41,20")

    def test_crops_row_major_frame(self) -> None:
        frame = bytes(range(24))
        self.assertEqual(crop(frame, 6, Rect(2, 1, 3, 2)), bytes((8, 9, 10, 14, 15, 16)))

    def test_reports_changed_bbox_and_count(self) -> None:
        before = bytes(24)
        after = bytearray(before)
        after[8] = 1
        after[16] = 2
        self.assertEqual(changed_pixels(before, after), 2)
        self.assertEqual(diff_bbox(before, after, 6), (2, 1, 4, 2))

    def test_unpack_packed_pixels(self) -> None:
        self.assertEqual(unpack_packed(bytes((0x12, 0xF0))), bytes((1, 2, 15, 0)))

    def test_normalizes_native_bottom_up_rows(self) -> None:
        physical_rows = bytes((0x12, 0x34, 0x56, 0x78))
        self.assertEqual(
            normalize_native(physical_rows, width=4, height=2),
            bytes((5, 6, 7, 8, 1, 2, 3, 4)),
        )

    def test_normalizes_com1_gram_lines_to_logical_rows(self) -> None:
        raw = bytes((0, 1, 10, 11, 20, 21, 30, 31, 40, 41))
        self.assertEqual(
            normalize_gram_com1(
                raw, width=2, gram_height=5, visible_height=3,
                visible_line=1,
            ),
            bytes((30, 31, 20, 21, 10, 11)),
        )

    def test_lcd_is_already_in_logical_coordinates(self) -> None:
        frame = bytes((1, 2, 3, 4))
        self.assertIs(normalize_lcd(frame, width=2, height=2), frame)

    def test_extracts_st7529_com_setting(self) -> None:
        registers = "PC=00:0000\nST7529=on SLEEP=off INV=on COM=1 CMD=5c\n"
        self.assertEqual(st7529_com_value(registers), 1)
        self.assertIsNone(st7529_com_value("ST7529=unavailable"))

    def test_counts_both_threshold_directions(self) -> None:
        self.assertEqual(
            threshold_transitions(bytes((1, 15, 3)), bytes((15, 1, 4)), 7),
            (1, 1),
        )

    def test_region_metrics_distinguish_draw_and_clear(self) -> None:
        before = bytes((0, 0, 0, 0, 0, 9, 9, 0))
        after = bytes((0, 0, 0, 0, 9, 0, 9, 0))
        self.assertEqual(
            region_metrics(before, after, 4, Rect(0, 1, 4, 1), 7),
            {
                "changed_pixels": 2,
                "drawn_pixels": 1,
                "cleared_pixels": 1,
                "diff_bbox": (0, 0, 1, 0),
                "evidence_scope": "completed-frame endpoints only",
                "proves_clear_before_draw": False,
            },
        )

    def test_region_metrics_support_post_inverse_foreground(self) -> None:
        before = bytes((31, 0))
        after = bytes((0, 31))
        metrics = region_metrics(
            before, after, 2, Rect(0, 0, 2, 1), 15,
            foreground_high=False,
        )
        self.assertEqual(metrics["drawn_pixels"], 1)
        self.assertEqual(metrics["cleared_pixels"], 1)

    def test_mismatch_metrics_split_clock_rect_and_outside(self) -> None:
        left = bytes(8)
        right = bytearray(left)
        right[1] = 1
        right[7] = 1
        self.assertEqual(
            mismatch_metrics(left, right, 4, Rect(1, 0, 2, 1)),
            {
                "available": True,
                "verified": True,
                "total_mismatch_pixels": 2,
                "clock_rect_mismatch_pixels": 1,
                "outside_clock_rect_mismatch_pixels": 1,
                "diff_bbox": (1, 0, 3, 1),
                "clock_rect_diff_bbox": (0, 0, 0, 0),
            },
        )

    def test_layer_report_does_not_guess_native_to_lcd_mapping(self) -> None:
        size = 240 * 120
        report = layer_mismatch_report(
            bytes(size), bytes(size), bytes(size), bytes(size),
            Rect(195, 100, 45, 20),
        )
        self.assertEqual(
            report["back_vs_front_gray4"]["total_mismatch_pixels"], 0,
        )
        self.assertEqual(
            report["gram_visible_vs_lcd_gray5"]["total_mismatch_pixels"], 0,
        )
        cross_domain = report["front_gray4_vs_gram_visible_gray5"]
        self.assertFalse(cross_domain["available"])
        self.assertFalse(cross_domain["verified"])
        self.assertIsNone(cross_domain["clock_rect_mismatch_pixels"])
        self.assertFalse(NATIVE_LCD_MAPPING["verified"])
        self.assertIsNone(map_native_x_to_lcd(195))
        self.assertIsNone(map_native_gray4_to_visible_gray5(15))
        self.assertIsNone(
            coordinate_contract()["native_to_lcd"]["native_x_to_lcd_x"],
        )

    @staticmethod
    def raster_cycle(sequence: int, foreground: tuple[int, int, int, int],
                     hashes: tuple[str, str, str, str],
                     levels: tuple[str, str, str, str] | None = None) -> str:
        if levels is None:
            levels = tuple(
                "8001" if foreground_pixels else "0001"
                for foreground_pixels in foreground
            )
        stages = "".join(
            f"/s{stage}:back{hashes[stage]}/f{foreground[stage]}/l{levels[stage]},"
            f"front11111111/f0/l0001/p500000/m1/a000f/b0000"
            for stage in range(4)
        )
        return (
            f"#{sequence}/vf/text:2030303a30390000" + stages
        )

    def test_parses_bounded_clock_raster_pipeline(self) -> None:
        cycle = self.raster_cycle(
            7, (12, 0, 0, 15),
            ("aaaaaaaa", "bbbbbbbb", "bbbbbbbb", "cccccccc"),
        )
        report = parse_clock_raster_pipeline(
            f"PC=00:0000\nCLOCK_RASTER_PIPELINE=COUNT:7 TRACE:{cycle}\n",
        )
        self.assertTrue(report["available"])
        self.assertTrue(report["verified"])
        self.assertEqual(report["count"], 7)
        self.assertEqual(report["retained_cycles"], 1)
        parsed = report["cycles"][0]
        self.assertEqual(parsed["sequence"], 7)
        self.assertEqual(parsed["text_ascii"], " 00:09")
        self.assertEqual(parsed["stages"][1]["back_foreground_pixels"], 0)

    def test_rejects_unbounded_or_malformed_raster_trace(self) -> None:
        cycle = self.raster_cycle(
            1, (0, 0, 0, 1),
            ("aaaaaaaa", "aaaaaaaa", "aaaaaaaa", "bbbbbbbb"),
        )
        too_many = ";".join(cycle.replace("#1/", f"#{index}/")
                            for index in range(1, 10))
        report = parse_clock_raster_pipeline(
            f"CLOCK_RASTER_PIPELINE=COUNT:9 TRACE:{too_many}",
        )
        self.assertFalse(report["available"])
        malformed = parse_clock_raster_pipeline(
            "CLOCK_RASTER_PIPELINE=COUNT:1 TRACE:#1/vf/text:00",
        )
        self.assertFalse(malformed["available"])

    def test_assesses_uniform_background_before_transparent_draw(self) -> None:
        cycle = self.raster_cycle(
            7, (12, 0, 0, 15),
            ("aaaaaaaa", "bbbbbbbb", "bbbbbbbb", "cccccccc"),
        )
        parsed = parse_clock_raster_pipeline(
            f"CLOCK_RASTER_PIPELINE=COUNT:7 TRACE:{cycle}",
        )["cycles"][0]
        assessment = assess_clock_raster_cycle(parsed)
        self.assertTrue(assessment["strict_sequence_evidence"])
        self.assertEqual(
            assessment["classification"],
            "uniform_background_observed_before_text_draw",
        )
        self.assertEqual(
            assessment["background_attribution"],
            "clock background call removed sampled foreground pixels",
        )

    def test_does_not_treat_multilevel_nonforeground_sample_as_clear(self) -> None:
        cycle = self.raster_cycle(
            9, (12, 0, 0, 15),
            ("aaaaaaaa", "bbbbbbbb", "bbbbbbbb", "cccccccc"),
            ("8001", "0003", "0003", "8003"),
        )
        parsed = parse_clock_raster_pipeline(
            f"CLOCK_RASTER_PIPELINE=COUNT:9 TRACE:{cycle}",
        )["cycles"][0]
        assessment = assess_clock_raster_cycle(parsed)
        self.assertFalse(assessment["strict_sequence_evidence"])
        self.assertEqual(assessment["classification"], "inconclusive")
        self.assertFalse(
            assessment["uniform_non_foreground_level_before_text"],
        )

    def test_assesses_foreground_surviving_background_phase(self) -> None:
        cycle = self.raster_cycle(
            8, (12, 12, 12, 15),
            ("aaaaaaaa", "aaaaaaaa", "aaaaaaaa", "cccccccc"),
        )
        parsed = parse_clock_raster_pipeline(
            f"CLOCK_RASTER_PIPELINE=COUNT:8 TRACE:{cycle}",
        )["cycles"][0]
        assessment = assess_clock_raster_cycle(parsed)
        self.assertTrue(assessment["strict_sequence_evidence"])
        self.assertEqual(
            assessment["classification"],
            "foreground_survived_background_phase_before_transparent_draw",
        )

    def test_pipeline_delta_reports_cycles_lost_from_bounded_ring(self) -> None:
        previous = parse_clock_raster_pipeline(
            "CLOCK_RASTER_PIPELINE=COUNT:0 TRACE:none",
        )
        cycles = []
        for sequence in range(3, 11):
            cycles.append(self.raster_cycle(
                sequence, (0, 0, 0, 1),
                ("aaaaaaaa", "aaaaaaaa", "aaaaaaaa", "bbbbbbbb"),
            ))
        current = parse_clock_raster_pipeline(
            "CLOCK_RASTER_PIPELINE=COUNT:10 TRACE:" + ";".join(cycles),
        )
        delta = clock_raster_pipeline_delta(previous, current)
        self.assertTrue(delta["available"])
        self.assertFalse(delta["verified"])
        self.assertEqual(delta["started_cycles"], 10)
        self.assertEqual(delta["retained_new_cycles"], 8)
        self.assertEqual(delta["lost_new_cycles"], 2)

    def test_capture_budget_explains_ninety_second_limit(self) -> None:
        budget = capture_budget_report(90.0, 20, 60.0)
        self.assertFalse(budget["request_fits_expected_period"])
        self.assertEqual(budget["best_case_changes_within_timeout"], 2)
        self.assertEqual(budget["minimum_timeout_best_phase_seconds"], 1140.0)
        self.assertEqual(budget["full_period_budget_seconds"], 1200.0)


if __name__ == "__main__":
    unittest.main()
