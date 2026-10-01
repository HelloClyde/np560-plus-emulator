"""Reject incomplete player transport observations, even when keys were delivered."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from probe_np560_mp3_player_heap import validate_transport_samples


class TransportSamplesTests(unittest.TestCase):
    def setUp(self):
        self.samples = {}
        for action, count, state, enabled in (
                ('play', 6, 1, True), ('pause', 3, 2, False),
                ('resume', 6, 1, True), ('stop', 3, 0, False)):
            for n in range(1, count + 1):
                self.samples[f'06-{action}-{n}'] = dict(
                    player={'state_087c': state}, device_audio={'enabled': enabled},
                    rom_mp3_hle=dict(frames=n if enabled else 10, failures=0,
                                     input_space_failures=0, pcm_copy_failures=0,
                                     final_frame_failures=0))

    def test_complete_states(self):
        self.assertEqual(len(validate_transport_samples(self.samples)), 4)

    def test_pause_not_only_a_picture(self):
        self.samples['06-pause-2']['device_audio']['enabled'] = True
        with self.assertRaisesRegex(AssertionError, 'DAC state'):
            validate_transport_samples(self.samples)

    def test_stopped_decode_cannot_continue(self):
        self.samples['06-stop-2']['rom_mp3_hle']['frames'] += 1
        with self.assertRaisesRegex(AssertionError, 'still advancing'):
            validate_transport_samples(self.samples)

    def test_resume_must_advance(self):
        self.samples['06-resume-2']['rom_mp3_hle']['frames'] = 1
        with self.assertRaisesRegex(AssertionError, 'stalled'):
            validate_transport_samples(self.samples)

    def test_codec_errors_are_not_success(self):
        self.samples['06-play-3']['rom_mp3_hle']['pcm_copy_failures'] = 1
        with self.assertRaisesRegex(AssertionError, 'codec failure'):
            validate_transport_samples(self.samples)


if __name__ == '__main__':
    unittest.main()
