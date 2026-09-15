#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline bounded EOF codec checks; not a factory-player or DAC test."""

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
import subprocess

from test_np560_mp3_hle_codec import Frame, decode, library
from test_np560_mp3_sideinfo import mp3_frames


def final(lib, handle, data):
    frame = Frame()
    status = lib.np560_mp3_codec_decode_final(handle, data, len(data), ct.byref(frame))
    return status, frame


def pcm(frame):
    return bytes(frame.pcm)[:frame.channels * frame.samples_per_channel * 2]


def crc16(data):
    crc = 0xffff
    for byte in data:
        for bit in range(8):
            carry = ((crc >> 15) ^ (byte >> (7 - bit))) & 1
            crc = ((crc << 1) & 65535) ^ (0x8005 if carry else 0)
    return crc


def geometry(packet):
    version = packet[1] >> 3 & 3
    channels = 1 if packet[3] >> 6 == 3 else 2
    header = 4 if packet[1] & 1 else 6
    side_bytes = (17 if channels == 1 else 32) if version == 3 else (
        9 if channels == 1 else 17)
    bits = ''.join(f'{b:08b}' for b in packet[header:header + side_bytes])
    back = int(bits[:9 if version == 3 else 8], 2)
    start = 9 + (5 if channels == 1 else 3) + 4 * channels if version == 3 else 8 + channels
    stride = 59 if version == 3 else 63
    count = (2 if version == 3 else 1) * channels
    parts = [int(bits[start + n * stride:start + n * stride + 12], 2) for n in range(count)]
    return dict(version=version, channels=channels, header=header, side_bytes=side_bytes,
                main_data_begin=back, part2_3_bits=parts, part_start=start)


