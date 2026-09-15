#!/usr/bin/env python3
"""Build a narrow SoC-ROM variant for the NP560 PRG-at-03 experiment.

The normal reconstructed image installs hundreds of application overlays at
resident entry 01:0200 because NP560.PRG was historically mapped at 20:0000.
When the unchanged PRG is instead mapped at its apparent link address
03:0000, those copies are already present.  The legacy loader occupies 13,453
words at 01:0200..01:6B19 and therefore also collides with real resident calls
at 01:4674 and 01:46CC.  Most of that loader is obsolete in this layout, but
its late storage-registry calls still have observable side effects after BSS
clear.  This tool replaces the copy-heavy body with a small guest-DMCU
bootstrap and relocates only its required capacity helper into free mask-ROM
space.  Strict ROM execution can consequently stop at the next genuinely
absent 00..02 service with its original call context intact.

The same rule applies to the obsolete source-repair installer at 01:B000:
its inline data occupied real resident entries 01:B6DE/B7AA/B816/B84E.
Retire its exact, source-checked body instead of executing it as a codec.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from scripts import build_np560_reconstructed_rom as reconstructed
    from scripts.inject_np560_minimal_pim import MINIMAL_PIM
except ImportError:  # Direct ``python scripts/build_...py`` invocation.
    import build_np560_reconstructed_rom as reconstructed
    from inject_np560_minimal_pim import MINIMAL_PIM


ROM01_POST_CLOCK_ADDRESS = 0x010200
LEGACY_ROM01_LOADER_WORDS = 13_453
EXPECTED_PREFIX = bytes.fromhex("06bd401d")
RETS = bytes.fromhex("20c6")
SKELETON_HOLE = bytes.fromhex("000f")
PROVISIONAL_AUDIO_RETURNS = {
    # These are missing services, not recovered DSP implementations. Labels
    # state the original caller's observable contract only; storage and
    # processing side effects remain unknown (doc/np560_resident_table_modes.md).
    0x014674: "unknown service receiving a far pointer and ten-word count",
    0x0146CC: "unknown no-argument service selected for modes 1..13",
    0x0146D0: "unknown no-argument service selected for default mode",
}
VMA03_CAPACITY_INSTALLER_ADDRESS = 0x025100
VMA03_CAPACITY_WRAPPER_ADDRESS = 0x025600
VMA03_FILE_CALLBACK_INSTALLER_ADDRESS = 0x025700
VMA03_FILE_CALLBACK_CHILD_ADDRESS = 0x025800
VMA03_FILE_CALLBACK_WRAPPER_ADDRESS = 0x025840
VMA03_NAND_PREPARE_READ_ADDRESS = 0x026000
VMA03_NAND_PACK_SPARE_ADDRESS = 0x026100
VMA03_NAND_UNPACK_SPARE_ADDRESS = 0x026200
VMA03_NAND_UNPACK_FULL_ADDRESS = 0x026400
VMA03_PIM_PROVISION_FILTER_ADDRESS = 0x027000
VMA03_PIM_PROVISION_WRITER_ADDRESS = 0x027200
VMA03_PIM_PATH_LOOKUP_VENEER_ADDRESS = 0x027400
VMA03_PIM_PROVISION_WRAPPER_ADDRESS = 0x027600
VMA03_PIM_PROVISION_TRIGGER_ADDRESS = 0x319E44
VMA03_PIM_PROVISION_TRIGGER_SOURCE = 0x4E9E44
VMA03_PIM_PROVISION_ORIGINAL_TARGET = 0x1E6444
VMA03_PIM_PATH_LOOKUP_CALL_ADDRESS = 0x2DD9E2
VMA03_PIM_PATH_LOOKUP_CALL_SOURCE = 0x4AD9E2
VMA03_PIM_PATH_LOOKUP_ORIGINAL_TARGET = 0x2076CA
VMA03_STORAGE_REGISTRY_ADDRESS = 0x255858
VMA03_PIM_PATH = r"0:\我的邮件\nminbox.pim"
VMA03_PIM_PATH_FP_OFFSET = -0x20


def words_to_bytes(words: list[int]) -> bytes:
    return b"".join(word.to_bytes(2, "little") for word in words)


def vma03_capacity_installer_words() -> list[int]:
    """Install the capacity closure without reading shifted PRG at runtime."""
    source_call = reconstructed.program_source_words(
        reconstructed.STORAGE_UNIT_OPEN_CAPACITY_CALL_SOURCE, 4
    )
    expected_call = [
        0xBD00
        | (reconstructed.STORAGE_UNIT_OPEN_CAPACITY_LINKED_DESTINATION >> 16),
        reconstructed.STORAGE_UNIT_OPEN_CAPACITY_LINKED_DESTINATION & 0xFFFF,
    ]
    if source_call != expected_call:
        raise ValueError(
            "storage unit-open call signature changed: "
            f"{source_call!r} != {expected_call!r}"
        )
    return [
        *reconstructed.write_program_words(
            reconstructed.STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_DESTINATION,
            reconstructed.program_source_words(
                reconstructed.STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_SOURCE,
                reconstructed.STORAGE_RECORD_CAPACITY_CHILD_OVERLAY_SIZE,
            ),
        ),
        *reconstructed.write_program_words(
            reconstructed.STORAGE_RECORD_CAPACITY_SERVICE_OVERLAY_DESTINATION,
            reconstructed.storage_record_capacity_service_words(),
        ),
        *reconstructed.write_program_words(
            reconstructed.STORAGE_RECORD_CAPACITY_WRAPPER_OVERLAY_DESTINATION,
            reconstructed.storage_record_capacity_wrapper_words(),
        ),
        *reconstructed.write_program_words(
            reconstructed.STORAGE_UNIT_OPEN_CAPACITY_CALL,
            [
                0xBD00 | (VMA03_CAPACITY_WRAPPER_ADDRESS >> 16),
                VMA03_CAPACITY_WRAPPER_ADDRESS & 0xFFFF,
            ],
        ),
        reconstructed.RETS,
    ]


def vma03_bootstrap_words(*, provision_minimal_pim: bool = False) -> list[int]:
    """Run the post-BSS storage side effects still required by VMA03.

    ``provision_minimal_pim`` is an explicit one-shot checkpoint-generation
    mode.  It installs a small guest-DMCU call filter at the common startup
    result-list allocator.  Category 0E arms the filter; the following
    category-08 call runs the provisioner at the same point where the normal
    firmware can already traverse the parent directory.  The provisioner
    uses the shipped resident open/write/close APIs; normal VMA03 ROMs leave
    this disabled and never manufacture user data.
    """
    words = [
        0xBD00 | (VMA03_STORAGE_REGISTRY_ADDRESS >> 16),
        VMA03_STORAGE_REGISTRY_ADDRESS & 0xFFFF,
    ]
    if provision_minimal_pim:
        source_call = reconstructed.program_source_words(
            VMA03_PIM_PROVISION_TRIGGER_SOURCE, 4
        )
        expected_call = [
            0xBD00 | (VMA03_PIM_PROVISION_ORIGINAL_TARGET >> 16),
            VMA03_PIM_PROVISION_ORIGINAL_TARGET & 0xFFFF,
        ]
        if source_call != expected_call:
            raise ValueError(
                "late PIM provision trigger signature changed: "
                f"{source_call!r} != {expected_call!r}"
            )
        words.extend(reconstructed.write_program_words(
            VMA03_PIM_PROVISION_TRIGGER_ADDRESS,
            [
                0xBD00 | (VMA03_PIM_PROVISION_FILTER_ADDRESS >> 16),
                VMA03_PIM_PROVISION_FILTER_ADDRESS & 0xFFFF,
            ],
        ))
    words.append(reconstructed.RETS)
    return words


def _guest_immediate_words(data: bytes) -> tuple[int, ...]:
    if len(data) & 1:
        raise ValueError("guest immediate data must contain complete words")
    return tuple(
        int.from_bytes(data[offset:offset + 2], "big")
        for offset in range(0, len(data), 2)
    )


def vma03_pim_provision_writer_words() -> list[int]:
    """Write the recovered 0x4A-byte empty PIM through resident FILE I/O."""
    if len(MINIMAL_PIM) != 0x4A:
        raise ValueError("minimal PIM fixture length changed")
    words = [0x2E25]  # LINK #0x25: one 0x4A-byte near-SRAM buffer
    for index, value in enumerate(_guest_immediate_words(MINIMAL_PIM)):
        words.extend((
            0x68F0, value,
            0x6A0B, (-len(MINIMAL_PIM) + index * 2) & 0xFFFF,
        ))
    words.extend((
        0x68F1, len(MINIMAL_PIM), 0x4800,  # 32-bit byte length
        0x58F1, 0x58F0,
        0x081B, 0x70F1, (-len(MINIMAL_PIM)) & 0xFFFF,
        0x4800, 0x58F1, 0x58F0,           # near source pointer
        0x780B, 0x0006, 0x781B, 0x0008,
        0x58F1, 0x58F0,                   # caller's FILE pointer
        0xBD17, 0xE3EE, 0x50FC,           # resident fwrite; pop 12 bytes
        0x2F00, reconstructed.RETS,
    ))
    return words


def _store_file_object_mode_words(value: int) -> list[int]:
    """Store one byte at ``FILE+0x15`` using the compiler's far-byte ABI."""
    if not 0 <= value <= 0xFF:
        raise ValueError("FILE mode must fit in one byte")
    return [
        0x780B, 0x0006, 0x781B, 0x0008,  # far FILE argument
        0x70F1, 0x0015, 0x5100,          # FILE + 0x15
        0x4830 | value,                   # R3 low byte supplies RB7
        0x3F11, 0x59F7, 0x52F1,          # stage one byte on near stack
        0x4C11, 0x5C01, 0x4D11,          # split far address into DS:R1
        0x58F0, 0x1F90, 0x3F01,
        0x50F1, 0x3B1F,                  # MOVB [R1], staged byte
    ]


