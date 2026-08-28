#!/usr/bin/env python3
"""Cross-check reconstructed-ROM overlays against QEMU executable aliases.

The guest installs application code through the DMCU data bus.  Every such
destination must therefore be backed by the same RAMBlock on QEMU's data and
code address spaces.  A missing alias is otherwise silent: the ROM builds and
boots, but instruction fetch keeps seeing the old flat PRG bytes.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFINE_RE = re.compile(
    r"^#define\s+(NP560_[A-Z0-9_]+)\s+(0x[0-9a-fA-F]+)u?\s*$",
    re.MULTILINE,
)
LATE_ARRAY_RE = re.compile(
    r"static const NP560ProgramOverlay np560_late_overlays\[\]\s*=\s*\{"
    r"(?P<body>.*?)\n\};",
    re.DOTALL,
)
LATE_ENTRY_RE = re.compile(
    r"\{\s*(?P<base>[^,]+),\s*(?P<size>[^,]+),\s*\"",
    re.DOTALL,
)
DMCU_PROGRAM_BASE = 0x200000


def parse_integer(expression: str, defines: dict[str, int]) -> int:
    expression = expression.strip()
    if expression in defines:
        return defines[expression]
    if re.fullmatch(r"0x[0-9a-fA-F]+u?", expression):
        return int(expression.rstrip("uU"), 16)
    raise ValueError(f"unsupported overlay expression: {expression!r}")


def qemu_executable_ranges(source: Path) -> list[tuple[int, int, str]]:
    text = source.read_text(encoding="utf-8")
    defines = {name: int(value, 16) for name, value in DEFINE_RE.findall(text)}
    ranges: list[tuple[int, int, str]] = []

    # Individually declared aliases use matching ..._BASE/..._SIZE macros.
    for name, base in defines.items():
        if not name.endswith("_BASE"):
            continue
        size_name = name[:-4] + "SIZE"
        if size_name in defines:
            ranges.append((base, base + defines[size_name], name))

    # The large late-overlay table also contains a few literal base/size pairs.
    match = LATE_ARRAY_RE.search(text)
    if not match:
        raise ValueError("np560_late_overlays[] was not found")
    body = re.sub(r"/\*.*?\*/", "", match.group("body"), flags=re.DOTALL)
    body = re.sub(r"//.*?$", "", body, flags=re.MULTILINE)
    for index, entry in enumerate(LATE_ENTRY_RE.finditer(body)):
        base = parse_integer(entry.group("base"), defines)
        size = parse_integer(entry.group("size"), defines)
        ranges.append((base, base + size, f"np560_late_overlays[{index}]"))
    return ranges


def parse_far_address(value: str) -> int:
    return int(value.replace(":", ""), 16)


def uncovered_application_overlays(
    manifest: Path,
    ranges: list[tuple[int, int, str]],
) -> list[dict[str, object]]:
    document = json.loads(manifest.read_text(encoding="utf-8"))
    missing: list[dict[str, object]] = []
    for overlay in document["application_main_chain"]:
        base = parse_far_address(str(overlay["destination"]))
        limit = base + int(overlay["bytes"])
        # Destinations below segment 20 are emitted directly into the
        # reconstructed resident SoC ROM.  They do not replace immutable PRG
        # code and therefore do not require a writable data/code alias.
        if base < DMCU_PROGRAM_BASE:
            continue
        if not any(start <= base and end >= limit for start, end, _ in ranges):
            missing.append(overlay)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--qemu-source",
        type=Path,
        default=Path(__file__).resolve().parent / "hw" / "dmcu" / "np560.c",
    )
    args = parser.parse_args()

    ranges = qemu_executable_ranges(args.qemu_source)
    missing = uncovered_application_overlays(args.manifest, ranges)
    print(
        f"application overlays: executable ranges={len(ranges)} "
        f"missing={len(missing)}"
    )
    for overlay in missing:
        print(
            f"MISSING {overlay['destination']}+0x{int(overlay['bytes']):x} "
            f"from {overlay['source']}"
        )
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
