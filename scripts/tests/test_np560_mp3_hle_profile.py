"""Check build preset selection without firmware or native codec execution."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_np560_mp3_hle import parse_args


class ProfileTests(unittest.TestCase):
    def test_player_enables_complete_tested_combination(self):
        args = parse_args(['--resident-bundle', 'input', '--output', 'output',
                           '--profile', 'player'])
        for flag in ('hle_free_words', 'deferred_input_retirement', 'hle_pcm_copy',
                     'final_frame', 'priming', 'arena_release', 'compact_workspace'):
            self.assertTrue(getattr(args, flag), flag)
        self.assertFalse(args.audio_mode_parameters)
        self.assertFalse(args.audio_mode_dsp)

    def test_dsp_extension_is_explicit(self):
        base = ['--resident-bundle', 'input', '--output', 'output', '--profile', 'player']
        with self.assertRaises(SystemExit):
            parse_args(base + ['--audio-mode-dsp'])
        args = parse_args(base + ['--audio-mode-parameters', '--audio-mode-dsp'])
        self.assertTrue(args.audio_mode_dsp)

    def test_parameter_only_extension_is_explicit(self):
        args = parse_args(['--resident-bundle', 'input', '--output', 'output',
                           '--profile', 'player', '--audio-mode-parameters'])
        self.assertTrue(args.audio_mode_parameters)
        self.assertTrue(args.priming)

    def test_default_keeps_legacy_selection(self):
        args = parse_args(['--resident-bundle', 'input', '--output', 'output'])
        self.assertEqual(args.profile, 'manual')
        self.assertFalse(args.priming)
        self.assertFalse(args.compact_workspace)
        self.assertFalse(args.arena_release)

    def test_manual_prerequisites_still_apply(self):
        with self.assertRaises(SystemExit):
            parse_args(['--resident-bundle', 'input', '--output', 'output',
                        '--compact-workspace'])


if __name__ == '__main__':
    unittest.main()