def _call_file_lookup_words() -> list[int]:
    """Forward the veneer's two far arguments to resident 20:76CA."""
    return [
        0x780B, 0x000A, 0x781B, 0x000C,  # component string
        0x58F1, 0x58F0,
        0x780B, 0x0006, 0x781B, 0x0008,  # FILE object
        0x58F1, 0x58F0,
        0xBD00 | (VMA03_PIM_PATH_LOOKUP_ORIGINAL_TARGET >> 16),
        VMA03_PIM_PATH_LOOKUP_ORIGINAL_TARGET & 0xFFFF,
        0x50F8,
    ]


def vma03_pim_path_lookup_veneer_words() -> list[int]:
    """Let a one-shot create walk its existing first-level directory.

    Resident fopen mode 0 treats the current component as the file to create;
    it consequently cannot descend through ``我的邮件`` on its own.  During
    checkpoint provisioning only, use lookup mode 1 while the directory
    selector is still zero, then restore mode 0 for the final filename.  The
    caller restores the original SCALL immediately after fopen returns.
    """
    words = [
        0x2E01, 0x58F1, 0x58F2, 0x58F3,  # LINK #1; preserve R1..R3
        0x780B, 0x0006, 0x781B, 0x0008,
        0x70F1, 0x0030, 0x5100,          # FILE directory selector
        0x4C11, 0x5C01, 0x58F0, 0x1F90, 0x4D11, 0x2801,
        0x5600, 0xAC02, 0x0000,          # if nonzero, keep create mode
    ]
    direct_target_index = len(words) - 1
    words.extend(_store_file_object_mode_words(1))
    words.extend(_call_file_lookup_words())
    words.extend((0x6A0B, 0xFFFE))        # preserve lookup result
    words.extend(_store_file_object_mode_words(0))
    words.extend((0x780B, 0xFFFE, 0xAC00, 0x0000))
    epilogue_target_index = len(words) - 1
    direct_address = VMA03_PIM_PATH_LOOKUP_VENEER_ADDRESS + len(words) * 2
    words[direct_target_index] = direct_address & 0xFFFF
    words.extend(_call_file_lookup_words())
    epilogue_address = VMA03_PIM_PATH_LOOKUP_VENEER_ADDRESS + len(words) * 2
    words[epilogue_target_index] = epilogue_address & 0xFFFF
    words.extend((0x383F, 0x382F, 0x381F, 0x2F00, reconstructed.RETS))
    return words


