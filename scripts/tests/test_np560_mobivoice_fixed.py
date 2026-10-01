"""Pure checks for fixed-pulse signs, index recurrence, and accumulation."""

from __future__ import annotations

import pytest

from scripts.np560_mobivoice_fixed import (
    CandidatePulseGroup, accumulate_candidate_pulses,
    candidate_amplitude_indices, candidate_sign_bits, groups_from_candidate_frame,
)
from scripts.np560_mobivoice_fields import CandidateField


def test_four_sign_bits_are_read_high_to_low() -> None:
    assert candidate_sign_bits(0) == (0, 0, 0, 0)
    assert candidate_sign_bits(8) == (1, 0, 0, 0)
    assert candidate_sign_bits(7) == (0, 1, 1, 1)
    assert candidate_sign_bits(15) == (1, 1, 1, 1)
    with pytest.raises(ValueError, match="four bits"):
        candidate_sign_bits(16)


def test_amplitude_index_recurrence_and_subframe_anchor() -> None:
    assert candidate_amplitude_indices((14, 10, 7, 0, 5)) == (
        14, 17, 17, 10, 8,
    )
    assert candidate_amplitude_indices((3, 0), prior_index=25) == (19, 12)
    assert candidate_amplitude_indices((3, 0), prior_index=11) == (7, 0)
    with pytest.raises(ValueError, match="0..31"):
        candidate_amplitude_indices((32,))


def test_collision_accumulates_with_signed_16_bit_wrap() -> None:
    group = CandidatePulseGroup((1, 1, 2, 3), (0, 0, 1, 1), 20000)
    snapshot, = accumulate_candidate_pulses((group,))
    assert snapshot[1] == -25536
    assert snapshot[2] == -20000
    assert snapshot[3] == -20000
    assert sum(value != 0 for value in snapshot) == 3
    with pytest.raises(ValueError, match="position/sign"):
        accumulate_candidate_pulses((CandidatePulseGroup((80, 1, 2, 3),
                                                          (0, 0, 0, 0), 1),))


def test_fixed_groups_are_built_from_packed_field_offsets() -> None:
    codes = (
        (0, (0, 1, 2, 3, 4), (0, 8, 7, 15, 1), (14, 10, 7, 0, 5)),
        (1, (0, 0, 0, 0, 0), (0, 0, 0, 0, 0), (11, 3, 7, 6, 7)),
    )
    fields = []
    for subframe, positions, signs, amplitudes in codes:
        for group in range(5):
            for base, value in ((0x470, positions[group]),
                                (0x498, signs[group]),
                                (0x4C0, amplitudes[group])):
                fields.append(CandidateField(
                    len(fields), 0, 5,
                    base + subframe * 20 + group * 2, value,
                ))
    position_table = tuple(index % 80 for index in range(256))
    amplitude_table = tuple(index * 32 for index in range(64))
    first, anchor = groups_from_candidate_frame(
        tuple(fields), 0, position_table, amplitude_table,
    )
    assert anchor == 14
    assert first[0] == CandidatePulseGroup((0, 1, 2, 3), (0, 0, 0, 0), 448)
    assert first[1] == CandidatePulseGroup((52, 53, 54, 55), (1, 0, 0, 0), 544)
    second, _ = groups_from_candidate_frame(
        tuple(fields), 1, position_table, amplitude_table, anchor,
    )
    assert tuple(group.amplitude for group in second) == (
        576, 448, 448, 416, 416,
    )
