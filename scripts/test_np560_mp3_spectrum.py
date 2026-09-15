#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare native quantized spectra to offline libmad entropy + FFmpeg regions.

Identity requantization in the reference exposes signed quantized integers,
not audio samples. Real MP3 granules are fixtures; no player is installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from build_np560_mp3_huffman import ROOT, build as build_entropy, codebooks, TABLE_SOURCE
from build_np560_mp3_scalefactors import build as build_sf, MAD_SHA
from build_np560_mp3_spectrum import build
from np560_assembler import _DMCUAssembler
from scan_np560_mpeg_tables import array
from test_np560_dtu import read_sfr, write_word
from test_np560_mac import run
from test_np560_mp3_huffman import symbol_bits, MAD_SHA as HUFF_SHA
from test_np560_mp3_scalefactors import source_excerpt, PREVIOUS
from test_np560_mp3_sideinfo import mp3_frames, reference as side_reference

TEMPLATE_SHA = "28f16d27ded3558280edf3b4e7e141a004082630b3df97f37222ee0bf8b60293"
GUARDS = (0x0FFE, 0x1480, 0x1FFE, 0x200A, 0x21FE, 0x224E, 0x227E, 0x22CE, 0x234E)


def reference_binary(output):
    mad = ROOT / "doc/sources/libmad-20260907"
    raw = (mad / "layer3.c").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MAD_SHA
    source = raw.decode().replace("\r\n", "\n")
    start = source.index("# define MASK(cache,")
    end = source.index("# undef MASK1BIT", start)+len("# undef MASK1BIT")
    entropy = source[start:end]
    entropy = entropy.replace("  /* rzero */", "  observed_coded = xrptr-xr;\n"
                              "  observed_stuffing = cachesz+bits_left-fakebits;\n  /* rzero */")
    (output / "libmad_entropy.inc").write_text(entropy, encoding="utf-8")
    (output / "libmad_scalefactors.inc").write_text(source_excerpt(), encoding="utf-8")
    template = (ROOT / "doc/sources/ffmpeg-mpeg-tables-20260907/mpegaudiodec_template-n8.0.c").read_bytes()
    assert hashlib.sha256(template).hexdigest() == TEMPLATE_SHA
    text = template.decode().replace("\r\n", "\n")
    start = text.index("static void init_short_region(")
    stop = text.index("static void compute_band_indexes(", start)
    common = TABLE_SOURCE.read_text()
    marker = common.index("ff_band_size_long[")
    table = common[common.rfind("const uint8_t", 0, marker):common.index("};", marker)+2]
    (output / "ffmpeg_regions.inc").write_text("#include <stdint.h>\n"+table+"\n"+text[start:stop], encoding="utf-8")
    # C99 designated initializers in huffman.c require no global.h macros.
    (output / "global.h").write_text("/* Offline C99 table build; no configuration overrides. */\n", encoding="utf-8")
    assert hashlib.sha256((mad / "huffman.c").read_bytes()).hexdigest() == HUFF_SHA
    binary = output / "spectrum-reference"
    compiled = subprocess.run(["gcc", "-O2", "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wno-error=sign-compare", "-I", str(output), "-I", str(mad),
                    str(ROOT / "scripts/test_np560_mp3_spectrum_reference.c"), str(mad / "huffman.c"),
                    "-o", str(binary)], capture_output=True, text=True)
    (output / "reference-compiler.log").write_text(compiled.stdout+compiled.stderr, encoding="utf-8")
    if compiled.returncode: raise RuntimeError(compiled.stderr)
    return binary


