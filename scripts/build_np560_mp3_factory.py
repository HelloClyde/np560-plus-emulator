#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Experimental native singleton implementation of the original MP3 ABI.

Unlike the session diagnostic thunks, 4804 allocates its own control object
through the original heap. All later entries locate that pinned object in
guest RAM. No QEMU hook, PRG edit, test owner address, or host decoder.

NEW software layout, NOT recovered mask-ROM fields: 3342/3344 hold a far
root between the original writer 3340 and error 3346. Their codec-private
ownership is an inference with static-reference checks, not proof against
all indirect access. A FFFF segment serializes calls with bounded CRIT.
Do not replace the user's instance before full application validation.

Explicit close releases both heap allocations; reinitialization closes the
old instance. Automatic original stop/exit -> close binding remains absent.
Callback timing is reconstructed (format change and completed granule), not
recovered original internals. Low-rate ACD8/AD92 and EQ remain missing.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct

import build_np560_mp3_allocation as lease
import build_np560_mp3_session as session
from build_np560_mp3_resident import load_bundle, PRG_SHA
from np560_assembler import _DMCUAssembler
from np560_mp3_link import code_span

ROOT, SIZE, SELF_HANDLE, SIGNATURE = 0x3342, 96, 80, 82
FORMAT_CALLBACK, FRAME_CALLBACK, SIGNATURE_VALUE = 84, 88, 0x504d
FIRST_FORMAT_SEEN = 92  # NEW owner field; reset at each decoder reset.
PUBLIC = {0x14804:"init", 0x1485a:"reset", 0x14954:"output",
          0x149be:"free_words", 0x149f8:"step",
          0x146f2:"set_format_callback", 0x146d4:"set_frame_callback"}


def sha(data): return hashlib.sha256(data).hexdigest()


def root_reference_guard(original,resident,cores):
    """Reject newly introduced direct references; not an indirect-access proof."""
    families={0x88,0x89,*range(0x90,0x9a),0xa8,0xa9,*range(0xb0,0xb8)}
    def references(data,base):
        words=struct.unpack(f"<{len(data)//2}H",data)
        return [(base+i*2,op,arg) for i,(op,arg) in enumerate(zip(words,words[1:]))
                if op>>8 in families and ROOT<=arg&0x7fff<ROOT+4]
    prg_refs=references(original,0x30000)
    assert prg_refs==[(0x0ad9fc,0x886c,0x3344),(0x0aea64,0x9648,0x3342)],prg_refs
    # These are sorted Unicode -> GB2312 (both high bits stripped) mapping
    # rows, not accesses by instructions. Check their actual text encoding.
    for _,unicode,value in prg_refs:
        assert int.from_bytes(chr(unicode).encode("gb2312"),"big")-0x8080==value
    from np560_mp3_link import fragments
    tables=[(addr,addr+len(data),name,kind) for name,component in cores.items()
            for kind,addr,data in fragments(component) if kind!="code"]
    raw_refs=references(resident,0)
    table_rows=[{"row":row,"fragment":[name,kind]} for row in raw_refs
                for lo,hi,name,kind in tables if lo<=row[0] and row[0]+4<=hi]
    rom_refs=[row for row in raw_refs if not any(lo<=row[0] and row[0]+4<=hi for lo,hi,_,_ in tables)]
    assert rom_refs==[(0x989b0,0xa8f0,ROOT),(0x989b8,0xa8f0,ROOT+2)],rom_refs
    assert resident[0x98930:0x98934]==struct.pack("<2H",0x6810,0x10)
    # Straight-line reconstructed installer, DS0=10: destinations are
    # physical 08:33xx, NOT 00:33xx. Every intervening instruction checked.
    for index,pos in enumerate(range(0x98934,0x989cc,8)):
        op,_,store,dest=struct.unpack_from("<4H",resident,pos)
        assert (op,store,dest)==(0x68f0,0xa8f0,0x3324+index*2)
    return {"original_data_rows":prg_refs,"native_constant_table_rows":table_rows,
            "resident_other_bank_writes":rom_refs,
            "other_bank":0x10,"unexplained_direct_references":[],
            "all_indirect_accesses_excluded":False,
            "ownership_basis":"inferred codec-private words between writer3340 and error3346; NEW layout"}


