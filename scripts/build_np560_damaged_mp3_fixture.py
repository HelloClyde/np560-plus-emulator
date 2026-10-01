#!/usr/bin/env python3
"""Build an isolated invalid-sideinfo MP3; never modify the source file."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'tests'))
from test_np560_mp3_sideinfo import mp3_frames


def build(source, output, frame_index=50, verify_codec=False):
    raw = source.read_bytes()
    # Pin the synthetic, no-Info 24 kHz mono source, not arbitrary user music.
    digest = hashlib.sha256(raw).hexdigest()
    if digest != 'b20217dd306e245377574b6dbdddfb5d28d4b92a2c3db03679e17186700a37b0':
        raise ValueError('requires the verified synthetic 24kHz LONG22 fixture')
    frames = mp3_frames(source)
    if not 1 <= frame_index < len(frames):
        raise ValueError('damage must follow at least one complete good frame')
    offset = frames[frame_index]['file_offset']
    header = raw[offset:offset+4]
    assert ((header[1] >> 3) & 3) == 2 and header[1] & 1 and header[3] >> 6 == 3
    begin, end = offset + 4, offset + 13
    damaged = raw[:begin] + b'\xff' * 9 + raw[end:]
    assert damaged[:begin] == raw[:begin] and damaged[end:] == raw[end:]
    output.mkdir(parents=True, exist_ok=False)
    (output / 'LONG22.MP3').write_bytes(damaged)
    report = {'synthetic_fixture_only': True, 'source': str(source),
              'source_sha256': digest, 'output_sha256': hashlib.sha256(damaged).hexdigest(),
              'bytes': len(raw), 'frame_index': frame_index, 'frame_count': len(frames),
              'changed_range': [begin, end], 'original_sideinfo_hex': raw[begin:end].hex(),
              'new_sideinfo_hex': damaged[begin:end].hex(),
              'unchanged_outside_range': True, 'original_not_modified': source.read_bytes() == raw}
    if verify_codec:
        from test_np560_mp3_hle_codec import library, decode
        lib = library(output)
        handle = lib.np560_mp3_codec_new()
        assert handle
        try:
            statuses = []
            for f in frames[:frame_index+1]:
                packet = damaged[f['file_offset']:f['file_offset']+f['frame_bytes']]
                status, result = decode(lib, handle, packet)
                statuses.append(status)
            assert statuses[:-1] == [0] * frame_index
            assert statuses[-1] == 5 and result.samples_per_channel == 0
            assert lib.np560_mp3_codec_no_pcm_info(handle).reason == 1
            report['codec_check'] = {'valid_prefix_frames': frame_index,
                                     'damaged_status': 5, 'invalid_sideinfo': True,
                                     'damaged_pcm_samples': 0,
                                     'scope': 'standalone kernel, not player recovery'}
        finally:
            lib.np560_mp3_codec_free(handle)
    (output / 'fixture.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frame-index', type=int, default=50)
    parser.add_argument('--verify-codec', action='store_true', help='requires gcc; validates intended error')
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, args.frame_index, args.verify_codec), indent=2))


if __name__ == '__main__':
    main()
