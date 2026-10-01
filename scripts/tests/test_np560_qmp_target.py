"""Verify standard target/CPU queries do not abort DMCU, paused or running."""
import argparse
from pathlib import Path
import struct
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web.np560_web import Emulator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='np560-qmp-target-') as directory:
        firmware = Path(directory)/'loop.prg'
        firmware.write_bytes(struct.pack('<H', 0xd0ff))
        emu = Emulator(qemu=args.qemu, firmware=firmware, start_paused=True)
        try:
            previous = None
            for action in (None, 'cont', 'stop'):
                if action:
                    emu.qmp.execute(action)
                assert emu.qmp.execute('query-target') == {'arch': 'dmcu'}
                cpus = emu.qmp.execute('query-cpus-fast')
                assert len(cpus) == 1 and cpus[0]['target'] == 'dmcu', cpus
                assert cpus[0]['cpu-index'] == 0 and cpus[0]['thread-id'] > 0, cpus
                if previous is not None:
                    assert cpus == previous, (previous, cpus)
                previous = cpus
                assert emu.qmp.execute('query-status')['running'] == (action == 'cont')
        finally:
            emu.close()
        assert emu.process.returncode == 0
    print('PASS: query-target/query-cpus-fast before, during and after execution')


if __name__ == '__main__':
    main()
