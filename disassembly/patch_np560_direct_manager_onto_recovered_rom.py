#!/usr/bin/env python3
"""Move only the direct-menu manager delta onto a recovered live ROM.

The clean-room builder's direct-menu mode differs from its natural scheduler
in four areas.  The large ROM-01 difference is an older loader arrangement
and must not replace the exact late-result/modal chain recovered at runtime.
The ranges below are the manager selector, direct pointer-index installer,
vendor-menu caller, guest-side text stream, and resource helpers.  They are
copied only when the recovered baseline still matches the natural builder
template at every byte.  ``--native-hierarchy`` deliberately leaves the
natural pointer-index installer and resident 1C:9748 hierarchy in place as a
negative control.  Exact 2C:C9E8/18:9A58 is a generic text-page application;
feeding it binary 0x42-byte hierarchy records proves this direct probe is not
the native catalogue/menu-manager path.

All copied code executes on the DMCU guest.  This patch does not add a QEMU
ROM-service or host-side filesystem callback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


RANGES: tuple[tuple[int, int, str], ...] = (
    (0x030080, 0x030088, "resident_manager_selector"),
    (0x03031C, 0x030328, "factory_system_main_terminal_handoff"),
    (0x061600, 0x061746, "direct_menu_pointer_index_installer"),
    (0x064900, 0x064A9A, "direct_vendor_menu_caller"),
    (0x066800, 0x066904, "direct_resource_helpers"),
    (0x1CA000, 0x1CA01E, "direct_menu_text_stream"),
)

DIRECT_TEXT_RANGE_NAMES = frozenset((
    "direct_menu_pointer_index_installer",
    "direct_menu_text_stream",
))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_image(
    baseline: bytes,
    natural_template: bytes,
    direct_template: bytes,
    *,
    native_hierarchy: bool = False,
) -> tuple[bytes, dict[str, object]]:
    if not (len(baseline) == len(natural_template) == len(direct_template)):
        raise ValueError("ROM images have different sizes")

    patched = bytearray(baseline)
    records: list[dict[str, object]] = []
    selected_ranges = tuple(
        entry for entry in RANGES
        if not (native_hierarchy and entry[2] in DIRECT_TEXT_RANGE_NAMES)
    )
    for start, end, name in selected_ranges:
        if baseline[start:end] != natural_template[start:end]:
            raise ValueError(
                f"recovered baseline no longer matches the natural template "
                f"at 0x{start:06x}..0x{end - 1:06x}"
            )
        if natural_template[start:end] == direct_template[start:end]:
            raise ValueError(f"{name} contains no direct-manager delta")
        patched[start:end] = direct_template[start:end]
        records.append({
            "name": name,
            "start": f"{start >> 16:02X}:{start & 0xFFFF:04X}",
            "end_exclusive": f"{end >> 16:02X}:{end & 0xFFFF:04X}",
            "bytes": end - start,
            "changed_bytes": sum(
                natural_template[index] != direct_template[index]
                for index in range(start, end)
            ),
        })

    metadata: dict[str, object] = {
        "copied_ranges": records,
        "menu_source": (
            "invalid_binary_hierarchy_negative_control_1c9748"
            if native_hierarchy else "isolated_crlf_stream_1ca000"
        ),
        "preserved_loader_range": "01:15EA..01:1685",
        "execution_model": "ordinary guest DMCU instructions; no host HLE",
    }
    return bytes(patched), metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--natural-template", type=Path, required=True)
    parser.add_argument("--direct-template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--native-hierarchy", action="store_true",
        help=("negative control: feed the natural binary 1C:9748 hierarchy "
              "to the generic text-page entry instead of the CR/LF probe"),
    )
    args = parser.parse_args()

    baseline = args.baseline.read_bytes()
    natural_template = args.natural_template.read_bytes()
    direct_template = args.direct_template.read_bytes()
    output, patch = patch_image(
        baseline, natural_template, direct_template,
        native_hierarchy=args.native_hierarchy,
    )
    args.output.write_bytes(output)
    print(f"installed recovered-ROM direct manager; sha256={sha256(output)}")

    if args.manifest:
        record = {
            "format": "np560-recovered-rom-direct-manager-patch-v1",
            "baseline": str(args.baseline),
            "baseline_sha256": sha256(baseline),
            "natural_template": str(args.natural_template),
            "natural_template_sha256": sha256(natural_template),
            "direct_template": str(args.direct_template),
            "direct_template_sha256": sha256(direct_template),
            "output": str(args.output),
            "output_sha256": sha256(output),
            "patch": patch,
        }
        args.manifest.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
