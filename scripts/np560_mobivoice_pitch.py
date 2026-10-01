"""Owned model of candidate decoder's pitch-delay code mapping.

The isolated x86 function at ``0x10001680`` maps one compressed code and
an optional previous delay to an integer delay plus {-1,0,1} fraction.
This is only one input to candidate excitation synthesis; it does not prove
equivalence to the unavailable NP560 mask-ROM decoder.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    from .np560_mobivoice_fields import CandidateField
except ImportError:  # Direct scripts/ execution.
    from np560_mobivoice_fields import CandidateField


@dataclass(frozen=True)
class CandidatePitchCall:
    previous_delay: int
    code: int
    delay: int
    fraction: int


def decode_candidate_pitch(previous_delay: int, code: int) -> tuple[int, int]:
    if not 0 <= previous_delay <= 0x7FFF or not 0 <= code <= 255:
        raise ValueError("candidate pitch requires prior delay and 8-bit code")
    if previous_delay == 0:
        if code >= 192:
            return code - 112, 0
        quotient, remainder = divmod(code, 3)
        if remainder == 2:
            return quotient + 17, -1
        return quotient + 16, remainder
    if code >= 16:
        quotient, remainder = divmod(code - 16, 3)
        if remainder == 2:
            return previous_delay + quotient + 1, -1
        return previous_delay + quotient, remainder
    quotient, remainder = divmod(16 - code, 3)
    if remainder == 2:
        return previous_delay - quotient - 1, 1
    return previous_delay - quotient, -remainder


def pitch_calls_from_candidate_frame(
    fields: tuple[CandidateField, ...],
) -> tuple[CandidatePitchCall, CandidatePitchCall]:
    """Decode both subframe pitch calls directly from packed mode-5 fields."""
    by_offset = {field.destination_from_context: field.value for field in fields}
    try:
        first_code = by_offset[0x468]
        second_code = by_offset[0x46A]
    except KeyError as exc:
        raise ValueError("candidate pitch field is missing") from exc
    first_delay, first_fraction = decode_candidate_pitch(0, first_code)
    second_delay, second_fraction = decode_candidate_pitch(
        first_delay, second_code,
    )
    return (
        CandidatePitchCall(0, first_code, first_delay, first_fraction),
        CandidatePitchCall(first_delay, second_code,
                           second_delay, second_fraction),
    )
