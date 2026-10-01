"""Pure checks for first-stage candidate LSF codebook selection."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import pytest

from scripts.np560_mobivoice_codebooks import candidate_codebook_vector
from scripts.np560_mobivoice_codebook_data import CODEBOOKS
from scripts.np560_mobivoice_fields import CandidateField


def test_three_indices_select_concatenated_3_3_4_vector() -> None:
    fields = tuple(CandidateField(i, i * 8, 8, offset, value)
                   for i, (offset, value) in enumerate((
                       (0x462, 1), (0x464, 2), (0x466, 3),
                   )))
    books = (tuple(range(256 * 3)),
             tuple(range(1000, 1000 + 256 * 3)),
             tuple(range(2000, 2000 + 256 * 4)))
    assert candidate_codebook_vector(fields, books) == (
        3, 4, 5, 1006, 1007, 1008, 2012, 2013, 2014, 2015,
    )


def test_codebook_geometry_and_fields_are_checked() -> None:
    fields = (CandidateField(0, 0, 8, 0x462, 0),)
    books = ((0,) * 768, (0,) * 768, (0,) * 1024)
    with pytest.raises(ValueError, match="field is missing"):
        candidate_codebook_vector(fields, books)
    with pytest.raises(ValueError, match="widths 3/3/4"):
        candidate_codebook_vector(fields, books[:2])
    with pytest.raises(ValueError, match="widths 3/3/4"):
        candidate_codebook_vector(fields, (books[0][:-1],) + books[1:])


def test_owned_candidate_codebook_shapes_and_hashes() -> None:
    expected = (
        "126e413d82415aab4c8db1fa14405243535cdc363bc6b2d3d8d3d48b754325d3",
        "096f1a091dc94710a596c1821539a7b0ec40eced37f255676ba321583391bb5e",
        "10842bfcb3510c1eec1f96d7349d8046ed142269064333843c78b6c6c9713f4f",
    )
    assert tuple(len(book) for book in CODEBOOKS) == (768, 768, 1024)
    for book, digest in zip(CODEBOOKS, expected):
        raw = struct.pack(f"<{len(book)}h", *book)
        assert hashlib.sha256(raw).hexdigest() == digest


def test_optional_reviewed_dll_matches_owned_codebooks() -> None:
    dll = (Path(__file__).resolve().parents[2] / "tmp" /
           "np560-mobivoice-codec-candidate-20260930-v1" / "mv_sp.dll")
    if not dll.is_file():
        pytest.skip("reviewed local DLL is not available")
    pefile = pytest.importorskip("pefile")
    raw = dll.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "7204d31972243812926fb589a7a0622eee73a91ac7a184627e04978559e8af01"
    )
    image = pefile.PE(data=raw).get_memory_mapped_image()
    for address, values in zip((0x6144, 0x6744, 0x6D44), CODEBOOKS):
        assert struct.unpack_from(f"<{len(values)}h", image, address) == values
