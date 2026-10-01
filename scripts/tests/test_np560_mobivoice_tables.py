"""Checks for candidate mode-5 lookup values used by the owned stages."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import pytest

from scripts.np560_mobivoice_tables import (
    INTERPOLATION_TAPS, LSF_BIAS, LSF_COSINE_TABLE, LSF_PREDICTOR_GAIN, PITCH_GAINS,
    PULSE_AMPLITUDES, PULSE_POSITIONS, interpolation_phase_taps,
)


def test_candidate_table_shapes_and_ranges() -> None:
    assert len(INTERPOLATION_TAPS) == 94
    assert len(PULSE_POSITIONS) == 256
    assert len(PULSE_AMPLITUDES) == 32
    assert len(PITCH_GAINS) == 16
    assert len(LSF_BIAS) == len(LSF_PREDICTOR_GAIN) == 10
    assert len(LSF_COSINE_TABLE) == 65
    assert all(0 <= value < 80 for value in PULSE_POSITIONS)
    assert all(0 <= value <= 0x7FFF for value in PULSE_AMPLITUDES)
    assert all(0 <= value <= 0x7FFF for value in PITCH_GAINS)


def test_candidate_table_bytes_are_stable() -> None:
    expected = (
        "b33f97da36b66fedb08ef8d1ed1a32e979997eddb38517f2eaa895df6079a47c",
        "d9a84ad3f47e2a801f9e842655c154f6c77422d1d3a5ce277378a04221056eb5",
        "c83868990ab14ea2a3808725c02deff006eae25b83a87929e9e85685fe6edc33",
        "b9bf3c43e65dfbcc552f0d872f69cc455036af8654dd75a8078ac451ce6122bc",
        "4db79c2a4273393fe5064901d4bd33ee663efae85fa5bab47915b98da6f25913",
        "e21ed4d2d3de497cde05dd751031faba009a81fe2936ed32d20e0b8d08fa7518",
    )
    for table, digest in zip(
        (INTERPOLATION_TAPS, PULSE_POSITIONS, PULSE_AMPLITUDES,
         PITCH_GAINS, LSF_BIAS, LSF_PREDICTOR_GAIN),
        expected,
    ):
        raw = struct.pack(f"<{len(table)}h", *table)
        assert hashlib.sha256(raw).hexdigest() == digest
    assert hashlib.sha256(struct.pack("<65h", *LSF_COSINE_TABLE)).hexdigest() == (
        "5ed25af197daf61d213c6bcff4db9fa8177ada52824dafea1238d09232ed0629"
    )


@pytest.mark.parametrize("fraction", (-1, 0, 1))
def test_interpolation_phase_uses_centered_three_way_stride(fraction: int) -> None:
    taps = interpolation_phase_taps(fraction)
    assert len(taps) == 29
    assert taps == tuple(INTERPOLATION_TAPS[47 + step * 3 + fraction]
                         for step in range(-14, 15))


def test_interpolation_phase_rejects_other_fractions() -> None:
    with pytest.raises(ValueError, match="fraction"):
        interpolation_phase_taps(2)


def test_optional_reviewed_dll_matches_owned_tables() -> None:
    dll = (Path(__file__).resolve().parents[2] / "tmp" /
           "np560-mobivoice-codec-candidate-20260930-v1" / "mv_sp.dll")
    if not dll.is_file():
        pytest.skip("reviewed local DLL is not available")
    pefile = pytest.importorskip("pefile")
    raw = dll.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "7204d31972243812926fb589a7a0622eee73a91ac7a184627e04978559e8af01"
    )
    pe = pefile.PE(data=raw)
    assert pe.OPTIONAL_HEADER.ImageBase == 0x10000000
    image = pe.get_memory_mapped_image()
    for address, values in (
        (0x7548, INTERPOLATION_TAPS),
        (0x7604, PULSE_POSITIONS),
        (0x60B4, PULSE_AMPLITUDES),
        (0x60F4, PITCH_GAINS),
        (0x6114, LSF_BIAS),
        (0x6128, LSF_PREDICTOR_GAIN),
        (0x6030, LSF_COSINE_TABLE),
    ):
        assert struct.unpack_from(f"<{len(values)}h", image, address) == values
