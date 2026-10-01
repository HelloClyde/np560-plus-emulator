"""Candidate intermediate-stage differential tests, never PCM compatibility claims."""

from __future__ import annotations

import pytest

from scripts.np560_mobivoice_lsf import normalize_candidate_words


def test_spacing_clamp_and_upper_boundary() -> None:
    values, status = normalize_candidate_words((0,) * 10)
    assert values == (204, 408, 613, 819, 1026, 1234, 1443, 1653, 1864, 2076)
    assert status == 0
    values, status = normalize_candidate_words((20000,) * 10)
    assert values[-1] > 0x4000
    assert status == -2
    with pytest.raises(ValueError, match="ten words"):
        normalize_candidate_words((0,) * 9)
