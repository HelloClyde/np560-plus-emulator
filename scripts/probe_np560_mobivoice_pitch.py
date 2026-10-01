#!/usr/bin/env python3
"""Exhaustively compare owned pitch-code mapping with isolated candidate x86.

For each selected previous delay, all 256 byte codes are exercised.  The
reviewed user-supplied DLL is interpreted in Unicorn, never run natively.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

from np560_mobivoice_pitch import decode_candidate_pitch
from probe_np560_mobivoice_sp_decoder import BASE, IO, IsolatedDecoder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll", type=Path, required=True)
    args = parser.parse_args()
    decoder = IsolatedDecoder(args.dll.read_bytes())
    previous_values = (0, 16, 80, 143)
    for previous in previous_values:
        for code in range(256):
            decoder.uc.mem_write(IO, bytes(4))
            decoder.call(BASE + 0x1680, IO, IO + 2, previous, code)
            actual = struct.unpack("<2h", decoder.uc.mem_read(IO, 4))
            expected = decode_candidate_pitch(previous, code)
            if actual != expected:
                raise RuntimeError(
                    f"candidate pitch mismatch previous={previous} code={code}: "
                    f"{actual} != {expected}"
                )
    print(json.dumps({
        "schema": "np560-candidate-pitch-differential-v1",
        "candidate_not_mask_rom_truth": True,
        "previous_delays": previous_values,
        "codes_per_delay": 256,
        "cases": len(previous_values) * 256,
        "all_match": True,
    }))


if __name__ == "__main__":
    main()
