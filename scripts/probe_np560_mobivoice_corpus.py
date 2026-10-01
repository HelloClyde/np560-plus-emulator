#!/usr/bin/env python3
"""Differentially check each distinct local NPE sound section once.

The reference DLL is emulated in Unicorn, never executed natively.  A prior
verified single-game report may supply already-checked sections.  This proves
compatibility with that candidate, not equivalence to the missing mask ROM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from analyse_np560_npe import _parse_sections
from probe_np560_mobivoice_owned_decoder import compare_sound_section


def load_corpus(inventory: dict) -> tuple[dict[str, dict], int]:
    if inventory.get("schema") != "np560-npe-audio-corpus-v1":
        raise ValueError("unsupported corpus inventory")
    unique: dict[str, dict] = {}
    candidate_count = 0
    for game in inventory["games"]:
        path = Path(game["path"])
        blob = path.read_bytes()
        if hashlib.sha256(blob).hexdigest().lower() != game["sha256"].lower():
            raise ValueError(f"game file changed: {path}")
        sections = _parse_sections(blob)
        if len(sections) != game["section_count"]:
            raise ValueError(f"section count changed: {path}")
        for sound in game["sound_candidates"]:
            index = sound["section"]
            if index < 16 or index >= len(sections):
                raise ValueError(f"invalid sound index: {path} section {index}")
            offset, size = sections[index]
            if (offset, size) != (sound["offset"], sound["bytes"]):
                raise ValueError(f"sound offset/size changed: {path} section {index}")
            payload = blob[offset:offset + size]
            digest = hashlib.sha256(payload).hexdigest()
            if digest != sound["sha256"].lower():
                raise ValueError(f"sound payload changed: {path} section {index}")
            entry = unique.setdefault(digest, {
                "payload": payload, "owners": [], "index": index,
            })
            entry["owners"].append({"game_sha256": game["sha256"].lower(),
                                    "section": index})
            candidate_count += 1
    if (len(inventory["games"]) != inventory["game_count"]
            or candidate_count != inventory["candidate_count"]
            or len(unique) != inventory["unique_count"]):
        raise ValueError("corpus inventory totals changed")
    return unique, candidate_count


def load_verified_baseline(
    report: dict, inventory: dict, unique: dict[str, dict], candidate_hash: str
) -> dict[str, dict]:
    if (report.get("schema") != "np560-npe-owned-candidate-all-sections-v1"
            or report.get("candidate_sha256") != candidate_hash
            or report.get("all_pcm_samples_match") is not True):
        raise ValueError("baseline is not a matching successful candidate comparison")
    source_games = [game for game in inventory["games"]
                    if game["sha256"].lower() == report.get("npe_sha256")]
    if len(source_games) != 1:
        raise ValueError("baseline game does not uniquely match inventory")
    source = source_games[0]
    rows = {row["section"]: row for row in report["sections"]}
    if (len(rows) != len(report["sections"])
            or set(rows) != {sound["section"] for sound in source["sound_candidates"]}
            or sum(row["frames"] for row in rows.values()) != report["total_frames"]):
        raise ValueError("baseline section coverage is incomplete")
    reused = {}
    for sound in source["sound_candidates"]:
        row = rows[sound["section"]]
        frames = int.from_bytes(unique[sound["sha256"]]["payload"][2:4], "big")
        if (frames != row["frames"]
                or row["pcm_sha256"] != row["candidate_pcm_sha256"]):
            raise ValueError("baseline frame count or PCM hashes disagree")
        reused[sound["sha256"]] = row
    return reused


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    unique, candidate_count = load_corpus(inventory)
    dll = args.dll.read_bytes()
    candidate_hash = hashlib.sha256(dll).hexdigest()
    reused = {}
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        reused = load_verified_baseline(baseline, inventory, unique, candidate_hash)
    rows = []
    for digest, entry in unique.items():
        if digest in reused:
            row = reused[digest]
            result = {"frames": row["frames"], "pcm_sha256": row["pcm_sha256"],
                      "candidate_pcm_sha256": row["candidate_pcm_sha256"],
                      "verification": "baseline"}
        else:
            row = compare_sound_section(entry["payload"], dll, entry["index"])
            result = {"frames": row["frames"], "pcm_sha256": row["pcm_sha256"],
                      "candidate_pcm_sha256": row["candidate_pcm_sha256"],
                      "verification": "fresh"}
            print(f"{len(rows) + 1}/{len(unique)} section {entry['index']}: "
                  f"{row['frames']} frames matched, {row['elapsed_seconds']} s", flush=True)
        rows.append({"payload_sha256": digest, "owners": entry["owners"], **result})
    report = {
        "schema": "np560-npe-owned-candidate-corpus-v1",
        "inventory_sha256": hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
        "candidate_sha256": candidate_hash,
        "game_count": len(inventory["games"]),
        "candidate_sections": candidate_count,
        "unique_sections": len(rows),
        "fresh_sections": sum(row["verification"] == "fresh" for row in rows),
        "reused_sections": sum(row["verification"] == "baseline" for row in rows),
        "unique_frames": sum(row["frames"] for row in rows),
        "all_pcm_samples_match": True,
        "sections": rows,
        "limitation": "local corpus and historical candidate only; no real NP560 ROM PCM reference",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"{report['unique_sections']} unique sections, "
          f"{report['unique_frames']} frames matched", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
