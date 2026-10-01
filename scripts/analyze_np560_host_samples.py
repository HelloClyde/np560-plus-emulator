#!/usr/bin/env python3
"""Symbolize sampled QEMU host IPs using recorded maps and ELF PT_LOAD segments."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import subprocess


def load_segments(path):
    with path.open('rb') as stream:
        header = stream.read(64)
        if header[:6] != b'\x7fELF\x02\x01':
            raise ValueError('expected little-endian ELF64')
        offset = struct.unpack_from('<Q', header, 32)[0]
        stride, count = struct.unpack_from('<HH', header, 54)
        if stride < 56 or not 0 < count < 65535:
            raise ValueError('invalid program-header table')
        result = []
        for index in range(count):
            stream.seek(offset+index*stride)
            fields = struct.unpack('<IIQQQQQQ', stream.read(56))
            if fields[0] == 1:
                result.append(dict(offset=fields[2], vaddr=fields[3], filesz=fields[5]))
        return result


def elf_address(file_offset, segments):
    candidates = {s['vaddr']+file_offset-s['offset'] for s in segments
                  if s['offset'] <= file_offset < s['offset']+s['filesz']}
    if len(candidates) != 1:
        raise ValueError(f'file offset not in a unique PT_LOAD: {file_offset:x}')
    return candidates.pop()


def parse_maps(text):
    result = []
    for line in text.splitlines():
        parts = line.split(maxsplit=5)
        start, end = (int(x, 16) for x in parts[0].split('-'))
        result.append(dict(start=start, end=end, permissions=parts[1],
                           offset=int(parts[2], 16), path=parts[5] if len(parts) == 6 else ''))
    return result


def analyze(profile, qemu):
    maps = parse_maps(profile['maps'])
    segments = load_segments(qemu)
    addresses, categories = Counter(), Counter()
    for sample in profile['samples']:
        ip = sample['ip']
        mapping = next((m for m in maps if m['start'] <= ip < m['end']), None)
        if mapping is None:
            categories['unmapped'] += 1
        elif mapping['path'] == str(qemu.resolve()):
            assert 'x' in mapping['permissions'], 'sample outside executable mapping'
            addresses[elf_address(ip-mapping['start']+mapping['offset'], segments)] += 1
            categories['qemu'] += 1
        else:
            # Do not label anonymous executable pages as proven TCG blocks.
            label = mapping['path'] or ('anonymous-executable' if 'x' in mapping['permissions'] else 'anonymous')
            categories[label] += 1
    ordered = sorted(addresses)
    rows = subprocess.check_output(['addr2line', '-f', '-C', '-e', str(qemu),
                                    *(hex(ip) for ip in ordered)], text=True).splitlines() if ordered else []
    assert len(rows) == 2*len(ordered), 'unexpected addr2line output'
    functions, locations = Counter(), Counter()
    for index, ip in enumerate(ordered):
        name, location = rows[2*index:2*index+2]
        functions[name] += addresses[ip]
        locations[(name, location)] += addresses[ip]
    return dict(samples=len(profile['samples']), lost_records=profile['lost'],
                categories=dict(categories.most_common()),
                functions=[dict(name=k, samples=v) for k,v in functions.most_common()],
                locations=[dict(name=k[0], location=k[1], samples=v) for k,v in locations.most_common()],
                scope='Leaf user-IP samples, not inclusive stacks or guest opcode counts; external binaries not symbolized')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    expected = report.get('qemu_sha256') or report['artifacts']['qemu']['sha256']
    assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == expected, 'QEMU differs from sampled build'
    profiles = ([report] if 'samples' in report else
                [w['host_cpu_profile'] for w in report['speed_windows'] if 'host_cpu_profile' in w])
    assert profiles, 'no host samples in report'
    result = dict(qemu_sha256=expected, windows=[analyze(p, args.qemu) for p in profiles])
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2)+'\n')
    for window in result['windows']:
        print(json.dumps({k: v for k,v in window.items() if k not in ('functions','locations')}))
        print(json.dumps(window['functions'][:15]))


if __name__ == '__main__':
    main()
