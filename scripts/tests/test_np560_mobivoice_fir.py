"""Pure fixed-point sample arithmetic tests without candidate binary."""

from __future__ import annotations

import random

import pytest

from scripts.np560_mobivoice_fir import candidate_dot_sample, signed16, signed32


def test_rounded_single_tap_and_signed_accumulator_wrap() -> None:
    assert candidate_dot_sample((0,), (0,)) == 0
    assert candidate_dot_sample((32767,), (32767,)) == 32766
    assert candidate_dot_sample((-32768,), (32767,)) == -32767
    assert candidate_dot_sample((32767,) * 3, (32767,) * 3) < 0


def test_requires_matching_odd_sequences() -> None:
    for history, taps in (((), ()), ((1, 2), (1, 2)), ((1,), (1, 2, 3))):
        with pytest.raises(ValueError, match="odd sequences"):
            candidate_dot_sample(history, taps)


def test_deferred_wrap_matches_per_tap_wrap_across_overflow_cases() -> None:
    random_source = random.Random(0x5605)
    for length in (1, 3, 7, 29):
        for _ in range(200):
            history = tuple(random_source.randrange(-(1 << 31), 1 << 31)
                            for _ in range(length))
            taps = tuple(random_source.randrange(-(1 << 31), 1 << 31)
                         for _ in range(length))
            per_tap = 0
            for sample, coefficient in zip(history, taps):
                per_tap = signed32(per_tap +
                                   signed16(sample) * signed16(coefficient))
            expected = signed32(per_tap + 0x3FFF) >> 15
            assert candidate_dot_sample(history, taps) == expected
