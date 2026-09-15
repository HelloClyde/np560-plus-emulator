#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Original MP3 public entries own their memory and dispatch PRG callbacks.

No diagnostic entry trampolines or host-provided owner. 4804 allocates the
control object; 49F8/49BE/4954, 485A and callback registration execute the
experimental native ROM. The original 16:E89C consumes continuous MP3 input.
This is a stopped, isolated software caller, not a complete playing device.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

import build_np560_mp3_factory as factory
import build_np560_mp3_allocation as lease
from build_np560_mp3_resident import load_bundle
from np560_assembler import _DMCUAssembler
from np560_mp3_link import fragments
from test_np560_mp3_allocation import PROGRAM, PRG_SHA, FUNCTIONS, HEAP_BEGIN
from test_np560_mp3_session import PARAMS, NEIGHBOURS
from test_np560_mp3_frame import fixtures, pcm_artifact, network_words
from test_np560_mac import run

DIAG, RESULT, CAPTURE, STREAM = 0x800, 0x900, 0x4f0000, 0x380000


def check(qemu,output,mp3,frames,bundle,icount,preconfigured_format=False,preconfigured_rate=None,
          preconfigured_selector=False,profile_pc=False,query_edges=False,eof_tail=False,
          finite_word_tail=False,startup_prime_count=None):
    cores,rom,manifest=load_bundle(bundle)
    assert manifest["experimental_factory_abi"]
    if finite_word_tail:
        assert eof_tail, "finite word tail requires the original EOF producer"
        assert manifest.get("rom_mp3_hle",{}).get("bounded_final_frame"), \
            "finite word tail requires a bounded_final_frame HLE bundle"
    deferred=manifest.get("rom_mp3_hle",{}).get("deferred_input_retirement",False)
    final_retirement=manifest.get("rom_mp3_hle",{}).get("final_input_retirement")
    original=PROGRAM.read_bytes();assert hashlib.sha256(original).hexdigest()==PRG_SHA
    raw=mp3.read_bytes();first=frames[0]["file_offset"]
    end=frames[-1]["file_offset"]+frames[-1]["frame_bytes"]
    prefix_bytes=end-first
    # A finite word-count producer cannot supply the last unpaired byte.
    # The older prefix test borrows the following byte to align its input;
    # retain that default, but never borrow or pad in this explicit case.
    stream_end=end-prefix_bytes%2 if finite_word_tail else end+prefix_bytes%2
    stream=raw[first:stream_end]
    assert len(stream)%2==0 and len(stream)<=1532
    # Exact even-byte EOF is also a final packet; only the legacy odd
    # prefix that borrows a following byte still has input beyond its frame.
    held_final=eof_tail and final_retirement=="next-step" and len(stream)<=prefix_bytes
    tail_input={"finite_word_tail":finite_word_tail,"prefix_bytes":prefix_bytes,
                "producer_bytes":len(stream),"omitted_final_bytes":max(0,end-stream_end),
                "borrowed_next_frame_bytes":max(0,len(stream)-prefix_bytes),
                "omitted_final_hex":raw[stream_end:end].hex() if finite_word_tail else "",
                "final_input_retirement":final_retirement,"held_until_next_step":held_final,
                "pcm_reference":"complete_declared_frames"}
    nch=frames[0]["nch"];assert all(f["nch"]==nch for f in frames)
    owner_address=HEAP_BEGIN+6+sum(n+6 for n in NEIGHBOURS)
    expected=[];names=[];a=_DMCUAssembler(0x30000)
    def imm(r,v): a.emit(0x68f0|r,v&65535)
    def call(target): a.emit(0xbd00|target>>16,target&65535)
    def arg(v): imm(0,v);a.emit(0x58f0)
    def original_heap(target,v): arg(v);call(target);a.emit(0x50f2)
    def const(addr,v): imm(0,v);a.emit(0x3f10,0xa8f0,addr)
    def sample(r,value,name):
        a.emit(0x3f10,0xa8f0|r,RESULT+len(expected)*2)
        expected.append(value&65535);names.append(name)
    def value(addr,want,name): a.emit(0x3f10,0x88f0,addr);sample(0,want,name)
    def result(r0,r2,name): sample(0,r0,name+".r0");sample(2,r2,name+".r2")
    def root(name,opened=True):
        value(factory.ROOT,owner_address>>16 if opened else 0,name+".segment")
        value(factory.ROOT+2,owner_address&65535 if opened else 0,name+".offset")
    def init(name):
        for v in reversed(PARAMS): arg(v)
        call(0x14804);a.emit(0x70ff,26);result(0,0,name);root(name)
    def output_pair(phase,name):
        for v in (DIAG+0x14,0,DIAG+0x10,0): arg(v)
        call(0x14954);a.emit(0x50f8);result(0,0,name)
        for i,v in enumerate((0,PARAMS[1+phase*2],0,PARAMS[5+phase*2])):
            value(DIAG+0x10+i*2,v,name+f".pointer{i}")
    def flag(group,bit,want,name):
        a.emit(0x7c00|group,0x7000|bit<<4,0x74f0,1);sample(0,want,name)
    def capture(label):
        for ch in range(nch):
            a.emit(0x6810,0,0x6811,CAPTURE>>15,0x88f5,DIAG+0x12+ch*4,0x88f6,DIAG+6)
            imm(1,576);a.label(label+str(ch))
            a.emit(0x3805,0x1a60,0x5211);a.ajmp(label+str(ch),2)
            a.emit(0xa8f6,DIAG+6)
    def zero_outputs(label):
        a.emit(0x6810,0);imm(5,0x1784);imm(1,2304);imm(2,0)
        a.label(label);a.emit(0x3805,0x1520,0x5211);a.ajmp(label,2)
        sample(2,0,label)
    def close(name):
        call(manifest["factory"]["entries"]["close"]);result(0,0,name);root(name,False)
    a.emit(0x6800,2,0x68ff,0x6000,0x6810,0,0x6811,0);call(0x308c1c)
    root("device reset root",False)
    for i,size in enumerate(NEIGHBOURS,1):
        original_heap(lease.ALLOC,size);sample(0,i,f"neighbour{i}")
        original_heap(lease.LOCK,i)
    for addr,v in ((0x333c,0xcafe),(0x3348,0xbeef),(0x33d4,1),(DIAG+6,0x8000)):
        const(addr,v)
    for group in (0x88,0x89,0x8a,0x8c):
        for bit in range(16): a.emit(0xf000|bit<<8|group)
    for off in (0x4a52,0x4a54,0x4a56,0x4a58,0x4a5a,0x4a76,0x4a78): const(off,0)
    init("public init");zero_outputs("init clears outputs")
    flag(0x83,15,0,"initial priming gate clear")
    call(0x1485a);result(0,0,"public reset")
    output_pair(1,"initial output");call(0x149be);result(766,0,"initial free")
    if query_edges:
        # A real guest caller edits its OWN allocated session for differential
        # native/HLE error-contract checks; no host RAM injection or NAND.
        import build_np560_mp3_session as session
        from build_np560_mp3_ring import READ, MAGIC, MAGIC_VALUE
        def owner_const(off,v):
            a.emit(0x6811,owner_address>>15);imm(0,v)
            a.emit(0xa8f0,0x8000|(owner_address&0x7fff)+off,0x6811,0)
        def work_const(off,v):
            a.emit(0x6810,owner_address>>15)
            a.emit(0x88f0,(owner_address&0x7fff)+lease.WORK_BANK,0x58f0,0x1f91)
            a.emit(0x88f1,(owner_address&0x7fff)+lease.WORK_OFFSET,0x70f1,off,0x75f1,0x8000)
            imm(0,v);a.emit(0x0a10,0x6810,0,0x6811,0)
        def query(name,r0,r2,error):
            const(0x3346,0x4567);call(0x149be);result(r0,r2,name)
            value(0x3346,error,name+".error")
        const(factory.ROOT,0xffff);query("root busy",0,7,0x4567)
        const(factory.ROOT,owner_address>>16)
        owner_const(session.BUSY,1);query("session busy",0,7,1)
        owner_const(session.BUSY,0)
        owner_const(session.MAGIC,0);query("closed session",0,8,1)
        owner_const(session.MAGIC,session.MAGIC_VALUE)
        work_const(MAGIC,0);query("bad ring magic",0,2,1)
        work_const(MAGIC,MAGIC_VALUE)
        for name,read,writer,r0,r2 in (
                ("partial odd word",0x1105,0x1200,640,0),
                ("odd wrap",0x15ff,0x1000,765,0),
                ("full guarded ring",0x1000,0x15fc,0,0),
                ("overfull ring",0x1000,0x15fe,0,2),
                ("bad reader",0x0fff,0x1000,0,2),
                ("odd writer",0x1000,0x1001,0,2),
                ("writer past end",0x1000,0x1600,0,2)):
            work_const(READ,read);const(0x3340,writer)
            query(name,r0,r2,1 if r2 else 0x4567)
        work_const(READ,0x1000);const(0x3340,0x1000)
        const(factory.ROOT+2,0x7fe0);query("cross-bank owner",0,2,1)
        const(factory.ROOT,0);const(factory.ROOT+2,0);query("closed root",0,8,1)
        const(factory.ROOT,owner_address>>16);const(factory.ROOT+2,owner_address&65535)
        call(0x1485a);result(0,0,"reset after query edges")
    hz=(44100,48000,32000,22050,24000,16000,11025,12000,8000)[frames[0]["segments"][0]["rate"]]
    if preconfigured_format:
        # Exercise original setup BEFORE registering 46F2: decode
        # the actual header with the original parser, then call the original
        # format routine. The initial compressed staging buffers are already
        # primed in the application when its first PCM frame arrives.
        a.emit(0x6810,0xa2,0x6811,0xa2)
        for i in range(2):
            imm(0,int.from_bytes(stream[i*2:i*2+2],"big"));a.emit(0xa8f0,0x2846+i*2)
        call(0x16e45e);sample(0,0,"original initial header parsed")
        configured_hz=preconfigured_rate or hz
        # The real 1D:3708 caller passes a table selector, NOT Hz. Raw Hz
        # chooses different hardware routes in 08:2F22 and is a separate case.
        selectors={8000:1,16000:2,32000:3,11025:4,22050:5,44100:6,
                   12000:7,24000:8,48000:9}
        configured_arg=selectors[configured_hz] if preconfigured_selector else configured_hz
        arg(configured_arg);call(0x2fa6ba);a.emit(0x50f2)
        value(0x4a60,configured_hz,"rate configured before first decoded frame")
        pll_offset=0x32bd96-0x30000+(configured_arg-1)*8+6
        configured_pll=(int.from_bytes(original[pll_offset:pll_offset+2],"little")
                        if preconfigured_selector else 0x0aa6)
        value(0xf2d4,0x8000|configured_pll,"original audio PLL table value, not pointer writeback")
        flag(0x8a,10,1,"format configured before callback registration")
        # Table entries use dedicated requests for 22.05/24/32/44.1/48 kHz;
        # raw-Hz setup uses Timer1/2. These are software routing assertions,
        # not proof that an audio clock or DTU transfer has started.
        dedicated=preconfigured_selector and configured_hz in (22050,24000,32000,44100,48000)
        for bit in (12,13):
            flag(0x8e,bit,int(dedicated),f"initial dedicated audio route {bit}")
        # A is in use/requested; B has been filled. These are isolated guest
        # control vectors, not host writes or production repairs to flags.
        a.emit(0xe08a,0xf18a,0xfb8a)
    for entry,target in ((0x146f2,0x2fa6ba),(0x146d4,0x16edb2)):
        arg(target&65535);arg(target>>16);call(entry);a.emit(0x50f4)
        result(0,0,f"register callback {entry:06x}")
    call(0x149f8);result(0,1,"public empty step");value(0x3346,0,"empty is nonfatal")
    if eof_tail:
        # A finite guest-owned tail, supplied through the ORIGINAL producer.
        # The alternate source buffer is unavailable. EAC2 returns zero
        # words, so EA94 (not this test) publishes the original EOF flag.
        a.emit(0x6811,0xa2)
        for off,v in ((0xa852,len(stream)//2),(0xa858,STREAM>>16),(0xa85a,0)):
            imm(0,v);a.emit(0xa8f0,off)
        a.emit(0xe18a,0xfb8a,0xfe89)
        call(0x16ea42);a.emit(0x6811,0)
        flag(0x89,7,1,"original producer publishes finite tail")
        flag(0x89,11,0,"producer does not finish before decode")
    else:
        for v in (len(stream)//2,0,STREAM>>16): arg(v)
        call(0x16e844);a.emit(0x50f6)
    if startup_prime_count is not None:
        assert manifest.get("rom_mp3_hle",{}).get("startup_priming")
        assert preconfigured_format and preconfigured_selector
        # Original startup loops accept nonfatal no-PCM before E89C refill.
        a.emit(0x6810,0xa2)
        a.emit(0x88f0,0x2b10)
        sample(0,startup_prime_count,"original configured priming count")
        a.emit(0x6810,0)
        for index in range(startup_prime_count-1):
            call(0x149f8);result(0,1,f"prime{index}.nonfatal without PCM")
            value(0x3346,0,f"prime{index}.not a decoder failure")
            value(0x3352,0,f"prime{index}.input retained")
            flag(0x83,15,0,f"prime{index}.not ready yet")
            output_pair(1,f"prime{index}.initial output retained")
            for offset in (0x1784,0x1c04,0x2084,0x2504):
                value(offset,0,f"prime{index}.unpublished PCM {offset:04x}")
            call(0x149be);result(766-(len(stream)+1)//2,0,f"prime{index}.occupied input retained")
    phase=1;consumed=0;granules=0
    total_granules=sum(len(frame["segments"])//nch for frame in frames)
    for frame_index,frame in enumerate(frames):
        hold_frame=held_final and frame_index==len(frames)-1
        for gr in range(len(frame["segments"])//nch):
            if not hold_frame and gr==(len(frame["segments"])//nch-1 if deferred else 0):
                # Final-frame HLE may decode a bounded, word-truncated tail,
                # but public retirement must count only real producer bytes.
                consumed+=min(frame["frame_bytes"],len(stream)-consumed) if finite_word_tail else frame["frame_bytes"]
            call(0x16e89c)
            value(0x3346,0,f"granule{granules}.error")
            value(0x3352,consumed//2,f"granule{granules}.public consumed words")
            flag(0x8c,8,0,f"granule{granules}.not exhausted")
            flag(0x83,15,1,f"granule{granules}.real PCM priming gate")
            if eof_tail:
                flag(0x89,7,1,f"granule{granules}.producer EOF retained")
            if eof_tail and (granules+1<total_granules or held_final):
                # BIT89.11 sends the original IRQ to the stop callback.
                # Continuing our isolated caller after it is diagnostic,
                # not evidence that the real player delivers the tail.
                flag(0x89,11,0,f"granule{granules}.must not finish with PCM pending")
            phase^=1;output_pair(phase,f"granule{granules}.output")
            capture(f"pcm-{granules}-")
            free_words=766-(len(stream)-consumed+1)//2
            call(0x149be);result(free_words,0,f"granule{granules}.free")
            if hold_frame:
                # A capacity query is not a new decoder step and must not
                # retire the final packet or release its original EOF guard.
                for query in range(2):
                    call(0x149be);result(free_words,0,f"granule{granules}.held free repeat{query}")
                value(0x3352,consumed//2,f"granule{granules}.queries retain public position")
                flag(0x89,11,0,f"granule{granules}.queries retain final PCM")
            if granules==0:
                if startup_prime_count is not None:
                    a.emit(0x6810,owner_address>>15,0x88f0,
                           (owner_address&0x7fff)+factory.FIRST_FORMAT_SEEN)
                    sample(0,1,"first real PCM retains initial format notification")
                    a.emit(0x6810,0)
                value(0x4a60,hz,"original callback sample rate")
                flag(0x8a,10,1,"original format callback completed")
                if preconfigured_format:
                    flag(0x8a,0,1,"first frame keeps buffer A request")
                    flag(0x8a,1,int(eof_tail or configured_hz!=hz),
                         "finite tail keeps alternate source unavailable" if eof_tail else
                         "different rate reconfigures buffer B" if configured_hz!=hz else
                         "first frame keeps filled buffer B")
                    flag(0x8a,11,0,"first frame keeps current buffer selection")
                for i,v in enumerate((576,0x1784,0x2084,0x1c04,0x2504)):
                    value(0x4ab0+i*2,v,f"original DAC config {i}")
            granules+=1
    call(0x16e89c);value(0x3346,0,"trailing input nonfatal")
    if held_final:
        value(0x3352,len(stream)//2,"next step retires actual final input words")
        call(0x149be);result(766,0,"next step releases final packet capacity")
    flag(0x8c,8,1,"original exhausted flag");value(0x4a76,16,"original fade countdown")
    if eof_tail:
        flag(0x89,11,1,"original exhaustion finishes finite tail")
    output_pair(phase,"trailing input keeps buffers")
    call(0x1485a);result(0,0,"public reset after PCM")
    flag(0x83,15,0,"reset invalidates priming gate")
    output_pair(1,"reset output");zero_outputs("reset clears outputs")
    # Reinit an existing live object: old core AND old owner must be freed.
    init("reinitialize owned instance");close("close reinitialized instance")
    call(0x149be);result(0,8,"closed free query")
    value(0x3346,1,"closed query failure")
    init("reopen after close");close("close reopened instance");close("repeat close")
    for addr,v in ((0x333c,0xcafe),(0x3348,0xbeef),(0x33d4,1)):
        value(addr,v,f"shared guard {addr:04x}")
    for handle in range(5,0,-1):
        original_heap(lease.FREE,handle);original_heap(lease.UNLOCK,handle)
    a.emit(0x6810,0xa2)
    for off,v in ((0x4a40,0),(0x4a42,0),(0x4a44,0),*((0x27ea+i*2,0x8000 if i==0 else 0) for i in range(16))):
        a.emit(0x88f0,off);sample(0,v,f"clean heap {off:04x}")
    words=a.finish();assert len(words)*2+2<0x1000,("caller too large",len(words)*2)
    payload=bytearray(original[0x1000:]);packed=struct.pack(f"<{len(stream)//2}H",*network_words(stream))
    payload[STREAM-0x31000:STREAM-0x31000+len(packed)]=packed
    code=[(addr,original[addr-0x30000:addr-0x30000+size]) for addr,size in FUNCTIONS]
    for start,end in ((0x16e89c,0x16eb0a),(0x16edfa,0x16ee34),(0x2fa6ba,0x2fa7ee),(0x082f22,0x083314),
                      (0x2497ac,0x2498fc),(0x16edb2,0x16edb4)):
        code.append((start,original[start-0x30000:end-0x30000]))
    code += [(addr,data) for core in cores.values() for _,addr,data in fragments(core)]
    case=run(qemu,output,"factory",words,{15:0x6000},rom=rom,tail=(0x1000,payload),
        rom_mp3_hle_base=manifest.get("rom_mp3_hle",{}).get("base",0),
        boot_mode="firmware-vma03",icount=icount,timeout=180,
        poll_interval=.05 if profile_pc else .25,profile_pc=profile_pc,
        expected_code=code,capture_ranges=[("checks",RESULT,len(expected)*2),
            ("guest-pcm",CAPTURE,granules*nch*1152)],metadata={
                "rom_sha256":manifest["rom_sha256"],"frames":len(frames),"granules":granules,
                "diagnostic_owner_trampolines":False,"owner_allocated_by":"original ABI 01:4804 native implementation",
                "original_callbacks":["2F:A6BA","16:EDB2"],
                "preconfigured_format":preconfigured_format,
                "preconfigured_hz":(preconfigured_rate or hz) if preconfigured_format else None,
                "preconfigured_argument":configured_arg if preconfigured_format else None,
                "preconfigured_selector":preconfigured_selector,
                "finite_tail_via_original_producer":eof_tail,
                "tail_input":tail_input,
                "factory_player_connected":False,"full_player_test":False,
                "automatic_stop_exit_release_connected":False})
    actual=struct.unpack(f"<{len(expected)}H",Path(case["captures"]["checks"]["path"]).read_bytes())
    diffs=[{"index":i,"check":name,"expected":want,"actual":got}
           for i,(name,want,got) in enumerate(zip(names,expected,actual)) if want!=got]
    case["control_checks"]={"count":len(expected),"differences":diffs,"passed":not diffs}
    (output/"control-values.json").write_text(json.dumps([
        {"check":name,"expected":want,"actual":got}
        for name,want,got in zip(names,expected,actual)],indent=2)+"\n",encoding="utf-8")
    (output/"control-checks.json").write_text(json.dumps(case["control_checks"],indent=2)+"\n",encoding="utf-8")
    case["passed"] = case["passed"] and not diffs
    if diffs:
        print("factory ABI contract failed: "+json.dumps(diffs[:20]),flush=True)
    return case


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ("qemu","mp3","resident-bundle","output"): p.add_argument("--"+flag,type=Path,required=True)
    p.add_argument("--limit",type=int,
                   help="prefix frames; default 3, or 2 with --query-edges/--eof-tail (3 with --finite-word-tail)")
    p.add_argument("--icount",type=int)
    p.add_argument("--startup-prime-count",type=int,choices=(1,2,3),
                   help="verify configured v6 priming before normal refill")
    p.add_argument("--preconfigured-format",action="store_true",
                   help="original rate setup and primed buffer flags precede first PCM")
    p.add_argument("--preconfigured-rate",type=int,choices=(44100,48000,32000,22050,24000,16000,11025,12000,8000),
                   help="use another existing rate to require the initial format-change callback")
    p.add_argument("--preconfigured-selector",action="store_true",
                   help="pass the original 1D:3708 rate selector instead of raw Hz")
    p.add_argument("--profile-pc",action="store_true",
                   help="record existing read-only PC observations; sampled host time, not guest cycle counts")
    p.add_argument("--query-edges",action="store_true",
                   help="differential native/HLE input-space geometry, busy and ring boundary checks")
    p.add_argument("--eof-tail",action="store_true",
                   help="original producer marks a finite tail; reject stop requests before its last PCM granule")
    p.add_argument("--finite-word-tail",action="store_true",
                   help="with --eof-tail and bounded_final_frame HLE, supply only complete words without borrowing the next frame byte")
    args=p.parse_args()
    if args.startup_prime_count is not None and not (args.preconfigured_format and args.preconfigured_selector):
        p.error("--startup-prime-count requires --preconfigured-format --preconfigured-selector")
    if args.limit is None:
        args.limit=2 if args.startup_prime_count is not None else 3 if args.finite_word_tail else 2 if args.query_edges or args.eof_tail else 3
    if args.finite_word_tail and not args.eof_tail:
        p.error("--finite-word-tail requires --eof-tail")
    if args.eof_tail and args.query_edges:
        p.error("--eof-tail and --query-edges use separate bounded guest callers")
    if args.eof_tail and not (args.preconfigured_format and args.preconfigured_selector):
        p.error("--eof-tail requires --preconfigured-format --preconfigured-selector, like the original player")
    if args.preconfigured_rate and not args.preconfigured_format:
        p.error("--preconfigured-rate requires --preconfigured-format")
    if args.preconfigured_selector and not args.preconfigured_format:
        p.error("--preconfigured-selector requires --preconfigured-format")
    args.output.mkdir(parents=True,exist_ok=False)
    report={"passed":False,"cases":[],"qemu_sha256":hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
            "finite_word_tail":args.finite_word_tail,"startup_prime_count":args.startup_prime_count}
    try:
        cores,_,manifest=load_bundle(args.resident_bundle)
        if args.finite_word_tail:
            assert manifest.get("rom_mp3_hle",{}).get("bounded_final_frame"), \
                "--finite-word-tail requires a bounded_final_frame HLE bundle"
        fast=bool(cores["synthesis"].get("fast_dct32",False))
        report["fast_dct32"]=fast
        frames=fixtures(args.mp3,args.output,args.limit,True,True,0,True,True,True,fast_dct=fast)
        case=check(args.qemu,args.output,args.mp3,frames,args.resident_bundle,args.icount,
                   preconfigured_format=args.preconfigured_format,preconfigured_rate=args.preconfigured_rate,
                   preconfigured_selector=args.preconfigured_selector,profile_pc=args.profile_pc,
                   query_edges=args.query_edges,eof_tail=args.eof_tail,
                   finite_word_tail=args.finite_word_tail,startup_prime_count=args.startup_prime_count)
        report["cases"].append(case)
        hle=bool(manifest.get("rom_mp3_hle"))
        if hle:
            state=case["rom_mp3_hle"]
            assert state["sessions"]==0 and state["frames"]==len(frames) and state["failures"]==0,state
            if args.startup_prime_count is not None:
                assert state["priming_calls"]==args.startup_prime_count-1,state
            if manifest["rom_mp3_hle"].get("hle_pcm_copy"):
                assert state["pcm_copy_calls"]==state["granules"] and state["pcm_copy_failures"]==0,state
        comparison=pcm_artifact(args.mp3,args.output,frames,case,hle=hle)
        report.update(pcm_comparison=comparison,passed=case["passed"] and case["exit_code"]==0 and comparison["within_8_pcm_lsb"])
    except (AssertionError,subprocess.CalledProcessError) as error:
        report["failure"]=str(error)[:3000];print(report["failure"],flush=True)
    finally: (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__=="__main__": raise SystemExit(main())
