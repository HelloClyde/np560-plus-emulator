#!/usr/bin/env python3
"""Exercise the real HLE kernel at all nine MP3 sample rates, mono/stereo.

Generated independent left/right tones and FFmpeg are test inputs/reference,
never replacements for guest audio. Does not prove original player support.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_np560_mp3_hle_codec import library, check


def diagnose_difference(path, output, rate, channels):
    """Compare whole-stream upstream entry and both FFmpeg arithmetic paths."""
    source = Path(__file__).resolve().parent / 'np560_minimp3_direct.c'
    include = source.parents[2] / 'qemu-dmcu/hw/dmcu'
    commands = []
    for mode in ('scalar', 'simd'):
        binary = output / f'direct-{mode}'
        command = ['gcc','-std=c11','-O2','-I',str(include),str(source),'-lm','-o',str(binary)]
        if mode == 'scalar':
            command.insert(1, '-DMINIMP3_NO_SIMD')
        commands.append(command)
        subprocess.run(command,check=True,capture_output=True)
        command = [str(binary.resolve()),str(path),str(output/f'direct-{mode}.s16le')]
        commands.append(command)
        subprocess.run(command,check=True,capture_output=True)
    command = ['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-n',
        '-c:a','mp3','-flags','+bitexact','-flags2','+skip_manual','-i',str(path),
        '-c:a','pcm_s16le','-f','s16le',str(output/'ffmpeg-fixed.s16le')]
    commands.append(command)
    subprocess.run(command,check=True,capture_output=True)
    raw = (output/'actual.s16le').read_bytes()
    actual = struct.unpack(f'<{len(raw)//2}h',raw)
    comparisons = {}
    samples_per_frame = (1152 if rate >= 32000 else 576) * channels
    for name in ('direct-scalar','direct-simd','ffmpeg','ffmpeg-fixed'):
        reference = (output/f'{name}.s16le').read_bytes()
        assert len(reference) == len(raw), (name,len(reference),len(raw))
        delta = [abs(a-b) for a,b in zip(actual,struct.unpack(f'<{len(actual)}h',reference))]
        comparisons[name] = dict(sha256=hashlib.sha256(reference).hexdigest(),
            max_difference=max(delta,default=0), samples_over_8=sum(d>8 for d in delta),
            rms_difference=(sum(d*d for d in delta)/len(delta))**.5,
            frame_maxima=[max(delta[i:i+samples_per_frame]) for i in range(0,len(delta),samples_per_frame)])
    result = dict(commands=commands, comparisons=comparisons,
                  production_core_modified=False, factory_player_verified=False)
    (output/'direct-comparison.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(passed=False, standalone_only=True, cases=[], generation_commands=[])
    try:
        lib = library(args.output)
        for rate in (8000,11025,12000,16000,22050,24000,32000,44100,48000):
            for channels in (1,2):
                label = f'{rate}-{channels}'
                path = args.output / (label + '.mp3')
                signal = '0.25*sin(2*PI*431*t)'
                if channels == 2:
                    signal += '|0.125*sin(2*PI*997*t)'
                command = ['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-n',
                    '-f','lavfi','-i',f'aevalsrc={signal}:s={rate}:d=0.6',
                    '-c:a','libmp3lame','-b:a','64k' if rate < 32000 else '128k',
                    '-write_xing','0',str(path)]
                report['generation_commands'].append(command)
                subprocess.run(command, check=True, capture_output=True)
                try:
                    result = check(lib, path, args.output / label)
                    assert (result['hz'], result['channels']) == (rate, channels), result
                    result['passed'] = True
                except (AssertionError, subprocess.CalledProcessError) as error:
                    # Keep failing inputs and PCM, and finish the matrix so
                    # one tail mismatch does not conceal other formats.
                    result = dict(path=str(path), hz=rate, channels=channels,
                                  passed=False, error=f'{type(error).__name__}: {error}')
                    if (args.output/label/'actual.s16le').exists() and (args.output/label/'ffmpeg.s16le').exists():
                        result['diagnostic'] = diagnose_difference(path,args.output/label,rate,channels)
                    print(json.dumps(result), flush=True)
                result['input_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                report['cases'].append(result)
        report['passed'] = all(case['passed'] for case in report['cases'])
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        if isinstance(error, subprocess.CalledProcessError):
            report['stderr'] = (error.stderr or b'').decode(errors='replace')
        print(report['error'], flush=True)
    finally:
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
