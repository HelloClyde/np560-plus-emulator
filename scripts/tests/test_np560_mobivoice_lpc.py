"""Pure checks for the candidate's ten-order LSF-to-LPC conversion."""

from __future__ import annotations

import pytest

from scripts.np560_mobivoice_lpc import candidate_lpc_from_lsf


def test_natural_tianjiang_subframe_vector() -> None:
    assert candidate_lpc_from_lsf((
        1263, 2002, 3059, 4859, 6170, 7462, 9434, 11031, 12717, 14246,
    )) == (4096, -5781, 3021, -1167, 889, -1049, 1014, -220, 437, -559, 185)


def test_lpc_input_requires_ten_words() -> None:
    with pytest.raises(ValueError, match="ten LSF words"):
        candidate_lpc_from_lsf((0,) * 9)
