#!/usr/bin/env python3
"""Build a guest harness for UpdateAll.exe's official NAND stream protocol.

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
    from disassembly.build_np560_burn_harness import (
        BURNER_GLOBAL_SEGMENT,
        PROGRAM_SIZE,
        _store_word,
    )
except ModuleNotFoundError:  # Direct execution from the disassembly directory.
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
STREAM_FINALIZE_COMMAND = 18
STREAM_FINALIZE_VALUE = 0x0200
STREAM_SOURCE = 0x526000
STREAM_START_PAGE = 0x00000880
# Kept as an import-compatible name for older diagnostics.
STREAM_START = STREAM_START_PAGE
DEFAULT_TOTAL_LENGTH = 0x029ED3B4
SETUP_MODES = {
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


def build_program(
    total_length: int = DEFAULT_TOTAL_LENGTH,
    setup_mode: str = "official",
) -> tuple[bytes, dict[str, int]]:
    total_hi, total_lo = _u32_words(total_length)
    words = [0x6810, BURNER_GLOBAL_SEGMENT]
    if setup_mode not in SETUP_MODES:
        raise ValueError(f"unknown setup mode: {setup_mode}")
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
    parser.add_argument(
        "--total-length", type=lambda value: int(value, 0),
        default=DEFAULT_TOTAL_LENGTH,
        help="complete NAND-image byte length supplied to command 25",
    )
    parser.add_argument(
        "--setup-mode", choices=tuple(SETUP_MODES), default="official",
        help="official UpdateAll setup chain",
    )
    args = parser.parse_args()

    image, addresses = build_program(args.total_length, args.setup_mode)
    args.output.write_bytes(image)
    manifest_path = args.manifest or args.output.with_suffix(".json")
    manifest = {
        "format": "np560-stream-burn-harness-v2",
        "warning": "Reverse-engineering fixture; not product firmware.",
        "protocol_source": (
            "UpdateAll.exe 0x4052E0..0x4054B2, 0x4023B0..0x402BE6, "
            "and 0x4042D0..0x4045AA"
        ),
        "setup_mode": args.setup_mode,
        "setup_commands": list(SETUP_MODES[args.setup_mode]),
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
        **{key: f"20:{value:04X}" for key, value in addresses.items()},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(image):,} bytes to {args.output.resolve()}")
    print(f"wrote {manifest_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
