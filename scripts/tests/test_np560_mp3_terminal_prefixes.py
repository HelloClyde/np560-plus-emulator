#!/usr/bin/env python3
"""Check EOF prefixes against complete-frame PCM and failed-call rollback.

Uses existing rate-matrix MP3 fixtures. Kernel contract only, not original
player bitrate support, guest EOF detection, DAC timing or NPE decoding.
"""
import argparse
import ctypes as ct
import hashlib
import json
from pathlib import Path

from test_np560_mp3_hle_codec import Frame, decode, library
from test_np560_mp3_hle_final import final, pcm
from test_np560_mp3_sideinfo import mp3_frames


def check(lib, path):
    raw = path.read_bytes()
    packets = [raw[f['file_offset']:f['file_offset'] + f['frame_bytes']]
               for f in mp3_frames(path)]
    assert len(packets) > 1
    handle = lib.np560_mp3_codec_new()
    assert handle
    histogram = {}
    successes = []
    try:
        wanted = []
        for packet in packets:
            status, row = decode(lib, handle, packet)
            assert status == 0 and row.consumed == len(packet)
            wanted.append(pcm(row))
        # Each attempt starts with precisely the same real reservoir/history.
        for length in range(len(packets[-1]) + 1):
            lib.np560_mp3_codec_reset(handle)
            for index, packet in enumerate(packets[:-1]):
                status, row = decode(lib, handle, packet)
                assert status == 0 and pcm(row) == wanted[index]
            status, row = final(lib, handle, packets[-1][:length])
            histogram[str(status)] = histogram.get(str(status), 0) + 1
            if status == 0:
                assert row.consumed == length
                assert pcm(row) == wanted[-1], (path, length, 'changed PCM')
                successes.append(length)
            else:
                assert status in (1, 6, 7), (path, length, status)
                assert not any(bytes(row)), (path, length, 'published failed PCM')
                status, retry = decode(lib, handle, packets[-1])
                assert status == 0 and pcm(retry) == wanted[-1], (
                    path, length, 'failed EOF changed decoder history')
        assert successes and successes[-1] == len(packets[-1])
        assert histogram.get('1', 0) >= 4
        return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                    frames=len(packets), terminal_bytes=len(packets[-1]),
                    prefix_checks=len(packets[-1]) + 1, statuses=histogram,
                    accepted_lengths=successes, passed=True)
    finally:
        lib.np560_mp3_codec_free(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(passed=False, standalone_only=True, cases=[])
    try:
        lib = library(args.output)
        lib.np560_mp3_codec_decode_final.argtypes = [
            ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.POINTER(Frame)]
        lib.np560_mp3_codec_decode_final.restype = ct.c_int
        for rate in (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000):
            for channels in (1, 2):
                case = check(lib, args.fixtures / f'{rate}-{channels}.mp3')
                report['cases'].append(case)
                print(rate, channels, case['prefix_checks'], case['statuses'], flush=True)
        report['passed'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        (args.output / 'report.json').write_text(
            json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
