#!/usr/bin/env python3
"""Build a one-shot NP560 firmware which provisions ``lirt.nwf`` in guest.

The default initializer trigger at runtime ``2D:7F66`` is retained for
reproducibility.  A late trigger is also available at the first main-resource
load (source ``3F:5582``, runtime ``22:5582``).  The latter runs after the
initializer has released its five temporary file objects, avoiding the exact
``FFF6`` pool-exhaustion failure observed when provisioning is attempted from
the earlier site.  Both modes patch a normal guest SCALL into a small shim in
an erased part of the 4 MiB PRG.  The shim copies the requested path into its
own internal-SRAM frame and uses the exact resident stat/open/write/close
implementations.  Before returning it calls the original target; for the late
site it also forwards the two original far-pointer arguments.  The near path
copy matters because the resident open entry accepts an internal-data pointer.

The external data bus maps 50:0000 and above to writable RAM, not to the PRG's
immutable code/NOR bytes.  Consequently an NWF blob stored at 5E:0000 is not a
valid write source.  This builder instead compiles the candidate into guest
instructions in the large erased 58:B140..5F:FFFF NOR window.  Those
instructions materialise 0x100-byte chunks in internal SRAM and call the real
resident writer for every chunk.  No host-side data injection is involved.

No host filesystem service or SCALL interception is involved.  This image is
intended only to produce an isolated NAND checkpoint; normal boot should use
the original NP560.PRG with that checkpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from . import build_np560_minimal_nwf as nwf_format
except ImportError:  # Direct script execution.
    import build_np560_minimal_nwf as nwf_format


PROGRAM_BASE = 0x200000
PROGRAM_SIZE = 0x400000

PROVISION_TRIGGER_CALL = 0x4A7F66
PROVISION_TRIGGER_CALL_WORDS = (0xBD33, 0x6F30)
LATE_PROVISION_TRIGGER_CALL = 0x3F5582
LATE_PROVISION_TRIGGER_CALL_WORDS = (0xBD32, 0x512C)
PROVISION_WRAPPER = 0x58B140
PROVISION_WRITER = 0x590000
PROVISION_CHUNK_BYTES = 0x100
MAX_PROVISION_DATA_SIZE = 0x10000
PROVISION_WRITER_LINK_WORDS = 0x80
PROVISION_BUFFER_FP_OFFSET = -PROVISION_CHUNK_BYTES

RESOURCE_STAT = 0x30C99E
RESIDENT_FILE_OPEN = 0x1F1F1A
RESIDENT_FILE_WRITE = 0x17E3EE
RESIDENT_FILE_CLOSE = 0x24EAEC
ORIGINAL_TRIGGER_TARGET = 0x336F30
LATE_ORIGINAL_TRIGGER_TARGET = 0x32512C

TRIGGERS = {
    "initializer": (
        PROVISION_TRIGGER_CALL,
        PROVISION_TRIGGER_CALL_WORDS,
        ORIGINAL_TRIGGER_TARGET,
        0,
    ),
    "main-resource": (
        LATE_PROVISION_TRIGGER_CALL,
        LATE_PROVISION_TRIGGER_CALL_WORDS,
        LATE_ORIGINAL_TRIGGER_TARGET,
        2,
    ),
}

# Runtime 52:4F36, captured at the resource-stat call, decodes as
# ``0:\\多媒体\\lirt.nwf`` in GB18030.  Store it in a near stack buffer before
# calling RESIDENT_FILE_OPEN.  A path override supports controlled root-path
# experiments without editing generated opcodes by hand.
DEFAULT_GUEST_PATH = r"0:\多媒体\lirt.nwf"
PROVISION_PATH_BYTES = 20
PROVISION_PATH_FP_OFFSET = -0x18


def encode_guest_path_words(path: str) -> tuple[int, ...]:
    encoded = path.encode("gb18030") + b"\0"
    if len(encoded) > PROVISION_PATH_BYTES:
        raise ValueError(
            f"guest path needs {len(encoded)} bytes including NUL; "
            f"limit is {PROVISION_PATH_BYTES}"
        )
    encoded = encoded.ljust(PROVISION_PATH_BYTES, b"\0")
    return tuple(
        int.from_bytes(encoded[offset:offset + 2], "big")
        for offset in range(0, len(encoded), 2)
    )


PROVISION_PATH_WORDS = encode_guest_path_words(DEFAULT_GUEST_PATH)


def file_offset(address: int) -> int:
    offset = address - PROGRAM_BASE
    if not 0 <= offset < PROGRAM_SIZE:
        raise ValueError(f"program address {address:06X} is outside PRG")
    return offset


def read_words(image: bytes, address: int, count: int) -> tuple[int, ...]:
    offset = file_offset(address)
    return tuple(
        int.from_bytes(image[offset + index * 2:offset + index * 2 + 2],
                       "little")
        for index in range(count)
    )


def put_words(image: bytearray, address: int, words: list[int]) -> None:
    offset = file_offset(address)
    data = b"".join(word.to_bytes(2, "little") for word in words)
    image[offset:offset + len(data)] = data


def guest_data_storage(data: bytes) -> bytes:
    """Encode logical guest bytes for the DMCU's swapped external byte lanes."""
    if len(data) & 1:
        raise ValueError("guest data fixture must contain complete words")
    stored = bytearray(data)
    for offset in range(0, len(stored), 2):
        stored[offset], stored[offset + 1] = stored[offset + 1], stored[offset]
    return bytes(stored)


