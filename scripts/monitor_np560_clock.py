#!/usr/bin/env python3
"""Capture correlated NP560 guest/LCD buffers whenever the clock changes.

The Web frontend is only a transport.  This monitor watches the final 240x120
ST7529 frame, pauses QEMU when the bottom-right clock rectangle changes, and
saves both native guest buffers, controller GRAM, and the final LCD frame.

Every saved layer also gets a logical 240x120 view.  Native buffers are stored
bottom-up, while COMSCN=001 exposes GRAM lines 139..20 as visible rows 0..119.
The native-to-controller horizontal/level transfer is not yet proven, so the
monitor reports that cross-domain comparison as unavailable instead of
silently guessing an X shift or a 4-bit-to-5-bit intensity conversion.

Completed-frame draw/clear counts are explicitly endpoint-only.  When the
QEMU build exposes its bounded CLOCK_RASTER_PIPELINE observer, the monitor also
parses the four exact guest stages around background and transparent text
drawing; only that stage evidence is allowed to make a write-order claim.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

try:
    from scripts.monitor_np560_web import control, render_lcd
except ModuleNotFoundError:  # Direct execution from scripts/.
    from monitor_np560_web import control, render_lcd


LCD_WIDTH = 240
LCD_HEIGHT = 120
GRAM_HEIGHT = 160
GRAM_VISIBLE_LINE = 20
BACK_BASE = 0x500000
FRONT_BASE = 0x503840
NATIVE_SIZE = LCD_WIDTH * LCD_HEIGHT // 2
FRONT_SIZE = NATIVE_SIZE
CLOCK_RASTER_TRACE_SLOTS = 8
CLOCK_RASTER_TEXT_BYTES = 8

# Keep parsing bounded even if a broken or unrelated Web endpoint returns an
# unexpectedly large register dump.  QEMU itself retains only eight cycles.
CLOCK_RASTER_LINE_LIMIT = 32 * 1024

NATIVE_LCD_MAPPING = {
    "verified": False,
    "native_x_to_lcd_x": None,
    "native_gray4_to_visible_gray5": None,
    "reason": (
        "native-to-controller horizontal transfer and 4-bit-to-5-bit level "
        "conversion have not been proven; no offset or level map is guessed"
    ),
}


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


CLOCK_RASTER_SAMPLE_RECT = Rect(196, 107, 40, 8)


def parse_rect(text: str) -> Rect:
    try:
        values = tuple(int(value, 0) for value in text.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "rectangle must use x,y,width,height integers"
        ) from exc
    if len(values) != 4:
        raise argparse.ArgumentTypeError(
            "rectangle must use x,y,width,height"
        )
    rect = Rect(*values)
    if (rect.x < 0 or rect.y < 0 or rect.width <= 0 or rect.height <= 0 or
            rect.right > LCD_WIDTH or rect.bottom > LCD_HEIGHT):
        raise argparse.ArgumentTypeError("rectangle is outside the 240x120 LCD")
    return rect


def crop(frame: bytes, width: int, rect: Rect) -> bytes:
    return b"".join(
        frame[y * width + rect.x:y * width + rect.right]
        for y in range(rect.y, rect.bottom)
    )


def diff_bbox(before: bytes, after: bytes, width: int) -> tuple[int, int, int, int] | None:
    if len(before) != len(after):
        raise ValueError("frames have different lengths")
    changed = [index for index, pair in enumerate(zip(before, after))
               if pair[0] != pair[1]]
    if not changed:
        return None
    xs = [index % width for index in changed]
    ys = [index // width for index in changed]
    return min(xs), min(ys), max(xs), max(ys)


def changed_pixels(before: bytes, after: bytes) -> int:
    if len(before) != len(after):
        raise ValueError("frames have different lengths")
    return sum(left != right for left, right in zip(before, after))


def region_metrics(before: bytes, after: bytes, width: int,
                   rect: Rect, threshold: int,
                   foreground_high: bool = True) -> dict[str, Any]:
    """Describe net endpoint transitions, not the renderer's write order.

    A foreground-to-background endpoint transition is conventionally called a
    cleared pixel below, but two completed frames cannot establish whether the
    guest restored the whole background before drawing the new glyph.  That
    sequence claim is deliberately reserved for the four-stage raster trace.
    """
    before_region = crop(before, width, rect)
    after_region = crop(after, width, rect)
    low_to_high, high_to_low = threshold_transitions(
        before_region, after_region, threshold,
    )
    drawn, cleared = (
        (low_to_high, high_to_low) if foreground_high
        else (high_to_low, low_to_high)
    )
    return {
        "changed_pixels": changed_pixels(before_region, after_region),
        "drawn_pixels": drawn,
        "cleared_pixels": cleared,
        "diff_bbox": diff_bbox(before_region, after_region, rect.width),
        "evidence_scope": "completed-frame endpoints only",
        "proves_clear_before_draw": False,
    }


def threshold_transitions(before: bytes, after: bytes,
                          threshold: int) -> tuple[int, int]:
    """Return low-to-high and high-to-low pixel transition counts."""
    if len(before) != len(after):
        raise ValueError("frames have different lengths")
    low_to_high = sum(
        left <= threshold < right for left, right in zip(before, after)
    )
    high_to_low = sum(
        right <= threshold < left for left, right in zip(before, after)
    )
    return low_to_high, high_to_low


def unpack_packed(frame: bytes) -> bytes:
    pixels = bytearray(len(frame) * 2)
    for index, value in enumerate(frame):
        pixels[index * 2] = value >> 4
        pixels[index * 2 + 1] = value & 0x0F
    return bytes(pixels)


def normalize_native(frame: bytes, width: int = LCD_WIDTH,
                     height: int = LCD_HEIGHT) -> bytes:
    """Decode a packed native framebuffer into logical top-down gray4 rows."""
    if width <= 0 or height <= 0 or width & 1:
        raise ValueError("native dimensions must be positive with even width")
    expected = width * height // 2
    if len(frame) != expected:
        raise ValueError(f"native frame is {len(frame)} bytes, expected {expected}")
    physical = unpack_packed(frame)
    return b"".join(
        physical[(height - 1 - y) * width:(height - y) * width]
        for y in range(height)
    )


def normalize_gram_com1(frame: bytes, width: int = LCD_WIDTH,
                        gram_height: int = GRAM_HEIGHT,
                        visible_height: int = LCD_HEIGHT,
                        visible_line: int = GRAM_VISIBLE_LINE) -> bytes:
    """Map raw controller lines to logical rows for the proven COMSCN=001 case."""
    if len(frame) != width * gram_height:
        raise ValueError(
            f"GRAM frame is {len(frame)} bytes, expected {width * gram_height}"
        )
    if (visible_line < 0 or visible_height <= 0 or
            visible_line + visible_height > gram_height):
        raise ValueError("visible GRAM window is outside the controller frame")
    last_line = visible_line + visible_height - 1
    return b"".join(
        frame[(last_line - y) * width:(last_line - y + 1) * width]
        for y in range(visible_height)
    )


def normalize_lcd(frame: bytes, width: int = LCD_WIDTH,
                  height: int = LCD_HEIGHT) -> bytes:
    """Validate the already-logical gray5 LCD frame."""
    expected = width * height
    if len(frame) != expected:
        raise ValueError(f"LCD frame is {len(frame)} bytes, expected {expected}")
    return frame


def st7529_com_value(registers: str) -> int | None:
    match = re.search(r"^ST7529=.*?\bCOM=(\d+)\b", registers, re.MULTILINE)
    return int(match.group(1)) if match else None


_CLOCK_RASTER_STAGE_RE = re.compile(
    r"/s(?P<stage>[0-3]):"
    r"back(?P<back_hash>[0-9a-fA-F]{8})/"
    r"f(?P<back_foreground>\d+)/l(?P<back_levels>[0-9a-fA-F]{4}),"
    r"front(?P<front_hash>[0-9a-fA-F]{8})/"
    r"f(?P<front_foreground>\d+)/l(?P<front_levels>[0-9a-fA-F]{4})/"
    r"p(?P<pointer>[0-9a-fA-F]{6})/m(?P<mode>\d+)/"
    r"a(?P<mask_a>[0-9a-fA-F]{4})/b(?P<mask_b>[0-9a-fA-F]{4})"
)


def _unavailable_raster_pipeline(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "verified": False,
        "count": None,
        "retained_cycles": 0,
        "retention_limit": CLOCK_RASTER_TRACE_SLOTS,
        "cycles": [],
        "reason": reason,
    }


def parse_clock_raster_pipeline(registers: str) -> dict[str, Any]:
    """Parse QEMU's bounded, observer-only four-stage clock raster trace."""
    line = next(
        (item for item in registers.splitlines()
         if item.startswith("CLOCK_RASTER_PIPELINE=")),
        None,
    )
    if line is None:
        return _unavailable_raster_pipeline(
            "CLOCK_RASTER_PIPELINE is absent from this QEMU build",
        )
    if len(line) > CLOCK_RASTER_LINE_LIMIT:
        return _unavailable_raster_pipeline(
            f"CLOCK_RASTER_PIPELINE exceeds {CLOCK_RASTER_LINE_LIMIT} bytes",
        )
    header = re.fullmatch(
        r"CLOCK_RASTER_PIPELINE=COUNT:(\d+) TRACE:(.*)", line,
    )
    if header is None:
        return _unavailable_raster_pipeline(
            "CLOCK_RASTER_PIPELINE header is malformed",
        )
    count = int(header.group(1))
    trace = header.group(2)
    if trace == "none":
        if count != 0:
            return _unavailable_raster_pipeline(
                "CLOCK_RASTER_PIPELINE has a nonzero count but no trace",
            )
        return {
            "available": True,
            "verified": True,
            "count": 0,
            "retained_cycles": 0,
            "retention_limit": CLOCK_RASTER_TRACE_SLOTS,
            "cycles": [],
        }

    parts = trace.split(";")
    if len(parts) > CLOCK_RASTER_TRACE_SLOTS:
        return _unavailable_raster_pipeline(
            "CLOCK_RASTER_PIPELINE exceeds its eight-cycle retention bound",
        )
    cycles: list[dict[str, Any]] = []
    try:
        for part in parts:
            prefix = re.match(
                rf"#(\d+)/v([0-9a-fA-F]+)/text:"
                rf"([0-9a-fA-F]{{{CLOCK_RASTER_TEXT_BYTES * 2}}})",
                part,
            )
            if prefix is None:
                raise ValueError("cycle prefix is malformed")
            sequence = int(prefix.group(1))
            valid_mask = int(prefix.group(2), 16)
            text_raw = bytes.fromhex(prefix.group(3))
            remainder = part[prefix.end():]
            stages: list[dict[str, Any]] = []
            position = 0
            seen: set[int] = set()
            while position < len(remainder):
                match = _CLOCK_RASTER_STAGE_RE.match(remainder, position)
                if match is None:
                    raise ValueError("stage payload is malformed")
                stage = int(match.group("stage"))
                if stage in seen:
                    raise ValueError(f"stage {stage} is duplicated")
                seen.add(stage)
                stages.append({
                    "stage": stage,
                    "back_hash": match.group("back_hash").lower(),
                    "back_foreground_pixels": int(
                        match.group("back_foreground")
                    ),
                    "back_levels_mask": match.group("back_levels").lower(),
                    "front_hash": match.group("front_hash").lower(),
                    "front_foreground_pixels": int(
                        match.group("front_foreground")
                    ),
                    "front_levels_mask": match.group("front_levels").lower(),
                    "framebuffer_pointer": match.group("pointer").lower(),
                    "glyph_mode": int(match.group("mode")),
                    "mask_a": match.group("mask_a").lower(),
                    "mask_b": match.group("mask_b").lower(),
                })
                position = match.end()
            expected_mask = sum(1 << stage for stage in seen)
            if valid_mask != expected_mask:
                raise ValueError(
                    f"valid mask {valid_mask:x} does not match parsed stages "
                    f"{expected_mask:x}"
                )
            cycles.append({
                "sequence": sequence,
                "valid_mask": f"{valid_mask:x}",
                "text_hex": text_raw.hex(),
                "text_ascii": text_raw.split(b"\0", 1)[0].decode(
                    "ascii", errors="backslashreplace",
                ),
                "stages": sorted(stages, key=lambda item: item["stage"]),
            })
    except ValueError as exc:
        return _unavailable_raster_pipeline(str(exc))

    return {
        "available": True,
        "verified": True,
        "count": count,
        "retained_cycles": len(cycles),
        "retention_limit": CLOCK_RASTER_TRACE_SLOTS,
        "cycles": cycles,
    }


