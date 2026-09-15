#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""DMCU port of pinned libmad dct32, with full-width intermediate values.

DS0:R3 -> {input32_Q23, output_bank, output64_Q17, scratch1062bytes}.
All buffers aligned, owned and nonoverlapping; input/scratch/descriptor
are below 8000 in caller DS0, output is 8000..FF00 in supplied DS1.
Produces the complete 64-entry synthesis V chunk, NOT PCM or player ABI.
Preserves R1,R3..14, DS/SOCR. Success R0=64,R2=0; bad geometry R0=0,R2=2.

Reuse libmad's exact 80-multiply factorization and Q28 constants. Every
temporary is signed 48-bit Q23; products are signed 80-bit before >>28.
Floor on each multiply, and Q23 -> Q17 only at output. No input scaling,
clipping or overflow rejection of valid signed int32 inputs. An exact
affine/error bound checks all intermediate expressions at build time.
The restricted expression emitter only accepts this SHA-pinned function;
it is not a general C compiler, a host codec, or recovered factory bytes.
"""
from __future__ import annotations

import ast
from fractions import Fraction
from functools import lru_cache
import hashlib
from pathlib import Path
import re
import struct

from np560_assembler import _DMCUAssembler
from np560_mp3_link import code_span
from np560_mp3_workspace import select_workspace

SOURCE=Path(__file__).resolve().parents[1]/"doc/sources/libmad-20260907/synth.c"
SOURCE_SHA="c7a49ee84744f3d6a7ef2fa5be69bfc3d65056b9748fc58978843df0deafd5f5"
ADDRESS,WORK_BYTES=0x220000,177*6


def input_index(node):
    index=node.slice
    if isinstance(index,ast.Index): index=index.value  # Python 3.8
    assert isinstance(index,ast.Constant) and isinstance(index.value,int)
    assert 0<=index.value<32
    return index.value


@lru_cache(maxsize=1)
def source_function():
    raw=SOURCE.read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_SHA
    text=raw.decode().replace("\r\n","\n")
    start=text.index("void dct32(");end=text.index("\n# undef MUL",start)
    return text[start:end].strip()


@lru_cache(maxsize=1)
def expressions():
    text=source_function()
    constants=text[text.index("# else"):text.index("# endif")]
    coeff={name:int(value,16) for name,value in re.findall(r"define (costab\d+)\s+MAD_F\((0x[0-9a-f]+)\)",constants)}
    assert len(coeff)==31 and all(0<v<1<<28 for v in coeff.values())
    body=text[text.index("  t0   ="):text.rindex("}")]
    body=re.sub(r"/\*.*?\*/","",body,flags=re.S)
    statements=[]
    for statement in body.split(";"):
        if not statement.strip(): continue
        lhs,rhs=statement.split("=",1)
        lhs=re.sub(r"\s+","",lhs)
        assert re.fullmatch(r"t\d+|(?:hi|lo)\[\d+\]\[slot\]",lhs),lhs
        tree=ast.parse(rhs.strip().replace("in[","inp["),mode="eval").body
        statements.append((lhs,tree))
    assert len(statements)==209
    assert {int(lhs[1:]) for lhs,_ in statements if lhs.startswith("t")}==set(range(177))
    return coeff,statements


@lru_cache(maxsize=1)
def range_proof():
    """Exact linear coefficients plus symmetric propagated floor error."""
    coeff,statements=expressions();values={};maximum=Fraction(0);output_max=Fraction(0)
    counts={"multiply":0,"add":0,"subtract":0,"double":0}
    def evaluate(node):
        nonlocal maximum
        if isinstance(node,ast.Name): result=values[node.id]
        elif isinstance(node,ast.Subscript):
            assert isinstance(node.value,ast.Name) and node.value.id=="inp"
            index=input_index(node)
            result=([Fraction(int(i==index)) for i in range(32)],Fraction(0))
        elif isinstance(node,ast.Call):
            assert isinstance(node.func,ast.Name)
            result=evaluate(node.args[0])
            if node.func.id=="MUL":
                assert len(node.args)==2 and isinstance(node.args[1],ast.Name)
                scale=Fraction(coeff[node.args[1].id],1<<28)
                result=([v*scale for v in result[0]],result[1]*scale+1)
                counts["multiply"]+=1
            else: assert node.func.id=="SHIFT" and len(node.args)==1
        elif isinstance(node,ast.BinOp):
            left=evaluate(node.left)
            if isinstance(node.op,ast.Mult):
                assert isinstance(node.right,ast.Constant) and node.right.value==2
                result=([v*2 for v in left[0]],left[1]*2);counts["double"]+=1
            else:
                right=evaluate(node.right);sign=1 if isinstance(node.op,ast.Add) else -1
                assert isinstance(node.op,(ast.Add,ast.Sub))
                result=([x+sign*y for x,y in zip(left[0],right[0])],left[1]+right[1])
                counts["add" if sign==1 else "subtract"]+=1
        else: raise AssertionError(ast.dump(node))
        maximum=max(maximum,sum(abs(v) for v in result[0])*(1<<31)+result[1])
        return result
    for lhs,node in statements:
        value=evaluate(node)
        if lhs.startswith("t"): values[lhs]=value
        else:
            bound=sum(abs(v) for v in value[0])*(1<<31)+value[1]
            output_max=max(output_max,bound/64+1)
    assert maximum<1<<47 and output_max<1<<31
    # The pinned source comment says 119 subtracts; its actual expression
    # body has 129 (80 butterfly differences + 49 doubled-output differences).
    assert counts=={"multiply":80,"add":80,"subtract":129,"double":49},counts
    ceil=lambda x:(x.numerator+x.denominator-1)//x.denominator
    return {"input_bits":32,"temporary_bits":48,"product_bits":80,
            "maximum_intermediate_magnitude_bound":ceil(maximum),
            "maximum_v_q17_magnitude_bound":ceil(output_max),**counts}


def emit_multiply_q28(a, imm, mov, push, pop):
    """Shared native signed-48 times positive-32, exact 80-bit then >>28."""
    a.label("multiply_q28")
    push(12);mov(4,0);mov(8,1);mov(9,2)
    products=(0,1,2,3,12)
    for r in products: imm(r,0)
    for i,x in enumerate((4,8,9)):
        for j,y in enumerate((10,11)):
            a.emit(0xbe3c,x<<8|y)
            a.emit(0x1007|products[i+j]<<4,0x1106|products[i+j+1]<<4)
            for r in products[i+j+2:]: a.emit(0x71f0|r,0)
    a.emit(0x76f9,0x8000);a.ajmp("product_unsigned",5)
    a.emit(0x123a,0x13cb)
    a.label("product_unsigned")
    mov(0,1);a.emit(0x4d0c);mov(4,2);a.emit(0x4c44,0x1504)
    mov(1,2);a.emit(0x4d1c);mov(4,3);a.emit(0x4c44,0x1514)
    mov(2,3);a.emit(0x4d2c);mov(4,12);a.emit(0x4c44,0x1524)
    pop(12);a.emit(0xc600)


def build(address=ADDRESS,workspace_bank=0):
    proof=range_proof();coeff,statements=expressions();a=_DMCUAssembler(address)
    def imm(r,v):
        if 0<=v<16: a.emit(0x4800|r<<4|v)
        else: a.emit(0x68f0|r,v&65535)
    def mov(d,s): a.emit(0x0800|d<<4|s)
    def push(r): a.emit(0x58f0|r)
    def pop(r): a.emit(0x380f|r<<4)
    def ptr(base,off):
        mov(3,base)
        if off: a.emit(0x70f3,off)
    def negate():
        for r in (0,1,2): a.emit(0x77f0|r,65535)
        a.emit(0x70f0,1,0x71f1,0,0x71f2,0)
    def expression(node):
        if isinstance(node,ast.Name):
            assert re.fullmatch(r"t\d+",node.id)
            ptr(14,int(node.id[1:])*6);a.emit(0x3803,0x3813,0x2823)
        elif isinstance(node,ast.Subscript):
            assert node.value.id=="inp"
            ptr(12,input_index(node)*4);a.emit(0x3803,0x2813)
            mov(2,1);a.emit(0x4b2f)  # sign extend int32 to three words
        elif isinstance(node,ast.Call):
            expression(node.args[0])
            if node.func.id=="MUL":
                value=coeff[node.args[1].id];imm(10,value);imm(11,value>>16)
                a.acall("multiply_q28")
            else: assert node.func.id=="SHIFT"
        elif isinstance(node,ast.BinOp):
            expression(node.left)
            if isinstance(node.op,ast.Mult):
                assert node.right.value==2;a.emit(0x1000,0x1111,0x1122)
            else:
                # All right operands in this pinned factorization are leaves.
                # Load into a second 48-bit register triple directly, rather
                # than spilling the left side to the call stack every time.
                right=node.right
                if isinstance(right,ast.Name):
                    assert re.fullmatch(r"t\d+",right.id)
                    ptr(14,int(right.id[1:])*6);a.emit(0x3843,0x3853,0x2863)
                else:
                    assert isinstance(right,ast.Subscript) and right.value.id=="inp"
                    ptr(12,input_index(right)*4);a.emit(0x3843,0x2853)
                    mov(6,5);a.emit(0x4b6f)
                if isinstance(node.op,ast.Add): a.emit(0x1004,0x1115,0x1126)
                else:
                    assert isinstance(node.op,ast.Sub)
                    a.emit(0x1204,0x1315,0x1326)
        else: raise AssertionError(ast.dump(node))
    saved=(1,*range(3,15))
    a.label("dct32")
    for r in saved: push(r)
    a.emit(0x1f10,0x1f11,0x1f00,*select_workspace(workspace_bank))
    a.emit(0x38c3,0x3843,0x38d3,0x28e3)
    # Only geometry is checked here. Alias/lifetime ownership is the caller's
    # contract, as in the other native filter components.
    for r,limit in ((12,0x7f80),(14,0x8000-WORK_BYTES),(4,0x1ff),(13,0xff00)):
        a.emit(0x76f0|r,limit);a.ajmp("invalid",0xa)
    a.emit(0x76fd,0x8000);a.ajmp("invalid",5)
    for r in (12,13,14):
        mov(0,r);a.emit(0x74f0,1);a.ajmp("invalid",2)
    push(4);a.emit(0x1f91,0x1f00,0x385f,0x74f5,0xffef,0x58f5,0x1f80)
    for lhs,node in statements:
        expression(node)
        if lhs.startswith("t"):
            ptr(14,int(lhs[1:])*6);a.emit(0x1a30,0x1a31,0x0a32)
        else:
            kind,index=re.fullmatch(r"(hi|lo)\[(\d+)\]\[slot\]",lhs).groups();index=int(index)
            if kind=="hi": negate();index+=33
            # V33..48 = floor(-C15..0 / 64), not -floor(C / 64).
            # Keep the original V symmetries on quantized rows afterwards.
            a.emit(0x4d06);mov(4,1);a.emit(0x4c4a,0x1504,0x4d16,0x4c2a,0x1512)
            ptr(13,index*4);a.emit(0x1a30,0x0a31)
    # Fill the other 32 entries; R3/R4 are ordinary DS-aware pointers.
    mov(3,13);mov(4,13);a.emit(0x70f4,128);imm(8,16)
    a.label("mirror_negative")
    a.emit(0x3803,0x3813,0x77f0,65535,0x77f1,65535,0x70f0,1,0x71f1,0,
           0x1a40,0x0a41,0x5246,0x5281);a.ajmp("mirror_negative",2)
    ptr(13,64);imm(0,0);a.emit(0x1a30,0x0a30)
    ptr(13,132);mov(4,13);a.emit(0x70f4,252);imm(8,15)
    a.label("mirror_positive")
    a.emit(0x3803,0x3813,0x1a40,0x0a41,0x5246,0x5281);a.ajmp("mirror_positive",2)
    imm(0,64);imm(2,0);a.ajmp("return")
    a.label("invalid");imm(0,0);imm(2,2)
    a.label("return")
    a.emit(0x1f80,0x1f91,0x1f90)
    for r in reversed(saved): pop(r)
    a.emit(0xc620)

    # Signed R2:R1:R0 * positive R11:R10 -> signed 80-bit, then >>28.
    # Six unsigned MULs, exact sign correction in the top 32 bits. ARX
    # clobbers R5, so all original operands and accumulating words avoid it.
    emit_multiply_q28(a,imm,mov,push,pop)
    code=struct.pack(f"<{len(a.words)}H",*a.finish());code_span(address,code)
    return {"code":code,"code_address":address,"entries":a.labels,"work_bytes":WORK_BYTES,
            "range_proof":proof,"source_sha256":SOURCE_SHA,"workspace_bank":workspace_bank}


if __name__=="__main__":
    import json
    core=build()
    print(json.dumps({"code_bytes":len(core["code"]),"scratch_bytes":WORK_BYTES,**range_proof()},indent=2))
