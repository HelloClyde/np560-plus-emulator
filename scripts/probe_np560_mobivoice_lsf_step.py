#!/usr/bin/env python3
"""Differentially check one owned candidate preparation step against local DLL.

This is opt-in research: the reviewed DLL runs only as x86 instructions in
Unicorn.  No vendor bytes are written to the repository or report, and this
step alone neither produces PCM nor establishes NP560 mask-ROM equivalence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import struct

from np560_mobivoice_lsf import normalize_candidate_words, signed16
from probe_np560_mobivoice_sp_decoder import BASE, IO, IsolatedDecoder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--random-vectors", type=int, default=100)
    args = parser.parse_args()
    if not 0 <= args.random_vectors <= 10000:
        parser.error("random vector count must be 0..10000")

    decoder = IsolatedDecoder(args.dll.read_bytes())
    rng = random.Random(560)
    vectors = [(0,) * 10, (20000,) * 10]
    vectors.extend(
        tuple(rng.randrange(-2000, 20001) for _ in range(10))
        for _ in range(args.random_vectors)
    )
    changed = 0
    nonzero = 0
    for index, words in enumerate(vectors):
        decoder.uc.mem_write(IO, struct.pack("<10h", *words))
        machine_status = signed16(decoder.call(BASE + 0x1220, IO))
        machine_values = struct.unpack("<10h", decoder.uc.mem_read(IO, 20))
        expected = normalize_candidate_words(words)
        if (machine_values, machine_status) != expected:
            raise RuntimeError(f"candidate preparation mismatch at vector {index}")
        changed += machine_values != words
        nonzero += machine_status != 0
    print(json.dumps({
        "schema": "np560-candidate-preparation-differential-v1",
        "candidate_not_mask_rom_truth": True,
        "vectors": len(vectors),
        "changed_vectors": changed,
        "nonzero_status_vectors": nonzero,
        "all_match": True,
    }))


if __name__ == "__main__":
    main()
