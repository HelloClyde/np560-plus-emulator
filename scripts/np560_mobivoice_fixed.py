"""Owned pulse-accumulation stage of candidate fixed excitation.

For each group, four table positions receive signed amplitude updates with
16-bit wrap.  Positions, sign bits, and amplitude are caller-supplied; their
compressed-code derivation and lookup tables are not included here.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    from .np560_mobivoice_fields import CandidateField
except ImportError:  # Direct scripts/ execution.
    from np560_mobivoice_fields import CandidateField


def signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


@dataclass(frozen=True)
class CandidatePulseGroup:
    positions: tuple[int, int, int, int]
    sign_bits: tuple[int, int, int, int]
    amplitude: int


def accumulate_candidate_pulses(
    groups: tuple[CandidatePulseGroup, ...],
) -> tuple[tuple[int, ...], ...]:
    """Return the 80-sample buffer after each successive pulse group."""
    samples = [0] * 80
    snapshots = []
    for group in groups:
        if len(group.positions) != 4 or len(group.sign_bits) != 4:
            raise ValueError("candidate pulse group needs four positions and signs")
        for position, sign in zip(group.positions, group.sign_bits):
            if not 0 <= position < 80 or sign not in (0, 1):
                raise ValueError("candidate pulse position/sign is invalid")
            change = -signed16(group.amplitude) if sign else signed16(group.amplitude)
            samples[position] = signed16(samples[position] + change)
        snapshots.append(tuple(samples))
    return tuple(snapshots)


def candidate_sign_bits(code: int) -> tuple[int, int, int, int]:
    if not 0 <= code <= 15:
        raise ValueError("candidate pulse sign code must be four bits")
    return tuple((code >> shift) & 1 for shift in (3, 2, 1, 0))


def candidate_amplitude_indices(
    codes: tuple[int, ...], prior_index: int | None = None,
) -> tuple[int, ...]:
    """Map group codes to table indices, carrying state between subframes."""
    if not codes or any(not 0 <= code <= 31 for code in codes):
        raise ValueError("candidate amplitude group codes must be 0..31")
    indices = []
    previous = prior_index
    for group_index, code in enumerate(codes):
        if previous is None:
            current = code
        elif group_index == 0:
            current = code + min(16, max(0, previous - 7))
        else:
            current = code + max(0, previous - 7)
        indices.append(current)
        previous = current
    return tuple(indices)


def groups_from_candidate_frame(
    fields: tuple[CandidateField, ...],
    subframe: int,
    position_table: tuple[int, ...],
    amplitude_table: tuple[int, ...],
    prior_anchor: int | None = None,
) -> tuple[tuple[CandidatePulseGroup, ...], int]:
    """Build fixed pulses from packed fields and caller-provided lookup tables.

    The first group's amplitude index is the anchor carried into subframe 1.
    No candidate lookup-table contents are embedded in this module.
    """
    if subframe not in (0, 1) or len(position_table) < 64 * 4:
        raise ValueError("candidate fixed subframe/table geometry is invalid")
    by_offset = {field.destination_from_context: field.value for field in fields}
    try:
        position_codes = tuple(by_offset[0x470 + subframe * 20 + 2 * group]
                               for group in range(5))
        sign_codes = tuple(by_offset[0x498 + subframe * 20 + 2 * group]
                           for group in range(5))
        amplitude_codes = tuple(by_offset[0x4C0 + subframe * 20 + 2 * group]
                                for group in range(5))
    except KeyError as exc:
        raise ValueError("candidate fixed field is missing") from exc
    amplitude_indices = candidate_amplitude_indices(amplitude_codes, prior_anchor)
    groups = []
    for index, (position_code, sign_code, amplitude_index) in enumerate(zip(
        position_codes, sign_codes, amplitude_indices,
    )):
        table_entry = position_code + (32 if index & 1 else 0)
        if not 0 <= position_code <= 31 or not 0 <= amplitude_index < len(amplitude_table):
            raise ValueError("candidate fixed code exceeds lookup table")
        start = table_entry * 4
        groups.append(CandidatePulseGroup(
            tuple(position_table[start:start + 4]),
            candidate_sign_bits(sign_code),
            amplitude_table[amplitude_index],
        ))
    return tuple(groups), amplitude_indices[0]