def assess_clock_raster_cycle(cycle: dict[str, Any]) -> dict[str, Any]:
    """Classify only sequence facts directly witnessed by trace stages."""
    stages = {int(item["stage"]): item for item in cycle.get("stages", [])}
    result: dict[str, Any] = {
        "sequence": cycle.get("sequence"),
        "text_ascii": cycle.get("text_ascii"),
        "scope": {
            "buffer": "native back framebuffer",
            "rect": CLOCK_RASTER_SAMPLE_RECT.__dict__,
            "foreground_definition": "gray4 pixel exactly 0xF",
        },
        "complete": set(stages) == {0, 1, 2, 3},
        "classification": "inconclusive",
        "strict_sequence_evidence": False,
    }
    if not result["complete"]:
        result["reason"] = "one or more of stages s0..s3 are absent"
        return result

    before_background = stages[0]
    after_background = stages[1]
    before_text = stages[2]
    after_text = stages[3]
    background_changed = (
        before_background["back_hash"] != after_background["back_hash"]
    )
    stable_until_text = (
        after_background["back_hash"] == before_text["back_hash"]
    )
    text_changed = before_text["back_hash"] != after_text["back_hash"]
    transparent_back_draw = (
        before_text["framebuffer_pointer"] == f"{BACK_BASE:06x}" and
        before_text["glyph_mode"] == 1
    )
    result.update({
        "background_call_changed_sample": background_changed,
        "post_background_stable_until_text": stable_until_text,
        "text_call_changed_sample": text_changed,
        "transparent_back_draw_contract": transparent_back_draw,
        "foreground_pixels": {
            f"s{stage}": stages[stage]["back_foreground_pixels"]
            for stage in range(4)
        },
    })

    s0_foreground = before_background["back_foreground_pixels"]
    s1_foreground = after_background["back_foreground_pixels"]
    s2_foreground = before_text["back_foreground_pixels"]
    s3_foreground = after_text["back_foreground_pixels"]
    s2_levels = int(before_text["back_levels_mask"], 16)
    s3_levels = int(after_text["back_levels_mask"], 16)
    foreground_level = 1 << 15
    s2_is_uniform_background = (
        s2_levels != 0 and
        (s2_levels & foreground_level) == 0 and
        (s2_levels & (s2_levels - 1)) == 0
    )
    s3_retains_background_and_adds_foreground = (
        (s3_levels & s2_levels) == s2_levels and
        (s3_levels & foreground_level) != 0
    )
    result.update({
        "levels_mask": {
            "s2": f"{s2_levels:04x}",
            "s3": f"{s3_levels:04x}",
        },
        "uniform_non_foreground_level_before_text": s2_is_uniform_background,
        "background_retained_and_foreground_added_after_text": (
            s3_retains_background_and_adds_foreground
        ),
    })
    if background_changed and s1_foreground < s0_foreground:
        result["background_attribution"] = (
            "clock background call removed sampled foreground pixels"
        )
    elif not background_changed and s0_foreground == 0:
        result["background_attribution"] = (
            "sample was already clear when the clock background call began"
        )
    elif not background_changed:
        result["background_attribution"] = (
            "clock background call left the sampled pixels unchanged"
        )
    else:
        result["background_attribution"] = (
            "clock background call changed the sample without reducing exact "
            "foreground pixels"
        )

    if (stable_until_text and transparent_back_draw and
            s2_foreground == 0 and s2_is_uniform_background and
            text_changed and s3_foreground > 0 and
            s3_retains_background_and_adds_foreground):
        result["classification"] = (
            "uniform_background_observed_before_text_draw"
        )
        result["strict_sequence_evidence"] = True
        result["reason"] = (
            "s2 contains exactly one non-foreground gray level; the following "
            "transparent text call retains that background level and introduces "
            "the exact foreground level"
        )
    elif (s0_foreground > 0 and not background_changed and
          stable_until_text and transparent_back_draw):
        result["classification"] = (
            "foreground_survived_background_phase_before_transparent_draw"
        )
        result["strict_sequence_evidence"] = True
        result["reason"] = (
            "sampled foreground is present at s0 and survives unchanged through "
            "s1/s2 before the transparent text call"
        )
    else:
        result["reason"] = (
            "the retained hashes/counts do not establish either strict case"
        )
    return result


