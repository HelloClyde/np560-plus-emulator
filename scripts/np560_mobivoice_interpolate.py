"""Owned model of the candidate decoder's fixed-point table interpolation.

This models isolated function ``0x10001280`` with caller-supplied input and
lookup table.  It is an intermediate arithmetic step, not a complete speech
decoder or evidence of equivalence to NP560's unavailable mask ROM.
"""

from __future__ import annotations


def signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def interpolate_candidate_table(
    positions: tuple[int, ...], table: tuple[int, ...], fractional_bits: int,
) -> tuple[int, ...]:
    """Interpolate signed Q-format positions using candidate x86 rounding.

    The caller supplies only nonnegative table positions so this compact
    model need not represent pointer arithmetic before the table base.
    """
    if not 1 <= fractional_bits <= 15:
        raise ValueError("fractional bits must be 1..15")
    rounding = (1 << (fractional_bits - 1)) - 1
    result = []
    for position in positions:
        source = signed16(position)
        index = source >> fractional_bits
        if index < 0 or index + 1 >= len(table):
            raise ValueError("candidate lookup index exceeds table")
        fraction = source - (index << fractional_bits)
        left = signed16(table[index])
        right = signed16(table[index + 1])
        value = left + ((fraction * (right - left) + rounding) >> fractional_bits)
        result.append(signed16(value))
    return tuple(result)
