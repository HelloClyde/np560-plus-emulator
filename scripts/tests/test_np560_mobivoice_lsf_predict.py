"""Pure checks for the candidate's recursive ten-word LSF predictor."""

from __future__ import annotations

import pytest

from scripts.np560_mobivoice_lsf_predict import CandidateLsfPredictor
from scripts.np560_mobivoice_tables import LSF_BIAS, LSF_PREDICTOR_GAIN


def test_zero_initial_state_and_two_real_game_vectors() -> None:
    predictor = CandidateLsfPredictor()
    first = (44, -97, -604, -211, -799, -1272, -560, -408, -355, -76)
    assert predictor.step(first) == (
        1286, 1954, 2758, 4754, 5771, 6827, 9155, 10828, 12540, 14209,
    )
    assert predictor.state == first
    second = (-152, -166, -540, -1040, -630, -453, -735, -235, 370, 71)
    assert predictor.step(second) == (
        1126, 1804, 2327, 3748, 5266, 6591, 8529, 10699, 12995, 14297,
    )
    assert predictor.state == (
        -116, -247, -1035, -1217, -1304, -1508, -1186, -537, 100, 12,
    )


def test_predictor_uses_signed_16bit_state_and_q15_gain() -> None:
    predictor = CandidateLsfPredictor((40000,) * 10)
    assert predictor.state == (-25536,) * 10
    expected = tuple(((prior * gain) >> 15) + bias
                     for prior, gain, bias in zip(
                         predictor.state, LSF_PREDICTOR_GAIN, LSF_BIAS,
                     ))
    assert predictor.step((0,) * 10) == expected


def test_predictor_rejects_wrong_geometry() -> None:
    with pytest.raises(ValueError, match="ten state"):
        CandidateLsfPredictor((0,) * 9)
    with pytest.raises(ValueError, match="ten words"):
        CandidateLsfPredictor().step((0,) * 9)
