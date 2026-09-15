#!/usr/bin/env python3
"""Verify the NP560+ physical Start-key lifecycle on a running Web/QEMU.

The monitor waits for a *completed and stable* guest-rendered root menu,
captures its native LCD frame, presses and releases matrix index 55 (event
0xB0), then records the resident callback/object lifecycle and resulting
visible frame.  Merely entering ``ROOTRENDER`` is not readiness: the guest can
remain on the boot text for seconds after that counter increments.  It never
writes guest RAM or selects a menu in the Web frontend.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from PIL import Image


START_MATRIX_INDEX = 55
START_MATRIX_HIGH = 1 << (START_MATRIX_INDEX - 32)
LCD_OFF = (0xB7, 0xC8, 0xA1)
LCD_ON = (0x24, 0x31, 0x26)
CLOCK_RECT = (180, 102, 240, 120)


def endpoint(root: str, path: str) -> str:
    return f"{root.rstrip('/')}{path}"


def fetch_json(root: str, path: str, timeout: float) -> dict[str, Any]:
    with urlopen(endpoint(root, path), timeout=timeout) as response:
        result = json.load(response)
    if not isinstance(result, dict) or "error" in result:
        raise ValueError(f"invalid Web/QEMU response: {result!r}")
    return result


def state_line(registers: str, name: str) -> str:
    prefix = f"{name}="
    for line in registers.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return "none"


def application_calls(registers: str, name: str) -> int:
    match = re.search(
        rf"(?:APPLICATION_TRACE=|,){re.escape(name)}:(\d+)@", registers
    )
    return int(match.group(1)) if match else 0


def named_count(registers: str, name: str) -> int:
    match = re.search(r"(?:^|\s)COUNT:(\d+)", state_line(registers, name))
    return int(match.group(1)) if match else 0


def parse_matrix_event(registers: str) -> tuple[int, int]:
    """Return the guest matrix-map count and latest translated event."""
    match = re.search(
        r"\bMATRIX_EVENT_MAPS=(\d+)\s+LAST=([0-9a-fA-F]{4})",
        registers,
    )
    if not match:
        return 0, -1
    return int(match.group(1)), int(match.group(2), 16)


def parse_foreground_mode(registers: str) -> dict[str, int | str]:
    line = state_line(registers, "FOREGROUND_MODE")
    match = re.search(
        r"COUNT:(\d+) FROM:([0-9a-fA-F]{2}:[0-9a-fA-F]{4}) "
        r"TARGET:([0-9a-fA-F]{2}:[0-9a-fA-F]{4}) .*?"
        r"MODE:([0-9a-fA-F]{4}) EVENT:([0-9a-fA-F]{4})",
        line,
    )
    if not match:
        return {"count": 0, "from": "00:0000", "target": "00:0000",
                "mode": 0, "event": 0}
    return {
        "count": int(match.group(1)),
        "from": match.group(2).lower(),
        "target": match.group(3).lower(),
        "mode": int(match.group(4), 16),
        "event": int(match.group(5), 16),
    }


def parse_foreground_return(registers: str) -> dict[str, int | str]:
    line = state_line(registers, "FOREGROUND_RETURN")
    match = re.search(
        r"COUNT:(\d+) FROM:([0-9a-fA-F]{2}:[0-9a-fA-F]{4}) "
        r"TARGET:([0-9a-fA-F]{2}:[0-9a-fA-F]{4}) .*?"
        r"RESULT:([0-9a-fA-F]{4})",
        line,
    )
    if not match:
        return {"count": 0, "from": "00:0000", "target": "00:0000",
                "result": 0}
    return {
        "count": int(match.group(1)),
        "from": match.group(2).lower(),
        "target": match.group(3).lower(),
        "result": int(match.group(4), 16),
    }


def parse_indirect_callbacks(registers: str) -> dict[str, object]:
    line = state_line(registers, "INDIRECT_CALLBACK")
    count_match = re.search(r"(?:^|\s)CALLS:(\d+)", line)
    targets = tuple(
        target.lower()
        for target in re.findall(
            r">([0-9a-fA-F]{2}:[0-9a-fA-F]{4})(?:/|$)", line
        )
    )
    return {
        "count": int(count_match.group(1)) if count_match else 0,
        "targets": targets,
    }


def parse_state_import(registers: str) -> dict[str, int | str]:
    """Parse the persistent summary of the latest nonempty state record."""
    line = state_line(registers, "STATE_IMPORT")
    match = re.search(
        r"CALLS:(\d+) NONEMPTY:(\d+) .*?"
        r"INPUT:([0-9a-fA-F,]+) .*?"
        r"COMPARES:(\d+) MATCHES:(\d+) MISMATCHES:(\d+) .*?"
        r"RESULT:([0-9a-fA-F]{4}:[0-9a-fA-F]{4}) "
        r"RETURN:([0-9a-fA-F]{2}:[0-9a-fA-F]{4})",
        line,
    )
    if not match:
        return {
            "calls": 0, "nonempty": 0, "input": "", "compares": 0,
            "matches": 0, "mismatches": 0, "result": "0000:0000",
            "return": "00:0000",
        }
    return {
        "calls": int(match.group(1)),
        "nonempty": int(match.group(2)),
        "input": match.group(3).lower(),
        "compares": int(match.group(4)),
        "matches": int(match.group(5)),
        "mismatches": int(match.group(6)),
        "result": match.group(7).lower(),
        "return": match.group(8).lower(),
    }


def parse_state_import_history(registers: str) -> dict[str, object]:
    """Parse the bounded state-import ring exported by QEMU diagnostics."""
    line = state_line(registers, "STATE_IMPORT_HISTORY")
    count_match = re.search(r"(?:^|\s)COUNT:(\d+)", line)
    entries: list[dict[str, object]] = []
    for match in re.finditer(
        r"#(\d+)/in:([0-9a-fA-F,]+)(.*?)(?=;#\d+/in:|$)", line,
    ):
        tail = match.group(3)
        result_match = re.search(
            r"/result:([0-9a-fA-F]{4}:[0-9a-fA-F]{4})", tail,
        )
        return_match = re.search(
            r"/return:([0-9a-fA-F]{2}:[0-9a-fA-F]{4})", tail,
        )
        entries.append({
            "sequence": int(match.group(1)),
            "input": tuple(
                int(word, 16) for word in match.group(2).split(",")
            ),
            "result": (
                result_match.group(1).lower()
                if result_match else "0000:0000"
            ),
            "return": (
                return_match.group(1).lower()
                if return_match else "00:0000"
            ),
        })
    return {
        "count": int(count_match.group(1)) if count_match else 0,
        "entries": tuple(entries),
    }


def start_event_imported_after(registers: str, sequence: int) -> bool:
    """Return true once a completed physical Start event is in the ring."""
    history = parse_state_import_history(registers)
    for entry in history["entries"]:
        words = entry["input"]
        if (
            entry["sequence"] > sequence and
            len(words) > 4 and words[0] == 0x0003 and words[4] == 0x00B0 and
            entry["result"] == "0032:f15c" and
            entry["return"] == "28:84d0"
        ):
            return True
    return False


def diagnostic_failure(registers: str) -> str | None:
    for name in ("ROM_MISSING", "INVALID_CONTROL", "UNSUPPORTED"):
        value = state_line(registers, name)
        if value != "none" and not value.startswith("none "):
            return f"{name}={value}"
    return None


def set_matrix(root: str, high: int, timeout: float) -> None:
    payload = json.dumps({
        "state": 0,
        "code": 0,
        "matrix_low": 0,
        "matrix_high": high & 0xFFFFFFFF,
    }).encode()
    request = Request(
        endpoint(root, "/api/key"), data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        response.read()


def decode_gray5(state: dict[str, Any]) -> tuple[int, int, bytes]:
    if state.get("format") != "gray5":
        raise ValueError(f"unexpected LCD format: {state.get('format')!r}")
    width = int(state["width"])
    height = int(state["height"])
    frame = base64.b64decode(state["frame"], validate=True)
    if len(frame) != width * height:
        raise ValueError(f"unexpected LCD byte count: {len(frame)}")
    return width, height, frame


def root_frame_complete(frame: bytes, width: int, height: int) -> bool:
    """Recognise the completed 240x120 native desktop chrome.

    The test uses structural LCD rows rather than OCR or a host-side menu
    state: the completed desktop has a dark top border, a uniform toolbar
    separator, a dark lower border and an opposite-polarity final scanline.
    Requiring glyph transitions in both the toolbar and left menu keeps the
    early, text-only boot frame from satisfying the predicate.
    """
    if (width, height) != (240, 120) or len(frame) != width * height:
        return False

    def row(y: int) -> bytes:
        return frame[y * width:(y + 1) * width]

    def transitions(values: bytes) -> int:
        return sum(a != b for a, b in zip(values, values[1:]))

    top = row(0)
    toolbar_separator = row(22)
    lower_border = row(118)
    final_row = row(119)
    if any(len(set(values)) != 1 for values in (
        top, toolbar_separator, lower_border, final_row,
    )):
        return False
    if abs(top[0] - final_row[0]) < 16:
        return False
    if lower_border[0] != top[0]:
        return False
    return transitions(row(10)) >= 40 and transitions(row(40)) >= 8


def static_frame_digest(frame: bytes, width: int, height: int) -> str:
    """Hash the visible frame while excluding the independently ticking clock."""
    x0, y0, x1, y1 = CLOCK_RECT
    stable = bytearray()
    for y in range(height):
        start = y * width
        if y0 <= y < y1:
            stable.extend(frame[start:start + x0])
            stable.extend(frame[start + x1:start + width])
        else:
            stable.extend(frame[start:start + width])
    return hashlib.sha256(stable).hexdigest()


def static_pixel_difference(
    before: bytes, after: bytes, width: int, height: int,
) -> int:
    if len(before) != len(after) or len(before) != width * height:
        raise ValueError("frames have incompatible dimensions")
    x0, y0, x1, y1 = CLOCK_RECT
    return sum(
        old != new
        for index, (old, new) in enumerate(zip(before, after))
        if not (y0 <= index // width < y1 and x0 <= index % width < x1)
    )


def menu_panel_right_edge(frame: bytes, width: int, height: int) -> int | None:
    """Locate the persistent vertical edge of the left menu panel."""
    if (width, height) != (240, 120) or len(frame) != width * height:
        return None
    y0, y1 = 23, 101
    for x in range(24, 90):
        column = bytes(frame[y * width + x] for y in range(y0, y1))
        if Counter(column).most_common(1)[0][1] >= (y1 - y0 - 3):
            return x
    return None


def is_start_popup_frame(frame: bytes, width: int, height: int) -> bool:
    """Distinguish the narrow five-row Start popup from the root app list."""
    edge = menu_panel_right_edge(frame, width, height)
    return edge is not None and 32 <= edge <= 42


def save_frame(state: dict[str, Any], prefix: Path, label: str,
               scale: int) -> tuple[Path, Path]:
    width, height, frame = decode_gray5(state)
    raw_path = Path(f"{prefix}-{label}.gray5")
    png_path = Path(f"{prefix}-{label}.png")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(frame)
    pixels = []
    for raw in frame:
        level = (raw & 31) / 31
        pixels.append(tuple(
            round(off + (on - off) * level)
            for off, on in zip(LCD_OFF, LCD_ON)
        ))
    image = Image.new("RGB", (width, height))
    image.putdata(pixels)
    if scale > 1:
        image = image.resize(
            (width * scale, height * scale), Image.Resampling.NEAREST
        )
    image.save(png_path)
    return raw_path, png_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8780")
    parser.add_argument("--ready-timeout", type=float, default=900.0)
    parser.add_argument("--transition-timeout", type=float, default=90.0)
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument(
        "--press-seconds", type=float, default=0.35,
        help=(
            "maximum physical hold time; release immediately after the "
            "first guest 0xB0 matrix mapping to avoid key-repeat pollution"
        ),
    )
    parser.add_argument("--ready-stable-seconds", type=float, default=1.0)
    parser.add_argument("--result-stable-seconds", type=float, default=1.0)
    parser.add_argument(
        "--post-import-observe-seconds", type=float, default=15.0,
        help=(
            "after the Start record is imported, stop this many seconds "
            "later if no visible transition begins"
        ),
    )
    parser.add_argument(
        "--output-prefix", type=Path,
        default=Path("tmp/np560-start-menu"),
    )
    parser.add_argument(
        "--observe-only", action="store_true",
        help="capture the stable root state without injecting the Start key",
    )
    parser.add_argument("--scale", type=int, default=4)
    args = parser.parse_args()

    deadline = time.monotonic() + args.ready_timeout
    registers = ""
    before_state: dict[str, Any] | None = None
    before_frame = b""
    before_digest = ""
    stable_since: float | None = None
    while time.monotonic() < deadline:
        try:
            diagnostics = fetch_json(args.root, "/api/diagnostics", 5.0)
            registers = str(diagnostics.get("registers", ""))
            failure = diagnostic_failure(registers)
            if failure:
                print(f"INCIDENT before-start {failure}")
                return 2
            if application_calls(registers, "ROOTRENDER"):
                candidate = fetch_json(args.root, "/api/state", 10.0)
                width, height, frame = decode_gray5(candidate)
                if root_frame_complete(frame, width, height):
                    digest = static_frame_digest(frame, width, height)
                    now = time.monotonic()
                    if digest != before_digest:
                        before_digest = digest
                        stable_since = now
                    elif (stable_since is not None and
                          now - stable_since >= args.ready_stable_seconds):
                        before_state = candidate
                        before_frame = frame
                        break
                else:
                    before_digest = ""
                    stable_since = None
        except URLError:
            # The Web process may be alive a fraction of a second before its
            # listening socket is bound.  Treat that as startup, not failure.
            pass
        time.sleep(max(args.interval, 0.02))
    else:
        print("TIMEOUT waiting for completed stable guest root menu")
        return 2

    assert before_state is not None
    before_render = application_calls(registers, "ROOTRENDER")
    before_mode = named_count(registers, "FOREGROUND_MODE")
    before_return = named_count(registers, "FOREGROUND_RETURN")
    before_callback = parse_indirect_callbacks(registers)
    before_history = parse_state_import_history(registers)
    raw, png = save_frame(before_state, args.output_prefix, "before", args.scale)
    before_edge = menu_panel_right_edge(before_frame, 240, 120)
    print(
        f"READY ROOTRENDER={before_render} PANEL_EDGE={before_edge} "
        f"CALLBACKS={before_callback['count']} FRAME={raw} PNG={png}"
    )

    if args.observe_only:
        print(f"STATE_IMPORT {state_line(registers, 'STATE_IMPORT')}")
        print(
            "STATE_IMPORT_HISTORY "
            f"{state_line(registers, 'STATE_IMPORT_HISTORY')}"
        )
        print(f"START_CALLBACK {state_line(registers, 'START_CALLBACK')}")
        return 0

    before_matrix_maps, _ = parse_matrix_event(registers)
    mapped = False
    after_matrix_maps = before_matrix_maps
    after_matrix_event = -1
    set_matrix(args.root, START_MATRIX_HIGH, 5.0)
    try:
        press_deadline = time.monotonic() + max(args.press_seconds, 0.05)
        while time.monotonic() < press_deadline:
            key_status = fetch_json(args.root, "/api/key-status", 5.0)
            after_matrix_maps = int(key_status.get("maps", 0))
            after_matrix_event = int(key_status.get("event", -1))
            if (after_matrix_maps > before_matrix_maps and
                    after_matrix_event == 0x00B0):
                mapped = True
                break
            time.sleep(0.005)
    finally:
        set_matrix(args.root, 0, 5.0)
    print(
        f"KEY M55 EVENT={after_matrix_event:04X} "
        f"MAPS={before_matrix_maps}->{after_matrix_maps} released"
    )
    if not mapped:
        print("INCIDENT Start key was not mapped before the hold timeout")
        return 2

    deadline = time.monotonic() + args.transition_timeout
    last_registers = registers
    after_state = before_state
    after_frame = before_frame
    result_digest = before_digest
    result_stable_since: float | None = None
    import_seen_since: float | None = None
    while time.monotonic() < deadline:
        diagnostics = fetch_json(args.root, "/api/diagnostics", 5.0)
        last_registers = str(diagnostics.get("registers", ""))
        failure = diagnostic_failure(last_registers)
        if failure:
            print(f"INCIDENT after-start {failure}")
            return 2
        candidate = fetch_json(args.root, "/api/state", 10.0)
        width, height, frame = decode_gray5(candidate)
        difference = static_pixel_difference(
            before_frame, frame, width, height,
        )
        import_hit = start_event_imported_after(
            last_registers, int(before_history["count"]),
        )
        now = time.monotonic()
        if import_hit and import_seen_since is None:
            import_seen_since = now
        if import_hit and difference >= 50:
            digest = static_frame_digest(frame, width, height)
            after_state = candidate
            after_frame = frame
            if digest != result_digest:
                result_digest = digest
                result_stable_since = now
            elif (result_stable_since is not None and
                  now - result_stable_since >= args.result_stable_seconds):
                break
        elif (import_seen_since is not None and
              now - import_seen_since >= args.post_import_observe_seconds):
            after_state = candidate
            after_frame = frame
            break
        time.sleep(max(args.interval, 0.02))

    mode = parse_foreground_mode(last_registers)
    returned = parse_foreground_return(last_registers)
    callback = parse_indirect_callbacks(last_registers)
    next_render = application_calls(last_registers, "ROOTRENDER")
    difference = static_pixel_difference(before_frame, after_frame, 240, 120)
    panel_edge = menu_panel_right_edge(after_frame, 240, 120)
    start_popup = is_start_popup_frame(after_frame, 240, 120)
    print(
        "MODE "
        f"COUNT={mode['count']} FROM={mode['from']} TARGET={mode['target']} "
        f"MODE={int(mode['mode']):04x} EVENT={int(mode['event']):04x}"
    )
    print(
        "RETURN "
        f"COUNT={returned['count']} FROM={returned['from']} "
        f"TARGET={returned['target']} RESULT={int(returned['result']):04x}"
    )
    print(f"ROOTRENDER {before_render}->{next_render}")
    print(
        f"CALLBACKS {before_callback['count']}->{callback['count']} "
        f"TARGETS={','.join(callback['targets']) or 'none'}"
    )
    print(
        f"VISIBLE STATIC_DIFF={difference} PANEL_EDGE={panel_edge} "
        f"START_POPUP={int(start_popup)}"
    )
    print(
        "CONTEXT_RETURN "
        f"{state_line(last_registers, 'FOREGROUND_CONTEXT_RETURN')}"
    )
    print(
        "OWNER_RETURN "
        f"{state_line(last_registers, 'FOREGROUND_OWNER_RETURN')}"
    )
    print(
        "RESOURCE_COUNT_WRITES "
        f"{state_line(last_registers, 'RESOURCE_COUNT_WRITES')}"
    )
    print(f"MENU_PATH_WRITES {state_line(last_registers, 'MENU_PATH_WRITES')}")
    print(f"ROOT_OBJECT_DATA {state_line(last_registers, 'ROOT_OBJECT_DATA')}")
    print(f"ROOT_EXIT_STATE {state_line(last_registers, 'ROOT_EXIT_STATE')}")
    print(f"STATE_IMPORT {state_line(last_registers, 'STATE_IMPORT')}")
    print(
        "B0_RECORD="
        f"{int(start_event_imported_after(last_registers, int(before_history['count'])))}"
    )
    print(
        "STATE_IMPORT_HISTORY "
        f"{state_line(last_registers, 'STATE_IMPORT_HISTORY')}"
    )
    print(f"START_CALLBACK {state_line(last_registers, 'START_CALLBACK')}")

    raw, png = save_frame(after_state, args.output_prefix, "after", args.scale)
    print(f"AFTER FRAME={raw} PNG={png}")

    expected = (
        start_event_imported_after(
            last_registers, int(before_history["count"]),
        ) and
        difference >= 50 and
        start_popup
    )
    return 0 if expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
