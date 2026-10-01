"""Capture evidence checks: never bridge gaps or trust a stale artifact."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_np560_eq_capture import analyze


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        raw = struct.pack('<4h', 100, -200, 200, -400)
        with wave.open(str(self.root/'audio.wav'), 'wb') as wav:
            wav.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            wav.writeframes(raw)
        self.report = {'device_audio_capture': {'error': None, 'parts': [
            dict(path='/linux/audio.wav', generation=1, first_frame=0, next_frame=2,
                 sha256=hashlib.sha256(raw).hexdigest())]}, 'native_codec_samples': {}}
        for name, frame in [('10-normal-start', 0), ('10-normal-end', 1),
                            ('10-audio-select', 1), ('10-audio-selected-running', 2)]:
            self.report['native_codec_samples'][name] = dict(
                device_audio=dict(generation=1, next_frame=frame), volume_bytes='0707',
                rom_mp3_hle=dict(audio_mode={}))

    def run_analysis(self):
        (self.root/'report.json').write_text(json.dumps(self.report), encoding='utf-8')
        return analyze(self.root)

    def test_measurement(self):
        result = self.run_analysis()
        self.assertEqual(result['measured_eq_over_normal_rms'], [2, 2])
        self.assertFalse(result['factory_equivalence_verified'])
        self.assertEqual(result['windows']['normal']['unequal_channel_frames'], 1)

    def test_gap_rejected(self):
        self.report['device_audio_capture']['parts'][0]['first_frame'] = 1
        with self.assertRaisesRegex(ValueError, 'coverage'):
            self.run_analysis()

    def test_changed_recording_rejected(self):
        self.report['device_audio_capture']['parts'][0]['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'hash'):
            self.run_analysis()

    def test_reset_rejected(self):
        self.report['native_codec_samples']['10-normal-end']['device_audio']['generation'] = 2
        with self.assertRaisesRegex(ValueError, 'generation'):
            self.run_analysis()

    def test_restored_window_is_separate(self):
        samples = self.report['native_codec_samples']
        samples['10-normal-restored-start'] = samples['10-normal-start']
        samples['10-normal-restored-end'] = samples['10-normal-end']
        result = self.run_analysis()
        self.assertEqual(result['windows']['restored']['channels'],
                         result['windows']['normal']['channels'])
        self.assertEqual(result['windows']['restored']['channels'][0]['block_rms_100ms'], [])


if __name__ == '__main__':
    unittest.main()
