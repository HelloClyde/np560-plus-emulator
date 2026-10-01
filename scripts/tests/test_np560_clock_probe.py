"""Clock probe must not navigate a still-booting guest."""
import sys
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from probe_np560_clock_progress import (wait_for_daily_phrase, require_return_consumed,
                                       interactive_steps, command_file_lines, power_clock_snapshot)


class ClockProbeTests(unittest.TestCase):
    def test_power_clock_uses_core_fields_not_ram_for_sfr(self):
        emulator = Mock()
        emulator.snapshot.return_value = {'frame': 'AAAAAAAAAAA='}
        emulator.qmp.execute.return_value = 'HZ:32768 CLKCON:e410 PLL:dfff AUDIO_PLL:dfff'
        result = power_clock_snapshot(emulator)
        emulator.snapshot.assert_called_once_with('data', 0x50b840, 8, diagnostics=False)
        self.assertEqual(result['register_bytes'], {'calendar': '0000000000000000'})
        self.assertEqual(emulator.qmp.execute.call_count, 5)
        for call in emulator.qmp.execute.call_args_list:
            self.assertEqual(call.args[0], 'qom-get')
        emulator.qmp.execute.return_value = 'HZ:32768'
        with self.assertRaisesRegex(RuntimeError, 'explicit core register fields'):
            power_clock_snapshot(emulator)

    def test_command_inbox_rejects_rewriting_consumed_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'commands.txt'
            lines = command_file_lines(path)
            with patch('probe_np560_clock_progress.time.sleep',
                       side_effect=lambda _: path.write_text('54\n', encoding='utf-8')):
                self.assertEqual(next(lines), '54\n')
            path.write_text('45\n54\n', encoding='utf-8')
            with patch('probe_np560_clock_progress.time.sleep'):
                with self.assertRaisesRegex(RuntimeError, 'previously consumed'):
                    next(lines)

    def test_command_inbox_waits_for_complete_line_and_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'commands.txt'
            writes = iter(['54', '54\n'])
            with patch('probe_np560_clock_progress.time.sleep',
                       side_effect=lambda _: path.write_text(next(writes), encoding='utf-8')):
                lines = command_file_lines(path)
                self.assertEqual(next(lines), '54\n')
                lines.close()
            with self.assertRaises(TimeoutError):
                next(command_file_lines(Path(directory) / 'expired.txt', timeout=0))

    def test_interactive_validation_contact_release_and_snapshot(self):
        contacts = []
        reads = []
        def snapshot(*args, **kwargs):
            reads.append((args, kwargs))
            return {'frame': ''}
        emulator = SimpleNamespace(process=SimpleNamespace(poll=lambda: None),
                                   key_status=lambda: {'faulted': False},
                                   set_key=lambda *args, **kwargs: contacts.append(kwargs),
                                   snapshot=snapshot)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            interactive_steps(emulator, output, ['64', '-1', 'shell', '54', 'snapshot', 'q', '53'],
                              sleep=lambda _: None)
            self.assertEqual(contacts, [{'matrix_low': 0, 'matrix_high': 1 << 22},
                                        {'matrix_low': 0, 'matrix_high': 0}])
            self.assertEqual(len(list(output.glob('interactive-*.json'))), 2)
            self.assertEqual(reads.count((('data', 0x5267c8, 0x200),
                                         {'diagnostics': False})), 2)

    def test_interactive_releases_key_on_interruption(self):
        contacts = []
        emulator = SimpleNamespace(process=SimpleNamespace(poll=lambda: None),
                                   key_status=lambda: {},
                                   set_key=lambda *args, **kwargs: contacts.append(kwargs))
        def interrupted(_):
            raise KeyboardInterrupt()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KeyboardInterrupt):
                interactive_steps(emulator, Path(directory), ['4'], sleep=interrupted)
        self.assertEqual(contacts[-1], {'matrix_low': 0, 'matrix_high': 0})

    def test_observer_step_rejects_missing_or_negative_index(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_clock_progress.py'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'unused'
            for index in ('-1', '1'):
                result = subprocess.run([sys.executable, str(script), '--output', str(output),
                                         '--matrix-step', '53', '--return-key',
                                         '--full-observer-step', index],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 2)
                self.assertIn('--full-observer-step', result.stderr)
                self.assertFalse(output.exists())

    def test_journal_seed_requires_matching_pin_before_output_creation(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_clock_progress.py'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.npj'
            source.write_bytes(b'not a journal')
            output = Path(directory) / 'unused'
            for args in (['--journal-seed', str(source)],
                         ['--expected-journal-sha256', '0'*64],
                         ['--journal-seed', str(source), '--expected-journal-sha256', '0'*64]):
                result = subprocess.run([sys.executable, str(script), '--output', str(output), *args],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(output.exists())
                self.assertEqual(source.read_bytes(), b'not a journal')

    def test_invalid_step_delays_rejected_before_output_creation(self):
        script = Path(__file__).resolve().parents[1] / 'probe_np560_clock_progress.py'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'unused'
            for values in (['0:0'], ['0:nan'], ['1:5'], ['0:5', '0:6']):
                command = [sys.executable, str(script), '--output', str(output),
                           '--matrix-step', '53', '--return-key']
                for value in values:
                    command += ['--settle-step', value]
                result = subprocess.run(command, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 2)
                self.assertIn('--settle-step requires', result.stderr)
                self.assertFalse(output.exists())

    def fake(self, states, exitcode=None):
        values = iter(states)
        return SimpleNamespace(key_status=lambda: next(values),
                               process=SimpleNamespace(poll=lambda: exitcode))

    def test_waits_for_state_and_guest_time(self):
        states = [dict(application_state=0, virtual_time_ns=9_000_000_000),
                  dict(application_state=253, virtual_time_ns=1_000_000_000),
                  dict(application_state=253, virtual_time_ns=8_000_000_000)]
        sleeps = []
        result = wait_for_daily_phrase(self.fake(states), now=lambda: 0, sleep=sleeps.append)
        self.assertEqual(result, states[-1])
        self.assertEqual(len(sleeps), 2)

    def test_timeout_and_fault(self):
        with self.assertRaises(TimeoutError):
            wait_for_daily_phrase(self.fake([{}]), timeout=0)
        with self.assertRaises(RuntimeError):
            wait_for_daily_phrase(self.fake([dict(faulted=True)]))
        with self.assertRaises(RuntimeError):
            wait_for_daily_phrase(self.fake([{}], exitcode=0))

    def test_requires_new_correct_ack(self):
        before = dict(modal_acknowledgements=2)
        for after in (dict(modal_acknowledgements=2, modal_acknowledgement=0x8e),
                      dict(modal_acknowledgements=3, modal_acknowledgement=0x86)):
            with self.assertRaises(RuntimeError):
                require_return_consumed(before, after)
        require_return_consumed(before, dict(modal_acknowledgements=3,
                                            modal_acknowledgement=0x8e))


if __name__ == '__main__':
    unittest.main()