def vma03_pim_provision_filter_words() -> list[int]:
    """Arm provisioning only after the observed category-0E startup call.

    The SCALL at 31:9E44 is shared by the category sequence
    05,04,03,08,0E,08.  Installing the provisioner directly there consumed
    the hook on category 05, before the resident filesystem had completed
    the mode-2 USERINFO/root-cache setup.  This first-stage filter forwards
    every call unchanged and replaces itself with the stage-two wrapper only
    while handling category 0E.  The next observed call is the late category
    08 which owns ``nminbox.pim``.
    """
    words = [
        0x2E00,                           # LINK #0
        0x780B, 0x0006,                  # category word at FP+6
        0x560E,                           # CMP R0, #0x0E
        0xAC02, 0x0000,                  # AJMP NZ, forward
    ]
    forward_target_index = len(words) - 1
    words.extend(reconstructed.write_program_words(
        VMA03_PIM_PROVISION_TRIGGER_ADDRESS,
        [
            0xBD00 | (VMA03_PIM_PROVISION_WRAPPER_ADDRESS >> 16),
            VMA03_PIM_PROVISION_WRAPPER_ADDRESS & 0xFFFF,
        ],
    ))
    forward_address = VMA03_PIM_PROVISION_FILTER_ADDRESS + len(words) * 2
    words[forward_target_index] = forward_address & 0xFFFF
    words.extend((
        0x780B, 0x0008, 0x58F0,          # mode first
        0x780B, 0x0006, 0x58F0,          # category second
        0xBD00 | (VMA03_PIM_PROVISION_ORIGINAL_TARGET >> 16),
        VMA03_PIM_PROVISION_ORIGINAL_TARGET & 0xFFFF,
        0x50F4,
        0x2F00, reconstructed.RETS,
    ))
    return words


