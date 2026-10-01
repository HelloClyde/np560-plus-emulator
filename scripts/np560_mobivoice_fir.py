"""Owned fixed-point dot-product stage observed in candidate speech decoder.

The candidate x86 helper ``0x10001610`` computes one intermediate sample
from equally long signed 16-bit history and coefficient sequences.  This
does not by itself reconstruct the frame's excitation, filters, or PCM stream.
"""

from __future__ import annotations


def signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def signed32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def candidate_dot_sample(
    history: tuple[int, ...], coefficients: tuple[int, ...],
) -> int:
    """Return the candidate function's signed 32-bit, rounded result."""
    if not history or len(history) != len(coefficients) or len(history) % 2 != 1:
        raise ValueError("candidate dot product needs equally sized odd sequences")
    accumulator = 0
    for sample, coefficient in zip(history, coefficients):
        # Two's-complement addition is associative modulo 2**32. Retain
        # the full Python integer through the tap loop and wrap once after
        # rounding; this is bit-identical to wrapping after every tap.
        accumulator += signed16(sample) * signed16(coefficient)
    return signed32(accumulator + 0x3FFF) >> 15
