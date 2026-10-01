#!/usr/bin/env python3
"""Compare opt-in codec input trace with an original NPE section.

This checks compressed bytes only. It does not establish ROM sample identity,
audio quality, or the behavior of the unobserved resident-ROM services.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyse_np560_npe import _parse_sections


def swapped_stream(section: bytes) -> bytes:
    if len(section) < 4 or len(section) & 1:
        raise ValueError("invalid NPE section")
    payload = section[4:]
    return bytes(payload[index ^ 1] for index in range(len(payload)))


def compare_trace(section: bytes, rows: list[dict], playback_start: int,
                  frame_bytes: int, max_frames: int | None = None) -> dict:
    if (playback_start < 0 or frame_bytes <= 0 or
            (max_frames is not None and max_frames <= 0)):
        raise ValueError("invalid trace configuration")
    expected = swapped_stream(section)
    checked = 0
    first_bad = None
    for row in rows:
        index = row["index"]
        if index < playback_start:
            continue
        if max_frames is not None and checked >= max_frames:
            break
        if index != playback_start + checked:
            raise ValueError("trace playback indexes are not contiguous")
        frame_index = index - playback_start
        start = frame_index * frame_bytes
        frame = bytes.fromhex(row["frame_hex"])
        reference = expected[start:start + frame_bytes]
        if len(frame) != frame_bytes or len(reference) != frame_bytes:
            raise ValueError("trace or reference has an incomplete frame")
        if first_bad is None and frame != reference:
            first_bad = {
                "trace_index": index,
                "frame_index": frame_index,
                "expected_hex": reference.hex(),
                "actual_hex": frame.hex(),
                "first_different_byte": next(i for i, (a, b) in enumerate(
                    zip(frame, reference)) if a != b),
            }
        checked += 1
    if not checked:
        raise ValueError("trace contains no playback frames")
    if max_frames is not None and checked != max_frames:
        raise ValueError("trace ended before the requested playback prefix")
    return {
        "schema": "np560-npe-codec-input-compare-v1",
        "section_declared_frames": int.from_bytes(section[2:4], "big"),
        "playback_start": playback_start,
        "frame_bytes": frame_bytes,
        "checked_frames": checked,
        "matching_prefix_frames": (checked if first_bad is None
                                   else first_bad["frame_index"]),
        "first_mismatch": first_bad,
        "scope": "compressed-input bytes only; PCM and guest playback not certified",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npe", type=Path, required=True)
    parser.add_argument("--section", type=int, default=16)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--playback-start", type=int, default=3)
    parser.add_argument("--frame-bytes", type=int, default=21)
    parser.add_argument("--max-frames", type=int,
                        help="bounded playback prefix, useful before a later stream begins")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.npe.read_bytes()
    sections = _parse_sections(source)
    if not 0 <= args.section < len(sections):
        parser.error("section index is outside the NPE table")
    offset, length = sections[args.section]
    rows = [json.loads(line) for line in args.trace.read_text(
        encoding="utf-8").splitlines() if line]
    result = compare_trace(source[offset:offset + length], rows,
                           args.playback_start, args.frame_bytes, args.max_frames)
    result.update(npe=str(args.npe), section=args.section, trace=str(args.trace))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
