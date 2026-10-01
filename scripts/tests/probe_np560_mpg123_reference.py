#!/usr/bin/env python3
"""Independent installed libmpg123 reference; never linked into the emulator.

ABI: https://www.mpg123.de/api/group__mpg123__input.shtml and setup/error docs.
No resampling, gain changes, manual delay trimming, or tolerance relaxation.
"""
import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import struct
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--reference',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if sys.byteorder != 'little':
        parser.error('this PCM16 evidence probe requires a little-endian host')
    args.output.mkdir(parents=True,exist_ok=False)
    lib=c.CDLL(str(args.library))
    lib.mpg123_new.argtypes=[c.c_char_p,c.POINTER(c.c_int)]
    lib.mpg123_new.restype=c.c_void_p
    lib.mpg123_delete.argtypes=[c.c_void_p]
    lib.mpg123_delete.restype=None
    lib.mpg123_param.argtypes=[c.c_void_p,c.c_int,c.c_long,c.c_double]
    lib.mpg123_open.argtypes=[c.c_void_p,c.c_char_p]
    lib.mpg123_getformat.argtypes=[c.c_void_p,c.POINTER(c.c_long),c.POINTER(c.c_int),c.POINTER(c.c_int)]
    lib.mpg123_read.argtypes=[c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)]
    assert lib.mpg123_init()==0
    error=c.c_int()
    handle=lib.mpg123_new(None,c.byref(error))
    assert handle,error.value
    pcm=bytearray()
    try:
        # MPG123_REMOVE_FLAGS=13, MPG123_GAPLESS=0x40: compare full decoded
        # frame output, including startup/flush, as for the other references.
        assert lib.mpg123_param(handle,13,0x40,0.0)==0
        assert lib.mpg123_open(handle,str(args.input).encode())==0
        rate,channels,encoding=c.c_long(),c.c_int(),c.c_int()
        assert lib.mpg123_getformat(handle,c.byref(rate),c.byref(channels),c.byref(encoding))==0
        assert encoding.value==0xd0, ('expected signed native PCM16',encoding.value)
        buffer=c.create_string_buffer(65536)
        for _ in range(10000):
            done=c.c_size_t()
            status=lib.mpg123_read(handle,buffer,len(buffer),c.byref(done))
            pcm.extend(buffer.raw[:done.value])
            if status==-12: break
            assert status==0, status
        else: raise AssertionError('bounded reference decode did not reach EOF')
    finally:
        lib.mpg123_delete(handle)
        lib.mpg123_exit()
    raw=bytes(pcm)
    (args.output/'mpg123.s16le').write_bytes(raw)
    observed=struct.unpack(f'<{len(raw)//2}h',raw)
    comparisons=[]
    for path in args.reference:
        data=path.read_bytes()
        assert len(data)==len(raw),(path,len(data),len(raw))
        delta=[abs(a-b) for a,b in zip(observed,struct.unpack(f'<{len(data)//2}h',data))]
        comparisons.append(dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),
            max_difference=max(delta),samples_over_8=sum(d>8 for d in delta)))
    report=dict(library=str(args.library.resolve()),library_sha256=hashlib.sha256(args.library.read_bytes()).hexdigest(),
        input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),pcm_sha256=hashlib.sha256(raw).hexdigest(),
        samples=len(observed),rate=rate.value,channels=channels.value,encoding=encoding.value,
        comparisons=comparisons,gapless_disabled=True,production_decoder_changed=False)
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':
    main()
