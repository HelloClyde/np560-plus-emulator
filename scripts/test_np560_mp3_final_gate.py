#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Small guest-only callers for the v5 EOF gate; no NAND, Web or host RAM writes.

Failures are captured before a same-session complete-frame recovery. Neither
the private ring cursors nor the original consumed-word/ready fields may move
on an unsuccessful request. This exercises the kernel gate, not ring/DTU end
ownership or full-player playback.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_np560_mp3_resident import load_bundle
from test_np560_dtu import read_word, write_word
from test_np560_mac import run
from test_np560_mp3_hle_codec import decode, library
from test_np560_mp3_hle_final import geometry
from test_np560_mp3_sideinfo import mp3_frames

BANK, OFFSET = 0xa3, 0x100
WORKSPACE = (BANK << 15) + OFFSET
FIELDS = {'pending': 8, 'valid': 14, 'status': 16, 'detail': 18,
          'read': 0x40, 'bytes_lo': 0x42, 'bytes_hi': 0x44,
          'final': 0x66}


def s16(value):
    return value if value < 32768 else value - 65536


def call(words, gate, service):
    target = gate + 16 * service
    words.extend([0x68f3, OFFSET, 0xbd00 | target >> 16, target & 65535])


def stage(words, packet, final):
    meta = geometry(packet)
    header = meta['header']
    values = {0x48: int.from_bytes(packet[:2], 'big'),
              0x4a: int.from_bytes(packet[2:4], 'big'),
              0x4c: len(packet), 0x50: len(packet) - header,
              0x102: meta['channels'], 0x66: final}
    if header == 6:
        values[0x54] = int.from_bytes(packet[4:6], 'big')
    body = packet[header:]
    for i in range(0, len(body), 2):
        # An odd high-lane byte is part of the guest staging ABI. The low
        # guard lane is not part of BODY_BYTES and must never reach codec.
        values[0x3300 + i] = body[i] << 8 | (body[i + 1] if i + 1 < len(body) else 0xa5)
    for offset, value in values.items():
        write_word(words, OFFSET + offset, value, banked=True)