def synthetic():
    books = codebooks()
    widths = array(TABLE_SOURCE.read_text(), "ff_band_size_long")
    result = []
    for rate in range(9):
        for block, mixed in ((0, 0), (1, 0), (2, 0), (2, 8), (3, 0)):
            if block:
                boundary0 = (72 if rate == 8 else 36) if block == 2 else (36 if rate <= 2 else (108 if rate == 8 else 54))
                boundary1 = 576
            else:
                boundary0 = widths[rate*22]
                boundary1 = boundary0+widths[rate*22+1]
            bits, quant = "", []
            for pair in range(64):
                book = 1 if pair*2 < boundary0 else (7 if pair*2 < boundary1 else 16)
                codes, linbits = books[book]
                symbol = list(codes)[pair % len(codes)]
                encoded, values = symbol_bits(book, codes[symbol], symbol, linbits, signs=pair % 4, escape=3)
                bits += encoded
                quant += values[:2]
            count1 = 32+rate % 2
            for symbol in (15, 5, 10):
                encoded, values = symbol_bits(count1, books[count1][0][symbol], symbol, 0, signs=5)
                bits += encoded
                quant += values
            bits += "0"  # too short for a complete extra count1 code/signs
            prefix = (rate+block) % 16
            stream = "1011010011010101"[:prefix]+bits+"11010101010101010"
            stream += "0"*((-len(stream)) % 16)
            ch = [len(bits), 64, 210, 0, mixed | rate % 2, block,
                  1, 7, 16, 0, 0, 0, 0, 0, int(block != 0), 0]
            result.append({"lsf": int(rate >= 3), "rate": rate, "scfsi": 0, "intensity": int(rate % 2 and rate >= 3),
                           "prefix": prefix, "channel": ch, "previous": PREVIOUS,
                           "stream": int(stream, 2).to_bytes(len(stream)//8, "big").hex(),
                           "known_quant": quant+[0]*(576-len(quant)), "kind": "synthetic"})
    return result


def real_cases(path, output):
    frames = mp3_frames(path)
    side_reference(output, frames)
    raw, history, cases = path.read_bytes(), b"", []
    for frame_index, frame in enumerate(frames):
        assert frame["status"] == 0
        offset = frame["file_offset"]
        header = int.from_bytes(raw[offset:offset+4], "big")
        version = (header >> 19) & 3
        rate = ((header >> 10) & 3) + (0 if version == 3 else (3 if version == 2 else 6))
        mdb = frame["fields"][0]
        assert mdb <= len(history)
        payload = bytes.fromhex(frame["main_data_hex"])
        main_data = (history[-mdb:] if mdb else b"")+payload
        history = (history+payload)[-511:]
        pos = 0
        for index in range(frame["fields"][5]*frame["fields"][6]):
            ch = frame["fields"][8+16*index:24+16*index]
            gr, channel_index = divmod(index, frame["nch"])
            assert pos+ch[0] <= len(main_data)*8
            data = main_data[pos//8:(pos+ch[0]+31)//8]
            data += bytes(len(data) % 2)
            # Zero-length Xing granules still need a valid allocated word.
            if not data: data = bytes(2)
            cases.append({"lsf": frame["lsf"], "rate": rate, "scfsi": frame["fields"][2+channel_index] if gr else 0,
                          "intensity": int(frame["lsf"] and channel_index == 1 and (header >> 6 & 3) == 1 and header >> 4 & 1),
                          "prefix": pos % 8, "channel": ch, "previous": [0]*39,
                          "stream": data.hex(), "frame": frame_index, "gr": gr, "ch": channel_index,
                          "kind": "real", "file_offset": offset})
            pos += ch[0]
    return cases


def reference(output, cases):
    binary = reference_binary(output)
    process = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, bufsize=1)
    previous = {}
    try:
        for c in cases:
            key = (c.get("frame"), c.get("ch"))
            if c.get("gr") == 1: c["previous"] = previous[key]
            fields = [c[k] for k in ("lsf", "rate", "scfsi", "intensity", "prefix")]+c["channel"]+c["previous"]
            process.stdin.write(" ".join(map(str, fields))+" "+c["stream"]+"\n")
            process.stdin.flush()
            row = process.stdout.readline()
            if not row: raise RuntimeError(process.stderr.read())
            vals = list(map(int, row.split()))
            assert len(vals) == 659
            status, part2, coded, stuffing, flags = vals[:5]
            assert status == 0, (c.get("frame"), c.get("gr"), status)
            c.update(status=status, part2=part2, coded=coded, stuffing=stuffing, flags=flags,
                     sf=vals[5:44], mask=vals[44:83], quant=vals[83:])
            # libmad's local cache counters can be negative after an
            # abandoned count1 lookahead. They are not a bit cursor.
            # Re-encode the independently decoded integers and verify the
            # exact source bits before calculating leftover stuffing.
            c["reference_cache_remainder"] = stuffing
            encoded = reencode(c)
            bitstream = "".join(f"{b:08b}" for b in bytes.fromhex(c["stream"]))
            begin = c["prefix"]+part2
            assert bitstream[begin:begin+len(encoded)] == encoded
            c["stuffing"] = c["channel"][0]-part2-len(encoded)
            assert c["stuffing"] >= 0
            if "known_quant" in c: assert c["quant"] == c["known_quant"]
            if c.get("gr") == 0: previous[key] = c["sf"]
    finally:
        process.stdin.close()
        try: result = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            result = process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()
    assert result == 0


def reencode(c):
    books = codebooks()
    ch, rate = c["channel"], c["rate"]
    if ch[14]:
        b0 = (72 if rate == 8 else 36) if ch[5] == 2 else (36 if rate <= 2 else (108 if rate == 8 else 54))
        b1 = 576
    else:
        widths = array(TABLE_SOURCE.read_text(), "ff_band_size_long")[rate*22:rate*22+22]
        b0, b1 = sum(widths[:ch[12]+1]), sum(widths[:min(ch[12]+ch[13]+2, 22)])
    encoded = ""
    for index in range(0, ch[1]*2, 2):
        book = ch[6 if index < b0 else (7 if index < b1 else 8)]
        codes, linbits = books[book]
        pair = c["quant"][index:index+2]
        symbol = (min(abs(pair[0]), 15) << 4) | min(abs(pair[1]), 15)
        encoded += codes[symbol]
        for value in pair:
            if abs(value) >= 15 and linbits: encoded += f"{abs(value)-15:0{linbits}b}"
            if value: encoded += str(int(value < 0))
    book = 32+(ch[4] & 1)
    for index in range(ch[1]*2, c["coded"], 4):
        quad = c["quant"][index:index+4]
        assert len(quad) == 4 and all(abs(v) <= 1 for v in quad)
        symbol = sum(abs(v) << (3-i) for i, v in enumerate(quad))
        encoded += books[book][0][symbol]
        encoded += "".join(str(int(v < 0)) for v in quad if v)
    return encoded


def check(qemu, output, name, cases, icount=None):
    cores = (build_entropy(), build_sf(), build())
    records, expected = [], []
    for c in cases:
        raw = bytes.fromhex(c["stream"])
        assert len(raw) % 2 == 0
        start = len(records)
        available = c.get("available", len(raw)*8)
        header = [0, available, c["prefix"], c["lsf"], c["rate"], c["scfsi"], c["intensity"]]+c["channel"]+c["previous"]
        pointer = 0x8000+(start+len(header))*2
        header[0] = pointer+len(raw)
        records += header+[int.from_bytes(raw[i:i+2], "big") for i in range(0, len(raw), 2)]
        consumed = c["prefix"]+c.get("consumed", c["channel"][0])
        loaded = (consumed+15)//16
        cache = 0
        if loaded:
            cache = (int.from_bytes(raw[2*(loaded-1):2*loaded], "big") << (consumed-16*(loaded-1))) & 65535
        state = [0x42, pointer+2*loaded, cache, loaded*16-consumed, available-consumed]
        expected += [c["coded"], c["status"], c["flags"]]+state+c["sf"]+c["mask"]+c["quant"]
        expected += c.get("metrics", [c["part2"], c["channel"][1]*2, c["coded"], c["stuffing"]])+[0xCAFE]*len(GUARDS)
    assert len(records)*2 < 0x8000 and 0x2400+len(expected)*2 < 0x5E00
    a = _DMCUAssembler(0x200000)
    a.emit(0x6800, 2, 0x68FF, 0x6000, 0x6810, 0, 0x6811, 0x42,
           0x68FC, 0x2000, 0x68F9, 0x8000, 0x68FB, 0x4444,
           0x68F7, 0, 0x68F8, len(cases), 0x68FA, 0x2400)
    for address in GUARDS: write_word(a.words, address, 0xCAFE)
    for addr,val in ((0x2050,0x2080),(0x2054,0x1000),(0x2056,0x2040),
                     (0x2082,0x20C0),(0x2086,0x2300),(0x2088,0x2200),(0x208C,0x2280)):
        write_word(a.words,addr,val)
    a.label("next")
    a.emit(0x3869, 0x3809, 0xA8F0, 0x2008, 0x3849)
    for addr in (0x2080,0x2052,0x2084,0x208A): a.emit(0x3809,0xA8F0,addr)
    for addr,count in ((0x20C0,16),(0x2300,39)):
        a.emit(0x68F3,addr,0x68F1,count)
        a.label(f"load_{addr:x}")
        a.emit(0x3809,0x1A30,0x5211)
        a.ajmp(f"load_{addr:x}",2)
    a.emit(0xA8F9,0x2002)
    for addr,val in ((0x2000,0x42),(0x2004,0),(0x2006,0)):
        write_word(a.words,addr,val)
    for addr,count in ((0x2200,39),(0x2280,39),(0x1000,576),(0x2040,4)):
        a.emit(0x68F0,0xA55A,0x68F3,addr,0x68F1,count)
        a.label(f"initialize_{addr:x}")
        a.emit(0x1A30,0x5211)
        a.ajmp(f"initialize_{addr:x}",2)
    a.emit(0x0804,0xBD20,cores[0]["entries"]["read_bits"] & 65535,
           0x68F3,0x2050,0xBD20,cores[2]["entries"]["spectrum"] & 65535,
           0x1AA0,0x1AA2,0x88F0,0x20C8,0x1AA0)
    for addr,count in ((0x2000,5),(0x2200,39),(0x2280,39),(0x1000,576),(0x2040,4)):
        a.emit(0x68F3,addr,0x68F1,count)
        a.label(f"dump_{addr:x}")
        a.emit(0x3803,0x1AA0,0x5211)
        a.ajmp(f"dump_{addr:x}",2)
    for addr in GUARDS: a.emit(0x88F0,addr,0x1AA0)
    a.emit(0x0896,0x5071,0x5281)
    a.ajmp("next",2)
    read_sfr(a.words,0x11,13)
    program=a.finish()
    assert len(program)*2+2 < 0x1000
    payload=bytearray(0xF000+len(records)*2)
    for core in cores:
        for key,addr in (("code","code_address"),("tables","table_address")):
            start=core[addr]-0x201000
            payload[start:start+len(core[key])]=core[key]
    payload[0xF000:]=struct.pack(f"<{len(records)}H",*records)
    (output/f"{name}.vectors.json").write_text(json.dumps(cases,indent=2)+"\n",encoding="utf-8")
    return run(qemu,output,name,program,{7:len(cases),8:0,9:0x8000+len(records)*2,11:0x4444,12:0x2000,13:0x42,15:0x6000},
               tail=(0x1000,payload),icount=icount,
               expected_data=[(n&65535)-(65536 if n&0x8000 else 0) for n in expected],
               metadata={"granules":len(cases),"real_granules":sum(c["kind"]=="real" for c in cases),
                         "spectrum_sha256":hashlib.sha256(cores[2]["code"]).hexdigest(),
                         "pcm_produced":False,"factory_rom_services_replaced":False})


def errors():
    cases=[]
    for kind in ("bad-table4","bad-table32","truncated-pair","sf-budget","bad-frequency",
                 "short-segment","stuffing-only","zero-bit-288-pairs"):
        ch=[1,1,210,0,0,0,1,0,0,0,0,0,0,0,0,0]
        c={"lsf":0,"rate":0,"scfsi":0,"intensity":0,"prefix":0,"channel":ch,"previous":PREVIOUS,
           "stream":"0000","status":0,"coded":0,"part2":0,"stuffing":1,"flags":0,
           "sf":[0]*39,"mask":[0]*39,"quant":[0]*576,"kind":kind}
        if kind.startswith("bad-table"):
            ch[6]=int(kind[len("bad-table"):]);c["status"]=4
        elif kind=="truncated-pair": c["status"]=5
        elif kind=="sf-budget":
            ch[3]=15;c.update(status=3,sf=[0xA55A]*39,mask=[0xA55A]*39,metrics=[0,0,0,1])
        elif kind in ("bad-frequency","short-segment"):
            c.update(status=2 if kind=="bad-frequency" else 1,consumed=0,
                     sf=[0xA55A]*39,mask=[0xA55A]*39,quant=[0xA55A]*576,metrics=[0xA55A]*4)
            if kind=="bad-frequency":c["rate"]=9
            else:c["available"]=0
        elif kind=="stuffing-only":ch[1]=0
        else:
            ch[0]=0;ch[1]=288;ch[6]=0
            c.update(coded=576,stuffing=0)
        cases.append(c)
    return cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--mp3",type=Path)
    parser.add_argument("--first-only",action="store_true")
    parser.add_argument("--errors-only",action="store_true")
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    cases=errors() if args.errors_only else synthetic()
    if not args.errors_only:
        if args.mp3: cases+=real_cases(args.mp3,args.output)
        reference(args.output,cases)
    report={"passed":False,"cases":[],"pcm_produced":False,
            "qemu_sha256":hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
            "libmad_sha256":MAD_SHA,"ffmpeg_template_sha256":TEMPLATE_SHA}
    try:
        selected=cases[:1] if args.first_only else cases
        for start in range(0,len(selected),8):
            report["cases"].append(check(args.qemu,args.output,f"spectrum-{start:04d}",selected[start:start+8]))
        if not args.first_only:
            report["cases"].append(check(args.qemu,args.output,"spectrum-icount5",cases[-8:],icount=5))
        report["passed"]=all(c["passed"] and c["exit_code"]==0 for c in report["cases"])
    except AssertionError as exc:
        detail=exc.args[0] if exc.args else "assertion failed"
        if isinstance(detail,dict):
            detail={"name":detail.get("name"),"registers":detail.get("registers"),
                    "differences":[(i,x,y) for i,(x,y) in enumerate(zip(detail.get("actual_samples",[]),
                                     detail.get("expected_samples",[]))) if x!=y][:20]}
        report["failure"]=str(detail)[:2000]
        print(report["failure"],flush=True)
    finally:
        (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
