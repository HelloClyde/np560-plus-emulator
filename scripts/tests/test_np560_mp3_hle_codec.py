#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Standalone HLE codec kernel checks, NOT an integrated QEMU/player test."""

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import argparse
import ctypes as ct
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time

from test_np560_mp3_sideinfo import mp3_frames

ROOT = Path(__file__).resolve().parents[2]


class Frame(ct.Structure):
    _fields_ = [(k, ct.c_uint32) for k in
                ("consumed", "hz", "channels", "samples_per_channel")] + [
                ("pcm", ct.c_int16 * 2304)]


class NoPCMInfo(ct.Structure):
    _fields_ = [(name, ct.c_uint32) for name in
                ('reason', 'available_history', 'required_history')]


def library(output):
    source = ROOT / "qemu-dmcu/hw/dmcu"
    assert hashlib.sha256((source / "minimp3/minimp3.h").read_bytes()).hexdigest() == (
        "57e437c5c1f0e8b243885d3929c8973b5e6c778451e0100ab4251d19915cb3ad")
    binary = output / "mp3-hle-codec.so"
    compiled = subprocess.run(["gcc", "-std=c11", "-O2", "-fPIC", "-shared", "-DNP560_MP3_CODEC_STANDALONE",
        "-Wall", "-Wextra", "-Werror", "-Wno-sign-compare",
        str(source / "np560_mp3_codec.c"), "-lm", "-o", str(binary)],
        capture_output=True, text=True)
    (output / "compiler.log").write_text(compiled.stdout + compiled.stderr)
    compiled.check_returncode()
    lib = ct.CDLL(str(binary.resolve()))
    lib.np560_mp3_codec_new.restype = ct.c_void_p
    lib.np560_mp3_codec_free.argtypes = [ct.c_void_p]
    lib.np560_mp3_codec_reset.argtypes = [ct.c_void_p]
    lib.np560_mp3_codec_decode.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t,
                                         ct.POINTER(Frame)]
    lib.np560_mp3_codec_decode.restype = ct.c_int
    lib.np560_mp3_codec_no_pcm_info.argtypes = [ct.c_void_p]
    lib.np560_mp3_codec_no_pcm_info.restype = NoPCMInfo
    return lib


def decode(lib, handle, data):
    output = Frame()
    status = lib.np560_mp3_codec_decode(handle, data, len(data), ct.byref(output))
    return status, output


