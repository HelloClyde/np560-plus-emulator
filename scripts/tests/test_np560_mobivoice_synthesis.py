"""Pure regression checks for the owned final candidate synthesis stage."""

from __future__ import annotations

import pytest

from scripts.np560_mobivoice_synthesis import synthesize_candidate_block


def test_zero_taps_scale_and_clip_intermediate_samples() -> None:
    assert synthesize_candidate_block(
        (0, 1, -1, 30000, -30000), (0,) * 10, (0,) * 10,
    ) == (0, 2, -2, 32767, -32767)


def test_new_outputs_feed_later_samples_in_the_same_block() -> None:
    assert synthesize_candidate_block(
        (100, 0, 0), (0,) * 10, (8192,) + (0,) * 9,
    ) == (200, -400, 800)


def test_exact_negative_16_bit_boundary_is_not_saturated() -> None:
    assert synthesize_candidate_block(
        (-16385, -16384, -16383), (0,) * 10, (0,) * 10,
    ) == (-32767, -32768, -32766)


def test_history_and_coefficient_geometry_is_exact() -> None:
    with pytest.raises(ValueError, match="ten history"):
        synthesize_candidate_block((0,), (0,) * 9, (0,) * 10)
    with pytest.raises(ValueError, match="ten history"):
        synthesize_candidate_block((0,), (0,) * 10, (0,) * 9)
