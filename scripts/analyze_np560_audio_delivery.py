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


def volume_capture_intervals(report, recordings):
    """Measure real PCM between matching settled volume endpoint observations.

    Nonzero output alone does not verify a nonzero level's gain curve.
    Missing/truncated recordings must never count as successful mute.
    """
    samples = report.get('native_codec_samples', {})
    results = {}
    for label, sample in samples.items():
        if not label.startswith('06-volume-') or not label.endswith('-delivered'):
            continue
        end = samples.get(label[:-len('-delivered')] + '-1', {})
        result = dict(covered=False, zero_level_silence_verified=False,
                      gain_correctness_verified=False)
        results[label] = result
        try:
            first_volume = bytes.fromhex(sample.get('volume_bytes', ''))
            last_volume = bytes.fromhex(end.get('volume_bytes', ''))
        except ValueError:
            continue
        if len(first_volume) == 4 and len(last_volume) == 4:
            # Snapshot bytes are physical little-endian storage. Logical
            # DMCU byte 4A64 is the high lane, i.e. the current volume.
            result['volume_start'] = dict(current=first_volume[1], target=first_volume[0])
            result['volume_end'] = dict(current=last_volume[1], target=last_volume[0])
        if (len(first_volume) != 4 or len(last_volume) != 4 or
                first_volume[:2] != last_volume[:2] or
                first_volume[0] != first_volume[1] or first_volume[0] > 7):
            continue
        result['level'] = first_volume[0]
        start_audio, end_audio = sample.get('device_audio', {}), end.get('device_audio', {})
        lo, hi = start_audio.get('next_frame'), end_audio.get('next_frame')
        if lo is None or hi is None or hi <= lo:
            continue
        for part, pcm, rate in recordings:
            if (start_audio.get('generation') != end_audio.get('generation') or
                    start_audio.get('generation') != part['generation'] or
                    not part['first_frame'] <= lo < hi <= part['next_frame'] or
                    len(pcm) != part['next_frame'] - part['first_frame']):
                continue
            window = pcm[lo-part['first_frame']:hi-part['first_frame']].astype(np.int32)
            nonzero = int(np.count_nonzero(window))
            result.update(covered=True, first_frame=lo, next_frame=hi, frames=len(window),
                          seconds=len(window)/rate, nonzero_values=nonzero,
                          peak=np.max(np.abs(window), axis=0).tolist(),
                          zero_level_silence_verified=first_volume[0] == 0 and nonzero == 0)
            break
    return results


def volume_transition_intervals(report, recordings):
    """Measure the whole pre-key through settled interval, not just its tail.

    Peak and last nonzero position are evidence, not a gain/ramp verdict.
    The snapshot precedes key delivery, so latency is not key-to-silence time.
    """
    samples = report.get('native_codec_samples', {})
    results = {}
    for label, sample in samples.items():
        if not label.startswith('06-volume-') or not label.endswith('-before'):
            continue
        end = samples.get(label[:-len('-before')] + '-1', {})
        result = dict(covered=False, ramp_correctness_verified=False)
        results[label] = result
        start_audio, end_audio = sample.get('device_audio', {}), end.get('device_audio', {})
        lo, hi = start_audio.get('next_frame'), end_audio.get('next_frame')
        if lo is None or hi is None or hi <= lo:
            continue
        for part, pcm, rate in recordings:
            if (start_audio.get('generation') != end_audio.get('generation') or
                    start_audio.get('generation') != part['generation'] or
                    not part['first_frame'] <= lo < hi <= part['next_frame'] or
                    len(pcm) != part['next_frame'] - part['first_frame']):
                continue
            window = pcm[lo-part['first_frame']:hi-part['first_frame']].astype(np.int32)
            nonzero = np.flatnonzero(np.any(window != 0, axis=1))
            last = int(nonzero[-1]) if len(nonzero) else -1
            result.update(covered=True, first_frame=lo, next_frame=hi,
                          frames=len(window), seconds=len(window)/rate,
                          peak=np.max(np.abs(window), axis=0).tolist(),
                          nonzero_values=int(np.count_nonzero(window)),
                          last_nonzero_frame=lo+last if last >= 0 else None,
                          trailing_zero_frames=len(window)-last-1,
                          trailing_zero_seconds=(len(window)-last-1)/rate)
            break
    return results


