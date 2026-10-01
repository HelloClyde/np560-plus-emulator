"""Owned model of the candidate's 80-sample adaptive excitation loop.

The decoder's pitch delay/fraction chooses either forward history copy or a
29-tap interpolating dot product.  The coefficient values are caller-supplied:
this module does not include the vendor table or independently decode a frame.
"""

from __future__ import annotations

try:
    from .np560_mobivoice_fir import signed16, signed32
except ImportError:  # Direct scripts/ execution.
    from np560_mobivoice_fir import signed16, signed32


RADIUS = 14
SUBFRAME_SAMPLES = 80


def generate_candidate_adaptive(
    history: tuple[int, ...], delay: int, fraction: int,
    taps: tuple[int, ...] | None = None,
) -> tuple[int, ...]:
    """Generate one candidate subframe with self-feedback from new samples.

    ``history`` is ordered oldest to newest and needs at least ``delay + 14``
    words for the fractional branch, or ``delay`` for the copy branch.
    """
    if delay < 1 or fraction not in (-1, 0, 1):
        raise ValueError("candidate adaptive delay/fraction is invalid")
    needed = delay + RADIUS if fraction else delay
    if len(history) < needed:
        raise ValueError("candidate adaptive history is too short")
    if fraction and (taps is None or len(taps) != 2 * RADIUS + 1):
        raise ValueError("fractional candidate adaptive branch needs 29 taps")
    samples = [signed16(value) for value in history]
    signed_taps = tuple(signed16(value) for value in taps) if fraction else ()
    prefix = len(samples)
    output = []
    for index in range(SUBFRAME_SAMPLES):
        center = prefix + index - delay
        if fraction:
            # The history and taps are already signed 16-bit here. Avoid
            # rebuilding a 29-word window and re-normalizing all 58 operands
            # for each of the 80 output samples. The full sum is equivalent
            # to the candidate's per-tap 32-bit wrap modulo 2**32.
            accumulator = 0
            left = center - RADIUS
            for tap_index, coefficient in enumerate(signed_taps):
                accumulator += samples[left + tap_index] * coefficient
            value = signed16(signed32(accumulator + 0x3FFF) >> 15)
        else:
            value = samples[center]
        samples.append(value)
        output.append(value)
    return tuple(output)
