#!/usr/bin/env python3
"""Create and verify a deterministic gzip of a complete NP560N1 NAND checkpoint."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile


HEADER_SIZE = 64
DATA_SIZE = 512 * 1024 * 1024
OOB_SIZE = 16 * 1024 * 1024
CHECKPOINT_SIZE = HEADER_SIZE + DATA_SIZE + OOB_SIZE
CHUNK_SIZE = 4 * 1024 * 1024


def validate_header(source: Path) -> None:
    if source.stat().st_size != CHECKPOINT_SIZE:
        raise ValueError(f"Expected {CHECKPOINT_SIZE} bytes: {source}")
    with source.open("rb") as stream:
        header = stream.read(HEADER_SIZE)
    if header[:8] != b"NP560N1\0":
        raise ValueError(f"Not an NP560N1 checkpoint: {source}")
    geometry = struct.unpack_from("<6I2Q", header, 8)
    if geometry != (1, HEADER_SIZE, 2048, 64, 64, 4096,
                    DATA_SIZE, OOB_SIZE):
        raise ValueError(f"Unsupported NP560N1 geometry: {geometry}")


def compress(source: Path, destination: Path,
             expected_sha256: str | None = None) -> dict:
    source = source.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(destination)
    validate_header(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                prefix=destination.name + ".", suffix=".tmp",
                dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            raw_hash = hashlib.sha256()
            with source.open("rb") as original, gzip.GzipFile(
                    filename="", mode="wb", fileobj=output, mtime=0,
                    compresslevel=6) as compressed:
                while chunk := original.read(CHUNK_SIZE):
                    raw_hash.update(chunk)
                    compressed.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        raw_digest = raw_hash.hexdigest()
        if expected_sha256 and raw_digest.lower() != expected_sha256.lower():
            raise ValueError("Source SHA-256 does not match the expected release asset")
        restored_hash = hashlib.sha256()
        restored_bytes = 0
        with gzip.open(temporary, "rb") as restored:
            while chunk := restored.read(CHUNK_SIZE):
                restored_hash.update(chunk)
                restored_bytes += len(chunk)
        if restored_bytes != CHECKPOINT_SIZE or restored_hash.hexdigest() != raw_digest:
            raise ValueError("Compressed checkpoint failed round-trip verification")
        with temporary.open("rb") as compressed_file:
            compressed_digest = hashlib.file_digest(
                compressed_file, "sha256").hexdigest()
        compressed_bytes = temporary.stat().st_size
        temporary.replace(destination)
        temporary = None
        return {
            "source_sha256": raw_digest,
            "compressed_sha256": compressed_digest,
            "source_bytes": CHECKPOINT_SIZE,
            "compressed_bytes": compressed_bytes,
            "compressed_percent": round(100 * compressed_bytes / CHECKPOINT_SIZE, 2),
        }
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    print(json.dumps(compress(args.source, args.destination,
                              args.expected_sha256), indent=2))


if __name__ == "__main__":
    main()
