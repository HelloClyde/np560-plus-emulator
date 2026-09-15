#!/usr/bin/env python3
"""Offline guards for control coverage and distinct DTU/request counters."""
import unittest

import numpy as np

from analyze_np560_audio_delivery import control_capture_intervals, dtu_request_accounting


class AudioEvidenceTests(unittest.TestCase):
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
