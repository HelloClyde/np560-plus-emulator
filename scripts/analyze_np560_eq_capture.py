#!/usr/bin/env python3
"""Measure contiguous normal/EQ DAC captures; not a factory EQ equivalence test."""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import sys
import wave


def analyze(root):
    report = json.loads((root / 'report.json').read_text(encoding='utf-8'))
    capture = report['device_audio_capture']
    if capture['error']:
        raise ValueError(capture['error'])
    samples = report['native_codec_samples']
    windows = {}
    intervals = [
        ('normal', '10-normal-start', '10-normal-end'),
        ('eq', '10-audio-select', '10-audio-selected-running'),
    ]
    if '10-normal-restored-start' in samples:
        intervals.append(('restored', '10-normal-restored-start', '10-normal-restored-end'))
    for name, begin, end in intervals:
        start, finish = samples[begin], samples[end]
        left, right = start['device_audio'], finish['device_audio']
        if left['generation'] != right['generation']:
            raise ValueError('device generation changed in '+name)
        lo, hi = left['next_frame'], right['next_frame']
        if hi <= lo:
            raise ValueError('empty/reversed interval')
        found = [p for p in capture['parts'] if p['generation'] == left['generation']
                 and p['first_frame'] <= lo and p['next_frame'] >= hi]
        if len(found) != 1:
            raise ValueError('missing or ambiguous continuous coverage in '+name)
        part = found[0]
        # Run reports may hold Linux absolute paths. Resolve only the artifact
        # basename within the supplied report directory, never arbitrary paths.
        path = root / Path(part['path']).name
        with wave.open(str(path), 'rb') as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (2, 2, 48000):
                raise ValueError('unexpected WAV format')
            raw = wav.readframes(wav.getnframes())
        if hashlib.sha256(raw).hexdigest() != part['sha256']:
            raise ValueError('capture hash mismatch')
        if len(raw) != (part['next_frame'] - part['first_frame']) * 4:
            raise ValueError('capture frame count mismatch')
        raw = raw[(lo-part['first_frame'])*4:(hi-part['first_frame'])*4]
        values = array('h', raw)
        if sys.byteorder != 'little':
            values.byteswap()
        channels = []
        for channel in (0, 1):
            data = values[channel::2]
            channels.append(dict(rms=math.sqrt(sum(x*x for x in data)/len(data)),
                                 peak=max(map(abs, data)),
                                 nonzero=sum(x != 0 for x in data),
                                 clipped=sum(x in (-32768, 32767) for x in data)))
            # Preserve all 100 ms block RMS values, including silence; a
            # median reduces loop-gap influence but is NOT exact frequency
            # response or permission to remove gaps from the recording.
            blocks = [math.sqrt(sum(x*x for x in data[j:j+4800])/4800)
                      for j in range(0, len(data)-4799, 4800)]
            channels[-1]['block_rms_100ms'] = blocks
            channels[-1]['median_block_rms'] = (sorted(blocks)[len(blocks)//2]
                                                if blocks else None)
        windows[name] = dict(first_frame=lo, next_frame=hi, seconds=(hi-lo)/48000,
                             unequal_channel_frames=sum(a != b for a, b in zip(values[::2], values[1::2])),
                             channels=channels, volume_start=start['volume_bytes'],
                             volume_end=finish['volume_bytes'],
                             mode_start=start['rom_mp3_hle']['audio_mode'],
                             mode_end=finish['rom_mp3_hle']['audio_mode'])
    ratios = [b['rms']/a['rms'] if a['rms'] else None for a, b in
              zip(windows['normal']['channels'], windows['eq']['channels'])]
    return dict(windows=windows, measured_eq_over_normal_rms=ratios,
                factory_equivalence_verified=False,
                note='RMS windows include natural track loops; not an exact filter transfer estimate.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = analyze(args.capture)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