def clock_raster_pipeline_delta(previous: dict[str, Any],
                                current: dict[str, Any]) -> dict[str, Any]:
    """Return newly retained cycles without inventing data lost from the ring."""
    if not previous.get("available") or not current.get("available"):
        return {
            "available": False,
            "verified": False,
            "new_cycles": [],
            "reason": "raster pipeline is unavailable in one snapshot",
        }
    previous_count = int(previous["count"])
    current_count = int(current["count"])
    if current_count < previous_count:
        return {
            "available": False,
            "verified": False,
            "new_cycles": [],
            "reason": "raster pipeline count reset between snapshots",
        }
    new_cycles = [
        cycle for cycle in current["cycles"]
        if previous_count < int(cycle["sequence"]) <= current_count
    ]
    assessments = [assess_clock_raster_cycle(cycle) for cycle in new_cycles]
    started = current_count - previous_count
    lost = max(0, started - len(new_cycles))
    classifications = {item["classification"] for item in assessments}
    if "foreground_survived_background_phase_before_transparent_draw" in classifications:
        conclusion = "foreground_survived_before_transparent_draw_observed"
    elif "uniform_background_observed_before_text_draw" in classifications:
        conclusion = "uniform_background_before_text_draw_observed"
    elif started == 0:
        conclusion = "no_new_raster_cycle"
    else:
        conclusion = "inconclusive"
    return {
        "available": True,
        "verified": lost == 0,
        "previous_count": previous_count,
        "current_count": current_count,
        "started_cycles": started,
        "retained_new_cycles": len(new_cycles),
        "lost_new_cycles": lost,
        "conclusion": conclusion,
        "new_cycles": assessments,
        "limitation": (
            "strict conclusions cover only the observer's 40x8 native-back "
            "sample; endpoint draw/clear counts alone never prove write order"
        ),
    }