def match_pcm_change_sequences(reference, actual):
    """Exact stereo change-order matches; repeated-value timing is discarded.

    This does NOT prove sample counts, duration, analog output or reference
    decoder correctness. The caller must independently check those facts.
    """
    for pcm in (reference, actual):
        if pcm.ndim != 2 or pcm.shape[1] != 2 or pcm.dtype.kind != 'i' or pcm.dtype.itemsize != 2:
            raise ValueError('expected Nx2 signed PCM16 arrays')
    if not len(reference) or not len(actual):
        raise ValueError('empty PCM cannot establish a sequence match')
    def changes(pcm):
        return np.r_[0, np.flatnonzero(np.any(pcm[1:] != pcm[:-1], axis=1))+1]
    ri, ai = changes(reference), changes(actual)
    if len(ri) < 2:
        raise ValueError('constant reference cannot establish playback order')
    needle = reference[ri].astype('<i2').tobytes()
    haystack = actual[ai].astype('<i2').tobytes()
    hits, cursor = [], 0
    while True:
        offset = haystack.find(needle, cursor)
        if offset < 0:
            break
        if offset % 4 == 0:
            first = offset // 4
            hits.append(dict(first_frame=int(ai[first]),
                             last_change_frame=int(ai[first+len(ri)-1])))
        cursor = offset + 1
    return dict(reference_frames=len(reference), reference_changes=len(ri),
                actual_frames=len(actual), matches=hits,
                sample_timing_verified=False, playback_correctness_verified=False)


def measure_pcm_change_timing(reference, actual, reference_rate, actual_rate):
    """Measure interior change timing without fitting away drift or pauses.

    A held-value DAC captured at another rate quantizes edges. Compare every
    edge to the declared rate ratio with only an additive alignment. Exclude
    the first run (it may merge with preceding silence) and the final hold
    (its end is not established by a change-order match). No resampling.
    """
    if (not np.isfinite(reference_rate) or not np.isfinite(actual_rate) or
            reference_rate <= 0 or actual_rate <= 0):
        raise ValueError('positive finite sample rates required')
    result = match_pcm_change_sequences(reference, actual)
    ri = np.r_[0, np.flatnonzero(np.any(reference[1:] != reference[:-1], axis=1))+1]
    ai = np.r_[0, np.flatnonzero(np.any(actual[1:] != actual[:-1], axis=1))+1]
    ratio = actual_rate / reference_rate
    for hit in result['matches']:
        first = int(np.searchsorted(ai, hit['first_frame']))
        observed = ai[first+1:first+len(ri)]
        expected = ri[1:] * ratio
        hit['interior_timing_measurable'] = len(observed) >= 2
        if len(observed) < 2:
            continue
        # Relative error range permits any sub-frame capture phase, but not
        # a slope fit that could disguise a wrong playback sample rate.
        residual = (observed-observed[0]) - (expected-expected[0])
        interval_error = np.diff(observed) - np.diff(expected)
        worst = int(np.argmax(np.abs(interval_error)))
        span = float(np.ptp(residual))
        hit.update(interior_first_frame=int(observed[0]),
                   interior_last_frame=int(observed[-1]),
                   interior_intervals=len(observed)-1,
                   interior_expected_seconds=float((ri[-1]-ri[1])/reference_rate),
                   interior_observed_seconds=float((observed[-1]-observed[0])/actual_rate),
                   edge_error_span_frames=span,
                   edge_error_span_ms=span*1000/actual_rate,
                   net_drift_frames=float(residual[-1]),
                   worst_interval_first_frame=int(observed[worst]),
                   worst_interval_error_frames=float(interval_error[worst]),
                   consistent_with_uniform_held_dac=bool(span <= 1.0+1e-9))
    result.update(reference_rate=reference_rate, actual_rate=actual_rate,
                  boundary_holds_verified=False,
                  timing_model='declared-rate zero-order hold; <=1 capture-frame edge error span')
    return result


def silence_control_alignment(evidence, recordings):
    """Partition a real zero run around observed DAC off/on; no causal claim."""
    results = []
    for part, pcm, rate in recordings:
        if len(pcm) != part['next_frame'] - part['first_frame']:
            continue
        silent = np.all(pcm == 0, axis=1)
        edges = np.diff(np.r_[False, silent, False].astype(np.int8))
        spans = list(zip(np.flatnonzero(edges == 1) + part['first_frame'],
                         np.flatnonzero(edges == -1) + part['first_frame']))
        for interval in (evidence or {}).get('disabled_intervals', []):
            if interval['generation'] != part['generation']:
                continue
            off, on = interval['off']['frame'], interval['on']['frame']
            for first, last in spans:
                if first <= off < on <= last:
                    results.append(dict(generation=part['generation'],
                        first_frame=int(first), next_frame=int(last),
                        # A part edge can truncate the zero run. Keep that
                        # distinction even when the off/on interval is covered.
                        zero_run_bounded=bool(first > part['first_frame'] and
                                              last < part['next_frame']),
                        before_off_ms=(off-int(first))*1000/rate,
                        disabled_ms=interval['disabled_ms'],
                        after_on_ms=(int(last)-on)*1000/rate,
                        writes_since_previous_close=interval.get('writes_since_previous_close'),
                        cause_verified=False))
                    break
    return results


def repeat_capture_intervals(report, recordings):
    """Measure complete DAC ranges between AB observations, without filling gaps."""
    labels = ['25-repeat-B'] + [f'26-repeat-{i}' for i in range(10)] + [
        '27-repeat-cancel', '28-repeat-canceled-progress']
    return pcm_capture_intervals(report, recordings, labels)


