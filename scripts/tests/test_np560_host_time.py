"""Check thread time parsing, identity guards, CPU/wall metrics and missing schedstat."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from np560_host_time import parse_stat, thread_time_delta


class HostTime(unittest.TestCase):
    def test_comm_parentheses_and_fields(self):
        fields = ['R'] + ['0']*19
        fields[11], fields[12], fields[19] = '100', '20', '900'
        self.assertEqual(parse_stat('42 (a ) b) '+' '.join(fields)),
                         dict(tid=42, user_ticks=100, system_ticks=20, start_ticks=900))

    def snapshots(self):
        before = dict(pid=1, tid=2, start_ticks=9, ticks_per_second=100,
                      user_ticks=100, system_ticks=20, runtime_ns=1200000000,
                      runqueue_wait_ns=0, timeslices=5)
        after = {**before, 'user_ticks': 250, 'runtime_ns': 2700000000, 'timeslices': 15}
        return before, after

    def test_ratio_and_identity(self):
        before, after = self.snapshots()
        result = thread_time_delta(before, after, 2, 300)
        self.assertEqual(result['cpu_wall_ratio'], .75)
        self.assertEqual(result['instructions_per_cpu_second'], 200)
        for key in ('pid', 'tid', 'start_ticks', 'ticks_per_second'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                thread_time_delta(before, {**after, key: after[key]+1}, 2, 300)
        with self.assertRaises(ValueError):
            thread_time_delta(after, before, 2, 300)

    def test_missing_and_zero(self):
        before, after = self.snapshots()
        before['runtime_ns'] = after['runtime_ns'] = None
        self.assertEqual(thread_time_delta(before, after, 2, 300)['cpu_time_source'], 'stat-ticks')
        result = thread_time_delta(before, before, 0, 0)
        self.assertIsNone(result['cpu_wall_ratio'])
        self.assertIsNone(result['instructions_per_cpu_second'])


if __name__ == '__main__':
    unittest.main()
