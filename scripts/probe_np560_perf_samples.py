#!/usr/bin/env python3
"""Bounded Linux perf user-IP sampling of an owned QEMU CPU thread, without ptrace."""
from __future__ import annotations

import argparse
from collections import Counter
import ctypes
import hashlib
import json
import mmap
import os
from pathlib import Path
import platform
import struct
import time

from probe_np560_cpu_cost import program
from web.np560_web import Emulator, RunJournal


def decode_records(data: bytes):
    """Decode a stopped PERF_SAMPLE_IP|TID stream; reject truncated records."""
    samples, lost, other = [], 0, Counter()
    offset = 0
    while offset < len(data):
        if len(data)-offset < 8:
            raise ValueError('truncated perf header')
        kind, misc, size = struct.unpack_from('<IHH', data, offset)
        if size < 8 or offset+size > len(data):
            raise ValueError('invalid perf record size')
        if kind == 9:  # PERF_RECORD_SAMPLE
            if size != 24:
                raise ValueError('unexpected sample layout')
            ip, pid, tid = struct.unpack_from('<QII', data, offset+8)
            samples.append(dict(ip=ip, pid=pid, tid=tid, misc=misc))
        elif kind == 2:  # PERF_RECORD_LOST
            if size != 24:
                raise ValueError('unexpected lost record layout')
            lost += struct.unpack_from('<Q', data, offset+16)[0]
        else:
            other[kind] += 1
        offset += size
    return dict(samples=samples, lost=lost, other_records=dict(other))


class UserIPSampler:
    """Caller must supply a thread of its owned process. No arbitrary-PID CLI.

    No live ring reads: disable the event before copying the buffer, so the
    producer is quiescent and no concurrent head/tail memory ordering is used.
    Buffer-full samples can be lost; never interpret sample count as elapsed
    time or claim zero perturbation. Linux x86_64 ABI only.
    """
    def __init__(self, tid, period_ns=2_000_000):
        if platform.system() != 'Linux' or platform.machine() != 'x86_64':
            raise RuntimeError('perf sampler requires Linux x86_64')
        import fcntl
        self.ioctl = fcntl.ioctl
        self.fd = -1
        self.ring = None
        self.running = False
        attr = ctypes.create_string_buffer(128)
        # type=SOFTWARE, config=CPU_CLOCK, period (not frequency), IP|TID,
        # disabled + exclude_kernel + exclude_hv. No child inheritance.
        struct.pack_into('<IIQQQQQ', attr, 0, 1, 128, 0, period_ns, 3, 0, 97)
        libc = ctypes.CDLL(None, use_errno=True)
        fd = libc.syscall(298, ctypes.byref(attr), tid, -1, -1, 8)  # CLOEXEC
        if fd < 0:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))
        self.fd = fd
        try:
            self.ring = mmap.mmap(fd, mmap.PAGESIZE*257,
                                 flags=mmap.MAP_SHARED,
                                 prot=mmap.PROT_READ | mmap.PROT_WRITE)
        except BaseException:
            self.close()
            raise

    def start(self):
        if self.running:
            raise RuntimeError('sampler already running')
        self.ioctl(self.fd, 0x2400, 0)  # PERF_EVENT_IOC_ENABLE
        self.running = True

    def stop(self):
        self.ioctl(self.fd, 0x2401, 0)  # PERF_EVENT_IOC_DISABLE
        self.running = False
        head, tail, offset, size = struct.unpack_from('<QQQQ', self.ring, 1024)
        if not size or offset+size > len(self.ring) or not tail <= head <= tail+size:
            raise ValueError('invalid/overwritten perf ring')
        start, count = tail % size, head-tail
        first = min(count, size-start)
        data = self.ring[offset+start:offset+start+first]
        data += self.ring[offset:offset+count-first]
        result = decode_records(data)
        struct.pack_into('<Q', self.ring, 1032, head)
        result['ring_bytes'] = count
        return result

    def close(self):
        if self.fd >= 0:
            try:
                if self.running:
                    self.ioctl(self.fd, 0x2401, 0)
            finally:
                if self.ring is not None:
                    self.ring.close()
                    self.ring = None
                os.close(self.fd)
                self.fd = -1
                self.running = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, choices=range(1, 31), default=3)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    firmware = args.output/'loop.prg'
    firmware.write_bytes(program(65535)[0])
    emu = sampler = None
    report = dict(passed=False, qemu_sha256=hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
                  nand_used=False, host_guest_memory_writes=0,
                  scope='software CPU-clock IP samples; no stacks, not a speed benchmark')
    try:
        emu = Emulator(qemu=args.qemu, firmware=firmware, start_paused=True,
                       journal=RunJournal(args.output/'runs', case='perf-owned-cpu'))
        tasks = {int(p.name): (p/'comm').read_text().strip()
                 for p in Path(f'/proc/{emu.process.pid}/task').iterdir()}
        # This build does not set Linux thread names. QMP is authoritative;
        # also verify the returned TID belongs to the process we created.
        cpus = [cpu['thread-id'] for cpu in emu.qmp.execute('query-cpus-fast')]
        if len(cpus) != 1:
            raise RuntimeError(f'expected one owned TCG CPU thread: {tasks}')
        assert cpus[0] in tasks, 'QMP CPU thread is outside the owned process'
        report.update(pid=emu.process.pid, tid=cpus[0], threads=tasks)
        sampler = UserIPSampler(cpus[0])
        sampler.start()
        emu.qmp.execute('cont')
        time.sleep(args.seconds)
        emu.qmp.execute('stop')
        report.update(sampler.stop())
        report['maps'] = Path(f'/proc/{emu.process.pid}/maps').read_text()
        report['cpu'] = emu.qmp.execute('qom-get', {'path':'/machine','property':'cpu-state'})
        assert report['samples'], 'kernel accepted perf event but produced no samples'
        assert all(s['pid'] == emu.process.pid and s['tid'] == cpus[0] for s in report['samples'])
        assert all(s['misc'] & 7 == 2 for s in report['samples']), 'non-user sample'
        assert all(f'{key}=none' in report['cpu'] for key in ('ROM_MISSING','UNSUPPORTED','INVALID_CONTROL'))
        report['passed'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        if sampler:
            sampler.close()
        if emu:
            emu.close()
            report['exit_code'] = emu.process.returncode
            report['passed'] &= emu.process.returncode == 0
    (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('samples','maps','cpu')}, indent=2))
    print(f"Samples: {len(report.get('samples', []))}")
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