def capture_budget_report(timeout: float, changes: int,
                          expected_period: float) -> dict[str, Any]:
    """Explain the bounded wall-time budget for a periodic clock source."""
    if expected_period <= 0:
        return {
            "available": False,
            "reason": "expected change period is disabled",
        }
    best_case_changes = math.floor(timeout / expected_period) + 1
    minimum_best_phase = max(0, changes - 1) * expected_period
    return {
        "available": True,
        "expected_change_period_seconds": expected_period,
        "timeout_seconds": timeout,
        "requested_changes": changes,
        "best_case_changes_within_timeout": best_case_changes,
        "minimum_timeout_best_phase_seconds": minimum_best_phase,
        "full_period_budget_seconds": changes * expected_period,
        "request_fits_expected_period": timeout >= minimum_best_phase,
        "timeout_scope": "starts after the baseline layer capture",
    }


def map_native_x_to_lcd(logical_x: int) -> int | None:
    """Return the proven LCD X for native X, or None while it is unverified."""
    if not 0 <= logical_x < LCD_WIDTH:
        raise ValueError("native logical X is outside the 240-pixel frame")
    # Keep this unavailable until the guest flush routine proves its ordering.
    return None


def map_native_gray4_to_visible_gray5(level: int) -> int | None:
    """Return the proven visible level, or None while level/INV is unverified."""
    if not 0 <= level <= 15:
        raise ValueError("native gray4 level is outside 0..15")
    # lcd/lcd-gram expose glass darkness after INV; the native conversion is
    # deliberately not inferred from visual similarity.
    return None


