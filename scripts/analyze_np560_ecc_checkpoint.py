#!/usr/bin/env python3
"""Validate every stored NP560 sector ECC descriptor in a NAND checkpoint."""

from __future__ import annotations

import argparse
import mmap
import struct
from pathlib import Path


CHECKPOINT_MAGIC = b"NP560N1\0"
CHECKPOINT_VERSION = 1
ECC_OFFSETS = (22, 30, 38, 46)
ECC_SIGNATURE = 0x6979
SECTOR_SIZE = 512


def _build_word_tables() -> tuple[list[int], bytearray]:
    """Return XOR-of-set-bit-indices and odd-popcount tables for uint16."""
    bit_xor = [0] * 0x10000
    odd = bytearray(0x10000)
    for value in range(1, 0x10000):
        previous = value & (value - 1)
        bit = (value ^ previous).bit_length() - 1
        bit_xor[value] = bit_xor[previous] ^ bit
        odd[value] = odd[previous] ^ 1
    return bit_xor, odd


WORD_BIT_XOR, WORD_ODD = _build_word_tables()


def sector_descriptor(image: mmap.mmap | bytes, offset: int = 0) -> bytes:
    """Compute the exact 51:C1A4 descriptor for one 512-byte sector."""
    parity = 0
    nparity = 0
    for index, value in enumerate(struct.unpack_from("<256H", image, offset)):
        contribution = WORD_BIT_XOR[value]
        if WORD_ODD[value]:
            contribution ^= index << 4
            nparity ^= 0xFFFF
        parity ^= contribution
        nparity ^= contribution
    return struct.pack(
        "<4H", nparity, parity, nparity ^ parity, ECC_SIGNATURE,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument(
        "--minimum-descriptors", type=int, default=1,
        help="fail unless at least this many signed sector descriptors exist",
    )
    parser.add_argument(
        "--show-mismatches", type=int, default=8,
        help="maximum mismatch details to print",
    )
    parser.add_argument(
        "--show-partials", type=int, default=8,
        help="maximum partial-descriptor page details to print",
    )
    args = parser.parse_args()

    with args.checkpoint.open("rb") as source:
        image = mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            if len(image) < 64 or image[:8] != CHECKPOINT_MAGIC:
                raise AssertionError("not an NP560 NAND checkpoint")
            (version, header_size, page_data, page_oob, block_pages,
             blocks) = struct.unpack_from("<6I", image, 8)
            data_size, oob_size = struct.unpack_from("<2Q", image, 32)
            if version != CHECKPOINT_VERSION or header_size != 64:
                raise AssertionError(
                    f"unsupported checkpoint version/header {version}/{header_size}"
                )
            page_count = block_pages * blocks
            expected = header_size + data_size + oob_size
            if (page_data != 2048 or page_oob != 64 or
                    data_size != page_count * page_data or
                    oob_size != page_count * page_oob or
                    len(image) != expected):
                raise AssertionError(
                    "incompatible checkpoint geometry or file length: "
                    f"page={page_data}+{page_oob} blocks={blocks}x{block_pages} "
                    f"file={len(image)} expected={expected}"
                )

            data_base = header_size
            oob_base = data_base + data_size
            non_erased_oob_pages = 0
            pages_with_ecc = 0
            full_ecc_pages = 0
            partial_ecc_pages = 0
            descriptors = 0
            mismatch_count = 0
            mismatches: list[str] = []
            partials: list[str] = []

            for page in range(page_count):
                page_oob_offset = oob_base + page * page_oob
                oob = image[page_oob_offset:page_oob_offset + page_oob]
                if oob != b"\xff" * page_oob:
                    non_erased_oob_pages += 1
                signed = [
                    struct.unpack_from("<H", oob, offset + 6)[0] ==
                    ECC_SIGNATURE
                    for offset in ECC_OFFSETS
                ]
                if not any(signed):
                    continue
                pages_with_ecc += 1
                if all(signed):
                    full_ecc_pages += 1
                else:
                    partial_ecc_pages += 1
                    if len(partials) < args.show_partials:
                        partials.append(
                            f"page=0x{page:05x} sectors=" +
                            ",".join(
                                str(sector) for sector, present in enumerate(signed)
                                if present
                            )
                        )
                for sector, present in enumerate(signed):
                    if not present:
                        continue
                    descriptors += 1
                    actual = oob[ECC_OFFSETS[sector]:ECC_OFFSETS[sector] + 8]
                    data_offset = (
                        data_base + page * page_data + sector * SECTOR_SIZE
                    )
                    expected_descriptor = sector_descriptor(image, data_offset)
                    if actual != expected_descriptor:
                        mismatch_count += 1
                        if len(mismatches) < args.show_mismatches:
                            mismatches.append(
                                f"page=0x{page:05x} sector={sector} "
                                f"actual={actual.hex()} "
                                f"expected={expected_descriptor.hex()}"
                            )

            print(
                "NP560 ECC checkpoint scan: "
                f"pages={page_count} non_erased_oob={non_erased_oob_pages} "
                f"ecc_pages={pages_with_ecc} full={full_ecc_pages} "
                f"partial={partial_ecc_pages} descriptors={descriptors}"
            )
            if partials:
                print("PARTIAL_ECC=" + "; ".join(partials))
            if mismatch_count:
                raise AssertionError(
                    f"{mismatch_count} stored ECC descriptors do not match "
                    "page data:\n" +
                    "\n".join(mismatches)
                )
            if descriptors < args.minimum_descriptors:
                raise AssertionError(
                    f"only {descriptors} descriptors, expected at least "
                    f"{args.minimum_descriptors}"
                )
            print(f"ECC_MATCH={descriptors}/{descriptors}")
        finally:
            image.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
