"""Read-only Linux owned-thread CPU-time endpoints for diagnostic windows."""
import os
from pathlib import Path


def parse_stat(text):
    # comm may contain spaces and closing parentheses. Fields after its last
    # ')' begin with state (field 3); never split the whole record on spaces.
    end = text.rfind(')')
    if end < 0:
        raise ValueError('missing stat comm')
    fields = text[end+1:].split()
    if len(fields) < 20:
        raise ValueError('truncated stat')
    return dict(tid=int(text[:text.index('(')].strip()),
                user_ticks=int(fields[11]), system_ticks=int(fields[12]),
                start_ticks=int(fields[19]))


def read_thread_time(pid, tid):
    root = Path(f'/proc/{int(pid)}/task/{int(tid)}')
    result = parse_stat((root/'stat').read_text())
    if result['tid'] != tid:
        raise ValueError('thread identity mismatch')
    result.update(pid=pid, ticks_per_second=os.sysconf('SC_CLK_TCK'))
    try:
        runtime, wait, slices = map(int, (root/'schedstat').read_text().split())
        result.update(runtime_ns=runtime, runqueue_wait_ns=wait, timeslices=slices)
    except FileNotFoundError:
        result.update(runtime_ns=None, runqueue_wait_ns=None, timeslices=None)
    return result


def thread_time_delta(before, after, wall_seconds, instructions):
    for key in ('pid', 'tid', 'start_ticks', 'ticks_per_second'):
        if before[key] != after[key]:
            raise ValueError(f'thread identity/clock changed: {key}')
    delta = {}
    for key in ('user_ticks', 'system_ticks', 'runtime_ns', 'runqueue_wait_ns', 'timeslices'):
        if before[key] is None or after[key] is None:
            delta[key] = None
        else:
            delta[key] = after[key]-before[key]
            if delta[key] < 0:
                raise ValueError(f'thread counter regressed: {key}')
    ticks_seconds = (delta['user_ticks']+delta['system_ticks']) / before['ticks_per_second']
    seconds = delta['runtime_ns']/1e9 if delta['runtime_ns'] is not None else ticks_seconds
    return dict(before=before, after=after, delta=delta, cpu_seconds=seconds,
                tick_cpu_seconds=ticks_seconds,
                cpu_time_source='schedstat' if delta['runtime_ns'] is not None else 'stat-ticks',
                cpu_wall_ratio=seconds/wall_seconds if wall_seconds else None,
                instructions_per_cpu_second=instructions/seconds if seconds else None,
                note='Linux thread accounting, not Windows-wide CPU availability. Zero runqueue wait may mean accounting disabled. Endpoint reads are sequential, not atomic.')
