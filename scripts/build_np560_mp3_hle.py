#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Opt-in 01/02 MP3 HLE gates in an existing native factory ROM bundle.

Keep PRG, original ABI adapter, ring, heap and output transport. Only the
NEW native decoder's three public entries become jumps to registered HLE
gates. Add explicit host release before freeing the guest session lease.
Default/legacy rom-hle is never enabled. No user instance is changed.
Optional version 2 also replaces the reconstructed public 01:49BE query
with an atomic HLE calculation on the same explicit software layouts.
It does not consume input or substitute file reads/ready/device requests.
Opt-in version 3 replaces the reconstructed ring too: completed input is
reclaimed after the public query calculates conservative writable capacity.
Original application, producer, EOF flags and peripheral transport stay intact.
Opt-in version 4 also replaces our reconstructed session's PCM software copy.
Both channels are copied before the unchanged native PHASE/READY publication;
actual device requests still transport individual samples through DTU/DAC.
Opt-in version 5 accepts a short final frame only at original producer EOF
and only when all audio bits are available in actual input plus real history.
It consumes actual bytes, never fills compressed data or changes EOF flags.
Opt-in version 6 keeps first-frame PCM until configured startup priming
finishes; the original application still owns ready and device startup.
Optional arena release supplies a ROM trampoline around the original heap
initializer. Its separate machine option selects the executable code alias;
the shipped PRG and guest data view remain unchanged.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct

