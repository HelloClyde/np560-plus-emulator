#!/usr/bin/env python3
"""Statically recover CYBIT MobiVoice decoder DLLs from one archived Wise installer.

No installer or DLL is executed.  This is source evidence for investigating
NPE format 13, not permission to treat the DLL as a verified NP560 decoder.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
from urllib.request import urlopen
import zipfile
import zlib


URL = ("https://web.archive.org/web/20061115201315id_/http://www.cybit.com/"
       "download/MobivoiceSetupCombined.zip")
ZIP_SHA256 = "2a372670523be164259f6a916c16985c314c06331a38c177c2bef5dce75ac152"
INSTALLER_NAME = "MobivoiceSetupCombined.exe"
FIRST_MEMBER = 0x3AB7
MAX_MEMBER = 16 * 1024 * 1024
TARGETS = {
    29: "MobiVoicePlayer.exe",
    30: "mv_sp.dll",
    31: "Mv_lmp.dll",
}


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def wise_members(installer: bytes):
    offset = FIRST_MEMBER
    for index in range(100):
        inflater = zlib.decompressobj(-15)
        decoded = inflater.decompress(installer[offset:], MAX_MEMBER)
        if not inflater.eof:
            raise ValueError(f"incomplete Wise member {index} at {offset:#x}")
        end = len(installer) - len(inflater.unused_data)
        if end + 4 > len(installer):
            raise ValueError(f"missing Wise CRC for member {index}")
        crc = struct.unpack_from("<I", installer, end)[0]
        if zlib.crc32(decoded) != crc:
            raise ValueError(f"Wise CRC mismatch for member {index}")
        yield index, offset, decoded, crc
        offset = end + 4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path,
                        help="use a previously downloaded copy instead of fetching URL")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error(f"output directory already exists: {args.output_dir}")
    if args.archive:
        raw = args.archive.read_bytes()
    else:
        with urlopen(URL, timeout=40) as response:
            raw = response.read(2 * 1024 * 1024)
    if sha256(raw) != ZIP_SHA256:
        parser.error(f"archive SHA-256 differs: {sha256(raw)}")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        installer = archive.read(INSTALLER_NAME)
    recovered = {}
    for index, offset, blob, crc in wise_members(installer):
        if index in TARGETS:
            recovered[index] = (offset, blob, crc)
        if index >= max(TARGETS):
            break
    if set(recovered) != set(TARGETS):
        parser.error(f"missing members: {set(TARGETS) - set(recovered)}")
    args.output_dir.mkdir(parents=True)
    manifest = {"schema": "np560-mobivoice-codec-candidate-v1",
                "source_url": URL, "archive_sha256": ZIP_SHA256,
                "installer_sha256": sha256(installer),
                "executed": False, "np560_compatibility_verified": False,
                "members": []}
    for index, name in TARGETS.items():
        offset, blob, crc = recovered[index]
        (args.output_dir / name).write_bytes(blob)
        manifest["members"].append({"index": index, "name": name,
            "offset": offset, "size": len(blob), "sha256": sha256(blob),
            "crc32": f"{crc:08x}", "crc_verified": True})
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
