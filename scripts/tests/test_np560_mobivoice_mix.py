"""Pure checks for candidate Q14 gain and fixed-pulse feedback."""

from __future__ import annotations

import pytest

from scripts.np560_mobivoice_mix import mix_candidate_excitation


def test_zero_gain_keeps_only_fixed_excitation() -> None:
    adaptive = (123,) * 80
    fixed = tuple(range(80))
    assert mix_candidate_excitation(adaptive, fixed, 0, 16) == fixed


def test_long_delay_skips_pulse_feedback() -> None:
    assert mix_candidate_excitation(
        (100,) * 80, (50,) * 80, 0x4000, 80,
    ) == (150,) * 80


def test_forward_feedback_uses_newly_updated_pulses() -> None:
    fixed = (100,) + (0,) * 79
    result = mix_candidate_excitation((0,) * 80, fixed, 8192, 16)
    assert [result[index] for index in (0, 16, 32, 48, 64)] == [
        100, 50, 25, 12, 6,
    ]


def test_exact_subframe_geometry() -> None:
    with pytest.raises(ValueError, match="80 samples"):
        mix_candidate_excitation((0,) * 79, (0,) * 80, 0, 1)
    with pytest.raises(ValueError, match="positive delay"):
        mix_candidate_excitation((0,) * 80, (0,) * 80, 0, 0)
