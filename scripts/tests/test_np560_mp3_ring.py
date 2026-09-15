#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Real PRG word producer + parser + ROM ring adapter -> captured native PCM.

Diagnostic guest feeds bounded word chunks through the original 16:E844,
not per-frame contexts. Header fields and side offsets are obtained by the
guest itself. Expected frame boundaries/PCM are read-only comparison data.
No host RAM writes, NAND, original-player success claim or audio interception.
"""
from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

import build_np560_mp3_ring as ring
import build_np560_mp3_decoder as decoder
import build_np560_mp3_allocation as lease
from build_np560_mp3_resident import load_bundle
from np560_mp3_link import fragments
from np560_assembler import _DMCUAssembler
from test_np560_mp3_allocation import PROGRAM,PRG_SHA,FUNCTIONS,layout
from test_np560_mp3_header import PARSER,TABLES,PARSER_SHA256,TABLES_SHA256,original_slice
from test_np560_mp3_frame import fixtures,network_words,pcm_artifact
from test_np560_mac import run

FIXTURE,STREAM,CAPTURE=0x3c8000,0x380000,0x4f0000
TRACE,DESC,RESULT,CAPTURE_PTR=0x2400,0x2200,0x30,0x38


def far(address): return [address>>15,0x8000|(address&0x7fff)]


def events(frames,raw,bank,base,start):
    begin=frames[0]["file_offset"];end=frames[-1]["file_offset"]+frames[-1]["frame_bytes"]
    stream=raw[begin:end]
    # A word producer may also read the next frame's first byte. Use that
    # actual file byte, not an invented zero at an odd prefix boundary.
    # End-of-file partial-word ownership belongs to the future file adapter.
    assert end+len(stream)%2<=len(raw), "odd EOF needs original EOF integration; choose an interior prefix"
    padded=raw[begin:end+len(stream)%2]
    written=consumed=index=granule=0;current_pcm=[[0]*576 for _ in range(2)]
    actions=[];chunks=(1,7,211,3,64,509,2,127);chunk_index=0
    next_write=False;last_format=None
    while index<len(frames) or not next_write:
        args=[];expected=[];productive=False
        if next_write:
            available=written-consumed;free=766-(available+1)//2
            count=min(chunks[chunk_index%len(chunks)],free,(len(padded)-written)//2)
            assert count>0, "fixture cannot satisfy next complete frame"
            chunk_index+=1;source=STREAM+written;written+=count*2
            args=[count,source&65535,source>>16];op=0
            expected_result=[(STREAM+written)>>16,(STREAM+written)&65535]
            next_write=False
        else:
            op=1;f=frames[index] if index<len(frames) else None
            if not f or (not granule and written-consumed<f["frame_bytes"]):
                expected_result=[0,1];next_write=True
            else:
                productive=True;expected_result=[576,0]
                if not granule: consumed+=f["frame_bytes"]
                nch=f["nch"];ngr=len(f["segments"])//nch
                for ch in range(nch): current_pcm[ch]=f["segments"][granule*nch+ch]["synthesis"]["pcm"]
                if nch==1: current_pcm[1]=[0]*576
                ident=(f["segments"][0]["rate"],nch)
                expected.append((bank,base+ring.FORMAT_CHANGE,[int(ident!=last_format)]));last_format=ident
                granule+=1
                if granule==ngr: index+=1;granule=0
        available=written-consumed;free=766-(available+1)//2
        read=0x1000+(start-0x1000+consumed)%0x600
        writer=0x1000+(start-0x1000+written)%0x600
        expected += [(bank,base+RESULT,expected_result+[free]),
            (bank,base+ring.READ,[read,consumed&65535,consumed>>16,ring.MAGIC_VALUE]),
            (0,ring.WRITER,[writer]),(0,0x3350,[(consumed//2)>>16,(consumed//2)&65535]),
            (0,0xffe,[0xcafe]),(0,0x1600,[0xcafe]),
            (bank,base+decoder.WORKSPACE_BYTES,[0xcafe])]
        for ch in range(2): expected.append((bank,base+decoder.PCM[ch],current_pcm[ch]))
        actions.append({"op":op,"args":args,"expected":expected,"written":written,
            "consumed":consumed,"free_words":free,"productive":productive,
            "frame_after":index,"granule_after":granule})
        if index==len(frames) and next_write: break
    records=[]
    for event in actions:
        encoded=[]
        for b,p,values in event["expected"]: encoded += [b,p,len(values)]+values
        encoded += [0,0,0]
        row=[0,0,event["op"]]+event["args"]+encoded
        row[:2]=far(FIXTURE+(len(records)+len(row))*2)
        records += row
    return records,actions,padded


def check(qemu,output,frames,mp3,bundle,start,icount,prefix_bytes):
    cores,rom,manifest=load_bundle(bundle);core=cores["ring"];allocation=cores["allocation"]
    desc=layout(prefix_bytes);assert desc[0]
    bank,base=desc[4],desc[8]
    records,actions,stream=events(frames,mp3.read_bytes(),bank,base,start)
    original=PROGRAM.read_bytes();assert hashlib.sha256(original).hexdigest()==PRG_SHA
    assert FIXTURE+len(records)*2<=0x430000 and STREAM+len(stream)<=FIXTURE
    a=_DMCUAssembler(0x030000)
    def imm(r,v): a.emit(0x68f0|r,v&65535)
    def const(addr,v): imm(0,v);a.emit(0xa8f0,addr)
    def call(target): a.emit(0xbd00|target>>16,target&65535)
    def entry(name): imm(3,base);call(core["entries"][name])
    def factory(target,arg): imm(0,arg);a.emit(0x58f0);call(target);a.emit(0x50f2)
    a.emit(0x6800,2,0x68ff,0x6000,0x6810,0,0x6811,0)
    call(0x308c1c)
    if prefix_bytes:
        factory(lease.ALLOC,prefix_bytes);a.emit(0x76f0,1);a.ajmp("failure",2)
        factory(lease.LOCK,1);a.emit(0x6810,0xa2);const(0x4a46,0xbeef)
    a.emit(0x6810,0)
    for off in range(0,lease.DESCRIPTOR_BYTES,2): const(DESC+off,0)
    imm(3,DESC);call(allocation["entries"]["acquire"])
    a.emit(0x76f2,0);a.ajmp("failure",2)
    for i,v in enumerate(desc): a.emit(0x88f0,DESC+i*2,0x76f0,v);a.ajmp("failure",2)
    for addr in range(TRACE,TRACE+8,2): const(addr,0)
    for addr in (0xffe,0x1600): const(addr,0xcafe)
    a.emit(0x88f0,DESC+lease.WORK_BANK,0x58f0,0x1f90)
    for off,v in ((decoder.SYN_BANK,desc[5]),(decoder.SYN_LEFT,desc[6]),(decoder.SYN_RIGHT,desc[7]),
                  (decoder.WORKSPACE_BYTES,0xcafe),(CAPTURE_PTR,CAPTURE>>15),(CAPTURE_PTR+2,0x8000)):
        const(base+off,v)
    imm(0,start);entry("reset");a.emit(0x76f2,0);a.ajmp("failure",2)
    a.emit(0x6811,FIXTURE>>15,0x68fe,FIXTURE>>15,0x68f9,0x8000,
        0x68f7,0,0x68f8,0,0x68fa,len(actions),0x68fc,0x7777)
    a.label("event")
    a.emit(0x6810,bank)
    for r in (6,4,13): a.acall("get_word");a.emit(0x0800|r<<4)
    a.emit(0x76fd,0);a.ajmp("step",2)
    a.emit(0x58fa)  # preserve remaining event count while R10 carries source offset
    for r in (5,10,11): a.acall("get_word");a.emit(0x0800|r<<4)
    for r in range(3,15): a.emit(0x58f0|r)
    a.emit(0x58f5,0x58fa,0x58fb);call(0x16e844);a.emit(0x50f6)
    for r in reversed(range(3,15)): a.emit(0x380f|r<<4)
    a.emit(0x38af)
    # The producer's public return is the advanced far source in R0:R1.
    a.emit(0xa8f0,base+RESULT,0xa8f1,base+RESULT+2);a.ajmp("called")
    a.label("step");entry("step")
    a.emit(0xa8f0,base+RESULT,0xa8f2,base+RESULT+2,0x76f2,0);a.ajmp("called",2)
    a.emit(0x76f0,576);a.ajmp("called",2)
    imm(3,base+decoder.PCM[0]);a.acall("capture_pcm")
    a.emit(0x88f0,base+decoder.FRAME+2,0x76f0,2);a.ajmp("called",2)
    imm(3,base+decoder.PCM[1]);a.acall("capture_pcm")
    a.label("called");entry("free_words");a.emit(0xa8f0,base+RESULT+4,0x76f2,0);a.ajmp("failure",2)
    a.label("range")
    a.acall("get_word");a.emit(0x58f0,0x1f90)
    a.acall("get_word");a.emit(0x0830)
    a.acall("get_word");a.emit(0x0850,0x76f5,0);a.ajmp("event_done",1)
    a.label("compare");a.acall("get_word");a.emit(0x0810,0x3803,0x1601);a.ajmp("same",1)
    a.acall("mismatch")
    a.label("same");a.emit(0x5251);a.ajmp("compare",2);a.ajmp("range")
    a.label("event_done");a.emit(0x0894,0x08e6,0x58fe,0x1f91,0x5081,0x52a1);a.ajmp("event",2)
    a.emit(0x6810,0);imm(3,DESC);call(allocation["entries"]["release"])
    a.emit(0x76f2,0);a.ajmp("failure",2)
    if prefix_bytes:
        a.emit(0x6810,0xa2,0x88f0,0x4a46,0x76f0,0xbeef);a.ajmp("failure",2)
        for r in range(3,15): a.emit(0x58f0|r)
        factory(lease.FREE,1);factory(lease.UNLOCK,1)
        for r in reversed(range(3,15)): a.emit(0x380f|r<<4)
    a.emit(0x6810,0xa2)
    for off,v in ((0x4a40,0),(0x4a42,0),(0x4a44,0),*((0x27ea+i*2,0x8000 if i==0 else 0) for i in range(16))):
        a.emit(0x88f0,off,0x76f0,v);a.ajmp("failure",2)
    a.ajmp("end")
    a.label("get_word");a.emit(0x2809,0x5092);a.ajmp("word_ready",2)
    a.emit(0x68f9,0x8000,0x50e1,0x58fe,0x1f91)
    a.label("word_ready");a.emit(0xc600)
    a.label("mismatch")
    a.emit(0x76f7,0);a.ajmp("count_mismatch",2)
    a.emit(0x1f10,0x6810,0,0xa8f8,TRACE,0xa8f3,TRACE+2,0xa8f0,TRACE+4,0xa8f1,TRACE+6,0x1f90)
    a.label("count_mismatch");a.emit(0x5071,0xc600)
    a.label("capture_pcm")
    for r in (0,1,2,3,5): a.emit(0x58f0|r)
    a.emit(0x1f11,0x88f2,base+CAPTURE_PTR,0x58f2,0x1f91,0x88f5,base+CAPTURE_PTR+2,0x68f1,576)
    a.label("capture_word");a.emit(0x3803,0x1a50,0x5211);a.ajmp("capture_word",2)
    a.emit(0xa8f5,base+CAPTURE_PTR+2,0x1f91)
    for r in (5,3,2,1,0): a.emit(0x380f|r<<4)
    a.emit(0xc600)
    a.label("failure");imm(7,65535)
    a.label("end")
    words=a.finish();assert len(words)*2+2<0x1000
    payload=bytearray(original[0x1000:])
    payload[STREAM-0x31000:STREAM-0x31000+len(stream)]=struct.pack(f"<{len(stream)//2}H",*network_words(stream))
    payload[FIXTURE-0x31000:FIXTURE-0x31000+len(records)*2]=struct.pack(f"<{len(records)}H",*(v&65535 for v in records))
    checks=[(addr,original[addr-0x30000:addr-0x30000+size]) for addr,size in FUNCTIONS]
    checks += [(PARSER[0],original_slice(original,PARSER,PARSER_SHA256)),(TABLES[0],original_slice(original,TABLES,TABLES_SHA256)),
               (0x16e844,original[0x13e844:0x13e898])]
    checks += [(addr,data) for c in cores.values() for _,addr,data in fragments(c)]
    pcm_bytes=1152*sum(len(f["segments"]) for f in frames)
    assert pcm_bytes<0x8000
    (output/"events.json").write_text(json.dumps([{k:v for k,v in e.items() if k!="expected"} for e in actions],indent=2)+"\n",encoding="utf-8")
    return run(qemu,output,"original-ring",words,{7:0,8:len(actions),10:0,12:0x7777,15:0x6000},
        rom=rom,tail=(0x1000,payload),boot_mode="firmware-vma03",icount=icount,timeout=180,poll_interval=.25,
        expected_data=[0]*4,expected_code=checks,capture_ranges=[("guest-pcm",CAPTURE,pcm_bytes),
            ("workspace",(bank<<15)+base,decoder.WORKSPACE_BYTES)],metadata={
        "frames":len(frames),"events":len(actions),"initial_ring_pointer":start,"original_writer_called":True,
        "original_header_parser_called":True,"host_supplied_frame_contexts":0,"original_heap_descriptor":desc,
        "rom_sha256":manifest["rom_sha256"],"factory_player_connected":False})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--qemu",type=Path,required=True);p.add_argument("--mp3",type=Path,required=True)
    p.add_argument("--resident-bundle",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--limit",type=int,default=3);p.add_argument("--icount",type=int)
    p.add_argument("--start",type=lambda s:int(s,0),default=0x15fc)
    p.add_argument("--heap-prefix-bytes",type=lambda s:int(s,0),choices=(0,0x2000,0x4000,0x5000),default=0x4000)
    args=p.parse_args();assert args.limit>0 and 0x1000<=args.start<0x1600 and args.start%2==0
    args.output.mkdir(parents=True,exist_ok=False)
    report={"passed":False,"qemu_sha256":hashlib.sha256(args.qemu.read_bytes()).hexdigest(),"cases":[]}
    try:
        frames=fixtures(args.mp3,args.output,args.limit,True,True,0,True,True,True)
        case=check(args.qemu,args.output,frames,args.mp3,args.resident_bundle,args.start,args.icount,args.heap_prefix_bytes)
        report["cases"].append(case)
        comparison=pcm_artifact(args.mp3,args.output,frames,case)
        report.update(pcm_comparison=comparison,passed=case["passed"] and case["exit_code"]==0 and comparison["within_8_pcm_lsb"])
    except (AssertionError,subprocess.CalledProcessError) as exc:
        detail=exc.args[0] if exc.args else str(exc)
        if isinstance(detail,dict): detail={k:detail[k] for k in ("name","registers","actual_samples","code_phase","first_code_differences") if k in detail}
        report["failure"]=str(detail)[:2500];print(report["failure"],flush=True)
    finally: (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__=="__main__": raise SystemExit(main())
