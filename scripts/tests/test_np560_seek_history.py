"""Reject late, unbounded or unexplained loss; don't erase raw failures."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from probe_np560_mp3_player_heap import validate_seek_history


class SeekHistoryTests(unittest.TestCase):
    def setUp(self):
        self.before = dict(calls=[3], frames=100)
        self.after = dict(calls=[4], frames=130, failures=2,
            input_space_failures=0, pcm_copy_failures=0, final_frame_failures=0,
            codec_results=dict(ok=130,no_pcm=2,bad_header=0,bad_crc=0,decode_error=0),
            no_pcm_reasons=dict(missing_history=2,invalid_sideinfo=0,unknown=0),
            history_recovery=dict(startup_frames=2,after_output=0,no_progress=0,max_startup_frames=2))

    def test_bounded_evidenced_history(self):
        original = copy.deepcopy(self.after)
        result = validate_seek_history(self.before, self.after, 2)
        self.assertEqual(result['raw_failures'], 2)
        self.assertEqual(self.after, original)

    def test_reject_each_insufficient_contract(self):
        cases = [('history_recovery','after_output',1),
                 ('history_recovery','no_progress',1),
                 ('history_recovery','max_startup_frames',3),
                 ('history_recovery','startup_frames',1),
                 ('no_pcm_reasons','invalid_sideinfo',1),
                 ('no_pcm_reasons','unknown',1),
                 ('codec_results','bad_crc',1)]
        for group, field, value in cases:
            sample = copy.deepcopy(self.after)
            sample[group][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                validate_seek_history(self.before, sample, 2)
        for field, value in [('calls',[3]),('frames',100),('failures',3),('pcm_copy_failures',1)]:
            sample = copy.deepcopy(self.after)
            sample[field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                validate_seek_history(self.before, sample, 2)

    def test_unknown_fixture_has_no_warmup_allowance(self):
        with self.assertRaises(AssertionError):
            validate_seek_history(self.before, self.after, 0)


if __name__ == '__main__':
    unittest.main()