def encode_candidate_words(data: bytes) -> tuple[int, ...]:
    """Encode logical candidate bytes as DMCU immediate 16-bit words."""
    if len(data) & 1:
        raise ValueError("provision candidate must contain complete words")
    return tuple(
        int.from_bytes(data[offset:offset + 2], "big")
        for offset in range(0, len(data), 2)
    )


def delta_materialized_word_count(data: bytes) -> int:
    """Count words that must change in the persistent chunk buffer."""
    if len(data) % PROVISION_CHUNK_BYTES:
        raise ValueError("candidate must contain complete provision chunks")
    previous: bytes | None = None
    count = 0
    for chunk_start in range(0, len(data), PROVISION_CHUNK_BYTES):
        chunk = data[chunk_start:chunk_start + PROVISION_CHUNK_BYTES]
        for offset in range(0, PROVISION_CHUNK_BYTES, 2):
            if previous is None or chunk[offset:offset + 2] != previous[
                    offset:offset + 2]:
                count += 1
        previous = chunk
    return count


class WrapperAssembler:
    def __init__(self, base_address: int) -> None:
        self.base_address = base_address
        self.words: list[int] = []
        self.labels: dict[str, int] = {}
        self.patches: list[tuple[int, str]] = []

    def emit(self, *words: int) -> None:
        self.words.extend(words)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"duplicate label {name}")
        self.labels[name] = self.base_address + len(self.words) * 2

    def ajmp(self, condition: int, target: str) -> None:
        self.emit(0xAC00 | condition, 0)
        self.patches.append((len(self.words) - 1, target))

    def finish(self) -> list[int]:
        for index, name in self.patches:
            if name not in self.labels:
                raise ValueError(f"undefined label {name}")
            target = self.labels[name]
            if target >> 16 != self.base_address >> 16:
                raise ValueError(f"AJMP label {name} crosses a segment")
            self.words[index] = target & 0xFFFF
        return self.words


