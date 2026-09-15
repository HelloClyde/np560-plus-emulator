#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Place reconstructed native MP3 code/tables in a pinned resident skeleton.

This installs an independently callable core, NOT the original player ABI.
Only aligned 0F00 holes below the VMA03 program are used. Known direct
factory targets and entire known missing audio-entry groups stay reserved.
The scan is conservative, not proof that unknown indirect targets cannot
exist; retain this limitation until the original entry adapter is connected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_np560_mp3_frame import components
from build_np560_mp3_decoder import build as build_decoder
from build_np560_mp3_allocation import build as build_allocation
from build_np560_mp3_ring import build as build_ring
from build_np560_mp3_session import build as build_session
from np560_mp3_link import fragments, validate

ROM_SHA = "a243f8ba64c6f51144be2a198e895fe38e43fe230123280e799eb363ac8553ef"
PRG_SHA = "d555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5"
BEGIN, END = 0x10000, 0x30000
RESERVED = ((0x10000,0x10206), (0x14600,0x14b00), (0x17d80,0x18000),
            (0x1b680,0x1b900), (0x2ac80,0x2ae00))


def sha(data): return hashlib.sha256(data).hexdigest()


def target_guards(original, rom):
    targets = set()
    # Include both PRG and existing reconstructed services. False positive
    # data words cost space, but must not silently allow a factory jump into
    # one of our new functions. Preserve odd raw targets conservatively too.
    for data in (original,rom):
        words = struct.unpack(f"<{len(data)//2}H",data)
        for op,low in zip(words,words[1:]):
            if op in (0xbd01,0xbd02,0xad01,0xad02):
                targets.add(((op&255)<<16)|low)
    guards = list(RESERVED)
    guards += [(max(BEGIN,(t&~1)-32),min(END,(t&~1)+64)) for t in targets]
    return sorted(targets), sorted(guards)


def free_spans(rom,guards):
    spans=[]; start=None
    for address in range(BEGIN,END,2):
        free = rom[address:address+2]==b"\x00\x0f" and not any(lo<=address<hi for lo,hi in guards)
        # Split at DS boundaries; this also satisfies every code CS limit.
        if start is not None and (not free or address%0x8000==0):
            spans.append((start,address));start=None
        if free and start is None: start=address
    if start is not None: spans.append((start,END))
    return spans