def pcm_capture_intervals(report, recordings, labels):
    """Read-only PCM coverage/statistics between explicitly named observations."""
    samples = report.get('native_codec_samples', {})
    results = []
    for left, right in zip(labels, labels[1:]):
        if left not in samples or right not in samples:
            continue
        a, b = samples[left]['device_audio'], samples[right]['device_audio']
        lo, hi = a['next_frame'], b['next_frame']
        item = dict(before=left, after=right, covered=False,
                    first_frame=lo, next_frame=hi, audio_correctness_verified=False)
        results.append(item)
        if a['generation'] != b['generation'] or hi <= lo:
            continue
        for part, pcm, rate in recordings:
            if (part['generation'] != a['generation'] or
                    not part['first_frame'] <= lo < hi <= part['next_frame'] or
                    len(pcm) != part['next_frame'] - part['first_frame']):
                continue
            values = pcm[lo-part['first_frame']:hi-part['first_frame']].astype(np.int32)
            zeros = np.all(values == 0, axis=1)
            edges = np.diff(np.r_[False, zeros, False].astype(np.int8))
            lengths = np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)
            changes = np.r_[0, np.flatnonzero(np.any(values[1:] != values[:-1], axis=1))+1, len(values)]
            item.update(covered=True, seconds=len(values)/rate,
                        nonzero_frames=int(np.count_nonzero(~zeros)),
                        peak=np.max(np.abs(values), axis=0).tolist(),
                        longest_zero_ms=float(np.max(lengths, initial=0))*1000/rate,
                        longest_constant_ms=float(np.max(np.diff(changes)))*1000/rate)
            break
    return results


def analyze(report_path, artifact_directory=None):
    # Explicit relocation for a WSL-generated capture inspected on Windows.
    # Never rewrite the source report or silently search other recordings.
    def artifact(value):
        return (Path(artifact_directory) / Path(value).name
                if artifact_directory is not None else Path(value))
    report = json.loads(report_path.read_text(encoding='utf-8'))
    capture = report['device_audio_capture']
    packets = json.loads(artifact(capture['request_delivery_path']).read_text(encoding='utf-8'))
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
        path = artifact(part['path'])
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
    output['repeat_capture_intervals'] = repeat_capture_intervals(report, recordings)
    output['blank_capture_intervals'] = pcm_capture_intervals(report, recordings, [
        '30-before-blank','31-blank-start','31-blank-end','32-restored-start','32-restored-end'])
    output['volume_capture_intervals'] = volume_capture_intervals(report, recordings)
    output['volume_transition_intervals'] = volume_transition_intervals(report, recordings)
    output['silence_control_alignment'] = silence_control_alignment(evidence, recordings)
    output['dtu_request_accounting'] = dtu_request_accounting(report)
    output['unpaused_capture_windows'] = unpaused_capture_windows(report, recordings)
    return output


def unpaused_capture_windows(report, recordings):
    """Describe only PCM covered by a recorded, same-generation run window."""
    result = []
    for window in report.get('speed_windows', []):
        if window.get('label') != 'player':
            continue
        first, last = window.get('audio_first_frame'), window.get('audio_next_frame')
        generation = window.get('audio_generation_before')
        item = dict(covered=False, first_frame=first, next_frame=last,
                    playback_correctness_verified=False)
        result.append(item)
        if (first is None or last is None or last <= first or generation is None or
                generation != window.get('audio_generation_after')):
            continue
        for part, pcm, rate in recordings:
            if (part['generation'] != generation or part['first_frame'] > first or
                    part['next_frame'] < last or
                    len(pcm) != part['next_frame'] - part['first_frame']):
                continue
            values = pcm[first-part['first_frame']:last-part['first_frame']]
            silent = np.all(values == 0, axis=1)
            edges = np.diff(np.r_[False, silent, False].astype(np.int8))
            lengths = np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)
            longest = int(lengths.max()) if len(lengths) else 0
            item.update(covered=True, frames=len(values), sample_rate=rate,
                        seconds=len(values)/rate,
                        pcm_sha256=hashlib.sha256(values.tobytes()).hexdigest(),
                        nonzero_samples=int(np.count_nonzero(values)),
                        longest_zero_run_frames=longest,
                        longest_zero_run_ms=longest*1000/rate,
                        unequal_channel_frames=int(np.count_nonzero(values[:, 0] != values[:, 1])))
            break
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--artifact-directory', type=Path,
                        help='explicit directory containing capture files by basename; PCM hashes still verified')
    args = parser.parse_args()
    result = analyze(args.report, args.artifact_directory)
    # Refuse accidental replacement of prior evidence.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(output=str(args.output), parts=len(result['parts']),
                          playback_verified=False)))


if __name__ == '__main__':
    main()
