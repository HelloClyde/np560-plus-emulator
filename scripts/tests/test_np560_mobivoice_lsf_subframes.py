"""Pure checks for two-subframe candidate LSF interpolation."""

from __future__ import annotations

import pytest

from scripts.np560_mobivoice_lsf_subframes import (
    CandidateLsfSubframes, interpolate_candidate_lsf,
)


def test_q15_weights_and_previous_frame_carry() -> None:
    state = CandidateLsfSubframes((0,) * 10)
    state.begin_frame((1000,) * 10)
    assert state.subframe(0) == (500,) * 10
    assert state.subframe(1) == (999,) * 10
    state.finish_frame()
    state.begin_frame((2000,) * 10)
    assert state.subframe(0) == (1499,) * 10
    assert state.subframe(1) == (1999,) * 10
    state.finish_frame()
    assert state.previous == (2000,) * 10


def test_signed_16bit_wrap_and_invalid_geometry() -> None:
    # Both products fit signed 32-bit, but the stored result is a 16-bit word.
    assert interpolate_candidate_lsf((40000,) * 10, (0,) * 10, 1) == (
        -25536,
    ) * 10
    with pytest.raises(ValueError, match="ten-word"):
        interpolate_candidate_lsf((0,) * 9, (0,) * 10, 0)
    with pytest.raises(ValueError, match="ten-word"):
        interpolate_candidate_lsf((0,) * 10, (0,) * 10, 2)
    state = CandidateLsfSubframes()
    assert state.previous[0] == 1242
    with pytest.raises(ValueError, match="not begun"):
        state.subframe(0)
    with pytest.raises(ValueError, match="not begun"):
        state.finish_frame()