def mismatch_metrics(left: bytes, right: bytes, width: int,
                     rect: Rect) -> dict[str, Any]:
    """Count exact mismatches inside and outside one logical rectangle."""
    if len(left) != len(right):
        raise ValueError("frames have different lengths")
    if len(left) % width:
        raise ValueError("frame length is not a whole number of rows")
    total = changed_pixels(left, right)
    left_region = crop(left, width, rect)
    right_region = crop(right, width, rect)
    inside = changed_pixels(left_region, right_region)
    return {
        "available": True,
        "verified": True,
        "total_mismatch_pixels": total,
        "clock_rect_mismatch_pixels": inside,
        "outside_clock_rect_mismatch_pixels": total - inside,
        "diff_bbox": diff_bbox(left, right, width),
        "clock_rect_diff_bbox": diff_bbox(
            left_region, right_region, rect.width,
        ),
    }


def unavailable_mismatch(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "verified": False,
        "total_mismatch_pixels": None,
        "clock_rect_mismatch_pixels": None,
        "outside_clock_rect_mismatch_pixels": None,
        "diff_bbox": None,
        "clock_rect_diff_bbox": None,
        "reason": reason,
    }


def layer_mismatch_report(back: bytes, front: bytes, gram_visible: bytes,
                          lcd: bytes, rect: Rect) -> dict[str, Any]:
    """Compare only layer pairs whose coordinate and level maps are proven."""
    cross_domain = unavailable_mismatch(str(NATIVE_LCD_MAPPING["reason"]))
    return {
        "back_vs_front_gray4": mismatch_metrics(
            back, front, LCD_WIDTH, rect,
        ),
        "front_gray4_vs_gram_visible_gray5": dict(cross_domain),
        "front_gray4_vs_lcd_gray5": dict(cross_domain),
        "gram_visible_vs_lcd_gray5": mismatch_metrics(
            gram_visible, lcd, LCD_WIDTH, rect,
        ),
    }


def coordinate_contract() -> dict[str, Any]:
    return {
        "logical_size": [LCD_WIDTH, LCD_HEIGHT],
        "native": {
            "physical_row_for_logical_y": "119-y",
            "even_x_nibble": "high",
            "levels": "gray4 (0..15)",
        },
        "gram_com1": {
            "controller_line_for_logical_y": "139-y",
            "controller_x_for_logical_x": "x",
            "visible_lines": [20, 139],
            "levels": "gray5 darkness (0 light, 31 dark)",
            "inverse_application": "lcd-gram API applies ST7529 INV and glass polarity",
        },
        "lcd": {
            "row_for_logical_y": "y",
            "column_for_logical_x": "x",
            "levels": "gray5 darkness (0 light, 31 dark)",
            "inverse_application": "lcd API applies ST7529 INV and glass polarity",
        },
        "native_to_lcd": dict(NATIVE_LCD_MAPPING),
    }


