#!/usr/bin/env python3
"""Observe clock progression in an owned instance, optionally with an isolated journal."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time

from web.np560_web import RunJournal, parse_args, start_emulator


def power_clock_snapshot(emulator):
    """Sequential read-only observations; never read GPIO to manufacture a scan."""
    result = {
        'note': 'sequential, unpaused observations; not an atomic hardware snapshot',
        'register_bytes': {
            name: base64.b64decode(emulator.snapshot('data', address, size,
                                  diagnostics=False)['frame']).hex()
            for name, address, size in (('calendar', 0x50b840, 8),)},
        'devices': {name: emulator.qmp.execute('qom-get', {
            'path': '/machine', 'property': name}) for name in (
                'instruction-clock-state', 'timebase-state',
                'timer0-state', 'timer1-state', 'timer2-state')},
    }
    clock = result['devices']['instruction-clock-state']
    if not all(f' {name}:' in clock for name in ('CLKCON', 'PLL', 'AUDIO_PLL')):
        raise RuntimeError('power-clock observation requires explicit core register fields')
    return result


def wait_for_daily_phrase(emulator, timeout=90, now=time.monotonic, sleep=time.sleep):
    """Wait for the verified settings-fixture entry page, not host boot time."""
    deadline = now() + timeout
    while True:
        status = emulator.key_status()
        if status.get('faulted') or emulator.process.poll() is not None:
            raise RuntimeError('emulator stopped/faulted while waiting for startup')
        if (status.get('application_state') == 0xfd and
                status.get('virtual_time_ns', 0) >= 8_000_000_000):
            return status
        if now() >= deadline:
            raise TimeoutError('daily-phrase startup not ready: ' + json.dumps(status))
        sleep(0.25)


def require_return_consumed(before, after):
    if (after.get('modal_acknowledgements', 0) <= before.get('modal_acknowledgements', 0)
            or after.get('modal_acknowledgement') != 0x8e):
        raise RuntimeError('F4 was not consumed by the startup modal; navigation aborted')


def command_file_lines(path, timeout=1800):
    """Local append-only diagnostic inbox for hosts without a persistent stdin."""
    path.touch(exist_ok=False)
    deadline = time.monotonic() + timeout
    consumed = 0
    consumed_prefix = ''
    while time.monotonic() < deadline:
        text = path.read_text(encoding='utf-8')
        if not text.startswith(consumed_prefix):
            raise RuntimeError('interactive inbox changed previously consumed commands')
        lines = text.splitlines(keepends=True)
        while consumed < len(lines) and lines[consumed].endswith('\n'):
            line = lines[consumed]
            consumed += 1
            consumed_prefix += line
            yield line
        time.sleep(0.1)
    raise TimeoutError('interactive command inbox expired')


def interactive_steps(emulator, output, lines=None, sleep=time.sleep):
    """Owned-instance console: a matrix index per line, or q/EOF to close.

    No memory writes, save-state injection, shell commands, or remote-instance attachment.
    """
    print('INTERACTIVE READY: matrix 0..63, snapshot, or q', flush=True)
    for line in sys.stdin if lines is None else lines:
        command = line.strip()
        if command == 'q':
            break
        if command != 'snapshot' and (not command.isdecimal() or not 0 <= int(command) < 64):
            print('ERROR: expected matrix 0..63, snapshot, or q', flush=True)
            continue
        before = emulator.key_status()
        if before.get('faulted') or emulator.process.poll() is not None:
            raise RuntimeError('interactive instance stopped or faulted')
        matrix = None if command == 'snapshot' else int(command)
        if matrix is not None:
            emulator.set_key(0, 0, matrix_low=(1 << matrix) if matrix < 32 else 0,
                             matrix_high=(1 << (matrix - 32)) if matrix >= 32 else 0)
            try:
                sleep(0.25)
            finally:
                emulator.set_key(0, 0, matrix_low=0, matrix_high=0)
            sleep(1)
        index = len(list(output.glob('interactive-*.json')))
        path = output / f'interactive-{index:03d}.json'
        with path.open('x', encoding='utf-8') as stream:
            json.dump({'matrix': matrix, 'before': before, 'after': emulator.key_status(),
                       'lcd': emulator.snapshot('lcd', 0, 1),
                       'rpg': emulator.snapshot('data', 0x527900, 512, diagnostics=False),
                       'inventory': emulator.snapshot('data', 0x5267c8, 0x200, diagnostics=False),
                       'world': emulator.snapshot('data', 0x526b80, 0xb00, diagnostics=False)}, stream)
        print('CAPTURE ' + str(path), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--interactive', action='store_true',
                        help='after the planned route, accept individual matrix keys on stdin; q/EOF closes')
    parser.add_argument('--interactive-file', action='store_true',
                        help='use output/commands.txt instead of stdin; append matrix lines or q; 30-minute limit')
    parser.add_argument('--journal-seed', type=Path,
                        help='copy a closed diagnostic journal into output; never open the source for writing')
    parser.add_argument('--expected-journal-sha256',
                        help='required SHA256 pin for journal-seed')
    parser.add_argument('--cold-readback', action='store_true',
                        help='use a new journal inside output, close, then boot a new process with that journal')
    parser.add_argument('--observe-rpg-state', action='store_true',
                        help='read raw 52:7900..7AFF before/after each physical step')
    parser.add_argument('--observe-event-loop', action='store_true',
                        help='capture RPG/event data per sample and live event-loop code after navigation')
    parser.add_argument('--observe-power-clock', action='store_true',
                        help='read CLKCON/PLL, calendar and timer states around physical keys')
    parser.add_argument('--samples', type=int, default=16, choices=range(1, 181))
    parser.add_argument('--lcd-timeline', action='store_true',
                        help='capture 20 running LCD frames at 100 ms intervals after observation')
    parser.add_argument('--trace-editor', action='store_true',
                        help='enable existing full read-only observers immediately before M39')
    parser.add_argument('--full-observer-step', type=int,
                        help='enable read-only control observers/logging before this zero-based step')
    parser.add_argument('--editor-contact-seconds', type=float, default=0.25,
                        help='M39 contact only; navigation remains 250 ms')
    parser.add_argument('--matrix-contact-seconds', type=float, default=0.25,
                        help='matrix contact duration; with full-observer-step applies only from that step')
    parser.add_argument('--return-key', action='store_true',
                        help='send one physical F4/M4 contact after startup; verify resulting page separately')
    parser.add_argument('--matrix-step', type=int, choices=range(64), action='append', default=[],
                        help='explicit matrix contacts after return, each captured for manual verification')
    parser.add_argument('--settle-step', action='append', default=[], metavar='INDEX:SECONDS',
                        help='override one zero-based step observation delay (1..60 seconds)')
    options, remaining = parser.parse_known_args()
    if (options.full_observer_step is not None and
            not 0 <= options.full_observer_step < len(options.matrix_step)):
        parser.error('--full-observer-step must name an existing matrix step')
    seed = None
    if bool(options.journal_seed) != bool(options.expected_journal_sha256):
        parser.error('--journal-seed and --expected-journal-sha256 must be supplied together')
    if options.journal_seed:
        seed = options.journal_seed.read_bytes()
        if hashlib.sha256(seed).hexdigest() != options.expected_journal_sha256.lower():
            parser.error('journal seed SHA256 mismatch')
    settle_steps = {}
    for value in options.settle_step:
        try:
            index_text, seconds_text = value.split(':')
            index, seconds = int(index_text), float(seconds_text)
            if not 0 <= index < len(options.matrix_step) or not 1 <= seconds <= 60:
                raise ValueError()
            if index in settle_steps:
                raise ValueError()
        except ValueError:
            parser.error('--settle-step requires a unique existing INDEX and 1..60 SECONDS')
        settle_steps[index] = seconds
    if not 0 < options.editor_contact_seconds <= 2:
        parser.error('--editor-contact-seconds must be in (0, 2]')
    if not 0 < options.matrix_contact_seconds <= 10:
        parser.error('--matrix-contact-seconds must be in (0, 10]')
    args = parse_args(remaining)
    if options.matrix_step and not options.return_key:
        parser.error('--matrix-step requires --return-key so startup precedes navigation')
    if any((args.device, args.create_device, args.nand_save_on_exit,
            args.nand_journal, args.debug_program_load,
            args.initial_key_matrix_low, args.initial_key_matrix_high)):
        parser.error('probe requires a fresh non-persistent instance without injected input/code')
    options.output.mkdir(parents=True, exist_ok=False)
    if options.cold_readback or seed is not None:
        args.nand_journal = options.output / 'device.npj'
        if seed is not None:
            with args.nand_journal.open('xb') as stream:
                stream.write(seed)
            with (options.output / 'journal-seed.json').open('x', encoding='utf-8') as stream:
                json.dump({'path': str(options.journal_seed.resolve()), 'bytes': len(seed),
                           'sha256': hashlib.sha256(seed).hexdigest()}, stream)
    journal = RunJournal(options.output / 'lifecycle', purpose='clock observation')
    emulator = start_emulator(args, journal)
    rows = []
    try:
        if options.return_key:
            wait_for_daily_phrase(emulator)
            with (options.output / 'before-key.json').open('x', encoding='utf-8') as stream:
                json.dump(emulator.snapshot('lcd', 0, 1), stream)
            before_key = emulator.key_status()
            emulator.set_key(0, 0, matrix_low=1 << 4, matrix_high=0)
            try:
                time.sleep(0.25)
            finally:
                emulator.set_key(0, 0, matrix_low=0, matrix_high=0)
            time.sleep(2)
            with (options.output / 'input.json').open('x', encoding='utf-8') as stream:
                after_key = emulator.key_status()
                json.dump({'matrix': 4, 'before': before_key, 'after': after_key}, stream)
            require_return_consumed(before_key, after_key)
        for step, matrix in enumerate(options.matrix_step):
            if ((options.trace_editor and matrix == 39) or
                    options.full_observer_step == step):
                emulator.qmp.execute('stop')
                try:
                    emulator.qmp.execute('qom-set', {'path': '/machine',
                        'property': 'control-observers-minimal', 'value': False})
                    emulator.qmp.execute('human-monitor-command',
                                         {'command-line': 'log guest_errors'})
                finally:
                    emulator.qmp.execute('cont')
            before_key = emulator.key_status()
            before_object = emulator.snapshot('data', 0x514a46, 256, diagnostics=False)
            power_before = power_clock_snapshot(emulator) if options.observe_power_clock else None
            rpg_before = (emulator.snapshot('data', 0x527900, 512, diagnostics=False)
                          if options.observe_rpg_state else None)
            emulator.set_key(0, 0, matrix_low=(1 << matrix) if matrix < 32 else 0,
                             matrix_high=(1 << (matrix - 32)) if matrix >= 32 else 0)
            try:
                contact_seconds = options.matrix_contact_seconds
                if (options.full_observer_step is not None and
                        step < options.full_observer_step):
                    contact_seconds = 0.25
                time.sleep(options.editor_contact_seconds if matrix == 39
                           else contact_seconds)
            finally:
                emulator.set_key(0, 0, matrix_low=0, matrix_high=0)
            time.sleep(settle_steps.get(step, 1))
            with (options.output / f'step-{step:02d}.json').open('x', encoding='utf-8') as stream:
                json.dump({'matrix': matrix, 'before': before_key,
                           'power_clock_before': power_before,
                           'power_clock_after': (power_clock_snapshot(emulator)
                                                 if options.observe_power_clock else None),
                           'after': emulator.key_status(), 'lcd': emulator.snapshot('lcd', 0, 1),
                           'object_address': 0x514a46, 'object_before': before_object,
                           'rpg_state_before': rpg_before,
                           'rpg_state_after': (emulator.snapshot('data', 0x527900, 512, diagnostics=False)
                                               if options.observe_rpg_state else None),
                           'object_after': emulator.snapshot('data', 0x514a46, 256, diagnostics=False)}, stream)
        if options.interactive or options.interactive_file:
            lines = (command_file_lines(options.output / 'commands.txt')
                     if options.interactive_file else None)
            interactive_steps(emulator, options.output, lines=lines)
        for index in range(options.samples):
            before = time.monotonic()
            # Data-byte addressing: DS=A1, logical 3840 maps to 50:B840.
            frame = emulator.snapshot('data', 0x50b840, 8, diagnostics=False)
            clock = base64.b64decode(frame['frame'])
            keys = emulator.key_status()
            row = {'sample': index, 'host_start': before,
                   'host_end': time.monotonic(), 'clock_bytes': clock.hex(),
                   'key_status': keys}
            if options.observe_power_clock:
                row['power_clock'] = power_clock_snapshot(emulator)
            if options.observe_event_loop:
                row['event_data'] = emulator.snapshot('data', 0x512a40, 128, diagnostics=False)
                row['rpg_data'] = emulator.snapshot('data', 0x527900, 512, diagnostics=False)
            rows.append(row)
            print(json.dumps({'sample': index, 'clock_bytes': clock.hex(),
                              'virtual_time_ns': keys.get('virtual_time_ns'),
                              'faulted': keys.get('faulted')}), flush=True)
            time.sleep(2)
        with (options.output / 'final-lcd.json').open('x', encoding='utf-8') as stream:
            json.dump(emulator.snapshot('lcd', 0, 1), stream)
        if options.observe_rpg_state:
            # Raw world tables for planning physical navigation; no coordinate writes.
            with (options.output / 'world-tables.json').open('x', encoding='utf-8') as stream:
                json.dump(emulator.snapshot('data', 0x526b80, 0xb00,
                                           diagnostics=False), stream)
        if options.observe_event_loop:
            # Sequential read-only instruction-bus captures, not an atomic CPU snapshot.
            regions = ((0x034154, 8), (0x1fd4e2, 0x292),
                       (0x1ef734, 0x648), (0x2df47c, 0x196), (0x293dd2, 0x2c4))
            with (options.output / 'event-code.json').open('x', encoding='utf-8') as stream:
                json.dump({f'{address:06x}': emulator.snapshot('code', address, size,
                           diagnostics=False) for address, size in regions}, stream)
        if options.lcd_timeline:
            frames = []
            for index in range(20):
                frames.append({'host_time': time.monotonic(),
                               'lcd': emulator.snapshot('lcd', 0, 1, diagnostics=False)})
                time.sleep(0.1)
            with (options.output / 'lcd-timeline.json').open('x', encoding='utf-8') as stream:
                json.dump(frames, stream)
        emulator.qmp.execute('stop')
        try:
            paired = {name: emulator.snapshot(source, address, size, diagnostics=False)
                      for name, source, address, size in (
                          ('back', 'data', 0x500000, 0x3840),
                          ('front', 'data', 0x503840, 0x3840),
                          ('gram', 'lcd-gram', 0, 1), ('lcd', 'lcd', 0, 1))}
            with (options.output / 'paired-raster.json').open('x', encoding='utf-8') as stream:
                json.dump(paired, stream)
        finally:
            emulator.qmp.execute('cont')
        # Read the live instruction bus, not just resident.bin: application
        # code can be published/mapped after boot.
        with (options.output / 'editor-code.json').open('x', encoding='utf-8') as stream:
            json.dump(emulator.snapshot('code', 0x123f6c, 0x5434 - 0x3f6c, diagnostics=False), stream)
        for name, source, address, size in (
            ('number-editor', 'code', 0x174a3a, 0x2a6),
            ('number-draw', 'code', 0x277e84, 0x344),
            ('number-format', 'code', 0x317772, 0xb2),
            ('number-formats', 'data', 0x1bffc0, 0x40),
        ):
            with (options.output / f'{name}.json').open('x', encoding='utf-8') as stream:
                json.dump(emulator.snapshot(source, address, size, diagnostics=False), stream)
    finally:
        emulator.close()
        with (options.output / 'samples.json').open('x', encoding='utf-8') as stream:
            json.dump({'samples': rows, 'returncode': emulator.process.poll()}, stream, indent=2)
    if options.cold_readback:
        cold_journal = RunJournal(options.output / 'cold-lifecycle', purpose='clock cold readback')
        cold = start_emulator(args, cold_journal)
        cold_rows = []
        try:
            wait_for_daily_phrase(cold)
            for index in range(10):
                frame = cold.snapshot('data', 0x50b840, 8, diagnostics=False)
                cold_rows.append({'sample': index,
                                  'clock_bytes': base64.b64decode(frame['frame']).hex(),
                                  'key_status': cold.key_status()})
                time.sleep(2)
            with (options.output / 'cold-lcd.json').open('x', encoding='utf-8') as stream:
                json.dump(cold.snapshot('lcd', 0, 1), stream)
        finally:
            cold.close()
            with (options.output / 'cold-samples.json').open('x', encoding='utf-8') as stream:
                json.dump({'samples': cold_rows, 'returncode': cold.process.poll()}, stream, indent=2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
