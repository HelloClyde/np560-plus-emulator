#!/usr/bin/env python3
"""Bounded physical-contact experiment on an owned emulator's desktop.

Uses M26, the firmware-consumed annunciator toggle, not a menu navigation key.
No logical event injection or guest memory writes. Results do not establish
all game input semantics, and host contact time is not a guest-time guarantee.
"""
import time


def observe(bridge):
    def ready():
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = bridge.get_json('/api/key-status')
            if status.get('matrix_rearmed'):
                return status
            time.sleep(.02)
        raise AssertionError('original keyboard scanner did not rearm')

    trials = []
    try:
        for repeat in range(6):
            # Alternate durations in the same live process; vary the idle
            # phase rather than always aligning to a single scanner phase.
            for duration in (.04, .08, .15):
                time.sleep(.137 + repeat * .011)
                before = ready()
                bridge.set_matrix(26)
                started = time.monotonic()
                time.sleep(duration)
                bridge.set_matrix(None)
                elapsed = time.monotonic() - started
                time.sleep(.5)
                after = ready()
                delta = after['candidates'] - before['candidates']
                trial = dict(repeat=repeat, requested_seconds=duration,
                             host_contact_upper_bound_seconds=elapsed,
                             candidate_delta=delta, candidate=after['candidate'],
                             matrix_read_delta=after['matrix_reads']-before['matrix_reads'])
                for field in ('matrix_active_reads', 'virtual_time_ns'):
                    if field in before and field in after:
                        trial[field + '_delta'] = after[field] - before[field]
                trial['counter_interval_includes_post_release_settle'] = True
                trials.append(trial)
                assert delta in (0, 1), trial
                assert not delta or after['candidate'] == 0x8c, trial
                print('contact trial ' + str(trial), flush=True)
    finally:
        bridge.set_matrix(None)
    return dict(matrix_index=26, expected_event=0x8c, trials=trials,
                scope='desktop scanner contact duration, not Web latency or game key meanings',
                host_guest_memory_writes=0)


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    from probe_np560_matrix_route import WebBridge
    from probe_np560_checkpoint_boot import assess
    from verify_np560_toolbar_frames import expected_from_package

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-physical-input', action='store_true')
    args = parser.parse_args()
    if not args.allow_physical_input:
        parser.error('use only an owned isolated desktop instance')
    bridge = WebBridge(args.root, 10)
    toolbar, provenance = expected_from_package(args.package)
    with args.output.open('x', encoding='utf-8') as output:
        report = dict(passed=False, package=provenance)
        try:
            deadline = time.monotonic() + 120
            while not assess(bridge.get_json('/api/state'), toolbar[1])['passed']:
                if time.monotonic() >= deadline:
                    raise TimeoutError('original desktop did not become ready')
                time.sleep(.5)
            report['health'] = bridge.get_json('/api/health')
            report.update(observe(bridge), passed=True)
        except Exception as error:
            report['error'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            json.dump(report, output, indent=2)
            output.write('\n')