def fetch(url: str, source: str = "lcd", base: int = 0,
          size: int = 3600, timeout: float = 10.0) -> dict[str, Any]:
    query = urlencode({"source": source, "base": hex(base), "size": hex(size)})
    with urlopen(f"{url.rstrip('/')}/api/state?{query}", timeout=timeout) as response:
        state = json.load(response)
    if not isinstance(state, dict):
        raise ValueError("Web state is not a JSON object")
    if "error" in state:
        raise ValueError(str(state["error"]))
    return state


def frame_bytes(state: dict[str, Any], expected: int) -> bytes:
    frame = base64.b64decode(str(state.get("frame", "")), validate=True)
    if len(frame) != expected:
        raise ValueError(f"frame is {len(frame)} bytes, expected {expected}")
    return frame


def render_crop(frame: bytes, width: int, rect: Rect, output: Path,
                scale: int = 8) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to render clock captures") from exc
    data = crop(frame, width, rect)
    pixels = bytes(round((31 - (value & 31)) * 255 / 31) for value in data)
    image = Image.frombytes("L", (rect.width, rect.height), pixels)
    image = image.resize(
        (rect.width * scale, rect.height * scale), Image.Resampling.NEAREST,
    )
    image.save(output)


def render_packed(frame: bytes, output: Path, scale: int = 4) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to render guest captures") from exc
    pixels = bytes(255 - value * 17 for value in normalize_native(frame))
    image = Image.frombytes("L", (LCD_WIDTH, LCD_HEIGHT), pixels)
    image = image.resize(
        (LCD_WIDTH * scale, LCD_HEIGHT * scale), Image.Resampling.NEAREST,
    )
    image.save(output)


