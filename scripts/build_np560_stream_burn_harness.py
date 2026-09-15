#!/usr/bin/env python3
"""Build a guest harness for UpdateAll.exe's official NAND stream protocol.

The CLI defaults to an externally driven command trampoline: only bootstrap
23 runs autonomously, while the host follows the original UpdateAll branches.
The legacy 'official' mode is a fixed forced-format diagnostic sequence.

UpdateAll first launches the freshly loaded burner at 0x506000 with bootstrap
command 23, whose first jump performs its one-time initialization.  For a
blank device it then runs commands 1, 27, 11, 2 and 25, and streams the
package's slot-3 image through command 13.  Each transfer contains at most
0xC000 bytes at data address 52:6000.  The updater writes the 512-byte page
count at 50:0010 and the destination page (starting at 0x880) at 50:0030.
After the last chunk, UpdateAll issues command 18 with 50:0040 set to 0x0200;
this is the vendor finalization pass that commits the streamed NAND image.
Commands after the bootstrap use
usb_Lib_DMCUProgramStart(0x506004); the word there jumps straight to the
50:7566 dispatcher without repeating initialization.  NAND/FTL work therefore
remains inside the unmodified vendor DMCU code.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.build_np560_burn_harness import (
        BURNER_GLOBAL_SEGMENT,
        PROGRAM_SIZE,
        _store_word,
    )
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    from build_np560_burn_harness import (  # type: ignore[no-redef]
        BURNER_GLOBAL_SEGMENT,
        PROGRAM_SIZE,
        _store_word,
    )


STREAM_CONTROL_SEGMENT = 0x01C0
STREAM_CONTROL_BASE = 0xE00000
STREAM_FLAG = 0x0000
STREAM_ACK = 0x0002
STREAM_PROBE = 0x0004
STREAM_SETUP_TRACE = 0x0010
STREAM_MAPPING_TRACE = 0x0100
STREAM_READY = 0xA55A
STREAM_PROTOCOL = 0x0006
STREAM_UPDATEALL_PROTOCOL = 0xC103
STREAM_FILES_PROTOCOL = 0xC104
STREAM_RETURN = 0x0030  # R0..R3, result, detail, partition base/extent.
STREAM_FINALIZE_COMMAND = 18
STREAM_FINALIZE_VALUE = 0x0200
STREAM_SOURCE = 0x526000
STREAM_START_PAGE = 0x00000880
# Kept as an import-compatible name for older diagnostics.
STREAM_START = STREAM_START_PAGE
DEFAULT_TOTAL_LENGTH = 0x029ED3B4
SETUP_MODES = {
    # Only bootstrap runs autonomously. The host follows UpdateAll's actual
    # error/format branches and submits subsequent original burner commands.
    "updateall": (23,),
    # Historical fixed sequence: explicitly forces repartitioning even when
    # command 27 says the current partition is already suitable.
    "official": (23, 1, 27, 11, 2, 25),
    # Isolates the post-format reset/object-rebuild stage against a saved NAND
    # checkpoint without spending minutes formatting it again.
    "diagnostic-reset": (23, 1, 2, 25),
}


def _u32_words(value: int) -> tuple[int, int]:
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("32-bit burner value is out of range")
    return value >> 16, value & 0xFFFF


def _call_command(
    words: list[int], command: int, assignments: tuple[tuple[int, int], ...],
    *, cold_start: bool,
) -> None:
    _store_word(words, 0x0008, command)
    for address, value in assignments:
        _store_word(words, address, value)
    # BURN_NAND_FLASH_CODE.bin starts with two jumps.  50:6000 is the cold
    # initializer and 50:6004 is UpdateAll's command re-entry at 0x506004.
    words.extend([0xBD50, 0x6000 if cold_start else 0x6004])


def _snapshot_partition(words: list[int], step: int) -> None:
    """Record partition and map-cache state after one setup command."""
    words.extend([
        0x6810, BURNER_GLOBAL_SEGMENT,
        0x88F0, 0x07EA,
        0x88F1, 0x07EC,
        0x88F2, 0x001A,
        0x88F3, 0x0860,
        0x6810, STREAM_CONTROL_SEGMENT,
        0xA8F0, STREAM_SETUP_TRACE + step * 8,
        0xA8F1, STREAM_SETUP_TRACE + step * 8 + 2,
        0xA8F2, STREAM_SETUP_TRACE + step * 8 + 4,
        0xA8F3, STREAM_SETUP_TRACE + step * 8 + 6,
        0x6810, BURNER_GLOBAL_SEGMENT,
        0x88F0, 0x0096,
        0x88F1, 0x0098,
        0x88F2, 0x009E,
        # Logical block 0x056F is the first command-13 target reached by the
        # official 0x880 start page.  When the cache covers 0x0500..0x05FF,
        # its entry is at 0x009E + 0x6F * 2 = 0x017C.
        0x88F3, 0x017C,
        0x6810, STREAM_CONTROL_SEGMENT,
        0xA8F0, STREAM_MAPPING_TRACE + step * 8,
        0xA8F1, STREAM_MAPPING_TRACE + step * 8 + 2,
        0xA8F2, STREAM_MAPPING_TRACE + step * 8 + 4,
        0xA8F3, STREAM_MAPPING_TRACE + step * 8 + 6,
        0x6810, BURNER_GLOBAL_SEGMENT,
    ])


def _snapshot_return(words: list[int]) -> None:
    # Capture the original return registers BEFORE any scratch-register use.
    words.extend([0x6810, STREAM_CONTROL_SEGMENT])
    for register in range(4):
        words.extend([0xA8F0 + register, STREAM_RETURN + register * 2])
    words.extend([0x6810, BURNER_GLOBAL_SEGMENT])
    for register, address in enumerate((0x001A, 0x001C, 0x07EA, 0x07EC)):
        words.extend([0x88F0 + register, address])
    words.extend([0x6810, STREAM_CONTROL_SEGMENT])
    for register in range(4):
        words.extend([0xA8F0 + register, STREAM_RETURN + 8 + register * 2])


def _build_updateall_program(*, file_transport=False) -> tuple[bytes, dict[str, int]]:
    """Transport trampoline, not an implementation of NAND or ROM services."""
    words, labels, fixups = [], {}, []

    def mark(name):
        labels[name] = len(words) * 2

    def jump(condition, target):
        words.extend([0xAC00 + condition, 0])
        fixups.append((len(words) - 1, target))

    def acknowledge():
        words.extend([0x6810, STREAM_CONTROL_SEGMENT])
        _store_word(words, STREAM_FLAG, 0)
        words.extend([0x88F0, STREAM_ACK, 0x5001, 0xA8F0, STREAM_ACK])

    words.extend([0x6810, BURNER_GLOBAL_SEGMENT])
    _call_command(words, 23, (), cold_start=True)
    _snapshot_return(words)
    _store_word(words, STREAM_PROTOCOL,
                STREAM_FILES_PROTOCOL if file_transport else STREAM_UPDATEALL_PROTOCOL)
    _store_word(words, STREAM_FLAG, 0)
    _store_word(words, STREAM_ACK, STREAM_READY)
    mark("loop")
    words.extend([0x88F0, STREAM_FLAG, 0x5600])
    jump(1, "loop")
    if not file_transport:
        words.extend([0x76F0, 0xFFFF])
        jump(1, "done")
        words.extend([0x5601])
        jump(1, "stream")
    words.extend([0x5602])
    jump(1, "command")
    if file_transport:
        words.extend([0x5603])
        jump(1, "pathname")
    # An invalid protocol request must not silently execute a stale command.
    jump(0, "stop")

    if file_transport:
        mark("pathname")
        # Original command 3/4/5 handlers take a near pathname at 00:0FF0.
        # Copy the bounded USB staging message there with ordinary guest
        # instructions; do not broaden the host's protected-RAM write window.
        words.extend([0x6810, 0, 0x6811, (STREAM_SOURCE >> 16) << 1,
                      # DS1 is selected by logical address bit 15, not by
                      # whether an operand is the source of MOV.
                      0x68F0, 0x0FF0, 0x68F1, (STREAM_SOURCE & 0x7FFF) | 0x8000,
                      0xBF00, 0x0080, 0x5A01])
    else:
        mark("stream")
        words.extend([0x6810, (STREAM_SOURCE >> 16) << 1,
                      0x88F0, STREAM_SOURCE & 0xFFFF,
                      0x6810, STREAM_CONTROL_SEGMENT, 0xA8F0, STREAM_PROBE,
                      0x6810, BURNER_GLOBAL_SEGMENT])
        _store_word(words, 0x0008, 13)
    mark("command")
    words.extend([0x6810, BURNER_GLOBAL_SEGMENT, 0xBD50, 0x6004])
    _snapshot_return(words)
    acknowledge()
    jump(0, "loop")

    mark("done")
    if not file_transport:
        words.extend([0x6810, BURNER_GLOBAL_SEGMENT])
        _call_command(words, STREAM_FINALIZE_COMMAND,
                      ((0x0040, STREAM_FINALIZE_VALUE),), cold_start=False)
        _snapshot_return(words)
        acknowledge()
    mark("stop")
    words.append(0xD0FF)
    for index, name in fixups:
        words[index] = labels[name]
    image = bytearray(PROGRAM_SIZE)
    for index, word in enumerate(words):
        image[index * 2:index * 2 + 2] = word.to_bytes(2, "little")
    return bytes(image), labels


def build_file_program() -> tuple[bytes, dict[str, int]]:
    """File transport variant; no autonomous burn or finalization commands."""
    return _build_updateall_program(file_transport=True)


def build_program(
    total_length: int = DEFAULT_TOTAL_LENGTH,
    setup_mode: str = "official",
) -> tuple[bytes, dict[str, int]]:
    total_hi, total_lo = _u32_words(total_length)
    words = [0x6810, BURNER_GLOBAL_SEGMENT]
    if setup_mode not in SETUP_MODES:
        raise ValueError(f"unknown setup mode: {setup_mode}")
    if setup_mode == "updateall":
        return _build_updateall_program()
    assignments = {
        # UpdateAll's device-preparation function at 0x4023B0..0x4027F1.
        1: ((0x0034, 0), (0x0036, 0xABF5), (0x0094, 2)),
        11: ((0x0010, 0), (0x0012, 0xABF5)),
        # UpdateAll.exe 0x402B46..0x402BE6 supplies the slot-3 length and
        # official 0xC000 staging-buffer size before entering 0x4042D0.
        25: ((0x0038, total_hi), (0x003A, total_lo),
             (0x003C, 0), (0x003E, 0xC000)),
    }
    setup = tuple(
        (command, assignments.get(command, ()))
        for command in SETUP_MODES[setup_mode]
    )
    for index, (command, assignments) in enumerate(setup):
        _call_command(words, command, assignments, cold_start=index == 0)
        _snapshot_partition(words, index)

    words.extend([0x6810, STREAM_CONTROL_SEGMENT])
    _store_word(words, STREAM_FLAG, 0)
    _store_word(words, STREAM_ACK, STREAM_READY)
    loop_word = len(words)
    words.extend([
        0x88F0, STREAM_FLAG,       # MOV R0, [STREAM_FLAG]
        0x5600,                    # CMP R0, #0
        0xAC01, 0,                 # AJMP Z, loop
        0x76F0, 0xFFFF,            # CMP R0, #0xFFFF
        0xAC01, 0,                 # AJMP Z, done
    ])
    wait_jump_target = loop_word * 2
    words[loop_word + 4] = wait_jump_target
    done_jump_word = loop_word + 8

    words.extend([
        0x6810, (STREAM_SOURCE >> 16) << 1,
        0x88F0, STREAM_SOURCE & 0xFFFF,
        0x6810, STREAM_CONTROL_SEGMENT,
        0xA8F0, STREAM_PROBE,
        0x6810, BURNER_GLOBAL_SEGMENT,
    ])
    _store_word(words, 0x0008, 13)
    _store_word(words, 0x0014, STREAM_SOURCE >> 16)
    _store_word(words, 0x0016, STREAM_SOURCE & 0xFFFF)
    # Each streamed command-13 chunk is launched at UpdateAll's 0x506004
    # command re-entry too.
    words.extend([0xBD50, 0x6004])
    words.extend([0x6810, STREAM_CONTROL_SEGMENT])
    _store_word(words, STREAM_FLAG, 0)
    words.extend([
        0x88F0, STREAM_ACK,        # MOV R0, [STREAM_ACK]
        0x5001,                    # ADD R0, #1
        0xA8F0, STREAM_ACK,        # MOV [STREAM_ACK], R0
        0xAC00, wait_jump_target,  # AJMP ALWAYS, loop
    ])
    done_word = len(words)
    words[done_jump_word] = done_word * 2
    words.extend([0x6810, BURNER_GLOBAL_SEGMENT])
    _call_command(
        words,
        STREAM_FINALIZE_COMMAND,
        ((0x0040, STREAM_FINALIZE_VALUE),),
        cold_start=False,
    )
    words.extend([0x6810, STREAM_CONTROL_SEGMENT])
    _store_word(words, STREAM_FLAG, 0)
    words.extend([
        0x88F0, STREAM_ACK,
        0x5001,
        0xA8F0, STREAM_ACK,
    ])
    words.append(0xD0FF)

    image = bytearray(PROGRAM_SIZE)
    for index, word in enumerate(words):
        image[index * 2:index * 2 + 2] = word.to_bytes(2, "little")
    info = {
        "loop": wait_jump_target,
        "done": done_word * 2,
        "stop": (len(words) - 1) * 2,
    }
    return bytes(image), info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--boot-mode", choices=("firmware", "firmware-vma03"),
                        default="firmware-vma03",
                        help="record the matching QEMU harness mapping in the manifest")
    parser.add_argument(
        "--total-length", type=lambda value: int(value, 0),
        default=DEFAULT_TOTAL_LENGTH,
        help="complete NAND-image byte length supplied to command 25",
    )
    parser.add_argument(
        "--setup-mode", choices=tuple(SETUP_MODES), default="updateall",
        help="updateall follows host decisions; official is the historical forced-format sequence",
    )
    args = parser.parse_args()

    image, addresses = build_program(args.total_length, args.setup_mode)
    args.output.write_bytes(image)
    manifest_path = args.manifest or args.output.with_suffix(".json")
    manifest = {
        "format": "np560-stream-burn-harness-v3",
        "warning": "Reverse-engineering fixture; not product firmware.",
        "protocol_source": (
            "UpdateAll.exe 0x4052E0..0x4054B2, 0x4023B0..0x402BE6, "
            "and 0x4042D0..0x4045AA"
        ),
        "setup_mode": args.setup_mode,
        "boot_mode": args.boot_mode,
        "setup_commands": list(SETUP_MODES[args.setup_mode]),
        "host_controlled_setup": args.setup_mode == "updateall",
        "protocol_word": f"0x{STREAM_UPDATEALL_PROTOCOL:04X}" if args.setup_mode == "updateall" else None,
        "stream_command": 13,
        "finalize_command": STREAM_FINALIZE_COMMAND,
        "finalize_field": "50:0040",
        "finalize_value": f"0x{STREAM_FINALIZE_VALUE:04X}",
        "target_start_page": f"0x{STREAM_START_PAGE:08X}",
        "total_length": args.total_length,
        "source": f"{STREAM_SOURCE >> 16:02X}:{STREAM_SOURCE & 0xFFFF:04X}",
        "flag_physical": f"0x{STREAM_CONTROL_BASE + STREAM_FLAG:06X}",
        "ack_physical": f"0x{STREAM_CONTROL_BASE + STREAM_ACK:06X}",
        "probe_physical": f"0x{STREAM_CONTROL_BASE + STREAM_PROBE:06X}",
        "setup_trace_physical": f"0x{STREAM_CONTROL_BASE + STREAM_SETUP_TRACE:06X}",
        "mapping_trace_physical": f"0x{STREAM_CONTROL_BASE + STREAM_MAPPING_TRACE:06X}",
        "ready": f"0x{STREAM_READY:04X}",
        **{key: f"{'03' if args.boot_mode == 'firmware-vma03' else '20'}:{value:04X}"
           for key, value in addresses.items()},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(image):,} bytes to {args.output.resolve()}")
    print(f"wrote {manifest_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
