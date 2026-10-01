"""Owned candidate-frame parser checks; no vendor DLL or NPE is bundled."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.np560_mobivoice_fields import (
    MODE5_FIELD_LAYOUT,
    MODE5_FRAME_BYTES,
    msb_bits,
    parse_mode5_frame,
)
from probe_np560_mobivoice_sp_decoder import candidate_bytes
from analyse_np560_npe import _parse_sections


def test_msb_reader_crosses_bytes_and_rejects_overrun() -> None:
    source = bytes((0b10110010, 0b01101101))
    assert msb_bits(source, 0, 4) == 0b1011
    assert msb_bits(source, 5, 6) == 0b010011
    assert msb_bits(source, 8, 8) == source[1]
    with pytest.raises(ValueError, match="bit range"):
        msb_bits(source, 13, 4)


def test_mode5_layout_covers_each_bit_once() -> None:
    frame = bytes(range(MODE5_FRAME_BYTES))
    fields = parse_mode5_frame(frame)
    assert len(fields) == len(MODE5_FIELD_LAYOUT) == 37
    assert fields[0].value == 0
    assert fields[1].value == 1
    assert fields[2].value == 2
    assert fields[3].value == 3
    assert fields[0].start_bit == 0
    assert fields[-1].start_bit + fields[-1].bits == 168
    bits = "".join(f"{field.value:0{field.bits}b}" for field in fields)
    assert bits == "".join(f"{byte:08b}" for byte in frame)
    with pytest.raises(ValueError, match="21 bytes"):
        parse_mode5_frame(frame[:-1])


@pytest.mark.parametrize("section_index,frame_index", [
    (20, 0), (20, 1), (20, 2), (23, 0), (23, 1), (23, 2),
])
def test_optional_local_candidate_trace(
    section_index: int, frame_index: int,
) -> None:
    """Cross-check local evidence if present; portable checkout can skip."""
    root = Path(__file__).resolve().parents[2]
    npe_path = Path(r"D:\Downloads\NP560plus游戏全集\天降风云V1.3.npe")
    report_path = root / "tmp/np560-npe-bitfields-tjfy-20261001-v1" / (
        f"section{section_index}-frame{frame_index}.json"
    )
    if not npe_path.is_file() or not report_path.is_file():
        pytest.skip("local game and candidate trace are optional")
    npe = npe_path.read_bytes()
    offset, size = _parse_sections(npe)[section_index]
    section = npe[offset:offset + size]
    encoded = candidate_bytes(section[4:], "swap16", 0)
    frame = encoded[frame_index * 21:(frame_index + 1) * 21]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    actual = parse_mode5_frame(frame)
    assert [
        (field.index, field.start_bit, field.bits,
         field.destination_from_context, field.value)
        for field in actual
    ] == [
        (field["index"], field["byte_index_before"] * 8 +
         field["bit_offset_before"], field["bits"],
         field["destination_from_context"], field["value"])
        for field in report["fields"]
    ]
