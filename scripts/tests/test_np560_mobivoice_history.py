"""Pure checks for the candidate's 160-sample excitation history."""

from __future__ import annotations

import pytest

from scripts.np560_mobivoice_history import CandidateExcitationHistory


def test_zero_seed_then_previous_and_current_frame_tail() -> None:
    history = CandidateExcitationHistory()
    assert history.tail(154) == (0,) * 154
    first = tuple(range(80))
    second = tuple(range(80, 160))
    history.append_subframe(first)
    assert history.tail(100) == (0,) * 20 + first
    history.append_subframe(second)
    assert history.tail(154) == tuple(range(6, 160))
    history.finish_frame()
    assert history.tail(154) == tuple(range(6, 160))
    history.append_subframe((40000,) * 80)
    assert history.tail(80) == (-25536,) * 80
    assert history.tail(154)[:74] == tuple(range(86, 160))


def test_requires_exact_two_subframes_per_frame() -> None:
    history = CandidateExcitationHistory()
    with pytest.raises(ValueError, match="length"):
        history.tail(0)
    with pytest.raises(ValueError, match="length"):
        history.tail(161)
    with pytest.raises(ValueError, match="160 samples"):
        history.finish_frame()
    with pytest.raises(ValueError, match="80-sample"):
        history.append_subframe((0,) * 79)
    history.append_subframe((0,) * 80)
    history.append_subframe((1,) * 80)
    with pytest.raises(ValueError, match="80-sample"):
        history.append_subframe((2,) * 80)
    history.finish_frame()
    assert history.tail(80) == (1,) * 80
