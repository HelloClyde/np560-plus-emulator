"""Compare observer overhead with unchanged guest timing and boot inputs."""
import argparse
import json
from pathlib import Path
import re
import time
from web.np560_web import Emulator


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=30)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    for minimal in (False, True):
        emu = Emulator(qemu=Path('/mnt/e/qemu-dmcu-build/qemu-system-dmcu'),
            firmware=Path('NP560+V3.80版系统升级程序/NP560.PRG'),
            soc_rom=Path('tmp/np560-mp3-arena-release-20260911-v2/resident.bin'),
            nand_checkpoint=Path('/mnt/e/qemu-dmcu-build/np560-mp3-tone-20260906-v1.nand'),
            boot_mode='firmware-vma03', soc_rom_skeleton=True,
            rom_mp3_hle_base=138790, rom_mp3_arena_image=93952,
            icount_shift=0, start_paused=True)
        try:
            for prop, value in [('instruction-clock', True), ('control-observers-minimal', minimal)]:
                emu.qmp.execute('qom-set', {'path':'/machine', 'property':prop, 'value':value})
            started = time.monotonic()
            emu.qmp.execute('cont')
            time.sleep(args.seconds)
            emu.qmp.execute('stop')
            elapsed = time.monotonic() - started
            clock = emu.qmp.execute('qom-get', {'path':'/machine', 'property':'instruction-clock-state'})
            state = emu.qmp.execute('qom-get', {'path':'/machine', 'property':'cpu-state'})
            ns = int(re.search(r'\bNS:(\d+)', clock)[1])
            result = dict(minimal=minimal, host_seconds=elapsed, guest_seconds=ns/1e9,
                          realtime_ratio=ns/1e9/elapsed, clock=clock, cpu=state)
            results.append(result)
            print({k:v for k,v in result.items() if k != 'cpu'}, flush=True)
        finally:
            emu.close()
            (args.output/'report.json').write_text(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
