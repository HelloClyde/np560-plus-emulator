#!/usr/bin/env python3
"""Emulate the archived CYBIT mv_sp.dll on NPE frame candidates, without native DLL execution.

This probe is deliberately isolated from QEMU.  Equal frame sizes and a
nonzero waveform are not proof of NP560 codec compatibility; inspect output
and original bit-field behavior before using any decoder in the emulator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import wave

import pefile
from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP

from analyse_np560_npe import _parse_sections


BASE = 0x10000000
HEAP = 0x20000000
STACK = 0x30000000
IO = 0x40000000
SENTINEL = 0x50000000
SP_INIT = BASE + 0x1FC0
SP_DECODE = BASE + 0x1000
SP_ALLOC = BASE + 0x2120
MAX_INSTRUCTIONS = 20000000
EXPECTED_DLL_SHA256 = "7204d31972243812926fb589a7a0622eee73a91ac7a184627e04978559e8af01"
BIT_REVERSE = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))


def candidate_bytes(payload: bytes, transform: str, bit_offset: int) -> bytes:
    if transform in ("swap16", "swap16-bitrev"):
        swapped = bytearray(payload)
        for i in range(0, len(swapped) - 1, 2):
            swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
        payload = bytes(swapped)
    if transform in ("bitrev", "swap16-bitrev"):
        payload = payload.translate(BIT_REVERSE)
    if bit_offset:
        payload = bytes(((a << bit_offset) & 255) |
                        (b >> (8 - bit_offset))
                        for a, b in zip(payload, payload[1:]))
    return payload


def encoded_frames(encoded: bytes, frame_bytes: int, limit: int):
    """Keep compressed input separate from PCM output across frame calls."""
    if frame_bytes <= 0 or limit < 0:
        raise ValueError("invalid compressed-frame bounds")
    for index in range(min(limit, len(encoded) // frame_bytes)):
        start = index * frame_bytes
        yield index, encoded[start:start + frame_bytes]


def decode_fresh_context(decoder_factory, mode: int, frame: bytes) -> bytes:
    """Decode one frame after a new init, as a statefulness control only."""
    decoder = decoder_factory()
    context, frame_bits = decoder.init(mode)
    if not context or frame_bits != len(frame) * 8:
        raise ValueError("fresh decoder returned an unexpected frame specification")
    samples, pcm = decoder.decode(frame, context)
    if samples != 160 or len(pcm) != samples * 2:
        raise ValueError("fresh decoder returned an unexpected PCM frame")
    return pcm


class IsolatedDecoder:
    def __init__(self, dll: bytes):
        if hashlib.sha256(dll).hexdigest() != EXPECTED_DLL_SHA256:
            raise ValueError("mv_sp.dll SHA-256 differs from the reviewed archive")
        pe = pefile.PE(data=dll)
        if pe.OPTIONAL_HEADER.ImageBase != BASE:
            raise ValueError("unexpected DLL image base")
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.uc.mem_map(BASE, 0x10000)
        self.uc.mem_write(BASE, pe.get_memory_mapped_image())
        self.uc.mem_map(HEAP, 0x200000)
        self.uc.mem_map(STACK, 0x100000)
        self.uc.mem_map(IO, 0x100000)
        self.uc.mem_map(SENTINEL, 0x1000)
        self.uc.mem_write(SENTINEL, b"\x90")
        self.heap_next = HEAP + 0x1000
        self.returned = False
        self.uc.hook_add(UC_HOOK_CODE, self._allocation, begin=SP_ALLOC, end=SP_ALLOC)
        self.uc.hook_add(UC_HOOK_CODE, self._return, begin=SENTINEL, end=SENTINEL)

    def _allocation(self, uc, _address, _size, _user):
        esp = uc.reg_read(UC_X86_REG_ESP)
        ret, length = struct.unpack("<II", uc.mem_read(esp, 8))
        allocated = self.heap_next
        self.heap_next += (length + 15) & ~15
        if self.heap_next > HEAP + 0x200000:
            raise ValueError("decoder heap limit exceeded")
        uc.reg_write(UC_X86_REG_EAX, allocated)
        uc.reg_write(UC_X86_REG_ESP, esp + 4)
        uc.reg_write(UC_X86_REG_EIP, ret)

    def _return(self, uc, _address, _size, _user):
        self.returned = True
        uc.emu_stop()

    def call(self, address: int, *args: int) -> int:
        esp = STACK + 0xFF000
        for value in reversed(args):
            esp -= 4
            self.uc.mem_write(esp, struct.pack("<I", value))
        esp -= 4
        self.uc.mem_write(esp, struct.pack("<I", SENTINEL))
        self.uc.reg_write(UC_X86_REG_ESP, esp)
        self.returned = False
        try:
            self.uc.emu_start(address, 0, timeout=30000000,
                              count=MAX_INSTRUCTIONS)
        except UcError as exc:
            pc = self.uc.reg_read(UC_X86_REG_EIP)
            raise RuntimeError(f"DLL emulation stopped at {pc:#x}: {exc}") from exc
        if not self.returned:
            pc = self.uc.reg_read(UC_X86_REG_EIP)
            raise RuntimeError(f"DLL emulation did not return; PC={pc:#x}")
        return self.uc.reg_read(UC_X86_REG_EAX)

    def init(self, mode: int) -> tuple[int, int]:
        self.uc.mem_write(IO + 0x30010, b"\x00\x00\x00\x00")
        context = self.call(SP_INIT, mode, IO + 0x30010)
        frame_bits = struct.unpack("<H", self.uc.mem_read(IO + 0x30010, 2))[0]
        return context, frame_bits

    def decode(self, frame: bytes, context: int) -> tuple[int, bytes]:
        self.uc.mem_write(IO, frame)
        self.uc.mem_write(IO + 0x10000, bytes(1024))
        self.uc.mem_write(IO + 0x30000, bytes(4))
        self.call(SP_DECODE, IO, len(frame), IO + 0x10000,
                  IO + 0x30000, context)
        count = struct.unpack("<H", self.uc.mem_read(IO + 0x30000, 2))[0]
        if count > 512:
            raise ValueError(f"unexpected decoder sample count: {count}")
        return count, bytes(self.uc.mem_read(IO + 0x10000, count * 2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--npe", type=Path, required=True)
    parser.add_argument("--section", type=int, default=16)
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--wav", type=Path,
                        help="optional experimental 8-kHz mono PCM output")
    parser.add_argument("--report-json", type=Path,
                        help="save the complete per-frame experimental report")
    parser.add_argument("--control-random-seed", type=int,
                        help="decode deterministic random bytes as a negative control")
    parser.add_argument("--input-transform", default="raw",
                        choices=("raw", "swap16", "bitrev", "swap16-bitrev"))
    parser.add_argument("--bit-offset", type=int, default=0, choices=range(8))
    parser.add_argument("--fresh-context-control", action="store_true",
                        help="also decode each frame after a new init to detect predictor state")
    args = parser.parse_args()
    if args.fresh_context_control and args.frames > 64:
        parser.error("fresh-context control is limited to 64 frames")
    source = args.npe.read_bytes()
    offset, length = _parse_sections(source)[args.section]
    section = source[offset:offset + length]
    if section[:2] != b"\x20\x0d":
        parser.error("selected section is not NP560 format 13")
    count = int.from_bytes(section[2:4], "big")
    if length != ((4 + count * 21 + 1) & ~1):
        parser.error("section length does not match 21-byte candidate frames")
    encoded = candidate_bytes(section[4:4 + count * 21],
                              args.input_transform, args.bit_offset)
    frames = min(args.frames, len(encoded) // 21)
    dll = args.dll.read_bytes()
    decoder = IsolatedDecoder(dll)
    context, frame_bits = decoder.init(5)
    if frame_bits != 168:
        raise ValueError(f"mv_sp_init(5) reported {frame_bits} bits, not 168")
    pcm = bytearray()
    results = []
    rng = (random.Random(args.control_random_seed)
           if args.control_random_seed is not None else None)
    for i, source_frame in encoded_frames(encoded, 21, frames):
        frame = rng.randbytes(21) if rng is not None else source_frame
        samples, pcm_block = decoder.decode(frame, context)
        pcm.extend(pcm_block)
        signed = (struct.unpack("<" + "h" * samples, pcm_block)
                  if samples else ())
        block_hash = hashlib.sha256(pcm_block).hexdigest()
        result = {"index": i, "samples": samples,
                        "pcm_sha256": block_hash,
                        "minimum": min(signed) if signed else None,
                        "maximum": max(signed) if signed else None,
                        "first_16": list(signed[:16])}
        if args.fresh_context_control:
            fresh = decode_fresh_context(lambda: IsolatedDecoder(dll), 5, frame)
            result["fresh_pcm_sha256"] = hashlib.sha256(fresh).hexdigest()
            result["matches_fresh_context"] = fresh == pcm_block
        results.append(result)
    if args.wav:
        if args.wav.exists():
            parser.error(f"WAV output already exists: {args.wav}")
        args.wav.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(args.wav), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(pcm)
    all_samples = struct.unpack("<" + "h" * (len(pcm) // 2), pcm) if pcm else ()
    summary = {"decoded_frames": frames, "decoded_samples": len(all_samples),
               "minimum": min(all_samples) if all_samples else None,
               "maximum": max(all_samples) if all_samples else None,
               "rms": ((sum(x * x for x in all_samples) / len(all_samples)) ** 0.5
                       if all_samples else None),
               "clipped_samples": sum(abs(x) >= 32767 for x in all_samples)}
    report = {"schema": "np560-mobivoice-sp-probe-v1",
              "npe": str(args.npe), "section": args.section,
              "section_sha256": hashlib.sha256(section).hexdigest(),
              "candidate_frames": count, "mode": 5,
              "source": ("random-control" if rng is not None else "npe-section"),
              "random_seed": args.control_random_seed,
              "input_transform": args.input_transform,
              "bit_offset": args.bit_offset,
              "fresh_context_control": args.fresh_context_control,
              "frame_bits": frame_bits, "compatibility_verified": False,
              "summary": summary, "decoded": results,
              "wav": str(args.wav) if args.wav else None}
    if args.report_json:
        if args.report_json.exists():
            parser.error(f"report output already exists: {args.report_json}")
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, indent=2) + "\n",
                                    encoding="utf-8")
        print(json.dumps({"schema": report["schema"], "summary": summary,
                          "report_json": str(args.report_json),
                          "wav": report["wav"]}, indent=2))
    else:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
