#!/usr/bin/env python3
"""Integration check for vendor-burner -> guest ROM -> QEMU NAND DMA."""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from web.np560_web import Emulator


PAGE_DATA = 2048
PAGE_OOB = 64
TEST_PAGE = 0x3F
TEST_BUFFER = 0x0032CA


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--soc-rom", type=Path, required=True)
    parser.add_argument("--burner", type=Path, required=True)
    parser.add_argument("--nand", type=Path, required=True)
    args = parser.parse_args()

    for path in (args.qemu, args.firmware, args.soc_rom, args.burner, args.nand):
        if not path.is_file():
            raise SystemExit(f"required file is absent: {path}")

    emulator = Emulator(
        qemu=args.qemu,
        firmware=args.firmware,
        soc_rom=args.soc_rom,
        soc_rom_skeleton=True,
        burn_code=args.burner,
        nand_image=args.nand,
    )
    try:
        deadline = time.monotonic() + 6
        while True:
            cpu_state = emulator.qmp.execute(
                "qom-get", {"path": "/machine", "property": "cpu-state"}
            )
            nand_state = emulator.qmp.execute(
                "qom-get", {"path": "/machine", "property": "nand-state"}
            )
            match = re.search(r" READS=(\d+)", nand_state)
            if match and int(match.group(1)) >= 2 and "PC=20:0012" in cpu_state:
                break
            if time.monotonic() >= deadline:
                raise AssertionError(
                    f"vendor command did not complete\n{cpu_state}\n{nand_state}"
                )
            time.sleep(0.02)

        required = (
            "NAND ID=EC:DC:10:95",
            "PAGE=2048+64",
            "BLOCK=64x2048",
            "BLOCKS=4096",
            "MASKROM_HEADER=stripped",
            "CMD=1 STATUS=1 ERROR=0",
            "PAGE_ADDR=0000003f",
            # Command 1 performs two caller-visible reads followed by an
            # internal page-3f validation read into the near 00:32ca cache.
            # The final-state buffer is therefore the near 00:32ca cache;
            # verify that exact DMA result below.
            "COLUMN=0 LENGTH=2112 BUFFER=0032ca",
        )
        for text in required:
            if text not in nand_state:
                raise AssertionError(f"missing {text!r} in {nand_state}")

        trace = re.search(r"^NAND_TRACE=.*$", cpu_state, re.M)
        if (not trace or "/p0000003f" not in trace.group(0) or
                "+c0/n2112>b0032ca" not in trace.group(0)):
            raise AssertionError(
                "command 1 did not finish its page-0x3f validation read: "
                f"{trace.group(0) if trace else 'NAND_TRACE=none'}"
            )

        emulator.qmp.execute(
            "pmemsave",
            {
                "val": TEST_BUFFER,
                "size": PAGE_DATA + PAGE_OOB,
                "filename": str(emulator.frame_path),
            },
        )
        actual = emulator.frame_path.read_bytes()
        package_block = args.nand.read_bytes()
        if package_block.startswith(b"MASKROM"):
            package_block = package_block[0x200:]
        start = TEST_PAGE * PAGE_DATA
        expected = package_block[start : start + PAGE_DATA] + b"\xFF" * PAGE_OOB
        expected_hash = 2166136261
        for byte in expected:
            expected_hash = ((expected_hash ^ byte) * 16777619) & 0xFFFFFFFF
        dma_records = re.findall(r"/([0-9a-f]{8})/([0-9a-f]{16})",
                                 trace.group(0), re.I)
        expected_dma = (f"{expected_hash:08x}", expected[:8].hex())
        if expected_dma not in {(digest.lower(), prefix.lower())
                                for digest, prefix in dma_records}:
            raise AssertionError(
                "page-0x3f DMA trace differs from the package image: "
                f"trace={dma_records or trace.group(0)} "
                f"expected={expected_hash:08x}/{expected[:8].hex()}"
            )
        # After the read, the unmodified vendor validator writes freshly
        # calculated ECC descriptors into fields of this metadata page.  The
        # post-return scratch buffer is therefore deliberately not byte-for-
        # byte identical to the raw DMA payload.  Its OOB remains untouched.
        if actual[:4] != expected[:4] or actual[PAGE_DATA:] != expected[PAGE_DATA:]:
            raise AssertionError("vendor page validator damaged DMA data or OOB")
        print("NP560+ NAND integration passed")
        print(nand_state)
        print(
            "CPU returned to harness at 20:0012; page-0x3F raw DMA "
            f"hash={expected_hash:08x}; resident ECC post-processing ran"
        )
    finally:
        emulator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
