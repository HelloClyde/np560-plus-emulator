"""Check real speed-window boundaries without running or patching a guest."""
import ast
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from np560_host_time import thread_time_delta


class SpeedWindowTests(unittest.TestCase):
    def fixture(self, never_active=False, duty=.96, profile=False, host_profile=False,
                host_time=False, clock_changes=False):
        source = Path(__file__).resolve().parents[1] / 'probe_np560_mp3_player_heap.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        function = next(n for n in ast.walk(tree)
                        if isinstance(n, ast.FunctionDef) and n.name == 'speed_window')
        clock = SimpleNamespace(now=0.)
        clock.monotonic = lambda: clock.now
        def sleep(seconds):
            clock.now += seconds
        clock.sleep = sleep
        commands = []
        profile_enabled = False
        def execute(command, arguments=None):
            nonlocal profile_enabled
            commands.append(command)
            if command == 'query-cpus-fast':
                return [{'thread-id': 101}]
            if command == 'qom-set':
                self.assertEqual(arguments['property'], 'instruction-clock-profile-enabled')
                profile_enabled = arguments['value']
            if command == 'qom-get':
                if arguments['property'] == 'instruction-clock-profile':
                    return __import__('json').dumps(dict(enabled=profile_enabled,
                        opcodes={'ac': round(clock.now*10)-round(clock.now*5)}))
                if arguments['property'] == 'instruction-clock-state':
                    return (f'NS:{int(clock.now * 1e9)} FAULT:0 '
                            f'INSTRUCTIONS:{round(clock.now * 1000)} '
                            f'CYCLES:{round(clock.now * 4000)} '
                            f'UNKNOWN_COST:{round(clock.now * 10)} '
                            f'UNKNOWN_SRAM:{round(clock.now * 5)} '
                            f'UNKNOWN_OPCODE:{round(clock.now * 10)-round(clock.now * 5)}')
                return 'ROM_MISSING=none UNSUPPORTED=none INVALID_CONTROL=none'
        def audio():
            active = not never_active and .1 <= clock.now < 1
            return dict(enabled=active, generation=2, next_frame=int(clock.now*48000),
                        request_clock=dict(running=active, hz=0 if clock_changes and clock.now >= 1 else 1000, pll=0,
                                           ticks=int(clock.now*1000*duty)),
                        control_event_next=int(clock.now >= 1)*2, pcm='')
        report = {}
        time_reads = []
        def read_thread_time(pid, tid):
            self.assertEqual((pid, tid), (100, 101))
            time_reads.append(clock.now)
            return dict(pid=pid, tid=tid, start_ticks=1, ticks_per_second=100,
                        user_ticks=round(clock.now*75), system_ticks=0,
                        runtime_ns=round(clock.now*750000000),
                        runqueue_wait_ns=0, timeslices=round(clock.now*10))
        sampler_calls = []
        class Sampler:
            def __init__(self, tid):
                self_tid = tid
                assert self_tid == 101
            def start(self): sampler_calls.append('start')
            def stop(self):
                sampler_calls.append('stop')
                return dict(samples=[dict(ip=123, pid=100, tid=101, misc=2)], lost=0)
            def close(self): sampler_calls.append('close')
        scope = dict(args=SimpleNamespace(speed_window_seconds=1, speed_audio_poll=False,
                                         profile_unknown_cycles=profile, profile_host_cpu=host_profile,
                                         observe_host_cpu_time=host_time),
                     emulator=SimpleNamespace(qmp=SimpleNamespace(execute=execute), audio=audio,
                                              process=SimpleNamespace(pid=100),
                                              snapshot=lambda *a, **k: {}),
                     active_host_samplers=[], UserIPSampler=Sampler, sampler_calls=sampler_calls,
                     read_thread_time=read_thread_time, thread_time_delta=thread_time_delta,
                     time_reads=time_reads,
                     Path=lambda path: SimpleNamespace(is_dir=lambda: True, read_text=lambda: 'test maps'),
                     time=clock, report=report, audio_capture=None, re=re, json=__import__('json'),
                     print=lambda *a, **k: None)
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
        return scope['speed_window'], report, commands

    def test_transient_boundary_is_recorded_not_mislabeled_continuous(self):
        run, report, commands = self.fixture()
        run('player')
        result = report['speed_windows'][0]
        self.assertFalse(result['endpoint_audio_active'])
        self.assertFalse(result['audio_continuous'])
        self.assertTrue(result['audio_playback_window'])
        self.assertEqual(commands[-1], 'cont')
        self.assertGreater(result['audio_first_frame'], 0)
        self.assertAlmostEqual(result['instructions_per_host_second'], 1000)
        self.assertEqual(result['cycles_per_instruction'], 4)
        self.assertEqual(result['unknown_cost_instructions'],
                         result['clock_after']['UNKNOWN_COST']-result['clock_before']['UNKNOWN_COST'])
        self.assertEqual(result['guest_cycles'], result['guest_instructions']*4)
        self.assertEqual(result['unknown_sram_instructions']+result['unknown_opcode_instructions'],
                         result['unknown_cost_instructions'])
        # Only the two existing clock reads and final CPU-state read.
        self.assertEqual(commands.count('qom-get'), 3)

    def test_persistent_stop_cannot_start_a_window(self):
        run, report, _ = self.fixture(never_active=True)
        with self.assertRaisesRegex(AssertionError, 'did not become active'):
            run('player')
        self.assertNotIn('speed_windows', report)

    def test_profile_window_subtracts_prior_counts_and_restores_disabled(self):
        run, report, commands = self.fixture(profile=True)
        run('player')
        result = report['speed_windows'][0]
        self.assertEqual(result['unknown_opcode_profile'],
                         {'ac': result['unknown_opcode_instructions']})
        self.assertIn('not an uninstrumented', result['profile_note'])
        self.assertEqual(commands.count('qom-set'), 2)
        self.assertEqual(commands.count('qom-get'), 5)
        current = run.__globals__['emulator'].qmp.execute('qom-get',
            {'path': '/machine', 'property': 'instruction-clock-profile'})
        self.assertFalse(__import__('json').loads(current)['enabled'])

    def test_low_activity_is_still_rejected(self):
        run, _, _ = self.fixture(duty=.2)
        with self.assertRaises(AssertionError):
            run('player')

    def test_host_profile_records_owned_thread_and_closes(self):
        run, report, commands = self.fixture(host_profile=True)
        run('player')
        profile = report['speed_windows'][0]['host_cpu_profile']
        self.assertEqual((profile['pid'], profile['tid']), (100, 101))
        self.assertEqual(profile['samples'][0]['ip'], 123)
        self.assertIn('not an uninstrumented', profile['note'])
        self.assertEqual(run.__globals__['sampler_calls'], ['start', 'stop', 'close'])
        self.assertEqual(run.__globals__['active_host_samplers'], [])
        self.assertEqual(commands.count('query-cpus-fast'), 1)

    def test_host_profile_does_not_instrument_desktop(self):
        run, report, commands = self.fixture(host_profile=True)
        run('desktop')
        self.assertNotIn('host_cpu_profile', report['speed_windows'][0])
        self.assertEqual(run.__globals__['sampler_calls'], [])

    def test_host_time_reads_only_endpoints(self):
        run, report, commands = self.fixture(host_time=True)
        run('player')
        result = report['speed_windows'][0]['host_cpu_time']
        self.assertAlmostEqual(result['cpu_wall_ratio'], .75)
        self.assertAlmostEqual(result['instructions_per_cpu_second'], 1000/.75)
        self.assertEqual(len(run.__globals__['time_reads']), 2)
        self.assertEqual(commands.count('query-cpus-fast'), 1)

    def test_changed_audio_clock_retains_endpoints_and_rejects_window(self):
        run, report, _ = self.fixture(host_time=True, clock_changes=True)
        with self.assertRaisesRegex(AssertionError, 'audio request clock changed'):
            run('player')
        result = report['speed_windows'][0]
        self.assertEqual(result['audio_request_clock_before']['hz'], 1000)
        self.assertEqual(result['audio_request_clock_after']['hz'], 0)
        self.assertNotIn('audio_playback_window', result)
        self.assertIn('host_cpu_time', result)


if __name__ == '__main__':
    unittest.main()
