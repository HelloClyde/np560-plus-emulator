#!/usr/bin/env python3
"""Build a sparse experimental DMCU ROM skeleton for ABI exploration.

This is not an original-ROM reconstruction.  Each explicitly selected entry
contains either RETS or a zero-return stub; all gaps contain the reserved word
0x0F00.  Keeping the output only as long as the highest selected entry makes
the next, higher resident call fall outside QEMU's loaded ROM range and stop
in strict mode, exposing its pre-SCALL state.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


RESERVED = 0x0F00
MOV_R0_ZERO = 0x4800
MOV_R1_ZERO = 0x4810
RETS = 0xC620


@dataclass(frozen=True)
class Stub:
    address: int
    mode: str
    values: tuple[int, int] | None = None

    @property
    def display_address(self) -> str:
        return f"{self.address >> 16:02X}:{self.address & 0xFFFF:04X}"

    @property
    def words(self) -> tuple[int, ...]:
        if self.mode == "rets":
            return (RETS,)
        if self.mode == "zero":
            return (MOV_R0_ZERO, RETS)
        if self.mode == "zero32":
            return (MOV_R0_ZERO, MOV_R1_ZERO, RETS)
        assert self.values is not None
        return (0x68F0, self.values[0], 0x68F1, self.values[1], RETS)


def parse_stub(value: str) -> Stub:
    address_text, separator, mode = value.partition("=")
    try:
        segment_text, pc_text = address_text.split(":", 1)
        segment = int(segment_text, 16)
        pc = int(pc_text, 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "entry must be hexadecimal CS:PC[=rets|zero|zero32|pair:R0:R1], "
            "for example 02:BAC4"
        ) from exc
    mode = mode if separator else "rets"
    values = None
    if mode.startswith("pair:"):
        fields = mode.split(":")
        if len(fields) != 3:
            raise argparse.ArgumentTypeError("pair mode must use pair:R0:R1")
        try:
            values = (int(fields[1], 0), int(fields[2], 0))
        except ValueError as exc:
            raise argparse.ArgumentTypeError("pair return values must be integers") from exc
        if any(not 0 <= item <= 0xFFFF for item in values):
            raise argparse.ArgumentTypeError("pair return values must fit in 16 bits")
        mode = "pair"
    if mode not in {"rets", "zero", "zero32", "pair"}:
        raise argparse.ArgumentTypeError(
            "stub mode must be 'rets', 'zero', 'zero32', or 'pair:R0:R1'"
        )
    if not 0 <= segment <= 0xFF or not 0 <= pc <= 0xFFFF or pc & 1:
        raise argparse.ArgumentTypeError("entry must be an even 8:16-bit code address")
    return Stub((segment << 16) | pc, mode, values)


def build_image(stubs: list[Stub]) -> bytes:
    if not stubs:
        raise ValueError("at least one stub is required")
    occupied: dict[int, Stub] = {}
    end = 0
    for stub in stubs:
        for index, _word in enumerate(stub.words):
            offset = stub.address + index * 2
            if offset in occupied:
                raise ValueError(
                    f"stub {stub.display_address} overlaps "
                    f"{occupied[offset].display_address}"
                )
            occupied[offset] = stub
            end = max(end, offset + 2)

    image = bytearray(end)
    reserved = RESERVED.to_bytes(2, "little")
    for offset in range(0, end, 2):
        image[offset : offset + 2] = reserved
    for stub in stubs:
        for index, word in enumerate(stub.words):
            offset = stub.address + index * 2
            image[offset : offset + 2] = word.to_bytes(2, "little")
    return bytes(image)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", type=parse_stub, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    try:
        image = build_image(args.entry)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    args.output.write_bytes(image)

    manifest_path = args.manifest or args.output.with_suffix(".json")
    manifest = {
        "format": "np560-experimental-rom-skeleton-v1",
        "warning": "Not original ROM code; selected ABI exploration stubs only.",
        "byte_order": "little-endian DMCU words",
        "size": len(image),
        "fill_word": f"0x{RESERVED:04X}",
        "entries": [
            {
                "address": stub.display_address,
                "mode": stub.mode,
                **(
                    {"r0": f"0x{stub.values[0]:04X}",
                     "r1": f"0x{stub.values[1]:04X}"}
                    if stub.values is not None else {}
                ),
            }
            for stub in sorted(args.entry, key=lambda item: item.address)
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(image):,} bytes to {args.output.resolve()}")
    print(f"wrote {manifest_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
