"""Owned model of the candidate decoder's final 10-tap synthesis filter.

The observed x86 function ``0x10001CA0`` transforms one block of signed
16-bit intermediate samples using ten previous output samples and ten
coefficients.  This reconstructs only that final stage, not the missing
NP560 mask-ROM codec or the upstream excitation and predictor state.
"""

from __future__ import annotations


def signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def signed32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def synthesize_candidate_block(
    intermediate: tuple[int, ...],
    prior_outputs: tuple[int, ...],
    coefficients: tuple[int, ...],
) -> tuple[int, ...]:
    """Return a block matching the candidate's 32-bit x86 integer rules."""
    if len(prior_outputs) != 10 or len(coefficients) != 10:
        raise ValueError("candidate synthesis needs ten history and coefficient words")
    history = [signed16(value) for value in prior_outputs]
    taps = tuple(signed16(value) for value in coefficients)
    output = []
    for sample in intermediate:
        accumulator = signed32(signed16(sample) << 13)
        for previous, coefficient in zip(reversed(history[-10:]), taps):
            accumulator = signed32(accumulator - previous * coefficient)
        accumulator = signed32(accumulator >> 1)
        accumulator = signed32(accumulator + 0x3FF)
        value = accumulator >> 11
        # The exact -32768 boundary is retained.  Values below it are
        # saturated to -32767 by the candidate's separate overflow path.
        if value > 32767:
            value = 32767
        elif value < -32768:
            value = -32767
        output.append(value)
        history.append(value)
    return tuple(output)