from build_np560_mp3_resident import load_bundle
from build_np560_mp3_factory import build as build_factory
from build_np560_mp3_session import build as build_session
from build_np560_mp3_ring import build as build_ring
from build_np560_mp3_allocation import build as build_allocation
from np560_assembler import _DMCUAssembler


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(bundle, *, hle_free_words=False, deferred_input_retirement=False,hle_pcm_copy=False,
          final_frame=False,priming=False,arena_release=False,compact_workspace=False,
          audio_mode_parameters=False, audio_mode_dsp=False):
    assert not deferred_input_retirement or hle_free_words
    assert not hle_pcm_copy or deferred_input_retirement
    assert not final_frame or hle_pcm_copy
    assert not priming or final_frame
    assert not compact_workspace or priming, "compact workspace requires version 6 HLE"
    assert not audio_mode_parameters or priming, 'audio mode parameters require priming'
    assert not audio_mode_dsp or audio_mode_parameters, 'DSP requires mode parameters'
    cores, original, old = load_bundle(bundle)
    assert old.get("experimental_factory_abi") and not old.get("rom_mp3_hle")
    manifest = copy.deepcopy(old)
    image = bytearray(original)
    spans = [tuple(p) for p in old["remaining_free_spans"]]
    changes = []

    def place(size):
        candidates = [(hi-lo, lo, i) for i, (lo, hi) in enumerate(spans)
                      if hi-lo >= size and lo >> 16 == (lo+size-1) >> 16]
        assert candidates, ("no reviewed ROM hole", size)
        _, address, index = min(candidates)
        lo, hi = spans[index]
        spans[index:index+1] = [(lo+size, hi)] if lo+size < hi else []
        assert 0x10000 <= address < address+size <= 0x30000
        assert original[address:address+size] == b"\x00\x0f"*(size//2)
        return address

    def write(address, data, reason):
        assert len(data) % 2 == 0 and 0x10000 <= address < address+len(data) <= 0x30000
        changes.append(dict(address=address, bytes=len(data), reason=reason,
            previous_sha256=sha(image[address:address+len(data)]), sha256=sha(data)))
        image[address:address+len(data)] = data

    def component(address, data, entries):
        return dict(entries=entries, fragments=[dict(kind="code", address=address,
                    bytes=len(data), sha256=sha(data))])

    version = 6 if priming else 5 if final_frame else 4 if hle_pcm_copy else 3 if deferred_input_retirement else 2 if hle_free_words else 1
    if audio_mode_parameters:
        version = 7
    if audio_mode_dsp:
        version = 8
    names = ("reset", "decode_frame", "next_granule", "release")
    if hle_free_words:
        names += ("free_words",)
    if hle_pcm_copy:
        names += ("copy_pcm",)
    if audio_mode_parameters:
        names += ('mode_load', 'mode_enable', 'mode_disable')
    gate_bytes = len(names)*16
    gate = place(gate_bytes)
    targets = {name: gate+16*i for i, name in enumerate(names)}
    gates = b"".join(struct.pack("<8H", 0x0f00, 0xc620, 0x504d, 0x484c, version, i, 0, 0)
                     for i in range(len(names)))
    write(gate, gates, f"explicit version-{version} MP3 HLE service markers")
    manifest["components"]["mp3-hle"] = component(gate, gates, targets)
    if audio_mode_parameters:
        for address, name in ((0x14674,'mode_load'),(0x146cc,'mode_enable'),
                              (0x146d0,'mode_disable')):
            assert original[address:address+4] == bytes.fromhex('20c6000f'), 'not the reviewed placeholder'
            target = targets[name]
            write(address, struct.pack('<2H',0xad00 | target >> 16,target & 65535),
                  'experimental audio-mode ABI with assumed EQ DSP' if audio_mode_dsp
                  else 'experimental audio-mode parameter ABI only; no DSP')
    for name in names[:3]:
        address = cores["decoder"]["entries"][name]
        write(address, struct.pack("<2H", 0xad00 | targets[name] >> 16, targets[name] & 65535),
              "replace reconstructed native decoder entry: " + name)
    part = manifest["components"]["decoder"]["fragments"][0]
    part["sha256"] = sha(image[part["address"]:part["address"]+part["bytes"]])

    ring = copy.deepcopy(cores["ring"])
    ring_bytes = 0
    if deferred_input_retirement:
        sample = build_ring(core=cores["decoder"],deferred_input_retirement=True,final_frame=final_frame)
        address = place(len(sample["code"]))
        ring = build_ring(address=address,core=cores["decoder"],deferred_input_retirement=True,final_frame=final_frame)
        write(address,ring["code"],"retain compressed frame through PCM handoff; query then reclaims input")
        ring_bytes = len(ring["code"])
        manifest["components"]["retired-eager-ring"] = manifest["components"]["ring"]
        manifest["components"]["ring"] = component(address,ring["code"],ring["entries"])
    ring["entries"]["release"] = targets["release"]
    manifest["components"]["ring"]["entries"]["release"] = targets["release"]
    allocation_bytes = 0
    if compact_workspace:
        sample = build_allocation(reserve_synthesis=False)
        address = place(len(sample["code"]))
        allocation = build_allocation(address=address,reserve_synthesis=False)
        write(address,allocation["code"],"HLE workspace lease without unused native synthesis history")
        allocation_bytes = len(allocation["code"])
        manifest["components"]["retired-native-allocation"] = manifest["components"]["allocation"]
        manifest["components"]["allocation"] = component(address,allocation["code"],allocation["entries"])
        cores["allocation"] = allocation
    sample = build_session(allocation=cores["allocation"], ring=ring,pcm_copy=targets.get("copy_pcm"),priming=priming)
    address = place(len(sample["code"]))
    session = build_session(address=address, allocation=cores["allocation"], ring=ring,
                            pcm_copy=targets.get("copy_pcm"),priming=priming)
    write(address, session["code"], "session with HLE release before original heap free")
    # Keep retired bytes identified and checked, but no ABI call targets them.
    manifest["components"]["retired-native-session"] = manifest["components"]["session"]
    manifest["components"]["session"] = component(address, session["code"], session["entries"])
    # Preserve legacy bundle layout when rebuilding it. New channel-state
    # publication requires first regenerating the native factory bundle.
    factory = build_factory(old["factory"]["code_address"], session,
        channel_publication="channel_published" in old["components"]["factory"]["entries"])
    assert len(factory["code"]) == old["factory"]["bytes"]
    assert factory["entries"] == old["components"]["factory"]["entries"]
    write(factory["code_address"], factory["code"], "existing ABI dispatches the release-aware session")
    manifest["factory"]["sha256"] = sha(factory["code"])
    for part in manifest["components"]["factory"]["fragments"]:
        if part["kind"] == "code":
            part["sha256"] = sha(factory["code"])
    if hle_free_words:
        target = targets["free_words"]
        data = struct.pack("<2H", 0xad00 | target >> 16, target & 65535)
        write(0x149be, data, "missing public input-space query uses HLE" +
              ("; reclaim completed input after calculating safe capacity" if deferred_input_retirement else "; no input consumption"))
        part = next(p for p in manifest["components"]["factory"]["fragments"]
                    if p["address"] == 0x149be)
        assert part["bytes"] == len(data)
        part["sha256"] = sha(data)
    arena_bytes = 0
    if arena_release:
        from build_np560_mp3_resident import PRG_SHA
        prg=(Path(__file__).resolve().parents[1]/'NP560+V3.80版系统升级程序'/'NP560.PRG').read_bytes()
        assert sha(prg)==PRG_SHA
        body=prg[0x4d8c1c-0x200000:0x4d8d12-0x200000]
        assert len(body)==0xf6 and body[:4]==struct.pack('<2H',0x2e03,0x58f0)
        def wrapper(at):
            a=_DMCUAssembler(at)
            a.emit(0x58f0,0x58f2)
            close=factory['entries']['close']
            a.emit(0xbd00|close>>16,close&65535,0x76f2,0)
            a.ajmp('failed',2)
            a.emit(0x382f,0x380f,0x2e03,0x58f0,0xad30,0x8c20)
            a.label('failed');a.ajmp('failed')
            words=a.finish();return struct.pack('<%dH'%len(words),*words)
        at=place(len(wrapper(0x10000)));code=wrapper(at)
        write(at,code,'release reconstructed MP3 owner before application arena invalidation')
        copied=struct.pack('<2H',0xad00|at>>16,at&65535)+body[4:]
        source=place(len(copied));write(source,copied,'original arena initializer with release trampoline')
        manifest['components']['mp3-arena-release']=component(at,code,{'entry':at})
        manifest['components']['mp3-arena-release']['fragments'].append(
            dict(kind='allocator-image',address=source,bytes=len(copied),sha256=sha(copied)))
        manifest['arena_release']={'wrapper':at,'allocator_image':source,
            'original_allocator_sha256':sha(body),'runtime_verified':False}
        arena_bytes=len(code)+len(copied)
    # Check every byte outside the enumerated changes stayed untouched.
    cursor = 0
    for change in sorted(changes, key=lambda c: c["address"]):
        address, size = change["address"], change["bytes"]
        assert cursor <= address and image[cursor:address] == original[cursor:address]
        cursor = address+size
    assert image[cursor:] == original[cursor:]
    manifest.update(rom_sha256=sha(image), source_bundle_rom_sha256=sha(original),
        remaining_free_spans=spans, remaining_free_bytes=sum(hi-lo for lo, hi in spans),
        installed_bytes=old["installed_bytes"]+gate_bytes+len(session["code"])+ring_bytes+arena_bytes+allocation_bytes,
        rom_mp3_hle=dict(version=version, base=gate, targets=targets, changes=changes,
            machine_option=(f"rom-mp3-hle-base={gate}" +
                (f",rom-mp3-arena-image={source}" if arena_release else "")), legacy_rom_hle=False,
            guest_workspace_abi="native-decoder-v1", host_decoder="minimp3",
            deferred_input_retirement=deferred_input_retirement,
            hle_pcm_copy=hle_pcm_copy,
            bounded_final_frame=final_frame,
            startup_priming=priming,
            audio_mode_parameters=audio_mode_parameters,
            audio_mode_dsp=audio_mode_dsp,
            arena_release=arena_release,
            compact_workspace=compact_workspace,
            final_input_retirement="next-step" if final_frame else None,
            original_prg_modified=False, factory_player_verified=False,
            host_release_connected=True, whole_machine_snapshot_supported=False))
    return bytes(image), manifest


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resident-bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument('--profile', choices=('manual', 'player'), default='manual',
                        help='player selects the tested v6 compact workspace and arena-release combination; not ESAC support')
    parser.add_argument("--hle-free-words", action="store_true",
                        help="version 2 also implements the missing 01:49BE input-space query")
    parser.add_argument("--deferred-input-retirement", action="store_true",
                        help="version 3 retains input through PCM delivery, then reclaims on the space query")
    parser.add_argument("--hle-pcm-copy",action="store_true",
                        help="version 4 also HLEs the reconstructed software PCM copy; not DTU/DAC")
    parser.add_argument("--final-frame",action="store_true",
                        help="version 5 permits EOF short frames only when all actual audio bits exist")
    parser.add_argument("--priming",action="store_true",
                        help="version 6 retains first PCM through original configured startup priming")
    parser.add_argument('--arena-release',action='store_true',
                        help='close reconstructed codec owner before original application arena reset')
    parser.add_argument('--compact-workspace',action='store_true',
                        help='HLE-only lease without native synthesis history; requires --priming')
    parser.add_argument('--audio-mode-parameters',action='store_true',
                        help='experimental v7 parameter ABI only, no EQ DSP; not a production player profile')
    parser.add_argument('--audio-mode-dsp', action='store_true',
                        help='experimental v8 assumed EQ; requires --audio-mode-parameters')
    args = parser.parse_args(argv)
    if args.profile == 'player':
        for option in ('hle_free_words', 'deferred_input_retirement', 'hle_pcm_copy',
                       'final_frame', 'priming', 'arena_release', 'compact_workspace'):
            setattr(args, option, True)
    if args.deferred_input_retirement and not args.hle_free_words:
        parser.error("--deferred-input-retirement requires --hle-free-words")
    if args.hle_pcm_copy and not args.deferred_input_retirement:
        parser.error("--hle-pcm-copy requires --deferred-input-retirement")
    if args.final_frame and not args.hle_pcm_copy:
        parser.error("--final-frame requires --hle-pcm-copy")
    if args.priming and not args.final_frame:
        parser.error("--priming requires --final-frame")
    if args.compact_workspace and not args.priming:
        parser.error("--compact-workspace requires --priming")
    if args.audio_mode_parameters and not args.priming:
        parser.error('--audio-mode-parameters requires --priming')
    if args.audio_mode_dsp and not args.audio_mode_parameters:
        parser.error('--audio-mode-dsp requires --audio-mode-parameters')
    return args


def main():
    args = parse_args()
    image, manifest = build(args.resident_bundle, hle_free_words=args.hle_free_words,
                           deferred_input_retirement=args.deferred_input_retirement,
                           hle_pcm_copy=args.hle_pcm_copy,final_frame=args.final_frame,priming=args.priming,
                           arena_release=args.arena_release,compact_workspace=args.compact_workspace,
                           audio_mode_parameters=args.audio_mode_parameters,
                           audio_mode_dsp=args.audio_mode_dsp)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/"resident.bin").write_bytes(image)
    (args.output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    load_bundle(args.output)
    print(json.dumps(dict(rom_sha256=sha(image), **manifest["rom_mp3_hle"]), indent=2))


if __name__ == "__main__":
    main()
