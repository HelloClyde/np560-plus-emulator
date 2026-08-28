#!/usr/bin/env python3
"""Inspect the block layout used by Noah NP560+ ``.upd`` packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path


HEADER_SIZE = 0x40
SIGNATURE_SIZE = 0x20
CHECKSUM_OFFSET = 0x20
SIZE_TABLE_OFFSET = 0x24
BLOCK_SLOTS = 4
MASKROM_HEADER_SIZE = 0x200


class UpdateFormatError(ValueError):
    """Raised when an update package is structurally inconsistent."""


@dataclass(frozen=True)
class MaskRomHeader:
    signature: str
    page_count: int
    field_24: int
    declared_block_size: int


@dataclass(frozen=True)
class UpdateBlock:
    slot: int
    offset: int
    size: int
    sha256: str
    kind: str
    maskrom: MaskRomHeader | None = None


@dataclass(frozen=True)
class UpdateImage:
    path: str
    signature: str
    size: int
    checksum: int
    calculated_checksum: int
    blocks: tuple[UpdateBlock, ...]

    @property
    def checksum_valid(self) -> bool:
        return self.checksum == self.calculated_checksum


def _cstring(data: bytes | memoryview) -> str:
    return bytes(data).split(b"\0", 1)[0].decode("ascii", errors="replace")


def word_swap(data: bytes | memoryview) -> bytes:
    """Convert the updater's byte order to the little-endian ``.PRG`` order."""
    raw = bytes(data)
    if len(raw) & 1:
        raise UpdateFormatError("a 16-bit word image has an odd byte count")
    converted = bytearray(len(raw))
    converted[0::2] = raw[1::2]
    converted[1::2] = raw[0::2]
    return bytes(converted)


def _classify_block(
    slot: int, block: memoryview
) -> tuple[str, MaskRomHeader | None]:
    if len(block) >= MASKROM_HEADER_SIZE and bytes(block[:7]) == b"MASKROM":
        page_count, field_24, declared_size = struct.unpack_from("<III", block, 0x20)
        maskrom = MaskRomHeader(
            signature=_cstring(block[:SIGNATURE_SIZE]),
            page_count=page_count,
            field_24=field_24,
            declared_block_size=declared_size,
        )
        if declared_size != len(block):
            raise UpdateFormatError(
                f"MASKROM declares 0x{declared_size:x} bytes, "
                f"block contains 0x{len(block):x}"
            )
        expected_pages = (len(block) + 0x1FF) // 0x200
        if page_count != expected_pages:
            raise UpdateFormatError(
                f"MASKROM declares {page_count} pages, "
                f"size requires {expected_pages}"
            )
        return "nand-image", maskrom
    if len(block) == 0x400000:
        return "program-word-image", None
    if slot == 0 and len(block) >= 4 and bytes(block[:2]) == b"\xadQ":
        return "burner-code", None
    if slot == 1 and len(block) >= 4 and bytes(block[:2]) == b"\xadS":
        return "driver-code", None
    return "loader-code", None


