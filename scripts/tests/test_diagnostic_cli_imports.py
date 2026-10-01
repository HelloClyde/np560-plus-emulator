"""Catch CLI imports broken by moving shared diagnostic helpers into tests."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class DiagnosticCLIImports(unittest.TestCase):
    def test_file_switch_audio_requires_recording_and_target(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script), '--audio-start-at-file-switch']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        for extra in ([], ['--record-device-audio']):
            result = subprocess.run(command + extra, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 2)
            self.assertIn('file-switch audio capture requires recording and a target reference', result.stderr)

    def test_file_switch_position_requires_reference(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script)]
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        for extra in (['--file-switch-up-count', '1'], ['--file-switch-row-y', '92']):
            result = subprocess.run(command + extra, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 2)
            self.assertIn('file-switch positioning requires a pinned target reference', result.stderr)

    def test_eq_game_route_requires_explicit_references(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_eq_web_bundle.py'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'must-not-create'
            command = [sys.executable, '-E', str(script), '--output', str(output)]
            for argument in ('qemu', 'firmware', 'bundle', 'nand'):
                command += ['--' + argument, 'does-not-exist']
            for extra, message in ((['--npe-exit-check'], 'requires --npe-scene-check'),
                                   (['--native-sound-off'], 'requires --npe-title-check'),
                                   (['--mp3-after-game-reference', 'absent'], 'requires --npe-exit-check'),
                                   (['--npe-scene-check'], 'requires --npe-title-check'),
                                   (['--npe-title-check'], 'requires package and startup-card-reference')):
                result = subprocess.run(command + extra, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
                self.assertFalse(output.exists())

    def test_player_blank_rejects_other_ui_routes(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script), '--observe-player-blank']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        for extra in ([], ['--observe-native-codec', '--observe-ab-repeat'],
                      ['--observe-native-codec', '--inspect-player-help']):
            with self.subTest(extra=extra):
                result = subprocess.run(command + extra, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 2)
                self.assertIn('--observe-player-blank requires native codec', result.stderr)

    def test_ab_repeat_rejects_other_ui_routes(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script), '--observe-ab-repeat']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        for extra in ([], ['--observe-native-codec', '--inspect-player-help'],
                      ['--observe-native-codec', '--observe-play-controls']):
            with self.subTest(extra=extra):
                result = subprocess.run(command + extra, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 2)
                self.assertIn('--observe-ab-repeat requires native codec', result.stderr)

    def test_player_help_rejects_unrelated_routes(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script), '--inspect-player-help']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        for extra in ([], ['--observe-native-codec', '--observe-play-controls'],
                      ['--observe-native-codec', '--inspect-audio-modes']):
            with self.subTest(extra=extra):
                result = subprocess.run(command + extra, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 2)
                self.assertIn('--inspect-player-help requires native codec', result.stderr)

    def test_seek_reload_watches_reject_other_observers(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script), '--observe-seek-reload-writes']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        for extra in ([], ['--observe-seek-controls', '--record-device-audio'],
                      ['--observe-seek-controls', '--observe-state-writes']):
            with self.subTest(extra=extra):
                result = subprocess.run(command + extra, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 2)
                self.assertIn('--observe-seek-reload-writes requires seek controls', result.stderr)

    def test_seek_controls_require_transport_observer(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script), '--observe-seek-controls']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--observe-seek-controls requires play controls', result.stderr)

    def test_eq_minimize_requires_reopen_route(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script), '--minimize-with-eq']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--minimize-with-eq requires --reopen-after-minimize', result.stderr)

    def test_transport_volume_requires_transport_route(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script), '--play-controls-volume-up', '7']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--play-controls-volume-up requires --observe-play-controls', result.stderr)

    def test_roundtrip_requires_verified_playlist_route(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script)]
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        for option in ('--file-switch-eq', '--return-stereo-from-list'):
            with self.subTest(option=option):
                result = subprocess.run(command + [option], capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 2)
                self.assertIn('EQ/return switch requires', result.stderr)

    def test_long22_switch_rejects_unverified_reference(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script), '--observe-native-codec',
                   '--inspect-player-files', '--play-mono-from-list']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / 'reference.gray5'
            reference.write_bytes(bytes(240*120))
            result = subprocess.run(command + ['--switch-long22-reference', str(reference)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 2)
            self.assertIn('LONG22 reference is not', result.stderr)

    def test_redraw_trace_requires_bounded_file_selection(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script), '--trace-player-redraw']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--trace-player-redraw requires', result.stderr)

    def test_mono_switch_rejects_unverified_reference_before_opening_emulator(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script), '--observe-native-codec',
                   '--inspect-player-files']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / 'reference.gray5'
            for content, message in ((b'', 'complete gray5 frame'),
                                     (bytes(240*120), 'not the observed MONO441')):
                reference.write_bytes(content)
                result = subprocess.run(command + ['--switch-mono-reference', str(reference)],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)

    def test_file_picker_inspection_rejects_missing_or_exited_player(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script), '--inspect-player-files']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        for options in ([], ['--observe-native-codec', '--observe-player-back'],
                        ['--observe-native-codec', '--observe-player-minimize']):
            with self.subTest(options=options):
                result = subprocess.run(command + options, capture_output=True,
                                        text=True, timeout=20)
                self.assertEqual(result.returncode, 2)
                self.assertIn('--inspect-player-files requires', result.stderr)

    def test_player_rejects_malformed_fixture_pin_before_opening_inputs(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script)]
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        for digest in ('', 'f'*63, 'g'*64, 'f'*65):
            with self.subTest(digest=digest):
                result = subprocess.run(command + ['--expected-nand-sha256', digest],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 2)
                self.assertIn('--expected-nand-sha256 must', result.stderr)

    def test_reopen_profile_requires_native_player(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script), '--profile-audio-reopen']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--profile-audio-reopen requires', result.stderr)
        command[3] = '--profile-audio-reopen-stack'
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--profile-audio-reopen-stack requires', result.stderr)

    def test_reopen_profile_window_is_bounded(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        command = [sys.executable, '-E', str(script)]
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            command += ['--' + argument, 'does-not-exist']
        for seconds in ('0', '-1', '121'):
            result = subprocess.run(command + ['--profile-audio-reopen-seconds', seconds],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 2)
            self.assertIn('--profile-audio-reopen-seconds: invalid choice', result.stderr)

    def test_poll_comparison_rejects_confounded_or_missing_windows(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        base = [sys.executable, '-E', str(script), '--compare-audio-poll']
        for argument in ('qemu', 'firmware', 'soc-rom', 'nand-checkpoint', 'package', 'output'):
            base += ['--' + argument, 'does-not-exist']
        with tempfile.TemporaryDirectory() as cwd:
            for options in ([], ['--speed-window-seconds', '15'],
                            ['--speed-window-seconds', '15', '--observe-native-codec',
                             '--record-device-audio']):
                with self.subTest(options=options):
                    result = subprocess.run(base + options, cwd=cwd, capture_output=True,
                                            text=True, timeout=20)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn('--compare-audio-poll requires', result.stderr)

    def test_standalone_help_without_discovery_or_pythonpath(self):
        scripts = Path(__file__).resolve().parents[1]
        # Separate processes and an unrelated cwd prevent test discovery's
        # sys.path mutations from concealing broken real CLI entry points.
        with tempfile.TemporaryDirectory() as cwd:
            for name in ("probe_np560_mp3_player_heap.py", "probe_np560_mp3_setup.py",
                         "probe_np560_npe_audio_contract.py",
                         "verify_np560_natural_menu_web.py",
                         "verify_np560_direct_menu_web.py"):
                with self.subTest(script=name):
                    result = subprocess.run(
                        [sys.executable, "-E", str(scripts / name), "--help"],
                        cwd=cwd, capture_output=True, text=True, timeout=20,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
