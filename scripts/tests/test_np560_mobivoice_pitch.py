"""Pure pitch-code boundary checks for the owned candidate mapping."""

from __future__ import annotations

import pytest

from scripts.np560_mobivoice_fields import CandidateField
from scripts.np560_mobivoice_pitch import (
    CandidatePitchCall, decode_candidate_pitch,
    pitch_calls_from_candidate_frame,
)


def test_absolute_code_boundaries() -> None:
    assert decode_candidate_pitch(0, 0) == (16, 0)
    assert decode_candidate_pitch(0, 1) == (16, 1)
    assert decode_candidate_pitch(0, 2) == (17, -1)
    assert decode_candidate_pitch(0, 191) == (80, -1)
    assert decode_candidate_pitch(0, 192) == (80, 0)
    assert decode_candidate_pitch(0, 255) == (143, 0)


def test_relative_code_boundaries() -> None:
    assert decode_candidate_pitch(80, 0) == (75, -1)
    assert decode_candidate_pitch(80, 14) == (79, 1)
    assert decode_candidate_pitch(80, 15) == (80, -1)
    assert decode_candidate_pitch(80, 16) == (80, 0)
    assert decode_candidate_pitch(80, 18) == (81, -1)


def test_rejects_out_of_domain_values() -> None:
    with pytest.raises(ValueError, match="8-bit code"):
        decode_candidate_pitch(0, 256)
    with pytest.raises(ValueError, match="prior delay"):
        decode_candidate_pitch(-1, 0)


def test_two_pitch_calls_come_from_packed_frame_fields() -> None:
    fields = (
        CandidateField(0, 0, 8, 0x468, 239),
        CandidateField(1, 8, 5, 0x46A, 15),
    )
    assert pitch_calls_from_candidate_frame(fields) == (
        CandidatePitchCall(0, 239, 127, 0),
        CandidatePitchCall(127, 15, 127, -1),
    )
    with pytest.raises(ValueError, match="pitch field"):
        pitch_calls_from_candidate_frame(fields[:1])
