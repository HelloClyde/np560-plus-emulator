#!/usr/bin/env python3
"""Index NP560 NAND checkpoints and isolate guest provisioning changes.

The checkpoint stores all 2048-byte page data first and all 64-byte OOB data
after it.  This tool works directly on that layout, compares checkpoints one
page at a time, and searches both physical bytes and the DMCU's pair-swapped
logical byte view.  It does not emulate or modify the proprietary guest FTL.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import mmap
from pathlib import Path
import struct
from typing import Iterable


CHECKPOINT_MAGIC = b"NP560N1\0"
HEADER_SIZE = 64
HEADER_FORMAT = "<6I2Q2I"

DEFAULT_NEEDLES = {
    "nwf-header": b"NEPLAYERV0.99",
    "lirt-name": b"lirt.nwf",
    "lirt-short": b"LIRT    NWF",
    "userinfo-name": b"USERINFO.SYS",
    "userinfo-short": b"USERINFOSYS",
    "userinfo-version": b"V1.0  ",
    "userinfo-id": b"7107169335",
    "userinfo-owner-gb18030": "阿诺".encode("gb18030"),
    "userinfo-language-gb18030": "英语".encode("gb18030"),
    "trash-short": b"TRASH   CAN",
}


@dataclass(frozen=True)
class Geometry:
    version: int
    header_size: int
    page_data: int
    page_oob: int
    pages_per_block: int
    blocks: int
    data_size: int
    oob_size: int
    data_hash: int
    oob_hash: int

    @property
    def pages(self) -> int:
        return self.pages_per_block * self.blocks


@dataclass(frozen=True)
class NeedleHit:
    name: str
    page: int
    block: int
    page_in_block: int
    offset: int
    view: str
    context_hex: str


class Checkpoint:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.file = path.open("rb")
        self.mapping = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            self.geometry = parse_geometry(self.mapping, path)
        except Exception:
            self.mapping.close()
            self.file.close()
            raise

    def close(self) -> None:
        self.mapping.close()
        self.file.close()

    def __enter__(self) -> "Checkpoint":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def page(self, page: int) -> bytes:
        geometry = self.geometry
        start = geometry.header_size + page * geometry.page_data
        return self.mapping[start:start + geometry.page_data]

    def oob(self, page: int) -> bytes:
        geometry = self.geometry
        start = (
            geometry.header_size + geometry.data_size +
            page * geometry.page_oob
        )
        return self.mapping[start:start + geometry.page_oob]


def parse_geometry(data: bytes | mmap.mmap, path: Path | str = "checkpoint") -> Geometry:
    if len(data) < HEADER_SIZE or data[:8] != CHECKPOINT_MAGIC:
        raise ValueError(f"{path}: invalid NP560 checkpoint magic")
    values = struct.unpack_from(HEADER_FORMAT, data, 8)
    geometry = Geometry(*values)
    expected_data = geometry.pages * geometry.page_data
    expected_oob = geometry.pages * geometry.page_oob
    expected_file = geometry.header_size + expected_data + expected_oob
    if geometry.header_size != HEADER_SIZE:
        raise ValueError(f"{path}: unsupported header size {geometry.header_size}")
    if geometry.data_size != expected_data or geometry.oob_size != expected_oob:
        raise ValueError(f"{path}: checkpoint geometry has inconsistent sizes")
    if len(data) != expected_file:
        raise ValueError(f"{path}: size {len(data)} != {expected_file}")
    return geometry


def pair_swap(data: bytes) -> bytes:
    swapped = bytearray(data)
    for index in range(0, len(swapped) - 1, 2):
        swapped[index], swapped[index + 1] = swapped[index + 1], swapped[index]
    return bytes(swapped)


def changed_pages(base: Checkpoint, candidate: Checkpoint) -> list[int]:
    base_layout = asdict(base.geometry)
    candidate_layout = asdict(candidate.geometry)
    for hash_field in ("data_hash", "oob_hash"):
        base_layout.pop(hash_field)
        candidate_layout.pop(hash_field)
    if base_layout != candidate_layout:
        raise ValueError("checkpoint geometries differ")
    return [
        page for page in range(candidate.geometry.pages)
        if base.page(page) != candidate.page(page) or
        base.oob(page) != candidate.oob(page)
    ]


def programmed_pages(checkpoint: Checkpoint) -> list[int]:
    erased_data = b"\xff" * checkpoint.geometry.page_data
    erased_oob = b"\xff" * checkpoint.geometry.page_oob
    return [
        page for page in range(checkpoint.geometry.pages)
        if checkpoint.page(page) != erased_data or checkpoint.oob(page) != erased_oob
    ]


def group_ranges(pages: Iterable[int]) -> list[str]:
    values = sorted(set(pages))
    if not values:
        return []
    ranges: list[str] = []
    start = previous = values[0]
    for page in values[1:]:
        if page != previous + 1:
            ranges.append(
                f"{start:08x}" if start == previous else
                f"{start:08x}-{previous:08x}"
            )
            start = page
        previous = page
    ranges.append(
        f"{start:08x}" if start == previous else
        f"{start:08x}-{previous:08x}"
    )
    return ranges


def scan_needles(
    checkpoint: Checkpoint,
    pages: Iterable[int],
    needles: dict[str, bytes],
    max_hits: int = 256,
    views: tuple[str, ...] = ("physical", "logical"),
) -> list[NeedleHit]:
    hits: list[NeedleHit] = []
    geometry = checkpoint.geometry
    for page_number in pages:
        physical = checkpoint.page(page_number)
        contents = {
            "physical": physical,
            "logical": pair_swap(physical),
        }
        for view in views:
            content = contents[view]
            for name, needle in needles.items():
                start = 0
                while len(hits) < max_hits:
                    offset = content.find(needle, start)
                    if offset < 0:
                        break
                    context_start = max(0, offset - 16)
                    context_end = min(len(content), offset + len(needle) + 32)
                    hits.append(NeedleHit(
                        name=name,
                        page=page_number,
                        block=page_number // geometry.pages_per_block,
                        page_in_block=page_number % geometry.pages_per_block,
                        offset=offset,
                        view=view,
                        context_hex=content[context_start:context_end].hex(),
                    ))
                    start = offset + 1
                if len(hits) >= max_hits:
                    return hits
    return hits


def page_summary(checkpoint: Checkpoint, page: int) -> dict[str, object]:
    data = checkpoint.page(page)
    oob = checkpoint.oob(page)
    return {
        "page": page,
        "page_hex": f"{page:08x}",
        "block": page // checkpoint.geometry.pages_per_block,
        "page_in_block": page % checkpoint.geometry.pages_per_block,
        "data_non_ff": len(data) - data.count(0xFF),
        "oob_non_ff": len(oob) - oob.count(0xFF),
        "data_prefix_hex": data[:64].hex(),
        "oob_hex": oob.hex(),
    }


def delta_page_summary(
    base: Checkpoint, checkpoint: Checkpoint, page: int,
) -> dict[str, object]:
    before = page_summary(base, page)
    after = page_summary(checkpoint, page)
    before_non_ff = int(before["data_non_ff"]) + int(before["oob_non_ff"])
    after_non_ff = int(after["data_non_ff"]) + int(after["oob_non_ff"])
    if before_non_ff and not after_non_ff:
        change = "erased"
    elif not before_non_ff and after_non_ff:
        change = "programmed"
    else:
        change = "modified"
    after.update({
        "change": change,
        "before_data_non_ff": before["data_non_ff"],
        "before_oob_non_ff": before["oob_non_ff"],
        "before_data_prefix_hex": before["data_prefix_hex"],
        "before_oob_hex": before["oob_hex"],
    })
    return after


def build_report(
    checkpoint: Checkpoint,
    *,
    base: Checkpoint | None = None,
    scan_all: bool = False,
    max_hits: int = 256,
    needles: dict[str, bytes] | None = None,
    include_pages: bool = True,
    include_default_needles: bool = True,
    views: tuple[str, ...] = ("physical", "logical"),
) -> dict[str, object]:
    if base is not None:
        pages = changed_pages(base, checkpoint)
        scope = "changed"
    elif scan_all:
        pages = programmed_pages(checkpoint)
        scope = "programmed"
    else:
        pages = []
        scope = "none"

    active_needles = dict(DEFAULT_NEEDLES) if include_default_needles else {}
    if include_default_needles:
        active_needles["root-path"] = b"0:\\lirt.nwf"
    if needles:
        active_needles.update(needles)
    hits = scan_needles(
        checkpoint, pages, active_needles, max_hits=max_hits, views=views,
    )
    return {
        "schema": "np560-nand-preprocess-v1",
        "checkpoint": str(checkpoint.path.resolve()),
        "base": str(base.path.resolve()) if base else None,
        "geometry": asdict(checkpoint.geometry),
        "scope": scope,
        "views": list(views),
        "needles": {name: value.hex() for name, value in active_needles.items()},
        "page_count": len(pages),
        "page_ranges": group_ranges(pages),
        "pages_included": include_pages,
        "pages": ([
            delta_page_summary(base, checkpoint, page) if base else
            page_summary(checkpoint, page)
            for page in pages
        ] if include_pages else []),
        "hits": [asdict(hit) for hit in hits],
        "hit_limit_reached": len(hits) >= max_hits,
    }


def print_report(report: dict[str, object]) -> None:
    geometry = report["geometry"]
    assert isinstance(geometry, dict)
    print(
        f"CHECKPOINT {report['checkpoint']}\n"
        f"GEOMETRY pages={geometry['pages_per_block']}x{geometry['blocks']} "
        f"data={geometry['page_data']} oob={geometry['page_oob']}"
    )
    print(
        f"SCOPE {report['scope']} pages={report['page_count']} "
        f"ranges={','.join(report['page_ranges']) or '-'}"
    )
    for hit in report["hits"]:
        assert isinstance(hit, dict)
        print(
            f"HIT {hit['name']} page={hit['page']:08x} "
            f"block={hit['block']:04x}+{hit['page_in_block']:02x} "
            f"offset={hit['offset']:04x} view={hit['view']}"
        )
    if not report["hits"]:
        print("HIT none")


def named_value(text: str, option: str) -> tuple[str, str]:
    if "=" not in text:
        raise argparse.ArgumentTypeError(f"{option} requires NAME=VALUE")
    name, value = text.split("=", 1)
    if not name or not value:
        raise argparse.ArgumentTypeError(f"{option} requires non-empty NAME=VALUE")
    return name, value


def custom_needles(
    text_values: Iterable[str], hex_values: Iterable[str],
) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for item in text_values:
        name, value = named_value(item, "--needle")
        result[name] = value.encode("utf-8")
    for item in hex_values:
        name, value = named_value(item, "--needle-hex")
        try:
            result[name] = bytes.fromhex(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"--needle-hex {name} has invalid hexadecimal data"
            ) from exc
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--base", type=Path)
    parser.add_argument(
        "--scan-all", action="store_true",
        help="scan every programmed page when no base checkpoint is supplied",
    )
    parser.add_argument("--max-hits", type=int, default=256)
    parser.add_argument(
        "--needles-only", action="store_true",
        help="omit per-page summaries; useful for fast full-checkpoint scans",
    )
    parser.add_argument(
        "--needle", action="append", default=[], metavar="NAME=TEXT",
        help="add a UTF-8 text signature (repeatable)",
    )
    parser.add_argument(
        "--needle-hex", action="append", default=[], metavar="NAME=HEX",
        help="add a raw hexadecimal signature (repeatable)",
    )
    parser.add_argument(
        "--no-default-needles", action="store_true",
        help="scan only signatures explicitly supplied on the command line",
    )
    parser.add_argument(
        "--view", choices=("both", "physical", "logical"), default="both",
        help="restrict byte-order views (default: both)",
    )
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    if args.base is None and not args.scan_all:
        parser.error("provide --base for a delta or --scan-all")

    try:
        extra_needles = custom_needles(args.needle, args.needle_hex)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    if args.no_default_needles and not extra_needles:
        parser.error("--no-default-needles requires at least one custom needle")
    views = (
        ("physical", "logical") if args.view == "both" else (args.view,)
    )

    with Checkpoint(args.checkpoint) as checkpoint:
        if args.base:
            with Checkpoint(args.base) as base:
                report = build_report(
                    checkpoint, base=base, max_hits=args.max_hits,
                    needles=extra_needles,
                    include_pages=not args.needles_only,
                    include_default_needles=not args.no_default_needles,
                    views=views,
                )
        else:
            report = build_report(
                checkpoint, scan_all=True, max_hits=args.max_hits,
                needles=extra_needles,
                include_pages=not args.needles_only,
                include_default_needles=not args.no_default_needles,
                views=views,
            )
    print_report(report)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"JSON {args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
