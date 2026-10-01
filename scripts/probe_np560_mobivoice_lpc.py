#!/usr/bin/env python3
"""Differential-test owned LSF-to-LPC conversion against isolated x86 code.

The reviewed DLL is interpreted in Unicorn and is never executed natively.
Equal outputs establish only candidate compatibility, not NP560 mask-ROM truth.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import struct

from np560_mobivoice_lpc import candidate_lpc_from_lsf
from probe_np560_mobivoice_sp_decoder import BASE, IO, IsolatedDecoder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--random-vectors", type=int, default=100)
    args = parser.parse_args()
    if not 0 <= args.random_vectors <= 10000:
        parser.error("random vector count must be 0..10000")
    decoder = IsolatedDecoder(args.dll.read_bytes())
    context, bits = decoder.init(5)
    if bits != 168:
        raise RuntimeError("candidate mode-5 bit width changed")
    config = context + 2
    table = struct.unpack("<I", decoder.uc.mem_read(config + 8, 4))[0]
    rng = random.Random(5601320)
    cases = [
        (1263, 2002, 3059, 4859, 6170, 7462, 9434, 11031, 12717, 14246),
        tuple(range(204, 204 * 11, 204)),
        tuple(range(14000, 14010)),
        tuple(range(16200, 16210)),
    ]
    cases.extend(tuple(sorted(rng.randrange(0, 16384) for _ in range(10)))
                 for _ in range(args.random_vectors))
    for index, lsf in enumerate(cases):
        decoder.uc.mem_write(IO, struct.pack("<10h", *lsf))
        decoder.uc.mem_write(IO + 0x1000, bytes(22))
        decoder.call(BASE + 0x1320, IO, IO + 0x1000, table)
        actual = struct.unpack("<11h", decoder.uc.mem_read(IO + 0x1000, 22))
        expected = candidate_lpc_from_lsf(lsf)
        if actual != expected:
            raise RuntimeError(
                f"candidate LPC mismatch vector={index} input={lsf} "
                f"actual={actual} expected={expected}"
            )
    print(json.dumps({
        "schema": "np560-candidate-lpc-differential-v1",
        "candidate_not_mask_rom_truth": True,
        "vectors": len(cases),
        "all_match": True,
    }))


if __name__ == "__main__":
    main()
