"""Candidate mode-5 ten-order LSF-to-LPC fixed-point conversion.

The recurrence models the isolated x86 function at 0x10001320.  It consumes
the two-subframe LSF vector and emits 11 Q12 synthesis coefficients; it is
not a claim that the unavailable NP560 mask ROM has identical behavior.
"""

from __future__ import annotations

try:
    from .np560_mobivoice_fir import signed16, signed32
    from .np560_mobivoice_interpolate import interpolate_candidate_table
    from .np560_mobivoice_tables import LSF_COSINE_TABLE
except ImportError:  # Direct scripts/ execution.
    from np560_mobivoice_fir import signed16, signed32
    from np560_mobivoice_interpolate import interpolate_candidate_table
    from np560_mobivoice_tables import LSF_COSINE_TABLE


def candidate_lpc_from_cosine(cosines: tuple[int, ...]) -> tuple[int, ...]:
    """Run the candidate's two five-stage fixed-point polynomial recurrences."""
    if len(cosines) != 10:
        raise ValueError("candidate LPC conversion needs ten cosine words")
    coefficients = tuple(signed16(value) for value in cosines)
    workspace = {offset: 0 for offset in range(0x14, 0xBC, 4)}

    def multiply_twice_q15(value: int, cosine: int) -> int:
        return signed32((signed32(value) * cosine) >> 14)

    def advance() -> None:
        for index in range(5):
            offset = index * 4
            even_state = workspace[0x48 + offset]
            even_lag = workspace[0x8C + offset]
            even_head = workspace[0x30 + offset]
            odd_state = workspace[0x60 + offset]
            odd_lag = workspace[0xA4 + offset]
            odd_head = workspace[0x18 + offset]
            workspace[0x8C + offset] = even_state
            workspace[0x34 + offset] = signed32(
                even_head + even_lag -
                multiply_twice_q15(even_state, coefficients[2 * index])
            )
            workspace[0xA4 + offset] = odd_state
            workspace[0x1C + offset] = signed32(
                odd_head + odd_lag -
                multiply_twice_q15(odd_state, coefficients[2 * index + 1])
            )
            workspace[0x48 + offset] = even_head
            workspace[0x60 + offset] = odd_head

    workspace[0x18] = 0x400000
    workspace[0x30] = 0x400000
    advance()

    workspace[0x18] = -0x400000
    workspace[0x30] = 0x400000
    advance()
    output = [0x1000, signed16(signed32(
        workspace[0x2C] + workspace[0x44]
    ) >> 11)]
    for _ in range(9):
        workspace[0x18] = 0
        workspace[0x30] = 0
        advance()
        output.append(signed16(signed32(
            workspace[0x2C] + workspace[0x44]
        ) >> 11))
    return tuple(output)


def candidate_lpc_from_lsf(lsf: tuple[int, ...]) -> tuple[int, ...]:
    if len(lsf) != 10:
        raise ValueError("candidate LPC conversion needs ten LSF words")
    cosines = interpolate_candidate_table(lsf, LSF_COSINE_TABLE, 8)
    return candidate_lpc_from_cosine(cosines)
