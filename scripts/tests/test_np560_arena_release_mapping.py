#!/usr/bin/env python3
"""Check the actual code bus before boot; do not mutate guest state."""

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import argparse
import base64
import re
from pathlib import Path
from web.np560_web import Emulator

p=argparse.ArgumentParser(description=__doc__)
for flag in ('qemu','firmware','soc-rom'):
    p.add_argument('--'+flag,type=Path,required=True)
p.add_argument('--arena-image',type=int,required=True)
p.add_argument('--hle-base',type=int,required=True)
args=p.parse_args()
e=Emulator(qemu=args.qemu,firmware=args.firmware,soc_rom=args.soc_rom,
    soc_rom_skeleton=True,rom_mp3_hle_base=args.hle_base,
    rom_mp3_arena_image=args.arena_image,boot_mode='firmware-vma03',start_paused=True)
try:
    tree=e.qmp.execute('human-monitor-command',{'command-line':'info mtree -f'})
    for line in tree.splitlines():
        match=re.search(r'([0-9a-f]{16})-([0-9a-f]{16})',line)
        if (match and int(match[1],16)<=0x308c1c<=int(match[2],16)) or any(
                s in line for s in ('FlatView','Root memory','AS "')):
            print(line)
    got=base64.b64decode(e.snapshot('code',0x308c1c,16)['frame'])
    expected=args.soc_rom.read_bytes()[args.arena_image:args.arena_image+16]
    print('actual',got.hex(),'expected',expected.hex())
    direct=base64.b64decode(e.snapshot('code',args.arena_image,16)['frame'])
    print('source-code',direct.hex())
    assert got==expected,'release wrapper is not selected on actual code bus'
finally:
    e.close()
