#!/usr/bin/env python3
"""Compare guest DAC sample-change order with an explicit NPE PCM candidate.

The guest repeats 8 kHz samples four times at 32 kHz. Comparing value changes
avoids asserting exact 48 kHz host presentation timing. A match validates the
observed guest-to-DAC chain against this candidate, not the missing ROM's
unknown bit-exact output or analog speaker quality.
"""

from __future__ import annotations

import argparse
from itertools import groupby
import json
from pathlib import Path
import struct
import wave


def clip16(value: int) -> int:
    return max(-32768, min(32767, value))


def compare_changes(reference: list[int], actual: list[int], gain: int) -> dict:
    if not reference or not actual or gain <= 0:
        raise ValueError("nonempty PCM and positive gain are required")
    expected_runs = [(value, sum(1 for _ in group)) for value, group in
                     groupby(clip16(value * gain) for value in reference)]
    first = next((index for index, value in enumerate(actual) if value), None)
    if first is None:
        raise ValueError("captured DAC is entirely silent")
    last = len(actual) - 1 - next(index for index, value in enumerate(
        reversed(actual)) if value)
    actual_runs = [value for value, _ in groupby(actual[first:last + 1])]
    while expected_runs and expected_runs[0][0] == 0:
        expected_runs.pop(0)
    matched = 0
    for (expected, _), got in zip(expected_runs, actual_runs):
        if expected != got:
            break
        matched += 1
    if matched < len(expected_runs) and matched < len(actual_runs):
        mismatch = {"expected": expected_runs[matched][0],
                    "actual": actual_runs[matched]}
    elif matched < len(expected_runs):
        mismatch = {"expected": expected_runs[matched][0],
                    "actual": None, "reason": "capture ended"}
    else:
        mismatch = None
    return {
        "schema": "np560-npe-dac-reference-v1",
        "gain_multiplier": gain,
        "reference_samples": len(reference),
        "expected_change_runs": len(expected_runs),
        "actual_change_runs": len(actual_runs),
        "matching_prefix_runs": matched,
        "matching_prefix_reference_samples": sum(length for _, length in
                                                  expected_runs[:matched]),
        "first_nonzero_captured_frame": first,
        "last_nonzero_captured_frame": last,
        "first_mismatch": mismatch,
        "scope": "DAC sample value order only; exact timing and original ROM PCM not certified",
    }


def pcm16_wav(path: Path, *, channels: int, rate: int) -> list[int]:
    with wave.open(str(path), "rb") as stream:
        if (stream.getnchannels() != channels or stream.getframerate() != rate or
                stream.getsampwidth() != 2 or stream.getcomptype() != "NONE"):
            raise ValueError(f"unexpected WAV format: {path}")
        data = stream.readframes(stream.getnframes())
    return list(struct.unpack("<%dh" % (len(data) // 2), data))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True,
                        help="explicit experimental 8 kHz mono PCM16 WAV")
    parser.add_argument("--capture", type=Path, required=True,
                        help="observed 48 kHz stereo PCM16 DAC WAV")
    parser.add_argument("--gain", type=int, default=2,
                        help="explicit integer candidate transform for the observed volume")
    parser.add_argument("--reference-frames", type=int, required=True,
                        help="number of 160-sample decoder frames to compare")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    reference = pcm16_wav(args.reference, channels=1, rate=8000)
    if not 1 <= args.reference_frames <= len(reference) // 160:
        parser.error("reference-frames exceeds complete 160-sample frames")
    actual = pcm16_wav(args.capture, channels=2, rate=48000)[::2]
    result = compare_changes(reference[:args.reference_frames * 160], actual,
                             args.gain)
    result.update(reference=str(args.reference), capture=str(args.capture),
                  compared_decoder_frames=args.reference_frames)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
