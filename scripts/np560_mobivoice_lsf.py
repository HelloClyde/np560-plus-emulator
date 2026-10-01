"""Owned model of one observed 10-word candidate synthesis preparation step.

The behavior is derived from the isolated ``mv_sp.dll`` function at
``0x10001220``.  Its ten values resemble LSF frequencies, but that semantic
label and equivalence to the missing NP560 ROM are not established.
"""

from __future__ import annotations


WORD_COUNT = 10
MIN_GAP = 0xCC
UPPER_BOUND = 0x4000


def signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def normalize_candidate_words(words: tuple[int, ...]) -> tuple[tuple[int, ...], int]:
    """Model the candidate's one-pass sort, spacing clamp and return code.

    Return the signed 16-bit words plus the observed function's 0/-2 status.
    This is an intermediate transform, not PCM output.
    """
    if len(words) != WORD_COUNT:
        raise ValueError("candidate preparation step needs ten words")
    values = [signed16(word) for word in words]
    for index in range(WORD_COUNT - 1, 0, -1):
        if values[index] < values[index - 1]:
            values[index], values[index - 1] = values[index - 1], values[index]
    lower_bound = MIN_GAP
    for index in range(WORD_COUNT):
        if values[index] < signed16(lower_bound):
            values[index] = signed16(lower_bound)
        lower_bound = (values[index] + index + MIN_GAP) & 0xFFFF
    status = 0 if values[-1] <= UPPER_BOUND else -2
    return tuple(values), status
