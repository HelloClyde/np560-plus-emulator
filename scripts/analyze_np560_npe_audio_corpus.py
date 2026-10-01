#!/usr/bin/env python3
"""Inventory NPE sound candidates without decoding or trimming their bytes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from analyse_np560_npe import MAGIC, SECTION_TABLE_END, _parse_sections


def inspect(blob, name):
    if len(blob) < SECTION_TABLE_END or not blob.startswith(MAGIC):
        raise ValueError(f'{name}: not a complete NPE container header')
    sections = _parse_sections(blob)
    if (sections[0][0] != SECTION_TABLE_END or
            any(a+n != b for (a,n),(b,_) in zip(sections, sections[1:])) or
            sum(n for _,n in sections) + SECTION_TABLE_END != len(blob)):
        raise ValueError(f'{name}: container coverage differs')
    candidates = []
    for index, (offset, size) in enumerate(sections):
        if index < 16:
            continue
        payload = blob[offset:offset+size]
        count = int.from_bytes(payload[2:4], 'big') if size >= 4 else None
        nominal = 4 + count * 21 if count is not None else None
        candidates.append(dict(section=index, offset=offset, bytes=size,
            sha256=hashlib.sha256(payload).hexdigest(), header_hex=payload[:6].hex(),
            format13_prefix=payload[:2] == b'\x20\x0d', header_count=count,
            matches_word_aligned_21byte_relation=(nominal is not None and size == (nominal+1)//2*2),
            bytes_beyond_nominal=(size-nominal if nominal is not None else None),
            extra_byte_hex=(payload[-1:].hex() if nominal is not None and size == nominal+1 else None)))
    return dict(path=str(name), bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest(),
                section_count=len(sections), sound_candidates=candidates)


def summarize(games):
    unique = {}
    for game in games:
        for sound in game['sound_candidates']:
            unique.setdefault(sound['sha256'], []).append(dict(path=game['path'], section=sound['section']))
    sounds = [sound for game in games for sound in game['sound_candidates']]
    return dict(schema='np560-npe-audio-corpus-v1', codec_verified=False,
        scope='sections >=16 are candidates; exact hashes include all bytes; no codec/frame-boundary/padding proof',
        game_count=len(games), candidate_count=len(sounds), unique_count=len(unique),
        prefix_counts=dict(Counter(sound['header_hex'][:4] for sound in sounds)),
        length_relation_mismatches=[dict(path=g['path'], section=s['section'])
            for g in games for s in g['sound_candidates'] if not s['matches_word_aligned_21byte_relation']],
        games=games, unique_owners=unique)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(p for p in args.directory.rglob('*') if p.is_file() and p.suffix.lower() == '.npe')
    if not paths:
        parser.error('no NPE files')
    report = summarize([inspect(path.read_bytes(), path) for path in paths])
    # Exclusive creation: evidence files are not silently rewritten.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({key:report[key] for key in ('game_count','candidate_count','unique_count','prefix_counts')}))


if __name__ == '__main__':
    main()