def check(lib, path):
    raw = path.read_bytes()
    frames = mp3_frames(path)
    packets = [raw[f['file_offset']:f['file_offset'] + f['frame_bytes']] for f in frames]
    wanted = []
    h = lib.np560_mp3_codec_new()
    try:
        for packet in packets:
            status, row = decode(lib, h, packet)
            assert status == 0 and row.consumed == len(packet), (path, status)
            wanted.append(pcm(row))
    finally:
        lib.np560_mp3_codec_free(h)

    def prime(index):
        handle = lib.np560_mp3_codec_new()
        for n in range(index):
            status, row = decode(lib, handle, packets[n])
            assert status == 0 and pcm(row) == wanted[n]
        return handle

    checks = []
    def reject(name, index, bad, status, api=final):
        handle = prime(index)
        try:
            observed, row = api(lib, handle, bad)
            assert observed == status and not any(bytes(row)), (path, name, observed)
            observed, row = decode(lib, handle, packets[index])
            assert observed == 0 and pcm(row) == wanted[index], (path, name, 'state changed')
            checks.append(name)
        finally:
            lib.np560_mp3_codec_free(handle)

    last, meta = packets[-1], geometry(packets[-1])
    minimum = meta['header'] + meta['side_bytes'] + (
        max(0, sum(meta['part2_3_bits']) - 8 * meta['main_data_begin']) + 7) // 8
    for missing in sorted({0, 1, len(last) - minimum}):
        handle = prime(len(packets) - 1)
        try:
            packet = last[:len(last) - missing]
            status, row = final(lib, handle, packet)
            assert status == 0 and row.consumed == len(packet), (path, missing, status)
            assert row.samples_per_channel == (1152 if meta['version'] == 3 else 576)
            assert pcm(row) == wanted[-1], (path, missing, 'PCM changed')
            checks.append(f'final missing {missing} bytes equals complete PCM')
        finally:
            lib.np560_mp3_codec_free(handle)

    # Add a real CRC field without changing the nominal packet length: the
    # two bytes removed are from the already-proved unused ancillary suffix.
    assert meta['header'] == 4 and minimum <= len(last) - 2
    protected = bytearray(last[:4] + b'\0\0' + last[4:-2])
    protected[1] &= 0xfe
    crc = crc16(protected[2:4] + protected[6:6 + meta['side_bytes']])
    protected[4:6] = crc.to_bytes(2, 'big')
    h = prime(len(packets) - 1)
    try:
        status, row = final(lib, h, bytes(protected[:-1]))
        assert status == 0 and row.consumed == len(protected) - 1 and pcm(row) == wanted[-1]
        checks.append('protected final packet validates CRC and matches PCM')
    finally:
        lib.np560_mp3_codec_free(h)
    protected[4] ^= 1
    reject('bad final CRC rejected', len(packets) - 1, bytes(protected[:-1]), 4)

    reject('ordinary decode remains strict', len(packets) - 1, last[:-1], 1, decode)
    for size in (0, 3, meta['header'] + meta['side_bytes'] - 1):
        reject(f'final insufficient header/sideinfo {size}', len(packets) - 1, last[:size], 1)
    reject('final rejects bytes past declared frame', len(packets) - 1, last + b'\0', 2)
    assert meta['main_data_begin'] > 0
    h = prime(0)
    try:
        status, row = final(lib, h, last[:-1])
        assert status == 7 and not any(bytes(row)), (path, 'missing history', status)
        status, row = decode(lib, h, packets[0])
        assert status == 0 and pcm(row) == wanted[0]
        checks.append('missing reservoir rejected without state mutation')
    finally:
        lib.np560_mp3_codec_free(h)

    # Pick real compressed audio needing current-frame bytes, not ancillary.
    for index, packet in enumerate(packets):
        g = geometry(packet)
        needed = sum(g['part2_3_bits']) - 8 * g['main_data_begin']
        if needed > 0:
            short = g['header'] + g['side_bytes'] + (needed + 7) // 8 - 1
            assert short < len(packet)
            reject('actual audio bits absent', index, packet[:short], 1)
            break
    else:
        raise AssertionError('fixture lacks a current-frame audio dependency')

    # Same declared audio length, impossible big_values: syntax rejection must
    # not leave synthesized state/history behind on the caller's decoder.
    invalid = bytearray(last)
    side_at = meta['header']
    bits = list(''.join(f'{b:08b}' for b in invalid[side_at:side_at + meta['side_bytes']]))
    start = meta['part_start'] + 12
    bits[start:start + 9] = f'{289:09b}'
    invalid[side_at:side_at + meta['side_bytes']] = int(''.join(bits), 2).to_bytes(meta['side_bytes'], 'big')
    reject('invalid sideinfo', len(packets) - 1, bytes(invalid[:-1]), 6)
    return dict(path=str(path), frames=len(frames), last=meta,
                final_frame_bytes=len(last), available_final_bytes=len(last) - 1,
                final_pcm_sha256=hashlib.sha256(wanted[-1]).hexdigest(),
                checks=checks, passed=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--mp3', type=Path, default=Path('tmp/np560-mp3-player-20260906-v1/input/tone440.mp3'))
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(passed=False, standalone_only=True, qemu_tested=False, cases=[])
    try:
        lib = library(args.output)
        lib.np560_mp3_codec_decode_final.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.POINTER(Frame)]
        lib.np560_mp3_codec_decode_final.restype = ct.c_int
        paths = [args.mp3]
        for rate, channels in ((44100, 1), (22050, 1), (22050, 2), (11025, 1), (11025, 2)):
            path = args.output / f'tone-{rate}-{channels}.mp3'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                '-i', f'sine=frequency=440:sample_rate={rate}:duration=0.6', '-ac', str(channels),
                '-c:a', 'libmp3lame', '-b:a', '64k' if rate == 44100 else '32k',
                '-write_xing', '0', '-id3v2_version', '0', '-map_metadata', '-1', str(path)],
                capture_output=True, check=True)
            paths.append(path)
        for path in paths:
            result = check(lib, path)
            report['cases'].append(result)
            print(json.dumps(result), flush=True)
        report['passed'] = True
    except (AssertionError, subprocess.CalledProcessError) as error:
        report['error'] = str(error)
        print(report['error'], flush=True)
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
