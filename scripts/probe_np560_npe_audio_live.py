"""Sample Web DAC audio and NPE HLE counters during an isolated route.

Run this before pressing the NPE launch key. Optional WAV output contains
observed DAC frames, not host-generated or decoded reference PCM. A key-pulse
HTTP acknowledgement alone does not prove guest delivery. Never attach this
diagnostic to a user instance.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import struct
import time
import wave
from pathlib import Path
from urllib.request import Request, urlopen


def get_json(url: str) -> dict:
    with urlopen(url, timeout=3) as response:
        return json.load(response)


def sample(root: str) -> tuple[dict, bytes, dict]:
    packet = get_json(root + "/api/audio")
    raw = base64.b64decode(packet["pcm"], validate=True)
    values = struct.unpack("<%dh" % (len(raw) // 2), raw)
    return {
        "time": time.time(),
        "monotonic_time": time.monotonic(),
        "generation": packet["generation"],
        "first_frame": packet["first_frame"],
        "next_frame": packet["next_frame"],
        "enabled": packet["enabled"],
        "running": packet["request_clock"]["running"],
        "writes": packet["writes"],
        "nonzero_samples": sum(value != 0 for value in values),
        "peak_abs": max(map(abs, values), default=0),
    }, raw, packet


def control_transitions(packet: dict, after_sequence: int | None,
                        ) -> tuple[int, list[dict], bool]:
    """Collect new guest DAC enable edges from the bounded device event ring.

    The first snapshot establishes a boundary and does not replay old edges.
    A ring overrun is explicit: missing events must not be interpreted as a
    continuous enabled interval.
    """
    next_sequence = int(packet["control_event_next"])
    if after_sequence is None:
        return next_sequence - 1, [], False
    events = packet["control_events"]
    unseen = [event for event in events
              if int(event["sequence"]) > after_sequence]
    missed = (next_sequence <= after_sequence or
              (next_sequence > after_sequence + 1 and
               (not unseen or int(unseen[0]["sequence"]) > after_sequence + 1)))
    edges = []
    for event in unseen:
        if int(event["reg"]) != 0x72:
            continue
        old_enabled = (int(event["old_value"]) & 0x8001) == 1
        new_enabled = (int(event["value"]) & 0x8001) == 1
        if old_enabled == new_enabled:
            continue
        edges.append({key: event[key] for key in (
            "sequence", "virtual_ns", "frame", "pc", "old_value",
            "value", "enabled", "running")})
    return next_sequence - 1, edges, missed


def guest_dac_off_windows(edges: list[dict], gaps: list[dict]) -> list[dict]:
    """Pair observed guest stop/start edges without crossing lost history."""
    windows = []
    off = None
    gap_at = {int(gap["after_sequence"]) for gap in gaps}
    for edge in edges:
        if off is not None and int(edge["sequence"]) <= int(off["sequence"]):
            off = None
        if any(off is not None and off["sequence"] <= gap < edge["sequence"]
               for gap in gap_at):
            off = None
        if not edge["enabled"]:
            off = edge
        elif off is not None:
            frames = int(edge["frame"]) - int(off["frame"])
            windows.append({
                "stop_sequence": off["sequence"],
                "start_sequence": edge["sequence"],
                "stop_pc": off["pc"],
                "start_pc": edge["pc"],
                "frames": frames,
                "virtual_seconds": frames / 48000 if frames >= 0 else None,
            })
            off = None
    return windows


def map_advance(before: dict, after: dict) -> dict:
    """Report a guest map-counter change without attributing unrelated keys."""
    old = int(before["maps"])
    new = int(after["maps"])
    return {
        "guest_maps_before": old,
        "guest_maps_after": new,
        "guest_maps_advanced": new > old,
        "guest_last_event": after.get("event"),
        "attribution": "unverified if other keys were pressed during capture",
    }


def hle_count_delta(before: dict, after: dict) -> dict | None:
    """Compare the six resident audio calls without interpreting their ABI."""
    pattern = r"\bcalls=([0-9]+(?:,[0-9]+){5})\b"
    old = re.search(pattern, str(before.get("state", "")))
    new = re.search(pattern, str(after.get("state", "")))
    if old is None or new is None:
        return None
    old_counts = [int(value) for value in old.group(1).split(",")]
    new_counts = [int(value) for value in new.group(1).split(",")]
    return {
        "order": ["ACD8", "B6DE", "B816", "B7AA", "B84E", "AD92"],
        "before": old_counts,
        "after": new_counts,
        "delta": [new_value - old_value for old_value, new_value
                  in zip(old_counts, new_counts)],
    }


def npe_game_control_state(diagnostics: dict) -> dict | None:
    """Extract the bounded guest-write trace without inferring game intent."""
    lines = str(diagnostics.get("registers", "")).splitlines()
    line = next((item for item in lines
                 if item.startswith("NPE_GAME_CONTROL=")), None)
    if line is None:
        return None
    match = re.search(
        r"LIVE:m([0-9a-f]{4})/g([0-9a-f]{4})/t([0-9a-f]{4})"
        r" .*? WRITES:(\d+) TRACE:(.*)$", line)
    if match is None:
        return {"raw": line, "parsed": False}
    return {
        "raw": line,
        "parsed": True,
        "live": dict(zip(("mode", "gate", "trigger"),
                         (int(value, 16) for value in match.groups()[:3]))),
        "write_count": int(match.group(4)),
        "recent_writes": [item for item in match.group(5).split(";") if item],
    }


def npe_load_rom_state(diagnostics: dict) -> dict | None:
    """Summarize exact successful-load branch resident calls, if available."""
    line = next((item for item in
                 str(diagnostics.get("registers", "")).splitlines()
                 if item.startswith("NPE_LOAD_ROM=")), None)
    if line is None:
        return None
    match = re.search(
        r"ACTIVE:(\d+) ENTER:(\d+) EXIT:(\d+) READ:(\d+)/R([0-9a-f]{4}) "
        r"SLOT:(\d+) FLAGS:([0-9a-f]{4}),([0-9a-f]{4}),([0-9a-f]{4}) "
        r"TRIGGER:([0-9a-f]{4})>([0-9a-f]{4}) CALLS:(\d+) "
        r"UNIQUE:(\d+) TRACE:(.*)$", line)
    if match is None:
        return {"raw": line, "parsed": False}
    values = match.groups()
    return {
        "raw": line,
        "parsed": True,
        "active": bool(int(values[0])),
        "entries": int(values[1]),
        "exits": int(values[2]),
        "read_returns": int(values[3]),
        "read_result": int(values[4], 16),
        "slot": int(values[5]),
        "slot_flags": [int(value, 16) for value in values[6:9]],
        "trigger_before": int(values[9], 16),
        "trigger_after": int(values[10], 16),
        "rom_calls": int(values[11]),
        "unique_rom_targets": int(values[12]),
        "rom_targets": [item for item in values[13].split(";") if item],
    }


def audio_clock_progress(items: list[dict], gaps: list) -> dict:
    """Measure active DAC media time against monotonic wall time.

    The counter runs even with the DAC disabled, so an inactive or incomplete
    window must not be reported as game-audio speed. This is not a CPU or
    browser playback benchmark.
    """
    samples = [item for item in items if all(key in item for key in (
        "monotonic_time", "generation", "next_frame", "enabled", "running"))]
    active = len(samples) >= 2 and all(
        item["enabled"] and item["running"] for item in samples)
    active_count = sum(bool(item["enabled"] and item["running"])
                       for item in samples)
    continuous = (len(samples) == len(items) and not gaps and
                  len({item["generation"] for item in samples}) == 1)
    wall = (samples[-1]["monotonic_time"] - samples[0]["monotonic_time"]
            if len(samples) >= 2 else 0.0)
    frames = (samples[-1]["next_frame"] - samples[0]["next_frame"]
              if len(samples) >= 2 else 0)
    measured_clock = continuous and wall > 0 and frames >= 0
    frame_clock_rate = frames / 48000 / wall if measured_clock else None
    return {
        "sample_count": len(samples),
        "active_sample_count": active_count,
        "active_entire_window": active,
        "continuous": continuous,
        "wall_seconds": wall if len(samples) >= 2 else None,
        "dac_media_seconds": frames / 48000 if len(samples) >= 2 and frames >= 0 else None,
        "frame_clock_rate": frame_clock_rate,
        "dac_media_rate": frame_clock_rate if active else None,
        "scope": "frame-clock rate is reported across disabled samples; active DAC rate requires all samples enabled; neither certifies CPU or browser playback speed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8891")
    parser.add_argument("--duration", type=float, default=15)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--trigger-matrix-index", type=int,
                        help="pulse this physical matrix position after the first audio sample")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wav-output", type=Path,
                        help="save unique observed DAC frames as stereo 48 kHz WAV if gap-free")
    parser.add_argument("--capture-npe-control", action="store_true",
                        help="capture the read-only 7934/7A50/7AB4 write ring before and after")
    args = parser.parse_args()
    root = args.root.rstrip("/")
    if args.output.exists() or args.duration <= 0 or args.interval <= 0:
        parser.error("output must not exist, and duration/interval must be positive")
    if args.wav_output is not None and args.wav_output.exists():
        parser.error("WAV output already exists")
    if args.trigger_matrix_index is not None and not 0 <= args.trigger_matrix_index < 64:
        parser.error("trigger matrix index must be in 0..63")
    items = []
    captured = bytearray()
    last_frame = None
    generation = None
    gaps = []
    trigger = None
    last_control_sequence = None
    dac_control_transitions = []
    control_coverage_gaps = []
    npe_hle_before = get_json(root + "/api/npe-hle-state")
    diagnostic_before = (get_json(root + "/api/diagnostics")
                         if args.capture_npe_control else None)
    npe_control_before = (npe_game_control_state(diagnostic_before)
                          if diagnostic_before is not None else None)
    npe_load_before = (npe_load_rom_state(diagnostic_before)
                       if diagnostic_before is not None else None)
    deadline = time.monotonic() + args.duration
    while time.monotonic() < deadline:
        try:
            item, raw, packet = sample(root)
            items.append(item)
            previous_sequence = last_control_sequence
            last_control_sequence, edges, missed = control_transitions(
                packet, last_control_sequence)
            dac_control_transitions.extend(edges)
            if missed:
                control_coverage_gaps.append({
                    "after_sequence": previous_sequence,
                    "next_sequence": packet["control_event_next"],
                })
            if generation is None:
                generation = item["generation"]
            if generation != item["generation"]:
                gaps.append("audio generation changed")
            elif last_frame is None:
                captured.extend(raw)
                last_frame = item["next_frame"]
            elif item["first_frame"] > last_frame:
                gaps.append([last_frame, item["first_frame"]])
                last_frame = item["next_frame"]
            elif item["next_frame"] > last_frame:
                captured.extend(raw[(last_frame - item["first_frame"]) * 4:])
                last_frame = item["next_frame"]
        except (OSError, ValueError, KeyError) as error:
            items.append({"time": time.time(), "error": str(error)})
        if trigger is None and args.trigger_matrix_index is not None:
            before = get_json(root + "/api/key-status")
            request = Request(root + "/api/key-pulse",
                              data=json.dumps({"matrix_index": args.trigger_matrix_index}).encode(),
                              headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=3) as response:
                trigger = json.load(response)
            trigger["guest_maps_before"] = int(before["maps"])
            trigger["meaning"] = "HTTP transport acceptance only; inspect guest_maps_advanced"
        time.sleep(args.interval)
    if trigger is not None:
        after = get_json(root + "/api/key-status")
        trigger.update(map_advance({"maps": trigger["guest_maps_before"]}, after))
    npe_hle_after = get_json(root + "/api/npe-hle-state")
    diagnostic_after = (get_json(root + "/api/diagnostics")
                        if args.capture_npe_control else None)
    npe_control_after = (npe_game_control_state(diagnostic_after)
                         if diagnostic_after is not None else None)
    npe_load_after = (npe_load_rom_state(diagnostic_after)
                      if diagnostic_after is not None else None)
    report = {
        "schema": "np560-npe-audio-live-v1",
        "samples": items,
        "nonzero_packets": sum(item.get("nonzero_samples", 0) > 0 for item in items),
        "max_peak_abs": max((item.get("peak_abs", 0) for item in items), default=0),
        "npe_hle": npe_hle_after,
        "npe_hle_before": npe_hle_before,
        "npe_hle_call_delta": hle_count_delta(npe_hle_before, npe_hle_after),
        "npe_game_control_before": npe_control_before,
        "npe_game_control_after": npe_control_after,
        "npe_load_rom_before": npe_load_before,
        "npe_load_rom_after": npe_load_after,
        "npe_game_control_write_delta": (
            npe_control_after["write_count"] - npe_control_before["write_count"]
            if npe_control_before and npe_control_after and
            npe_control_before.get("parsed") and
            npe_control_after.get("parsed") else None),
        "trigger": trigger,
        "captured_pcm_bytes": len(captured),
        "capture_gaps": gaps,
        "audio_clock_progress": audio_clock_progress(items, gaps),
        "dac_control_transitions": dac_control_transitions,
        "dac_control_coverage_gaps": control_coverage_gaps,
        "guest_dac_off_windows": guest_dac_off_windows(
            dac_control_transitions, control_coverage_gaps),
    }
    if args.wav_output is not None and not gaps:
        args.wav_output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(args.wav_output), "wb") as output:
            output.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
            output.writeframes(captured)
        report["wav_output"] = str(args.wav_output.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("nonzero_packets", "max_peak_abs", "npe_hle")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