def check(lib, path, output):
    source = path.read_bytes()
    frames = mp3_frames(path)
    packets = [source[f["file_offset"]:f["file_offset"]+f["frame_bytes"]] for f in frames]
    handle = lib.np560_mp3_codec_new()
    assert handle
    observed, checks = [], 0
    started = time.perf_counter()
    try:
        for packet in packets:
            status, row = decode(lib, handle, packet)
            assert status == 0 and row.consumed == len(packet), (status, row.consumed)
            observed.append(bytes(row.pcm)[:row.channels*row.samples_per_channel*2])
        elapsed = time.perf_counter() - started
        # Replay on the same allocated object. Truncated packets/invalid
        # headers/CRC failure must NOT mutate the following decode result.
        lib.np560_mp3_codec_reset(handle)
        for packet, wanted in zip(packets, observed):
            for oversized in (packet + b'\0', packet + packet):
                status, row = decode(lib, handle, oversized)
                assert status == 6 and not any(bytes(row)), 'overlong packet was consumed'
                checks += 1
            for prefix in (b"", packet[:3], packet[:-1]):
                status, row = decode(lib, handle, prefix)
                assert status == 1 and row.consumed == row.samples_per_channel == 0
                checks += 1
            malformed = bytes([0]) + packet[1:]
            status, row = decode(lib, handle, malformed)
            assert status == 2 and row.consumed == row.samples_per_channel == 0
            checks += 1
            unsupported = packet[:2] + bytes([packet[2] & 15]) + packet[3:]
            status, row = decode(lib, handle, unsupported)
            assert status == 3 and row.consumed == row.samples_per_channel == 0
            checks += 1
            protected = bytearray(packet)
            protected[1] &= 0xfe
            protected[4:6] = b"\0\0"
            status, row = decode(lib, handle, bytes(protected))
            assert status == 4 and row.consumed == row.samples_per_channel == 0
            checks += 1
            status, row = decode(lib, handle, packet)
            assert status == 0 and bytes(row.pcm)[:len(wanted)] == wanted
            checks += 1
        hz, channels = row.hz, row.channels
        # A real seek into a dependent frame cannot claim silent PCM. Keep
        # its exact result in the report; no requirement to invent history.
        lib.np560_mp3_codec_reset(handle)
        seek_status, seek = decode(lib, handle, packets[min(2, len(packets)-1)])
        assert seek_status in (0, 5)
        if seek_status == 5:
            assert seek.samples_per_channel == 0 and seek.consumed > 0
            explanation = lib.np560_mp3_codec_no_pcm_info(handle)
            assert explanation.reason == 2
            assert explanation.available_history == 0 < explanation.required_history
        # Invalid sideinfo is a separate no-output path, not reservoir warmup.
        packet = packets[0]
        if packet[1] & 1:  # unprotected fixture: avoid triggering CRC first
            invalid = bytearray(packet)
            version = (packet[1] >> 3) & 3
            mono = packet[3] >> 6 == 3
            side = (17 if mono else 32) if version == 3 else (9 if mono else 17)
            invalid[4:4+side] = b'\xff' * side
            lib.np560_mp3_codec_reset(handle)
            status, bad = decode(lib, handle, bytes(invalid))
            assert status == 5 and bad.samples_per_channel == 0, status
            assert lib.np560_mp3_codec_no_pcm_info(handle).reason == 1
        lib.np560_mp3_codec_reset(handle)
        assert lib.np560_mp3_codec_no_pcm_info(handle).reason == 0
        status, clean = decode(lib, handle, packets[0])
        assert status == 0
        assert bytes(clean.pcm)[:clean.channels*clean.samples_per_channel*2] == observed[0]
        assert lib.np560_mp3_codec_no_pcm_info(handle).reason == 0
    finally:
        lib.np560_mp3_codec_free(handle)
    pcm = b"".join(observed)
    output.mkdir()
    (output / "actual.s16le").write_bytes(pcm)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "packet=pos", "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    positions = [int(p["pos"]) for p in json.loads(probe.stdout)["packets"]]
    omitted = len(frames) - len(positions)
    assert omitted >= 0 and [f["file_offset"] for f in frames[omitted:]] == positions
    for i in range(omitted):
        assert b"Info" in packets[i] or b"Xing" in packets[i]
        assert not any(observed[i]), "only proven zero metadata PCM can be excluded"
    compared = b"".join(observed[omitted:])
    ref = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
        "-flags", "+bitexact", "-flags2", "+skip_manual", "-f", "mp3", "-i", "pipe:0",
        "-map", "0:a:0", "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1"],
        input=source, capture_output=True, check=True)
    (output / "ffmpeg.s16le").write_bytes(ref.stdout)
    (output / "ffmpeg.log").write_bytes(ref.stderr)
    assert len(compared) == len(ref.stdout), (len(compared), len(ref.stdout))
    samples = len(compared)//2
    errors = [abs(a-b) for a, b in zip(struct.unpack(f"<{samples}h", compared),
                                      struct.unpack(f"<{samples}h", ref.stdout))]
    peak = max(errors, default=0)
    result = dict(path=str(path), frames=len(frames), hz=hz, channels=channels,
        pcm_samples=len(pcm)//2, max_pcm16_difference=peak,
        pcm_sha256=hashlib.sha256(pcm).hexdigest(), reset_and_failure_checks=checks,
        omitted_zero_metadata_frames=omitted, delay_trimmed=False, gain_adjusted=False,
        seek_status=seek_status, seek_samples=seek.samples_per_channel,
        standalone_decode_seconds=elapsed, duration_seconds=len(pcm)/2/channels/hz,
        factory_player_connected=False, qemu_tested=False)
    (output / "report.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result), flush=True)
    # Preserve the comparison evidence even when its acceptance bound fails.
    assert peak <= 8, peak
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mp3", type=Path, action="append", required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(passed=False, standalone_only=True, cases=[])
    try:
        lib = library(args.output)
        for i, path in enumerate(args.mp3):
            report["cases"].append(check(lib, path, args.output/str(i)))
        report["passed"] = True
    except (AssertionError, subprocess.CalledProcessError) as error:
        report["failure"] = str(error)[:2000]
        print(report["failure"], flush=True)
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2)+"\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