def vma03_pim_provision_wrapper_words() -> list[int]:
    """Create the late category-08 PIM through shipped filesystem calls."""
    encoded_path = VMA03_PIM_PATH.encode("gb18030") + b"\0"
    if len(encoded_path) > -VMA03_PIM_PATH_FP_OFFSET:
        raise ValueError("minimal PIM guest path exceeds wrapper buffer")
    encoded_path = encoded_path.ljust(-VMA03_PIM_PATH_FP_OFFSET, b"\0")
    words = [
        0x2E10,                           # 32-byte near path buffer
        0x780B, 0x0006,                  # category word at FP+6
        0x5608,                           # CMP R0, #0x08
        0xAC02, 0x0000,                  # AJMP NZ, forward unchanged
    ]
    category_mismatch_target_index = len(words) - 1
    # Restore the replaced SCALL only on the selected late category-08 call.
    # This is an ordinary guest write to VMA03 executable RAM and makes
    # provisioning one-shot without consuming the hook on an earlier call.
    words.extend(reconstructed.write_program_words(
        VMA03_PIM_PROVISION_TRIGGER_ADDRESS,
        [
            0xBD00 | (VMA03_PIM_PROVISION_ORIGINAL_TARGET >> 16),
            VMA03_PIM_PROVISION_ORIGINAL_TARGET & 0xFFFF,
        ],
    ))
    lookup_call = reconstructed.program_source_words(
        VMA03_PIM_PATH_LOOKUP_CALL_SOURCE, 4
    )
    expected_lookup_call = [
        0xBD00 | (VMA03_PIM_PATH_LOOKUP_ORIGINAL_TARGET >> 16),
        VMA03_PIM_PATH_LOOKUP_ORIGINAL_TARGET & 0xFFFF,
    ]
    if lookup_call != expected_lookup_call:
        raise ValueError(
            "PIM path-lookup call signature changed: "
            f"{lookup_call!r} != {expected_lookup_call!r}"
        )
    words.extend(reconstructed.write_program_words(
        VMA03_PIM_PATH_LOOKUP_CALL_ADDRESS,
        [
            0xBD00 | (VMA03_PIM_PATH_LOOKUP_VENEER_ADDRESS >> 16),
            VMA03_PIM_PATH_LOOKUP_VENEER_ADDRESS & 0xFFFF,
        ],
    ))
    for index, value in enumerate(_guest_immediate_words(encoded_path)):
        words.extend((
            0x68F0, value,
            0x6A0B, (VMA03_PIM_PATH_FP_OFFSET + index * 2) & 0xFFFF,
        ))
    words.extend((
        0x4800, 0x58F0,                   # fopen mode 0: create if absent
        0x081B, 0x70F1, VMA03_PIM_PATH_FP_OFFSET & 0xFFFF,
        0x4800, 0x58F1, 0x58F0,           # near path pointer
        0xBD1F, 0x1F1A, 0x50F6,
        0x6A0B, 0xFFFC, 0x6A1B, 0xFFFE,  # save returned FILE pointer
        0x5210, 0x5300,
        0xAC02, 0x0000,                   # non-null: skip bounded fallback
    ))
    restore_lookup_target_index = len(words) - 1
    # Keep one bounded retry through the same native API before restoring the
    # path call.  The successful v6 trace returns a FILE on the first fopen;
    # the retry is only a defensive checkpoint-generation fallback and is not
    # evidence for a resident cache dependency.
    words.extend((
        0x4800, 0x58F0,
        0x081B, 0x70F1, VMA03_PIM_PATH_FP_OFFSET & 0xFFFF,
        0x4800, 0x58F1, 0x58F0,
        0xBD1F, 0x1F1A, 0x50F6,
        0x6A0B, 0xFFFC, 0x6A1B, 0xFFFE,
    ))
    # Restore the path resolver before forwarding to normal startup.  The
    # saved FILE result is reloaded because the guest code write uses R0/R1.
    restore_lookup_address = (
        VMA03_PIM_PROVISION_WRAPPER_ADDRESS + len(words) * 2
    )
    words[restore_lookup_target_index] = restore_lookup_address & 0xFFFF
    words.extend(reconstructed.write_program_words(
        VMA03_PIM_PATH_LOOKUP_CALL_ADDRESS,
        expected_lookup_call,
    ))
    words.extend((
        0x780B, 0xFFFC, 0x781B, 0xFFFE,
        0x5210, 0x5300,
        0xAC01, 0x0000,                   # AJMP Z, done (patched below)
    ))
    done_target_index = len(words) - 1
    words.extend((
        0x780B, 0xFFFC, 0x781B, 0xFFFE, 0x58F1, 0x58F0,
        0xBD00 | (VMA03_PIM_PROVISION_WRITER_ADDRESS >> 16),
        VMA03_PIM_PROVISION_WRITER_ADDRESS & 0xFFFF,
        0x50F4,
        0x780B, 0xFFFC, 0x781B, 0xFFFE, 0x58F1, 0x58F0,
        0xBD24, 0xEAEC, 0x50F4,           # resident close/commit
    ))
    done_address = (
        VMA03_PIM_PROVISION_WRAPPER_ADDRESS + len(words) * 2
    )
    words[done_target_index] = done_address & 0xFFFF
    words[category_mismatch_target_index] = done_address & 0xFFFF
    # Preserve the replaced two-word PIM allocator call.  Its caller pushes
    # mode first and category second, leaving category at wrapper FP+6.
    words.extend((
        0x780B, 0x0008, 0x58F0,
        0x780B, 0x0006, 0x58F0,
        0xBD00 | (VMA03_PIM_PROVISION_ORIGINAL_TARGET >> 16),
        VMA03_PIM_PROVISION_ORIGINAL_TARGET & 0xFFFF,
        0x50F4,
        0x2F00, reconstructed.RETS,
    ))
    return words


