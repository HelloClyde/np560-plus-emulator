"""Independent parser for the observed candidate MobiVoice SP mode-5 frame.

The field widths and write destinations were measured from the locally
supplied ``mv_sp.dll`` parser on NP560+ game frames.  They describe that
candidate implementation, not the missing mask-ROM decoder or PCM synthesis.
No vendor binary or encoded game bytes are included here.
"""

from __future__ import annotations

from dataclasses import dataclass


MODE5_FRAME_BYTES = 21

# (number of high-bit-first bits, destination offset from candidate context)
# The first four fields are whole bytes; the remainder are packed.  The
# destination offsets are observations only, not names for codec parameters.
MODE5_FIELD_LAYOUT = (
    (8, 0x462), (8, 0x464), (8, 0x466), (8, 0x468),
    (4, 0x46C), (5, 0x470), (4, 0x498), (5, 0x4C0),
    (5, 0x472), (4, 0x49A), (3, 0x4C2),
    (5, 0x474), (4, 0x49C), (3, 0x4C4),
    (5, 0x476), (4, 0x49E), (3, 0x4C6),
    (5, 0x478), (4, 0x4A0), (3, 0x4C8),
    (5, 0x46A), (4, 0x46E),
    (5, 0x484), (4, 0x4AC), (4, 0x4D4),
    (5, 0x486), (4, 0x4AE), (3, 0x4D6),
    (5, 0x488), (4, 0x4B0), (3, 0x4D8),
    (5, 0x48A), (4, 0x4B2), (3, 0x4DA),
    (5, 0x48C), (4, 0x4B4), (3, 0x4DC),
)

assert sum(width for width, _ in MODE5_FIELD_LAYOUT) == MODE5_FRAME_BYTES * 8


@dataclass(frozen=True)
class CandidateField:
    index: int
    start_bit: int
    bits: int
    destination_from_context: int
    value: int


def msb_bits(source: bytes, start_bit: int, count: int) -> int:
    """Read up to 16 bits without depending on the candidate DLL."""
    if start_bit < 0 or count < 1 or count > 16 or start_bit + count > len(source) * 8:
        raise ValueError("bit range exceeds source")
    value = 0
    for position in range(start_bit, start_bit + count):
        value = (value << 1) | ((source[position // 8] >>
                                (7 - position % 8)) & 1)
    return value


def parse_mode5_frame(frame: bytes) -> tuple[CandidateField, ...]:
    """Parse one already-normalized 21-byte candidate frame."""
    if len(frame) != MODE5_FRAME_BYTES:
        raise ValueError("candidate mode-5 frame must contain exactly 21 bytes")
    bit = 0
    fields = []
    for index, (width, destination) in enumerate(MODE5_FIELD_LAYOUT):
        fields.append(CandidateField(
            index=index,
            start_bit=bit,
            bits=width,
            destination_from_context=destination,
            value=msb_bits(frame, bit, width),
        ))
        bit += width
    return tuple(fields)