def build(rom_path,prg_path,*,fast_dct=False):
    source=rom_path.read_bytes();original=prg_path.read_bytes()
    assert sha(source)==ROM_SHA, "only the reviewed skeleton is supported"
    assert sha(original)==PRG_SHA, "unexpected factory PRG"
    targets,guards=target_guards(original,source)
    spans=free_spans(source,guards);initial_spans=list(spans)
    # Determine exact fragment sizes using the same paged lookup that the
    # final image will execute. Address changes do not change instruction size.
    power_page_entries=256 if fast_dct else 1024
    power_page_count=(8207+power_page_entries-1)//power_page_entries
    template={"requantize":{"power_pages":[0x230000+i*power_page_entries*4 for i in range(power_page_count)],
               "power_page_entries":power_page_entries,
               "power_directory":0x220020,"root_address":0x220000,"geometry_address":0x220100}}
    if fast_dct: template["dct32"]={"address":0x240000}
    sample=components(workspace_bank=None,layout=template,fast_dct=fast_dct)
    sample["decoder"]=build_decoder(cores=sample)
    sample["allocation"]=build_allocation()
    sample["ring"]=build_ring(core=sample["decoder"])
    sample["session"]=build_session(allocation=sample["allocation"],ring=sample["ring"])
    requests=[(len(data),name,kind) for name,core in sample.items() for kind,_,data in fragments(core)]
    # These two filters call the antialias private RETC multiplication helper
    # with ACALL. They MUST share CS, not merely have individually valid spans.
    near_group=("antialias","hybrid","synthesis")
    packing=[row for row in requests if not(row[1] in near_group and row[2]=="code")]
    packing.append((sum(len(sample[n]["code"]) for n in near_group),"near-math-group","code"))
    factory_reserve_size=0
    if fast_dct:
        # This core is intended for the real player. Reserve an actually
        # sized ABI adapter hole in the SAME packing pass, otherwise many
        # small leftovers can fit the core but not its 2200-byte adapter.
        # The bytes remain untouched for build_np560_mp3_factory to install.
        from build_np560_mp3_factory import build as build_factory
        factory_reserve_size=len(build_factory(BEGIN,sample["session"])["code"])
        packing.append((factory_reserve_size,"factory-reserve","code"))
    placed={}
    # Large tables first, best fit within a checked near bank. No runtime
    # mapper, extra ROM region, PRG patch or host table lookup is introduced.
    for size,name,kind in sorted(packing,key=lambda r:(-r[0],r[1],r[2])):
        fits=[(hi-lo,lo,i) for i,(lo,hi) in enumerate(spans) if hi-lo>=size]
        assert fits, ("resident holes cannot fit fragment",name,kind,size)
        _,lo,i=min(fits);hi=spans[i][1];placed[name,kind]=lo
        spans[i:i+1]=[(lo+size,hi)] if lo+size<hi else []
    offset=placed.pop(("near-math-group","code"))
    factory_reserve=None
    if factory_reserve_size:
        reserve_start=placed.pop(("factory-reserve","code"))
        factory_reserve=(reserve_start,reserve_start+factory_reserve_size)
        spans.append(factory_reserve);spans.sort()
    for name in near_group:
        placed[name,"code"]=offset;offset+=len(sample[name]["code"])
    layout={}
    for name,core in sample.items():
        if name in ("decoder","allocation","ring","session"): continue
        opts={"code_address" if name=="entropy" else "address":placed[name,"code"]}
        if name=="requantize":
            opts.update(power_pages=[placed[name,f"power-{i}"] for i in range(power_page_count)],
                power_page_entries=power_page_entries,
                power_directory=placed[name,"power-directory"],root_address=placed[name,"roots"],
                geometry_address=placed[name,"geometry"])
        elif "tables" in core: opts["table_address"]=placed[name,"tables"]
        layout[name]=opts
    cores=components(workspace_bank=None,layout=layout)
    cores["decoder"]=build_decoder(address=placed["decoder","code"],cores=cores)
    cores["allocation"]=build_allocation(address=placed["allocation","code"])
    cores["ring"]=build_ring(address=placed["ring","code"],core=cores["decoder"])
    cores["session"]=build_session(address=placed["session","code"],allocation=cores["allocation"],ring=cores["ring"])
    ranges=validate(cores);image=bytearray(source);items={};written=0
    for name,core in cores.items():
        item={"entries":core["entries"],"fragments":[]}
        for key in ("work_bytes","fast_dct32","source_sha256","range_proof","power_page_entries"):
            if key in core: item[key]=core[key]
        for kind,address,data in fragments(core):
            assert len(data)==next(size for size,n,k in requests if (n,k)==(name,kind))
            assert BEGIN<=address<address+len(data)<=END
            assert source[address:address+len(data)]==b"\x00\x0f"*(len(data)//2)
            assert not any(address<hi and lo<address+len(data) for lo,hi in guards)
            image[address:address+len(data)]=data;written+=len(data)
            item["fragments"].append({"kind":kind,"address":address,"bytes":len(data),"sha256":sha(data)})
        items[name]=item
    cursor=0
    for lo,hi,_ in ranges:
        assert image[cursor:lo]==source[cursor:lo];cursor=hi
    assert image[cursor:]==source[cursor:] and len(image)==len(source)
    for lo,hi in guards: assert image[lo:hi]==source[lo:hi]
    manifest={"source_rom_sha256":sha(source),"original_prg_sha256":sha(original),
        "rom_sha256":sha(image),"rom_bytes":len(image),"installed_bytes":written,
        "components":items,"layout":layout,"guarded_direct_targets":targets,
        "same_cs_near_call_group":list(near_group),
        "reserved_ranges":guards,"initial_free_bytes":sum(hi-lo for lo,hi in initial_spans),
        "remaining_free_bytes":sum(hi-lo for lo,hi in spans),"remaining_free_spans":spans,
        "outside_fragments_unchanged":True,"known_factory_entries_unchanged":True,
        "original_prg_modified":False,"factory_player_connected":False,
        "reconstructed_not_original_rom_bytes":True,"fast_dct32":fast_dct,
        "factory_abi_reserved_span":factory_reserve,
        "unknown_indirect_targets_proven_absent":False,"license":"GPL-2.0-or-later"}
    return cores,bytes(image),manifest


def load_bundle(directory):
    manifest=json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
    image=(directory/"resident.bin").read_bytes()
    assert sha(image)==manifest["rom_sha256"] and len(image)==manifest["rom_bytes"]
    cores={}
    for name,item in manifest["components"].items():
        core={"entries":item["entries"],"table_parts":[]}
        for key in ("work_bytes","fast_dct32","source_sha256","range_proof","power_page_entries"):
            if key in item: core[key]=item[key]
        for part in item["fragments"]:
            kind,address,size=part["kind"],part["address"],part["bytes"]
            data=image[address:address+size]
            assert sha(data)==part["sha256"]
            if kind=="code": core.update(code=data,code_address=address)
            else: core["table_parts"].append({"name":kind,"address":address,"data":data})
        cores[name]=core
    validate(cores)
    return cores,image,manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resident-rom",type=Path,required=True)
    parser.add_argument("--firmware",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--fast-dct32",action="store_true",help="use the wide libmad fast DCT port; explicit experimental build")
    args=parser.parse_args()
    cores,image,manifest=build(args.resident_rom,args.firmware,fast_dct=args.fast_dct32)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/"resident.bin").write_bytes(image)
    for name,core in cores.items():
        for kind,_,data in fragments(core): (args.output/f"{name}-{kind}.bin").write_bytes(data)
    (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({key:manifest[key] for key in ("rom_sha256","installed_bytes","initial_free_bytes","remaining_free_bytes")},indent=2))
    return 0


if __name__=="__main__": raise SystemExit(main())
