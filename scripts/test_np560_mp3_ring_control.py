#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""CRC, resync, ring fullness, odd cursors and consumption carry in guest.

Synthetic Layer III zero-spectrum frames are control vectors, NOT pretend
music/game audio. CRC expected words use the pinned libmad byte table,
independent of the guest's bit-loop implementation. The real PRG producer
feeds every stream. A counter seed is diagnostic guest setup, never a host
write or part of the production API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import build_np560_mp3_ring as ring
import build_np560_mp3_decoder as decoder
import build_np560_mp3_allocation as lease
from build_np560_mp3_huffman import ROOT
from build_np560_mp3_resident import load_bundle
from np560_mp3_link import fragments
from np560_assembler import _DMCUAssembler
from test_np560_mp3_allocation import PROGRAM,PRG_SHA,FUNCTIONS,layout
from test_np560_mac import run
from scan_np560_mpeg_tables import array


def vector():
    raw=(ROOT/"doc/sources/libmad-20260907/bit.c").read_bytes()
    table=array(raw.decode(),"crc_table");assert len(table)==256
    crc=65535
    for b in bytes.fromhex("9000")+bytes(32): crc=((crc<<8)^table[((crc>>8)^b)&255])&65535
    data=bytes.fromhex("fffa9000")+struct.pack(">H",crc)+bytes(417-6)
    return data,{"crc":crc,"crc_reference_sha256":hashlib.sha256(raw).hexdigest(),
                 "reference":"pinned libmad bit.c crc_table byte recurrence"}


