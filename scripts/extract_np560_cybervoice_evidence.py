#!/usr/bin/env python3
"""Recover independently CRC-checked Wise members from the archived ZIP prefix.

The outer ZIP and installer are truncated: neither is called complete or run.
Offsets and framing here are observed in this specific official trial archive.
This is source acquisition, not an ESAC decoder or a guest implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

PREFIX_SHA256 = "a8a833868e5eb6699bc67e7e3443396bb4578926ca6bc6ee39883180bf692580"
MAX_MEMBER = 8 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def extract(source: Path, destination: Path):
    raw = source.read_bytes()
    if sha(raw) != PREFIX_SHA256:
        raise ValueError("Not the reviewed CyberVoicetrial.zip prefix")
    if raw[:4] != b"PK\x03\x04":
        raise ValueError("Missing ZIP local header")
    _, flags, method, _, _, crc, packed, unpacked, namesize, extrasize = (
        struct.unpack_from("<5H3I2H", raw, 4))
    if flags != 0 or method != 8 or raw[30:30+namesize] != b"setuptrial.EXE":
        raise ValueError("Unexpected outer member")
    inflater = zlib.decompressobj(-15)
    installer = inflater.decompress(raw[30+namesize+extrasize:], MAX_MEMBER)
    if inflater.eof or len(installer) >= unpacked:
        raise ValueError("Expected a truncated installer, not a complete archive")
    if destination.exists():
        raise ValueError("Use a new output directory; never overwrite evidence")
    destination.mkdir(parents=True)
    report = {
        "source": str(source.resolve()), "source_sha256": sha(raw),
        "outer_zip_complete": False, "outer_zip_crc_verified": False,
        "outer_expected_crc32": f"{crc:08x}",
        "outer_expected_compressed_size": packed,
        "outer_expected_uncompressed_size": unpacked,
        "installer_prefix_size": len(installer),
        "installer_prefix_sha256": sha(installer),
        "installer_executed": False, "wise_members": [],
    }
    # PE raw sections end at 0x3800. Wise's initial strings end at 0x38C1.
    # A complete raw DEFLATE member is followed by its little-endian CRC32.
    offset = 0x38C1
    for index in range(100):
        inflater = zlib.decompressobj(-15)
        try:
            decoded = inflater.decompress(installer[offset:], MAX_MEMBER)
        except zlib.error as error:
            report["stop"] = {"offset": offset, "reason": "invalid_deflate",
                              "detail": str(error)}
            break
        if not inflater.eof:
            report["stop"] = {"offset": offset, "reason": "incomplete_or_size_limit",
                              "decoded_prefix_bytes_not_saved": len(decoded)}
            break
        end = len(installer) - len(inflater.unused_data)
        if end+4 > len(installer):
            report["stop"] = {"offset": offset, "reason": "missing_crc"}
            break
        expected = struct.unpack_from("<I", installer, end)[0]
        actual = zlib.crc32(decoded)
        if expected != actual:
            report["stop"] = {"offset": offset, "reason": "crc_mismatch"}
            break
        filename = f"member-{index:02d}-{offset:08x}.bin"
        (destination / filename).write_bytes(decoded)
        strings = [m.group().decode("ascii") for m in
                   re.finditer(rb"[\x20-\x7e]{6,}", decoded)]
        hints = [s for s in strings if re.search(
            r"esac|cyber|codec|\.dll|\.exe|\.wav|\.cbv|\.cve", s, re.I)]
        report["wise_members"].append({
            "file": filename, "offset": offset, "compressed_end": end,
            "size": len(decoded), "sha256": sha(decoded),
            "crc32": f"{actual:08x}", "crc_verified": True,
            "prefix_hex": decoded[:16].hex(), "string_hints": hints[:100],
        })
        offset = end+4
    else:
        raise ValueError("Unexpectedly many members")
    (destination / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = extract(args.prefix, args.output)
    for member in result["wise_members"]:
        print(member["file"], member["size"],
              [hint[:120] for hint in member["string_hints"][:8]])
    print("STOP", result["stop"])
