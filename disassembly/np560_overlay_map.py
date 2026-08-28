#!/usr/bin/env python3
"""Build and validate the NP560 reconstructed runtime-overlay map.

The ROM builder is the source of truth for recovered destination/source/size
triples.  QEMU must independently expose every executable destination as a
writable alias on its code bus.  A missing code alias is particularly subtle:
the guest loader can read back the correct bytes through the data bus while
the CPU continues to fetch unrelated immutable NOR bytes.

This tool turns that failure mode into a deterministic preflight check and
also resolves runtime PCs back to their linked PRG source ranges.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QEMU_SOURCE = ROOT / "qemu-dmcu" / "hw" / "dmcu" / "np560.c"
DEFAULT_OUTPUT = ROOT / "tmp" / "np560-overlay-map.json"

# These older builder symbols predate the *_DATA_OVERLAY_* naming rule.  Both
# are copied by guest installer code and intentionally remain non-executable
# on the Harvard instruction bus.
BUILDER_DATA_ONLY_OVERLAYS = frozenset({
    "APPLICATION_USERINFO_LITERAL",
    "APPLICATION_BYTE_CLASSIFY_TABLE",
})

# Keep direct ``python disassembly/np560_overlay_map.py`` invocation working
# as well as package/module execution.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True, order=True)
class OverlaySpec:
    destination: int
    size: int
    name: str
    source: int | None
    role: str

    @property
    def end(self) -> int:
        return self.destination + self.size


@dataclass(frozen=True, order=True)
class QemuMapping:
    base: int
    size: int
    symbol: str
    code: bool
    source: int | None = None

    @property
    def end(self) -> int:
        return self.base + self.size


def _integer_expression(expression: str, names: dict[str, int]) -> int | None:
    """Evaluate the small integer-only subset used by C ``#define`` lines."""

    expression = re.sub(r"(?<=[0-9a-fA-F])[uUlL]+\b", "",
                        expression.strip())
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return None

    def visit(node: ast.AST) -> int:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.Name) and node.id in names:
            return names[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.LShift):
                return left << right
            if isinstance(node.op, ast.RShift):
                return left >> right
        raise ValueError

    try:
        return visit(tree)
    except (ValueError, ZeroDivisionError):
        return None


def parse_defines(source: str) -> dict[str, int]:
    values: dict[str, int] = {}
    pending = [
        (match.group(1), match.group(2).split("/*", 1)[0].strip())
        for match in re.finditer(
            r"^\s*#define\s+([A-Za-z_]\w*)\s+([^\r\n]+)",
            source,
            re.MULTILINE,
        )
        if "(" not in match.group(1)
    ]
    # Resolve simple references regardless of declaration order.
    while pending:
        progress = False
        unresolved: list[tuple[str, str]] = []
        for name, expression in pending:
            value = _integer_expression(expression, values)
            if value is None:
                unresolved.append((name, expression))
            else:
                values[name] = value
                progress = True
        if not progress:
            break
        pending = unresolved
    return values


def collect_builder_overlays() -> list[OverlaySpec]:
    # Import lazily so unit tests can exercise the parsers without loading the
    # large builder module.
    from disassembly import build_np560_reconstructed_rom as rom

    result: list[OverlaySpec] = []
    suffix = "_OVERLAY_DESTINATION"
    for variable, destination in vars(rom).items():
        if not variable.endswith(suffix) or not isinstance(destination, int):
            continue
        prefix = variable[: -len(suffix)]
        size = getattr(rom, f"{prefix}_OVERLAY_SIZE", None)
        if not isinstance(size, int) or size <= 0 or destination < 0x200000:
            continue
        source = getattr(rom, f"{prefix}_OVERLAY_SOURCE", None)
        if not isinstance(source, int):
            source = None
        # The builder deliberately uses *_DATA_OVERLAY_* for Harvard data
        # islands that must remain unrelated code on the instruction bus.
        role = "data" if (
            "_DATA_" in prefix
            or prefix.endswith("_DATA")
            or prefix in BUILDER_DATA_ONLY_OVERLAYS
        ) else "code"
        result.append(OverlaySpec(destination, size, prefix, source, role))
    return sorted(result)


def _resolve_token(token: str, defines: dict[str, int]) -> int | None:
    token = token.strip()
    return defines.get(token, _integer_expression(token, defines))


