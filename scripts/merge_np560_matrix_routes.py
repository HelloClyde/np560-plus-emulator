#!/usr/bin/env python3
"""Merge segmented NP560+ matrix probes into one auditable 64-key report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.probe_np560_matrix_route import (
        ACTIVE_MATRIX_EVENTS,
        CANDIDATE_ONLY_EVENTS,
    )
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from probe_np560_matrix_route import (  # type: ignore[no-redef]
        ACTIVE_MATRIX_EVENTS,
        CANDIDATE_ONLY_EVENTS,
    )


def classify_step(step: dict[str, Any]) -> str:
    maps_advanced = int(step.get("maps_after", 0)) > int(
        step.get("maps_before", 0)
    )
    acknowledgement_advanced = int(
        step.get("acknowledgements_after", 0)
    ) > int(step.get("acknowledgements_before", 0))
    acknowledgement_matches = int(step.get("acknowledgement", -1)) == int(
        step["expected_event"]
    )
    if not maps_advanced:
        return "candidate-only"
    if acknowledgement_advanced and acknowledgement_matches:
        return "map+foreground-ack"
    return "map-only"


def build_report(route_paths: list[Path]) -> dict[str, Any]:
    by_index: dict[int, dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    errors: list[str] = []

    for route_path in route_paths:
        route = json.loads(route_path.read_text(encoding="utf-8"))
        if route.get("schema") != "np560-matrix-route-v2":
            errors.append(f"{route_path}: unsupported route schema")
            continue
        for raw_step in route.get("steps", []):
            step = dict(raw_step)
            index = int(step.get("matrix_index", -1))
            if not 0 <= index < len(ACTIVE_MATRIX_EVENTS):
                errors.append(f"{route_path}: invalid matrix index {index}")
                continue
            step["source_route"] = str(route_path)
            if index in by_index:
                duplicates.append({
                    "matrix_index": index,
                    "first_source": by_index[index]["source_route"],
                    "duplicate_source": str(route_path),
                })
                continue
            by_index[index] = step

    entries: list[dict[str, Any]] = []
    for index in sorted(by_index):
        step = by_index[index]
        expected = ACTIVE_MATRIX_EVENTS[index]
        actual = int(step.get("expected_event", -1))
        observed = int(step.get("event", -1))
        candidate_advanced = int(
            step.get("candidate_writes_after", 0)
        ) > int(step.get("candidate_writes_before", 0))
        maps_advanced = int(step.get("maps_after", 0)) > int(
            step.get("maps_before", 0)
        )
        classification = classify_step(step)
        entry_errors: list[str] = []
        if actual != expected:
            entry_errors.append(
                f"table event 0x{actual & 0xffff:04X} != 0x{expected:04X}"
            )
        if observed != expected:
            entry_errors.append(
                f"observed event 0x{observed & 0xffff:04X} != 0x{expected:04X}"
            )
        if not candidate_advanced:
            entry_errors.append("candidate counter did not advance")
        if not bool(step.get("release_observed")):
            entry_errors.append("released matrix was not observed")
        if expected not in CANDIDATE_ONLY_EVENTS and not maps_advanced:
            entry_errors.append("ordinary event did not reach 28:F6DE")
        if expected in CANDIDATE_ONLY_EVENTS and classification != "candidate-only":
            entry_errors.append("guest-consumed event unexpectedly reached 28:F6DE")
        if bool(step.get("foreground_ack_required")):
            if classification != "map+foreground-ack":
                entry_errors.append("required foreground acknowledgement is absent")
        if entry_errors:
            errors.extend(f"M{index:02d}: {error}" for error in entry_errors)
        entries.append({
            "matrix_index": index,
            "expected_event": expected,
            "classification": classification,
            "candidate_advanced": candidate_advanced,
            "map_advanced": maps_advanced,
            "foreground_ack_required": bool(
                step.get("foreground_ack_required")
            ),
            "release_observed": bool(step.get("release_observed")),
            "source_route": step["source_route"],
        })

    missing = [
        index for index in range(len(ACTIVE_MATRIX_EVENTS))
        if index not in by_index
    ]
    counts = {
        name: sum(entry["classification"] == name for entry in entries)
        for name in (
            "candidate-only", "map-only", "map+foreground-ack",
        )
    }
    complete = not missing and not duplicates and not errors
    return {
        "schema": "np560-matrix-route-merge-v1",
        "complete": complete,
        "covered": len(entries),
        "expected": len(ACTIVE_MATRIX_EVENTS),
        "missing": missing,
        "duplicates": duplicates,
        "classification_counts": counts,
        "errors": errors,
        "sources": [str(path) for path in route_paths],
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-incomplete", action="store_true",
        help="write an incomplete report without returning a failure status",
    )
    args = parser.parse_args()
    report = build_report(args.route)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"COVERAGE={report['covered']}/{report['expected']} "
        f"COMPLETE={int(report['complete'])} "
        f"CLASSIFICATIONS={report['classification_counts']}"
    )
    if report["errors"]:
        for error in report["errors"]:
            print(f"ERROR={error}")
    if report["missing"]:
        print("MISSING=" + ",".join(f"M{index:02d}" for index in report["missing"]))
    if report["duplicates"]:
        print(f"DUPLICATES={len(report['duplicates'])}")
    return 0 if report["complete"] or args.allow_incomplete else 1


if __name__ == "__main__":
    raise SystemExit(main())
