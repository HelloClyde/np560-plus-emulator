"""Candidate mode-5 LSF interpolation across the two 80-sample subframes.

The normalized current and previous ten-word vectors are weighted in Q15.
This yields the frequency-domain input to the later 10th-order LPC conversion,
not PCM and not proof of equivalence to the unavailable NP560 mask ROM.
"""

from __future__ import annotations

try:
    from .np560_mobivoice_fir import signed16, signed32
    from .np560_mobivoice_tables import LSF_BIAS
except ImportError:  # Direct scripts/ execution.
    from np560_mobivoice_fir import signed16, signed32
    from np560_mobivoice_tables import LSF_BIAS


CURRENT_WEIGHTS = (16384, 32767)
PRIOR_WEIGHTS = (16383, 0)


def interpolate_candidate_lsf(
    current: tuple[int, ...], previous: tuple[int, ...], subframe: int,
) -> tuple[int, ...]:
    if len(current) != 10 or len(previous) != 10 or subframe not in (0, 1):
        raise ValueError("candidate LSF interpolation needs two ten-word vectors")
    current_weight = CURRENT_WEIGHTS[subframe]
    previous_weight = PRIOR_WEIGHTS[subframe]
    return tuple(
        signed16(signed32(signed16(now) * current_weight +
                          signed16(prior) * previous_weight) >> 15)
        for now, prior in zip(current, previous)
    )


class CandidateLsfSubframes:
    def __init__(self, previous: tuple[int, ...] = LSF_BIAS) -> None:
        if len(previous) != 10:
            raise ValueError("candidate prior LSF needs ten words")
        self.previous = tuple(signed16(value) for value in previous)
        self.current: tuple[int, ...] | None = None

    def begin_frame(self, normalized: tuple[int, ...]) -> None:
        if self.current is not None or len(normalized) != 10:
            raise ValueError("candidate LSF frame already active or vector invalid")
        self.current = tuple(signed16(value) for value in normalized)

    def subframe(self, index: int) -> tuple[int, ...]:
        if self.current is None:
            raise ValueError("candidate LSF frame has not begun")
        return interpolate_candidate_lsf(self.current, self.previous, index)

    def finish_frame(self) -> None:
        if self.current is None:
            raise ValueError("candidate LSF frame has not begun")
        self.previous = self.current
        self.current = None