def check(qemu,output,bundle,icount):
    cores,rom,manifest=load_bundle(bundle);entries=cores["ring"]["entries"]
    deferred=manifest.get("rom_mp3_hle",{}).get("deferred_input_retirement",False)
    desc=layout(0);bank,base=desc[4],desc[8];assert base==0
    frame,reference=vector();bad=bytearray(frame);bad[5]^=1
    streams=[frame,bytes(bad),bytes.fromhex("00fa9000")+frame[4:],bytes(1532),frame*2]
    original=PROGRAM.read_bytes();assert hashlib.sha256(original).hexdigest()==PRG_SHA
    payload=bytearray(original[0x1000:])
    for index,raw in enumerate(streams):
        raw+=b"\0"*(len(raw)%2)
        packed=b"".join(raw[i:i+2][::-1] for i in range(0,len(raw),2))
        off=0x380000+index*0x1000-0x31000;payload[off:off+len(packed)]=packed
    a=_DMCUAssembler(0x30000);expected=[];cases=[]
    def imm(r,v): a.emit(0x68f0|r,v&65535)
    def const(off,v): imm(0,v);a.emit(0xa8f0,off)
    def call(target): a.emit(0xbd00|target>>16,target&65535)
    def entry(name): a.emit(0x6810,bank);imm(3,base);call(entries[name])
    def sample(r,value):
        a.emit(0x1f10,0x6810,0,0xa8f0|r,0x2400+2*len(expected),0x1f90)
        expected.append(value&65535)
    def begin(start=0x1000): imm(0,start);entry("reset");sample(2,0)
    def feed(index,count):
        for v in (count,index*0x1000,0x38): imm(0,v);a.emit(0x58f0)
        call(0x16e844);a.emit(0x50f6)
    def position(words):
        # The real caller writes this after 485A (1D:3792/3796), for seek.
        a.emit(0x6811,0);const(0xb350,words>>16);const(0xb352,words&65535)
    def record(name,r0,r2,consumed,start,written,word_base=0,held=0):
        sample(0,r0);sample(2,r2)
        entry("free_words");sample(0,766-(written-consumed+held+1)//2);sample(2,0)
        if held:
            entry("free_words");sample(0,766-(written-consumed+1)//2);sample(2,0)
        a.emit(0x88f0,ring.READ);sample(0,0x1000+(start-0x1000+consumed)%0x600)
        a.emit(0x88f0,ring.BYTES_LO);sample(0,consumed&65535)
        a.emit(0x88f0,ring.BYTES_HI);sample(0,consumed>>16)
        absolute=(word_base+consumed//2)&0xffffffff
        a.emit(0x6811,0,0x88f0,0xb350);sample(0,absolute>>16)
        a.emit(0x88f0,0xb352);sample(0,absolute&65535)
        cases.append(name)
    a.emit(0x6800,2,0x68ff,0x6000,0x6810,0,0x6811,0);call(0x308c1c)
    for off in range(18):
        if off%2==0: const(0x2200+off,0)
    imm(3,0x2200);call(cores["allocation"]["entries"]["acquire"]);sample(2,0)
    a.emit(0x6810,bank)
    for off,v in ((decoder.SYN_BANK,desc[5]),(decoder.SYN_LEFT,desc[6]),(decoder.SYN_RIGHT,desc[7])): const(off,v)
    begin(0x15fc);feed(0,1);entry("step");record("partial-header",0,1,0,0x15fc,2)
    # Reset and supply a complete header but no side information/CRC yet.
    begin(0x15fc);feed(0,2);entry("step");record("partial-protected-frame",0,1,0,0x15fc,4)
    first_consumed=0 if deferred else 417
    held=417 if deferred else 0
    begin(0x15fc);feed(0,209);entry("step");record("crc-valid-first-granule",576,0,first_consumed,0x15fc,418)
    # The compressed zero-spectrum input must really decode to all-zero PCM.
    imm(3,decoder.PCM[0]);imm(1,1152);imm(2,0)
    a.label("zero_pcm");a.emit(0x3803,0x1520,0x5211);a.ajmp("zero_pcm",2);sample(2,0)
    entry("step");record("second-granule-completes-frame",576,0,417,0x15fc,418,held=held)
    entry("step");record("trailing-half-word",0,1,417,0x15fc,418)
    begin();feed(1,209);entry("step");record("crc-rejected-no-consumption",0,5,0,0x1000,418)
    begin();feed(2,209);entry("step");record("sync-rejected-one-byte",0,3,1,0x1000,418)
    begin();feed(3,766);entry("free_words");sample(0,0);sample(2,0)
    entry("step");record("full-ring-partial-word-still-occupied",0,3,1,0x1000,1532)
    entry("step");record("full-ring-one-word-freed",0,3,2,0x1000,1532)
    begin();a.emit(0x6811,0);const(0xb340,0x1001)
    entry("free_words");sample(0,0);sample(2,2);cases.append("invalid-producer-cursor")
    begin();const(ring.READ,0x1600);entry("free_words");sample(0,0);sample(2,2);cases.append("invalid-consumer-cursor")
    begin();const(ring.BYTES_LO,0xfffe);position(0x7fff)
    feed(0,209);entry("step");sample(0,576);sample(2,0)
    if deferred:
        entry("step");sample(0,576);sample(2,0)
    for off,v in ((ring.BYTES_LO,0x019f),(ring.BYTES_HI,1)):
        a.emit(0x88f0,off);sample(0,v)
    a.emit(0x6811,0,0x88f0,0xb350);sample(0,0)
    a.emit(0x88f0,0xb352);sample(0,0x80cf);cases.append("byte-counter-carry-to-original-word-position")
    # Exercise the caller's full 32-bit *word* position, not a truncated
    # 32-bit byte address. These two odd frames advance by 208 then 209.
    seek_words=0x8123ff80
    begin(0x15fc);position(seek_words);feed(4,417)
    entry("step");record("seek-first-granule",576,0,first_consumed,0x15fc,834,seek_words)
    entry("step");record("seek-completed-frame-low-word-carry",576,0,417,0x15fc,834,seek_words,held=held)
    entry("step");record("seek-second-odd-frame-retains-half-word",576,0,417 if deferred else 834,0x15fc,834,seek_words)
    if deferred:
        entry("step");record("seek-second-frame-completes-parity",576,0,834,0x15fc,834,seek_words,held=held)
    begin();record("reset-clears-seek-position-and-pending",0,0,0,0x1000,0)
    if "release" in entries:
        entry("release");sample(2,0)
    a.emit(0x6810,0,0x68f3,0x2200);call(cores["allocation"]["entries"]["release"]);sample(2,0)
    words=a.finish();assert len(words)*2+2<0x1000
    checks=[(address,data) for c in cores.values() for _,address,data in fragments(c)]
    checks += [(addr,original[addr-0x30000:addr-0x30000+size]) for addr,size in FUNCTIONS]
    result=run(qemu,output,f"ring-control-icount{icount}",words,{15:0x6000},rom=rom,tail=(0x1000,payload),
        rom_mp3_hle_base=manifest.get("rom_mp3_hle",{}).get("base",0),
        boot_mode="firmware-vma03",icount=icount,expected_data=[v-65536 if v&0x8000 else v for v in expected],
        expected_code=checks,timeout=60,poll_interval=.25,metadata={"control_cases":cases,
            "reference":reference,"rom_sha256":manifest["rom_sha256"],"factory_player_connected":False})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,required=True);p.add_argument("--resident-bundle",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    report={"passed":False,"cases":[],"qemu_sha256":hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    try:
        for icount in (None,5): report["cases"].append(check(args.qemu,args.output,args.resident_bundle,icount))
        report["passed"]=all(c["passed"] and c["exit_code"]==0 for c in report["cases"])
    except AssertionError as exc:
        detail=exc.args[0] if exc.args else str(exc)
        if isinstance(detail,dict):
            detail={"registers":detail.get("registers"),"differences":[(i,x,y) for i,(x,y) in enumerate(zip(detail.get("actual_samples",[]),detail.get("expected_samples",[]))) if x!=y][:20]}
        report["failure"]=str(detail)[:2500];print(report["failure"],flush=True)
    finally: (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__=="__main__": raise SystemExit(main())
