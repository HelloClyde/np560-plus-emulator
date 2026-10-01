#!/usr/bin/env python3
"""Make an isolated ROM-hole probe, never a production audio implementation.

The sole patched instruction is a diagnostic RETS at 02:ACD8.  This lets an
isolated run reveal the *next* missing resident service.  It does not model
ACD8's unknown side effects and must not be used as a playable ROM.
"""

import argparse
import hashlib
import json
from pathlib import Path


ADDRESS = 0x02ACD8
HOLE = bytes.fromhex("000f")
RETS = bytes.fromhex("20c6")


def make_probe(source: bytes) -> bytes:
    if source[ADDRESS:ADDRESS + 2] != HOLE:
        raise ValueError("02:ACD8 is not the expected ROM skeleton hole")
    result = bytearray(source)
    result[ADDRESS:ADDRESS + 2] = RETS
    return bytes(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True,
                        help="full SHA-256 of the source ROM; prevents stale probes")
    args = parser.parse_args()
    source = args.source.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest.lower() != args.expected_sha256.lower():
        parser.error(f"source ROM SHA-256 differs: {digest}")
    probe = make_probe(source)
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(probe)
    print(json.dumps({"diagnostic_only": True, "patch": "02:ACD8 RETS",
                      "source_sha256": digest,
                      "probe_sha256": hashlib.sha256(probe).hexdigest(),
                      "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