def install_hole_routine(
        output: bytearray, address: int, words: list[int], name: str) -> None:
    payload = words_to_bytes(words)
    end = address + len(payload)
    if end > len(output):
        raise ValueError(f"input is too short for {name}")
    expected = SKELETON_HOLE * len(words)
    actual = bytes(output[address:end])
    if actual != expected:
        raise ValueError(
            f"{name} mask-ROM range is not a skeleton hole: "
            f"{address:06X}..{end:06X}"
        )
    output[address:end] = payload


def replace_exact_routine(
        output: bytearray,
        address: int,
        old_words: list[int],
        new_words: list[int],
        name: str) -> None:
    if len(old_words) != len(new_words):
        raise ValueError(f"{name} replacement changes the entry size")
    expected = words_to_bytes(old_words)
    end = address + len(expected)
    actual = bytes(output[address:end])
    if actual != expected:
        raise ValueError(
            f"{name} entry signature changed at {address:06X}: "
            f"expected={expected[:16].hex()} actual={actual[:16].hex()}"
        )
    output[address:end] = words_to_bytes(new_words)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def retire_legacy_source_repair(output: bytearray) -> dict:
    """Remove only the known pre-VMA03 installer, not unknown ROM bytes.

    The original PRG calls the resident entries inside this range, not the
    synthesized installer at B000.  Under VMA03 the two source fragments
    are already linked in place.  Missing services remain strict holes;
    this does not implement the services or manufacture a return value.
    """
    address = reconstructed.APPLICATION_OPERATION_MODAL_SOURCE_REPAIR_INSTALLER_ADDRESS
    words = reconstructed.operation_modal_source_repair_installer_words()
    expected = words_to_bytes(words)
    end = address + len(expected)
    if end > len(output) or bytes(output[address:end]) != expected:
        raise ValueError(
            f"legacy source-repair installer signature changed at {address:06X}"
        )
    output[address:end] = SKELETON_HOLE * len(words)
    return {
        "address": f"{address >> 16:02X}:{address & 0xffff:04X}",
        "end_exclusive": f"{end >> 16:02X}:{end & 0xffff:04X}",
        "bytes": len(expected),
        "retired_sha256": sha256(expected),
        "fill": "0F00 (missing resident service, not a success stub)",
        "known_resident_entries": ["01:B6DE", "01:B7AA", "01:B816", "01:B84E"],
        "services_implemented": False,
    }


