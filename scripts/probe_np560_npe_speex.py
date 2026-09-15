#!/usr/bin/env python3
"""Test fixed 21-byte NPE records against the reference Speex decoder.

This is a falsification probe, not a format declaration.  A clean decode is
only evidence that a section is Speex-compatible; decode failures help avoid
labelling high-entropy records as audio from size alone.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import math
from pathlib import Path

try:
    from analyse_np560_npe import _parse_sections
except ModuleNotFoundError:
    from .analyse_np560_npe import _parse_sections


class SpeexBits(ctypes.Structure):
    _fields_ = [
        ("chars", ctypes.c_void_p),
        ("nb_bits", ctypes.c_int),
        ("char_ptr", ctypes.c_int),
        ("bit_ptr", ctypes.c_int),
        ("owner", ctypes.c_int),
        ("overflow", ctypes.c_int),
        ("buf_size", ctypes.c_int),
        ("reserved1", ctypes.c_int),
        ("reserved2", ctypes.c_void_p),
    ]


def framed_section(blob: bytes, index: int) -> tuple[int, list[bytes], bytes]:
    sections = _parse_sections(blob)
    if not 0 <= index < len(sections):
        raise ValueError(f"section index {index} is outside 0..{len(sections)-1}")
    offset, size = sections[index]
    section = blob[offset:offset + size]
    if len(section) < 4 or section[:2] != b"\x20\x0d":
        raise ValueError(f"section {index} does not start with 20 0D")
    count = int.from_bytes(section[2:4], "big")
    records_end = 4 + count * 21
    if records_end > len(section) or len(section) - records_end > 1:
        raise ValueError(
            f"section {index} is not count*21 plus at most one pad byte"
        )
    records = [
        section[4 + record * 21:4 + (record + 1) * 21]
        for record in range(count)
    ]
    return count, records, section[records_end:]


class SpeexDecoder:
    def __init__(self, mode_name: str) -> None:
        library_name = ctypes.util.find_library("speex")
        if not library_name:
            raise RuntimeError("libspeex is not installed")
        self.lib = ctypes.CDLL(library_name)
        mode = ctypes.c_byte.in_dll(self.lib, f"speex_{mode_name}_mode")

        self.lib.speex_decoder_init.argtypes = [ctypes.c_void_p]
        self.lib.speex_decoder_init.restype = ctypes.c_void_p
        self.lib.speex_decoder_destroy.argtypes = [ctypes.c_void_p]
        self.lib.speex_decoder_ctl.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
        ]
        self.lib.speex_bits_init.argtypes = [ctypes.POINTER(SpeexBits)]
        self.lib.speex_bits_destroy.argtypes = [ctypes.POINTER(SpeexBits)]
        self.lib.speex_bits_reset.argtypes = [ctypes.POINTER(SpeexBits)]
        self.lib.speex_bits_read_from.argtypes = [
            ctypes.POINTER(SpeexBits), ctypes.c_void_p, ctypes.c_int,
        ]
        self.lib.speex_bits_remaining.argtypes = [ctypes.POINTER(SpeexBits)]
        self.lib.speex_bits_remaining.restype = ctypes.c_int
        self.lib.speex_decode_int.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(SpeexBits),
            ctypes.POINTER(ctypes.c_int16),
        ]
        self.lib.speex_decode_int.restype = ctypes.c_int

        self.state = self.lib.speex_decoder_init(ctypes.byref(mode))
        if not self.state:
            raise RuntimeError(f"could not initialize Speex {mode_name} decoder")
        frame_size = ctypes.c_int()
        if self.lib.speex_decoder_ctl(
            self.state, 3, ctypes.byref(frame_size)
        ) != 0:
            self.close()
            raise RuntimeError("SPEEX_GET_FRAME_SIZE failed")
        self.frame_size = frame_size.value
        self.bits = SpeexBits()
        self.lib.speex_bits_init(ctypes.byref(self.bits))

    def close(self) -> None:
        if getattr(self, "state", None):
            if hasattr(self, "bits"):
                self.lib.speex_bits_destroy(ctypes.byref(self.bits))
            self.lib.speex_decoder_destroy(self.state)
            self.state = None

    def decode(self, packet: bytes) -> tuple[int, int, list[int]]:
        self.lib.speex_bits_reset(ctypes.byref(self.bits))
        buffer = ctypes.create_string_buffer(packet)
        self.lib.speex_bits_read_from(
            ctypes.byref(self.bits), buffer, len(packet)
        )
        output = (ctypes.c_int16 * self.frame_size)()
        result = self.lib.speex_decode_int(
            self.state, ctypes.byref(self.bits), output
        )
        remaining = self.lib.speex_bits_remaining(ctypes.byref(self.bits))
        return result, remaining, list(output)


def probe(records: list[bytes], mode: str, variant: str) -> dict[str, object]:
    decoder = SpeexDecoder(mode)
    return_codes: dict[int, int] = {}
    remaining: list[int] = []
    samples: list[int] = []
    try:
        for record in records:
            packet = {
                "all21": record,
                "first20": record[:20],
                "last20": record[1:],
            }[variant]
            result, bits, decoded = decoder.decode(packet)
            return_codes[result] = return_codes.get(result, 0) + 1
            remaining.append(bits)
            if result == 0:
                samples.extend(decoded)
    finally:
        frame_size = decoder.frame_size
        decoder.close()
    rms = (
        math.sqrt(sum(sample * sample for sample in samples) / len(samples))
        if samples else 0.0
    )
    return {
        "mode": mode,
        "variant": variant,
        "frame_size": frame_size,
        "return_codes": {
            str(code): count for code, count in sorted(return_codes.items())
        },
        "success_ratio": (
            return_codes.get(0, 0) / len(records) if records else 0.0
        ),
        "remaining_bits_min": min(remaining) if remaining else None,
        "remaining_bits_max": max(remaining) if remaining else None,
        "decoded_samples": len(samples),
        "sample_min": min(samples) if samples else None,
        "sample_max": max(samples) if samples else None,
        "sample_rms": round(rms, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("npe", type=Path)
    parser.add_argument("--section", type=int, default=16)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be nonnegative")

    blob = args.npe.read_bytes()
    count, records, padding = framed_section(blob, args.section)
    if args.limit:
        records = records[:args.limit]
    results = [
        probe(records, mode, variant)
        for mode in ("nb", "wb", "uwb")
        for variant in ("all21", "first20", "last20")
    ]
    report = {
        "schema": "np560-npe-speex-falsification-v1",
        "claim": "decoder compatibility probe only",
        "npe": str(args.npe),
        "section": args.section,
        "declared_records": count,
        "tested_records": len(records),
        "record_bytes": 21,
        "padding_hex": padding.hex(),
        "results": results,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
