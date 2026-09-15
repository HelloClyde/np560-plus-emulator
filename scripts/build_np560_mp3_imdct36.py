#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Wide native libmad fast long IMDCT and windows (blocks 0,1,3).

DS0:R3 -> {block_type, input18_Q28, output36_Q23, scratch}. All memory
is owned, aligned, disjoint, below 8000 in DS0. No short-block substitute.
Preserves R1,R3..14, DS/SOCR; R0=36/R2=0 or R0=0/R2=2 for bad block.
Temporaries are signed 48-bit Q28, products 80-bit. Multiply floors >>28;
the source's /2 truncates toward zero. Final window result floors >>5.
This is reconstructed guest software, not original ROM or a host codec.
"""
import ast
from fractions import Fraction
from functools import lru_cache
import hashlib
from pathlib import Path
import re
import struct

from build_np560_mp3_scalefactors import MAD_SHA
from build_np560_mp3_dct32 import emit_multiply_q28
from np560_assembler import _DMCUAssembler
from np560_mp3_link import code_span, near_table
from np560_mp3_workspace import select_workspace

SOURCE=Path(__file__).resolve().parents[1]/"doc/sources/libmad-20260907/layer3.c"
# Standalone fixture uses the already bus-verified NOR code hole at 22:0000.
# 22:515E is an existing executable application overlay, not free test space.
ADDRESS,TABLE_ADDRESS=0x220000,0x22d000


@lru_cache(maxsize=1)
def source_text():
    raw=SOURCE.read_bytes();assert hashlib.sha256(raw).hexdigest()==MAD_SHA
    return raw.decode().replace("\r\n","\n")


def function(name):
    text=source_text()
    match=re.search(r"\bvoid "+name+r"\([^;]+?\)\s*(?:/\*.*?\*/\s*)?\{",text,re.S)
    assert match,name
    end=match.end();depth=1
    while depth:
        depth+=(text[end]=="{")-(text[end]=="}");end+=1
    return text[match.start():end]


def constants(text):
    return [(-1 if sign else 1)*int(value,16)
            for sign,value in re.findall(r"(-?)\s*MAD_F\((0x[0-9a-f]+)\)",text)]


@lru_cache(maxsize=1)
def graph():
    nodes=[]
    def op(kind,*args): nodes.append((kind,*args));return len(nodes)-1
    inp=[op("input",i) for i in range(18)]
    def sdct(x):
        text=function("fastsdct")
        names={name:(-1 if sign else 1)*int(value,16) for name,sign,value in
               re.findall(r"(c\d+)\s*=\s*(-?)MAD_F\((0x[0-9a-f]+)\)",text)}
        assert len(names)==7
        body=re.sub(r"/\*.*?\*/","",text[text.index("  a0 ="):text.rindex("}")],flags=re.S)
        values={};out={}
        def coefficient(node):
            if isinstance(node,ast.Name):return names[node.id]
            assert isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.USub)
            return -coefficient(node.operand)
        def expression(node):
            if isinstance(node,ast.Name): return values[node.id]
            if isinstance(node,ast.Subscript):
                index=node.slice.value if isinstance(node.slice,ast.Index) else node.slice
                assert node.value.id=="x" and isinstance(index,ast.Constant)
                return x[index.value]
            if isinstance(node,ast.Call):
                assert node.func.id=="mad_f_mul" and len(node.args)==2
                return op("mul",expression(node.args[0]),coefficient(node.args[1]))
            assert isinstance(node,ast.BinOp)
            if isinstance(node.op,ast.Mult):
                assert isinstance(node.left,ast.Constant) and node.left.value==2
                value=expression(node.right);return op("add",value,value)
            assert isinstance(node.op,(ast.Add,ast.Sub))
            return op("add" if isinstance(node.op,ast.Add) else "sub",expression(node.left),expression(node.right))
        for statement in body.split(";"):
            if not statement.strip():continue
            lhs,rhs=statement.split("=",1);lhs=re.sub(r"\s+","",lhs)
            value=expression(ast.parse(rhs.strip(),mode="eval").body)
            if lhs.startswith("y["): out[int(lhs[2:-1])]=value
            else: values[lhs]=value
        assert set(out)==set(range(0,18,2))
        return [out[i] for i in range(0,18,2)]
    iv=constants(function("dctIV"));ii=constants(function("sdctII"))
    assert len(iv)==18 and len(ii)==9
    scaled=[op("mul",x,c) for x,c in zip(inp,iv)]
    even=sdct([op("add",scaled[i],scaled[17-i]) for i in range(9)])
    odd=sdct([op("mul",op("sub",scaled[i],scaled[17-i]),ii[i]) for i in range(9)])
    out=[v for pair in zip(even,odd) for v in pair]
    for i in range(3,18,2):out[i]=op("sub",out[i],out[i-2])
    out[0]=op("half",out[0])
    for i in range(1,18):out[i]=op("sub",op("half",out[i]),out[i-1])
    assert sum(n[0]=="mul" for n in nodes)==43
    return nodes,out


def windows():
    text=source_text();tables=[]
    for name,count in (("window_l",36),("window_s",12)):
        start=text.index("mad_fixed_t const "+name+"[")
        values=constants(text[start:text.index("};",start)])
        assert len(values)==count;tables.append(values)
    long,short=tables
    return [long, long[:18]+[1<<28]*6+short[6:]+[0]*6,
            [0]*6+short[:6]+[1<<28]*6+long[18:]]


def output_mapping():
    _,out=graph()
    return ([(out[9+i],1) for i in range(9)]+
            [(out[26-i],-1) for i in range(9,27)]+
            [(out[i-27],-1) for i in range(27,36)])


@lru_cache(maxsize=1)
def range_proof():
    nodes,_=graph();values=[];maximum=Fraction(0)
    for node in nodes:
        kind,*args=node
        if kind=="input":v=([Fraction(int(i==args[0])) for i in range(18)],Fraction(0))
        elif kind in ("add","sub"):
            x,y=[values[i] for i in args];sign=1 if kind=="add" else -1
            v=([a+sign*b for a,b in zip(x[0],y[0])],x[1]+y[1])
        else:
            x=values[args[0]];scale=Fraction(args[1],1<<28) if kind=="mul" else Fraction(1,2)
            v=([a*scale for a in x[0]],x[1]*abs(scale)+1)
        values.append(v);maximum=max(maximum,sum(abs(a) for a in v[0])*(1<<31)+v[1])
    output_bound=Fraction(0)
    for win in windows():
        for (index,_),coefficient in zip(output_mapping(),win):
            vector,error=values[index]
            bound=(sum(abs(a) for a in vector)*(1<<31)+error)*Fraction(coefficient,1<<28)+1
            output_bound=max(output_bound,bound/32+1)
    assert maximum<1<<47 and output_bound<1<<31
    ceil=lambda n:(n.numerator+n.denominator-1)//n.denominator
    return {"input_bits":32,"temporary_bits":48,"product_bits":80,
            "maximum_intermediate_bound":ceil(maximum),"maximum_q23_output_bound":ceil(output_bound),
            "transform_multiplies":43,"window_multiplies_max":36}


def tables():
    return b"".join(struct.pack("<HI",index*6|(0x8000 if sign<0 else 0),coefficient)
                    for win in windows() for (index,sign),coefficient in zip(output_mapping(),win))


def evaluate(block,inputs):
    """Integer graph check only; independent pinned-C reference is separate."""
    assert block in (0,1,3) and len(inputs)==18
    values=[]
    for kind,*args in graph()[0]:
        if kind=="input":v=inputs[args[0]]
        elif kind=="add":v=values[args[0]]+values[args[1]]
        elif kind=="sub":v=values[args[0]]-values[args[1]]
        elif kind=="mul":v=values[args[0]]*args[1]>>28
        else:
            x=values[args[0]];v=x//2 if x>=0 else -((-x)//2)
        assert -(1<<47)<=v<1<<47;values.append(v)
    win=windows()[(0,1,3).index(block)]
    return [((values[index]*sign*coefficient)>>28)>>5
            for (index,sign),coefficient in zip(output_mapping(),win)]


def build(address=ADDRESS,workspace_bank=0,*,table_address=TABLE_ADDRESS):
    nodes,_=graph();proof=range_proof();a=_DMCUAssembler(address)
    def imm(r,v):
        if 0<=v<16:a.emit(0x4800|r<<4|v)
        else:a.emit(0x68f0|r,v&65535)
    def mov(d,s):a.emit(0x0800|d<<4|s)
    def push(r):a.emit(0x58f0|r)
    def pop(r):a.emit(0x380f|r<<4)
    def pointer(base,off):
        mov(3,base)
        if off:a.emit(0x70f3,off)
    def load(index,regs=(0,1,2)):
        pointer(14,index*6)
        for reg in regs[:-1]:a.emit(0x3803|reg<<4)
        a.emit(0x2803|regs[-1]<<4)
    def negate():
        for r in (0,1,2):a.emit(0x77f0|r,65535)
        a.emit(0x70f0,1,0x71f1,0,0x71f2,0)
    saved=(1,*range(3,15));a.label("transform")
    for r in saved:push(r)
    a.emit(0x1f10,0x1f11,0x1f00,*select_workspace(workspace_bank))
    a.emit(0x3803,0x38c3,0x38d3,0x28e3)
    a.emit(0x5603);a.ajmp("invalid",0xa)
    a.emit(0x5602);a.ajmp("invalid",1)
    # Unsigned limb products must not inherit the caller's accumulator
    # saturation mode. Restore the saved full SOCR on both exit paths.
    a.emit(0x1f00,0x385f,0x74f5,0xffef,0x58f5,0x1f80)
    push(0)
    for index,(kind,*args) in enumerate(nodes):
        if kind=="input":
            pointer(12,args[0]*4);a.emit(0x3803,0x2813);mov(2,1);a.emit(0x4b2f)
        else:
            load(args[0])
            if kind in ("add","sub"):
                load(args[1],(4,5,6))
                a.emit(*(0x1004,0x1115,0x1126) if kind=="add" else (0x1204,0x1315,0x1326))
            elif kind=="mul":
                coefficient=args[1]
                if coefficient<0:negate()
                imm(10,abs(coefficient)&65535);imm(11,abs(coefficient)>>16)
                a.acall("multiply_q28")
            else:a.acall("half_toward_zero")
        pointer(14,index*6);a.emit(0x1a30,0x1a31,0x0a32)
    pop(0);a.emit(0x6811,table_address>>15)
    imm(9,0x8000|(table_address&0x7fff))
    a.emit(0x5600);a.ajmp("window_ready",1)
    a.emit(0x70f9,216,0x5601);a.ajmp("window_ready",1)
    a.emit(0x70f9,216)
    a.label("window_ready");imm(8,36)
    a.label("window")
    mov(3,9);a.emit(0x3873,0x38a3,0x38b3);mov(9,3)
    mov(3,7);a.emit(0x74f3,0x7fff,0x103e,0x3803,0x3813,0x2823)
    a.emit(0x76f7,0x8000);a.ajmp("positive_window",5);negate()
    a.label("positive_window")
    push(8);push(9);a.acall("multiply_q28");pop(9);pop(8)
    a.emit(0x4d05);mov(4,1);a.emit(0x4c4b,0x1504,0x4d15,0x4c2b,0x1512)
    mov(3,13);a.emit(0x1a30,0x1a31);mov(13,3)
    a.emit(0x5281);a.ajmp("window",2)
    imm(0,36);imm(2,0);a.ajmp("return")
    a.label("invalid");imm(0,0);imm(2,2)
    a.label("return");a.emit(0x1f80,0x1f91,0x1f90)
    for r in reversed(saved):pop(r)
    a.emit(0xc620)
    a.label("half_toward_zero")
    a.emit(0x76f2,0x8000);a.ajmp("half_shift",5)
    a.emit(0x70f0,1,0x71f1,0,0x71f2,0)
    a.label("half_shift")
    a.emit(0x4d01);mov(4,1);a.emit(0x4c4f,0x1504,0x4d11)
    mov(4,2);a.emit(0x4c4f,0x1514,0x4b21,0xc600)
    emit_multiply_q28(a,imm,mov,push,pop)
    code=struct.pack(f"<{len(a.words)}H",*a.finish());data=tables()
    code_span(address,code);near_table(table_address,data)
    return {"code":code,"code_address":address,"tables":data,"table_address":table_address,
            "entries":a.labels,"work_bytes":len(nodes)*6,"range_proof":proof,"source_sha256":MAD_SHA}


if __name__=="__main__":
    import json
    core=build();print(json.dumps({"code_bytes":len(core["code"]),"work_bytes":core["work_bytes"],
                                  "table_bytes":len(core["tables"]),**range_proof()},indent=2))
