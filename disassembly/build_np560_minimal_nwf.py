#!/usr/bin/env python3
"""Build and inspect a minimal experimental NP560+ V3.80 NWF resource.

This tool reconstructs a file that satisfies the format contract recovered
from the shipped PRG.  It is an experiment for exercising the original guest
reader and menu launcher; it is not claimed to be an original factory file.

The first candidate deliberately uses the firmware's supported authorization
offset ``-1``.  That keeps the real device-specific XOR key out of the first
validation experiment and lets NAND/FTL insertion be debugged independently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


HEADER_SIZE = 0x200
PROTECTED_OFFSET = 0x10
PROTECTED_BLOCKS = 0x3E
DES_BLOCK_BYTES = 8
PROTECTED_SIZE = PROTECTED_BLOCKS * DES_BLOCK_BYTES
HEADER_TABLE_OFFSET = 0x40
DECODED_HEADER_START = 0x5F
DIRECT_READ_THRESHOLD = 0xFE00
LEGACY_RECORD_OFFSET = DIRECT_READ_THRESHOLD
# Repeated clean runs agree that the first 32 guest-native 0x100-byte writes
# succeed.  Later extent growth is not stable in the recovered storage model.
# Put the record in the final page of that common 0x2000-byte extent and use
# the original below-threshold reader.
RECORD_OFFSET = 0x1F00
RECORD_READ_WINDOW_SIZE = 0x200
RECORD_STORAGE_SIZE = 0x100
LEGACY_RECORD_STORAGE_SIZE = 0x200
FILE_SIZE = RECORD_OFFSET + RECORD_STORAGE_SIZE

VERSION = b"NEPLAYERV0.99"
VERSION_SIZE = 13
PLAYER_MAGIC = b"NEPLAYER"
AUTHORIZATION_MAGIC = b"NOAHAUTH"
KEY_PADDING = b"\x00\x00\x00"

AUTHORIZATION_FIELD_OFFSET = HEADER_TABLE_OFFSET + 0x0A
RECORD_POSITION_FIELD_OFFSET = HEADER_TABLE_OFFSET + 0x0D
APPLICATION_CODE = 0x1203
MENU_PAGE = 0
MENU_FLAGS = 0


def encode_signed24(value: int) -> bytes:
    if not -(1 << 23) <= value < (1 << 23):
        raise ValueError(f"signed 24-bit value out of range: {value}")
    return (value & 0xFFFFFF).to_bytes(3, "little")


def decode_signed24(data: bytes) -> int:
    if len(data) != 3:
        raise ValueError("signed 24-bit input must contain exactly 3 bytes")
    value = int.from_bytes(data, "little")
    return value - (1 << 24) if value & 0x800000 else value


def _triple_des(data: bytes, key1: bytes, key2: bytes, *, encrypt: bool) -> bytes:
    if len(data) % DES_BLOCK_BYTES:
        raise ValueError("Triple-DES data must contain complete DES blocks")
    if len(key1) != 8 or len(key2) != 8:
        raise ValueError("each DES key must contain 8 bytes")
    # A 16-byte TripleDES key is expanded as K1,K2,K1, exactly matching the
    # three resident 02:DEA6 calls recovered from 1D:668A.
    context = Cipher(
        algorithms.TripleDES(key1 + key2), modes.ECB(), backend=default_backend()
    )
    transform = context.encryptor() if encrypt else context.decryptor()
    return transform.update(data) + transform.finalize()


def decode_header(raw_header: bytes) -> bytes:
    if len(raw_header) != HEADER_SIZE:
        raise ValueError(f"NWF header must be exactly {HEADER_SIZE:#x} bytes")
    key1 = raw_header[0:8]
    key2 = raw_header[8:16]
    decoded = bytearray(raw_header)
    decoded[PROTECTED_OFFSET:HEADER_SIZE] = _triple_des(
        raw_header[PROTECTED_OFFSET:HEADER_SIZE], key1, key2, encrypt=True
    )
    return bytes(decoded)


def encode_header(decoded_header: bytes) -> bytes:
    if len(decoded_header) != HEADER_SIZE:
        raise ValueError(f"NWF header must be exactly {HEADER_SIZE:#x} bytes")
    key1 = decoded_header[0:8]
    key2 = decoded_header[8:16]
    encoded = bytearray(decoded_header)
    encoded[PROTECTED_OFFSET:HEADER_SIZE] = _triple_des(
        decoded_header[PROTECTED_OFFSET:HEADER_SIZE],
        key1,
        key2,
        encrypt=False,
    )
    return bytes(encoded)


def decoded_candidate_header(record_offset: int = RECORD_OFFSET) -> bytes:
    header = bytearray(HEADER_SIZE)
    header[:VERSION_SIZE] = VERSION
    header[VERSION_SIZE:PROTECTED_OFFSET] = KEY_PADDING
    header[AUTHORIZATION_FIELD_OFFSET:AUTHORIZATION_FIELD_OFFSET + 3] = (
        encode_signed24(-1)
    )
    header[RECORD_POSITION_FIELD_OFFSET:RECORD_POSITION_FIELD_OFFSET + 3] = (
        encode_signed24(record_offset)
    )
    # Equal bytes make the header XOR seed zero.  Pinning it removes an extra
    # variable while the original below-threshold record path is exercised.
    header[0x1C] = 0
    header[0x1D] = 0
    return bytes(header)


def build_candidate(
    record_offset: int = RECORD_OFFSET,
    record_storage_size: int = RECORD_STORAGE_SIZE,
) -> bytes:
    if record_offset < HEADER_SIZE:
        raise ValueError("record offset overlaps the encoded header")
    if record_storage_size < 7:
        raise ValueError("record storage must contain the seven-byte root record")
    image = bytearray(record_offset + record_storage_size)
    image[:HEADER_SIZE] = encode_header(decoded_candidate_header(record_offset))
    image[record_offset:record_offset + 2] = APPLICATION_CODE.to_bytes(
        2, "little"
    )
    image[record_offset + 4:record_offset + 6] = MENU_PAGE.to_bytes(
        2, "little"
    )
    image[record_offset + 6] = MENU_FLAGS
    return bytes(image)


def inspect_candidate(image: bytes) -> dict[str, Any]:
    errors: list[str] = []
    if len(image) < FILE_SIZE:
        errors.append(f"file is {len(image):#x} bytes, need at least {FILE_SIZE:#x}")
        padded = image[:HEADER_SIZE].ljust(HEADER_SIZE, b"\x00")
    else:
        padded = image[:HEADER_SIZE]

    try:
        decoded = decode_header(padded)
    except ValueError as error:
        decoded = bytes(HEADER_SIZE)
        errors.append(str(error))

    version = decoded[:VERSION_SIZE]
    if version not in (b"NEPLAYERV0.98", b"NEPLAYERV0.99"):
        errors.append(f"unsupported version bytes: {version!r}")
    if decoded[:8] != PLAYER_MAGIC:
        errors.append(f"missing decoded {PLAYER_MAGIC!r} magic")

    authorization_offset = decode_signed24(
        decoded[AUTHORIZATION_FIELD_OFFSET:AUTHORIZATION_FIELD_OFFSET + 3]
    )
    record_position = decode_signed24(
        decoded[RECORD_POSITION_FIELD_OFFSET:RECORD_POSITION_FIELD_OFFSET + 3]
    )
    if authorization_offset != -1:
        end = authorization_offset + len(AUTHORIZATION_MAGIC)
        if authorization_offset < 0 or end > HEADER_SIZE:
            errors.append(f"authorization offset is outside header: {authorization_offset}")
        elif decoded[authorization_offset:end] != AUTHORIZATION_MAGIC:
            errors.append("authorization marker does not match NOAHAUTH")
    if record_position < 0 or record_position + 7 > len(image):
        errors.append(f"record position is outside file: {record_position:#x}")
        application_code = None
        menu_page = None
        menu_flags = None
    else:
        application_code = int.from_bytes(
            image[record_position:record_position + 2], "little"
        )
        menu_page = int.from_bytes(
            image[record_position + 4:record_position + 6], "little"
        )
        menu_flags = image[record_position + 6]
        if application_code != APPLICATION_CODE:
            errors.append(
                f"application code is {application_code:#06x}, expected "
                f"{APPLICATION_CODE:#06x}"
            )

    return {
        "schema": "np560-minimal-nwf-inspection-v1",
        "valid_offline_candidate": not errors,
        "original_factory_nwf": False,
        "sha256": hashlib.sha256(image).hexdigest(),
        "file_bytes": len(image),
        "version": version.decode("ascii", errors="replace"),
        "key_1_hex": padded[0:8].hex(),
        "key_2_hex": padded[8:16].hex(),
        "protected_header_blocks": PROTECTED_BLOCKS,
        "protected_header_bytes": PROTECTED_SIZE,
        "authorization_offset": authorization_offset,
        "authorization_disabled": authorization_offset == -1,
        "record_position": record_position,
        "record_position_hex": f"0x{record_position:X}",
        "application_code": application_code,
        "application_code_hex": (
            None if application_code is None else f"{application_code:04X}"
        ),
        "menu_page": menu_page,
        "menu_flags": menu_flags,
        "assumptions": [
            "version-key padding bytes 0x0D..0x0F are zero",
            "authorization offset -1 selects the guest's no-auth/no-XOR branch",
            "record base 0x1F00 exercises the guest's original paged/decrypted branch below the 0xFE00 direct-read threshold",
            "the file ends at the common 0x2000-byte extent because repeated clean runs agree only the first 32 writes are stable",
            "application record 0x1203 uses root page 0 and flags 0",
        ],
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="NWF candidate to create or inspect")
    parser.add_argument(
        "--inspect", action="store_true", help="inspect an existing file instead of creating it"
    )
    parser.add_argument("--manifest", type=Path, help="optional JSON report path")
    args = parser.parse_args()

    if args.inspect:
        image = args.file.read_bytes()
    else:
        image = build_candidate()
        args.file.parent.mkdir(parents=True, exist_ok=True)
        args.file.write_bytes(image)

    result = inspect_candidate(image)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["valid_offline_candidate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
