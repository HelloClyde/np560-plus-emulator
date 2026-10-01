#!/usr/bin/env python3
"""Create an explicitly synthetic LONG22 control, preserving all audio frames.

Remove only its 182-byte Info metadata frame, retaining ID3 and compressed
audio bytes exactly. This is an isolated experiment, not a playback fix.
"""
import argparse
import hashlib
import json
from pathlib import Path


def build(source, output):
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != '27521fc999c954d7e05cc56f2ba54253d4bdd32ac65c0ea7204fdda58945ec73':
        raise ValueError('requires the verified LONG22 fixture')
    if output.exists():
        raise FileExistsError(output)
    assert raw[45:49] == bytes.fromhex('fff370c0')
    assert raw[58:62] == b'Info'
    assert raw[227:231] == bytes.fromhex('fff360c4')
    result = raw[:45] + raw[227:]
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'LONG22.MP3').open('xb') as stream:
        stream.write(result)
    report = dict(source=str(source.resolve()), source_sha256=digest,
                  output_sha256=hashlib.sha256(result).hexdigest(),
                  source_bytes=len(raw), output_bytes=len(result),
                  removed_range=[45, 227], removed_bytes=182,
                  compressed_audio_unchanged=result[45:] == raw[227:],
                  production_fix=False)
    with (output / 'fixture.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), indent=2))
