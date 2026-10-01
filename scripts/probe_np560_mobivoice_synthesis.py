#!/usr/bin/env python3
"""Differentially test the owned final synthesis filter with synthetic data.

This opt-in probe interprets the reviewed, user-supplied DLL in Unicorn.
It never executes the DLL natively or includes vendor code in its report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import struct

from np560_mobivoice_synthesis import synthesize_candidate_block
from probe_np560_mobivoice_sp_decoder import BASE, IO, IsolatedDecoder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--random-vectors", type=int, default=100)
    args = parser.parse_args()
    if not 0 <= args.random_vectors <= 10000:
        parser.error("random vector count must be 0..10000")

    decoder = IsolatedDecoder(args.dll.read_bytes())
    rng = random.Random(0x5601CA0)
    cases = [
        ((0, 1, -1, 30000, -30000), (0,) * 10, (0,) * 10),
        ((-16385, -16384, -16383), (0,) * 10, (0,) * 10),
        ((32767,) * 80, (32767,) * 10, (32767,) * 10),
    ]
    for _ in range(args.random_vectors):
        length = rng.choice((1, 5, 80))
        cases.append((
            tuple(rng.randrange(-32768, 32768) for _ in range(length)),
            tuple(rng.randrange(-32768, 32768) for _ in range(10)),
            tuple(rng.randrange(-32768, 32768) for _ in range(10)),
        ))

    clipped = 0
    for index, (intermediate, previous, taps) in enumerate(cases):
        decoder.uc.mem_write(
            IO, struct.pack(f"<{len(intermediate)}h", *intermediate),
        )
        decoder.uc.mem_write(
            IO + 0x1000,
            struct.pack(f"<{len(previous)}h", *previous) +
            bytes(len(intermediate) * 2),
        )
        decoder.uc.mem_write(
            IO + 0x2000,
            b"\x00\x00" + struct.pack("<10h", *taps),
        )
        decoder.call(BASE + 0x1CA0, IO, len(intermediate),
                     IO + 0x2000, IO + 0x1000 + 20)
        actual = struct.unpack(
            f"<{len(intermediate)}h",
            decoder.uc.mem_read(IO + 0x1000 + 20, len(intermediate) * 2),
        )
        expected = synthesize_candidate_block(intermediate, previous, taps)
        if actual != expected:
            raise RuntimeError(f"candidate synthesis mismatch at vector {index}")
        clipped += sum(abs(sample) == 32767 for sample in actual)
    print(json.dumps({
        "schema": "np560-candidate-synthesis-differential-v1",
        "candidate_not_mask_rom_truth": True,
        "vectors": len(cases),
        "clipped_samples": clipped,
        "all_match": True,
    }))


if __name__ == "__main__":
    main()
