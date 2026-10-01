"""First-stage vector lookup for the candidate mode-5 LSF predictor.

Three compressed byte indices select 3, 3 and 4 signed words from separate
256-entry codebooks.  This reconstructs the 10-word vector before recursive
prediction; the numeric values are sourced from the reviewed candidate,
not the missing NP560 mask ROM.  Subsequent LPC conversion is not modeled.
"""

from __future__ import annotations

try:
    from .np560_mobivoice_fields import CandidateField
    from .np560_mobivoice_codebook_data import CODEBOOKS
except ImportError:  # Direct scripts/ execution.
    from np560_mobivoice_fields import CandidateField
    from np560_mobivoice_codebook_data import CODEBOOKS


CODEBOOK_WIDTHS = (3, 3, 4)
CODE_FIELD_OFFSETS = (0x462, 0x464, 0x466)


def candidate_codebook_vector(
    fields: tuple[CandidateField, ...],
    codebooks: tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]] = CODEBOOKS,
) -> tuple[int, ...]:
    """Select and concatenate the three candidate codebook entries."""
    if len(codebooks) != 3 or any(
        len(book) != 256 * width
        for book, width in zip(codebooks, CODEBOOK_WIDTHS)
    ):
        raise ValueError("candidate LSF codebooks require 256 entries of widths 3/3/4")
    by_offset = {field.destination_from_context: field.value for field in fields}
    try:
        indices = tuple(by_offset[offset] for offset in CODE_FIELD_OFFSETS)
    except KeyError as exc:
        raise ValueError("candidate LSF code field is missing") from exc
    if any(not 0 <= index < 256 for index in indices):
        raise ValueError("candidate LSF code index must be one byte")
    output: list[int] = []
    for index, width, book in zip(indices, CODEBOOK_WIDTHS, codebooks):
        start = index * width
        output.extend(book[start:start + width])
    return tuple(output)