def build(address, core):
    a=_DMCUAssembler(address)
    saved=(1,*range(3,15))
    def imm(r,v): a.emit(0x68f0|r,v&65535)
    def mov(d,s): a.emit(0x0800|d<<4|s)
    def cmpi(r,v): a.emit(0x76f0|r,v&65535)
    def call(target): a.emit(0xbd00|target>>16,target&65535)
    def invoke(name): call(core["entries"][name])
    def field(off): mov(1,3);a.emit(0x70f1,off)
    def get(r,off): field(off);a.emit(0x2801|r<<4)
    def put(r,off):
        assert r!=1
        field(off);a.emit(0x0a10|r)
    def native(target,arg):
        for r in range(3,15): a.emit(0x58f0|r)
        a.emit(0x1f10,0x1f11,0x1f00,0x58f0|arg)
        call(target);a.emit(0x50f2,0x1f80,0x1f91,0x1f90)
        for r in reversed(range(3,15)): a.emit(0x380f|r<<4)
    def enter():
        for r in saved: a.emit(0x58f0|r)
        a.emit(0x1f10,0x1f11,0x1f00);mov(11,15)
        a.emit(0x6810,0);imm(1,ROOT);imm(4,0xffff)
        a.emit(0x3f03,0x28c1,0x76fc,0xffff);a.ajmp("busy",1)
        a.emit(0x0a14,0x88fd,ROOT+2)
    def require_owner():
        a.acall("locate");cmpi(2,0);a.ajmp("failed",2)
    def failure_if_needed(): cmpi(2,0);a.ajmp("failed",2)
    def clear_error(): imm(4,0);a.emit(0x3f10,0xa8f4,0x3346)

    a.label("init");enter()
    a.acall("drop");failure_if_needed()
    imm(4,SIZE);native(lease.ALLOC,4);cmpi(0,0);a.ajmp("no_memory",1)
    mov(14,0);native(lease.LOCK,14);mov(12,0);mov(13,1)
    a.acall("geometry");cmpi(2,0);a.ajmp("bad_new_geometry",2)
    mov(5,3);imm(1,SIZE//2);imm(0,0)
    a.label("zero_owner");a.emit(0x1a50,0x5211);a.ajmp("zero_owner",2)
    put(14,SELF_HANDLE);imm(0,SIGNATURE_VALUE);put(0,SIGNATURE)
    for i in range(13): a.emit(0x780b,36+i*2);put(0,session.CONFIG+i*2)
    invoke("create");cmpi(2,0);a.ajmp("create_failed",2)
    # Reconstructed publication of the original priming gate. This is a
    # software DPRAM bit, not hardware forced-ready: it is clear until real
    # PCM has completed, and reset/close invalidate it.
    a.emit(0xff83);clear_error();a.ajmp("return")
    a.label("bad_new_geometry")
    native(lease.FREE,14);native(lease.UNLOCK,14);imm(12,0);imm(13,0)
    imm(2,2);a.ajmp("failed")
    a.label("create_failed")
    # Keep a live lease recoverable if a lower-layer release failed. Otherwise
    # no state should remain after failed initialization.
    mov(10,2);get(0,lease.HANDLE);cmpi(0,0);a.ajmp("create_error_ready",2)
    native(lease.FREE,14);native(lease.UNLOCK,14);imm(12,0);imm(13,0)
    a.label("create_error_ready");mov(2,10);a.ajmp("failed")

    a.label("reset");enter();require_owner();invoke("reset");failure_if_needed()
    imm(0,0);put(0,FIRST_FORMAT_SEEN)
    a.emit(0xff83);clear_error();a.ajmp("return")
    a.label("free_words");enter();require_owner();invoke("free_words")
    failure_if_needed();a.ajmp("return")
    a.label("output");enter();require_owner()
    for off in (42,40,38,36): a.emit(0x780b,off,0x58f0)
    invoke("output");a.emit(0x50f8);failure_if_needed();a.ajmp("return")
    for label,off in (("set_format_callback",FORMAT_CALLBACK),("set_frame_callback",FRAME_CALLBACK)):
        a.label(label);enter();require_owner()
        a.emit(0x786b,36,0x787b,38)
        cmpi(6,255);a.ajmp("invalid",0xa)
        mov(0,7);a.emit(0x74f0,1);a.ajmp("invalid",2)
        put(6,off);put(7,off+2);imm(0,0);imm(2,0);a.ajmp("return")

    a.label("step");enter();require_owner();invoke("player_step")
    cmpi(0,1);a.ajmp("step_no_pcm",2)
    get(0,session.FORMAT_CHANGE);cmpi(0,0);a.ajmp("frame_callback",1)
    get(6,FORMAT_CALLBACK);get(7,FORMAT_CALLBACK+2)
    mov(0,6);a.emit(0x1507);a.ajmp("frame_callback",1)
    # The original 2F:A6BA accepts Hz as well as the setup's selector codes.
    a.emit(0x1f11,0x6811,0xa2,0x88f5,0xa5ce,0x1f91)
    # 1D:3708 / 27:95A0 configure the device BEFORE registering 46F2.
    # The ring's first frame is a new format to the *decoder*, but not
    # necessarily a device format change. Calling 2F:A6BA again runs
    # 08:3292 and invalidates already-filled compressed staging buffers.
    # Suppress only the first notification when the original completion
    # gate and actual configured Hz agree. Later format changes still
    # notify (including equal-Hz channel changes); unconfigured callers
    # still receive their initial callback. Never manufacture ready bits.
    get(0,FIRST_FORMAT_SEEN);cmpi(0,0);a.ajmp("notify_format",2)
    imm(0,1);put(0,FIRST_FORMAT_SEEN)
    a.emit(0x7c8a,0x70a0,0x74f0,1);a.ajmp("notify_format",1)
    a.emit(0x1f11,0x6811,0,0x88f0,0xca60,0x1f91,0x1605)
    a.ajmp("frame_callback",1)
    a.label("notify_format")
    imm(9,1);a.acall("callback")
    a.label("frame_callback")
    get(6,FRAME_CALLBACK);get(7,FRAME_CALLBACK+2)
    mov(0,6);a.emit(0x1507);a.ajmp("frame_done",1)
    imm(9,0);a.acall("callback")
    a.label("frame_done");a.emit(0xef83);imm(0,1);imm(2,0);a.ajmp("return")
    a.label("step_no_pcm")
    cmpi(2,1);a.ajmp("return",1)
    cmpi(2,7);a.ajmp("return",1)
    a.emit(0xff83);a.ajmp("return")

    a.label("close");enter();a.acall("drop");failure_if_needed();a.ajmp("return")
    a.label("drop")
    mov(0,12);a.emit(0x150d);a.ajmp("dropped",1)
    a.acall("locate");cmpi(2,0);a.ajmp("drop_return",2)
    get(14,SELF_HANDLE);invoke("release");cmpi(2,0);a.ajmp("drop_return",2)
    native(lease.FREE,14);native(lease.UNLOCK,14);imm(12,0);imm(13,0);a.emit(0xff83)
    a.label("dropped");imm(0,0);imm(2,0)
    a.label("drop_return");a.emit(0xc600)

    a.label("locate")
    mov(0,12);a.emit(0x150d);a.ajmp("locate_closed",1)
    a.acall("geometry");cmpi(2,0);a.ajmp("locate_return",2)
    get(0,SIGNATURE);cmpi(0,SIGNATURE_VALUE);a.ajmp("locate_invalid",2)
    get(0,SELF_HANDLE);cmpi(0,0);a.ajmp("locate_invalid",1)
    cmpi(0,255);a.ajmp("locate_invalid",0xa)
    imm(2,0);a.ajmp("locate_return")
    a.label("locate_invalid");imm(2,2);a.ajmp("locate_return")
    a.label("locate_closed");imm(2,8)
    a.label("locate_return");a.emit(0xc600)

    a.label("geometry")
    # The measured original arena is [51:4A40,52:3A40); payload follows a
    # six-byte node. Reject unsupported near-bank-straddling control objects.
    cmpi(12,0x51);a.ajmp("segment52",2)
    cmpi(13,0x4a46);a.ajmp("geometry_invalid",5);a.ajmp("address_ready")
    a.label("segment52");cmpi(12,0x52);a.ajmp("geometry_invalid",2)
    cmpi(13,0x3a40-SIZE);a.ajmp("geometry_invalid",0xa)
    a.label("address_ready")
    mov(0,13);a.emit(0x74f0,1);a.ajmp("geometry_invalid",2)
    mov(3,13);a.emit(0x74f3,0x7fff)
    cmpi(3,0x8000-SIZE);a.ajmp("geometry_invalid",0xa)
    mov(5,12);a.emit(0x4c51);mov(0,13);a.emit(0x4d0f,0x1050,0x58f5,0x1f90)
    imm(2,0);a.emit(0xc600)
    a.label("geometry_invalid");imm(2,2);a.emit(0xc600)

    a.label("callback")
    # A normal guest far return-stack call, with optional one-word argument.
    # Preserve the owning context even if an original callback uses scratch DS.
    for r in range(3,15): a.emit(0x58f0|r)
    a.emit(0x1f10,0x1f11,0x1f00)
    cmpi(9,0);a.ajmp("callback_no_arg",1);a.emit(0x58f5)
    a.emit(0x68f4,0);a.fixups.append((len(a.words)-1,"callback_arg_return"))
    a.ajmp("callback_jump")
    a.label("callback_no_arg")
    a.emit(0x68f4,0);a.fixups.append((len(a.words)-1,"callback_return"))
    a.label("callback_jump")
    a.emit(0x58f4);imm(4,address>>16);a.emit(0x58f4,0x58f7,0x58f6,0xc620)
    a.label("callback_arg_return");a.emit(0x50f2)
    a.label("callback_return")
    # Distinct continuations consume the optional argument without depending
    # on any register preservation by the original callee.
    a.emit(0x1f80,0x1f91,0x1f90)
    for r in reversed(range(3,15)): a.emit(0x380f|r<<4)
    a.emit(0xc600)

    a.label("invalid");imm(2,2);a.ajmp("failed")
    a.label("no_memory");imm(2,9)
    a.label("failed");imm(0,0);imm(4,1);a.emit(0x3f10,0xa8f4,0x3346)
    a.label("return")
    # Publish offset before releasing the root lock (segment).
    a.emit(0x3f11,0xa8fd,ROOT+2,0xa8fc,ROOT)
    a.ajmp("epilogue")
    a.label("busy");imm(0,0);imm(2,7)
    a.label("epilogue");a.emit(0x1f80,0x1f91,0x1f90)
    for r in reversed(saved): a.emit(0x380f|r<<4)
    a.emit(0xc620)
    words=a.finish();code=struct.pack(f"<{len(words)}H",*words);code_span(address,code)
    return {"entries":a.labels,"code_address":address,"code":code}


def install(bundle,prg):
    cores,source,manifest=load_bundle(bundle);original=prg.read_bytes()
    assert sha(original)==PRG_SHA
    assert "factory" not in cores,"do not install an adapter twice"
    root_evidence=root_reference_guard(original,source,cores)
    sample=build(0x20000,cores["session"]);size=len(sample["code"])
    choices=[(hi-lo,lo) for lo,hi in manifest["remaining_free_spans"] if hi-lo>=size]
    assert choices,"no checked code hole for MP3 factory adapter"
    _,address=min(choices);factory=build(address,cores["session"])
    image=bytearray(source);changes=[(address,factory["code"])]
    for entry,name in PUBLIC.items():
        target=factory["entries"][name]
        changes.append((entry,struct.pack("<2H",0xad00|target>>16,target&65535)))
    for target,data in changes:
        assert source[target:target+len(data)]==b"\x00\x0f"*(len(data)//2),(hex(target),"not a missing-ROM hole")
        image[target:target+len(data)]=data
    result=copy.deepcopy(manifest)
    result.update(rom_sha256=sha(image),source_bundle_rom_sha256=sha(source),
        original_prg_modified=False,known_factory_entries_unchanged=False,
        experimental_factory_abi=True,factory_player_connected=False,
        automatic_stop_exit_release_connected=False,
        root={"address":ROOT,"bytes":4,"layout":"NEW far pointer; FFFF segment is busy",
              "original_private_layout_recovered":False,"all_indirect_accesses_excluded":False,
              "reference_guard":root_evidence},
        factory={"entries":factory["entries"],"public":PUBLIC,
                 "code_address":address,"bytes":size,"sha256":sha(factory["code"]),
                 "control_object_bytes":SIZE},
        installed_bytes=manifest["installed_bytes"]+sum(len(data) for _,data in changes))
    result["remaining_free_bytes"]-=size
    result["remaining_free_spans"]=[(lo+size if lo==address else lo,hi)
                                    for lo,hi in manifest["remaining_free_spans"] if lo+size!=hi or lo!=address]
    # Keep original components loadable and verify the new code/jump fragments.
    result["components"]["factory"]={"entries":factory["entries"],"fragments":[
        {"kind":"code" if target==address else f"entry-{target:06x}","address":target,
         "bytes":len(data),"sha256":sha(data)} for target,data in changes]}
    return factory,bytes(image),result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ("resident-bundle","firmware","output"): p.add_argument("--"+flag,type=Path,required=True)
    p.add_argument("--experimental-private-layout",action="store_true",required=True,
                   help="acknowledge the inferred codec-private root, not original mask-ROM state")
    args=p.parse_args();factory,image,manifest=install(args.resident_bundle,args.firmware)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/"resident.bin").write_bytes(image)
    (args.output/"factory-code.bin").write_bytes(factory["code"])
    (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"rom_sha256":sha(image),"factory":manifest["factory"]},indent=2))
    return 0


if __name__=="__main__": raise SystemExit(main())