def check(qemu, image, gate, output, case, first, expected_pcm):
    name, packet, final, eof, status, detail = case
    words = [0x6800, 2, 0x68ff, 0x6000, 0x6810, BANK, 0x6811, BANK]
    call(words, gate, 0)
    # Guest-owned cursor/ready sentinels. The decoder gate must not invent
    # input consumption or drive original software ready/EOF publication.
    for off, value in ((0x40, 0x1234), (0x42, 0x55aa), (0x44, 0x66bb)):
        write_word(words, OFFSET + off, value, banked=True)
    for address, value in ((0x3340, 0x1200), (0x3350, 0x1122), (0x3352, 0x3344)):
        write_word(words, address, value)
    words.extend([0xff83, 0xe789 if eof else 0xf789])
    stage(words, packet, final)
    call(words, gate, 1)
    values = [('r0', 576 if status == 0 else 0), ('r2', status)]
    for register in (0, 2):
        words.extend([0x3f10, 0xa8f0 | register, 0x2400 + (0 if register == 0 else 2)])
    expected_fields = {'pending': int(status == 0), 'valid': 576 if status == 0 else 0,
                       'status': status, 'detail': detail, 'read': 0x1234,
                       'bytes_lo': 0x55aa, 'bytes_hi': 0x66bb, 'final': final}
    for name_field, off in FIELDS.items():
        read_word(words, OFFSET + off, 0, banked=True)
        words.extend([0x3f10, 0xa8f0, 0x2400 + 2 * len(values)])
        values.append((name_field, expected_fields[name_field]))
    for name_field, address, value in (('writer', 0x3340, 0x1200),
            ('consumed_hi', 0x3350, 0x1122), ('consumed_lo', 0x3352, 0x3344)):
        read_word(words, address, 0)
        words.extend([0x3f10, 0xa8f0, 0x2400 + 2 * len(values)])
        values.append((name_field, value))
    for name_field, address, mask, value in (('original_ready', 0xf006, 0x8000, 0),
            ('original_eof', 0xf012, 0x80, 0x80 if eof else 0)):
        read_word(words, address, 0)
        words.extend([0x74f0, mask, 0x3f10, 0xa8f0, 0x2400 + 2 * len(values)])
        values.append((name_field, value))
    if status:
        # No reset: the failed attempt must not poison real codec history.
        # The first frame contains actual nonzero audio and needs no history.
        stage(words, first, 0)
        call(words, gate, 1)
    # A negative case ends at its recovery call; the positive case ends
    # after copying the EOF bit to the evidence record, which clobbers R0.
    result = run(qemu, output, name, words,
        {0: 576 if status else (0x80 if eof else 0), 2: 0, 3: OFFSET, 15: 0x6000},
        rom=image, rom_mp3_hle_base=gate, icount=5,
        expected_data=[s16(value) for _, value in values],
        capture_ranges=[('pcm', WORKSPACE + 0x5700, 2304)],
        metadata=dict(final_flag=final, real_eof=eof, packet_bytes=len(packet),
                      captured_fields=[field for field, _ in values],
                      failed_request_then_same_session_recovery=bool(status)))
    actual = (output / f'{name}.pcm.bin').read_bytes()
    assert actual == expected_pcm, (name, 'PCM/recovery differs from complete first frame')
    stats = result['rom_mp3_hle']
    assert stats['version'] == 5 and stats['frames'] == stats['granules'] == 1
    assert stats['calls'] == [1, 2 if status else 1, 0, 0]
    assert stats['failures'] == int(status != 0)
    assert stats['final_frame_calls'] == int(final == 1)
    assert stats['final_frame_failures'] == int(final == 1 and status != 0)
    assert stats['input_space_calls'] == stats['pcm_copy_calls'] == 0
    result['pcm_recovery_verified'] = True
    result['pcm_sha256'] = hashlib.sha256(actual).hexdigest()
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for option in ('qemu', 'resident-bundle', 'output'):
        p.add_argument('--' + option, type=Path, required=True)
    p.add_argument('--mp3', type=Path, default=Path('tmp/np560-mp3-player-20260906-v1/input/tone440.mp3'))
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    _, image, manifest = load_bundle(args.resident_bundle)
    assert manifest['rom_mp3_hle']['version'] == 5
    gate = manifest['rom_mp3_hle']['base']
    identity = dict(qemu_sha256=hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
                    resident_sha256=hashlib.sha256(image).hexdigest(),
                    source_sha256=hashlib.sha256(args.mp3.read_bytes()).hexdigest())
    report = dict(passed=False, identity=identity, cases=[], host_guest_memory_writes=0,
                  nand_used=False, full_player_tested=False)
    try:
        raw, packets = args.mp3.read_bytes(), []
        for frame in mp3_frames(args.mp3):
            packets.append(raw[frame['file_offset']:frame['file_offset'] + frame['frame_bytes']])
        first, dependent = packets[0], packets[1]
        g = geometry(first)
        assert g['main_data_begin'] == 0 and g['channels'] == 2
        assert geometry(dependent)['main_data_begin'] > 0
        minimum = g['header'] + g['side_bytes'] + (sum(g['part2_3_bits']) + 7) // 8
        assert minimum < len(first) - 1
        lib = library(args.output)
        handle = lib.np560_mp3_codec_new()
        try:
            status, row = decode(lib, handle, first)
            assert status == 0 and row.samples_per_channel == 1152 and any(bytes(row.pcm))
            expected = [row.pcm[2 * i + channel] for channel in (0, 1) for i in range(576)]
            expected_pcm = struct.pack('<1152h', *expected)
        finally:
            lib.np560_mp3_codec_free(handle)
        for case in (
            ('final-without-original-eof', first[:-1], 1, False, 2, 0),
            ('invalid-final-flag', first[:-1], 2, True, 2, 0),
            ('ordinary-short-stays-rejected', first[:-1], 0, True, 7, 0x801),
            ('eof-missing-sideinfo', first[:g['header'] + g['side_bytes'] - 1], 1, True, 7, 0x801),
            ('eof-missing-audio-bits', first[:minimum - 1], 1, True, 7, 0x801),
            ('eof-missing-real-history', dependent[:-1], 1, True, 7, 0x807),
            ('eof-short-audio-complete', first[:-1], 1, True, 0, 0)):
            report['cases'].append(check(args.qemu, image, gate, args.output, case, first, expected_pcm))
        assert hashlib.sha256(args.qemu.read_bytes()).hexdigest() == identity['qemu_sha256']
        report['passed'] = True
    except (AssertionError, RuntimeError) as error:
        report['failure'] = str(error)[:3000]
        print(report['failure'], flush=True)
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
