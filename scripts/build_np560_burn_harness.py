#!/usr/bin/env python3
"""Build a minimal NP560.PRG that enters the real updater command dispatcher.

The burner normally receives its command block from the unavailable resident
loader.  This guest-side harness writes that block through ordinary DMCU
instructions and then jumps to the unmodified burner at 50:6000.  It is a
reverse-engineering fixture, not a host-side ROM or storage service.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROGRAM_SIZE = 0x400000
DS0 = 0x10
BURNER_GLOBAL_SEGMENT = 0x00A0


def parse_word(value: str) -> tuple[int, int]:
    address_text, separator, word_text = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("word must use ADDRESS=VALUE")
    try:
        address = int(address_text, 0)
        word = int(word_text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("word address and value must be integers") from exc
    if not 0 <= address <= 0x7FFE or address & 1:
        raise argparse.ArgumentTypeError("word address must be even and below 0x8000")
    if not 0 <= word <= 0xFFFF:
        raise argparse.ArgumentTypeError("word value must fit in 16 bits")
    return address, word


def parse_step_word(value: str) -> tuple[int, int, int]:
    step_text, separator, assignment_text = value.partition(":")
    if not separator:
        raise argparse.ArgumentTypeError(
            "step word must use STEP:ADDRESS=VALUE"
        )
    try:
        step = int(step_text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("step must be an integer") from exc
    if step < 0:
        raise argparse.ArgumentTypeError("step must not be negative")
    address, word = parse_word(assignment_text)
    return step, address, word


def parse_far_entry(value: str) -> tuple[int, int]:
    segment_text, separator, offset_text = value.partition(":")
    if not separator:
        raise argparse.ArgumentTypeError("far entry must use SEGMENT:OFFSET")
    try:
        segment = int(segment_text, 0)
        offset = int(offset_text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "far entry segment and offset must be integers"
        ) from exc
    if not 0 <= segment <= 0xFF or not 0 <= offset <= 0xFFFF:
        raise argparse.ArgumentTypeError("far entry is outside the 24-bit code space")
    return segment, offset


def parse_embed(value: str) -> tuple[Path, int, int | None]:
    source_text, separator, address_spec = value.rpartition("@")
    if not separator or not source_text:
        raise argparse.ArgumentTypeError("embed must use SOURCE@ADDRESS")
    address_text, length_separator, length_text = address_spec.partition(":")
    try:
        address = int(address_text, 0)
        length = int(length_text, 0) if length_separator else None
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "embed address and length must be integers"
        ) from exc
    if not 0 <= address < PROGRAM_SIZE:
        raise argparse.ArgumentTypeError("embed address is outside the PRG image")
    if length is not None and length < 0:
        raise argparse.ArgumentTypeError("embed length must not be negative")
    return Path(source_text), address, length


def _store_word(words: list[int], address: int, value: int) -> None:
    words.extend(
        [
            0x68F0,
            value,       # MOV R0, #value (SFR alias encoding)
            0xA8F0,
            address,     # MOV [address], R0
        ]
    )


def build_program(
    command: int,
    extra_words: list[tuple[int, int]],
    next_commands: list[int] | None = None,
    step_words: list[tuple[int, int, int]] | None = None,
    tail_calls: list[tuple[int, int]] | None = None,
    embeds: list[tuple[int, bytes]] | None = None,
) -> bytes:
    commands = [command, *(next_commands or [])]
    if any(not 1 <= item <= 27 for item in commands):
        raise ValueError("burner command must be in the observed range 1..27")
    by_step: dict[int, list[tuple[int, int]]] = {}
    for step, address, value in step_words or []:
        if step >= len(commands):
            raise ValueError(
                f"step word selects step {step}, but the sequence has "
                f"{len(commands)} step(s)"
            )
        by_step.setdefault(step, []).append((address, value))
    by_step.setdefault(0, []).extend(extra_words)

    words = [0x6810, BURNER_GLOBAL_SEGMENT]  # MOV REG[DS0], #0x00A0
    _store_word(words, 0x0008, command)
    for address, value in by_step.get(0, []):
        _store_word(words, address, value)
    words.extend([0xBD50, 0x6000])           # SCALL 50:6000
    for step, next_command in enumerate(commands[1:], start=1):
        _store_word(words, 0x0008, next_command)
        for address, value in by_step.get(step, []):
            _store_word(words, address, value)
        words.extend([0xBD50, 0x7566])        # SCALL command dispatcher
    for segment, offset in tail_calls or []:
        words.extend([0xBD00 | segment, offset])
    words.append(0xD0FF)                     # RJMP ALWAYS, self

    image = bytearray(PROGRAM_SIZE)
    for index, word in enumerate(words):
        image[index * 2 : index * 2 + 2] = word.to_bytes(2, "little")
    code_size = len(words) * 2
    for address, payload in embeds or []:
        if address < code_size:
            raise ValueError(
                f"embedded payload at 0x{address:X} overlaps the "
                f"0x{code_size:X}-byte harness"
            )
        if address + len(payload) > PROGRAM_SIZE:
            raise ValueError("embedded payload extends past the PRG image")
        image[address:address + len(payload)] = payload
    return bytes(image)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", type=lambda value: int(value, 0), required=True)
    parser.add_argument(
        "--next-command", type=lambda value: int(value, 0), action="append",
        default=[], help="dispatch another command after the previous one returns",
    )
    parser.add_argument("--word", type=parse_word, action="append", default=[])
    parser.add_argument(
        "--step-word", type=parse_step_word, action="append", default=[],
        help=("write ADDRESS=VALUE immediately before the zero-based command "
              "STEP; syntax STEP:ADDRESS=VALUE"),
    )
    parser.add_argument(
        "--tail-call", type=parse_far_entry, action="append", default=[],
        help="SCALL SEGMENT:OFFSET after the command sequence returns",
    )
    parser.add_argument(
        "--embed", type=parse_embed, action="append", default=[],
        help="embed raw data using SOURCE@ADDRESS[:LENGTH]",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    try:
        embedded_payloads = [
            (address, source.read_bytes()[:length])
            for source, address, length in args.embed
        ]
        image = build_program(
            args.command, args.word, args.next_command, args.step_word,
            args.tail_call, embedded_payloads,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    args.output.write_bytes(image)
    manifest_path = args.manifest or args.output.with_suffix(".json")
    manifest = {
        "format": "np560-burn-command-harness-v1",
        "warning": "Reverse-engineering fixture; not product firmware.",
        "command": args.command,
        "next_commands": args.next_command,
        "global_segment": f"0x{BURNER_GLOBAL_SEGMENT:04X}",
        "extra_words": [
            {"address": f"0x{address:04X}", "value": f"0x{value:04X}"}
            for address, value in args.word
        ],
        "step_words": [
            {
                "step": step,
                "address": f"0x{address:04X}",
                "value": f"0x{value:04X}",
            }
            for step, address, value in args.step_word
        ],
        "tail_calls": [
            f"{segment:02X}:{offset:04X}"
            for segment, offset in args.tail_call
        ],
        "embedded_payloads": [
            {
                "source": str(source),
                "address": f"0x{address:06X}",
                "bytes": len(payload),
            }
            for (source, address, length), (_, payload) in zip(
                args.embed, embedded_payloads
            )
        ],
        "entry": "20:0000",
        "initial_destination": "50:6000",
        "subsequent_destination": "50:7566",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(image):,} bytes to {args.output.resolve()}")
    print(f"wrote {manifest_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