def build(
        input_path: Path, output_path: Path, manifest_path: Path, *,
        provision_minimal_pim: bool = False) -> None:
    source = input_path.read_bytes()
    end = ROM01_POST_CLOCK_ADDRESS + len(EXPECTED_PREFIX)
    if end > len(source):
        raise ValueError("input is too short to contain resident 01:0200")
    actual = source[ROM01_POST_CLOCK_ADDRESS:end]
    if actual != EXPECTED_PREFIX:
        raise ValueError(
            "resident 01:0200 signature changed: "
            f"expected={EXPECTED_PREFIX.hex()} actual={actual.hex()}"
        )

    loader_end = (
        ROM01_POST_CLOCK_ADDRESS + LEGACY_ROM01_LOADER_WORDS * 2
    )
    if loader_end > len(source):
        raise ValueError("input is too short to contain the legacy ROM01 loader")

    output = bytearray(source)
    source_repair_retirement = retire_legacy_source_repair(output)
    output[ROM01_POST_CLOCK_ADDRESS:loader_end] = (
        SKELETON_HOLE * LEGACY_ROM01_LOADER_WORDS
    )
    bootstrap = vma03_bootstrap_words(
        provision_minimal_pim=provision_minimal_pim
    )
    output[
        ROM01_POST_CLOCK_ADDRESS:
        ROM01_POST_CLOCK_ADDRESS + len(bootstrap) * 2
    ] = words_to_bytes(bootstrap)
    for address in PROVISIONAL_AUDIO_RETURNS:
        if output[address:address + 2] != SKELETON_HOLE:
            raise ValueError(
                f"expected retired-loader hole at {address:06X}"
            )
        output[address:address + 2] = RETS

    capacity_installer = vma03_capacity_installer_words()
    capacity_wrapper = reconstructed.storage_unit_open_capacity_wrapper_words(
        VMA03_CAPACITY_WRAPPER_ADDRESS
    )
    installer_end = VMA03_CAPACITY_INSTALLER_ADDRESS + len(capacity_installer) * 2
    if installer_end > VMA03_CAPACITY_WRAPPER_ADDRESS:
        raise ValueError("VMA03 capacity installer overlaps its wrapper")
    install_hole_routine(
        output,
        VMA03_CAPACITY_INSTALLER_ADDRESS,
        capacity_installer,
        "VMA03 capacity installer",
    )
    install_hole_routine(
        output,
        VMA03_CAPACITY_WRAPPER_ADDRESS,
        capacity_wrapper,
        "VMA03 unit-open capacity wrapper",
    )
    file_callback_installer = reconstructed.file_driver_callback_installer_words(
        VMA03_FILE_CALLBACK_WRAPPER_ADDRESS
    )
    file_callback_child = reconstructed.file_driver_callback_child_words()
    file_callback_wrapper = reconstructed.file_driver_callback_wrapper_words(
        VMA03_FILE_CALLBACK_CHILD_ADDRESS
    )
    for address, words, name in (
        (
            VMA03_FILE_CALLBACK_INSTALLER_ADDRESS,
            file_callback_installer,
            "VMA03 file callback installer",
        ),
        (
            VMA03_FILE_CALLBACK_CHILD_ADDRESS,
            file_callback_child,
            "VMA03 file callback child",
        ),
        (
            VMA03_FILE_CALLBACK_WRAPPER_ADDRESS,
            file_callback_wrapper,
            "VMA03 file callback wrapper",
        ),
    ):
        install_hole_routine(output, address, words, name)

    pim_provision_filter: list[int] = []
    pim_provision_wrapper: list[int] = []
    pim_provision_writer: list[int] = []
    pim_path_lookup_veneer: list[int] = []
    if provision_minimal_pim:
        pim_provision_filter = vma03_pim_provision_filter_words()
        pim_provision_wrapper = vma03_pim_provision_wrapper_words()
        pim_provision_writer = vma03_pim_provision_writer_words()
        pim_path_lookup_veneer = vma03_pim_path_lookup_veneer_words()
        install_hole_routine(
            output,
            VMA03_PIM_PROVISION_FILTER_ADDRESS,
            pim_provision_filter,
            "VMA03 guest-native minimal-PIM timing filter",
        )
        install_hole_routine(
            output,
            VMA03_PIM_PROVISION_WRAPPER_ADDRESS,
            pim_provision_wrapper,
            "VMA03 guest-native minimal-PIM provision wrapper",
        )
        install_hole_routine(
            output,
            VMA03_PIM_PROVISION_WRITER_ADDRESS,
            pim_provision_writer,
            "VMA03 guest-native minimal-PIM writer",
        )
        install_hole_routine(
            output,
            VMA03_PIM_PATH_LOOKUP_VENEER_ADDRESS,
            pim_path_lookup_veneer,
            "VMA03 one-shot nested-create lookup veneer",
        )

    nand_prepare = reconstructed.prepare_logical_read_words()
    nand_pack = reconstructed.pack_logical_spare_words()
    nand_unpack = reconstructed.unpack_logical_spare_words(
        VMA03_NAND_UNPACK_FULL_ADDRESS
    )
    nand_unpack_full = reconstructed.unpack_full_logical_page_words()
    for address, words, name in (
        (VMA03_NAND_PREPARE_READ_ADDRESS, nand_prepare,
         "VMA03 NAND read preparation"),
        (VMA03_NAND_PACK_SPARE_ADDRESS, nand_pack,
         "VMA03 NAND spare packer"),
        (VMA03_NAND_UNPACK_SPARE_ADDRESS, nand_unpack,
         "VMA03 NAND spare unpacker"),
        (VMA03_NAND_UNPACK_FULL_ADDRESS, nand_unpack_full,
         "VMA03 NAND full-page unpacker"),
    ):
        install_hole_routine(output, address, words, name)

    replace_exact_routine(
        output,
        0x02BBF6,
        reconstructed.read_page_words(),
        reconstructed.read_page_words(
            VMA03_NAND_PREPARE_READ_ADDRESS,
            VMA03_NAND_UNPACK_SPARE_ADDRESS,
        ),
        "VMA03 NAND page-read",
    )
    replace_exact_routine(
        output,
        0x02BCC6,
        reconstructed.program_page_words(),
        reconstructed.program_page_words(VMA03_NAND_PACK_SPARE_ADDRESS),
        "VMA03 NAND page-program",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output)
    manifest = {
        "format": "np560-vma03-soc-rom-experiment-v4",
        "input": str(input_path.resolve()),
        "input_sha256": sha256(source),
        "output": str(output_path.resolve()),
        "output_sha256": sha256(output),
        "legacy_source_repair_retirement": source_repair_retirement,
        "legacy_loader_retirement": {
            "address": "01:0200",
            "end_exclusive": f"01:{loader_end & 0xffff:04X}",
            "words": LEGACY_ROM01_LOADER_WORDS,
            "expected": "BD06 1D40",
            "fill": "0F00 (strict skeleton hole)",
            "entry_replacement": (
                "SCALL 25:5858; install two-stage late 31:9E44 hook; RETS"
                if provision_minimal_pim else
                "SCALL 25:5858; RETS"
            ),
            "purpose": (
                "retire obsolete overlay copies while preserving the "
                "post-BSS storage registry side effects"
            ),
        },
        "vma03_storage_bootstrap": {
            "entry": "01:0200",
            "capacity_installer": "02:5100",
            "capacity_installer_words": len(capacity_installer),
            "unit_open_wrapper": "02:5600",
            "unit_open_wrapper_words": len(capacity_wrapper),
            "storage_registry": "25:5858",
            "file_callback_installer": "02:5700",
            "file_callback_child": "02:5800",
            "file_callback_wrapper": "02:5840",
            "helper_usage": (
                "installed for controlled comparison but not called: in "
                "VMA03 the original 33/32 targets already resolve to their "
                "+1D source-proven implementations"
            ),
            "implementation": (
                "guest DMCU code using signature-checked NP560.PRG words; "
                "no host ROM-service interception"
            ),
        },
        "vma03_nand_helpers": {
            "read_entry": "02:BBF6",
            "program_entry": "02:BCC6",
            "prepare_read": "02:6000",
            "pack_spare": "02:6100",
            "unpack_spare": "02:6200",
            "unpack_full": "02:6400",
            "purpose": (
                "keep the complete guest NAND helper closure below 03:0000, "
                "where VMA03 firmware RAM cannot hide it"
            ),
        },
        "checkpoint_provisioning": {
            "enabled": provision_minimal_pim,
            "scope": "one-shot diagnostic checkpoint generation",
            "filter": "02:7000" if provision_minimal_pim else None,
            "arm_category": "0E" if provision_minimal_pim else None,
            "wrapper": "02:7600" if provision_minimal_pim else None,
            "provision_category": "08" if provision_minimal_pim else None,
            "writer": "02:7200" if provision_minimal_pim else None,
            "path_lookup_veneer": (
                "02:7400" if provision_minimal_pim else None
            ),
            "path_lookup_call": (
                "2D:D9E2 restored after the bounded create attempt"
                if provision_minimal_pim
                else None
            ),
            "late_trigger": (
                "31:9E44 (source 4E:9E44), filter remains until category 0E"
                if provision_minimal_pim else None
            ),
            "original_target": (
                "1E:6444 with category/mode words forwarded"
                if provision_minimal_pim else None
            ),
            "filter_words": len(pim_provision_filter),
            "wrapper_words": len(pim_provision_wrapper),
            "writer_words": len(pim_provision_writer),
            "path_lookup_veneer_words": len(pim_path_lookup_veneer),
            "guest_calls": (
                "1F:1F1A mode 0; 17:E3EE 0x4A bytes; 24:EAEC"
                if provision_minimal_pim else None
            ),
            "guest_path": VMA03_PIM_PATH,
            "payload_sha256": sha256(MINIMAL_PIM),
            "normal_boot_rom": not provision_minimal_pim,
            "host_filesystem_service": False,
            "scall_interception": False,
        },
        "provisional_audio_returns": [
            {
                "address": f"{address >> 16:02X}:{address & 0xffff:04X}",
                "replacement": "C620",
                "inferred_contract": contract,
            }
            for address, contract in PROVISIONAL_AUDIO_RETURNS.items()
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--provision-minimal-pim", action="store_true",
        help=(
            "one-shot diagnostic mode: create category-08 nminbox.pim "
            "through the guest resident PIM/file/NAND path"
        ),
    )
    args = parser.parse_args()
    manifest = args.manifest or args.output.with_suffix(".json")
    build(
        args.input, args.output, manifest,
        provision_minimal_pim=args.provision_minimal_pim,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
