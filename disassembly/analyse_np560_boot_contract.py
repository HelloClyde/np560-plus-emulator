#!/usr/bin/env python3
"""Verify the NP560+ boot contract recovered from the shipped images.

This is deliberately an evidence checker, not a ROM-byte generator.  It pins
the instruction signatures that constrain a clean-room resident ROM and the
QEMU memory model.  If a different firmware revision is supplied, a mismatch
is reported instead of silently carrying the V3.80 conclusions across.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROGRAM = ROOT / "NP560+V3.80版系统升级程序" / "NP560.PRG"
DEFAULT_BURNER = (
    ROOT / "NP560+V3.80版系统升级程序" / "BURN_NAND_FLASH_CODE.bin"
)


class EvidenceMismatch(ValueError):
    """Raised when an input image does not contain the pinned V3.80 code."""


@dataclass(frozen=True)
class WordImage:
    name: str
    data: bytes
    base: int
    byteorder: str

    def words_at(self, address: int, count: int) -> tuple[int, ...]:
        offset = address - self.base
        size = count * 2
        if offset < 0 or offset + size > len(self.data) or offset & 1:
            raise EvidenceMismatch(
                f"{self.name}: address 0x{address:06X} is outside the image"
            )
        return tuple(
            int.from_bytes(self.data[index:index + 2], self.byteorder)
            for index in range(offset, offset + size, 2)
        )

    def expect(self, address: int, expected: Iterable[int], label: str) -> None:
        expected_tuple = tuple(expected)
        actual = self.words_at(address, len(expected_tuple))
        if actual != expected_tuple:
            actual_text = " ".join(f"{word:04X}" for word in actual)
            expected_text = " ".join(f"{word:04X}" for word in expected_tuple)
            raise EvidenceMismatch(
                f"{self.name}: {label} at {format_address(address)}: "
                f"expected {expected_text}, found {actual_text}"
            )


def format_address(address: int) -> str:
    return f"{address >> 16:02X}:{address & 0xFFFF:04X}"


def count_word_pattern(
    image: WordImage,
    start: int,
    end: int,
    pattern: tuple[int, ...],
) -> int:
    words = image.words_at(start, (end - start) // 2)
    return sum(
        words[index:index + len(pattern)] == pattern
        for index in range(len(words) - len(pattern) + 1)
    )


def count_direct_calls_to_segment(image: WordImage, segment: int) -> int:
    """Count literal SCALL opcodes selecting one code segment."""
    if not 0 <= segment <= 0xFF:
        raise ValueError("code segment must fit in eight bits")
    words = image.words_at(image.base, len(image.data) // 2)
    return sum(word == (0xBD00 | segment) for word in words[:-1])


def count_direct_calls_to_address(image: WordImage, address: int) -> int:
    """Count literal two-word SCALLs to one 24-bit code address."""
    words = image.words_at(image.base, len(image.data) // 2)
    pattern = (0xBD00 | ((address >> 16) & 0xFF), address & 0xFFFF)
    return count_word_pattern(image, image.base,
                              image.base + len(image.data), pattern)


def count_far_transfers_to_address(image: WordImage, address: int) -> int:
    """Count literal SCALL or SJMP transfers to one 24-bit code address."""
    return sum(
        count_word_pattern(
            image,
            image.base,
            image.base + len(image.data),
            (opcode | ((address >> 16) & 0xFF), address & 0xFFFF),
        )
        for opcode in (0xBD00, 0xAD00)
    )


def find_program_copy_descriptors(program: WordImage) -> list[dict[str, int]]:
    """Find compiler initializer records that call the overlay at 32:F786."""
    words = program.words_at(program.base, len(program.data) // 2)
    descriptors: list[dict[str, int]] = []
    index = 0
    while index + 12 < len(words):
        if not (
            words[index] == 0x68F0
            and words[index + 2] == 0x68F1
            and words[index + 4] == 0x68F2
            and words[index + 6] == 0x68F3
        ):
            index += 1
            continue
        cursor = index + 8
        if words[cursor] & 0xFFF0 == 0x4840:
            length = words[cursor] & 0xF
            cursor += 1
        elif words[cursor] == 0x68F4:
            length = words[cursor + 1]
            cursor += 2
        else:
            index += 1
            continue
        if words[cursor:cursor + 2] != (0xBD32, 0xF786):
            index += 1
            continue
        descriptors.append({
            "address": program.base + index * 2,
            "end": program.base + (cursor + 2) * 2,
            "destination": (words[index + 1] << 16) | words[index + 3],
            "source": (words[index + 5] << 16) | words[index + 7],
            "length": length,
        })
        index = cursor + 2
    return descriptors


def group_contiguous_descriptors(
    descriptors: list[dict[str, int]],
) -> list[list[dict[str, int]]]:
    groups: list[list[dict[str, int]]] = []
    for descriptor in descriptors:
        if groups and descriptor["address"] == groups[-1][-1]["end"]:
            groups[-1].append(descriptor)
        else:
            groups.append([descriptor])
    return groups


def analyse_contract(program_bytes: bytes, burner_bytes: bytes) -> dict[str, Any]:
    """Return verified facts and explicitly labelled model inferences."""
    program = WordImage("NP560.PRG", program_bytes, 0x200000, "little")
    burner = WordImage(
        "BURN_NAND_FLASH_CODE.bin", burner_bytes, 0x506000, "big"
    )

    # Reset performs a resident call and then selects logical 33:4F50.  Flat
    # PRG at that address is inside an event handler, but the exact same-PC
    # source at 50:4F50 proves the reset code bank uses a linked ROM alias.
    program.expect(
        0x200000,
        (0xBD03, 0x0030, 0xAD33, 0x4F50),
        "reset resident call and continuation",
    )
    program.expect(
        0x334510,
        (0x2E0A, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
         0x780B, 0x0008, 0x781B, 0x000A),
        "ordinary event-handler prologue and context argument loads",
    )
    program.expect(
        0x334730,
        (0x780B, 0x0006, 0x68F1, 0x008E, 0x1601, 0xAC01, 0x4E80),
        "event-0x008E dispatch",
    )
    program.expect(
        0x334F42,
        (0x70F3, 0x0030, 0x5120, 0x70F1, 0x0038,
         0x5100, 0x4C11, 0x5C01),
        "activation-path pointer preparation and reset continuation",
    )
    # The reset continuation itself is a bounded resident preamble with an
    # exact same-PC source at segment +0x1D.  It selects three memory segments
    # and jumps to a second exact linked preamble, which initializes SP/FP and
    # enters the 261-descriptor chain at its resident 11:* address.
    program.expect(
        0x504F50,
        (0xE600, 0xE700, 0x6804, 0x5002, 0x6805, 0x6003,
         0x6806, 0xF003, 0xAD33, 0x603C),
        "factory reset preamble linked source",
    )
    program.expect(
        0x50603C,
        (0x68FF, 0x1000, 0x68FB, 0x1000, 0xAD11, 0x4560),
        "factory compiler-start preamble linked source",
    )
    linked_transfer_counts = {
        "33:603C": count_far_transfers_to_address(program, 0x33603C),
        "11:4560": count_far_transfers_to_address(program, 0x114560),
        "07:7FE4": count_far_transfers_to_address(program, 0x077FE4),
        "03:026A": count_far_transfers_to_address(program, 0x03026A),
    }
    if linked_transfer_counts != {
        "33:603C": 1,
        "11:4560": 1,
        "07:7FE4": 1,
        "03:026A": 1,
    }:
        raise EvidenceMismatch(
            "NP560.PRG: factory linked transfer chain changed: "
            f"{linked_transfer_counts!r}"
        )
    linked_source_transfer_counts = {
        "50:603C": count_far_transfers_to_address(program, 0x50603C),
        "2E:4560": count_far_transfers_to_address(program, 0x2E4560),
        "24:7FE4": count_far_transfers_to_address(program, 0x247FE4),
        "20:026A": count_far_transfers_to_address(program, 0x20026A),
    }
    if any(linked_source_transfer_counts.values()):
        raise EvidenceMismatch(
            "NP560.PRG: linked storage address unexpectedly called/jumped: "
            f"{linked_source_transfer_counts!r}"
        )

    # The fixed application callback is self-contained and returns normally.
    program.expect(
        0x200030,
        (0x2E02, 0x58F0, 0x58F1, 0x58F3),
        "fixed callback prologue",
    )
    for address, words, label in (
        (0x200038, (0x68F1, 0x2082), "memory register 0x7100 value"),
        (0x200042, (0xA8F1, 0x7100), "memory register 0x7100 store"),
        (0x200046, (0x68F1, 0x5001), "memory register 0x7108 value"),
        (0x200050, (0xA8F1, 0x7108), "memory register 0x7108 store"),
        (0x200054, (0x4800, 0x68F1, 0x0100), "first clear start"),
        (0x200098, (0x72F1, 0x0FA0, 0x5300), "first clear limit"),
        (0x2000A2, (0x4800, 0x68F1, 0x0FF0), "second clear start"),
        (0x2000E6, (0x72F1, 0x5000, 0x5300), "second clear limit"),
        (0x2000F0, (0x4800, 0x68F1, 0x8000), "third clear start"),
        (0x200134, (0x72F1, 0x9000, 0x5300), "third clear limit"),
        (0x20013E, (0x68F0, 0x0050, 0x4810), "far clear start"),
        (0x200182, (0x5210, 0x73F0, 0x0054), "far clear limit"),
        (0x200192, (0x2F00, 0xC620), "fixed callback return"),
    ):
        program.expect(address, words, label)
    program.expect(
        0x20031C,
        (0xBD2D, 0x7DD2, 0x4800, 0x381F, 0x2F00, 0xC620),
        "sole application call followed by startup epilogue",
    )
    application_dispatch_calls = count_direct_calls_to_address(
        program, 0x2D7DD2
    )
    resident_0080_references = sum(
        count_word_pattern(
            program, program.base, program.base + len(program.data), pattern
        )
        for pattern in ((0xBD03, 0x0080), (0xAD03, 0x0080))
    )
    if application_dispatch_calls != 1 or resident_0080_references != 0:
        raise EvidenceMismatch(
            "NP560.PRG: expected one 2D:7DD2 startup call and no literal "
            "resident 03:0080 references, found "
            f"{application_dispatch_calls} and {resident_0080_references}"
        )

    # A complete no-argument function exists at the same PC in segment 49.
    # It preserves the caller registers, updates exactly the memory-controller
    # register families initialized by 20:026A, and returns normally.  Segment
    # 49 has no literal SCALL sites anywhere in the image, consistent with
    # loader source storage rather than an in-place execution segment.
    program.expect(
        0x499A7C,
        (0x2E00, 0x58F0, 0x58F1, 0x6810, 0x0001,
         0x88F1, 0x7160, 0x4800, 0x74F1, 0xF0FF),
        "same-PC complete memory-initializer candidate",
    )
    program.expect(
        0x499AF2,
        (0xBD33, 0x6030, 0xBD08, 0x427E),
        "memory-initializer nested calls",
    )
    program.expect(
        0x499C5E,
        (0x381F, 0x380F, 0x2F00, 0xC620),
        "memory-initializer epilogue",
    )
    segment_49_direct_calls = count_direct_calls_to_segment(program, 0x49)
    if segment_49_direct_calls != 0:
        raise EvidenceMismatch(
            "NP560.PRG: expected segment 49 to have no literal SCALL sites, "
            f"found {segment_49_direct_calls}"
        )

    # The first nested call has the same overlay conflict.  Flat 33:6030 is a
    # large parameterized function, while 50:6030 is a complete no-argument
    # wrapper.  Its nested 33:5906 target likewise has a short complete source
    # at 50:5906 instead of the flat target's frame-relative shared tail.
    program.expect(
        0x336030,
        (0x2EFF, 0x52F6, 0x58F0, 0x58F1, 0x58F2, 0x58F3),
        "flat incompatible 33:6030 function",
    )
    program.expect(
        0x336096,
        (0x780B, 0x0006),
        "flat 33:6030 parameter access",
    )
    program.expect(
        0x506030,
        (0x2E00, 0xBD33, 0x5906, 0x4800, 0x2F00, 0xC620),
        "same-PC no-argument 33:6030 overlay source",
    )
    program.expect(
        0x335906,
        (0x780B, 0x0012, 0x781B, 0x0014, 0x68FE, 0x5920),
        "flat incompatible 33:5906 shared tail",
    )
    program.expect(
        0x505906,
        (0x2E00, 0xFA39, 0xFA41, 0xEA49,
         0xEA31, 0x4800, 0x2F00, 0xC620),
        "same-PC no-argument 33:5906 overlay source",
    )
    system_init_source_calls = count_direct_calls_to_address(program, 0x506030)
    system_bits_source_calls = count_direct_calls_to_address(program, 0x505906)
    if system_init_source_calls or system_bits_source_calls:
        raise EvidenceMismatch(
            "NP560.PRG: expected 50:5906 and 50:6030 overlay sources to "
            "have no literal in-place calls"
        )

    # A later application transition exposes the same collision at 33:5B70.
    # The flat destination is a frame-relative shared tail, whereas 50:5B70
    # is a complete no-argument state-byte reader with a balanced epilogue.
    program.expect(
        0x335B70,
        (0xFFF8, 0x783B, 0xFFFA, 0x0840, 0x0851, 0x1053, 0x1142),
        "flat incompatible 33:5B70 shared tail",
    )
    program.expect(
        0x505B70,
        (0x2E00, 0x6810, 0x00A0, 0x99F0, 0x7E58, 0x2F00, 0xC620),
        "same-PC complete application-state-byte overlay source",
    )
    application_state_byte_destination_calls = count_direct_calls_to_address(
        program, 0x335B70
    )
    application_state_byte_source_calls = count_direct_calls_to_address(
        program, 0x505B70
    )
    if (application_state_byte_destination_calls != 36 or
            application_state_byte_source_calls):
        raise EvidenceMismatch(
            "NP560.PRG: expected 36 literal calls to overlay target 33:5B70 "
            "and no in-place 50:5B70 source calls"
        )

    # Two independent callers bracket 08:427E with the same controller-reset
    # and software-state-reset calls.  Both flat targets are impossible naked
    # entries, whereas their same-PC segment 4E/50 copies are complete
    # no-argument functions with normal epilogues and no in-place callers.
    reset_sequence = (
        0x4800, 0x6810, 0x00A2, 0xC700, 0xA8F0, 0x2A44,
        0xBD31, 0xAF72, 0xBD08, 0x427E, 0xBD33, 0x38D6,
    )
    program.expect(0x2B93B2, reset_sequence,
                   "first controller/ROM/software reset sequence")
    program.expect(0x3F9AAC, reset_sequence,
                   "second controller/ROM/software reset sequence")
    program.expect(
        0x31AF72,
        (0xAC00, 0xB3D0, 0x6810, 0x00A4, 0x99F1),
        "flat incompatible 31:AF72 branch fragment",
    )
    program.expect(
        0x4EAF72,
        (0x2E01, 0x58F0, 0x68F0, 0x4000, 0x6810, 0x0001,
         0xB5F0, 0x7100, 0x68F0, 0x85E3, 0x6810, 0x0001,
         0xC700, 0xA8F0, 0x72D4),
        "same-PC complete controller-reset overlay source",
    )
    program.expect(
        0x4EB00E,
        (0x380F, 0x2F00, 0xC620),
        "controller-reset overlay epilogue",
    )
    program.expect(
        0x31B014,
        (0x7050, 0x50F2, 0x5600, 0xAC01, 0xB756),
        "flat incompatible 31:B014 branch fragment",
    )
    program.expect(
        0x4EB014,
        (0x2E01, 0x58F0, 0x58F1, 0x780B, 0x0006,
         0x6B1B, 0x0006, 0x791B, 0x0006, 0x1901),
        "same-PC complete one-argument memory-mode overlay source",
    )
    program.expect(
        0x4EB0AE,
        (0x381F, 0x380F, 0x2F00, 0xC620),
        "memory-mode overlay epilogue",
    )
    program.expect(
        0x3338D6,
        (0x1F90, 0x4D11, 0x2801, 0x1630),
        "flat incompatible 33:38D6 fragment",
    )
    program.expect(
        0x5038D6,
        (0x2E00, 0x58F0, 0x4800, 0x6810, 0x00A2, 0xC700,
         0xA8F0, 0x2A84, 0x4800, 0x6810, 0x00A2, 0xC700,
         0xA8F0, 0x2A80, 0x380F, 0x2F00, 0xC620),
        "same-PC complete software-state-reset overlay source",
    )
    controller_reset_source_calls = count_direct_calls_to_address(
        program, 0x4EAF72
    )
    memory_mode_destination_calls = count_direct_calls_to_address(
        program, 0x31B014
    )
    memory_mode_source_calls = count_direct_calls_to_address(
        program, 0x4EB014
    )
    global_reset_source_calls = count_direct_calls_to_address(
        program, 0x5038D6
    )
    if memory_mode_destination_calls != 130:
        raise EvidenceMismatch(
            "NP560.PRG: expected 130 literal calls to overlay target "
            f"31:B014, found {memory_mode_destination_calls}"
        )
    if (controller_reset_source_calls or memory_mode_source_calls or
            global_reset_source_calls):
        raise EvidenceMismatch(
            "NP560.PRG: expected 4E:AF72, 4E:B014, and 50:38D6 overlay "
            "sources to have no literal in-place calls"
        )

    # The next startup call has the same signature: 33:305E starts in a
    # conditional branch fragment, while 50:305E is a complete one-argument
    # function that stores the mode byte, calls 33:180A, and returns normally.
    program.expect(
        0x33305E,
        (0xAC01, 0x30E6, 0x68F0, 0x03E8, 0x58F0),
        "flat incompatible 33:305E branch fragment",
    )
    program.expect(
        0x50305E,
        (0x2E00, 0x58F0, 0x780B, 0x0006, 0x6B1B, 0x0006,
         0x791B, 0x0006, 0x6810, 0x00A2, 0xC700, 0xA9F1,
         0x2A36, 0xBD33, 0x180A, 0x380F, 0x2F00, 0xC620),
        "same-PC complete one-argument mode initializer source",
    )
    mode_init_destination_calls = count_direct_calls_to_address(
        program, 0x33305E
    )
    mode_init_source_calls = count_direct_calls_to_address(program, 0x50305E)
    if mode_init_destination_calls != 7 or mode_init_source_calls:
        raise EvidenceMismatch(
            "NP560.PRG: expected seven 33:305E calls and no in-place "
            "50:305E source calls"
        )
    program.expect(
        0x33180A,
        (0xFFE0, 0x781B, 0xFFE2, 0x5210, 0x5300),
        "flat incompatible 33:180A frame-relative fragment",
    )
    program.expect(
        0x50180A,
        (0x2E00, 0x58F0, 0x58F1, 0x68F1, 0x0010, 0x6810,
         0x00A2, 0x99F0, 0x2A36, 0x1210, 0x68F0, 0xFFFF,
         0x0C03, 0x4A03, 0x6810, 0x00A2, 0xC700, 0xA8F0,
         0x2A34, 0x381F, 0x380F, 0x2F00, 0xC620),
        "same-PC complete no-argument mode-mask source",
    )
    mode_mask_destination_calls = count_direct_calls_to_address(
        program, 0x33180A
    )
    mode_mask_source_calls = count_direct_calls_to_address(program, 0x50180A)
    if mode_mask_destination_calls != 1 or mode_mask_source_calls:
        raise EvidenceMismatch(
            "NP560.PRG: expected one 33:180A call and no in-place 50:180A "
            "source calls"
        )

    # The next no-argument startup call has the same overlay signature.
    # Flat 32:4218 is in the middle of a large frame-relative function.  The
    # same PC in the otherwise uncalled source segment 4F is a complete LINK
    # #1 function which preserves its caller state and returns normally.
    program.expect(
        0x324218,
        (0x4C11, 0x5C01, 0x58F0, 0x1F90, 0x4D11, 0x2911),
        "flat incompatible 32:4218 shared tail",
    )
    program.expect(
        0x4F4218,
        (0x2E01, 0x58F0, 0x58F2, 0x58F3, 0x58F4, 0x58F5,
         0x69F1, 0x0010, 0x6810, 0x00A1),
        "same-PC complete no-argument startup-table source",
    )
    program.expect(
        0x4F4282,
        (0x385F, 0x384F, 0x383F, 0x382F, 0x380F, 0x2F00, 0xC620),
        "startup-table overlay epilogue",
    )
    startup_table_destination_calls = count_direct_calls_to_address(
        program, 0x324218
    )
    startup_table_source_calls = count_direct_calls_to_address(
        program, 0x4F4218
    )
    if startup_table_destination_calls != 4 or startup_table_source_calls:
        raise EvidenceMismatch(
            "NP560.PRG: expected four 32:4218 calls and no in-place "
            "4F:4218 source calls"
        )

    program.expect(
        0x32CC9C,
        (0x50F1, 0x3B1F, 0x782B, 0xFFFC, 0x4C21, 0x5021),
        "flat incompatible 32:CC9C shared tail",
    )
    program.expect(
        0x4FCC9C,
        (0x2E00, 0x58F0, 0x58F1, 0x58F3, 0x3F11,
         0x88F0, 0x04FC, 0x88F1, 0x04FE, 0x4830),
        "same-PC complete no-argument startup-pointer source",
    )
    program.expect(
        0x4FCCD8,
        (0xBD18, 0x6D56, 0x50FA, 0x383F, 0x381F,
         0x380F, 0x2F00, 0xC620),
        "startup-pointer overlay nested call and epilogue",
    )
    startup_pointer_destination_calls = count_direct_calls_to_address(
        program, 0x32CC9C
    )
    startup_pointer_source_calls = count_direct_calls_to_address(
        program, 0x4FCC9C
    )
    if startup_pointer_destination_calls != 88 or startup_pointer_source_calls:
        raise EvidenceMismatch(
            "NP560.PRG: expected 88 32:CC9C calls and no in-place "
            "4F:CC9C source calls"
        )

    program.expect(
        0x328EBE,
        (0x5C01, 0x58F0, 0x1F90, 0x4D11, 0x2801, 0x4C51),
        "flat incompatible 32:8EBE shared tail",
    )
    program.expect(
        0x4F8EBE,
        (0x2E01, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
         0x4800, 0x6A0B, 0xFFFE),
        "same-PC complete no-argument startup-array source",
    )
    program.expect(
        0x4F8F14,
        (0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, 0xC620),
        "startup-array overlay epilogue",
    )
    startup_array_destination_calls = count_direct_calls_to_address(
        program, 0x328EBE
    )
    startup_array_source_calls = count_direct_calls_to_address(
        program, 0x4F8EBE
    )
    if startup_array_destination_calls != 3 or startup_array_source_calls:
        raise EvidenceMismatch(
            "NP560.PRG: expected three 32:8EBE calls and no in-place "
            "4F:8EBE source calls"
        )

    program.expect(
        0x314BAC,
        (0x1901, 0x5600, 0xAC02, 0x4E28, 0x780B, 0xFFFC),
        "flat incompatible 31:4BAC frame-relative body",
    )
    program.expect(
        0x4E4BAC,
        (0x2E04, 0x58F0, 0x58F1, 0xBD33, 0x5CB2,
         0x1901, 0x5601),
        "same-PC complete no-argument startup-runtime source",
    )
    program.expect(
        0x4E4C58,
        (0xBD33, 0x3C86, 0xBD33, 0x2FF2,
         0x381F, 0x380F, 0x2F00, 0xC620),
        "startup-runtime nested calls and epilogue",
    )
    startup_runtime_destination_calls = count_direct_calls_to_address(
        program, 0x314BAC
    )
    startup_runtime_source_calls = count_direct_calls_to_address(
        program, 0x4E4BAC
    )
    if startup_runtime_destination_calls != 128 or startup_runtime_source_calls:
        raise EvidenceMismatch(
            "NP560.PRG: expected 128 31:4BAC calls and no in-place "
            "4E:4BAC source calls"
        )

    for address, words, label in (
        (0x335CB2, (0x782B, 0xFFFC, 0x783B, 0xFFFE),
         "flat incompatible 33:5CB2 shared tail"),
        (0x505CB2, (0x2E00, 0x6810, 0x00A1, 0x99F0, 0x386C,
                    0x2F00, 0xC620),
         "same-PC complete system-mode query"),
        (0x333C86, (0x4800, 0x783B, 0xFFFE, 0x5630),
         "flat incompatible 33:3C86 shared tail"),
        (0x503C86, (0x2E00, 0x58F0, 0x58F1, 0x68F1, 0x2734,
                    0x68F0, 0x0051, 0x58F1, 0x58F0,
                    0xBD14, 0x6E10, 0x50F4,
                    0x381F, 0x380F, 0x2F00, 0xC620),
         "same-PC complete table-service wrapper"),
        (0x332FF2, (0x4970, 0x3F11, 0x59F7, 0x52F1),
         "flat incompatible 33:2FF2 shared tail"),
        (0x502FF2, (0x2E00, 0x58F0, 0x58F1, 0x68F1, 0x3840,
                    0x68F0, 0x0050, 0x58F1, 0x58F0, 0x4800,
                    0x58F0, 0xBD14, 0x6AEC, 0x50F6,
                    0x381F, 0x380F, 0x2F00, 0xC620),
         "same-PC complete region-service wrapper"),
    ):
        program.expect(address, words, label)
    nested_startup_specs = (
        (0x335CB2, 0x505CB2, 35),
        (0x333C86, 0x503C86, 29),
        (0x332FF2, 0x502FF2, 107),
    )
    nested_startup_counts = []
    for destination, source, expected_calls in nested_startup_specs:
        destination_calls = count_direct_calls_to_address(program, destination)
        source_calls = count_direct_calls_to_address(program, source)
        if destination_calls != expected_calls or source_calls:
            raise EvidenceMismatch(
                f"NP560.PRG: expected {expected_calls} calls to "
                f"{format_address(destination)} and no in-place calls to "
                f"{format_address(source)}"
            )
        nested_startup_counts.append((destination_calls, source_calls))

    # The recovered 08:3292 body makes one naked call to 24:9BD4.  Flat
    # 24:9BD4 is inside a parameterized byte-counting routine, while the same
    # PC in segment 41 is a bounded no-argument SFR initializer.
    program.expect(
        0x249BD4,
        (0x0006, 0x781B, 0x0008, 0x4C11, 0x5C01, 0x58F0),
        "flat incompatible 24:9BD4 shared tail",
    )
    program.expect(
        0x419BD4,
        (0x6821, 0x0000, 0x6822, 0x0000,
         0xEE8E, 0xEF8E, 0xF18E, 0xEB8E, 0x3F00, 0xC620),
        "same-PC complete peripheral/SFR initializer",
    )
    peripheral_init_destination_calls = count_direct_calls_to_address(
        program, 0x249BD4
    )
    peripheral_init_source_calls = count_direct_calls_to_address(
        program, 0x419BD4
    )
    if (peripheral_init_destination_calls != 1 or
            peripheral_init_source_calls):
        raise EvidenceMismatch(
            "NP560.PRG: expected one 24:9BD4 call and no in-place "
            "41:9BD4 source calls"
        )

    # 33:4F76 pushes two words before calling 30:9E30.  The flat target starts
    # with POP and is a shared epilogue inside another function.  Same-PC
    # 4D:9E30 is an otherwise uncalled complete LINK #4 function, reads its
    # two arguments from FP+6/FP+8, and returns through its own epilogue.
    program.expect(
        0x334F6A,
        (0x780B, 0xFFFC, 0x781B, 0xFFFE, 0x58F1, 0x58F0,
         0xBD30, 0x9E30, 0x50F4),
        "two-word caller of activation-context function",
    )
    program.expect(
        0x309E30,
        (0x1F90, 0x4D11, 0x0A12, 0x68F1, 0x0094, 0x4800),
        "flat incompatible 30:9E30 shared epilogue",
    )
    program.expect(
        0x4D9E30,
        (0x2E04, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
         0x780B, 0x0006, 0x781B, 0x0008,
         0x6A0B, 0xFFFC, 0x6A1B, 0xFFFE),
        "same-PC complete activation-context entry",
    )
    program.expect(
        0x4D9F14,
        (0x383F, 0x382F, 0x381F, 0x380F, 0x2F00, 0xC620),
        "same-PC activation-context epilogue",
    )
    activation_context_destination_calls = count_direct_calls_to_address(
        program, 0x309E30
    )
    activation_context_source_calls = count_direct_calls_to_address(
        program, 0x4D9E30
    )
    if (activation_context_destination_calls != 17 or
            activation_context_source_calls):
        raise EvidenceMismatch(
            "NP560.PRG: expected 17 calls to 30:9E30 and no in-place "
            "4D:9E30 source calls"
        )

    # The three-word service called at 32:D530 has the same overlay conflict.
    # Flat 32:D530 starts after its LINK and can branch directly to another
    # function's common epilogue; uncalled 4F:D530 is the complete wrapper.
    program.expect(
        0x2C9DC2,
        (0x4810, 0x58F1, 0x68F1, 0x7740, 0x68F0, 0x002D,
         0x58F1, 0x58F0, 0xBD32, 0xD530, 0x50F6),
        "three-word caller of pointer service",
    )
    program.expect(
        0x32D530,
        (0x781B, 0xFFFC, 0x5610, 0xAC02, 0xD53E, 0xAC00, 0xE2AA),
        "flat incompatible 32:D530 shared tail",
    )
    program.expect(
        0x4FD530,
        (0x2E01, 0x58F0, 0x58F1, 0xBD33, 0x5FD0,
         0x6B1B, 0xFFFF, 0x68F0, 0x00F0),
        "same-PC complete pointer-service entry",
    )
    program.expect(
        0x4FD56A,
        (0xBD33, 0x4492, 0x50F2,
         0x381F, 0x380F, 0x2F00, 0xC620),
        "same-PC pointer-service epilogue",
    )
    pointer_service_destination_calls = count_direct_calls_to_address(
        program, 0x32D530
    )
    pointer_service_cleanups = count_word_pattern(
        program,
        program.base,
        program.base + len(program.data),
        (0xBD32, 0xD530, 0x50F6),
    )
    pointer_service_source_calls = count_direct_calls_to_address(
        program, 0x4FD530
    )
    if (pointer_service_destination_calls != 306 or
            pointer_service_cleanups != pointer_service_destination_calls or
            pointer_service_source_calls):
        raise EvidenceMismatch(
            "NP560.PRG: expected 306 three-word calls to 32:D530 and no "
            "in-place 4F:D530 source calls"
        )

    # Direct dependencies of 4F:D530 follow the same fixed +0x1D segment
    # storage convention. Pin both incompatible flat entries and complete
    # source bodies, including the argument-cleanup counts where applicable.
    program.expect(
        0x335FD0,
        (0x000E, 0x783B, 0x0010, 0x1213, 0x1302, 0xAC0C, 0x601C),
        "flat incompatible 33:5FD0 shared tail",
    )
    program.expect(
        0x505FD0,
        (0x2E00, 0xBD33, 0x5C18, 0x1901, 0x2F00, 0xC620),
        "same-PC complete pointer-state wrapper",
    )
    program.expect(
        0x335C18,
        (0x1253, 0x1342, 0x4C51, 0x5C41, 0x58F4, 0x1F90),
        "flat incompatible 33:5C18 shared tail",
    )
    program.expect(
        0x505C18,
        (0x2E00, 0x6810, 0x00A1, 0x99F0, 0x384E, 0x2F00, 0xC620),
        "same-PC complete pointer-flag getter",
    )
    program.expect(
        0x334492,
        (0x4D11, 0x2801, 0x5600, 0xAC02, 0x44E6, 0x4910),
        "flat incompatible 33:4492 shared tail",
    )
    program.expect(
        0x504492,
        (0x2E00, 0x780B, 0x0006, 0x6B1B, 0x0006,
         0x791B, 0x0006, 0x1901, 0x58F0,
         0xBD2F, 0x5B98, 0x50F2, 0x2F00, 0xC620),
        "same-PC complete pointer-normalize wrapper",
    )
    program.expect(
        0x31F282,
        (0x58F0, 0xBD03, 0x4010, 0x50FA, 0x4804, 0x58F0),
        "flat incompatible 31:F282 shared tail",
    )
    program.expect(
        0x4EF282,
        (0x2E03, 0x58F0, 0x58F1,
         0x780B, 0x0006, 0x781B, 0x0008,
         0x58F1, 0x58F0, 0xBD21, 0xFD80, 0x50F4),
        "same-PC complete pointer-resolve entry",
    )
    program.expect(
        0x4EF304,
        (0xBD32, 0xC476, 0x50F2,
         0x381F, 0x380F, 0x2F00, 0xC620),
        "same-PC pointer-resolve epilogue",
    )
    pointer_dependency_specs = (
        (0x335FD0, 0x505FD0, 11, None),
        (0x335C18, 0x505C18, 13, None),
        (0x334492, 0x504492, 56, (0xBD33, 0x4492, 0x50F2)),
        (0x31F282, 0x4EF282, 40, (0xBD31, 0xF282, 0x50F6)),
    )
    pointer_dependency_counts = []
    for destination, source, expected_calls, cleanup_pattern in (
            pointer_dependency_specs):
        destination_calls = count_direct_calls_to_address(program, destination)
        source_calls = count_direct_calls_to_address(program, source)
        cleanup_count = (
            count_word_pattern(
                program, program.base, program.base + len(program.data),
                cleanup_pattern,
            )
            if cleanup_pattern else None
        )
        if (destination_calls != expected_calls or source_calls or
                (cleanup_pattern and cleanup_count != destination_calls)):
            raise EvidenceMismatch(
                f"NP560.PRG: invalid same-PC pointer dependency "
                f"{format_address(destination)} <- {format_address(source)}"
            )
        pointer_dependency_counts.append(
            (destination_calls, source_calls, cleanup_count)
        )

    # The final direct call in 4D:9E30 reaches 27:507C with four stack words.
    # Flat 27:507C starts in the body of a different function. Same-PC
    # 44:507C is a complete LINK #0x0A dispatch function with balanced RETS.
    program.expect(
        0x4D9F00,
        (0x70F1, 0x0012, 0x5100, 0x0801, 0x58F0, 0x4800, 0x58F0,
         0xBD27, 0x507C, 0x50F8),
        "four-word activation-dispatch caller",
    )
    program.expect(
        0x27507C,
        (0x003C, 0x5120, 0x4C31, 0x5C21, 0x58F2, 0x1F90),
        "flat incompatible 27:507C shared body",
    )
    program.expect(
        0x44507C,
        (0x2E0A, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F6, 0x58F7,
         0x781B, 0x0006, 0x5610, 0xAC0E, 0x509A),
        "same-PC complete activation-dispatch entry",
    )
    program.expect(
        0x4453BC,
        (0x387F, 0x386F, 0x383F, 0x382F,
         0x381F, 0x380F, 0x2F00, 0xC620),
        "same-PC activation-dispatch epilogue",
    )
    activation_dispatch_destination_calls = count_direct_calls_to_address(
        program, 0x27507C
    )
    activation_dispatch_cleanups = count_word_pattern(
        program, program.base, program.base + len(program.data),
        (0xBD27, 0x507C, 0x50F8),
    )
    activation_dispatch_source_calls = count_direct_calls_to_address(
        program, 0x44507C
    )
    if (activation_dispatch_destination_calls != 165 or
            activation_dispatch_cleanups != activation_dispatch_destination_calls or
            activation_dispatch_source_calls):
        raise EvidenceMismatch(
            "NP560.PRG: expected 165 four-word calls to 27:507C and no "
            "in-place 44:507C source calls"
        )

    # After activation-context setup, 33:4F82 calls 31:C0E8 with one word.
    # Its complete 4E source is a six-way wrapper around another complete
    # one-word same-PC property setter at 4E:4D24.
    for address, words, label in (
        (0x31C0E8, (0x58F0, 0x780B, 0xFFFC, 0x781B, 0xFFFE),
         "flat incompatible 31:C0E8 shared body"),
        (0x4EC0E8, (0x2E00, 0x58F0, 0x780B, 0x0006, 0x5401,
                    0x5600, 0xAC01, 0xC104),
         "same-PC complete application-property entry"),
        (0x4EC180, (0x380F, 0x2F00, 0xC620),
         "same-PC application-property epilogue"),
        (0x314D24, (0xFFF4, 0x6810, 0x0066, 0x88F4, 0x3A96),
         "flat incompatible 31:4D24 shared body"),
        (0x4E4D24, (0x2E04, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
                    0x58F4, 0x58F5, 0x58F6, 0x58F7),
         "same-PC complete property-setter entry"),
        (0x4E4DD0, (0x385F, 0x384F, 0x383F, 0x382F,
                    0x381F, 0x380F, 0x2F00, 0xC620),
         "same-PC property-setter epilogue"),
    ):
        program.expect(address, words, label)
    application_property_destination_calls = count_direct_calls_to_address(
        program, 0x31C0E8
    )
    application_property_source_calls = count_direct_calls_to_address(
        program, 0x4EC0E8
    )
    application_property_cleanups = count_word_pattern(
        program, program.base, program.base + len(program.data),
        (0xBD31, 0xC0E8, 0x50F2),
    )
    property_setter_destination_calls = count_direct_calls_to_address(
        program, 0x314D24
    )
    property_setter_source_calls = count_direct_calls_to_address(
        program, 0x4E4D24
    )
    property_setter_cleanups = count_word_pattern(
        program, program.base, program.base + len(program.data),
        (0xBD31, 0x4D24, 0x50F2),
    )
    if (application_property_destination_calls != 194 or
            application_property_cleanups != 194 or
            application_property_source_calls or
            property_setter_destination_calls != 445 or
            property_setter_cleanups != 445 or property_setter_source_calls):
        raise EvidenceMismatch(
            "NP560.PRG: invalid 31:C0E8/31:4D24 same-PC overlay chain"
        )

    # The recovered 4E:A914 LCD/application initializer also calls 25:206E
    # with five words. That flat address is resource data; 42:206E contains
    # the complete same-PC LINK #6 function and its own balanced epilogue.
    program.expect(
        0x25206E,
        (0xECB1, 0x0768, 0x129F, 0x0BAF, 0xFBDC, 0xF168),
        "flat incompatible 25:206E resource data",
    )
    program.expect(
        0x42206E,
        (0x2E06, 0x58F1, 0x58F2, 0x58F3,
         0x780B, 0x000A, 0x781B, 0x000C,
         0x6A0B, 0xFFFC, 0x6A1B, 0xFFFE),
        "same-PC complete LCD/resource entry",
    )
    program.expect(
        0x42246E,
        (0x383F, 0x382F, 0x381F, 0x2F00, 0xC620),
        "same-PC LCD/resource epilogue",
    )
    lcd_resource_destination_calls = count_direct_calls_to_address(
        program, 0x25206E
    )
    lcd_resource_source_calls = count_direct_calls_to_address(
        program, 0x42206E
    )
    lcd_resource_cleanups = count_word_pattern(
        program, program.base, program.base + len(program.data),
        (0xBD25, 0x206E, 0x50FA),
    )
    if (lcd_resource_destination_calls != 100 or
            lcd_resource_cleanups != 100 or lcd_resource_source_calls):
        raise EvidenceMismatch(
            "NP560.PRG: expected 100 five-word calls to 25:206E and no "
            "in-place 42:206E source calls"
        )

    # The resident 1A:423C implementation is absent from the mask-ROM dump,
    # but NP560.PRG stores a complete same-PC copy at 37:423C. Every one of
    # the 29 callers uses a ten-byte/five-word cleanup; the source starts with
    # LINK #0x41, has its own local RET paths, and ends in a balanced RETS.
    program.expect(
        0x4D9E80,
        (0x3801, 0x2811, 0x58F1, 0x58F0,
         0xBD1A, 0x423C, 0x50FA),
        "five-word call to resident 1A:423C",
    )
    program.expect(
        0x37423C,
        (0x2E41, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4, 0x58F5,
         0x783B, 0x000E, 0x6B7B, 0x000E,
         0x780B, 0x000A, 0x781B, 0x000C),
        "same-PC complete resident 1A:423C source entry",
    )
    program.expect(
        0x374B8C,
        (0x385F, 0x384F, 0x383F, 0x382F,
         0x381F, 0x380F, 0x2F00, 0xC620),
        "same-PC resident 1A:423C source epilogue",
    )
    resident_dispatch_1a_calls = count_direct_calls_to_address(
        program, 0x1A423C
    )
    resident_dispatch_1a_cleanups = count_word_pattern(
        program,
        program.base,
        program.base + len(program.data),
        (0xBD1A, 0x423C, 0x50FA),
    )
    resident_dispatch_1a_source_calls = count_direct_calls_to_address(
        program, 0x37423C
    )
    if (resident_dispatch_1a_calls != 29 or
            resident_dispatch_1a_cleanups != resident_dispatch_1a_calls or
            resident_dispatch_1a_source_calls):
        raise EvidenceMismatch(
            "NP560.PRG: expected 29 five-word calls to resident 1A:423C "
            "and no in-place 37:423C source calls"
        )

    # Application event 0x84 reaches missing resident entry 1F:B496 from the
    # recovered dispatcher path.  NP560.PRG contains its complete same-PC
    # one-argument implementation at 3C:B496; all nine resident calls have a
    # one-word cleanup, while the source address is never called in place.
    program.expect(
        0x3BFC68,
        (0xBD1F, 0xB496, 0x50F2),
        "one-word call to resident application-event dispatcher",
    )
    program.expect(
        0x3CB496,
        (0x2E0C, 0x58F1, 0x58F2, 0x58F3, 0x58F6, 0x58F7,
         0x4800, 0x6A0B, 0xFFF6, 0x4800, 0x6A0B, 0xFFF0,
         0x780B, 0x0006, 0x76F0, 0x0082),
        "same-PC resident application-event source entry",
    )
    program.expect(
        0x3CBA56,
        (0xFFF6, 0x387F, 0x386F, 0x383F,
         0x382F, 0x381F, 0x2F00, 0xC620),
        "resident application-event source epilogue",
    )
    resident_application_event_calls = count_direct_calls_to_address(
        program, 0x1FB496
    )
    resident_application_event_cleanups = count_word_pattern(
        program, program.base, program.base + len(program.data),
        (0xBD1F, 0xB496, 0x50F2),
    )
    resident_application_event_source_calls = count_direct_calls_to_address(
        program, 0x3CB496
    )
    if (resident_application_event_calls != 9 or
            resident_application_event_cleanups !=
            resident_application_event_calls or
            resident_application_event_source_calls):
        raise EvidenceMismatch(
            "NP560.PRG: expected nine one-word calls to resident 1F:B496 "
            "and no in-place 3C:B496 source calls"
        )

    # A complete module linked for resident segment 08 is stored verbatim at
    # the same PCs in segment 25.  This is stronger than an ABI inference:
    # the source module's own far calls select segment 08, never segment 25,
    # and all 43 real literal 08:* API targets observed anywhere in NP560.PRG
    # have same-PC entries inside this source window.  A raw-word scan also
    # sees AC05 BD08 at 2A:BCD2 as if BD08 were an opcode; pin and exclude that
    # branch destination word explicitly.
    expected_rom08_targets = (
        0x2EDC, 0x2F22, 0x31AC, 0x320E, 0x3238, 0x3262, 0x3292,
        0x3314, 0x3324, 0x334A, 0x33FA, 0x3462, 0x34C4, 0x3536,
        0x372A, 0x378A, 0x37BA, 0x37CE, 0x37F4, 0x3820, 0x385C,
        0x38A4, 0x38D0, 0x3906, 0x3930, 0x3994, 0x427E, 0x4360,
        0x4380, 0x43A6, 0x441A, 0x4470, 0x44F2, 0x450C, 0x45E0,
        0x45F6, 0x460E, 0x46EC, 0x4702, 0x475E, 0x479C, 0x47A0,
        0x4844,
    )
    program.expect(
        0x2ABCD0,
        (0x1621, 0xAC05, 0xBD08, 0x780B, 0x0006),
        "non-call BD08 word inside an AJMP operand",
    )
    program_words = program.words_at(program.base, len(program.data) // 2)
    rom08_targets = tuple(sorted({
        program_words[index + 1]
        for index, word in enumerate(program_words[:-1])
        if word == 0xBD08 and program_words[index + 1] != 0x780B
    }))
    rom08_call_count = sum(
        word == 0xBD08 and program_words[index + 1] != 0x780B
        for index, word in enumerate(program_words[:-1])
    )
    if rom08_targets != expected_rom08_targets or rom08_call_count != 316:
        raise EvidenceMismatch(
            "NP560.PRG: resident segment-08 call inventory changed: "
            f"{rom08_call_count} calls to {len(rom08_targets)} targets"
        )
    rom08_source_calls = sum(
        word == 0xBD25 and program_words[index + 1] in expected_rom08_targets
        for index, word in enumerate(program_words[:-1])
    )
    rom08_source_words = program.words_at(0x252EDC, 0x1CB2 // 2)
    rom08_internal_calls = sum(
        word == 0xBD08 for word in rom08_source_words[:-1]
    )
    rom08_internal_source_calls = sum(
        word == 0xBD25 for word in rom08_source_words[:-1]
    )
    if (rom08_source_calls != 0 or rom08_internal_calls != 27 or
            rom08_internal_source_calls != 0):
        raise EvidenceMismatch(
            "NP560.PRG: segment-25 resident-module relocation evidence "
            "does not match the pinned 08 linkage"
        )
    for address, words, label in (
        (0x252EDC,
         (0x1F10, 0x58F0, 0x6810, 0x0000, 0x4907,
          0x86F0, 0x4A65),
         "resident segment-08 module source entry"),
        (0x252EF6, (0xBD08, 0x3292),
         "source module call linked to segment 08"),
        (0x25427E, (0xFD38, 0xED40, 0xFD48, 0x3F00, 0xC620),
         "exact 08:427E same-PC source body"),
        (0x2543A6,
         (0x2E02, 0x58F0, 0x58F1, 0x58F2, 0x58F3, 0x58F4,
          0x58F5, 0x1F10, 0x1F11, 0x58FB),
         "exact 08:43A6 far-copy source entry"),
        (0x25440A,
         (0x384F, 0x383F, 0x382F, 0x381F, 0x380F,
          0x2F00, 0x3F00, 0xC620),
         "exact 08:43A6 far-copy source epilogue"),
        (0x254470, (0x2E00, 0x58F0, 0x58F1, 0x58F2,
                    0x1F00, 0x1F11),
         "exact 08:4470 one-argument source entry"),
        (0x254B78,
         (0x1F09, 0x6809, 0x0000, 0x1F10, 0x1F11,
          0xBD01, 0xAD48, 0x1F91, 0x1F90, 0x1F89, 0xC610),
         "resident segment-08 module final interrupt callback"),
        (0x254B8E, (0x1B2C, 0xC71C, 0x2899, 0xC31C),
         "data immediately following resident executable module"),
    ):
        program.expect(address, words, label)

    # All 18:6D56 users clean ten argument bytes.  The generic wrapper at
    # 4F:E458 forwards a length and two far pointers, while the three fixed
    # calls below first seed one zero word then copy from address N to N+2.
    # That overlapping forward-copy pattern establishes memcpy direction as
    # well as the five-word stack layout without requiring the absent ROM.
    program.expect(
        0x4FE46E,
        (0x780B, 0x000E, 0x58F0,
         0x780B, 0xFFFC, 0x781B, 0xFFFE, 0x58F1, 0x58F0,
         0x780B, 0x0006, 0x781B, 0x0008, 0x58F1, 0x58F0,
         0xBD18, 0x6D56, 0x50FA),
        "five-word far-memory-copy forwarding wrapper",
    )
    program.expect(
        0x4EC2EC,
        (0x68F0, 0x383E, 0x58F0,
         0x68F1, 0x3840, 0x68F0, 0x0050, 0x58F1, 0x58F0,
         0x68F1, 0x3842, 0x68F0, 0x0050, 0x58F1, 0x58F0,
         0xBD18, 0x6D56, 0x50FA),
        "forward-overlap zero expansion through 18:6D56",
    )
    resident_far_memcpy_calls = count_direct_calls_to_address(
        program, 0x186D56
    )
    if resident_far_memcpy_calls != 16:
        raise EvidenceMismatch(
            "NP560.PRG: expected 16 direct calls to resident far memcpy "
            f"18:6D56, found {resident_far_memcpy_calls}"
        )

    # 08:43A6 has the same five-word far-copy ABI.  Every direct call removes
    # ten argument bytes.  Its exact original guest body is now available at
    # 25:43A6 inside the relocation-proven segment-08 module above.
    program.expect(
        0x4E4BDE,
        (0x68F0, 0x3840, 0x58F0,
         0x780B, 0xFFFC, 0x781B, 0xFFFE, 0x58F1, 0x58F0,
         0x780B, 0xFFF8, 0x781B, 0xFFFA, 0x58F1, 0x58F0,
         0xBD08, 0x43A6, 0x50FA),
        "fixed 50:0000 to 50:3840 copy through 08:43A6",
    )
    program.expect(
        0x4EAB72,
        (0x68F3, 0x383E, 0x58F3,
         0x6810, 0x0000, 0x88F0, 0x04FC, 0x88F1, 0x04FE,
         0x58F1, 0x58F0, 0x5012, 0x5100, 0x58F1, 0x58F0,
         0xBD08, 0x43A6, 0x50FA),
        "forward-overlap seed expansion through 08:43A6",
    )
    resident_far_memcpy_08_calls = count_direct_calls_to_address(
        program, 0x0843A6
    )
    resident_far_memcpy_08_cleanups = count_word_pattern(
        program,
        program.base,
        program.base + len(program.data),
        (0xBD08, 0x43A6, 0x50FA),
    )
    if (resident_far_memcpy_08_calls != 9 or
            resident_far_memcpy_08_cleanups != resident_far_memcpy_08_calls):
        raise EvidenceMismatch(
            "NP560.PRG: expected nine five-word calls to resident far memcpy "
            f"08:43A6, found {resident_far_memcpy_08_calls} calls and "
            f"{resident_far_memcpy_08_cleanups} ten-byte cleanups"
        )

    # Four application paths call 31:A914 with no arguments.  The flat target
    # is the middle of 31:A870, whereas uncalled 4E:A914 is a complete LINK #1
    # initializer that reaches the LCD power and bus setup resident entries.
    program.expect(
        0x31A914,
        (0xA8F1, 0x555E, 0x6810, 0x00A4, 0x88F0, 0x5554),
        "flat incompatible 31:A914 mid-function bytes",
    )
    program.expect(
        0x4EA914,
        (0x2E01, 0x58F0, 0x58F1, 0x4814, 0x58F1,
         0xBD33, 0x305E),
        "same-PC complete LCD/application initializer entry",
    )
    program.expect(
        0x4EA9A8,
        (0xBD14, 0x65CE, 0xBD14, 0x6622,
         0x381F, 0x380F, 0x2F00, 0xC620),
        "same-PC LCD/application initializer epilogue",
    )
    application_lcd_init_destination_calls = count_direct_calls_to_address(
        program, 0x31A914
    )
    application_lcd_init_source_calls = count_direct_calls_to_address(
        program, 0x4EA914
    )
    if (application_lcd_init_destination_calls != 4 or
            application_lcd_init_source_calls):
        raise EvidenceMismatch(
            "NP560.PRG: expected four 31:A914 calls and no in-place "
            "4E:A914 source calls"
        )

    # The segment-14 LCD boundaries are not opaque after all. Complete
    # functions exist at the same PCs in segment 31 and have no literal
    # callers at their storage addresses. The power wrapper reaches the full
    # ST7529 command stream at 31:68B0; that stream calls the clear and delay
    # entries whose same-PC bodies are adjacent in the same source module.
    program.expect(
        0x316622,
        (0x1F10, 0x1F11, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
         0x1F39, 0x1F41, 0x1F49, 0x1F31, 0xBD14, 0x665A),
        "same-PC segment-14 LCD bus-init source",
    )
    program.expect(
        0x316642,
        (0x383F, 0x382F, 0x381F, 0x380F,
         0x1F91, 0x1F90, 0x3F00, 0xC620),
        "same-PC segment-14 LCD bus-init epilogue",
    )
    program.expect(
        0x31665A,
        (0x6810, 0x0000, 0x88F0, 0x4B44,
         0x6811, 0x0028, 0x68F2, 0xE652),
        "same-PC segment-14 LCD bus-write source",
    )
    program.expect(
        0x316680,
        (0x0B04, 0x69F4, 0x0081, 0x0B04, 0x0946,
         0x0B14, 0x4944, 0x0B14, 0x3F00, 0xC620),
        "same-PC segment-14 LCD bus-write epilogue",
    )
    program.expect(
        0x3165CE,
        (0x1F10, 0x1F11, 0x58F0, 0x58F1, 0x58F2,
         0xBD14, 0x68B0, 0x382F, 0x381F, 0x380F,
         0x1F91, 0x1F90, 0x3F00, 0xC620),
        "same-PC segment-14 LCD power wrapper",
    )
    program.expect(
        0x3168B0,
        (0xF439, 0xF441, 0xF842, 0xF84A, 0xE83A,
         0x3F00, 0xBD14, 0x6F30),
        "same-PC segment-14 ST7529 initialization source",
    )
    program.expect(
        0x316AC4,
        (0x3F00, 0xBD14, 0x6F30, 0xBD14, 0x6AD8,
         0x69F4, 0x00AF, 0x0B04, 0x3F00, 0xC620),
        "ST7529 initialization display-on epilogue",
    )
    program.expect(
        0x316AD8,
        (0x4940, 0x68F6, 0x009F, 0xAF06, 0x6AE8,
         0xBF00, 0x00FE, 0x0B14, 0x3F00, 0xC620),
        "same-PC segment-14 LCD clear source",
    )
    program.expect(
        0x316AEC,
        (0x2E02, 0x1F11, 0x1F10, 0x58F0, 0x58F1,
         0x58F2, 0x58F3, 0x58F4, 0x58F6, 0x58F7),
        "same-PC segment-14 LCD region source entry",
    )
    program.expect(
        0x316BBE,
        (0x387F, 0x386F, 0x384F, 0x383F, 0x382F, 0x381F,
         0x380F, 0x1F91, 0x1F90, 0x2F00, 0x3F00, 0xC620),
        "same-PC segment-14 LCD region source epilogue",
    )
    program.expect(
        0x316E10,
        (0x2E02, 0x1F11, 0x1F10, 0x58F0, 0x58F1,
         0x58F2, 0x58F3, 0x58F4, 0x3F10, 0x6811, 0x01E0),
        "same-PC segment-14 LCD bitmap source entry",
    )
    program.expect(
        0x316E56,
        (0x3F00, 0xBD14, 0x6F30),
        "LCD bitmap source first resident delay call",
    )
    program.expect(
        0x316F1C,
        (0x384F, 0x383F, 0x382F, 0x381F, 0x380F,
         0x1F91, 0x1F90, 0x2F00, 0x3F00, 0xC620),
        "same-PC segment-14 LCD bitmap source epilogue",
    )
    program.expect(
        0x316F30,
        (0xC700, 0x2E00, 0xBF00, 0x0014,
         0xC700, 0x2F00, 0x3F00, 0xC620),
        "same-PC segment-14 delay source",
    )
    resident_lcd_specs = (
        (0x146622, 0x316622, 8, 0x30),
        (0x14665A, 0x31665A, 1, 0x3A),
        (0x1465CE, 0x3165CE, 1, 0x1C),
        (0x1468B0, 0x3168B0, 1, 0x228),
        (0x146AD8, 0x316AD8, 1, 0x14),
        (0x146AEC, 0x316AEC, 2, 0xEA),
        (0x146E10, 0x316E10, 1, 0x120),
        (0x146F30, 0x316F30, 37, 0x10),
    )
    resident_lcd_entries = []
    for destination, source, expected_calls, size in resident_lcd_specs:
        destination_calls = count_direct_calls_to_address(program, destination)
        source_calls = count_direct_calls_to_address(program, source)
        if destination_calls != expected_calls or source_calls:
            raise EvidenceMismatch(
                f"NP560.PRG: expected {expected_calls} calls to "
                f"{format_address(destination)} and no calls to same-PC source "
                f"{format_address(source)}"
            )
        resident_lcd_entries.append({
            "destination": format_address(destination),
            "source": format_address(source),
            "bytes": size,
            "destination_address_direct_calls": destination_calls,
            "source_address_direct_calls": source_calls,
        })

    program.expect(
        0x2F90A8,
        (0x780B, 0xFFFA, 0x781B, 0xFFFC,
         0x58F1, 0x58F0, 0x68F0, 0x005D, 0x58F0,
         0x68F0, 0x00D8, 0x58F0, 0xBD2E, 0x5316, 0x50F8),
        "four-word call to second runtime overlay",
    )
    program.expect(
        0x2E5316,
        (0x4842, 0xBD32, 0xF786, 0x68F0, 0x0052),
        "second runtime call lands inside initializer data",
    )
    program.expect(
        0x4B5316,
        (0x2E03, 0x58F0, 0x58F1, 0x58F2, 0x58F3,
         0x780B, 0x0006, 0x6B1B, 0x0006),
        "same-PC complete four-argument overlay candidate",
    )
    program.expect(
        0x4B548A,
        (0xBD31, 0x4BAC, 0x383F, 0x382F, 0x381F,
         0x380F, 0x2F00, 0xC620),
        "four-argument overlay candidate epilogue",
    )
    segment_4b_direct_calls = count_direct_calls_to_segment(program, 0x4B)
    if segment_4b_direct_calls != 0:
        raise EvidenceMismatch(
            "NP560.PRG: expected segment 4B to have no literal SCALL sites, "
            f"found {segment_4b_direct_calls}"
        )

    # 20:026A configures additional windows but its first call does not match
    # the stack/register state required by the bytes currently visible at the
    # target.  These signatures make that conflict reviewable.
    program.expect(
        0x20026A,
        (0x2E00, 0x58F1, 0x68F0, 0x3F00),
        "second startup-looking entry",
    )
    for address, words, label in (
        (0x200278, (0xA8F0, 0x7174), "0x7174 setup"),
        (0x200284, (0xA8F0, 0x7184), "0x7184 setup"),
        (0x200288, (0x68F0, 0x2082), "0x7100 setup value"),
        (0x200296, (0x68F0, 0x5002), "0x7108 setup value"),
        (0x2002A4, (0x68F0, 0x6001), "0x710A setup value"),
        (0x2002B2, (0x68F0, 0xF002), "0x710C setup value"),
        (0x2002C0, (0xBD2C, 0x9A7C), "first deep call"),
        (0x2C9A6A, (0x780B, 0x0006, 0x781B, 0x0008,
                    0x70F1, 0x001C, 0x5100, 0x6A0B, 0xFFD4),
         "shared-tail predecessor that computes and stores R0"),
        (0x2C9A7C, (0x6A1B, 0xFFD6, 0x4C11, 0x5C01),
         "deep-call target begins with the paired R1 store"),
        (0x2C9AB2, (0x783B, 0xFFFA),
        "deep-call target reads an unallocated negative local"),
    ):
        program.expect(address, words, label)

    # The application also contains an exact compiler copy-helper template at
    # 4F:F786, while 270 descriptors call the same PC in segment 32.  The
    # current bytes at 32:F786 are unrelated mid-function code, proving a
    # loader-installed overlay is required before either initializer chain.
    program.expect(
        0x4FF786,
        (0x2E00, 0x4C11, 0x5C01, 0x4D11,
         0x4C31, 0x5C21, 0x4D31, 0x75F3, 0x8000,
         0x3F11, 0x8810, 0xF2E0, 0x8811, 0xF2E4,
         0x5241, 0xAF04, 0xF7BE, 0x2B13, 0x5011,
         0x7C71, 0x01F2, 0x7110, 0x0000, 0xFF71,
         0x5031, 0x7111, 0x0000, 0xEF73, 0x2F00, 0xC620),
        "60-byte compiler copy-helper template",
    )
    program.expect(
        0x32F786,
        (0xFFEE, 0x6A1B, 0xFFF0),
        "flat-image code currently visible at the overlay destination",
    )
    descriptors = find_program_copy_descriptors(program)
    descriptor_groups = group_contiguous_descriptors(descriptors)
    if [len(group) for group in descriptor_groups] != [9, 261]:
        raise EvidenceMismatch(
            "NP560.PRG: expected initializer groups of 9 and 261 copy "
            f"descriptors, found {[len(group) for group in descriptor_groups]}"
        )
    first_group, second_group = descriptor_groups
    if first_group[0]["address"] != 0x247FE4:
        raise EvidenceMismatch("NP560.PRG: first initializer does not start at 24:7FE4")
    if second_group[0]["address"] != 0x2E4560:
        raise EvidenceMismatch("NP560.PRG: second initializer does not start at 2E:4560")
    containing_2e5316 = [
        descriptor for descriptor in second_group
        if descriptor["address"] <= 0x2E5316 < descriptor["end"]
    ]
    if len(containing_2e5316) != 1 or not (
        containing_2e5316[0]["address"] == 0x2E5306
        and containing_2e5316[0]["end"] == 0x2E531C
    ):
        raise EvidenceMismatch(
            "NP560.PRG: expected 2E:5316 inside initializer descriptor "
            "2E:5306..2E:531C"
        )
    program.expect(first_group[-1]["end"], (0xAD03, 0x026A),
                   "first initializer resident continuation")
    program.expect(second_group[-1]["end"], (0xAD07, 0x7FE4),
                   "second initializer resident continuation")

    expected_first_descriptors = [
        (0x5322DE, 0x04FFFC, 0x04),
        (0x532364, 0x07A622, 0x01),
        (0x532376, 0x07A626, 0x02),
        (0x5323A2, 0x07A630, 0x02),
        (0x53237A, 0x07A62A, 0x02),
        (0x532378, 0x07A628, 0x02),
        (0x53228E, 0x04FFF8, 0x04),
        (0x532366, 0x07A624, 0x02),
        (0x5322DA, 0x0757C8, 0x04),
    ]
    actual_first_descriptors = [
        (item["destination"], item["source"], item["length"])
        for item in first_group
    ]
    if actual_first_descriptors != expected_first_descriptors:
        raise EvidenceMismatch(
            "NP560.PRG: first initializer descriptors changed: "
            f"{actual_first_descriptors!r}"
        )

    # The first chain's three resident source ranges have exact storage
    # copies at the same PCs in segment +0x1D, the relocation rule already
    # proven for resident code throughout this image.  All three are bounded:
    # 21:FFF8 is the segment tail after RETS, 24:57C8 lies between RETS and the
    # next LINK, and 24:A622 includes the two valid RETS leaves at A62C/A62E.
    for address, words, label in (
        (0x21FFF0, (0x381F, 0x380F, 0x2F00, 0xC620),
         "initializer source-04 preceding epilogue"),
        (0x21FFF8, (0x0000, 0x0000, 0x0000, 0x0280),
         "initializer source-04 linked storage"),
        (0x2457C0, (0x383F, 0x381F, 0x2F00, 0xC620,
                    0x0000, 0x0000, 0x2E02, 0x58F1),
         "initializer source-07 57C8 bounded storage"),
        (0x24A622, (0x0000, 0x0000, 0x0000, 0x0000,
                    0x0000, 0xC620, 0xC620, 0x0000),
         "initializer source-07 A622 linked storage"),
        (0x24A632, (0xFFFF, 0xFFFF),
         "initializer source-07 A622 trailing padding"),
    ):
        program.expect(address, words, label)
    first_factory_sources = [
        {
            "destination": "04:FFF8",
            "source": "21:FFF8",
            "bytes": 8,
            "storage_hex": program.data[
                0x21FFF8 - program.base:0x220000 - program.base
            ].hex(),
        },
        {
            "destination": "07:57C8",
            "source": "24:57C8",
            "bytes": 4,
            "storage_hex": program.data[
                0x2457C8 - program.base:0x2457CC - program.base
            ].hex(),
        },
        {
            "destination": "07:A622",
            "source": "24:A622",
            "bytes": 16,
            "storage_hex": program.data[
                0x24A622 - program.base:0x24A632 - program.base
            ].hex(),
        },
    ]

    # The separately shipped burner exposes the compiler's initialized-data
    # startup pattern: far source on the code bus -> far destination in RAM.
    burner.expect(0x506000, (0xAD51, 0xDC18), "burner entry jump")
    burner.expect(
        0x51DC18,
        (0xE600, 0xE700, 0x6804, 0x5003, 0xAD51, 0x7F3E),
        "burner compiler startup",
    )
    burner.expect(
        0x517F3E,
        (0x68F0, 0x0050, 0x68F1, 0x084A,
         0x68F2, 0x0051, 0x68F3, 0xDC68,
         0x4844, 0xBD51, 0xD714),
        "first initialized-data copy descriptor",
    )
    burner.expect(
        0x51D714,
        (0x2E00, 0x4C11, 0x5C01, 0x4D11,
         0x4C31, 0x5C21, 0x4D31, 0x75F3, 0x8000,
         0x3F11, 0x8810, 0xF2E0, 0x8811, 0xF2E4,
         0x5241, 0xAF04, 0xD74C, 0x2B13),
        "code-to-data copy helper",
    )
    copy_count = count_word_pattern(
        burner, 0x517F3E, 0x518110, (0xBD51, 0xD714)
    )
    if copy_count != 21:
        raise EvidenceMismatch(
            "BURN_NAND_FLASH_CODE.bin: expected 21 compiler startup copies, "
            f"found {copy_count}"
        )

    return {
        "images": {
            "program": {
                "size": len(program_bytes),
                "sha256": hashlib.sha256(program_bytes).hexdigest(),
                "word_order": "little-endian",
                "base": "20:0000",
            },
            "burner": {
                "size": len(burner_bytes),
                "sha256": hashlib.sha256(burner_bytes).hexdigest(),
                "word_order": "big-endian",
                "base": "50:6000",
            },
        },
        "proven": {
            "reset": {
                "resident_call": "03:0030",
                "continuation": "33:4F50",
                "flat_image_container": "33:4510 event-0x008E handler",
                "flat_image_is_reset_code": False,
                "required_registers": {
                    "SP": "set to 0x1000 at linked 33:603C",
                    "FP": "set to 0x1000 at linked 33:603C",
                },
                "linked_preambles": [
                    {
                        "destination": "33:4F50..33:4F64",
                        "source": "50:4F50..50:4F64",
                        "terminal_jump": "33:603C",
                    },
                    {
                        "destination": "33:603C..33:6048",
                        "source": "50:603C..50:6048",
                        "terminal_jump": "11:4560",
                    },
                ],
                "linked_transfer_counts": linked_transfer_counts,
                "linked_source_transfer_counts":
                    linked_source_transfer_counts,
            },
            "fixed_callback_20_0030": {
                "returns": True,
                "register_writes": {"0x7100": "0x2082", "0x7108": "0x5001"},
                "zeroed_half_open_ranges": [
                    "00:0100..00:0FA0",
                    "00:0FF0..00:5000",
                    "00:8000..00:9000",
                    "50:0000..54:0000",
                ],
            },
            "entry_20_026a": {
                "register_writes": {
                    "0x7174": "0x3F00",
                    "0x7184": "0x0000",
                    "0x7100": "0x2082",
                    "0x7108": "0x5002",
                    "0x710A": "0x6001",
                    "0x710C": "0xF002",
                },
                "first_call": "2C:9A7C",
                "application_call": "20:031C -> 2D:7DD2",
                "application_call_count": application_dispatch_calls,
                "resident_03_0080_reference_count":
                    resident_0080_references,
                "returns_immediately_after_application": True,
                "flat_image_conflict": (
                    "target starts after the paired R0 calculation/store and "
                    "later reads [R11-6], while 20:026A allocates no frame locals"
                ),
                "same_pc_overlay_candidate": {
                    "source": "49:9A7C..49:9C66",
                    "destination": "2C:9A7C..2C:9C66",
                    "bytes": 0x1EA,
                    "abi": "LINK #0, preserves R0/R1, RETS",
                    "direct_calls_to_source_segment": segment_49_direct_calls,
                    "nested_calls": ["33:6030", "08:427E"],
                },
            },
            "compiler_runtime": {
                "source_image": "BURN_NAND_FLASH_CODE.bin",
                "copy_helper": "51:D714",
                "startup_copy_count": copy_count,
                "first_copy": {
                    "destination": "50:084A",
                    "source": "51:DC68",
                    "bytes": 4,
                },
                "direction": "code/image source -> data RAM destination",
            },
            "program_overlay_initializers": {
                "copy_template": "4F:F786..4F:F7C2",
                "template_bytes": 0x3C,
                "overlay_call_target": "32:F786",
                "flat_target_matches_template": False,
                "descriptor_count": len(descriptors),
                "groups": [
                    {
                        "entry": "24:7FE4",
                        "count": len(first_group),
                        "continuation": "03:026A",
                        "first_copy": {
                            "destination": format_address(
                                first_group[0]["destination"]
                            ),
                            "source": format_address(first_group[0]["source"]),
                            "bytes": first_group[0]["length"],
                        },
                    },
                    {
                        "entry": "2E:4560",
                        "count": len(second_group),
                        "continuation": "07:7FE4",
                        "first_copy": {
                            "destination": format_address(
                                second_group[0]["destination"]
                            ),
                            "source": format_address(second_group[0]["source"]),
                            "bytes": second_group[0]["length"],
                        },
                    },
                ],
                "linked_execution_order": [
                    "11:4560 (source 2E:4560, 261 copies)",
                    "07:7FE4 (source 24:7FE4, 9 copies)",
                    "03:026A (source 20:026A, system main)",
                ],
                "first_factory_sources": first_factory_sources,
            },
            "resident_rom08_module": {
                "destination": "08:2EDC..08:4B8E",
                "source": "25:2EDC..25:4B8E",
                "bytes": 0x1CB2,
                "direct_call_count": rom08_call_count,
                "direct_target_count": len(rom08_targets),
                "target_pcs": [f"{pc:04X}" for pc in rom08_targets],
                "source_address_direct_calls": rom08_source_calls,
                "source_internal_calls_to_segment_08": rom08_internal_calls,
                "source_internal_calls_to_segment_25":
                    rom08_internal_source_calls,
                "exact_guest_words_recovered": True,
                "mask_rom_dump_present": False,
            },
            "resident_far_memcpy": {
                "address": "18:6D56",
                "direct_call_count": resident_far_memcpy_calls,
                "stack_words": 5,
                "abi": "forward far memcpy(destination, source, u16 bytes)",
                "fixed_zero_expansion": {
                    "destination": "50:3842",
                    "source": "50:3840",
                    "bytes": 0x383E,
                },
                "original_rom_bytes_present": False,
            },
            "resident_far_memcpy_08": {
                "address": "08:43A6",
                "direct_call_count": resident_far_memcpy_08_calls,
                "stack_words": 5,
                "abi": "forward far memcpy(destination, source, u16 bytes)",
                "fixed_copy": {
                    "destination": "50:3840",
                    "source": "50:0000",
                    "bytes": 0x3840,
                },
                "forward_overlap": {
                    "destination": "source + 2",
                    "bytes": 0x383E,
                },
                "source": "25:43A6..25:441A",
                "exact_guest_body_recovered": True,
                "mask_rom_dump_present": False,
            },
            "resident_dispatch_1a": {
                "address": "1A:423C",
                "source": "37:423C..37:4B9C",
                "bytes": 0x960,
                "direct_call_count": resident_dispatch_1a_calls,
                "stack_words": 5,
                "cleanup_count": resident_dispatch_1a_cleanups,
                "source_address_direct_calls":
                    resident_dispatch_1a_source_calls,
                "exact_guest_body_recovered": True,
                "mask_rom_dump_present": False,
            },
            "resident_application_event": {
                "address": "1F:B496",
                "source": "3C:B496..3C:BA66",
                "bytes": 0x5D0,
                "direct_call_count": resident_application_event_calls,
                "stack_words": 1,
                "cleanup_count": resident_application_event_cleanups,
                "source_address_direct_calls":
                    resident_application_event_source_calls,
                "exact_guest_body_recovered": True,
                "mask_rom_dump_present": False,
            },
            "resident_lcd_same_pc_sources": resident_lcd_entries,
            "runtime_overlay_candidates": [
                {
                    "call_site": "20:02C0",
                    "destination": "2C:9A7C..2C:9C66",
                    "source": "49:9A7C..49:9C66",
                    "bytes": 0x1EA,
                    "source_segment_direct_calls": segment_49_direct_calls,
                },
                {
                    "call_site": "2F:90C0",
                    "destination": "2E:5316..2E:549A",
                    "source": "4B:5316..4B:549A",
                    "bytes": 0x184,
                    "flat_target_container": "initializer descriptor 2E:5306..2E:531C",
                    "source_segment_direct_calls": segment_4b_direct_calls,
                },
                {
                    "call_site": "49:9AF2 after installation at 2C:9A7C",
                    "destination": "33:6030..33:603C",
                    "source": "50:6030..50:603C",
                    "bytes": 0x0C,
                    "source_address_direct_calls": system_init_source_calls,
                },
                {
                    "call_site": "50:6032 after installation at 33:6030",
                    "destination": "33:5906..33:5916",
                    "source": "50:5906..50:5916",
                    "bytes": 0x10,
                    "source_address_direct_calls": system_bits_source_calls,
                },
                {
                    "call_sites": ["2B:93BE", "3F:9AB8"],
                    "destination": "31:AF72..31:B014",
                    "source": "4E:AF72..4E:B014",
                    "bytes": 0xA2,
                    "source_address_direct_calls": controller_reset_source_calls,
                    "next_call": "08:427E",
                },
                {
                    "call_site": "20:02D2 and 129 other literal calls",
                    "destination": "31:B014..31:B0B6",
                    "source": "4E:B014..4E:B0B6",
                    "bytes": 0xA2,
                    "destination_address_direct_calls":
                        memory_mode_destination_calls,
                    "source_address_direct_calls": memory_mode_source_calls,
                },
                {
                    "call_sites": ["2B:93C6", "3F:9AC0"],
                    "destination": "33:38D6..33:38F8",
                    "source": "50:38D6..50:38F8",
                    "bytes": 0x22,
                    "source_address_direct_calls": global_reset_source_calls,
                    "previous_call": "08:427E",
                },
                {
                    "call_site": "20:02DC and six other literal calls",
                    "destination": "33:305E..33:3082",
                    "source": "50:305E..50:3082",
                    "bytes": 0x24,
                    "destination_address_direct_calls":
                        mode_init_destination_calls,
                    "source_address_direct_calls": mode_init_source_calls,
                },
                {
                    "call_site": "50:3078 after installation at 33:305E",
                    "destination": "33:180A..33:1838",
                    "source": "50:180A..50:1838",
                    "bytes": 0x2E,
                    "destination_address_direct_calls":
                        mode_mask_destination_calls,
                    "source_address_direct_calls": mode_mask_source_calls,
                },
                {
                    "call_site": "20:02E2 and three other literal calls",
                    "destination": "32:4218..32:4290",
                    "source": "4F:4218..4F:4290",
                    "bytes": 0x78,
                    "destination_address_direct_calls":
                        startup_table_destination_calls,
                    "source_address_direct_calls": startup_table_source_calls,
                },
                {
                    "call_site": "20:02E6 and 87 other literal calls",
                    "destination": "32:CC9C..32:CCE8",
                    "source": "4F:CC9C..4F:CCE8",
                    "bytes": 0x4C,
                    "destination_address_direct_calls":
                        startup_pointer_destination_calls,
                    "source_address_direct_calls": startup_pointer_source_calls,
                    "nested_call": "18:6D56",
                },
                {
                    "call_site": "20:02EA and two other literal calls",
                    "destination": "32:8EBE..32:8F20",
                    "source": "4F:8EBE..4F:8F20",
                    "bytes": 0x62,
                    "destination_address_direct_calls":
                        startup_array_destination_calls,
                    "source_address_direct_calls": startup_array_source_calls,
                },
                {
                    "call_site": "20:02EE and 127 other literal calls",
                    "destination": "31:4BAC..31:4C68",
                    "source": "4E:4BAC..4E:4C68",
                    "bytes": 0xBC,
                    "destination_address_direct_calls":
                        startup_runtime_destination_calls,
                    "source_address_direct_calls": startup_runtime_source_calls,
                },
                {
                    "call_site": "3F:4554, 3F:4644, 3F:9764, 3F:9BAC",
                    "destination": "31:A914..31:A9B8",
                    "source": "4E:A914..4E:A9B8",
                    "bytes": 0xA4,
                    "destination_address_direct_calls":
                        application_lcd_init_destination_calls,
                    "source_address_direct_calls":
                        application_lcd_init_source_calls,
                    "nested_calls": ["14:65CE", "14:6622"],
                },
                {
                    "call_site": "25:3302 after relocation to 08:3292",
                    "destination": "24:9BD4..24:9BE8",
                    "source": "41:9BD4..41:9BE8",
                    "bytes": 0x14,
                    "destination_address_direct_calls":
                        peripheral_init_destination_calls,
                    "source_address_direct_calls":
                        peripheral_init_source_calls,
                },
                {
                    "call_site": "33:4F76 and 16 other literal calls",
                    "destination": "30:9E30..30:9F20",
                    "source": "4D:9E30..4D:9F20",
                    "bytes": 0xF0,
                    "abi": "two stack words at FP+6 and FP+8",
                    "destination_address_direct_calls":
                        activation_context_destination_calls,
                    "source_address_direct_calls":
                        activation_context_source_calls,
                },
                {
                    "call_site": "2C:9DD2 and 305 other literal calls",
                    "destination": "32:D530..32:D578",
                    "source": "4F:D530..4F:D578",
                    "bytes": 0x48,
                    "stack_words": 3,
                    "destination_address_direct_calls":
                        pointer_service_destination_calls,
                    "cleanup_count": pointer_service_cleanups,
                    "source_address_direct_calls":
                        pointer_service_source_calls,
                    "nested_calls": ["33:5FD0", "33:4492", "31:F282"],
                },
                {
                    "call_site": "4F:D536 after installation at 32:D530",
                    "destination": "33:5FD0..33:5FDC",
                    "source": "50:5FD0..50:5FDC",
                    "bytes": 0x0C,
                    "destination_address_direct_calls":
                        pointer_dependency_counts[0][0],
                    "source_address_direct_calls":
                        pointer_dependency_counts[0][1],
                    "nested_call": "33:5C18",
                },
                {
                    "call_site": "50:5FD2 after installation at 33:5FD0",
                    "destination": "33:5C18..33:5C26",
                    "source": "50:5C18..50:5C26",
                    "bytes": 0x0E,
                    "destination_address_direct_calls":
                        pointer_dependency_counts[1][0],
                    "source_address_direct_calls":
                        pointer_dependency_counts[1][1],
                },
                {
                    "call_sites": ["4F:D544", "4F:D56A"],
                    "destination": "33:4492..33:44AE",
                    "source": "50:4492..50:44AE",
                    "bytes": 0x1C,
                    "stack_words": 1,
                    "destination_address_direct_calls":
                        pointer_dependency_counts[2][0],
                    "cleanup_count": pointer_dependency_counts[2][2],
                    "source_address_direct_calls":
                        pointer_dependency_counts[2][1],
                    "nested_call": "2F:5B98",
                },
                {
                    "call_site": "4F:D55C after installation at 32:D530",
                    "destination": "31:F282..31:F312",
                    "source": "4E:F282..4E:F312",
                    "bytes": 0x90,
                    "stack_words": 3,
                    "destination_address_direct_calls":
                        pointer_dependency_counts[3][0],
                    "cleanup_count": pointer_dependency_counts[3][2],
                    "source_address_direct_calls":
                        pointer_dependency_counts[3][1],
                    "nested_calls": [
                        "21:FD80", "33:463E", "32:4C34", "29:3DD2",
                        "32:C476",
                    ],
                },
                {
                    "call_site": "4D:9F0E after installation at 30:9E30",
                    "destination": "27:507C..27:53CC",
                    "source": "44:507C..44:53CC",
                    "bytes": 0x350,
                    "stack_words": 4,
                    "destination_address_direct_calls":
                        activation_dispatch_destination_calls,
                    "cleanup_count": activation_dispatch_cleanups,
                    "source_address_direct_calls":
                        activation_dispatch_source_calls,
                },
                {
                    "call_site": "33:4F82 and 193 other literal calls",
                    "destination": "31:C0E8..31:C186",
                    "source": "4E:C0E8..4E:C186",
                    "bytes": 0x9E,
                    "stack_words": 1,
                    "destination_address_direct_calls":
                        application_property_destination_calls,
                    "cleanup_count": application_property_cleanups,
                    "source_address_direct_calls":
                        application_property_source_calls,
                    "nested_call": "31:4D24",
                },
                {
                    "call_sites": "six paths in 4E:C0E8 and 439 others",
                    "destination": "31:4D24..31:4DE0",
                    "source": "4E:4D24..4E:4DE0",
                    "bytes": 0xBC,
                    "stack_words": 1,
                    "destination_address_direct_calls":
                        property_setter_destination_calls,
                    "cleanup_count": property_setter_cleanups,
                    "source_address_direct_calls":
                        property_setter_source_calls,
                },
                {
                    "call_site": "4E:A940 after installation at 31:A914",
                    "destination": "25:206E..25:2478",
                    "source": "42:206E..42:2478",
                    "bytes": 0x40A,
                    "stack_words": 5,
                    "destination_address_direct_calls":
                        lcd_resource_destination_calls,
                    "cleanup_count": lcd_resource_cleanups,
                    "source_address_direct_calls": lcd_resource_source_calls,
                    "nested_call": "28:12A8",
                },
                {
                    "call_site": "4E:4BB2 after installation at 31:4BAC",
                    "destination": "33:5CB2..33:5CC0",
                    "source": "50:5CB2..50:5CC0",
                    "bytes": 0x0E,
                    "destination_address_direct_calls": nested_startup_counts[0][0],
                    "source_address_direct_calls": nested_startup_counts[0][1],
                },
                {
                    "call_site": "4E:4C58 after installation at 31:4BAC",
                    "destination": "33:3C86..33:3CA6",
                    "source": "50:3C86..50:3CA6",
                    "bytes": 0x20,
                    "destination_address_direct_calls": nested_startup_counts[1][0],
                    "source_address_direct_calls": nested_startup_counts[1][1],
                    "nested_call": "14:6E10",
                },
                {
                    "call_site": "4E:4C5C after installation at 31:4BAC",
                    "destination": "33:2FF2..33:3016",
                    "source": "50:2FF2..50:3016",
                    "bytes": 0x24,
                    "destination_address_direct_calls": nested_startup_counts[2][0],
                    "source_address_direct_calls": nested_startup_counts[2][1],
                    "nested_call": "14:6AEC",
                },
                {
                    "call_site": "3B:FC56 and 35 other literal calls",
                    "destination": "33:5B70..33:5B7E",
                    "source": "50:5B70..50:5B7E",
                    "bytes": 0x0E,
                    "destination_address_direct_calls":
                        application_state_byte_destination_calls,
                    "source_address_direct_calls":
                        application_state_byte_source_calls,
                },
            ],
        },
        "model_inferences": [
            (
                "03:0030 remains an unknown resident reset service, but the "
                "following 33:4F50 target no longer needs a fabricated event-"
                "handler frame: exact linked 50:4F50 and 50:603C preambles "
                "reset the memory-segment registers, SP, and FP before entering "
                "the compiler initializer."
            ),
            (
                "The update image cannot supply the factory post-application "
                "manager: its sole literal 2D:7DD2 call is at 20:031C inside "
                "startup and is immediately followed by the 20:0320 epilogue; "
                "the whole PRG contains no literal 03:0080 call or jump."
            ),
            (
                "Program/NOR bytes and writable external data RAM must be "
                "distinct mappings: 20:0030 clears data 50:0000..53:FFFF "
                "while the application has code in those logical segments."
            ),
            (
                "Before 20:026A can run, resident code must establish a code "
                "window/overlay selection or equivalent mapping that makes its "
                "2C:9A7C call ABI-consistent."
            ),
            (
                "The high-confidence source for that overlay is the complete "
                "same-PC function at 49:9A7C..49:9C65: it has the required "
                "no-argument ABI, configures the adjacent memory-controller "
                "register families, and segment 49 is never called in place."
            ),
            (
                "The same rule identifies a second runtime overlay: 2F:90C0 "
                "passes four stack words to 2E:5316, which lies inside a data "
                "initializer descriptor, while uncalled 4B:5316..4B:5499 is "
                "a complete same-PC four-argument function."
            ),
            (
                "The nested 33:6030 call is another two-level overlay: its "
                "complete no-argument wrapper is at 50:6030 and that wrapper's "
                "33:5906 dependency has a complete same-PC body at 50:5906. "
                "Because flat 33:5906 is also live fall-through code, the "
                "short helper must be relocated and its known callers patched "
                "instead of being installed there permanently."
            ),
            (
                "The application-event path independently requires the exact "
                "50:5B70 state-byte reader at logical 33:5B70; the flat target "
                "is a frame-relative shared tail and all 36 literal callers "
                "select the overlay destination."
            ),
            (
                "The same-PC rule also resolves the calls surrounding "
                "08:427E: 31:AF72 is installed from the complete controller "
                "sequence at 4E:AF72, and 33:38D6 from the complete global "
                "reset at 50:38D6. The exact 08:427E body is FD38 ED40 FD48 "
                "3F00 C620 in the relocation-proven segment-25 source module."
            ),
            (
                "The immediately adjacent 31:B014 target is also an overlay: "
                "130 literal calls land on a flat branch fragment, while the "
                "complete same-PC one-argument function at 4E:B014 has no "
                "in-place callers."
            ),
            (
                "The 20:02DC startup call likewise requires 33:305E to be "
                "installed from the complete one-argument same-PC function "
                "stored at 50:305E."
            ),
            (
                "That mode initializer has one nested overlay dependency: "
                "33:180A is installed from the complete no-argument body at "
                "50:180A."
            ),
            (
                "The 20:02E2 startup call requires 32:4218 to be installed "
                "from the complete no-argument function at 4F:4218; the "
                "flat destination is an incompatible shared tail."
            ),
            (
                "The next startup call similarly requires 32:CC9C to be "
                "installed from complete no-argument 4F:CC9C. Its nested "
                "18:6D56 dependency has a five-word forward far-memcpy ABI."
            ),
            (
                "A clean-room 18:6D56 implementation can reproduce the "
                "proven copy behavior, but it does not recover or claim the "
                "original mask-ROM instruction bytes."
            ),
            (
                "The following 32:8EBE startup call must use the complete "
                "no-argument table-clear body stored at 4F:8EBE; executing "
                "the flat shared tail creates a false 03:4010 dependency."
            ),
            (
                "The 20:02EE call and its three nested 33:* entries form "
                "another same-PC overlay group sourced at 4E:4BAC, 50:5CB2, "
                "50:3C86, and 50:2FF2. Its mode-1 path calls 08:43A6, whose "
                "exact original guest body is stored at 25:43A6."
            ),
            (
                "The segment-14 LCD driver is recoverable without guessed ROM "
                "behavior: complete same-PC bus-init, bus-write, power, "
                "controller-init, clear, region, bitmap, and delay bodies are "
                "stored in segment 31. None of those source addresses has a "
                "literal caller."
            ),
            (
                "The no-argument LCD/application initializer called at "
                "31:A914 must be installed from complete 4E:A914; the flat "
                "target is mid-function and the source calls recovered "
                "14:65CE and 14:6622 entries before returning normally."
            ),
            (
                "The exact 08:3292 body exposes another overlay dependency: "
                "its no-argument 24:9BD4 call must use the complete 20-byte "
                "peripheral/SFR initializer stored at 41:9BD4, not the flat "
                "parameterized shared tail."
            ),
            (
                "The application initialization chain reaches 30:9E30 with "
                "two stack words. Its flat bytes begin at a POP-based shared "
                "epilogue, while uncalled same-PC 4D:9E30 is the complete "
                "240-byte LINK #4 function with matching FP+6/FP+8 reads."
            ),
            (
                "The pointer-service calls at 32:D530 likewise require the "
                "complete 72-byte LINK #1 body stored at 4F:D530. All 306 "
                "literal calls use its three-word cleanup; the flat target "
                "can branch into an unrelated common epilogue."
            ),
            (
                "Its direct 33:5FD0, 33:5C18, 33:4492 and 31:F282 "
                "dependencies have complete uncalled same-PC bodies in "
                "segments 50/4E. Their no-argument, one-word and three-word "
                "ABIs match all observed cleanup sequences."
            ),
            (
                "The activation-context tail calls 27:507C with four words. "
                "All 165 callers use the same cleanup, while complete "
                "uncalled 44:507C supplies the 0x350-byte LINK #0x0A body; "
                "the flat destination starts mid-function."
            ),
            (
                "The next application step calls one-word 31:C0E8, whose "
                "complete 4E:C0E8 wrapper invokes one-word 31:4D24. Both "
                "uncalled same-PC bodies and all 194/445 cleanup sequences "
                "agree; both flat targets are shared bodies."
            ),
            (
                "The LCD/application initializer's five-word 25:206E call "
                "cannot execute the resource data at its flat address. All "
                "100 callers match the complete uncalled 0x40A-byte LINK #6 "
                "same-PC function stored at 42:206E."
            ),
            (
                "That function next calls resident 1A:423C. All 29 callers "
                "use a five-word cleanup, and the update image stores the "
                "complete uncalled 0x960-byte same-PC guest implementation "
                "at 37:423C, including its balanced RETS epilogue."
            ),
            (
                "Resident application-event dispatcher 1F:B496 is likewise "
                "recoverable exactly from the complete uncalled 0x5D0-byte "
                "same-PC body at 3C:B496. All nine callers use its one-word "
                "cleanup; the recovered event-0x84 path performs a native "
                "application screen transition."
            ),
            (
                "Segment 25 contains a complete 0x1CB2-byte module linked for "
                "resident segment 08: its internal far calls select 08, none "
                "select 25, and all 43 real 08:* API targets have same-PC "
                "source entries. This recovers exact guest code rather than "
                "an ABI-only implementation."
            ),
            (
                "Resident startup must install the 60-byte copy template from "
                "4F:F786 at executable RAM address 32:F786 before running the "
                "24:7FE4 or 2E:4560 initializer chains."
            ),
            (
                "The exact factory ROM bytes and the low-bit meaning of 0x7100 "
                "remain unknown; the patent identifies EMBLK in bits 15..8 and "
                "WS in bits 1..0 of the three external-memory boundary registers."
            ),
        ],
    }


def render_markdown(contract: dict[str, Any]) -> str:
    proven = contract["proven"]
    reset = proven["reset"]
    callback = proven["fixed_callback_20_0030"]
    entry = proven["entry_20_026a"]
    runtime = proven["compiler_runtime"]
    initializers = proven["program_overlay_initializers"]
    runtime_overlays = proven["runtime_overlay_candidates"]
    lines = [
        "# NP560+ V3.80 resident boot contract",
        "",
        "This report contains instruction-signature-verified facts from the "
        "shipped images. It does not claim to recover the vendor's factory ROM bytes.",
        "",
        "## Proven from NP560.PRG",
        "",
        f"- Reset calls `{reset['resident_call']}` and then jumps directly to "
        f"`{reset['continuation']}`.",
        f"- Flat PRG places `{reset['continuation']}` inside the "
        f"`{reset['flat_image_container']}`, but those are not the reset-time "
        "code-bus bytes: the exact same-PC linked source resolves the conflict.",
        "- The continuation has exact +0x1D linked source bodies: "
        "`50:4F50 -> 33:4F50` selects the memory segments and jumps to "
        "`33:603C`; `50:603C -> 33:603C` sets `SP=FP=0x1000` and jumps "
        "to `11:4560`. No literal transfer targets any of the four source "
        "storage addresses.",
        "- `20:0030` is a self-contained callback that returns normally. It writes "
        "`0x7100=0x2082`, `0x7108=0x5001`, then clears these half-open data ranges: "
        + ", ".join(f"`{value}`" for value in callback["zeroed_half_open_ranges"]) + ".",
        f"- `20:026A` writes the additional memory-window values and calls "
        f"`{entry['first_call']}`. In the flat PRG mapping, {entry['flat_image_conflict']}.",
        f"- Its only application call is `{entry['application_call']}`; the "
        "next instructions are the startup epilogue. Across the complete PRG "
        f"there are {entry['application_call_count']} literal `2D:7DD2` calls "
        f"and {entry['resident_03_0080_reference_count']} literal call/jump "
        "references to `03:0080`.",
        f"- The sole same-PC ABI-compatible function is stored at "
        f"`{entry['same_pc_overlay_candidate']['source']}` "
        f"({entry['same_pc_overlay_candidate']['bytes']} bytes). It preserves "
        "`R0/R1`, configures the neighboring memory-control register families, "
        "and its source segment has no literal `SCALL` users.",
        "",
        "## Proven from the NAND burner",
        "",
        f"- Compiler startup makes {runtime['startup_copy_count']} calls to "
        f"`{runtime['copy_helper']}` to copy initialized data from the code image into data RAM.",
        f"- The first descriptor copies {runtime['first_copy']['bytes']} bytes from "
        f"`{runtime['first_copy']['source']}` to `{runtime['first_copy']['destination']}`.",
        "",
        "## Proven overlay initializer chains in NP560.PRG",
        "",
        f"- A {initializers['template_bytes']}-byte copy-helper template is stored at "
        f"`{initializers['copy_template']}`, but all "
        f"{initializers['descriptor_count']} descriptors call "
        f"`{initializers['overlay_call_target']}`.",
        "- The flat bytes at the call target are unrelated mid-function code, so "
        "the target must be installed as an overlay before use.",
        f"- PRG storage contains a {initializers['groups'][0]['count']}-copy "
        f"chain at `{initializers['groups'][0]['entry']}` ending at "
        f"`{initializers['groups'][0]['continuation']}`, and a "
        f"{initializers['groups'][1]['count']}-copy chain at "
        f"`{initializers['groups'][1]['entry']}` ending at "
        f"`{initializers['groups'][1]['continuation']}`.",
        "- Their linked execution order is **261 copies -> 9 copies -> "
        "system main**: " + " -> ".join(
            f"`{item}`" for item in initializers["linked_execution_order"]
        ) + ".",
        "- The first chain's three internal-ROM source ranges are recovered "
        "from their exact +0x1D linked PRG storage copies: "
        + ", ".join(
            f"`{item['destination']} <- {item['source']}` "
            f"({item['bytes']} bytes, `{item['storage_hex']}`)"
            for item in initializers["first_factory_sources"]
        ) + ".",
        f"- A later four-word call at `{runtime_overlays[1]['call_site']}` lands "
        f"inside `{runtime_overlays[1]['flat_target_container']}`. The complete "
        f"same-PC function is stored at `{runtime_overlays[1]['source']}` and "
        "its source segment likewise has no literal `SCALL` users.",
        "",
        "## Consequences for the emulator",
        "",
    ]
    lines.extend(f"- {item}" for item in contract["model_inferences"])
    lines.extend([
        "",
        "Run `python disassembly/analyse_np560_boot_contract.py` to re-check the "
        "signatures against the local V3.80 images.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program", type=Path, default=DEFAULT_PROGRAM)
    parser.add_argument("--burner", type=Path, default=DEFAULT_BURNER)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    contract = analyse_contract(args.program.read_bytes(), args.burner.read_bytes())
    if args.format == "json":
        print(json.dumps(contract, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(contract), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