def provision_wrapper_words(
        path_words: tuple[int, ...] = PROVISION_PATH_WORDS,
        *,
        original_target: int = ORIGINAL_TRIGGER_TARGET,
        forward_far_args: int = 0,
) -> list[int]:
    if len(path_words) != PROVISION_PATH_BYTES // 2:
        raise ValueError("provision path must fill the fixed near buffer")
    asm = WrapperAssembler(PROVISION_WRAPPER)
    asm.emit(0x2E0C)                    # LINK #12: path plus saved FILE *

    # RESIDENT_FILE_OPEN consumes a near internal-data pointer.  Materialise
    # the exact path seen by the resource reader at FP-0x18 instead of passing
    # its original 52:xxxx far pointer through unchanged.
    for index, word in enumerate(path_words):
        asm.emit(
            0x68F0, word,               # R0 = logical path word
            0x6A0B,                     # [FP+offset] = R0
            (PROVISION_PATH_FP_OFFSET + index * 2) & 0xFFFF,
        )

    # Keep the original stat call as a read-only observation, but do not use
    # its nonzero result as a completion flag.  The input checkpoint contains
    # a deliberately seeded empty root record which is discoverable by stat
    # before it has any file payload.
    asm.emit(
        0x780B, 0x0006,                 # path high
        0x781B, 0x0008,                 # path low
        0x58F1, 0x58F0,
        0xBD30, 0xC99E,                 # exact generic resource stat
        0x50F4,
    )

    asm.emit(
        # Resident fopen mode 2 only accepts an already catalogued object and
        # reports FFF9 when lookup returns zero.  Mode 0 is its evidenced
        # create-if-missing arm: it validates the parent record and proceeds
        # through 23:7584/30:6D9E to allocate and commit a new object.
        0x4800, 0x58F0,
        0x081B,                         # R1 = FP
        0x70F1, PROVISION_PATH_FP_OFFSET & 0xFFFF,
        0x4800,                         # R0 = near segment 0
        0x58F1, 0x58F0,
        0xBD1F, 0x1F1A,
        0x50F6,
        0x6A0B, 0xFFFC,                 # save FILE * high
        0x6A1B, 0xFFFE,                 # save FILE * low
        0x5210, 0x5300,                 # compare full far pointer with zero
    )
    asm.ajmp(0x01, "done")             # creation failed: return null

    asm.emit(
        0x780B, 0xFFFC,
        0x781B, 0xFFFE,
        0x58F1, 0x58F0,
        0xBD00 | (PROVISION_WRITER >> 16), PROVISION_WRITER & 0xFFFF,
        0x50F4,
        0x780B, 0xFFFC,
        0x781B, 0xFFFE,
        0x58F1, 0x58F0,
        0xBD24, 0xEAEC,                 # exact resident close/commit
        0x50F4,
        0x780B, 0x0006,                 # retry original stat after commit
        0x781B, 0x0008,
        0x58F1, 0x58F0,
        0xBD30, 0xC99E,
        0x50F4,
    )

    asm.label("done")
    # A nested callee sees the most recently pushed original far argument at
    # wrapper FP+6.  Re-push arguments in their original caller order before
    # invoking a replaced call which accepts arguments.
    for index in reversed(range(forward_far_args)):
        offset = 0x0006 + index * 4
        asm.emit(
            0x780B, offset,              # far pointer high
            0x781B, offset + 2,          # far pointer low
            0x58F1, 0x58F0,
        )
    asm.emit(
        0xBD00 | (original_target >> 16),
        original_target & 0xFFFF,
    )
    if forward_far_args:
        asm.emit(0x50F0 | (forward_far_args * 4))
    asm.emit(0x2F00, 0xC620)             # preserve original call; return
    return asm.finish()


def provision_writer_words(candidate: bytes) -> list[int]:
    """Compile *candidate* into a guest-only chunked FILE writer.

    The helper receives FILE * as its sole far-pointer argument.  Every chunk
    is materialised in the helper's internal-SRAM frame before using the exact
    three-far-argument ABI witnessed at eleven original 17:E3EE call sites:
    length, source buffer, FILE pointer, followed by 12-byte cleanup.
    """
    if not candidate or len(candidate) % PROVISION_CHUNK_BYTES:
        raise ValueError(
            "provision candidate must contain complete non-empty chunks"
        )
    if len(candidate) > MAX_PROVISION_DATA_SIZE:
        raise ValueError(
            f"provision candidate exceeds {MAX_PROVISION_DATA_SIZE} bytes"
        )
    if PROVISION_CHUNK_BYTES & 1:
        raise ValueError("provision chunk must contain complete words")

    # The minimal NWF contains only a few distinct chunks.  Initialise
    # every word for chunk zero, then retain the internal-SRAM buffer and emit
    # stores only for words which differ from the preceding chunk.  This is a
    # build-time encoding optimisation: the guest still performs every native
    # 0x100-byte write, but its generated code no longer crosses into
    # the mutable 5C:C000 application-overlay window.
    words: list[int] = [0x2E00 | PROVISION_WRITER_LINK_WORDS]
    previous_chunk: bytes | None = None
    for chunk_start in range(0, len(candidate), PROVISION_CHUNK_BYTES):
        chunk = candidate[chunk_start:chunk_start + PROVISION_CHUNK_BYTES]
        for index, value in enumerate(encode_candidate_words(chunk)):
            byte_offset = index * 2
            if (previous_chunk is not None and
                    chunk[byte_offset:byte_offset + 2] ==
                    previous_chunk[byte_offset:byte_offset + 2]):
                continue
            frame_offset = PROVISION_BUFFER_FP_OFFSET + index * 2
            words.extend((
                0x68F0, value,              # R0 = logical candidate word
                0x6A0B, frame_offset & 0xFFFF,
            ))

        words.extend((
            0x68F1, PROVISION_CHUNK_BYTES,  # 32-bit length = 0x00000100
            0x4800,
            0x58F1, 0x58F0,
            0x081B,                        # near SRAM source buffer
            0x70F1, PROVISION_BUFFER_FP_OFFSET & 0xFFFF,
            0x4800,
            0x58F1, 0x58F0,
            0x780B, 0x0006,                # FILE * high/low
            0x781B, 0x0008,
            0x58F1, 0x58F0,
            0xBD17, 0xE3EE,                # exact resident file-write
            0x50FC,                        # three far args = 12 bytes
        ))
        previous_chunk = chunk
    words.extend((0x2F00, 0xC620))          # UNLINK; RETS
    return words


