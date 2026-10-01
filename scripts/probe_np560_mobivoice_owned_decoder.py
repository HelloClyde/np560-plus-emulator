#!/usr/bin/env python3
"""Compare every format-13 NPE sound section with the isolated codec candidate.

The owned decoder never loads the DLL.  The reference image is emulated in
Unicorn for this explicit offline differential only, not run natively.
This cannot establish identity with the unavailable NP560 mask ROM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

from analyse_np560_npe import _parse_sections
from np560_mobivoice_decoder import CandidateMode5Decoder
from probe_np560_mobivoice_sp_decoder import IsolatedDecoder, candidate_bytes


def compare_sound_section(section: bytes, dll: bytes, index: int) -> dict:
    if len(section) < 4 or section[:2] != b"\x20\x0d":
        raise ValueError(f"section {index} is not format 13")
    count = int.from_bytes(section[2:4], "big")
    expected_size = (4 + count * 21 + 1) & ~1
    if count <= 0 or len(section) != expected_size:
        raise ValueError(f"section {index} has inconsistent frame geometry")
    # The word swap spans 21-byte frame boundaries, not each frame separately.
    encoded = candidate_bytes(section[4:4 + count * 21], "swap16", 0)
    owned = CandidateMode5Decoder()
    reference = IsolatedDecoder(dll)
    context, bits = reference.init(5)
    if not context or bits != 168:
        raise ValueError("reference candidate rejected mode 5")
    owned_hash = hashlib.sha256()
    reference_hash = hashlib.sha256()
    started = time.monotonic()
    for frame_index in range(count):
        frame = encoded[frame_index * 21:(frame_index + 1) * 21]
        pcm_words = owned.decode_frame(frame)
        actual = struct.pack("<160h", *pcm_words)
        samples, expected = reference.decode(frame, context)
        if samples != 160 or len(expected) != 320:
            raise ValueError(f"section {index} frame {frame_index}: invalid reference output")
        owned_hash.update(actual)
        reference_hash.update(expected)
        if actual != expected:
            reference_words = struct.unpack("<160h", expected)
            sample = next(position for position, (a, b) in enumerate(
                zip(pcm_words, reference_words)
            ) if a != b)
            raise AssertionError(
                f"section {index} frame {frame_index} sample {sample}: "
                f"owned={pcm_words[sample]} candidate={reference_words[sample]}"
            )
    return {
        "section": index,
        "frames": count,
        "pcm_sha256": owned_hash.hexdigest(),
        "candidate_pcm_sha256": reference_hash.hexdigest(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npe", type=Path, required=True)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    game = args.npe.read_bytes()
    dll = args.dll.read_bytes()
    # Refuse an unreviewed candidate before processing any section.
    IsolatedDecoder(dll)
    rows = []
    for index, (offset, size) in enumerate(_parse_sections(game)):
        if index < 16:
            continue
        row = compare_sound_section(game[offset:offset + size], dll, index)
        rows.append(row)
        print(f"section {index}: {row['frames']} frames, "
              f"PCM {row['pcm_sha256']}, {row['elapsed_seconds']} s", flush=True)
    report = {
        "schema": "np560-npe-owned-candidate-all-sections-v1",
        "npe_sha256": hashlib.sha256(game).hexdigest(),
        "candidate_sha256": hashlib.sha256(dll).hexdigest(),
        "sections": rows,
        "total_frames": sum(row["frames"] for row in rows),
        "all_pcm_samples_match": True,
        "limitation": "candidate compatibility only; no real NP560 ROM PCM reference",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
