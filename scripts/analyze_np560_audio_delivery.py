#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Align recorded DAC WAV windows with same-packet request counters (read-only).

This measures output, not playback correctness. A missing write may be a
legitimate stopped/empty buffer; outside-request writes include native ramps.
FFT peaks and average write rates need not agree during nonuniform holds.
Requires numpy. Never resamples, trims, fills, or modifies the input WAV.
"""
import argparse
import hashlib
import json
from pathlib import Path
import wave

import numpy as np


def lifecycle_evidence(report, packets):
    """Join bounded device/HLE evidence in virtual time, not host poll time.

    A control event's pc is the CPU's current instruction, not a promise
    that all possible writers (e.g. DTU) originated at that PC. HLE service
    0/3 events are entries to validated reset/release, not success reports.
    """
    controls, lifecycle = {}, {}
    for packet in packets:
        for event in packet.get('control_events', []):
            key = (packet['generation'], event['sequence'])
            assert key not in controls or controls[key] == event
            controls[key] = event
    for sample in report.get('native_codec_samples', {}).values():
        audio = sample.get('device_audio', {})
        for event in audio.get('control_events', []):
            key = (audio['generation'], event['sequence'])
            assert key not in controls or controls[key] == event
            controls[key] = event
        hle = sample.get('rom_mp3_hle', {})
        for event in hle.get('lifecycle_events', []):
            key = (hle['device_resets'], event['sequence'])
            assert key not in lifecycle or lifecycle[key] == event
            lifecycle[key] = event
    if not controls and not lifecycle:
        return None
    hle_events = [dict(device_resets=key[0], **event)
                  for key, event in sorted(lifecycle.items())]
    sequences = {}
    for generation, sequence in controls:
        sequences.setdefault(generation, []).append(sequence)
    coverage = {generation: dict(first=min(values), last=max(values),
                                missing=max(values)-min(values)+1-len(values))
                for generation, values in sequences.items()}
    intervals, disabled, last_closed_writes = [], {}, {}
    for (generation, _), event in sorted(controls.items()):
        if event['reg'] != 0x72:
            continue
        before = event['old_value'] & 0x8001 == 1
        if before and not event['enabled']:
            disabled[generation] = event
        elif not before and event['enabled'] and generation in disabled:
            start = disabled.pop(generation)
            complete = coverage[generation]['first'] == coverage[generation]['missing'] == 0
            previous = last_closed_writes.get(generation, [0, 0] if complete else None)
            intervals.append(dict(generation=generation, off=start, on=event,
                disabled_ms=(event['virtual_ns']-start['virtual_ns'])/1e6,
                writes_since_previous_close=([a-b for a,b in zip(start['writes'], previous)]
                                             if previous is not None else None),
                hle_during_disabled=[e for e in hle_events
                    if start['virtual_ns'] <= e['virtual_ns'] <= event['virtual_ns']]))
            last_closed_writes[generation] = start['writes']
    return dict(control_events_observed=len(controls), control_sequence_coverage=coverage,
                control_events=[dict(generation=key[0], **event)
                                for key, event in sorted(controls.items())],
                hle_events=hle_events, disabled_intervals=intervals,
                open_disabled_intervals=[dict(generation=k, **v) for k,v in disabled.items()],
                caveat='bounded observed history; no gapless, tail or hardware-fidelity claim')


def dtu_request_accounting(report):
    """DTU can service a latched request outside the audio timer callback."""
    import re
    results = {}
    for label, sample in report.get('native_codec_samples', {}).items():
        state = sample.get('transport', {}).get('dtu-state', '')
        delivery = sample.get('device_audio', {}).get('request_delivery', {})
        if 'writes' not in delivery:
            continue
        channels = []
        for ch in (0, 1):
            match = re.search(r'\bCH%d:([0-9a-fA-F]+)/([0-9]+)/([0-9]+)' % ch, state)
            if match:
                transfers = int(match[2])
                channels.append(dict(channel=ch, dtu_transfers=transfers,
                    request_callback_writes=delivery['writes'][ch],
                    difference=transfers-delivery['writes'][ch]))
        if channels:
            results[label] = channels
    return results


def control_capture_intervals(report, recordings):
    """Check actual continuous PCM coverage; snapshots alone cannot prove silence."""
    samples = report.get('native_codec_samples', {})
    results = {}
    for action in ('pause', 'stop'):
        start = samples.get('06-' + action + '-delivered', {}).get('device_audio')
        end = samples.get('06-' + action + '-3', {}).get('device_audio')
        if start is None or end is None:
            continue
        lo, hi = start['next_frame'], end['next_frame']
        result = dict(first_frame=lo, next_frame=hi, covered=False,
                      continuous_silence_verified=False)
        for part, pcm, rate in recordings:
            if (start['generation'] == end['generation'] == part['generation']
                    and part['first_frame'] <= lo < hi <= part['next_frame']):
                window = pcm[lo-part['first_frame']:hi-part['first_frame']]
                nonzero = int(np.count_nonzero(window))
                result.update(covered=True, frames=len(window), seconds=len(window)/rate,
                              nonzero_samples=nonzero,
                              continuous_silence_verified=nonzero == 0)
                break
        results[action] = result
    return results


def analyze(report_path):
    report = json.loads(report_path.read_text(encoding='utf-8'))
    capture = report['device_audio_capture']
    packets = json.loads(Path(capture['request_delivery_path']).read_text(encoding='utf-8'))
    output = dict(source_report=str(report_path),
                  qemu_sha256=(report.get('qemu_sha256') or
                               report.get('artifacts', {}).get('qemu', {}).get('sha256')),
                  playback_verified=False, parts=[])
    evidence = lifecycle_evidence(report, packets)
    if evidence is not None:
        output['lifecycle'] = evidence
    refill_events = {}
    for sample in report.get('native_codec_samples', {}).values():
        for event in sample.get('dtu_refill', {}).get('events', []):
            refill_events[event['seq']] = event
    if refill_events:
        output['refill'] = dict(unique_observed_events=len(refill_events), channels=[])
        for ch in range(4):
            all_events = [e for e in refill_events.values() if e['channel'] == ch]
            if not all_events: continue
            # Retain the selection rule: short completed 576-sample reloads,
            # not a claim that every selected event is steady-state playback.
            selected = [e for e in all_events if e['accepted'] and e['count'] == 576
                        and 0 <= e['reloaded_ns']-e['completed_ns'] < 20000000]
            summary = dict(channel=ch, observed=len(all_events), selected=len(selected),
                           accepted=sum(e['accepted'] for e in all_events),
                           selection='accepted, COUNT=576, total latency <20ms')
            for label, end, start in [('entry_us','accepted_ns','completed_ns'),
                                      ('handler_us','reloaded_ns','accepted_ns'),
                                      ('total_us','reloaded_ns','completed_ns')]:
                values = [(e[end]-e[start])/1000 for e in selected]
                if values:
                    summary[label] = dict(zip(('min','p50','p90','max'),
                        [float(v) for v in np.percentile(values, [0,50,90,100])]))
            output['refill']['channels'].append(summary)
    recordings = []
    for part in capture['parts']:
        path = Path(part['path'])
        with wave.open(str(path), 'rb') as stream:
            assert stream.getsampwidth() == 2 and stream.getnchannels() == 2
            rate = stream.getframerate()
            raw = stream.readframes(stream.getnframes())
        pcm = np.frombuffer(raw, dtype='<i2').reshape(-1, 2)
        assert len(pcm) == part['frames']
        observed = [packet for packet in packets
                    if packet['generation'] == part['generation'] and
                    part['first_frame'] <= packet['next_frame'] <= part['next_frame']]
        positions = np.array([packet['next_frame'] for packet in observed])
        stats = dict(path=str(path), pcm_sha256=hashlib.sha256(raw).hexdigest(),
                     frames=len(pcm), seconds=len(pcm)/rate, windows=[])
        assert stats['pcm_sha256'] == part['sha256']
        recordings.append((part, pcm, rate))
        # Preserve maximal stereo constant runs, including zero-output gaps.
        edges = np.r_[0, np.flatnonzero(np.any(pcm[1:] != pcm[:-1], axis=1))+1, len(pcm)]
        runs = sorted(zip(edges[:-1], np.diff(edges)), key=lambda pair: -pair[1])
        stats['longest_constant_runs'] = [dict(start_seconds=int(start)/rate,
            seconds=int(length)/rate, value=pcm[start].tolist()) for start, length in runs[:12]]
        stats['stereo_different_frames'] = int(np.count_nonzero(pcm[:, 0] != pcm[:, 1]))
        # [target, target+1] is complete when target+1 <= duration. The
        # previous upper bound omitted the last complete second (and all
        # steady output in short captures with a ~1.5 second startup).
        for target in range(1, int(len(pcm)/rate)):
            indices = [int(np.argmin(abs(positions-(part['first_frame']+(target+i)*rate))))
                       for i in (0, 1)]
            left, right = (observed[index] for index in indices)
            lo, hi = (packet['next_frame']-part['first_frame'] for packet in (left, right))
            if hi <= lo: continue
            seconds = (hi-lo)/rate
            window = dict(target_second=target, from_seconds=lo/rate, to_seconds=hi/rate)
            ticks = right['request_clock']['ticks']-left['request_clock']['ticks']
            window['request_hz'] = ticks/seconds
            window['active_through_observed_packets'] = all(
                packet['enabled'] and packet['request_clock']['running']
                for packet in observed[indices[0]:indices[1]+1])
            window['channels'] = []
            for ch in range(2):
                x = pcm[lo:hi, ch].astype(float)
                power = abs(np.fft.rfft((x-x.mean())*np.hanning(len(x))))
                # An all-constant DAC latch has no AC spectral peak. argmax
                # of an all-zero spectrum would otherwise invent bin 1
                # (about 1 Hz) and mislabel a stuck sample as a low tone.
                has_ac = bool(np.any(x != x[0]))
                index = int(np.argmax(power[1:])+1) if has_ac else None
                # Store the unadjusted FFT bin. Precision is 1/window_seconds;
                # no interpolation or tone-model fitting is hidden here.
                data = dict(peak_hz=index/seconds if has_ac else None,
                            rms=float(np.sqrt(np.mean(x*x))),
                            ac_rms=float(np.sqrt(np.mean((x-x.mean())**2))))
                data.update({key: right['request_delivery'][key][ch]-left['request_delivery'][key][ch]
                             for key in left['request_delivery']})
                data['total_write_hz'] = (data['writes']+data['writes_outside_request'])/seconds
                window['channels'].append(data)
            stats['windows'].append(window)
        output['parts'].append(stats)
    output['control_capture_intervals'] = control_capture_intervals(report, recordings)
    output['dtu_request_accounting'] = dtu_request_accounting(report)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.report)
    # Refuse accidental replacement of prior evidence.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(output=str(args.output), parts=len(result['parts']),
                          playback_verified=False)))


if __name__ == '__main__':
    main()
