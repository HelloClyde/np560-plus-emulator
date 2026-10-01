"""Guard reuse of an earlier differential before skipping corpus sections."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from probe_np560_mobivoice_corpus import load_verified_baseline


def test_baseline_reuse_requires_same_game_candidate_and_complete_sections() -> None:
    payload = b"\x20\x0d\x00\x01" + b"\x55" * 21 + b"\x00"
    digest = hashlib.sha256(payload).hexdigest()
    candidate = "b" * 64
    game = "a" * 64
    inventory = {"games": [{"sha256": game,
                            "sound_candidates": [{"section": 16, "sha256": digest}]}]}
    unique = {digest: {"payload": payload}}
    row = {"section": 16, "frames": 1,
           "pcm_sha256": "c" * 64, "candidate_pcm_sha256": "c" * 64}
    baseline = {"schema": "np560-npe-owned-candidate-all-sections-v1",
                "npe_sha256": game, "candidate_sha256": candidate,
                "all_pcm_samples_match": True, "sections": [row], "total_frames": 1}
    assert load_verified_baseline(baseline, inventory, unique, candidate) == {digest: row}
    with pytest.raises(ValueError, match="candidate comparison"):
        load_verified_baseline(baseline, inventory, unique, "d" * 64)
    with pytest.raises(ValueError, match="coverage"):
        load_verified_baseline({**baseline, "total_frames": 2}, inventory, unique, candidate)
    with pytest.raises(ValueError, match="PCM hashes"):
        load_verified_baseline({**baseline, "sections": [{**row, "pcm_sha256": "e" * 64}]},
                               inventory, unique, candidate)
