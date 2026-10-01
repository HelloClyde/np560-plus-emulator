#!/usr/bin/env python3
"""Compare captured DAC WAV with explicit raw PCM16 reference change order.

Repeated values are collapsed by the shared analyzer; this does not certify
sample timing, analog output, or the reference decoder. Mono is duplicated to
both DAC channels. Inputs are read-only and existing reports are never replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path
import wave

import numpy as np
from analyze_np560_audio_delivery import measure_pcm_change_timing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wav', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--reference-channels', type=int, choices=(1, 2), required=True)
    parser.add_argument('--reference-rate', type=float, required=True)
    parser.add_argument('--reference-frames', type=int,
                        help='explicit prefix length; excluded suffix is NOT verified')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.reference.read_bytes()
    if not raw or len(raw) % (2 * args.reference_channels):
        parser.error('reference must contain complete signed PCM16 frames')
    reference = np.frombuffer(raw, dtype='<i2').reshape(-1, args.reference_channels)
    total_frames = len(reference)
    if args.reference_frames is not None:
        if not 2 <= args.reference_frames <= total_frames:
            parser.error('reference prefix must contain 2..total frames')
        reference = reference[:args.reference_frames]
    if args.reference_channels == 1:
        reference = np.repeat(reference, 2, axis=1)
    with wave.open(str(args.wav), 'rb') as wav:
        if wav.getnchannels() != 2 or wav.getsampwidth() != 2 or wav.getcomptype() != 'NONE':
            parser.error('capture must be uncompressed stereo PCM16 WAV')
        rate = wav.getframerate()
        pcm = wav.readframes(wav.getnframes())
    actual = np.frombuffer(pcm, dtype='<i2').reshape(-1, 2)
    result = measure_pcm_change_timing(reference, actual, args.reference_rate, rate)
    result.update(reference_path=str(args.reference.resolve()), wav_path=str(args.wav.resolve()),
                  reference_sha256=hashlib.sha256(raw).hexdigest(),
                  captured_pcm_sha256=hashlib.sha256(pcm).hexdigest(),
                  original_reference_frames=total_frames,
                  excluded_reference_suffix_frames=total_frames-len(reference),
                  reference_channels=args.reference_channels)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'exact_change_matches': len(result['matches']),
                      'playback_correctness_verified': False}))


if __name__ == '__main__':
    main()
