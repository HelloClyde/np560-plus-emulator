"""Owned candidate excitation gain, pitch sharpening, and final summation.

This models one 80-sample subframe between the adaptive/fixed generators and
the final synthesis filter.  The gain itself is caller-supplied; the decoder
table and full compressed-frame state are not included here.
"""

from __future__ import annotations

try:
    from .np560_mobivoice_fir import signed16, signed32
except ImportError:  # Direct scripts/ execution.
    from np560_mobivoice_fir import signed16, signed32


def mix_candidate_excitation(
    adaptive: tuple[int, ...], fixed: tuple[int, ...],
    pitch_gain: int, delay: int,
) -> tuple[int, ...]:
    """Apply the candidate's Q14 gain and forward pulse feedback."""
    if len(adaptive) != 80 or len(fixed) != 80 or delay < 1:
        raise ValueError("candidate excitation mix needs 80 samples and positive delay")
    gain = signed16(pitch_gain)
    adaptive_scaled = [
        signed16(signed32(signed16(value) * gain + 0x1FFF) >> 14)
        for value in adaptive
    ]
    sharpened = [signed16(value) for value in fixed]
    if delay < 80:
        for index in range(80 - delay):
            feedback = signed16(
                signed32(sharpened[index] * gain + 0x1FFF) >> 14
            )
            sharpened[index + delay] = signed16(
                sharpened[index + delay] + feedback
            )
    return tuple(signed16(left + right)
                 for left, right in zip(adaptive_scaled, sharpened))
