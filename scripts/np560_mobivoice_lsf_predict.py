"""Ten-word recursive LSF predictor of the candidate mode-5 decoder.

The vector comes from the three compressed-field codebooks.  This produces
the candidate's pre-normalization LSF words and carries predictor state
between frames.  LPC conversion and NP560 mask-ROM equivalence remain open.
"""

from __future__ import annotations

try:
    from .np560_mobivoice_fir import signed16, signed32
    from .np560_mobivoice_tables import LSF_BIAS, LSF_PREDICTOR_GAIN
except ImportError:  # Direct scripts/ execution.
    from np560_mobivoice_fir import signed16, signed32
    from np560_mobivoice_tables import LSF_BIAS, LSF_PREDICTOR_GAIN


class CandidateLsfPredictor:
    def __init__(self, state: tuple[int, ...] = (0,) * 10) -> None:
        if len(state) != 10:
            raise ValueError("candidate LSF predictor needs ten state words")
        self.state = tuple(signed16(value) for value in state)

    def step(self, vector: tuple[int, ...]) -> tuple[int, ...]:
        if len(vector) != 10:
            raise ValueError("candidate LSF codebook vector needs ten words")
        updated = []
        lsf = []
        for value, prior, gain, bias in zip(
            vector, self.state, LSF_PREDICTOR_GAIN, LSF_BIAS,
        ):
            prediction = signed32(signed16(prior) * gain) >> 15
            current = signed16(signed16(value) + prediction)
            updated.append(current)
            lsf.append(signed16(current + bias))
        self.state = tuple(updated)
        return tuple(lsf)
