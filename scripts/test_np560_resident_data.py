#!/usr/bin/env python3
"""VMA03 resident ROM data reads and writable-memory boundaries.

Guest instructions read/write both DS paths; no MP3-specific table mapping,
NAND, host RAM writes or substitute ROM service. The fixture deliberately
puts different code and data sources at the VMA03 firmware boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from test_np560_mac import run


def check(qemu, output, *, icount=None, short=False):
    rom = bytearray(b"\x00\x0f" * ((0x10100 if short else 0x33000)//2))
    constants = ((0x10000,0x1357),(0x100fe,0x2468)) if short else (
        (0x10000,0x1357),(0x17ffe,0x2468),(0x18000,0x369c),
        (0x1fffe,0x48ad),(0x20000,0x5abe),(0x27ffe,0x6bcf),
        (0x28000,0x7cd0),(0x2fffe,0x8de1))
    for address, value in constants: struct.pack_into("<H",rom,address,value)
    if not short: struct.pack_into("<3H",rom,0x10800,0x68f0,0x1234,0xc620)
    words = [0x6800,2,0x68ff,0x6000]
    expected = []
    def record(value):
        words.extend((0x3f10,0xa8f0,0x2400+len(expected)*2))
        expected.append(value if value<32768 else value-65536)
    def data_word(address, value, readonly=False):
        # Both DS0 and DS1 must see the same ROM/RAM at this physical byte.
        bank, off = address>>15,address&0x7fff
        words.extend((0x6810,bank,0x6811,bank,0x88f0,off));record(value)
        words.extend((0x68f3,off|0x8000,0x2803));record(value)
        words.extend((0x68f0,0xbeef,0xa8f0,off,0x88f0,off));record(value if readonly else 0xbeef)
        # Word and low/high byte stores to ROM must not mutate it.
        words.extend((0x68f1,0xcafe,0x0a31,0x68f0,0x55,0xa9f1,off,
                      0xa9f1,off+1,0x88f0,off))
        record(value if readonly else 0x5555)
    for address,value in constants: data_word(address,value,True)
    # X/Y RAM and DPRAM are below the internal program-ROM start.
    for address in (0x0500,0x8400,0xf010): data_word(address,0)
    if short:
        # Loading a short file must not turn the rest of RAM into zero ROM.
        data_word(0x10100,0)
    else:
        words.extend((0xbd01,0x0800));record(0x1234)
        # FP accesses remain internal, even while DS0 selects resident ROM.
        words.extend((0x6810,2,0x68fb,0x0802,0x68f0,0xabcd,
                      0x0ab0,0x280b));record(0xabcd)
        words.extend((0x88f0,0x0802));record(0x1234)
        words.extend((0xbd01,0x0800));record(0x1234)
    # The loaded PRG is still coherent writable code/data from 03:0000.
    words.extend((0xbd03,0x2000));record(0x5678)
    words.extend((0x6810,6,0x68f0,0x6789,0xa8f0,0x2002,
                  0x88f0,0x2002));record(0x6789)
    words.extend((0xbd03,0x2000));record(0x6789)
    code_checks = [(start,bytes(rom[start:min(start+0x8000,0x30000,len(rom))]))
                   for start in range(0x10000,min(0x30000,len(rom)),0x8000)]
    return run(qemu,output,f"resident-data-{'short' if short else 'full'}-{icount}",
        words,{15:0x6000},rom=rom,tail=(0x2000,struct.pack("<3H",0x68f0,0x5678,0xc620)),
        boot_mode="firmware-vma03",icount=icount,expected_data=expected,
        expected_code=code_checks,metadata={"rom_bytes":len(rom),
            "constants":list(constants),"readonly_rom_writes_checked":True,
            "x_y_dpram_and_vma03_writes_checked":True,"mp3_specific_mapping":False})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--first-only",action="store_true")
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    report={"passed":False,"qemu_sha256":hashlib.sha256(args.qemu.read_bytes()).hexdigest(),"cases":[]}
    try:
        for short,icount in ((False,None),) if args.first_only else ((False,None),(False,5),(True,None),(True,5)):
            report["cases"].append(check(args.qemu,args.output,short=short,icount=icount))
        report["passed"]=all(c["passed"] and c["exit_code"]==0 for c in report["cases"])
    except AssertionError as exc:
        detail=exc.args[0] if exc.args else "assertion failed"
        if isinstance(detail,dict): detail={k:detail[k] for k in ("name","actual_samples","expected_samples","code_phase","first_code_differences") if k in detail}
        report["failure"]=str(detail)[:4000];print(report["failure"],flush=True)
    finally: (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__=="__main__": raise SystemExit(main())
