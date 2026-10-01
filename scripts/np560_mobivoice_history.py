"""Stateful excitation history for the candidate mode-5 decoder.

The candidate keeps the previous 160 mixed excitation samples and the
subframes already mixed in the current frame.  This model starts with zero
history after mode-5 initialization; it does not reconstruct the upstream
LSF predictor or prove NP560 mask-ROM equivalence.
"""

from __future__ import annotations

try:
    from .np560_mobivoice_fir import signed16
except ImportError:  # Direct scripts/ execution.
    from np560_mobivoice_fir import signed16


class CandidateExcitationHistory:
    def __init__(self) -> None:
        self.prior_frame = (0,) * 160
        self.current_frame: tuple[int, ...] = ()

    def tail(self, length: int) -> tuple[int, ...]:
        """Return the samples before the next adaptive subframe, oldest first."""
        available = self.prior_frame + self.current_frame
        if not 1 <= length <= len(available):
            raise ValueError("candidate excitation history length is invalid")
        return available[-length:]

    def append_subframe(self, samples: tuple[int, ...]) -> None:
        if len(samples) != 80 or len(self.current_frame) >= 160:
            raise ValueError("candidate excitation needs two 80-sample subframes")
        self.current_frame += tuple(signed16(value) for value in samples)

    def finish_frame(self) -> None:
        if len(self.current_frame) != 160:
            raise ValueError("candidate excitation frame needs 160 samples")
        self.prior_frame = self.current_frame
        self.current_frame = ()
