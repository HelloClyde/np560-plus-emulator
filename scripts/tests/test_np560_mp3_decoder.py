#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Real raw MP3 -> native bank-owned PCM API, no test-orchestrated stages.

Only public reset/decode_frame/next_granule orchestrate codec stages. Every granule's PCM,
overlap, synthesis history and raw input position are checked. Busy/empty
calls must preserve the same results. Bank-zero RAM is poisoned and checked
afterward (except actual CPU stack and the eight-byte mismatch diagnostic).
A final reset must clear all entropy/filter histories and published PCM;
an empty call afterward must preserve the fresh state and input position.
The optional factory-heap path also calls the real PRG allocation lifecycle.
No NAND, original-player bypass or host guest-memory writes.
"""
from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess

import build_np560_mp3_decoder as decoder
from build_np560_mp3_frame import components, RECORDS, SIDE, STRIDE, SIZE as ENTROPY_BYTES
from np560_assembler import _DMCUAssembler
from test_np560_mac import run
from test_np560_dtu import read_sfr
from test_np560_mp3_frame import fixtures, far, context, network_words, FIXTURE_ADDRESS, FIXTURE_END, pcm_artifact

TRACE, RESULT, CAPTURE_POINTER, CAPTURE_ADDRESS = 0x2400, 0x30, 0x34, 0x1C0000
WORK_GUARD, SYN_PTRS = decoder.WORKSPACE_BYTES, (0x8100, 0xA100)


def words32(values):
    return [v>>shift&65535 for v in values for shift in (0,16)]


def prepare(frames,bank,syn_bank=None,syn_ptrs=SYN_PTRS,base=0):
    if syn_bank is None: syn_bank=bank+1
    records,details=[],[]
    overlaps=[[0]*576 for _ in range(2)]
    synth=[{"head":0,"state":[0]*1024} for _ in range(2)]
    current_pcm=[[0]*576 for _ in range(2)]
    for index,f in enumerate(frames):
        nch=f["nch"];ngr=len(f["segments"])//nch
        raw=int(f["side"],2).to_bytes(len(f["side"])//8,"big")+bytes.fromhex(f["main_data_hex"])
        last_context=None
        for gr in range(ngr):
            for ch in range(nch):
                c=f["segments"][gr*nch+ch]
                current_pcm[ch]=c["synthesis"]["pcm"]
                overlaps[ch]=c["hybrid"]["expected"][576:]
                synth[ch]={k:copy.deepcopy(c["synthesis"][k]) for k in ("head","state")}
            if nch==1: current_pcm[1]=[0]*576
            # Calls after the productive one prove pending/empty behavior.
            actions=[("decode_frame" if gr==0 else "next_granule",576,0)]
            actions.append(("decode_frame",0,6) if gr+1<ngr else ("next_granule",0,1))
            for number,(entry,r0,r2) in enumerate(actions):
                productive=number==0
                new_input=productive and gr==0
                header=[0]*4+[int(new_input),int(entry=="next_granule"),int(productive)]
                if new_input:
                    header += [f["lsf"],nch,f["segments"][0]["rate"],max(c["intensity"] for c in f["segments"]),
                               len(bytes.fromhex(f["main_data_hex"])),f["mode_ext"],len(raw)*8]
                input_offset=len(records)+len(header)
                if new_input:
                    last_context=context(raw,input_offset,len(raw)*8,len(raw)*8)
                assert last_context is not None
                expected=[(bank,RESULT,[r0,r2]),(bank,decoder.INPUT,last_context),
                    (bank,decoder.PENDING,[ngr-gr-1,base+decoder.FRAME+RECORDS+(gr+1)*nch*STRIDE,
                        base+decoder.FRAME+SIDE+16+(gr+1)*nch*32,576,0,0,decoder.MAGIC_VALUE]),
                    (bank,WORK_GUARD,[0xcafe])]
                for ch in range(2):
                    expected += [(bank,decoder.PCM[ch],current_pcm[ch]),
                                 (bank,decoder.OVERLAP[ch],words32(overlaps[ch])),
                                 (syn_bank,syn_ptrs[ch]&0x7fff,[synth[ch]["head"]]+words32(synth[ch]["state"])),
                                 (syn_bank,(syn_ptrs[ch]&0x7fff)-2,[0xcafe]),
                                 (syn_bank,(syn_ptrs[ch]&0x7fff)+4098,[0xcafe])]
                encoded=[]
                for b,p,values in expected: encoded += [b,p+(base if b==bank else 0),len(values)]+[v&65535 for v in values]
                encoded += [0,0,0]
                raw_words=network_words(raw) if new_input else []
                expected_offset=input_offset+len(raw_words)
                header[:4]=far(expected_offset+len(encoded))+far(expected_offset)
                records += header+raw_words+encoded
                details.append({"frame":index,"granule":gr,"entry":entry,"expected_return":[r0,r2],
                                "new_input":new_input,"pcm_published":productive,"compared_words":sum(len(v) for _,_,v in expected)})
    # Stop/seek will need real history reset, not just a successful return.
    # Preserve input/header configuration, clear all persistent filter and
    # entropy state, and ensure next_granule cannot publish the old output.
    f=frames[-1]
    header_fields=[f["lsf"],f["nch"],f["segments"][0]["rate"],
                   max(c["intensity"] for c in f["segments"]),len(bytes.fromhex(f["main_data_hex"]))]
    for entry,entry_id,status in (("reset",2,0),("next_granule",1,1)):
        expected=[(bank,RESULT,[0,status]),(bank,decoder.INPUT,last_context),
                  (bank,decoder.MODE_EXT,[f["mode_ext"],syn_bank,*syn_ptrs]),
                  (bank,decoder.PENDING,[0,0,0,0,0,0,decoder.MAGIC_VALUE]),
                  (bank,decoder.FRAME,header_fields+[0]*(ENTROPY_BYTES//2-5)),
                  (bank,WORK_GUARD,[0xcafe])]
        for ch in range(2):
            expected += [(bank,decoder.PCM[ch],[0]*576),(bank,decoder.OVERLAP[ch],[0]*1152),
                         (syn_bank,syn_ptrs[ch]&0x7fff,[0]*2049),
                         (syn_bank,(syn_ptrs[ch]&0x7fff)-2,[0xcafe]),
                         (syn_bank,(syn_ptrs[ch]&0x7fff)+4098,[0xcafe])]
        encoded=[]
        for b,p,values in expected: encoded += [b,p+(base if b==bank else 0),len(values)]+[v&65535 for v in values]
        encoded += [0,0,0]
        expected_offset=len(records)+7
        records += far(expected_offset+len(encoded))+far(expected_offset)+[0,entry_id,0]+encoded
        details.append({"frame":None,"granule":None,"entry":entry,"expected_return":[0,status],
                        "new_input":False,"pcm_published":False,"after_stream":True,
                        "compared_words":sum(len(v) for _,_,v in expected)})
    return records,details


def check(qemu,output,frames,bank,icount,trace=False,factory_heap=False,heap_prefix_bytes=0,base=0,resident_bundle=None):
    if resident_bundle:
        from build_np560_mp3_resident import load_bundle
        cores,resident_image,resident_manifest=load_bundle(resident_bundle)
        core=cores["decoder"]
        assert factory_heap, "resident PCM check must use actual allocated RAM"
    else:
        cores=components(workspace_bank=None);core=decoder.build(cores=cores);cores["decoder"]=core
    program_base=0x030000 if resident_bundle else 0x200000
    capture_address=0x4f0000 if resident_bundle else CAPTURE_ADDRESS
    rom=None;factory_code=[];syn_bank,syn_ptrs=bank+1,SYN_PTRS
    if factory_heap:
        import build_np560_mp3_allocation as lease
        from test_np560_mp3_allocation import firmware,layout,FUNCTIONS,PROGRAM,PRG_SHA
        if resident_bundle:
            allocation=cores["allocation"];rom=resident_image;factory_image=PROGRAM.read_bytes()
            assert hashlib.sha256(factory_image).hexdigest()==PRG_SHA
            factory_code=[(addr,factory_image[addr-0x30000:addr-0x30000+size]) for addr,size in FUNCTIONS]
        else:
            allocation=lease.build();factory_image,rom,factory_code=firmware(allocation)
        heap_descriptor=layout(heap_prefix_bytes);bank,syn_bank,*syn_ptrs=heap_descriptor[4:8]
        base=heap_descriptor[8]
        assert heap_descriptor[0], "test requires room for a real workspace"
        cores["allocation"]=allocation
    assert base%2==0 and 0<=base<=0x8000-decoder.WORKSPACE_BYTES-2
    records,details=prepare(frames,bank,syn_bank,syn_ptrs,base)
    assert FIXTURE_ADDRESS+len(records)*2<=FIXTURE_END
    if factory_heap:
        for address,size in FUNCTIONS:
            source=address if resident_bundle else address+0x1d0000
            assert FIXTURE_ADDRESS+len(records)*2<=source or source+size<=FIXTURE_ADDRESS, (
                "diagnostic fixtures overlap original heap code source; use a shorter prefix",hex(source))
    pcm_bytes=1152*sum(len(f["segments"]) for f in frames)
    assert capture_address+pcm_bytes<=(0x500000 if resident_bundle else 0x1f0000)
    a=_DMCUAssembler(program_base)
    def const(addr,v): a.emit(0x68F0,v&65535,0xA8F0,addr)
    def call(entry): a.emit(0x68F3,base,0xBD00|core["entries"][entry]>>16,core["entries"][entry]&65535)
    a.emit(0x6800,2,0x68FF,0x6000,0x6810,0,0x68F3,0,0x68F1,0x4000,0x68F0,0xcafe)
    a.label("poison_bank0");a.emit(0x1A30,0x5211);a.ajmp("poison_bank0",2)
    for addr in range(TRACE,TRACE+8,2): const(addr,0)
    heap_desc=0x2420
    if factory_heap:
        # Only the isolated caller resets the original heap. The new runtime
        # allocator itself must never reset the heap of a running player.
        a.emit(0xBD30,0x8c1c,0x6810,0)
        if heap_prefix_bytes:
            a.emit(0x68F0,heap_prefix_bytes,0x58F0,0xBD25,0x77da,0x50F2,0x76F0,1)
            a.ajmp("heap_failure",2)
            a.emit(0x6810,0,0xA8F0,heap_desc+lease.DESCRIPTOR_BYTES,
                   0x58F0,0xBD31,0x5300,0x50F2,0x76F0,0x51)
            a.ajmp("heap_failure",2)
            a.emit(0x76F1,0x4a46);a.ajmp("heap_failure",2)
            a.emit(0x6810,0xa2);const(0x4a46,0xbeef);a.emit(0x6810,0)
        for off in range(0,lease.DESCRIPTOR_BYTES,2): const(heap_desc+off,0)
        a.emit(0x68F3,heap_desc,0xBD00|allocation["entries"]["acquire"]>>16,allocation["entries"]["acquire"]&65535,0x76F2,0)
        a.ajmp("heap_failure",2)
        for i,value in enumerate(heap_descriptor):
            a.emit(0x88F0,heap_desc+i*2,0x76F0,value);a.ajmp("heap_failure",2)
        # Consume the actual allocator result, not hardcoded RAM selectors.
        for r,off in ((4,lease.WORK_BANK),(6,lease.SYN_BANK),(8,lease.LEFT),(9,lease.RIGHT)):
            a.emit(0x88F0|r,heap_desc+off)
        a.emit(0x58F4,0x1F90,0x58F6,0x1F91)
    else: a.emit(0x6810,bank,0x6811,syn_bank)
    a.emit(0x68F3,base,0x68F1,decoder.WORKSPACE_BYTES//2,0x68F0,0xa55a)
    a.label("poison_workspace");a.emit(0x1A30,0x5211);a.ajmp("poison_workspace",2)
    const(base+WORK_GUARD,0xcafe)
    for p in syn_ptrs:
        for addr in (p-2,p+4098): const(addr,0xcafe)
    if factory_heap:
        a.emit(0xA8F6,base+decoder.SYN_BANK,0xA8F8,base+decoder.SYN_LEFT,0xA8F9,base+decoder.SYN_RIGHT)
    else:
        for addr,v in ((decoder.SYN_BANK,syn_bank),(decoder.SYN_LEFT,syn_ptrs[0]),(decoder.SYN_RIGHT,syn_ptrs[1])): const(base+addr,v)
    for addr,v in ((CAPTURE_POINTER,capture_address>>15),(CAPTURE_POINTER+2,0x8000)):
        const(base+addr,v)
    call("reset")
    # Fail the same register assertion if reset did not install its state.
    a.emit(0x76F2,0);a.ajmp("reset_ok",1)
    a.emit(0x68F7,0xffff);a.ajmp("end")
    a.label("reset_ok")
    a.emit(0x6811,FIXTURE_ADDRESS>>15,0x68FE,FIXTURE_ADDRESS>>15,0x68F9,0x8000,
           0x68F7,0,0x68F8,0,0x68FA,len(details),0x68FC,0x7777)
    a.label("operation")
    a.emit(0x6810,bank)
    for r in (6,4,13,11): a.acall("get_word");a.emit(0x0800|r<<4)
    a.acall("get_word");a.emit(0x0830)
    a.acall("get_word");a.emit(0x0850)
    a.acall("get_word");a.emit(0x58F0) # whether PCM is newly produced
    a.emit(0x76F3,0);a.ajmp("input_ready",1)
    a.emit(0x68F3,base+decoder.FRAME,0x68F1,5)
    a.label("header")
    a.acall("get_word");a.emit(0x1A30,0x5211);a.ajmp("header",2)
    a.acall("get_word");a.emit(0xA8F0,base+decoder.MODE_EXT)
    a.acall("get_word");a.emit(0xA8F0,base+decoder.INPUT+8)
    a.emit(0xA8FE,base+decoder.INPUT,0xA8F9,base+decoder.INPUT+2)
    const(base+decoder.INPUT+4,0);const(base+decoder.INPUT+6,0)
    a.label("input_ready")
    a.emit(0x76F5,2);a.ajmp("call_reset",1)
    a.emit(0x76F5,0);a.ajmp("call_next",2)
    call("decode_frame");a.ajmp("called")
    a.label("call_next");call("next_granule");a.ajmp("called")
    a.label("call_reset");call("reset")
    a.label("called")
    a.emit(0xA8F0,base+RESULT,0xA8F2,base+RESULT+2,0x380F,0x76F0,0)
    a.ajmp("captured",1)
    # The output recorder sees native buffers, not reference table values.
    a.emit(0x68F3,base+decoder.PCM[0]);a.acall("capture_pcm")
    a.emit(0x88F0,base+decoder.FRAME+2,0x76F0,2);a.ajmp("captured",2)
    a.emit(0x68F3,base+decoder.PCM[1]);a.acall("capture_pcm")
    a.label("captured")
    a.emit(0x089B,0x08ED,0x58FE,0x1F91)
    a.label("range")
    a.acall("get_word");a.emit(0x58F0,0x1F90)
    a.acall("get_word");a.emit(0x0830)
    a.acall("get_word");a.emit(0x0850,0x76F5,0);a.ajmp("operation_done",1)
    a.label("compare")
    a.acall("get_word");a.emit(0x0810,0x3803,0x1601);a.ajmp("same",1)
    a.acall("mismatch")
    a.label("same");a.emit(0x5251);a.ajmp("compare",2);a.ajmp("range")
    a.label("operation_done")
    a.emit(0x0894,0x08E6,0x58FE,0x1F91,0x5081,0x52A1);a.ajmp("operation",2)
    if factory_heap:
        a.emit(0x6810,0,0x68F3,heap_desc,0xBD00|allocation["entries"]["release"]>>16,allocation["entries"]["release"]&65535,0x76F2,0)
        a.ajmp("heap_failure",2)
        for off in range(0,lease.DESCRIPTOR_BYTES,2):
            a.emit(0x88F0,heap_desc+off,0x76F0,0);a.ajmp("heap_failure",2)
            const(heap_desc+off,0xcafe)
        if heap_prefix_bytes:
            a.emit(0x6810,0xa2,0x88F0,0x4a46,0x76F0,0xbeef);a.ajmp("heap_failure",2)
            for r in range(3,15): a.emit(0x58F0|r)
            a.emit(0x1F11)
            for target in (lease.FREE,lease.UNLOCK):
                a.emit(0x6810,0,0x88F0,heap_desc+lease.DESCRIPTOR_BYTES,
                       0x58F0,0xBD00|target>>16,target&65535,0x50F2)
            a.emit(0x1F91)
            for r in reversed(range(3,15)): a.emit(0x380F|r<<4)
            a.emit(0x6810,0);const(heap_desc+lease.DESCRIPTOR_BYTES,0xcafe)
        # The full real allocation must return to the original free list.
        a.emit(0x6810,0xa2)
        for off,value in ((0x4a40,0),(0x4a42,0),(0x4a44,0),
                          *((0x27ea+i*2,0x8000 if i==0 else 0) for i in range(16))):
            a.emit(0x88F0,off,0x76F0,value);a.ajmp("heap_failure",2)
    # Internal SRAM stack is legitimate; every other low word must remain
    # poisoned, including all original MP3 ring/output/state addresses.
    a.emit(0x6810,0,0x68F1,0xcafe)
    for i,(start,end) in enumerate(((0,TRACE),(TRACE+8,0x5b00),(0x6000,0x8000))):
        a.emit(0x68F3,start,0x68F5,(end-start)//2)
        a.label(f"bank0_{i}");a.emit(0x3803,0x1601);a.ajmp(f"bank0_same_{i}",1)
        a.acall("mismatch")
        a.label(f"bank0_same_{i}");a.emit(0x5251);a.ajmp(f"bank0_{i}",2)
    read_sfr(a.words,0x10,2);read_sfr(a.words,0x11,13)
    a.ajmp("end")
    a.label("mismatch")
    a.emit(0x76F7,0);a.ajmp("count_mismatch",2)
    a.emit(0x1F10,0x6810,0,0xA8F8,TRACE,0xA8F3,TRACE+2,0xA8F0,TRACE+4,0xA8F1,TRACE+6,0x1F90)
    a.label("count_mismatch");a.emit(0x5071,0xC600)
    a.label("get_word")
    a.emit(0x2809,0x5092);a.ajmp("word_ready",2)
    a.emit(0x68F9,0x8000,0x50E1,0x58FE,0x1F91)
    a.label("word_ready");a.emit(0xC600)
    a.label("capture_pcm")
    for r in (0,1,2,3,5): a.emit(0x58F0|r)
    a.emit(0x1F11,0x88F2,base+CAPTURE_POINTER,0x58F2,0x1F91,0x88F5,base+CAPTURE_POINTER+2,0x68F1,576)
    a.label("capture_word");a.emit(0x3803,0x1A50,0x76F5,0);a.ajmp("capture_next",2)
    a.emit(0x68F5,0x8000,0x5021,0x58F2,0x1F91)
    a.label("capture_next");a.emit(0x5211);a.ajmp("capture_word",2)
    a.emit(0xA8F2,base+CAPTURE_POINTER,0xA8F5,base+CAPTURE_POINTER+2,0x1F91)
    for r in (5,3,2,1,0): a.emit(0x380F|r<<4)
    a.emit(0xC600)
    if factory_heap:
        a.label("heap_failure");a.emit(0x68F7,0xffff);a.ajmp("end")
    a.label("end")
    program=a.finish();assert len(program)*2+2<0x1000
    payload=bytearray(factory_image[0x1000:]) if factory_heap else bytearray(FIXTURE_ADDRESS-0x201000+len(records)*2)
    if not resident_bundle:
        for c in cores.values():
            for key,addr in (("code","code_address"),("tables","table_address")):
                if key in c:
                    off=c[addr]-0x201000;payload[off:off+len(c[key])]=c[key]
    fixture_off=FIXTURE_ADDRESS-program_base-0x1000
    assert fixture_off+len(records)*2<=len(payload), "fixture exceeds diagnostic program"
    payload[fixture_off:fixture_off+len(records)*2]=struct.pack(f"<{len(records)}H",*records)
    if resident_bundle:
        from np560_mp3_link import fragments
        factory_code += [(address,data) for c in cores.values() for _,address,data in fragments(c)]
        (output/"resident-manifest.json").write_text(json.dumps(resident_manifest,indent=2)+"\n",encoding="utf-8")
    (output/"operations.json").write_text(json.dumps(details,indent=2)+"\n",encoding="utf-8")
    end_bank,end_ptr=far(len(records))
    return run(qemu,output,"banked-decoder",program,{2:0,7:0,8:len(details),9:end_ptr,10:0,12:0x7777,
        13:end_bank,14:end_bank,15:0x6000},rom=rom,tail=(0x1000,payload),expected_data=[0]*4,icount=icount,
        boot_mode="firmware-vma03" if resident_bundle else "firmware",
        timeout=max(180,len(frames)*35),poll_interval=.25,capture_ranges=[("guest-pcm",capture_address,pcm_bytes),
            ("workspace",(bank<<15)+base,decoder.WORKSPACE_BYTES)],
        expected_disassembly="" if trace else None,
        expected_code=factory_code+[(core["code_address"],core["code"])],
        metadata={"frames":len(frames),"workspace_bank":bank,"workspace_offset":base,"workspace_bytes":decoder.WORKSPACE_BYTES,
            "synthesis_bank":syn_bank,"synthesis_pointers":list(syn_ptrs),
            "only_public_decoder_calls":True,"host_history_injections":0,
            "original_heap_acquire_release":factory_heap,
            "original_heap_pinned_neighbour_bytes":heap_prefix_bytes,
            "original_heap_descriptor":heap_descriptor if factory_heap else None,
            "resident_code_and_tables":bool(resident_bundle),
            "diagnostic_program_overwrites":[[program_base,0x1000],[FIXTURE_ADDRESS,len(records)*2]] if resident_bundle else None,
            "diagnostic_pcm_capture_address":capture_address,
            "reset_after_stream_checked":True,
            "factory_player_connected":False,"operations":len(details),"decoder_sha256":hashlib.sha256(core["code"]).hexdigest(),
            "fixture_bytes":len(records)*2,"compared_words":sum(d["compared_words"] for d in details)})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu",type=Path,required=True);parser.add_argument("--mp3",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True);parser.add_argument("--limit",type=int,default=4)
    parser.add_argument("--workspace-bank",type=lambda v:int(v,0),choices=(0x30,0x34),default=0x30)
    parser.add_argument("--icount",type=int)
    parser.add_argument("--trace-asm",action="store_true")
    parser.add_argument("--factory-heap",action="store_true",help="acquire/pin/release PCM workspace through actual PRG heap functions; workspace-bank ignored")
    parser.add_argument("--heap-prefix-bytes",type=lambda v:int(v,0),choices=(0,0x2000,0x4000,0x5000),default=0)
    parser.add_argument("--workspace-offset",type=lambda v:int(v,0),default=0,help="even near base; ignored for --factory-heap")
    parser.add_argument("--resident-bundle",type=Path,help="checked resident image/manifest from build_np560_mp3_resident; requires --factory-heap")
    args=parser.parse_args();assert args.limit>0
    if args.heap_prefix_bytes and not args.factory_heap: parser.error("--heap-prefix-bytes requires --factory-heap")
    if args.resident_bundle and not args.factory_heap: parser.error("--resident-bundle requires --factory-heap")
    args.output.mkdir(parents=True,exist_ok=False)
    frames=fixtures(args.mp3,args.output,args.limit,True,True,0,True,True,True)
    report={"passed":False,"qemu_sha256":hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
            "mp3_sha256":hashlib.sha256(args.mp3.read_bytes()).hexdigest(),"cases":[]}
    try:
        case=check(args.qemu,args.output,frames,args.workspace_bank,args.icount,args.trace_asm,args.factory_heap,args.heap_prefix_bytes,args.workspace_offset,args.resident_bundle)
        report["cases"].append(case)
        comparison=pcm_artifact(args.mp3,args.output,frames,case)
        report.update(pcm_comparison=comparison,passed=case["passed"] and case["exit_code"]==0 and comparison["within_8_pcm_lsb"])
    except (AssertionError,subprocess.CalledProcessError) as exc:
        if isinstance(exc,subprocess.CalledProcessError):
            stderr=exc.stderr.decode(errors="replace") if isinstance(exc.stderr,bytes) else exc.stderr
            detail={"offline_reference_process":exc.cmd,"exit_code":exc.returncode,"stderr":stderr}
            report["failure"]=detail;print(json.dumps(detail),flush=True)
            return 1
        detail=exc.args[0] if exc.args else "assertion failed"
        if isinstance(detail,dict): detail={k:detail[k] for k in ("name","registers","actual_samples","expected_samples","code_phase","first_code_differences") if k in detail}
        report["failure"]=str(detail)[:2500];print(report["failure"],flush=True)
    finally: (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__=="__main__": raise SystemExit(main())
