#!/usr/bin/env python3
"""Compare owned fixed-point interpolation with isolated candidate x86 code.

Only synthetic tables and positions are used.  The user-supplied DLL is
interpreted in Unicorn, not executed natively or copied into the report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import struct

from np560_mobivoice_interpolate import interpolate_candidate_table
from probe_np560_mobivoice_sp_decoder import BASE, IO, IsolatedDecoder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--random-vectors", type=int, default=100)
    args = parser.parse_args()
    if not 0 <= args.random_vectors <= 10000:
        parser.error("random vector count must be 0..10000")

    decoder = IsolatedDecoder(args.dll.read_bytes())
    rng = random.Random(5601280)
    cases = [
        (8, (0, 127, 255, 256, 511), tuple(range(65))),
        (4, (0, 7, 15, 16, 31), tuple(range(65))),
    ]
    for _ in range(args.random_vectors):
        shift = rng.choice((4, 5, 8))
        table = tuple(rng.randrange(-10000, 10001) for _ in range(65))
        positions = tuple(
            rng.randrange(0, 64 << shift) for _ in range(10)
        )
        cases.append((shift, positions, table))

    for index, (shift, positions, table) in enumerate(cases):
        decoder.uc.mem_write(IO, struct.pack(f"<{len(positions)}h", *positions))
        decoder.uc.mem_write(IO + 0x1000, struct.pack(f"<{len(table)}h", *table))
        decoder.uc.mem_write(IO + 0x2000, bytes(len(positions) * 2))
        decoder.call(BASE + 0x1280, IO, len(positions), shift,
                     IO + 0x1000, IO + 0x2000)
        actual = struct.unpack(
            f"<{len(positions)}h",
            decoder.uc.mem_read(IO + 0x2000, len(positions) * 2),
        )
        expected = interpolate_candidate_table(positions, table, shift)
        if actual != expected:
            raise RuntimeError(f"candidate interpolation mismatch at vector {index}")
    print(json.dumps({
        "schema": "np560-candidate-interpolation-differential-v1",
        "candidate_not_mask_rom_truth": True,
        "vectors": len(cases),
        "all_match": True,
    }))


if __name__ == "__main__":
    main()