def parse_qemu_mappings(source: str) -> list[QemuMapping]:
    defines = parse_defines(source)
    result: list[QemuMapping] = []

    # The complete 24-bit data bus is ordinary writable RAM.  Record that
    # broad backing before adding its more specific fixed-source aliases, so
    # guest-copied data overlays do not look like missing instruction maps.
    if (
        re.search(
            r"memory_region_init_ram\(\s*&s->data,.*?DMCU_DATA_SIZE",
            source,
            re.DOTALL,
        )
        and re.search(
            r"memory_region_add_subregion\(\s*get_system_memory\(\),\s*0,"
            r"\s*&s->data\s*\)",
            source,
            re.DOTALL,
        )
    ):
        result.append(QemuMapping(
            0,
            1 << 24,
            "DMCU_DATA_SIZE",
            False,
        ))

    array_match = re.search(
        r"static\s+const\s+NP560ProgramOverlay\s+"
        r"np560_late_overlays\[\]\s*=\s*\{(?P<body>.*?)\n\};",
        source,
        re.DOTALL,
    )
    if array_match:
        for entry in re.finditer(r"\{(?P<body>[^{}]+)\}",
                                 array_match.group("body"), re.DOTALL):
            body = re.sub(r"/\*.*?\*/", "", entry.group("body"),
                          flags=re.DOTALL)
            fields = [field.strip() for field in body.split(",") if field.strip()]
            if len(fields) < 4:
                continue
            base = _resolve_token(fields[0], defines)
            size = _resolve_token(fields[1], defines)
            if base is None or size is None:
                continue
            code = fields[3] != "NULL"
            code_source = (
                _resolve_token(fields[4], defines)
                if code and len(fields) >= 5 else None
            )
            if (
                code
                and code_source is None
                and base >= defines.get(
                    "NP560_RESOURCE_BUFFER_CODE_BANK_BASE", 1 << 32)
                and base + size <= defines.get(
                    "NP560_RESOURCE_BUFFER_CODE_BANK_LIMIT", 0)
            ):
                code_source = base + defines.get(
                    "NP560_RESOURCE_BUFFER_CODE_SOURCE_DELTA", 0)
            result.append(QemuMapping(
                base, size, fields[0], code, code_source,
            ))

    # Immutable same-linked data islands use direct aliases into the loaded
    # PRG instead of writable late-overlay RAM.  They are still required
    # Harvard data-bus mappings and must satisfy *_DATA_OVERLAY_* preflights.
    for array_match in re.finditer(
        r"static\s+const\s+NP560FixedDataAlias\s+\w+\[\]\s*=\s*"
        r"\{(?P<body>.*?)\n\};",
        source,
        re.DOTALL,
    ):
        for entry in re.finditer(r"\{(?P<body>[^{}]+)\}",
                                 array_match.group("body"), re.DOTALL):
            body = re.sub(r"/\*.*?\*/", "", entry.group("body"),
                          flags=re.DOTALL)
            fields = [field.strip() for field in body.split(",") if field.strip()]
            if len(fields) < 4:
                continue
            base = _resolve_token(fields[0], defines)
            size = _resolve_token(fields[2], defines)
            if base is None or size is None:
                continue
            source_address = _resolve_token(fields[1], defines)
            result.append(QemuMapping(
                base, size, fields[0], False, source_address,
            ))

    # Early overlays predate the table.  Count only aliases explicitly wired
    # to ``s->code``; merely defining or seeding RAM is not enough.
    for match in re.finditer(
        r"memory_region_init_alias\(\s*&s->code_[^,]+,.*?&s->data,\s*"
        r"(?P<base>[A-Za-z_]\w*|0x[0-9a-fA-F]+[uUlL]*),\s*"
        r"(?P<size>[A-Za-z_]\w*|0x[0-9a-fA-F]+[uUlL]*)\s*\);\s*"
        r"memory_region_add_subregion_overlap\(\s*&s->code,",
        source,
        re.DOTALL,
    ):
        base = _resolve_token(match.group("base"), defines)
        size = _resolve_token(match.group("size"), defines)
        if base is not None and size is not None:
            result.append(QemuMapping(base, size, match.group("base"), True))

    # A few exact early Harvard windows alias the immutable PRG directly
    # instead of using the late-overlay table.  Their alias offset is the
    # linked source while the following code-subregion address is the runtime
    # destination; retain both so source and runtime-patch audits can see the
    # same mapping that QEMU installs.
    for match in re.finditer(
        r"memory_region_init_alias\(\s*&s->code_[^,]+,.*?&s->program,\s*"
        r"(?P<source>[^,]+),\s*"
        r"(?P<size>[A-Za-z_]\w*|0x[0-9a-fA-F]+[uUlL]*)\s*\);\s*"
        r"memory_region_add_subregion_overlap\(\s*&s->code,\s*"
        r"(?P<base>[A-Za-z_]\w*|0x[0-9a-fA-F]+[uUlL]*),",
        source,
        re.DOTALL,
    ):
        program_names = dict(defines)
        program_names.setdefault("DMCU_PROGRAM_BASE", 0x200000)
        base = _resolve_token(match.group("base"), defines)
        size = _resolve_token(match.group("size"), defines)
        source_expression = " ".join(match.group("source").split())
        source_offset = _resolve_token(source_expression, program_names)
        if base is not None and size is not None and source_offset is not None:
            result.append(QemuMapping(
                base,
                size,
                match.group("base"),
                True,
                source_offset + program_names["DMCU_PROGRAM_BASE"],
            ))

    # De-duplicate table/legacy declarations while retaining data-vs-code.
    return sorted(set(result))


