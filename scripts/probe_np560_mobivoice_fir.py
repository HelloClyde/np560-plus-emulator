#!/usr/bin/env python3
"""Check an owned candidate sample dot product against isolated x86 code.

Synthetic history and tap sequences only.  The user-supplied DLL is
interpreted in Unicorn and is never executed natively or redistributed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import struct

from np560_mobivoice_fir import candidate_dot_sample, signed32
from probe_np560_mobivoice_sp_decoder import BASE, IO, IsolatedDecoder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--random-vectors", type=int, default=100)
    args = parser.parse_args()
    if not 0 <= args.random_vectors <= 10000:
        parser.error("random vector count must be 0..10000")

    decoder = IsolatedDecoder(args.dll.read_bytes())
    rng = random.Random(5601610)
    cases = [
        ((0,), (0,), 0),
        ((32767,), (32767,), 0),
        ((-32768,) * 29, (-32768,) * 29, 2),
    ]
    for _ in range(args.random_vectors):
        radius = rng.choice((0, 2, 14))
        length = 2 * radius + 1
        history = tuple(rng.randrange(-32768, 32768) for _ in range(length))
        taps = tuple(rng.randrange(-32768, 32768) for _ in range(length))
        cases.append((history, taps, rng.randrange(-2, 3)))

    for index, (history, taps, lag) in enumerate(cases):
        radius = len(history) // 2
        history_base = IO + 0x200
        coefficients_base = IO + 0x1000
        coefficients = [0] * (4 + 3 * len(taps) + 4)
        for tap_index, tap in enumerate(taps):
            coefficients[4 + tap_index * 3] = tap
        decoder.uc.mem_write(
            history_base, struct.pack(f"<{len(history)}h", *history),
        )
        decoder.uc.mem_write(
            coefficients_base,
            struct.pack(f"<{len(coefficients)}h", *coefficients),
        )
        result = signed32(decoder.call(
            BASE + 0x1610,
            history_base + radius * 2,
            lag & 0xFFFFFFFF,
            coefficients_base + (4 + radius * 3 + lag) * 2,
            radius,
        ))
        expected = candidate_dot_sample(history, taps)
        if result != expected:
            raise RuntimeError(f"candidate dot-product mismatch at vector {index}")
    print(json.dumps({
        "schema": "np560-candidate-dot-product-differential-v1",
        "candidate_not_mask_rom_truth": True,
        "vectors": len(cases),
        "all_match": True,
    }))


if __name__ == "__main__":
    main()
