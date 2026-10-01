#!/usr/bin/env python3
"""Guest HLE error/release/reopen contract, not a player UI or audio test."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_np560_mp3_resident import load_bundle
from np560_assembler import _DMCUAssembler
from test_np560_mac import run
from test_np560_mp3_sideinfo import mp3_frames

WORK = 0x518100


def check(qemu, bundle, output, packet, recover, icount):
    _, rom, manifest = load_bundle(bundle)
    gate = manifest['rom_mp3_hle']
    a = _DMCUAssembler(0x200000)
    two_granules = ((packet[1] >> 3) & 3) == 3
    def const(offset, value):
        a.emit(0x6810, WORK >> 15, 0x68f0, value,
               0xa8f0, (WORK & 0x7fff) + offset)
    def call(service):
        target = gate['base'] + service * 16
        a.emit(0x6810, WORK >> 15, 0x68f3, WORK & 0x7fff,
               0xbd00 | (target >> 16), target & 65535)
    def read(offset, reg):
        a.emit(0x6810, WORK >> 15, 0x88f0 | reg, (WORK & 0x7fff) + offset)
    def stage():
        const(0x48, int.from_bytes(packet[:2], 'big'))
        const(0x4a, int.from_bytes(packet[2:4], 'big'))
        const(0x4c, len(packet))
        const(0x50, len(packet) - 4)
        const(0x102, 1)
        const(0x66, 0)
        for off in range(4, len(packet), 2):
            const(0x3300 + off - 4, int.from_bytes(packet[off:off+2].ljust(2, b'\0'), 'big'))
    a.emit(0x6800, 2, 0x68ff, 0x7000)
    call(0)
    stage()
    call(1)
    read(14, 4)
    expected = {4: 576, 15: 0x7000}
    if recover in ('channel-baseline', 'channel-mismatch', 'extra-frame-byte'):
        assert not two_granules
        if recover == 'channel-mismatch':
            const(0x102, 2)  # staged descriptor contradicts mono header
            call(1)
            read(14, 5)
            read(16, 6)
            expected.update({5: 0, 6: 7})
            const(0x102, 1)
        elif recover == 'extra-frame-byte':
            # Internally consistent LENGTH/BODY, but larger than the frame
            # header declares. This reaches the codec, unlike 'length'.
            const(0x4c, len(packet) + 1)
            const(0x50, len(packet) - 3)
            call(1)
            read(14, 5)
            read(16, 6)
            expected.update({5: 0, 6: 7})
            const(0x4c, len(packet))
            const(0x50, len(packet) - 4)
        # Retry without release/reopen: rejected metadata must not advance
        # reservoir or synthesis history. Compare with two accepted packets.
        call(1)
    elif recover == 'busy':
        call(1)
        read(14, 5)
        read(16, 6)
        expected.update({5: 576, 6: 6})
    elif recover:
        mutation = {'oversized': (0x50, 0xffff), 'length': (0x4c, len(packet) + 1),
                    'final-flag': (0x66, 2), 'unproven-eof': (0x66, 1)}[recover]
        const(*mutation)
        call(1)
        read(14, 5)
        read(16, 6)
        expected.update({5: 0, 6: 2})
        call(3)
        read(20, 7)
        call(0)
        stage()
        call(1)
        expected[7] = 0
    expected.update({0: 576, 2: 0})
    if two_granules:
        # Busy must preserve the queued second half and its real PCM. Empty
        # means no NEW publication; the native service retains the last one.
        call(2)
        read(14, 8)
        read(8, 9)
        a.emit(0x08a0)  # MOV R10,R0: second-half sample count
        call(2)
        read(14, 12)
        expected.update({0: 0, 2: 1, 8: 576, 9: 0, 10: 576, 12: 576})
    name = ('mpeg1-' if two_granules else '') + (recover or 'baseline') + f'-{icount}'
    result = run(qemu, output, name, a.finish(), expected, rom=rom,
                 rom_mp3_hle_base=gate['base'], icount=icount,
                 capture_ranges=[('pcm', WORK + 0x5700, 2304)],
                 metadata={'synthetic_gate_contract_only': True,
                           'packet_sha256': hashlib.sha256(packet).hexdigest()})
    stats = result['rom_mp3_hle']
    assert stats['sessions'] == 1
    assert stats['frames'] == (2 if recover and recover != 'busy' else 1)
    if two_granules:
        assert stats['granules'] == 2
    assert stats['failures'] == (1 if recover and recover != 'channel-baseline' else 0)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('qemu', 'bundle', 'input', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--mpeg1-input', type=Path)
    args = p.parse_args()
    data = args.input.read_bytes()
    first = mp3_frames(args.input)[0]
    packet = data[first['file_offset']:first['file_offset'] + first['frame_bytes']]
    assert (packet[1] >> 3) & 3 == 2 and packet[1] & 1 and packet[3] >> 6 == 3
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'passed': False, 'cases': [], 'qemu_sha256': hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    try:
        for icount in (None, 5):
            baseline = None
            for recover in (None, 'oversized', 'length', 'final-flag', 'unproven-eof'):
                result = check(args.qemu, args.bundle, args.output, packet, recover, icount)
                pcm = Path(result['captures']['pcm']['path']).read_bytes()
                assert any(pcm), 'fixture must prove nonzero PCM recovery'
                if baseline is None:
                    baseline = pcm
                else:
                    assert pcm == baseline, 'release/reopen leaked previous decoder state'
                report['cases'].append(result)
            channel_baseline = check(args.qemu, args.bundle, args.output, packet,
                                     'channel-baseline', icount)
            report['cases'].append(channel_baseline)
            mismatch = check(args.qemu, args.bundle, args.output, packet,
                             'channel-mismatch', icount)
            report['cases'].append(mismatch)
            assert Path(mismatch['captures']['pcm']['path']).read_bytes() == \
                Path(channel_baseline['captures']['pcm']['path']).read_bytes(), \
                'rejected channel descriptor advanced decoder history'
            extra = check(args.qemu, args.bundle, args.output, packet,
                          'extra-frame-byte', icount)
            report['cases'].append(extra)
            assert Path(extra['captures']['pcm']['path']).read_bytes() == \
                Path(channel_baseline['captures']['pcm']['path']).read_bytes(), \
                'rejected extra frame byte advanced decoder history'
            if args.mpeg1_input:
                mpeg1_data = args.mpeg1_input.read_bytes()
                f = mp3_frames(args.mpeg1_input)[0]
                mpeg1_packet = mpeg1_data[f['file_offset']:f['file_offset'] + f['frame_bytes']]
                assert ((mpeg1_packet[1] >> 3) & 3) == 3 and mpeg1_packet[1] & 1
                assert mpeg1_packet[3] >> 6 == 3
                baseline = None
                for recover in (None, 'busy'):
                    result = check(args.qemu, args.bundle, args.output, mpeg1_packet, recover, icount)
                    pcm = Path(result['captures']['pcm']['path']).read_bytes()
                    assert any(pcm)
                    if baseline is None:
                        baseline = pcm
                    else:
                        assert pcm == baseline, 'busy request damaged second granule'
                    report['cases'].append(result)
        report['passed'] = True
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
