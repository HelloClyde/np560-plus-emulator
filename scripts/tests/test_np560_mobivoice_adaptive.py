"""Pure checks for the candidate's self-feeding adaptive subframe loop."""

from __future__ import annotations

import random

import pytest

from scripts.np560_mobivoice_adaptive import generate_candidate_adaptive
from scripts.np560_mobivoice_fir import candidate_dot_sample, signed16


def test_zero_fraction_repeats_recent_history_forward() -> None:
    assert generate_candidate_adaptive(tuple(range(16)), 16, 0) == (
        tuple(range(16)) * 5
    )


def test_fractional_branch_uses_29_tap_interpolating_window() -> None:
    impulse = (0,) * 14 + (32767,) + (0,) * 14
    assert generate_candidate_adaptive((100,) * 30, 16, 1, impulse) == (100,) * 80


def test_requires_valid_geometry_and_fractional_taps() -> None:
    with pytest.raises(ValueError, match="delay/fraction"):
        generate_candidate_adaptive((0,) * 30, 16, 2)
    with pytest.raises(ValueError, match="history"):
        generate_candidate_adaptive((0,) * 16, 16, 1, (0,) * 29)
    with pytest.raises(ValueError, match="29 taps"):
        generate_candidate_adaptive((0,) * 30, 16, -1)


def test_fractional_feedback_matches_per_sample_reference() -> None:
    random_source = random.Random(0x560A)
    for delay in (15, 16, 30, 79):
        for fraction in (-1, 1):
            for _ in range(20):
                history = tuple(random_source.randrange(-(1 << 20), 1 << 20)
                                for _ in range(delay + 14))
                taps = tuple(random_source.randrange(-(1 << 20), 1 << 20)
                             for _ in range(29))
                reference_history = [signed16(value) for value in history]
                expected = []
                for index in range(80):
                    center = len(history) + index - delay
                    window = tuple(reference_history[center + offset]
                                   for offset in range(-14, 15))
                    value = signed16(candidate_dot_sample(window, taps))
                    reference_history.append(value)
                    expected.append(value)
                assert generate_candidate_adaptive(
                    history, delay, fraction, taps,
                ) == tuple(expected)
