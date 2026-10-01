#!/usr/bin/env python3
"""Replay a bounded NP560+ physical-matrix route through the Web bridge.

Every step is expressed as ``LABEL:INDEX:EVENT[:OBSERVATION]``.  Ordinary
application events use the default ``map`` observation and must reach the
guest's 28:F6DE completion slot.  Firmware-consumed status keys use
``candidate`` and must appear in the original 28:F4A4 worker's current/previous
event slots.  The probe presses one real 8x8 matrix position, observes the
selected read-only boundary, captures failures while the key is still held,
releases the position, and for ordinary events waits for 28:F6DE delivery plus
either the root foreground consumer at 20:2E9E or the modal consumer at
1E:F8E4 before presenting the next physical edge.  It then captures the native
LCD/API state.  It never writes guest RAM or invokes a host-side menu action.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class RouteStep:
    label: str
    matrix_index: int
    expected_event: int
    observation: str = "map"
    require_foreground_ack: bool = True


OBSERVATIONS = frozenset(("map", "candidate"))

# This active-table result deliberately does not traverse ordinary 28:F6DE.
# 0x8C is the proven guest-consumed annunciator toggle.  Although 0xFFFF is
# the table's reserved value, live guest execution still maps and returns it,
# so it remains part of the ordinary delivery classification.
CANDIDATE_ONLY_EVENTS = frozenset((0x8C,))

# Exact active-table result at source 4F:2AB2, indexed by the raw 8x8 matrix
# position returned from 2E:5F28.  The reserved 0xFFFF entry remains part of
# the physical sweep so every row/column intersection is exercised.
ACTIVE_MATRIX_EVENTS = (
    0x65, 0x64, 0x71, 0x77, 0x8E, 0xFFFF, 0x78, 0xC0,
    0x72, 0x66, 0x61, 0x94, 0xE0, 0xE6, 0x63, 0x8D,
    0x74, 0x67, 0x73, 0x92, 0x85, 0x90, 0x76, 0x8B,
    0x79, 0x68, 0x8C, 0x95, 0x84, 0x81, 0x62, 0x88,
    0x75, 0x6A, 0x7A, 0x97, 0xE9, 0x83, 0x6E, 0x8A,
    0x69, 0x6B, 0xB8, 0xBF, 0xEA, 0x80, 0x6D, 0x89,
    0x6F, 0x6C, 0xEE, 0xB7, 0xE1, 0x86, 0x20, 0xB0,
    0x70, 0xE3, 0x7B, 0xB4, 0xE2, 0x82, 0xE7, 0x8F,
)


def parse_step(value: str) -> RouteStep:
    observation = "map"
    try:
        extended = value.rsplit(":", 3)
        if len(extended) == 4 and extended[-1].lower() in OBSERVATIONS:
            label, index_text, event_text, observation = extended
            observation = observation.lower()
        else:
            label, index_text, event_text = value.rsplit(":", 2)
        index = int(index_text, 0)
        event = int(event_text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "step must be LABEL:INDEX:EVENT[:map|candidate], for example "
            "right:29:0x81 or status:26:0x8c:candidate"
        ) from error
    if not label:
        raise argparse.ArgumentTypeError("step label must not be empty")
    if not 0 <= index < 64:
        raise argparse.ArgumentTypeError("matrix index must be in 0..63")
    if not 0 <= event <= 0xFFFF:
        raise argparse.ArgumentTypeError("expected event must be 16-bit")
    return RouteStep(
        label, index, event, observation,
        require_foreground_ack=(observation == "map"),
    )


def matrix_masks(index: int) -> tuple[int, int]:
    if not 0 <= index < 64:
        raise ValueError("matrix index must be in 0..63")
    if index < 32:
        return 1 << index, 0
    return 0, 1 << (index - 32)


def safe_label(label: str) -> str:
    rendered = re.sub(r"[^0-9A-Za-z._-]+", "-", label).strip("-._")
    return rendered or "step"


def diagnostic_failure(registers: str) -> str | None:
    for name in ("ROM_MISSING", "INVALID_CONTROL", "UNSUPPORTED"):
        match = re.search(rf"(?m)^{name}=([^\r\n]+)", registers)
        if match and not match.group(1).startswith("none"):
            return f"{name}={match.group(1)}"
    return None


def matrix_rearm_state(registers: str, reads_before: int) -> tuple[bool, int]:
    """Return whether the released matrix has been observed by guest scanning."""
    reads_match = re.search(r"\bMATRIX_READS:(\d+)\b", registers)
    matrix_match = re.search(
        r"(?m)^KEY_STATE=.*\bKEY_MATRIX=([0-9A-Fa-f]{8}):([0-9A-Fa-f]{8})\b",
        registers,
    )
    gate_match = re.search(r"(?m)^KEY_GUEST=.*\b2A5C:([0-9A-Fa-f]{4})\b", registers)
    columns_match = re.search(r"\bF160:([0-9A-Fa-f]{4})\b", registers)
    if (reads_match is None or matrix_match is None or gate_match is None
            or columns_match is None):
        return False, reads_before
    reads = int(reads_match.group(1), 10)
    released = int(matrix_match.group(1), 16) == 0 and int(
        matrix_match.group(2), 16
    ) == 0
    gate_clear = int(gate_match.group(1), 16) == 0
    columns_released = (int(columns_match.group(1), 16) & 0xFF) == 0xFF
    return (
        released and gate_clear and columns_released and reads > reads_before,
        reads,
    )


def key_status_rearm_state(
    status: dict[str, Any], reads_before: int,
) -> tuple[bool, int] | None:
    """Use the bounded QOM snapshot when the current backend exposes it."""
    if "matrix_reads" not in status or "matrix_rearmed" not in status:
        return None
    reads_after = int(status["matrix_reads"])
    return (
        bool(status["matrix_rearmed"]) and reads_after > reads_before,
        reads_after,
    )


def raise_if_key_status_faulted(web: WebBridge, status: dict[str, Any]) -> None:
    if not bool(status.get("faulted", False)):
        return
    diagnostics = web.get_json("/api/diagnostics")
    registers = str(diagnostics.get("registers", ""))
    raise RuntimeError(
        diagnostic_failure(registers) or "guest faulted during key delivery"
    )


def key_delivery_state(
    status: dict[str, Any],
    *,
    maps_before: int,
    acknowledgements_before: int,
    modal_acknowledgements_before: int = 0,
    expected_event: int,
) -> tuple[bool, bool, str | None]:
    """Report exact ordinary-map and original guest-consumer boundaries."""
    mapped = (
        int(status.get("maps", 0)) > maps_before
        and int(status.get("event", -1)) == expected_event
    )
    foreground_acknowledged = (
        int(status.get("acknowledgements", 0)) > acknowledgements_before
        and int(status.get("acknowledgement", -1)) == expected_event
    )
    modal_acknowledged = (
        int(status.get("modal_acknowledgements", 0)) >
        modal_acknowledgements_before
        and int(status.get("modal_acknowledgement", -1)) == expected_event
    )
    acknowledgement_path = (
        "foreground" if foreground_acknowledged else
        "modal" if modal_acknowledged else None
    )
    return mapped, acknowledgement_path is not None, acknowledgement_path


def held_counter_summary(
    before: dict[str, Any], held: dict[str, Any],
) -> dict[str, int]:
    """Return bounded guest event deltas observed during one physical hold."""
    fields = (
        "candidates", "maps", "acknowledgements", "modal_acknowledgements",
    )
    return {
        f"{name}_during_hold": max(
            0, int(held.get(name, 0)) - int(before.get(name, 0))
        )
        for name in fields
    }


KEY_COUNTER_FIELDS = (
    "candidates", "maps", "acknowledgements", "modal_acknowledgements",
)


def key_counter_signature(status: dict[str, Any]) -> tuple[int, ...]:
    """Return the atomic counters that identify a new input-pipeline edge."""
    return tuple(int(status.get(name, 0)) for name in KEY_COUNTER_FIELDS)


def key_counter_timeline_point(
    before: dict[str, Any], status: dict[str, Any], elapsed: float,
) -> dict[str, Any]:
    """Render one bounded status transition relative to the press baseline."""
    point: dict[str, Any] = {"elapsed_seconds": round(elapsed, 6)}
    for name in KEY_COUNTER_FIELDS:
        absolute = int(status.get(name, 0))
        point[name] = absolute
        point[f"{name}_delta"] = max(
            0, absolute - int(before.get(name, 0)),
        )
    for name in ("candidate", "event", "acknowledgement",
                 "modal_acknowledgement"):
        if name in status:
            point[name] = int(status[name])
    if "matrix_reads" in status:
        point["matrix_reads"] = int(status["matrix_reads"])
        point["matrix_reads_delta"] = max(
            0,
            int(status["matrix_reads"]) - int(before.get("matrix_reads", 0)),
        )
    if "virtual_time_ns" in status and "virtual_time_ns" in before:
        point["virtual_time_ns"] = int(status["virtual_time_ns"])
        point["virtual_elapsed_ns"] = int(status["virtual_time_ns"]) - int(before["virtual_time_ns"])
    return point


def selector_candidate_state(
    registers: str,
    *,
    count_before: int,
    expected_event: int,
) -> tuple[bool, int, dict[str, int] | None]:
    """Find a newly written key-completion current/previous event slot."""
    line = re.search(
        r"(?m)^SELECTOR_STATE_WRITES=COUNT:(\d+) TRACE=([^\r\n]*)",
        registers,
    )
    if line is None:
        return False, count_before, None
    count = int(line.group(1), 10)
    writes = [
        {
            "pc": int(match.group(1).replace(":", ""), 16),
            "address": int(match.group(2), 16),
            "old": int(match.group(3), 16),
            "new": int(match.group(4), 16),
            "bits": int(match.group(5), 10),
        }
        for match in re.finditer(
            r"([0-9A-Fa-f]{2}:[0-9A-Fa-f]{4})/"
            r"([0-9A-Fa-f]{6})/([0-9A-Fa-f]{4})>"
            r"([0-9A-Fa-f]{4})/(\d+)",
            line.group(2),
        )
    ]
    if count <= count_before or not writes:
        return False, count, None
    new_count = min(count - count_before, len(writes))
    for write in writes[-new_count:]:
        if (
            write["address"] in (0x5128D8, 0x5128DA)
            and write["new"] == expected_event
            and write["bits"] == 16
        ):
            return True, count, write
    return False, count, None


class WebBridge:
    def __init__(self, root: str, timeout: float) -> None:
        self.root = root.rstrip("/")
        self.timeout = timeout

    def get_json(self, path: str) -> dict[str, Any]:
        with urlopen(self.root + path, timeout=self.timeout) as response:
            value = json.load(response)
        if not isinstance(value, dict):
            raise ValueError(f"{path} returned a non-object JSON value")
        return value

    def post_json(self, path: str, value: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self.root + path,
            data=json.dumps(value).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            result = json.load(response)
        if not isinstance(result, dict):
            raise ValueError(f"{path} returned a non-object JSON value")
        return result

    def set_matrix(self, index: int | None) -> None:
        low, high = (0, 0) if index is None else matrix_masks(index)
        result = self.post_json("/api/key", {
            "state": 0,
            "code": 0,
            "matrix_low": low,
            "matrix_high": high,
        })
        if result.get("applied") is False or result.get("ok") is False:
            raise RuntimeError("Web bridge rejected physical matrix input")

    def pulse_matrix(self, index: int) -> None:
        if not 0 <= index < 64:
            raise ValueError("matrix pulse index must be in 0..63")
        self.post_json("/api/key-pulse", {"matrix_index": index})


def capture_state(
    web: WebBridge,
    output_dir: Path,
    prefix: str,
    *,
    allow_failure: bool = False,
) -> dict[str, Any]:
    state = web.get_json("/api/state")
    registers = str(state.get("registers", ""))
    failure = diagnostic_failure(registers)
    if failure and not allow_failure:
        raise RuntimeError(failure)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{prefix}.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if state.get("format") == "gray5" and "frame" in state:
        frame = base64.b64decode(str(state["frame"]), validate=True)
        width = int(state.get("width", 0))
        height = int(state.get("height", 0))
        if len(frame) != width * height:
            raise ValueError(
                f"invalid gray5 frame length {len(frame)} for {width}x{height}"
            )
        (output_dir / f"{prefix}.gray5").write_bytes(frame)
    return state


def capture_frame(web: WebBridge, output_dir: Path, prefix: str) -> dict[str, Any]:
    """Capture only the completed LCD frame without pausing for diagnostics."""
    state = web.get_json("/api/frame")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{prefix}-frame.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if state.get("format") == "gray5" and "frame" in state:
        frame = base64.b64decode(str(state["frame"]), validate=True)
        width = int(state.get("width", 0))
        height = int(state.get("height", 0))
        if len(frame) != width * height:
            raise ValueError(
                f"invalid gray5 frame length {len(frame)} for {width}x{height}"
            )
        (output_dir / f"{prefix}.gray5").write_bytes(frame)
    return state


def stable_frame_signature(state: dict[str, Any]) -> str:
    """Hash one completed LCD frame while excluding the live clock glyphs.

    The system clock occupies the lower-right status area and may redraw while
    an otherwise completed menu is idle.  Masking only that bounded rectangle
    lets the route synchronizer distinguish a real menu transition from a
    timestamp tick without modifying the captured frame or guest state.
    """
    if state.get("format") != "gray5" or "frame" not in state:
        raise ValueError("/api/frame did not return a gray5 frame")
    width = int(state.get("width", 0))
    height = int(state.get("height", 0))
    frame = bytearray(base64.b64decode(str(state["frame"]), validate=True))
    if width <= 0 or height <= 0 or len(frame) != width * height:
        raise ValueError(
            f"invalid gray5 frame length {len(frame)} for {width}x{height}"
        )
    # Native panel coordinates.  The rectangle includes the clock border and
    # digits but leaves the Start button and main menu content in the hash.
    for y in range(min(101, height), height):
        row = y * width
        for x in range(min(184, width), width):
            frame[row + x] = 0
    return hashlib.sha256(frame).hexdigest()


def wait_for_stable_frame(
    web: WebBridge,
    *,
    sequence_before: int,
    timeout: float,
    poll_interval: float,
    stable_samples: int,
) -> dict[str, Any]:
    """Wait for a post-input redraw and consecutive stable non-clock pixels."""
    if stable_samples < 2:
        raise ValueError("stable_samples must be at least 2")
    deadline = time.monotonic() + timeout
    previous_signature: str | None = None
    matching_samples = 0
    last_sequence = sequence_before
    last_signature: str | None = None
    while time.monotonic() < deadline:
        state = web.get_json("/api/frame")
        sequence = int(state.get("sequence", -1))
        if sequence <= sequence_before:
            time.sleep(poll_interval)
            continue
        signature = stable_frame_signature(state)
        last_sequence = sequence
        last_signature = signature
        if signature == previous_signature:
            matching_samples += 1
        else:
            previous_signature = signature
            matching_samples = 1
        if matching_samples >= stable_samples:
            return {
                "sequence_before": sequence_before,
                "sequence_after": sequence,
                "stable_samples": matching_samples,
                "masked_sha256": signature,
            }
        time.sleep(poll_interval)
    raise TimeoutError(
        "LCD did not reach a stable post-input frame before the frame timeout "
        f"(sequence={sequence_before}->{last_sequence}, "
        f"stable={matching_samples}/{stable_samples}, "
        f"sha256={last_signature or 'none'})"
    )


def wait_for_matrix_rearm(
    web: WebBridge,
    *,
    reads_before: int,
    release_timeout: float,
    poll_interval: float,
) -> int:
    """Wait until guest scanning has consumed the all-released matrix state."""
    deadline = time.monotonic() + release_timeout
    reads_after = reads_before
    while time.monotonic() < deadline:
        state = web.get_json("/api/state")
        registers = str(state.get("registers", ""))
        failure = diagnostic_failure(registers)
        if failure:
            raise RuntimeError(failure)
        rearmed, reads_after = matrix_rearm_state(registers, reads_before)
        if rearmed:
            return reads_after
        time.sleep(poll_interval)
    raise TimeoutError(
        "guest did not observe the released matrix before the release timeout"
    )


def wait_for_delivery_and_matrix_rearm(
    web: WebBridge,
    *,
    reads_before: int,
    maps_before: int,
    acknowledgements_before: int,
    modal_acknowledgements_before: int,
    expected_event: int,
    require_foreground_ack: bool,
    release_timeout: float,
    poll_interval: float,
    use_bounded_status: bool = True,
) -> tuple[int, dict[str, int]]:
    """Wait for guest key delivery and the all-released hardware state.

    Candidate-only keys have no ordinary delivery.  Normal events must cross
    28:F6DE and then either root KEYMAPRET at 20:2E9E or the exact state-50
    modal dispatch boundary at 1E:F8E4.  Keeping these requirements in the
    release phase also supports firmware paths that commit on key-up.
    """
    deadline = time.monotonic() + release_timeout
    reads_after = reads_before
    last_rearmed = False
    last_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_status = web.get_json("/api/key-status")
        raise_if_key_status_faulted(web, last_status)
        if require_foreground_ack and (
            "acknowledgements" not in last_status
            or "acknowledgement" not in last_status
            or "modal_acknowledgements" not in last_status
            or "modal_acknowledgement" not in last_status
        ):
            raise RuntimeError(
                "guest-consumer acknowledgement counters are absent from "
                "/api/key-status"
            )
        bounded_rearm = (
            key_status_rearm_state(last_status, reads_before)
            if use_bounded_status else None
        )
        if bounded_rearm is not None:
            last_rearmed, reads_after = bounded_rearm
        else:
            state = web.get_json("/api/state")
            registers = str(state.get("registers", ""))
            failure = diagnostic_failure(registers)
            if failure:
                raise RuntimeError(failure)
            last_rearmed, reads_after = matrix_rearm_state(
                registers, reads_before,
            )
        mapped, acknowledged, acknowledgement_path = key_delivery_state(
            last_status,
            maps_before=maps_before,
            acknowledgements_before=acknowledgements_before,
            modal_acknowledgements_before=modal_acknowledgements_before,
            expected_event=expected_event,
        )
        delivery_complete = (
            not require_foreground_ack or (mapped and acknowledged)
        )
        if last_rearmed and delivery_complete:
            return reads_after, {
                "maps": int(last_status.get("maps", maps_before)),
                "event": int(last_status.get("event", 0)),
                "acknowledgements": int(last_status.get(
                    "acknowledgements", acknowledgements_before,
                )),
                "acknowledgement": int(last_status.get(
                    "acknowledgement", 0,
                )),
                "modal_acknowledgements": int(last_status.get(
                    "modal_acknowledgements",
                    modal_acknowledgements_before,
                )),
                "modal_acknowledgement": int(last_status.get(
                    "modal_acknowledgement", 0,
                )),
                "acknowledgement_path": acknowledgement_path,
            }
        time.sleep(poll_interval)
    mapped, acknowledged, acknowledgement_path = key_delivery_state(
        last_status,
        maps_before=maps_before,
        acknowledgements_before=acknowledgements_before,
        modal_acknowledgements_before=modal_acknowledgements_before,
        expected_event=expected_event,
    )
    raise TimeoutError(
        "guest did not complete released-matrix delivery before the release "
        f"timeout (rearmed={last_rearmed}, mapped={mapped}, "
        f"acknowledged={acknowledged}, path={acknowledgement_path})"
    )


class KeyObservationTimeout(TimeoutError):
    """Failed observation with bounded input evidence, not an inferred cause."""

    def __init__(self, message: str, evidence: dict[str, Any]):
        super().__init__(message)
        self.input_evidence = evidence


def replay_step(
    web: WebBridge,
    step: RouteStep,
    *,
    press_timeout: float,
    release_timeout: float,
    poll_interval: float,
    settle: float,
    frame_stable_samples: int = 0,
    frame_stable_timeout: float = 3.0,
    frame_stable_interval: float = 0.2,
    use_bounded_status: bool = True,
    single_scan_pulse: bool = False,
    pulse_duration: float = 0.0,
    observe_contact_bounds: bool = False,
    hold_duration: float = 0.0,
    on_observed: Callable[[], None] | None = None,
    on_timeout: Callable[[], None] | None = None,
) -> dict[str, Any]:
    if observe_contact_bounds and (pulse_duration <= 0 or single_scan_pulse):
        raise ValueError('contact bounds require a fixed physical pulse')
    contact_bounds = None
    frame_before = (
        web.get_json("/api/frame") if frame_stable_samples else None
    )
    frame_sequence_before = (
        int(frame_before.get("sequence", -1))
        if frame_before is not None else -1
    )
    before = web.get_json("/api/key-status")
    raise_if_key_status_faulted(web, before)
    selector_before = 0
    if (use_bounded_status and "matrix_reads" in before and
            "candidates" in before):
        reads_before = int(before["matrix_reads"])
    else:
        before_state = web.get_json("/api/state")
        before_registers = str(before_state.get("registers", ""))
        failure = diagnostic_failure(before_registers)
        if failure:
            raise RuntimeError(failure)
        reads_match = re.search(r"\bMATRIX_READS:(\d+)\b", before_registers)
        if reads_match is None:
            raise RuntimeError(
                "MATRIX_READS is absent from /api/state diagnostics"
            )
        reads_before = int(reads_match.group(1), 10)
        selector_match = re.search(
            r"(?m)^SELECTOR_STATE_WRITES=COUNT:(\d+)", before_registers,
        )
        if selector_match is None:
            raise RuntimeError(
                "SELECTOR_STATE_WRITES is absent from /api/state diagnostics"
            )
        selector_before = int(selector_match.group(1), 10)
    before_maps = int(before.get("maps", 0))
    before_candidates = int(before.get("candidates", 0))
    before_acknowledgements = int(before.get("acknowledgements", 0))
    before_modal_acknowledgements = int(before.get(
        "modal_acknowledgements", 0,
    ))
    contact_request_started = time.monotonic()
    contact_request_interval = None
    candidate_observation = None
    if single_scan_pulse:
        web.pulse_matrix(step.matrix_index)
    else:
        web.set_matrix(step.matrix_index)
    contact_started = time.monotonic()
    contact_upper_bound = None
    observed: dict[str, Any] | None = None
    held_status: dict[str, Any] = before
    hold_elapsed = 0.0
    hold_samples = 0
    hold_timeline: list[dict[str, Any]] = []
    hold_started: float | None = None
    released = single_scan_pulse
    deadline = time.monotonic() + press_timeout
    status = before
    try:
        if pulse_duration:
            if observe_contact_bounds:
                # These reads bracket, not timestamp, the actual level changes.
                # Keep the requested deadline anchored at the make ACK.
                made = web.get_json('/api/key-status')
                time.sleep(max(0, pulse_duration - (time.monotonic() - contact_started)))
                releasing = web.get_json('/api/key-status')
            else:
                time.sleep(pulse_duration)
            web.set_matrix(None)
            contact_upper_bound = time.monotonic() - contact_started
            contact_request_interval = time.monotonic() - contact_request_started
            released = True
            if observe_contact_bounds:
                released_status = web.get_json('/api/key-status')
                contact_bounds = dict(before_make=before, after_make=made,
                    before_release=releasing, after_release=released_status,
                    scope='sampled guest-time bounds; extra reads perturb contact timing')
                times = [s.get('virtual_time_ns') for s in
                         (before, made, releasing, released_status)]
                if all(type(t) is int for t in times) and times == sorted(times):
                    contact_bounds['guest_contact_lower_ns'] = times[2] - times[1]
                    contact_bounds['guest_contact_upper_ns'] = times[3] - times[0]
        while time.monotonic() < deadline:
            status = web.get_json("/api/key-status")
            raise_if_key_status_faulted(web, status)
            if step.observation == "map":
                # The original worker always writes the candidate before an
                # ordinary event is delivered.  Releasing at this earliest
                # guest boundary avoids artificial long-press repeats and
                # permits mappings which commit only after key-up.
                if (
                    int(status.get("candidates", 0)) > before_candidates
                    and int(status.get("candidate", -1)) == step.expected_event
                ):
                    observed = {
                        "candidate_writes": int(status["candidates"]),
                        "event": int(status["candidate"]),
                    }
                    break
            else:
                if "candidates" in status and "candidate" in status:
                    if (
                        int(status["candidates"]) > before_candidates
                        and int(status["candidate"]) == step.expected_event
                    ):
                        observed = {
                            "candidate_writes": int(status["candidates"]),
                            "event": int(status["candidate"]),
                        }
                        break
                else:
                    # Compatibility with an older diagnostic QEMU: the full
                    # selector ring proves the same guest slot write, but is
                    # intentionally slower than the bounded QOM counters.
                    diagnostics = web.get_json("/api/diagnostics")
                    registers = str(diagnostics.get("registers", ""))
                    failure = diagnostic_failure(registers)
                    if failure:
                        raise RuntimeError(failure)
                    matched, selector_after, write = selector_candidate_state(
                        registers,
                        count_before=selector_before,
                        expected_event=step.expected_event,
                    )
                    if not matched:
                        time.sleep(poll_interval)
                        continue
                    observed = {
                        "selector_writes": selector_after,
                        "event": step.expected_event,
                        "write": write,
                    }
                    break
            time.sleep(poll_interval)
        if observed is None:
            if on_timeout is not None:
                on_timeout()
            raise KeyObservationTimeout(
                f"matrix {step.matrix_index} did not reach {step.observation} "
                f"observation for event 0x{step.expected_event:04X}",
                {
                    "matrix_index": step.matrix_index,
                    "expected_event": step.expected_event,
                    "pulse_duration_seconds": pulse_duration,
                    "contact_after_make_ack_upper_bound_seconds": contact_upper_bound,
                    "before": before,
                    "contact_bounds": contact_bounds,
                    "last_observation": status,
                    "released_before_timeout": released,
                    "scope": "host timing and sampled counters; not guest contact duration or root cause",
                },
            )
        candidate_observation = key_counter_timeline_point(
            before, status, time.monotonic() - contact_request_started,
        )
        if on_observed is not None:
            on_observed()
        hold_started = time.monotonic()
        hold_deadline = hold_started + hold_duration
        if hold_duration > 0:
            held_status = status
            initial_point = key_counter_timeline_point(
                before, held_status, 0.0,
            )
            initial_point["phase"] = "held"
            hold_timeline.append(initial_point)
        last_hold_signature = key_counter_signature(held_status)
        while time.monotonic() < hold_deadline:
            held_status = web.get_json("/api/key-status")
            raise_if_key_status_faulted(web, held_status)
            hold_samples += 1
            signature = key_counter_signature(held_status)
            if signature != last_hold_signature:
                point = key_counter_timeline_point(
                    before, held_status, time.monotonic() - hold_started,
                )
                point["phase"] = "held"
                hold_timeline.append(point)
                last_hold_signature = signature
            remaining = hold_deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(poll_interval, remaining))
        if hold_duration > 0:
            # A repeat can land during the final sleep slice.  Take one
            # atomic sample while the matrix is still asserted so the last
            # held edge is not only discovered by the post-release counters.
            held_status = web.get_json("/api/key-status")
            raise_if_key_status_faulted(web, held_status)
            hold_samples += 1
            signature = key_counter_signature(held_status)
            if signature != last_hold_signature:
                point = key_counter_timeline_point(
                    before, held_status, time.monotonic() - hold_started,
                )
                point["phase"] = "held"
                hold_timeline.append(point)
        hold_elapsed = time.monotonic() - hold_started
    finally:
        if not released:
            web.set_matrix(None)
            contact_request_interval = time.monotonic() - contact_request_started
    reads_after, delivered = wait_for_delivery_and_matrix_rearm(
        web,
        reads_before=reads_before,
        maps_before=before_maps,
        acknowledgements_before=before_acknowledgements,
        modal_acknowledgements_before=before_modal_acknowledgements,
        expected_event=step.expected_event,
        require_foreground_ack=step.require_foreground_ack,
        release_timeout=release_timeout,
        poll_interval=poll_interval,
        use_bounded_status=use_bounded_status,
    )
    frame_stability: dict[str, Any] | None = None
    if frame_stable_samples:
        frame_stability = wait_for_stable_frame(
            web,
            sequence_before=frame_sequence_before,
            timeout=frame_stable_timeout,
            poll_interval=frame_stable_interval,
            stable_samples=frame_stable_samples,
        )
    elif settle:
        time.sleep(settle)
    settled_status = web.get_json("/api/key-status")
    candidates_after_settle = int(settled_status.get(
        "candidates", before_candidates,
    ))
    maps_after_settle = int(settled_status.get("maps", before_maps))
    acknowledgements_after_settle = int(settled_status.get(
        "acknowledgements", before_acknowledgements,
    ))
    modal_acknowledgements_after_settle = int(settled_status.get(
        "modal_acknowledgements", before_modal_acknowledgements,
    ))
    foreground_acknowledgements_total = max(
        0, acknowledgements_after_settle - before_acknowledgements,
    )
    modal_acknowledgements_total = max(
        0,
        modal_acknowledgements_after_settle -
        before_modal_acknowledgements,
    )
    logical_delivery_observed = (
        (foreground_acknowledgements_total > 0 and
         int(settled_status.get("acknowledgement", -1)) ==
         step.expected_event) or
        (modal_acknowledgements_total > 0 and
         int(settled_status.get("modal_acknowledgement", -1)) ==
         step.expected_event)
    )
    if hold_duration > 0 and hold_started is not None:
        terminal_signature = key_counter_signature(settled_status)
        if terminal_signature != key_counter_signature(held_status):
            terminal_point = key_counter_timeline_point(
                before, settled_status, time.monotonic() - hold_started,
            )
            terminal_point["phase"] = "post_release"
            hold_timeline.append(terminal_point)
    result = {
        "label": step.label,
        "matrix_index": step.matrix_index,
        "expected_event": step.expected_event,
        "observation": step.observation,
        "foreground_ack_required": step.require_foreground_ack,
        "consumer_ack_required": step.require_foreground_ack,
        "maps_before": before_maps,
        "maps_after": int(delivered["maps"]),
        "event": int(observed["event"]),
        "acknowledgements_before": before_acknowledgements,
        "acknowledgements_after": int(delivered["acknowledgements"]),
        "acknowledgement": int(delivered["acknowledgement"]),
        "modal_acknowledgements_before": before_modal_acknowledgements,
        "modal_acknowledgements_after": int(
            delivered["modal_acknowledgements"]
        ),
        "modal_acknowledgement": int(delivered["modal_acknowledgement"]),
        "acknowledgement_path": delivered["acknowledgement_path"],
        "matrix_reads_before": reads_before,
        "matrix_reads_after_release": reads_after,
        "release_observed": True,
        "input_mode": (
            "single-scan-pulse" if single_scan_pulse else "held-level"
        ),
        "hold_duration_requested_seconds": hold_duration,
        # This includes host request/ack latency, not exact guest contact
        # duration. hold_elapsed below is only the extra post-candidate hold.
        "host_contact_request_interval_seconds": contact_request_interval,
        "candidate_observation": candidate_observation,
        "matrix_make_requests": 1,
        "hold_duration_observed_seconds": round(hold_elapsed, 6),
        "hold_status_samples": hold_samples,
        "hold_timeline": hold_timeline,
        "pulse_duration_seconds": pulse_duration,
        "contact_bounds": contact_bounds,
        "candidate_writes_after_settle": candidates_after_settle,
        "maps_after_settle": maps_after_settle,
        "acknowledgements_after_settle": acknowledgements_after_settle,
        "modal_acknowledgements_after_settle": (
            modal_acknowledgements_after_settle
        ),
        "candidate_writes_total": max(
            0, candidates_after_settle - before_candidates,
        ),
        "maps_total": max(0, maps_after_settle - before_maps),
        # A single event may legitimately cross both foreground and modal
        # observation boundaries, while one guest delivery can also perform
        # more than one mapper store.  Keep the raw counters for provenance
        # and expose a separate boolean logical-delivery result rather than
        # treating their sum as a user-event count.
        "map_writes_total": max(0, maps_after_settle - before_maps),
        "foreground_acknowledgements_total": (
            foreground_acknowledgements_total
        ),
        "modal_acknowledgements_total": modal_acknowledgements_total,
        "logical_delivery_observed": logical_delivery_observed,
        "logical_guest_events_total": int(logical_delivery_observed),
        # logical_guest_events_total is a legacy boolean, NOT a cardinality
        # of guest dispatches. Preserve raw counters when auditing repeats.
        "consumer_acknowledgements_total": (
            foreground_acknowledgements_total +
            modal_acknowledgements_total
        ),
        **held_counter_summary(before, held_status),
    }
    if frame_stability is not None:
        result["frame_stability"] = frame_stability
    if "selector_writes" in observed:
        result["selector_writes_before"] = selector_before
        result["selector_writes_after"] = int(observed["selector_writes"])
        result["candidate_write"] = observed["write"]
    if "candidate_writes" in observed:
        result["candidate_writes_before"] = before_candidates
        result["candidate_writes_after"] = int(observed["candidate_writes"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="http://127.0.0.1:8781")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--step", action="append", type=parse_step)
    parser.add_argument(
        "--all-candidates", action="store_true",
        help=(
            "probe all 64 positions against the exact active 4F:2AB2 table; "
            "this proves the candidate boundary, not application behavior"
        ),
    )
    parser.add_argument(
        "--candidate-start", type=int, default=0, metavar="INDEX",
        help="first physical index included by --all-candidates (default: 0)",
    )
    parser.add_argument(
        "--candidate-stop", type=int, default=64, metavar="INDEX",
        help="exclusive physical index included by --all-candidates (default: 64)",
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--press-timeout", type=float, default=3.0)
    parser.add_argument("--release-timeout", type=float, default=3.0)
    parser.add_argument("--poll-interval", type=float, default=0.01)
    parser.add_argument("--settle", type=float, default=0.35)
    parser.add_argument(
        "--frame-stable-samples", type=int, default=0,
        help=(
            "after each delivered key, wait for a newer completed LCD frame "
            "whose non-clock pixels match this many consecutive samples; "
            "0 preserves the fixed --settle behavior"
        ),
    )
    parser.add_argument(
        "--frame-stable-timeout", type=float, default=3.0,
        help="maximum seconds to wait for each post-input stable LCD frame",
    )
    parser.add_argument(
        "--frame-stable-interval", type=float, default=0.2,
        help="seconds between post-input LCD stability samples",
    )
    parser.add_argument(
        "--single-scan-pulse", action="store_true",
        help=(
            "diagnostic mode: let QEMU expose the switch for exactly one "
            "selected-row scan, independent of host wall-clock timing"
        ),
    )
    parser.add_argument(
        "--pulse-duration", type=float, default=0.0,
        help=(
            "release each matrix position after this many seconds before "
            "polling guest counters; use a small value to prevent one held "
            "confirm key from being consumed by successive modal pages "
            "(default: 0 keeps the observe-then-release behavior)"
        ),
    )
    parser.add_argument(
        "--observe-contact-bounds", action="store_true",
        help=(
            "with --pulse-duration, sample guest virtual time around matrix "
            "make/break; the extra QMP reads perturb timing, so report "
            "bounds rather than an exact hold duration"
        ),
    )
    parser.add_argument(
        "--hold-duration", type=float, default=0.0,
        help=(
            "seconds to keep each physical matrix position asserted after "
            "its first guest observation (default: 0)"
        ),
    )
    parser.add_argument(
        "--capture-held", action="store_true",
        help="also capture every successfully observed step before release",
    )
    parser.add_argument(
        "--capture-final-only", action="store_true",
        help=(
            "avoid the expensive full-state capture between route steps and "
            "capture only the final successful step; timeout captures are "
            "still retained"
        ),
    )
    parser.add_argument(
        "--capture-frame-only", action="store_true",
        help=(
            "capture the lightweight completed LCD frame after each step "
            "instead of the full diagnostic state"
        ),
    )
    parser.add_argument(
        "--skip-initial-capture", action="store_true",
        help=(
            "begin the first physical edge immediately; useful when the "
            "current foreground is a short-lived diagnostic window"
        ),
    )
    parser.add_argument(
        "--skip-candidate-held", action="store_true",
        help=(
            "skip held-state captures for successful candidate steps; "
            "timeouts are still captured before release"
        ),
    )
    args = parser.parse_args()

    if args.timeout <= 0 or args.press_timeout <= 0 or args.release_timeout <= 0:
        parser.error("timeouts must be positive")
    if (args.poll_interval <= 0 or args.settle < 0 or
            args.pulse_duration < 0 or args.hold_duration < 0):
        parser.error(
            "poll interval must be positive and settle/pulse/hold "
            "non-negative"
        )
    if args.frame_stable_samples not in (0,) and args.frame_stable_samples < 2:
        parser.error("--frame-stable-samples must be 0 or at least 2")
    if args.frame_stable_timeout <= 0 or args.frame_stable_interval <= 0:
        parser.error("frame stability timeout and interval must be positive")
    if sum(bool(value) for value in (
            args.single_scan_pulse, args.pulse_duration,
            args.hold_duration)) > 1:
        parser.error(
            "--single-scan-pulse, --pulse-duration and --hold-duration "
            "are mutually exclusive"
        )
    if args.observe_contact_bounds and args.pulse_duration <= 0:
        parser.error("--observe-contact-bounds requires --pulse-duration")
    if args.capture_final_only and args.capture_frame_only:
        parser.error(
            "--capture-final-only and --capture-frame-only are mutually exclusive"
        )
    if not args.step and not args.all_candidates:
        parser.error("at least one --step or --all-candidates is required")
    if not (0 <= args.candidate_start <= args.candidate_stop <= 64):
        parser.error("candidate range must satisfy 0 <= start <= stop <= 64")
    if args.all_candidates and args.candidate_start == args.candidate_stop:
        parser.error("--all-candidates candidate range must not be empty")

    steps = list(args.step or [])
    if args.all_candidates:
        steps.extend(
            RouteStep(
                f"matrix-{index:02d}", index, ACTIVE_MATRIX_EVENTS[index],
                "candidate",
                require_foreground_ack=(
                    ACTIVE_MATRIX_EVENTS[index] not in CANDIDATE_ONLY_EVENTS
                ),
            )
            for index in range(args.candidate_start, args.candidate_stop)
        )

    web = WebBridge(args.root, args.timeout)
    web.set_matrix(None)
    if not args.skip_initial_capture:
        if args.capture_frame_only:
            capture_frame(web, args.output_dir, "00-before")
        else:
            capture_state(web, args.output_dir, "00-before")
    route: list[dict[str, Any]] = []
    for index, step in enumerate(steps, 1):
        prefix = f"{index:02d}-{safe_label(step.label)}"
        held_prefix = f"{prefix}-held"

        def capture_held() -> None:
            capture_state(web, args.output_dir, held_prefix)

        try:
            result = replay_step(
                web,
                step,
                press_timeout=args.press_timeout,
                release_timeout=args.release_timeout,
                poll_interval=args.poll_interval,
                settle=args.settle,
                frame_stable_samples=args.frame_stable_samples,
                frame_stable_timeout=args.frame_stable_timeout,
                frame_stable_interval=args.frame_stable_interval,
                single_scan_pulse=args.single_scan_pulse,
                pulse_duration=args.pulse_duration,
                observe_contact_bounds=args.observe_contact_bounds,
                hold_duration=args.hold_duration,
                on_observed=(
                    capture_held
                    if args.capture_held or (
                        step.observation == "candidate"
                        and not args.skip_candidate_held
                    )
                    else None
                ),
                on_timeout=capture_held,
            )
            # Loading may fail after key acknowledgement, during settle.
            # Keep the post-input capture inside the same failure-recording
            # boundary so a ROM hole still produces a snapshot and route.json.
            if args.capture_frame_only:
                capture_frame(web, args.output_dir, prefix)
            elif not args.capture_final_only or index == len(steps):
                capture_state(web, args.output_dir, prefix)
        except Exception as error:
            failure_prefix = f"{prefix}-failed"
            capture_state(
                web, args.output_dir, failure_prefix, allow_failure=True,
            )
            summary = {
                "schema": "np560-matrix-route-v2",
                "root": args.root,
                "steps": route,
                "failed_step": {
                    "label": step.label,
                    "matrix_index": step.matrix_index,
                    "expected_event": step.expected_event,
                    "observation": step.observation,
                    "error": f"{type(error).__name__}: {error}",
                    "input_evidence": getattr(error, "input_evidence", None),
                    "held_capture": held_prefix,
                    "capture": failure_prefix,
                },
            }
            (args.output_dir / "route.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            raise
        route.append(result)
        print(
            f"{prefix}: M{step.matrix_index:02d} "
            f"EVENT={step.expected_event:04X} "
            f"OBS={step.observation} "
            f"MAPS={result['maps_before']}->{result['maps_after']} "
            f"ACK={result.get('acknowledgement_path') or 'none'}"
        )

    summary = {
        "schema": "np560-matrix-route-v2",
        "root": args.root,
        "steps": route,
    }
    (args.output_dir / "route.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