def parse_update(path: Path, *, strict_checksum: bool = True) -> UpdateImage:
    data = path.read_bytes()
    if len(data) < HEADER_SIZE:
        raise UpdateFormatError("file is shorter than the 0x40-byte header")

    signature = _cstring(data[:SIGNATURE_SIZE])
    if not signature.startswith("NP560+"):
        raise UpdateFormatError(f"unexpected package signature {signature!r}")

    checksum = struct.unpack_from("<I", data, CHECKSUM_OFFSET)[0]
    sizes = struct.unpack_from(f"<{BLOCK_SLOTS}I", data, SIZE_TABLE_OFFSET)
    expected_size = HEADER_SIZE + sum(sizes)
    if expected_size != len(data):
        raise UpdateFormatError(
            f"size table resolves to 0x{expected_size:x}, "
            f"file is 0x{len(data):x} bytes"
        )

    # The legacy packer sums the 0x20-byte signature field and all payload
    # bytes.  The checksum and size table themselves are deliberately omitted.
    calculated_checksum = (sum(data[:SIGNATURE_SIZE]) + sum(data[HEADER_SIZE:])) & 0xFFFFFFFF
    if strict_checksum and calculated_checksum != checksum:
        raise UpdateFormatError(
            f"checksum mismatch: stored 0x{checksum:08x}, "
            f"calculated 0x{calculated_checksum:08x}"
        )

    blocks: list[UpdateBlock] = []
    offset = HEADER_SIZE
    view = memoryview(data)
    for slot, size in enumerate(sizes):
        if not size:
            continue
        payload = view[offset : offset + size]
        kind, maskrom = _classify_block(slot, payload)
        blocks.append(
            UpdateBlock(
                slot=slot,
                offset=offset,
                size=size,
                sha256=hashlib.sha256(payload).hexdigest(),
                kind=kind,
                maskrom=maskrom,
            )
        )
        offset += size

    return UpdateImage(
        path=str(path.resolve()),
        signature=signature,
        size=len(data),
        checksum=checksum,
        calculated_checksum=calculated_checksum,
        blocks=tuple(blocks),
    )


def verify_program_block(update_path: Path, program_path: Path) -> int:
    """Return the slot containing the byte-swapped copy of ``program_path``."""
    image = parse_update(update_path)
    package = update_path.read_bytes()
    expected = program_path.read_bytes()
    for block in image.blocks:
        if block.kind != "program-word-image":
            continue
        payload = package[block.offset : block.offset + block.size]
        if word_swap(payload) == expected:
            return block.slot
    raise UpdateFormatError(f"{program_path.name} is not present in word-swapped form")


def extract_update(
    update_path: Path, output_dir: Path, *, slots: set[int] | None = None
) -> dict[int, Path]:
    """Extract selected update slots in the byte order expected by QEMU."""
    image = parse_update(update_path)
    package = update_path.read_bytes()
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: dict[int, Path] = {}
    names = {
        "burner-code": "BURN_NAND_FLASH_CODE.bin",
        "driver-code": "NP560_UPDATE_DRIVER.bin",
        "program-word-image": "NP560.PRG",
        "nand-image": "NP560_NAND_IMAGE.bin",
    }
    for block in image.blocks:
        if slots is not None and block.slot not in slots:
            continue
        payload = package[block.offset : block.offset + block.size]
        if block.kind == "program-word-image":
            payload = word_swap(payload)
        destination = output_dir / names.get(
            block.kind, f"block{block.slot}.bin"
        )
        destination.write_bytes(payload)
        extracted[block.slot] = destination
    return extracted


def _json_ready(image: UpdateImage) -> dict:
    result = asdict(image)
    result["checksum_valid"] = image.checksum_valid
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("update", type=Path)
    parser.add_argument("--program", type=Path, help="verify the embedded NP560.PRG")
    parser.add_argument(
        "--extract-dir", type=Path,
        help="extract payloads (program is converted to CPU byte order)",
    )
    parser.add_argument(
        "--extract-slot", action="append", type=int, choices=range(BLOCK_SLOTS),
        help="extract only this slot; may be repeated",
    )
    parser.add_argument(
        "--allow-bad-checksum", action="store_true",
        help="report rather than reject a checksum mismatch",
    )
    args = parser.parse_args()

    image = parse_update(args.update, strict_checksum=not args.allow_bad_checksum)
    report = _json_ready(image)
    if args.program:
        report["program_slot"] = verify_program_block(args.update, args.program)
    if args.extract_dir:
        selected = set(args.extract_slot) if args.extract_slot else None
        report["extracted"] = {
            str(slot): str(path.resolve())
            for slot, path in extract_update(
                args.update, args.extract_dir, slots=selected
            ).items()
        }
    elif args.extract_slot:
        parser.error("--extract-slot requires --extract-dir")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
