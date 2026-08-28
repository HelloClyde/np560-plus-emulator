#!/usr/bin/env python3
"""Disassemble an auxiliary NP560+ big-endian 16-bit word image.

Unlike NP560.PRG, the USB loader and NAND burner store each DMCU word in
big-endian byte order and are mapped at non-zero CS:PC addresses.  This tool
reuses the verified instruction decoder while preserving those mappings.
"""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from pathlib import Path

import np560_disasm as dmcu


def parse_number(value: str) -> int:
    return int(value, 0)


def parse_address(value: str) -> dmcu.Address:
    try:
        segment_text, pc_text = value.split(":", 1)
        segment = int(segment_text, 16)
        pc = int(pc_text, 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "address must use hexadecimal CS:PC notation, for example 00:1000"
        ) from exc
    if not 0 <= segment <= 0xFF or not 0 <= pc <= 0xFFFF:
        raise argparse.ArgumentTypeError("address is outside the 8:16-bit CS:PC range")
    return dmcu.Address(segment, pc)


def write_listing(
    path: Path,
    image: Path,
    image_offset: int,
    byte_order: str,
    base: dmcu.Address,
    decoded: dict[int, dmcu.Instruction],
    xrefs: dict[int, list[dmcu.Address]],
    seed_names: dict[dmcu.Address, str],
    padded_word_count: int,
) -> None:
    call_targets: set[int] = set()
    for instruction in decoded.values():
        if instruction.flow != "call":
            continue
        for target in instruction.targets:
            target_index = dmcu.index_for_address(
                target, base.segment, padded_word_count
            )
            if target_index is not None:
                call_targets.add(target_index)

    lines = [
        f"; Reachable DMCU code from {image.name}",
        "; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)",
        f"; source file offset: 0x{image_offset:X}",
        f"; source word byte order: {byte_order}",
        f"; source file word 0 maps to {base}",
        "; addresses are byte-addressed CS:PC; words are in CPU numeric order",
        "",
    ]
    previous_end: int | None = None
    for index in sorted(decoded):
        instruction = decoded[index]
        if previous_end is not None and index > previous_end:
            lines.append(
                f"; ---- gap: {index - previous_end} word(s), data or unreachable code ----"
            )
            lines.append("")

        if instruction.address in seed_names:
            lines.append(f"{seed_names[instruction.address]}:")
        elif index in call_targets:
            lines.append(
                f"sub_{instruction.address.segment:02X}_{instruction.address.pc:04X}:"
            )
        elif index in xrefs:
            lines.append(
                f"loc_{instruction.address.segment:02X}_{instruction.address.pc:04X}:"
            )

        refs = xrefs.get(index, [])
        if refs:
            suffix = " ..." if len(refs) > 12 else ""
            lines.append("; xref: " + ", ".join(map(str, refs[:12])) + suffix)
        raw = " ".join(f"{value:04X}" for value in instruction.words)
        note = f" ; {instruction.note}" if instruction.note else ""
        lines.append(f"{instruction.address}  {raw:<9}  {instruction.text}{note}")
        previous_end = max(previous_end or 0, index + instruction.size)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(
    path: Path,
    image: Path,
    selected: bytes,
    image_offset: int,
    byte_order: str,
    base: dmcu.Address,
    seeds: list[dmcu.Address],
    decoded: dict[int, dmcu.Instruction],
    unresolved: Counter[dmcu.Address],
    conflicts: list[tuple[dmcu.Address, int]],
) -> None:
    calls = [instruction for instruction in decoded.values() if instruction.flow == "call"]
    unknown = [instruction for instruction in decoded.values() if instruction.text.startswith(".word")]
    lines = [
        f"# {image.name} DMCU auxiliary-image report",
        "",
        f"- Source: `{image}`",
        f"- Selected file range: `0x{image_offset:X}..0x{image_offset + len(selected):X}`",
        f"- Size: {len(selected):,} bytes / {len(selected) // 2:,} words",
        f"- SHA-256: `{hashlib.sha256(selected).hexdigest()}`",
        f"- 16-bit word byte order: `{byte_order}`",
        f"- Mapping: source word 0 = `{base}`",
        "- Entry seeds: " + ", ".join(f"`{seed}`" for seed in seeds),
        "",
        "## Results",
        "",
        f"- Reachable instructions: {len(decoded):,}",
        f"- Call instructions: {len(calls):,}",
        f"- Unknown/reserved frontiers: {len(unknown):,}",
        f"- Overlapping decode targets: {len(conflicts):,}",
        "",
        "## Unresolved targets",
        "",
    ]
    if unresolved:
        lines.extend(
            f"- `{address}`: {count} reference(s)"
            for address, count in unresolved.most_common(40)
        )
    else:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--base", type=parse_address, required=True)
    parser.add_argument("--entry", type=parse_address, action="append")
    parser.add_argument("--endian", choices=("big", "little"), default="big")
    parser.add_argument("--offset", type=parse_number, default=0)
    parser.add_argument("--length", type=parse_number)
    parser.add_argument("--name")
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).resolve().parent
    )
    args = parser.parse_args()

    image = args.image.resolve()
    all_bytes = image.read_bytes()
    end = len(all_bytes) if args.length is None else args.offset + args.length
    if args.offset < 0 or end > len(all_bytes) or end < args.offset:
        raise SystemExit("selected file range is outside the image")
    selected = all_bytes[args.offset:end]
    if not selected or len(selected) & 1:
        raise SystemExit("selected image must contain a non-zero even number of bytes")

    source_words = [
        int.from_bytes(selected[offset : offset + 2], args.endian)
        for offset in range(0, len(selected), 2)
    ]
    # The shared decoder maps list index zero to CS:0000.  Padding shifts a
    # non-zero-PC image into the correct location without fabricating seeds in
    # the padding, so it never appears in the reachable listing.
    if args.base.pc & 1:
        raise SystemExit("DMCU code images must start on an even byte address")
    words = [0] * (args.base.pc // 2) + source_words
    seeds = args.entry or [args.base]
    seed_names = {
        address: ("entry" if index == 0 else f"entry_{index}")
        for index, address in enumerate(seeds)
    }
    decoded, xrefs, unresolved, conflicts = dmcu.analyse(
        words, args.base.segment, seeds
    )

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_name = args.name or image.stem
    listing = output_dir / f"{output_name}_reachable.asm"
    report = output_dir / f"{output_name}_report.md"
    write_listing(
        listing, image, args.offset, args.endian, args.base, decoded, xrefs,
        seed_names, len(words),
    )
    write_report(
        report, image, selected, args.offset, args.endian, args.base, seeds,
        decoded, unresolved, conflicts,
    )
    print(f"decoded {len(decoded):,} reachable instructions")
    print(f"wrote {listing}")
    print(f"wrote {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