def covering_mapping(spec: OverlaySpec,
                     mappings: Iterable[QemuMapping]) -> QemuMapping | None:
    matches = [
        mapping for mapping in mappings
        if not (spec.role == "code" and not mapping.code)
        and mapping.base <= spec.destination and mapping.end >= spec.end
    ]
    # A broad historical overlay may contain a later, exact Harvard window.
    # QEMU's overlapping subregions select that narrow window, so the audit
    # must do the same instead of returning the first address-sorted range.
    return min(matches, key=lambda mapping: mapping.size, default=None)


def missing_mappings(overlays: Iterable[OverlaySpec],
                     mappings: Iterable[QemuMapping]) -> list[OverlaySpec]:
    mapping_list = list(mappings)
    return [spec for spec in overlays
            if covering_mapping(spec, mapping_list) is None]


def overlapping_overlays(overlays: Iterable[OverlaySpec]) -> list[tuple[str, str]]:
    ordered = sorted(overlays)
    collisions: list[tuple[str, str]] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            if right.destination >= left.end:
                break
            # Identical aliases occur in the builder under a few historical
            # names; retain them in JSON but do not call them a collision.
            if (left.destination, left.size, left.source, left.role) == (
                    right.destination, right.size, right.source, right.role):
                continue
            # Code and data occupy independent Harvard buses, so an exact
            # address overlap across roles is intentional rather than a
            # collision.  Likewise, a later source-proven superset may retire
            # an older prefix while preserving the same destination/source
            # delta.
            if left.role != right.role:
                continue
            if (
                left.source is not None
                and right.source is not None
                and left.source - left.destination
                == right.source - right.destination
                and (
                    (left.destination <= right.destination
                     and left.end >= right.end)
                    or (right.destination <= left.destination
                        and right.end >= left.end)
                )
            ):
                continue
            collisions.append((left.name, right.name))
    return collisions


def parse_address(text: str) -> int:
    if ":" in text:
        segment, offset = text.split(":", 1)
        return (int(segment, 16) << 16) | int(offset, 16)
    return int(text, 0)


def resolve_address(address: int,
                    overlays: Iterable[OverlaySpec]) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for spec in overlays:
        if spec.destination <= address < spec.end:
            offset = address - spec.destination
            matches.append({
                "name": spec.name,
                "destination": f"0x{spec.destination:06x}",
                "source": None if spec.source is None
                else f"0x{spec.source + offset:06x}",
                "offset": f"0x{offset:x}",
                "size": spec.size,
                "role": spec.role,
            })
    return matches


def manifest(overlays: list[OverlaySpec], mappings: list[QemuMapping]) -> dict:
    missing = missing_mappings(overlays, mappings)
    collisions = overlapping_overlays(overlays)
    return {
        "format": "np560-overlay-map-v1",
        "builder_overlay_count": len(overlays),
        "qemu_mapping_count": len(mappings),
        "missing_count": len(missing),
        "collision_count": len(collisions),
        "missing": [asdict(spec) for spec in missing],
        "collisions": [list(pair) for pair in collisions],
        "overlays": [
            {
                **asdict(spec),
                "end": spec.end,
                "qemu_mapping": (
                    asdict(mapping)
                    if (mapping := covering_mapping(spec, mappings)) else None
                ),
            }
            for spec in overlays
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu-source", type=Path, default=DEFAULT_QEMU_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resolve", action="append", default=[],
                        help="resolve a runtime PC (for example 5f:1a5a)")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)

    overlays = collect_builder_overlays()
    mappings = parse_qemu_mappings(args.qemu_source.read_text(encoding="utf-8"))
    result = manifest(overlays, mappings)
    if not args.no_write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")

    print(f"builder overlays: {len(overlays)}")
    print(f"QEMU mapped ranges: {len(mappings)}")
    print(f"missing mappings: {result['missing_count']}")
    for item in result["missing"]:
        print(f"  {item['name']}: {item['destination']:06x}+{item['size']:x} "
              f"({item['role']})")
    print(f"non-identical overlaps: {result['collision_count']}")
    for text_address in args.resolve:
        address = parse_address(text_address)
        matches = resolve_address(address, overlays)
        print(f"resolve {address >> 16:02x}:{address & 0xffff:04x}:")
        if not matches:
            print("  flat/unrecovered (no builder overlay)")
        for match in matches:
            print(f"  {match['name']} +{match['offset']} -> {match['source']} "
                  f"[{match['role']}]")
    return 1 if result["missing_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