def require_erased(image: bytes, address: int, size: int) -> None:
    offset = file_offset(address)
    region = image[offset:offset + size]
    if len(region) != size or any(value != 0xFF for value in region):
        raise ValueError(
            f"provision region {address:06X}+{size:X} is not erased"
        )


def require_words(
        image: bytes,
        address: int,
        expected: list[int],
        description: str,
) -> None:
    actual = read_words(image, address, len(expected))
    if actual != tuple(expected):
        mismatch = next(
            (
                index for index, (left, right) in
                enumerate(zip(actual, expected)) if left != right
            ),
            min(len(actual), len(expected)),
        )
        raise ValueError(
            f"existing {description} changed at "
            f"{address + mismatch * 2:06X}: expected exact prior payload"
        )


def build_firmware(
        program: bytes,
        candidate: bytes,
        guest_path: str = DEFAULT_GUEST_PATH,
        trigger: str = "initializer",
        rearm_existing_path: str | None = None,
        rearm_existing_trigger: str | None = None,
        rearm_existing_candidate: bytes | None = None,
) -> tuple[bytes, dict]:
    if len(program) != PROGRAM_SIZE:
        raise ValueError(
            f"NP560 PRG must be {PROGRAM_SIZE} bytes, got {len(program)}"
        )
    report = nwf_format.inspect_candidate(candidate)
    if not report["valid_offline_candidate"]:
        raise ValueError(f"invalid NWF candidate: {report['errors']}")
    if not candidate or len(candidate) % PROVISION_CHUNK_BYTES:
        raise ValueError(
            "provision candidate must contain complete non-empty chunks"
        )
    if len(candidate) > MAX_PROVISION_DATA_SIZE:
        raise ValueError(
            f"provision candidate exceeds {MAX_PROVISION_DATA_SIZE} bytes"
        )
    if trigger not in TRIGGERS:
        raise ValueError(f"unknown provision trigger: {trigger}")
    if rearm_existing_trigger is not None and rearm_existing_path is None:
        raise ValueError(
            "rearm_existing_trigger requires rearm_existing_path"
        )
    if (rearm_existing_trigger is not None and
            rearm_existing_trigger not in TRIGGERS):
        raise ValueError(
            f"unknown existing provision trigger: {rearm_existing_trigger}"
        )
    if rearm_existing_candidate is not None and rearm_existing_path is None:
        raise ValueError(
            "rearm_existing_candidate requires rearm_existing_path"
        )
    trigger_call, trigger_words, original_target, forward_far_args = (
        TRIGGERS[trigger]
    )
    actual_call = read_words(program, trigger_call, 2)
    if actual_call != trigger_words:
        raise ValueError(
            f"provision trigger signature changed: {actual_call!r}"
        )

    path_words = encode_guest_path_words(guest_path)
    wrapper = provision_wrapper_words(
        path_words,
        original_target=original_target,
        forward_far_args=forward_far_args,
    )
    writer = provision_writer_words(candidate)
    if rearm_existing_path is None:
        require_erased(program, PROVISION_WRAPPER, len(wrapper) * 2)
        require_erased(program, PROVISION_WRITER, len(writer) * 2)
    else:
        previous_trigger = rearm_existing_trigger or trigger
        (_previous_call, _previous_words, previous_target,
         previous_forward_far_args) = TRIGGERS[previous_trigger]
        previous_wrapper = provision_wrapper_words(
            encode_guest_path_words(rearm_existing_path),
            original_target=previous_target,
            forward_far_args=previous_forward_far_args,
        )
        require_words(
            program, PROVISION_WRAPPER, previous_wrapper,
            "provision wrapper",
        )
        previous_candidate = rearm_existing_candidate or candidate
        previous_writer = provision_writer_words(previous_candidate)
        require_words(
            program, PROVISION_WRITER, previous_writer,
            "provision writer",
        )
        if len(writer) > len(previous_writer):
            require_erased(
                program,
                PROVISION_WRITER + len(previous_writer) * 2,
                (len(writer) - len(previous_writer)) * 2,
            )

    image = bytearray(program)
    put_words(
        image,
        trigger_call,
        [0xBD00 | (PROVISION_WRAPPER >> 16), PROVISION_WRAPPER & 0xFFFF],
    )
    put_words(image, PROVISION_WRAPPER, wrapper)
    put_words(image, PROVISION_WRITER, writer)

    manifest = {
        "purpose": "guest-native one-shot lirt.nwf provisioning",
        "host_filesystem_service": False,
        "scall_interception": False,
        "input_program_sha256": hashlib.sha256(program).hexdigest(),
        "output_program_sha256": hashlib.sha256(image).hexdigest(),
        "nwf_sha256": hashlib.sha256(candidate).hexdigest(),
        "provision_trigger": trigger,
        "provision_trigger_call_source":
            f"{trigger_call >> 16:02X}:"
            f"{trigger_call & 0xFFFF:04X}",
        "provision_trigger_call_runtime":
            f"{(trigger_call >> 16) - 0x1D:02X}:"
            f"{trigger_call & 0xFFFF:04X}",
        "provision_trigger_original_target":
            f"{original_target >> 16:02X}:"
            f"{original_target & 0xFFFF:04X}",
        "provision_trigger_forwarded_far_args": forward_far_args,
        "resource_stat_target": "30:C99E",
        "resident_open_path": "near copy at FP-0018",
        "guest_path": guest_path,
        "resident_open_path_words": [f"{word:04X}" for word in path_words],
        "rearmed_existing_payload": rearm_existing_path is not None,
        "previous_guest_path": rearm_existing_path,
        "previous_provision_trigger": (
            (rearm_existing_trigger or trigger)
            if rearm_existing_path is not None else None
        ),
        "previous_nwf_sha256": (
            hashlib.sha256(rearm_existing_candidate).hexdigest()
            if rearm_existing_candidate is not None else None
        ),
        "overlay_copy": "4B:BE2E..4B:BF99 -> 2E:BE2E..2E:BF99",
        "wrapper": f"{PROVISION_WRAPPER >> 16:02X}:"
                   f"{PROVISION_WRAPPER & 0xFFFF:04X}",
        "wrapper_bytes": len(wrapper) * 2,
        "guest_data": "compiled immediate words -> internal SRAM chunks",
        "guest_data_bytes": len(candidate),
        "writer": f"{PROVISION_WRITER >> 16:02X}:"
                  f"{PROVISION_WRITER & 0xFFFF:04X}",
        "writer_bytes": len(writer) * 2,
        "writer_chunks": len(candidate) // PROVISION_CHUNK_BYTES,
        "writer_chunk_bytes": PROVISION_CHUNK_BYTES,
        "writer_materialization": "first chunk plus word deltas",
        "writer_materialized_words": delta_materialized_word_count(candidate),
        "writer_full_materialization_words": len(candidate) // 2,
        "writer_unique_chunks": len({
            candidate[offset:offset + PROVISION_CHUNK_BYTES]
            for offset in range(0, len(candidate), PROVISION_CHUNK_BYTES)
        }),
        "guest_calls": {
            "resource_stat": "30:C99E before and after provisioning",
            "file_open": "1F:1F1A mode=0 (create-if-missing)",
            "file_write": (
                f"17:E3EE {len(candidate) // PROVISION_CHUNK_BYTES} "
                "chunks x 0x100 bytes"
            ),
            "file_close": "24:EAEC",
        },
    }
    return bytes(image), manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("program", type=Path)
    parser.add_argument("nwf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--guest-path", default=DEFAULT_GUEST_PATH)
    parser.add_argument(
        "--trigger", choices=tuple(TRIGGERS), default="initializer",
        help="guest call site to replace with the one-shot provision shim",
    )
    parser.add_argument(
        "--rearm-existing-path",
        help=(
            "replace an exact inactive payload previously built for this "
            "guest path instead of requiring erased injection regions"
        ),
    )
    parser.add_argument(
        "--rearm-existing-trigger",
        choices=tuple(TRIGGERS),
        help=(
            "trigger ABI used by the exact inactive payload; defaults to "
            "the newly selected trigger"
        ),
    )
    parser.add_argument(
        "--rearm-existing-nwf",
        type=Path,
        help=(
            "candidate compiled into the exact inactive writer being "
            "replaced; defaults to the new candidate"
        ),
    )
    args = parser.parse_args()

    firmware, manifest = build_firmware(
        args.program.read_bytes(), args.nwf.read_bytes(), args.guest_path,
        args.trigger, args.rearm_existing_path, args.rearm_existing_trigger,
        (args.rearm_existing_nwf.read_bytes()
         if args.rearm_existing_nwf else None),
    )
    args.output.write_bytes(firmware)
    manifest_path = args.manifest or args.output.with_suffix(".json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
