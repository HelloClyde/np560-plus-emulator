#!/usr/bin/env python3
"""Offline guards for control coverage and distinct DTU/request counters."""

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import unittest
import json

import numpy as np

from analyze_np560_audio_delivery import (control_capture_intervals, dtu_request_accounting,
                                         volume_capture_intervals, volume_transition_intervals,
                                         unpaused_capture_windows, silence_control_alignment,
                                         match_pcm_change_sequences, measure_pcm_change_timing)
from analyze_np560_audio_delivery import repeat_capture_intervals


class AudioEvidenceTests(unittest.TestCase):
    def test_repeat_pcm_coverage_and_zero_gaps(self):
        sample = lambda n, g=2: dict(device_audio=dict(next_frame=n, generation=g))
        report = dict(native_codec_samples={'25-repeat-B': sample(10),
                                           '26-repeat-0': sample(16)})
        part = dict(generation=2, first_frame=10, next_frame=16)
        pcm = np.array([[1,1], [0,0], [0,0], [-32768,2], [4,4], [4,4]], dtype=np.int16)
        result = repeat_capture_intervals(report, [(part, pcm, 1000)])[0]
        self.assertTrue(result['covered'])
        self.assertEqual(result['nonzero_frames'], 4)
        self.assertEqual(result['peak'], [32768,4])
        self.assertEqual(result['longest_zero_ms'], 2)
        self.assertEqual(result['longest_constant_ms'], 2)
        self.assertFalse(result['audio_correctness_verified'])
        silent = repeat_capture_intervals(report, [(part, np.zeros_like(pcm), 1000)])[0]
        self.assertEqual(silent['nonzero_frames'], 0)
        self.assertEqual(silent['longest_zero_ms'], 6)
        stuck = repeat_capture_intervals(report, [(part, np.ones_like(pcm), 1000)])[0]
        self.assertEqual(stuck['nonzero_frames'], 6)
        self.assertEqual(stuck['longest_constant_ms'], 6)
        self.assertFalse(stuck['audio_correctness_verified'])
        self.assertFalse(repeat_capture_intervals(report, [(part, pcm[:-1], 1000)])[0]['covered'])
        split = dict(generation=2, first_frame=11, next_frame=16)
        self.assertFalse(repeat_capture_intervals(report, [(split, pcm[1:], 1000)])[0]['covered'])
        report['native_codec_samples']['26-repeat-0'] = sample(16,3)
        self.assertFalse(repeat_capture_intervals(report, [(part, pcm, 1000)])[0]['covered'])

    def test_volume_transition_includes_short_spike_before_settled_tail(self):
        label = '06-volume-down-7'
        sample = lambda n: dict(device_audio=dict(next_frame=n, generation=2))
        report = dict(native_codec_samples={label+'-before': sample(10), label+'-1': sample(20)})
        part = dict(generation=2, first_frame=10, next_frame=20)
        pcm = np.zeros((10, 2), dtype=np.int16)
        pcm[2, 0] = -32768
        check = lambda: volume_transition_intervals(report, [(part, pcm, 48000)])[label+'-before']
        self.assertEqual(check()['peak'], [32768, 0])
        self.assertEqual(check()['last_nonzero_frame'], 12)
        self.assertEqual(check()['trailing_zero_frames'], 7)
        self.assertFalse(check()['ramp_correctness_verified'])
        part['next_frame'] = 21
        self.assertFalse(check()['covered'])
        part['next_frame'] = 20
        part['generation'] = 3
        self.assertFalse(check()['covered'])
        part['generation'] = 2
        pcm[:] = 0
        self.assertIsNone(check()['last_nonzero_frame'])
        self.assertEqual(check()['trailing_zero_frames'], 10)

    def test_volume_mute_requires_covered_zero_pcm_and_settled_endpoints(self):
        label = '06-volume-down-1'
        sample = lambda frame: dict(volume_bytes='00006400',
                                    device_audio=dict(generation=2, next_frame=frame))
        report = dict(native_codec_samples={label+'-delivered': sample(10), label+'-1': sample(20)})
        part = dict(generation=2, first_frame=10, next_frame=20)
        pcm = np.zeros((10, 2), dtype=np.int16)
        check = lambda: volume_capture_intervals(report, [(part, pcm, 48000)])[label+'-delivered']
        self.assertTrue(check()['zero_level_silence_verified'])
        pcm[4, 1] = -32768
        self.assertEqual(check()['peak'], [0, 32768])
        self.assertFalse(check()['zero_level_silence_verified'])
        pcm[4, 1] = 0
        part['generation'] = 3
        self.assertFalse(check()['covered'])
        part['generation'] = 2
        part['next_frame'] = 21  # claimed coverage exceeds actual data
        self.assertFalse(check()['covered'])
        part['next_frame'] = 20
        report['native_codec_samples'][label+'-1']['volume_bytes'] = '01016400'
        self.assertFalse(check()['covered'])
        report['native_codec_samples'][label+'-delivered']['volume_bytes'] = '01016400'
        pcm[:] = 12
        self.assertTrue(check()['covered'])
        self.assertFalse(check()['gain_correctness_verified'])
        self.assertFalse(check()['zero_level_silence_verified'])

    def test_volume_snapshot_uses_dmcu_high_byte_for_current(self):
        label = '06-volume-up-7'
        samples = {
            label+'-delivered': dict(volume_bytes='07076400'),
            label+'-1': dict(volume_bytes='07036400'),
        }
        result = volume_capture_intervals(dict(native_codec_samples=samples), [])[label+'-delivered']
        self.assertEqual(result['volume_start'], dict(current=7, target=7))
        self.assertEqual(result['volume_end'], dict(current=3, target=7))
        self.assertFalse(result['covered'])

    def test_change_timing_rejects_long_hold_and_wrong_rate(self):
        ref = np.array([[0, 0], [1, -1], [2, -2], [3, -3], [0, 0]], dtype=np.int16)
        actual = np.repeat(ref, [100, 2, 2, 2, 500], axis=0)
        check = lambda x: measure_pcm_change_timing(ref, x, 24000, 48000)
        hit = check(actual)['matches'][0]
        self.assertTrue(hit['consistent_with_uniform_held_dac'])
        self.assertEqual(hit['interior_first_frame'], 100)
        self.assertEqual(hit['net_drift_frames'], 0)
        self.assertFalse(check(actual)['boundary_holds_verified'])
        self.assertFalse(check(actual)['sample_timing_verified'])
        delayed = np.repeat(ref, [100, 2, 22, 2, 500], axis=0)
        hit = check(delayed)['matches'][0]
        self.assertEqual(hit['worst_interval_error_frames'], 20)
        self.assertFalse(hit['consistent_with_uniform_held_dac'])
        hit = check(np.repeat(ref, 3, axis=0))['matches'][0]
        self.assertFalse(hit['consistent_with_uniform_held_dac'])
        for rate in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                measure_pcm_change_timing(ref, actual, rate, 48000)
        short = measure_pcm_change_timing(ref[:2], actual, 24000, 48000)
        self.assertFalse(short['matches'][0]['interior_timing_measurable'])

    def test_change_timing_accepts_fractional_capture_phase(self):
        values = np.arange(1, 301, dtype=np.int16)
        ref = np.column_stack((values, -values))
        # Synthetic ideal held DAC at 44.1k captured at 48k, unknown phase.
        index = np.floor((np.arange(327)+0.3)*44100/48000).astype(int)
        actual = ref[index]
        result = measure_pcm_change_timing(ref, actual, 44100, 48000)
        self.assertTrue(result['matches'][0]['consistent_with_uniform_held_dac'])
        self.assertFalse(result['playback_correctness_verified'])

    def test_change_order_distinguishes_content_from_repeated_value_timing(self):
        ref = np.array([[0, 0], [1, -1], [1, -1], [2, -2], [0, 0]], dtype=np.int16)
        actual = np.repeat(ref, [3, 1, 5, 2, 8], axis=0)
        result = match_pcm_change_sequences(ref, actual)
        self.assertEqual(result['reference_changes'], 4)
        self.assertEqual(result['matches'], [dict(first_frame=0, last_change_frame=11)])
        self.assertFalse(result['sample_timing_verified'])
        self.assertFalse(result['playback_correctness_verified'])
        actual[9, 1] = 7
        self.assertEqual(match_pcm_change_sequences(ref, actual)['matches'], [])
        for invalid in (np.zeros((4, 2), dtype=np.int16), ref[:0]):
            with self.assertRaises(ValueError):
                match_pcm_change_sequences(invalid, actual)
        with self.assertRaises(ValueError):
            match_pcm_change_sequences(ref.astype(np.float64), actual)

    def test_silence_partition_requires_real_pcm_and_same_generation(self):
        interval = dict(generation=2, off={'frame': 14}, on={'frame': 17},
                        disabled_ms=3.0, writes_since_previous_close=[8, 8])
        evidence = {'disabled_intervals': [interval]}
        pcm = np.ones((12, 2), dtype=np.int16)
        pcm[2:9] = 0
        part = dict(generation=2, first_frame=10, next_frame=22)
        check = lambda: silence_control_alignment(evidence, [(part, pcm, 1000)])
        row = check()[0]
        self.assertEqual((row['before_off_ms'], row['disabled_ms'], row['after_on_ms']),
                         (2.0, 3.0, 2.0))
        self.assertTrue(row['zero_run_bounded'])
        self.assertEqual(json.loads(json.dumps(row)), row)
        self.assertFalse(row['cause_verified'])
        pcm[5, 1] = 1
        self.assertEqual(check(), [])  # one nonzero lane prevents a silence claim
        pcm[5, 1] = 0
        part['generation'] = 3
        self.assertEqual(check(), [])
        part['generation'] = 2
        pcm[:2] = 0
        self.assertFalse(check()[0]['zero_run_bounded'])
        part['next_frame'] += 1
        self.assertEqual(check(), [])  # inconsistent/missing capture data

    def test_unpaused_window_excludes_setup_and_rejects_gaps_or_generation_changes(self):
        window = dict(label='player', audio_first_frame=12, audio_next_frame=18,
                      audio_generation_before=2, audio_generation_after=2)
        report = {'speed_windows': [window]}
        part = dict(first_frame=10, next_frame=20, generation=2)
        pcm = np.ones((10, 2), dtype=np.int16)
        pcm[3:5] = 0
        pcm[6, 1] = 2
        check = lambda p: unpaused_capture_windows(report, [(p, pcm, 48000)])[0]
        observed = check(part)
        self.assertTrue(observed['covered'])
        self.assertEqual(observed['frames'], 6)
        self.assertEqual(observed['longest_zero_run_frames'], 2)
        self.assertEqual(observed['unequal_channel_frames'], 1)
        self.assertFalse(observed['playback_correctness_verified'])
        self.assertFalse(check(dict(part, first_frame=13))['covered'])
        self.assertFalse(check(dict(part, next_frame=17))['covered'])
        window['audio_generation_after'] = 3
        self.assertFalse(check(part)['covered'])
        self.assertEqual(unpaused_capture_windows({}, []), [])

    def test_control_requires_continuous_same_generation_silence(self):
        sample = lambda n: {'device_audio': {'next_frame': n, 'generation': 2}}
        report = {'native_codec_samples': {
            '06-pause-delivered': sample(12), '06-pause-3': sample(18)}}
        part = dict(first_frame=10, next_frame=20, generation=2)
        pcm = np.zeros((10, 2), dtype=np.int16)
        check = lambda p: control_capture_intervals(report, [(p, pcm, 48000)])['pause']
        self.assertTrue(check(part)['continuous_silence_verified'])
        self.assertFalse(check(dict(part, next_frame=17))['covered'])
        self.assertFalse(check(dict(part, generation=3))['covered'])
        pcm[3, 1] = 1
        self.assertFalse(check(part)['continuous_silence_verified'])

    def test_latched_transfer_is_not_callback_write(self):
        report = {'native_codec_samples': {'resume': {
            'transport': {'dtu-state': 'CH0:8204/281724/489 CH1:8204/281724/489'},
            'device_audio': {'request_delivery': {'writes': [281723, 281723]}}}}}
        result = dtu_request_accounting(report)['resume']
        self.assertEqual([x['difference'] for x in result], [1, 1])
        self.assertEqual(dtu_request_accounting({}), {})


if __name__ == '__main__':
    unittest.main()