def capture_layers(url: str, output_dir: Path, index: int, rect: Rect,
                   timeout: float) -> tuple[bytes, bytes, bytes, bytes, str]:
    """Pause and capture guest back/front buffers, controller GRAM, and LCD."""
    control(url, "pause", timeout)
    try:
        lcd_state = fetch(url, timeout=timeout)
        gram_state = fetch(url, "lcd-gram", timeout=timeout)
        back_state = fetch(
            url, "data", BACK_BASE, NATIVE_SIZE, timeout=timeout,
        )
        front_state = fetch(
            url, "data", FRONT_BASE, NATIVE_SIZE, timeout=timeout,
        )
    finally:
        control(url, "resume", timeout)

    lcd = frame_bytes(lcd_state, LCD_WIDTH * LCD_HEIGHT)
    gram = frame_bytes(gram_state, LCD_WIDTH * GRAM_HEIGHT)
    back = frame_bytes(back_state, NATIVE_SIZE)
    front = frame_bytes(front_state, NATIVE_SIZE)
    registers = str(lcd_state.get("registers", ""))
    com = st7529_com_value(registers)
    if com != 1:
        raise ValueError(
            f"logical GRAM normalization requires ST7529 COM=1, got {com!r}"
        )
    lcd_logical = normalize_lcd(lcd)
    gram_visible = normalize_gram_com1(gram)
    back_logical = normalize_native(back)
    front_logical = normalize_native(front)
    mismatches = layer_mismatch_report(
        back_logical, front_logical, gram_visible, lcd_logical, rect,
    )
    prefix = f"{index:02d}"
    (output_dir / f"{prefix}-lcd.gray5").write_bytes(lcd)
    (output_dir / f"{prefix}-lcd-gram.gray5").write_bytes(gram)
    (output_dir / f"{prefix}-lcd-gram-visible.gray5").write_bytes(gram_visible)
    (output_dir / f"{prefix}-back-500000.packed").write_bytes(back)
    (output_dir / f"{prefix}-front-503840.packed").write_bytes(front)
    (output_dir / f"{prefix}-back-logical.gray4").write_bytes(back_logical)
    (output_dir / f"{prefix}-front-logical.gray4").write_bytes(front_logical)
    (output_dir / f"{prefix}-layer-mismatches.json").write_text(
        json.dumps(mismatches, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    (output_dir / f"{prefix}-registers.txt").write_text(
        registers, encoding="utf-8",
    )
    render_lcd(lcd, LCD_WIDTH, LCD_HEIGHT, output_dir / f"{prefix}-lcd.png")
    render_crop(lcd, LCD_WIDTH, rect, output_dir / f"{prefix}-clock.png")
    render_packed(back, output_dir / f"{prefix}-back-500000.png")
    render_packed(front, output_dir / f"{prefix}-front-503840.png")
    return lcd_logical, gram_visible, back_logical, front_logical, registers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8778")
    parser.add_argument(
        "--rect", type=parse_rect, default=parse_rect("195,100,45,20"),
        help="LCD clock rectangle x,y,width,height (default: 195,100,45,20)",
    )
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--changes", type=int, default=1)
    parser.add_argument(
        "--expected-change-period", type=float, default=60.0,
        help=(
            "expected wall-clock seconds between minute changes, used only "
            "for capture-budget reporting (0 disables; default: 60)"
        ),
    )
    parser.add_argument("--request-timeout", type=float, default=10.0)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("tmp") / (
            "np560-clock-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        ),
    )
    args = parser.parse_args()
    if args.poll_interval <= 0 or args.timeout <= 0:
        parser.error("poll interval and timeout must be positive")
    if args.changes <= 0:
        parser.error("changes must be positive")
    if args.expected_change_period < 0:
        parser.error("expected change period cannot be negative")

    budget = capture_budget_report(
        args.timeout, args.changes, args.expected_change_period,
    )
    if budget.get("available") and not budget["request_fits_expected_period"]:
        print(
            "WARNING=capture budget cannot contain the requested number of "
            f"changes at a {args.expected_change_period:g}s period; best-case "
            f"capacity is {budget['best_case_changes_within_timeout']}",
            file=sys.stderr,
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    baseline_time = datetime.now().astimezone()
    (previous_lcd, previous_gram, previous_back, previous_front,
     previous_registers) = capture_layers(
         args.url, args.output_dir, 0, args.rect, args.request_timeout,
     )
    previous_pipeline = parse_clock_raster_pipeline(previous_registers)
    initial_pipeline = previous_pipeline
    previous_clock = crop(previous_lcd, LCD_WIDTH, args.rect)
    records: list[dict[str, Any]] = []
    trigger_races: list[dict[str, Any]] = []
    transient_trigger_total = 0
    capture_attempts = 0
    poll_samples = 0
    capture_started = time.monotonic()
    deadline = capture_started + args.timeout

    while time.monotonic() < deadline and len(records) < args.changes:
        state = fetch(args.url, timeout=args.request_timeout)
        poll_samples += 1
        sampled_lcd = frame_bytes(state, LCD_WIDTH * LCD_HEIGHT)
        sampled_clock = crop(sampled_lcd, LCD_WIDTH, args.rect)
        if sampled_clock == previous_clock:
            time.sleep(args.poll_interval)
            continue

        capture_attempts += 1
        index = len(records) + 1
        trigger_elapsed = time.monotonic() - capture_started
        lcd, gram, back, front, registers = capture_layers(
            args.url, args.output_dir, capture_attempts, args.rect,
            args.request_timeout,
        )
        current_clock = crop(lcd, LCD_WIDTH, args.rect)
        current_pipeline = parse_clock_raster_pipeline(registers)
        pipeline_delta = clock_raster_pipeline_delta(
            previous_pipeline, current_pipeline,
        )
        trigger_matches_capture = sampled_clock == current_clock
        if current_clock == previous_clock:
            # The poll caught a transient state which had returned to the last
            # completed endpoint before the coherent paused capture.  Keep a
            # bounded diagnostic, but do not count it as a completed change.
            transient_trigger_total += 1
            if len(trigger_races) < CLOCK_RASTER_TRACE_SLOTS:
                trigger_races.append({
                    "time": datetime.now().astimezone().isoformat(
                        timespec="seconds",
                    ),
                    "elapsed_seconds": round(trigger_elapsed, 6),
                    "sampled_clock_sha256": hashlib.sha256(
                        sampled_clock,
                    ).hexdigest(),
                    "captured_clock_sha256": hashlib.sha256(
                        current_clock,
                    ).hexdigest(),
                    "sample_to_capture_changed_pixels": changed_pixels(
                        sampled_clock, current_clock,
                    ),
                    "raster_pipeline_delta": pipeline_delta,
                })
            previous_pipeline = current_pipeline
            continue
        lcd_drawn, lcd_cleared = threshold_transitions(
            previous_lcd, lcd, 15,
        )
        gram_drawn, gram_cleared = threshold_transitions(
            previous_gram, gram, 15,
        )
        front_drawn, front_cleared = threshold_transitions(
            previous_front, front, 7,
        )
        record = {
            "index": index,
            "capture_index": capture_attempts,
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "elapsed_seconds": round(trigger_elapsed, 6),
            "lcd_sha256": hashlib.sha256(lcd).hexdigest(),
            "clock_sha256": hashlib.sha256(current_clock).hexdigest(),
            "trigger_clock_sha256": hashlib.sha256(
                sampled_clock,
            ).hexdigest(),
            "trigger_matches_coherent_capture": trigger_matches_capture,
            "trigger_to_capture_changed_pixels": changed_pixels(
                sampled_clock, current_clock,
            ),
            "clock_region": region_metrics(
                previous_lcd, lcd, LCD_WIDTH, args.rect, 15,
                foreground_high=True,
            ),
            "lcd_changed_pixels": changed_pixels(previous_lcd, lcd),
            "lcd_cleared_pixels": lcd_cleared,
            "lcd_drawn_pixels": lcd_drawn,
            "lcd_diff_bbox": diff_bbox(previous_lcd, lcd, LCD_WIDTH),
            "gram_changed_pixels": changed_pixels(previous_gram, gram),
            "gram_cleared_pixels": gram_cleared,
            "gram_drawn_pixels": gram_drawn,
            "gram_diff_bbox": diff_bbox(previous_gram, gram, LCD_WIDTH),
            "gram_clock_region": region_metrics(
                previous_gram, gram, LCD_WIDTH, args.rect, 15,
                foreground_high=True,
            ),
            "back_changed_pixels": changed_pixels(previous_back, back),
            "back_diff_bbox": diff_bbox(previous_back, back, LCD_WIDTH),
            "back_clock_region": region_metrics(
                previous_back, back, LCD_WIDTH, args.rect, 7,
            ),
            "front_changed_pixels": changed_pixels(
                previous_front, front,
            ),
            "front_cleared_pixels": front_cleared,
            "front_drawn_pixels": front_drawn,
            "front_diff_bbox": diff_bbox(
                previous_front, front, LCD_WIDTH,
            ),
            "front_clock_region": region_metrics(
                previous_front, front, LCD_WIDTH, args.rect, 7,
            ),
            "layer_mismatches": layer_mismatch_report(
                back, front, gram, lcd, args.rect,
            ),
            "raster_pipeline_delta": pipeline_delta,
        }
        records.append(record)
        print(json.dumps(record, ensure_ascii=False))
        previous_lcd, previous_gram = lcd, gram
        previous_back, previous_front = back, front
        previous_clock = current_clock
        previous_pipeline = current_pipeline

    elapsed = time.monotonic() - capture_started
    change_times = [float(record["elapsed_seconds"]) for record in records]
    intervals = [
        round(right - left, 6)
        for left, right in zip(change_times, change_times[1:])
    ]
    expected_next = None
    stopped_before_expected_next = None
    if args.expected_change_period > 0 and change_times:
        expected_next = round(
            change_times[-1] + args.expected_change_period, 6,
        )
        stopped_before_expected_next = round(expected_next - elapsed, 6)
    result = {
        "url": args.url,
        "rect": args.rect.__dict__,
        "coordinate_contract": coordinate_contract(),
        "back": {"base": BACK_BASE, "size": NATIVE_SIZE},
        "front": {"base": FRONT_BASE, "size": NATIVE_SIZE},
        "requested_changes": args.changes,
        "captured_changes": len(records),
        "capture_budget": budget,
        "timing": {
            "baseline_capture_time": baseline_time.isoformat(
                timespec="seconds",
            ),
            "elapsed_seconds": round(elapsed, 6),
            "change_elapsed_seconds": change_times,
            "inter_change_intervals_seconds": intervals,
            "expected_next_change_elapsed_seconds": expected_next,
            "seconds_before_expected_next_at_stop": (
                stopped_before_expected_next
            ),
            "poll_samples": poll_samples,
            "coherent_capture_attempts": capture_attempts,
        },
        "endpoint_metric_contract": {
            "scope": "completed-frame endpoints only",
            "proves_clear_before_draw": False,
            "strict_order_source": "raster_pipeline_delta",
        },
        "initial_raster_pipeline": initial_pipeline,
        "transient_trigger_count": transient_trigger_total,
        "retained_transient_triggers": len(trigger_races),
        "dropped_transient_triggers": (
            transient_trigger_total - len(trigger_races)
        ),
        "transient_triggers": trigger_races,
        "records": records,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"CAPTURE={args.output_dir.resolve()}")
    if len(records) != args.changes:
        print(f"TIMEOUT={args.timeout:g}s CHANGES={len(records)}/{args.changes}")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
