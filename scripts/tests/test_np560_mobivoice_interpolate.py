"""Pure synthetic checks for the owned candidate interpolation stage."""

from __future__ import annotations

import pytest

from scripts.np560_mobivoice_interpolate import interpolate_candidate_table


def test_fixed_point_rounding_and_adjacent_table_entries() -> None:
    assert interpolate_candidate_table(
        (0, 127, 128, 255, 256), (0, 100, 200), 8,
    ) == (0, 50, 50, 100, 100)
    assert interpolate_candidate_table((128,), (100, 0), 8) == (50,)


def test_invalid_shift_and_table_bounds() -> None:
    with pytest.raises(ValueError, match="fractional bits"):
        interpolate_candidate_table((0,), (0, 1), 0)
    with pytest.raises(ValueError, match="lookup index"):
        interpolate_candidate_table((512,), (0, 1), 8)
    with pytest.raises(ValueError, match="lookup index"):
        interpolate_candidate_table((-1,), (0, 1), 8)
