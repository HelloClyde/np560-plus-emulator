#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""QEMU joint stereo against adapted offline libmad; no PCM/player."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import subprocess

from build_np560_mp3_huffman import ROOT, TABLE_SOURCE, TABLE_SHA
from build_np560_mp3_scalefactors import MAD_SHA
from build_np560_mp3_requantize import build as build_requant
from build_np560_mp3_stereo import build as build_ms
from build_np560_mp3_intensity import build, WORK_WORDS
from np560_assembler import _DMCUAssembler
from scan_np560_mpeg_tables import array
from test_np560_dtu import read_sfr, write_word
from test_np560_mac import run
from test_np560_mp3_requantize import signed_words, FIXTURE
from test_np560_mp3_stereo import words32


def reference_binary(output):
    raw=(ROOT/'doc/sources/libmad-20260907/layer3.c').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==MAD_SHA
    text=raw.decode().replace('\r\n','\n')
    start=text.index('enum {',text.index('/* --- Layer III'))
    end=text.index('/*\n * scalefactor bit lengths',start)
    snippets=[text[:text.index('# ifdef HAVE_CONFIG_H')],text[start:end]]
    for name in ('root_table','is_table','is_lsf_table'):
        pos=text.index('mad_fixed_t const '+name+'[')
        snippets.append(text[text.rfind('static',0,pos):text.index('};',pos)+2])
    start=text.index('static\nenum mad_error III_stereo(')
    end=text.index('/*\n * NAME:\tIII_aliasreduce()',start)
    body=text[start:end]
    # Deliberate semantic/numeric adaptations, NOT an unmodified-libmad claim.
    for old,new in [('mad_fixed_t const *right_xr = xr[1];','mad_fixed_t const *right_xr = quant_right;'),
                    ('while (l < 36)', 'while (l < mixed_lines)'),
                    ('register mad_fixed_t m, s;', 'register int64_t m, s;'),
                    ('return MAD_ERROR_NONE;', 'memcpy(observed_modes, modes, sizeof(modes));\n  return MAD_ERROR_NONE;')]:
        assert body.count(old)==1,old
        body=body.replace(old,new)
    snippets.append(body)
    (output/'libmad_joint.inc').write_text('\n'.join(snippets),encoding='utf-8')
    raw=TABLE_SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==TABLE_SHA
    text=raw.decode()
    snippets=[]
    for name in ('ff_band_size_long','ff_band_size_short'):
        pos=text.index(name+'[')
        snippets.append(text[text.rfind('const uint8_t',0,pos):text.index('};',pos)+2])
    (output/'ffmpeg_joint_bands.inc').write_text('\n'.join(snippets),encoding='utf-8')
    binary=output/'intensity-reference'
    result=subprocess.run(['gcc','-O2','-std=c99','-Wall','-Wextra','-Werror','-I',str(output),
        str(ROOT/'scripts/test_np560_mp3_intensity_reference.c'),'-o',str(binary)],capture_output=True,text=True)
    (output/'intensity-reference-compiler.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode: raise RuntimeError(result.stderr)
    return binary


def reference(output,cases,binary=None):
    binary=binary or reference_binary(output)
    lines=[]
    for c in cases:
        values=c['input'] if c['mode']=='P' else ([c['rate'],c['ext']]+c['channels'][0]+c['channels'][1]+
            c['sf']+c['mask']+c['quant']+c['left']+c['right'])
        lines.append(c['mode']+' '+' '.join(map(str,values)))
    result=subprocess.run([str(binary)],input='\n'.join(lines)+'\n',capture_output=True,text=True,check=True)
    rows=result.stdout.splitlines()
    assert len(rows)==len(cases)
    for c,row in zip(cases,rows):
        values=list(map(int,row.split()))
        c['status']=values[0]
        if c['mode']=='P':
            assert len(values)==3
            c['expected']=values[1:]
        else:
            assert len(values)==1192
            c['tags'],c['expected']=values[1:40],values[40:]


def geometry(rate,block,mixed):
    text=TABLE_SOURCE.read_text()
    lw,sw=array(text,'ff_band_size_long'),array(text,'ff_band_size_short')
    le=22 if block!=2 else ((8 if rate<3 else 6) if mixed else 0)
    ss=13 if block!=2 else (3 if mixed else 0)
    return [(lw[rate*22+i],3) for i in range(le)]+[(sw[rate*13+i],w) for i in range(ss,13) for w in range(3)]


def vector(rate,block,mixed,ext,pattern=0):
    rng=random.Random(560+rate*100+block*10+mixed+pattern)
    channels=[[0,0,140,rate%2,8 if mixed else 0,block,0,0,0,0,0,0,0,0,int(block!=0),0] for _ in range(2)]
    sf=[(i*5+pattern)%(7 if rate<3 else 31) for i in range(39)]
    mask=[int(i%7==3) if rate>=3 else 0 for i in range(39)]
    if rate<3: sf[5]=7
    else: sf[5],mask[5]=31,1
    quant,right=[0]*576,[0]*576
    bands=geometry(rate,block,mixed)
    p=0
    for i,(width,win) in enumerate(bands):
        active = (i < (len(bands)//3 + (win if win<3 else 0))) if pattern==0 else False
        if pattern==2: active=i==len(bands)-4  # prior top SF is not itself IS
        if pattern==3: active=i==len(bands)-1  # terminal nonzero disables IS below it
        if pattern==4: active=i==0            # all short windows zero in mixed blocks
        if pattern==5: active=(win==1 and i>len(bands)//2 and i<len(bands)-6)
        if active:
            quant[p+width-1]=1
            right[p+width-1]=rng.randrange(1,2**26)
        p+=width
    return {'mode':'J','rate':rate,'ext':ext,'channels':channels,'sf':sf,'mask':mask,'quant':quant,
            'left':[rng.randrange(-2**28,2**28) or 1 for _ in range(576)],'right':right,'pattern':pattern}


def cases():
    values=[-2**31,-65537,-1,0,1,65537,2**31-1]
    pairs=[{'mode':'P','input':[v,i]} for i in range(69) for v in values]
    pairs += [{'mode':'P','input':[1,i]} for i in (69,65535)]
    vectors=[vector(rate,block,mixed,ext,rate%6) for rate in range(9)
             for block,mixed in ((0,0),(2,0),(2,1)) for ext in (1,3)]
    vectors += [vector(rate,block,mixed,ext,pattern) for rate in (0,3)
                for block,mixed in ((0,0),(2,0),(2,1)) for ext in (1,3) for pattern in (1,2,5)]
    for ext in (0,2): vectors.append(vector(0,0,0,ext))
    c=vector(0,0,0,3,4)
    c['right']=[0]*576  # quantized nonzero must still suppress IS despite Q28 underflow
    c['kind']='raw-quant-boundary-after-underflow'
    vectors.append(c)
    for kind in ('rate','ext','left-block','right-block','flags','mismatch-block','mismatch-mixed','sf','mask','pos31','compress'):
        c=vector(3,0,0,3)
        c['kind']='invalid-'+kind
        if kind=='rate': c['rate']=9
        elif kind=='ext': c['ext']=4
        elif kind=='left-block': c['channels'][0][5]=4
        elif kind=='right-block': c['channels'][1][5]=4
        elif kind=='flags': c['channels'][1][4]=16
        elif kind=='mismatch-block': c['channels'][1][5]=1
        elif kind=='mismatch-mixed': c['channels'][1][4]=8
        elif kind=='sf': c['sf'][38]=32
        elif kind=='mask': c['mask'][38]=2
        elif kind=='pos31': c['sf'][5],c['mask'][5]=31,0
        else: c['channels'][1][3]=512
        vectors.append(c)
    return pairs,vectors


def payload(records):
    data=bytearray(FIXTURE-0x201000+len(records)*2)
    for core in (build_requant(),build_ms(),build()):
        for key,addr in (('code','code_address'),('tables','table_address')):
            if key not in core: continue
            off=core[addr]-0x201000
            data[off:off+len(core[key])]=core[key]
    data[FIXTURE-0x201000:]=struct.pack(f'<{len(records)}H',*(n&65535 for n in records))
    return data


def check_pairs(qemu,output,cases,name,icount=None):
    core,records,expected=build(),[],[]
    for i,c in enumerate(cases):
        records+=words32(c['input'][:1])+[c['input'][1],26 if i%2 else 2]
        expected+=words32(c['expected'])+[c['status'],26 if i%2 else 2]
    assert len(records)*2<0x8000 and 0x2400+len(expected)*2<0x5e00
    a=_DMCUAssembler(0x200000)
    a.emit(0x6800,2,0x68FF,0x6000,0x6810,0,0x6811,FIXTURE>>15,0x68F9,0x8000,
           0x68FC,len(cases),0x68F8,0x2400,0x68FB,0x4444,0x68FD,0x5555,0x68FE,0x6666)
    a.label('pair')
    a.emit(0x3809,0x3819,0x3839,0x3859,0x58F5,0x1F80,0xBD20,core['entries']['pair']&65535,
           0x0858,0x1A50,0x1A51,0x1A53,0x1A54,0x1A52)
    read_sfr(a.words,0,6)
    a.emit(0x1A56,0x0885,0x52C1)
    a.ajmp('pair',2)
    read_sfr(a.words,0x11,7)
    return run(qemu,output,name,a.finish(),{7:FIXTURE>>15,8:0x2400+len(expected)*2,9:0x8000+len(records)*2,
        11:0x4444,12:0,13:0x5555,14:0x6666,15:0x6000},tail=(0x1000,payload(records)),
        expected_data=signed_words(expected),icount=icount,timeout=60,poll_interval=.25,
        metadata={'pairs':len(cases),'pcm_produced':False,'code_sha256':hashlib.sha256(core['code']).hexdigest()})


def check_vectors(qemu,output,cases,name,icount=None):
    core,records,expected=build(),[],[]
    guards=(0x00fe,0x1300,0x13fe,0x1880,0x207e,0x20c0,0x20fe,0x214e,0x217e,0x21ce,0x21fe,0x2258,0x204e,0x2064)
    for c in cases:
        records += [c['rate'],c['ext']]+c['channels'][0]+c['channels'][1]+c['sf']+c['mask']+c['quant']+words32(c['left']+c['right'])
        expected += [576 if not c['status'] else 0,c['status']]+c['tags']+words32(c['expected'])+c['sf']+c['mask']+[0xcafe]*len(guards)
    assert len(records)*2<0x8000 and 0x2400+len(expected)*2<0x4ffe
    a=_DMCUAssembler(0x200000)
    a.emit(0x6800,26,0x68FF,0x6000,0x6810,0,0x6811,FIXTURE>>15,
           0x68F9,0x8000,0x68F6,0x2400,0x68F7,0,0x68F8,len(cases),0x68FB,0x4444)
    for addr in guards: write_word(a.words,addr,0xcafe)
    for i,v in enumerate((0,0,0x2080,0x20a0,0x2100,0x2180,0x1400,0x0100,0x0a00,0x2200)):
        write_word(a.words,0x2050+2*i,v)
    a.label('vector')
    for addr,count in ((0x2050,2),(0x2080,32),(0x2100,39),(0x2180,39),(0x1400,576),(0x0100,2304)):
        a.emit(0x68F3,addr,0x68F4,count)
        a.label(f'input_{addr:x}')
        a.emit(0x3809,0x1A30,0x5241)
        a.ajmp(f'input_{addr:x}',2)
    a.emit(0x68F3,0x2200,0x68F4,WORK_WORDS,0x68F0,0xa55a)
    a.label('clear')
    a.emit(0x1A30,0x5241)
    a.ajmp('clear',2)
    a.emit(0x68F3,0x2050,0xBD20,core['entries']['joint']&65535,0x1A60,0x1A62)
    for addr,count in ((0x2208,39),(0x0100,2304),(0x2100,39),(0x2180,39)):
        a.emit(0x68F3,addr,0x68F4,count)
        a.label(f'dump_{addr:x}')
        a.emit(0x3803,0x1A60,0x5241)
        a.ajmp(f'dump_{addr:x}',2)
    for addr in guards: a.emit(0x88F0,addr,0x1A60)
    a.emit(0x5071,0x5281)
    a.ajmp('vector',2)
    read_sfr(a.words,0,12)
    read_sfr(a.words,0x11,5)
    (output/f'{name}.vectors.json').write_text(json.dumps(cases)+'\n',encoding='utf-8')
    return run(qemu,output,name,a.finish(),{5:FIXTURE>>15,6:0x2400+len(expected)*2,7:len(cases),8:0,
        9:0x8000+len(records)*2,11:0x4444,12:26,15:0x6000},tail=(0x1000,payload(records)),
        expected_data=signed_words(expected),icount=icount,timeout=60,poll_interval=.25,
        metadata={'joint_granules':len(cases),'pcm_produced':False,'code_sha256':hashlib.sha256(core['code']).hexdigest()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--first-only',action='store_true')
    parser.add_argument('--errors-only',action='store_true')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    pairs,vectors=cases()
    if args.errors_only:
        pairs=[]
        vectors=[c for c in vectors if c.get('kind','').startswith('invalid-')]
    if args.first_only:
        pairs=pairs[::7]+pairs[-2:]
        vectors=[vector(0,0,0,3,0),vector(3,2,1,3,5)]
    reference(args.output,pairs+vectors)
    if not args.first_only:
        c=vector(0,0,0,3,0)
        c['left'][0]=c['right'][0]=2**31-1
        c.update(status=3,expected=c['left']+c['right'],tags=[1]+[0]*38,kind='first-ms-coefficient-overflow')
        vectors.append(c)
    maximum=0.0
    for c in pairs:
        if c['status']: continue
        v,i=c['input']
        if i<7:
            ratio=math.tan(i*math.pi/12) if i<6 else 0
            kl,kr=(ratio/(1+ratio),1/(1+ratio)) if i<6 else (1,0)
        else:
            scale,pos=divmod(i-7,31)
            opposite=2**(-((pos+1)//2)*(1+scale)/4)
            kl,kr=(opposite,1) if pos%2 else (1,opposite)
        delta=max(abs(c['expected'][0]-v*kl),abs(c['expected'][1]-v*kr))
        assert delta<5,(c,delta)
        maximum=max(maximum,delta)
    report={'passed':False,'cases':[],'pcm_produced':False,'formula_max_q28_lsb_error':maximum,
            'qemu_sha256':hashlib.sha256(args.qemu.read_bytes()).hexdigest()}
    try:
        if pairs: report['cases'].append(check_pairs(args.qemu,args.output,pairs,'pairs'))
        for i in range(0,len(vectors),2):
            report['cases'].append(check_vectors(args.qemu,args.output,vectors[i:i+2],f'joint-{i:03d}'))
        if not args.first_only:
            if pairs: report['cases'].append(check_pairs(args.qemu,args.output,pairs[-128:],'pairs-icount5',5))
            report['cases'].append(check_vectors(args.qemu,args.output,vectors[-2:] if args.errors_only else vectors[40:42],'joint-icount5',5))
        report['passed']=all(c['passed'] and c['exit_code']==0 for c in report['cases'])
    except AssertionError as exc:
        detail=exc.args[0] if exc.args else 'assertion failed'
        if isinstance(detail,dict):
            detail={'name':detail.get('name'),'registers':detail.get('registers'),
                'differences':[(i,x,y) for i,(x,y) in enumerate(zip(detail.get('actual_samples',[]),detail.get('expected_samples',[]))) if x!=y][:20]}
        report['failure']=str(detail)[:2500]
        print(report['failure'],flush=True)
    finally:
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
