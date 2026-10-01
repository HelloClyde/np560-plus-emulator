#!/usr/bin/env python3
"""Check bounded-memory NAND export/load and preservation on a short host write.

Uses a blank, paused, owned QEMU only. Full temporary checkpoints are removed;
no user NAND input, host guest-memory writes, or running-instance attachment.
POSIX-only failure injection limits the child process, not the test runner.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web.np560_web import Emulator, QMPError


def peak_kib(pid):
    rows = Path(f'/proc/{pid}/status').read_text().splitlines()
    return int(next(row for row in rows if row.startswith('VmHWM:')).split()[1])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qemu', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if os.name != 'posix':
        p.error('run this process-limit check under Linux/WSL')
    import resource
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(passed=False, nand_input_used=False, host_guest_memory_writes=0,
                  qemu_sha256=hashlib.sha256(args.qemu.read_bytes()).hexdigest())
    try:
        with tempfile.TemporaryDirectory(prefix='export-', dir=args.output) as temp:
            root = Path(temp)
            firmware = root / 'caller.prg'
            firmware.write_bytes(struct.pack('<H', 0xc701))
            target = root / 'backup.nand'
            sentinel = b'previous-backup-must-survive'
            target.write_bytes(sentinel)
            real_popen = subprocess.Popen

            def limited_popen(*args, **kwargs):
                previous = kwargs.pop('preexec_fn', None)
                def prepare():
                    if previous:
                        previous()
                    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
                    _, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
                    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, hard))
                return real_popen(*args, preexec_fn=prepare, **kwargs)

            with patch('web.np560_web.subprocess.Popen', side_effect=limited_popen):
                emu = Emulator(qemu=args.qemu, firmware=firmware, start_paused=True)
            try:
                try:
                    emu.save_nand(target)
                except QMPError as error:
                    report['injected_error'] = str(error)
                else:
                    raise AssertionError('file-size limit did not reject export')
                assert target.read_bytes() == sentinel
                assert not list(root.glob('*.export.*'))
                report['old_backup_preserved'] = True
            finally:
                emu.close()
                assert emu.process.returncode == 0

            emu = Emulator(qemu=args.qemu, firmware=firmware, start_paused=True)
            try:
                before = peak_kib(emu.process.pid)
                emu.save_nand(target)
                after = peak_kib(emu.process.pid)
                report['peak_kib_before_after'] = [before, after]
                assert after - before < 64 * 1024, (before, after)
                assert target.stat().st_size == 64 + 528 * 1024 * 1024
                with target.open('rb') as stream:
                    header = stream.read(64)
                    assert header[:8] == b'NP560N1\0'
                    assert struct.unpack_from('<6I', header, 8) == (1, 64, 2048, 64, 64, 4096)
                    erased = b'\xff' * (1024 * 1024)
                    for _ in range(528):
                        assert stream.read(len(erased)) == erased
                    assert stream.read(1) == b''
                assert not list(root.glob('*.export.*'))
            finally:
                emu.close()
                assert emu.process.returncode == 0
            # Production loader validates both stored plane checksums.
            emu = Emulator(qemu=args.qemu, firmware=firmware,
                           nand_checkpoint=target, start_paused=True)
            try:
                loaded_peak = peak_kib(emu.process.pid)
                report['reload_peak_kib'] = loaded_peak
                assert loaded_peak - before < 64 * 1024, (before, loaded_peak)
            finally:
                emu.close()
                assert emu.process.returncode == 0
            report['complete_blank_planes_and_reload'] = True
            # Corrupt only our disposable backup, never a user's NAND. Restore
            # each byte before the next case; avoid copying a 528 MiB fixture.
            rejected = []
            def reject(label, message):
                result = subprocess.run([
                    str(args.qemu), '-M', f'np560,nand-checkpoint={target}',
                    '-bios', str(firmware), '-display', 'none', '-S',
                ], capture_output=True, text=True, timeout=30)
                assert result.returncode != 0, label
                assert message in result.stderr, (label, result.stderr)
                rejected.append(label)

            for label, offset, message in [
                ('magic', 0, 'incompatible header or size'),
                ('geometry', 16, 'incompatible header or size'),
                ('data', 64 + 12345, 'failed its checksum'),
                ('oob', 64 + 512 * 1024 * 1024 + 123, 'failed its checksum'),
            ]:
                with target.open('r+b') as stream:
                    stream.seek(offset)
                    original = stream.read(1)
                    stream.seek(offset)
                    stream.write(bytes([original[0] ^ 1]))
                try:
                    reject(label, message)
                finally:
                    with target.open('r+b') as stream:
                        stream.seek(offset)
                        stream.write(original)
            size = target.stat().st_size
            with target.open('ab') as stream:
                stream.write(b'\0')
            reject('trailing-byte', 'incompatible header or size')
            with target.open('r+b') as stream:
                stream.truncate(size - 1)
            reject('truncated-oob', 'incompatible header or size')
            report['invalid_checkpoints_rejected'] = rejected
        report['passed'] = True
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
