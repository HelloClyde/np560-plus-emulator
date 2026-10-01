#!/usr/bin/env python3
"""Observe the real player's live heap and optional native codec integration.

Boot an isolated, read-only tone NAND with the whole original PRG. Reuse
the physical-key route driver; do not inject RAM, reset the heap, allocate
test neighbours, or persist NAND. Default mode measures the missing init
entry. Native-codec mode requires the caller's experimental resident image;
it observes actual ownership/PCM, NOT successful music playback.
Optional physical-control observations also record delivery failures; a
delivered key alone is not proof of the requested playback state change.
"""
from __future__ import annotations

import argparse
from array import array
import base64
import hashlib
import json
import re
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
import wave

from build_np560_mp3_allocation import WORK_STORAGE, SYN_STORAGE
from probe_np560_checkpoint_boot import assess, save_snapshot
from probe_np560_matrix_route import RouteStep, replay_step, matrix_masks
from probe_np560_code_write import HostWatch
from probe_np560_perf_samples import UserIPSampler
from np560_host_time import read_thread_time, thread_time_delta
# Shared diagnostic helpers moved with the test suite; direct CLI invocation
# must not rely on unittest discovery having already changed sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))
from test_np560_mp3_allocation import HEAP_BEGIN, HEAP_END, PRG_SHA
from verify_np560_toolbar_frames import expected_from_package
from web.np560_web import Emulator, RunJournal, artifact_identity

TONE_NAND_SHA = "639e470754517a6b763b0f762d788aed6b78c479aef061692834df3b22a10a19"


class DeviceAudioCapture:
    """Read the actual DAC presentation ring for a bounded time; never fill gaps."""
    def __init__(self, emulator, seconds=20):
        self.seconds=seconds
        self.stop=threading.Event();self.parts=[];self.error=None;self.delivery=[]
        self.lock=threading.Lock()
        self.checkpoint_packets=0
        self.cost=dict(packets=0, query_wall_seconds=0.0, query_thread_cpu_seconds=0.0,
                       processing_wall_seconds=0.0, processing_thread_cpu_seconds=0.0,
                       pcm_base64_chars=0, unique_pcm_bytes=0)
        self.thread=threading.Thread(target=self.run,args=(emulator,),daemon=True)
        self.thread.start()

    def checkpoint(self, packet):
        """Retain the already-read paused endpoint, without another QMP read."""
        with self.lock:
            if self.parts and self.parts[-1]['generation'] == packet['generation']:
                if self.parts[-1]['next_frame'] >= packet['next_frame']:
                    return
            self.append_packet(packet)
            self.checkpoint_packets+=1

    def append_packet(self, packet):
        # Caller owns lock, including QMP read for periodic packets. A saved
        # endpoint can then never overtake a not-yet-appended periodic read.
        processing_started=time.monotonic()
        processing_cpu=time.thread_time()
        if "request_delivery" in packet:
            self.delivery.append({k:packet[k] for k in (
                "generation","next_frame","enabled","request_clock","request_delivery",
                "request_timing","control_event_next","control_events") if k in packet})
        assert packet["sample_rate"]==48000 and packet["channels"]==2
        first,last=packet["first_frame"],packet["next_frame"]
        raw=base64.b64decode(packet["pcm"], validate=True)
        assert len(raw)==(last-first)*4
        if last>first:
            part=self.parts[-1] if self.parts else None
            if part is None or part["generation"]!=packet["generation"] or first>part["next_frame"]:
                part={"generation":packet["generation"],"first_frame":first,
                      "next_frame":first,"data":bytearray()}
                self.parts.append(part)
            assert last>=part["next_frame"],"device audio timeline moved backwards"
            appended=raw[(part["next_frame"]-first)*4:]
            part["data"].extend(appended)
            self.cost['unique_pcm_bytes']+=len(appended)
            part["next_frame"]=last
        self.cost['processing_wall_seconds']+=time.monotonic()-processing_started
        self.cost['processing_thread_cpu_seconds']+=time.thread_time()-processing_cpu

    def run(self, emulator):
        run_started=time.monotonic()
        cpu_started=time.thread_time()
        deadline=time.monotonic()+self.seconds
        try:
            while not self.stop.is_set() and time.monotonic()<deadline:
                with self.lock:
                    query_started=time.monotonic()
                    query_cpu=time.thread_time()
                    packet=emulator.audio()
                    self.cost['query_wall_seconds']+=time.monotonic()-query_started
                    self.cost['query_thread_cpu_seconds']+=time.thread_time()-query_cpu
                    self.cost['packets']+=1
                    self.cost['pcm_base64_chars']+=len(packet['pcm'])
                    self.append_packet(packet)
                self.stop.wait(.05)
        except Exception as error:
            if not self.stop.is_set(): self.error=str(error)
        finally:
            self.cost['total_wall_seconds']=time.monotonic()-run_started
            self.cost['total_thread_cpu_seconds']=time.thread_time()-cpu_started

    def finish(self, output):
        self.thread.join(timeout=5)
        assert not self.thread.is_alive(),"audio reader did not stop after owned QEMU closed"
        results=[]
        for i,part in enumerate(self.parts):
            path=output/f"playback-device-{i}.wav"
            with wave.open(str(path),"wb") as wav:
                wav.setparams((2,2,48000,0,"NONE","not compressed"));wav.writeframes(part["data"])
            values=array("h",part["data"])
            if sys.byteorder!="little": values.byteswap()
            results.append({k:v for k,v in part.items() if k!="data"})
            results[-1].update(path=str(path),sha256=hashlib.sha256(part["data"]).hexdigest(),
                frames=len(part["data"])//4,nonzero_samples=sum(v!=0 for v in values),
                peak=max(map(abs,values),default=0))
        delivery_path=output/"playback-device-requests.json"
        delivery_path.write_text(json.dumps(self.delivery,indent=2)+"\n",encoding="utf-8")
        return {"error":self.error,"parts":results,"sample_rate":48000,
                "capture_cost":self.cost,
                "endpoint_checkpoint_packets":self.checkpoint_packets,
                "request_delivery_path":str(delivery_path),"request_delivery_samples":len(self.delivery),
                "channels":2,"requested_wall_seconds":self.seconds,
                "source":"actual DAC ring; no gap filling, gain or time adjustment"}


class InputRingWatch(HostWatch):
    """Observe two ring words before file selection; dump first AAAA write.

    Much narrower than watching heavily updated IRQ flag words. The first
    complete bad header was at odd ring address 1453, hence watch word 1452.
    This records real writes, not the origin or significance of the value.
    """
    def __init__(self,qemu,pid,output):
        self.path=output/"input-ring-writes.log"
        self.log=self.path.open("x",encoding="utf-8")
        self.process=subprocess.Popen(["gdb","-q","-nx",str(qemu)],stdin=subprocess.PIPE,
            stdout=self.log,stderr=subprocess.STDOUT,text=True)
        commands=f"""set pagination off
set confirm off
set max-value-size unlimited
attach {pid}
set $np = (NP560MachineState *)current_machine
set $env = &$np->cpu->env
set $hits = 0
set $dumped = 0
"""
        dumps=""
        for name,start,size in (("ring",0x1000,0x600),("source-buffers",0x50d948,0x2000),
                ("decoder",0x333e,0xa8),("stream-globals",0x512840,0x40),
                ("audio",0x4a52,0x6a),("flags",0xf000,0x20),
                ("heap",HEAP_BEGIN,HEAP_END-HEAP_BEGIN)):
            # GDB 9.2 aborted inside `dump binary memory` in v1. Keep the
            # read-only examination path already used for stack evidence;
            # delimit it for lossless offline reconstruction if necessary.
            dumps+=f'printf "INPUT_DUMP name={name} address={start:06x} bytes={size}\\n"\nx/{size//2}hx $np->data.ram_block->host+{start}\n'
        for address in (0x1000,0x1452):
            commands+=f"""set $ring_{address:x} = (unsigned short *)($np->cpu->internal_data + {address})
watch -l *$ring_{address:x}
commands
silent
set $hits = $hits + 1
printf "INPUT_WRITE address={address:04x} value=%04x hit=%u writer=%06x pc=%06x sp=%04x fp=%04x\\n", *$ring_{address:x}, $hits, $env->current_instruction_pc, $env->pc, $env->gpr[15], $env->gpr[11]
p/x $env->gpr
printf "SOCR=%04x DS0=%04x DS1=%04x IRQ=%u IGNDS=%u CRIT=%u\\n", $env->sfr[0], $env->sfr[16], $env->sfr[17], $env->in_interrupt, $env->ignore_ds_count, $env->critical_count
x/64hx $np->cpu->internal_data + ($env->gpr[15] & 0xfffe)
if *$ring_{address:x} == 0xaaaa && $dumped == 0
set $dumped = 1
printf "FIRST_AAAA_WRITE captured before further guest instructions\\n"
{dumps}printf "FIRST_AAAA_DUMP_COMPLETE\\n"
end
if $hits >= 64
printf "INPUT_WRITE_LIMIT reached; subsequent writes not observed\\n"
disable
end
continue
end
printf "INPUT_INITIAL address={address:04x} value=%04x\\n", *$ring_{address:x}
"""
        commands+='printf "WATCH_READY guest_address=input_ring_words\\n"\ncontinue\n'
        self.process.stdin.write(commands);self.process.stdin.flush()


class PlayerStateWatch(HostWatch):
    """Two or four host hardware write watches, only on our own process.

    Addresses are resolved from the actual player and allocated owner after
    selection. No guest breakpoint/patch/injection and no calls into QEMU.
    GDB pauses affect wall-clock timing; this is caller evidence, not a
    performance measurement. Keep the existing debugger cleanup protocol.
    """
    def __init__(self,qemu,pid,addresses,output,observe_end=False,observe_volume=False):
        assert not (observe_end and observe_volume), 'hardware watchpoint capacity exceeded'
        assert len(addresses)==2 and all(0x500000<=v<0x600000 and not v&1 for v in addresses.values())
        self.path=output/"player-state-writes.log"
        self.log=self.path.open("x",encoding="utf-8")
        self.process=subprocess.Popen(["gdb","-q","-nx",str(qemu)],stdin=subprocess.PIPE,
            stdout=self.log,stderr=subprocess.STDOUT,text=True)
        commands=f"""set pagination off
set confirm off
set max-value-size unlimited
attach {pid}
set $np = (NP560MachineState *)current_machine
set $env = &$np->cpu->env
set $hits = 0
"""
        targets=[(name,address,"$np->data.ram_block->host",0xffff)
                 for name,address in addresses.items()]
        if observe_volume:
            # DMCU current byte 4A64 occupies the high lane. Capture the
            # whole word to distinguish target changes from native ramps.
            targets += [("volume_current_target",0x4a64,"$np->cpu->internal_data",0xffff)]
        if observe_end:
            # Resolve BIT groups >= 80 through the CPU's internal SRAM.
            # This board currently aliases its base to data RAM; do not
            # confuse these addresses with similarly numbered SFR slots.
            # 89.11 is the original drain/stop request, 89.15 gates the
            # registered end callback; 8C.8 receives !R0.bit0 at 16:E8B8.
            targets += [("end_flags",0xf012,"$np->cpu->internal_data",0x8800),
                        ("decode_exhausted",0xf018,"$np->cpu->internal_data",0x0100)]
        for name,address,backing,mask in targets:
            commands+=f"""set ${name} = (unsigned short *)({backing} + {address})
set ${name}_last = *${name} & {mask}
watch -l *${name}
commands
silent
if (*${name} & {mask}) != ${name}_last
set ${name}_last = *${name} & {mask}
set $hits = $hits + 1
printf "STATE_WRITE name={name} address={address:06x} value=%04x hit=%u writer=%06x pc=%06x sp=%04x fp=%04x\\n", *${name}, $hits, $env->current_instruction_pc, $env->pc, $env->gpr[15], $env->gpr[11]
p/x $env->gpr
printf "SOCR=%04x DS0=%04x DS1=%04x IRQ=%u IGNDS=%u CRIT=%u\\n", $env->sfr[0], $env->sfr[16], $env->sfr[17], $env->in_interrupt, $env->ignore_ds_count, $env->critical_count
x/128hx $np->cpu->internal_data + ($env->gpr[15] & 0xfffe)
printf "INTERNAL_DPRAM_AND_DECODER\\n"
x/16hx $np->cpu->internal_data + 0xf000
x/16hx $np->cpu->internal_data + 0x333e
printf "RAW_DATA_DECODER\\n"
x/16hx $np->data.ram_block->host + 0x333e
if $hits >= 128
printf "STATE_WRITE_LIMIT reached; subsequent writes not observed\\n"
disable
end
end
continue
end
printf "STATE_INITIAL name={name} address={address:06x} value=%04x\\n", *${name}
"""
        commands+='printf "WATCH_READY guest_address=resolved_player_and_owner\\n"\ncontinue\n'
        self.process.stdin.write(commands);self.process.stdin.flush()


class FileScanWatch(HostWatch):
    """One SRAM counter write watch, resolved from a live original call frame.

    The first decrease records its writer and stack, then disables the watch.
    This distinguishes a new call/frame reuse from a damaged loop counter;
    debugger pauses make this unsuitable for throughput measurements.
    """
    def __init__(self,qemu,pid,frame,output):
        assert 0xb04 <= frame <= 0xfea and not frame&1
        self.path=output/"file-scan-writes.log"
        self.log=self.path.open("x",encoding="utf-8")
        self.process=subprocess.Popen(["gdb","-q","-nx",str(qemu)],stdin=subprocess.PIPE,
            stdout=self.log,stderr=subprocess.STDOUT,text=True)
        commands=f"""set pagination off
set confirm off
set max-value-size unlimited
attach {pid}
set $np = (NP560MachineState *)current_machine
set $env = &$np->cpu->env
set $counter = (unsigned short *)($np->cpu->internal_data + {frame-2})
set $last_counter = *$counter
set $hits = 0
watch -l *$counter
commands
silent
set $hits = $hits + 1
if $hits <= 8 || *$counter < $last_counter || (*$counter & 15) == 0
printf "SCAN_WRITE address={frame-2:04x} old=%04x value=%04x hit=%u writer=%06x pc=%06x sp=%04x fp=%04x IRQ=%u\\n", $last_counter, *$counter, $hits, $env->current_instruction_pc, $env->pc, $env->gpr[15], $env->gpr[11], $env->in_interrupt
end
if *$counter < $last_counter
printf "FIRST_SCAN_DECREASE\\n"
p/x $env->gpr
printf "SOCR=%04x DS0=%04x DS1=%04x IGNDS=%u CRIT=%u\\n", $env->sfr[0], $env->sfr[16], $env->sfr[17], $env->ignore_ds_count, $env->critical_count
x/640hx $np->cpu->internal_data + 0xb00
printf "FIRST_SCAN_DECREASE_DUMP_COMPLETE\\n"
disable
end
set $last_counter = *$counter
if $hits >= 1024
printf "SCAN_WRITE_LIMIT reached\\n"
disable
end
continue
end
printf "WATCH_READY guest_address=file_scan_counter frame={frame:04x} value=%04x\\n", *$counter
continue
"""
        self.process.stdin.write(commands);self.process.stdin.flush()


def find_file_scan_frame(raw):
    """Recognize 32:1614's original frame, including its parent's return.

    No fixed FP: the raw stack snapshot is obtained with this owned guest
    stopped. Refuse ambiguous/stale-looking matches instead of watching an
    arbitrary stack address. Actual writer evidence is still required.
    """
    def word(address): return struct.unpack_from("<H",raw,address-0xb00)[0]
    matches=[]
    for frame in range(0xb04,0xfec,2):
        parent=word(frame)
        if not (frame+6 <= parent <= 0xffa and not parent&1): continue
        if (word(frame+2),word(frame+4)) != (0x17,0xe9c0): continue
        if (word(parent+2),word(parent+4)) != (0x32,0xc194): continue
        if (word(frame+6),word(frame+8),word(frame+10)) != (0,0x120,0x81): continue
        count,current=word(frame-2),word(frame-4)
        if count>0x81 or current != 0x120+count: continue
        matches.append(dict(frame=frame,parent=parent,counter=count,current=current))
    return matches[0] if len(matches)==1 else None


def heap_nodes(raw):
    assert len(raw) == HEAP_END-HEAP_BEGIN
    result=[]; address=HEAP_BEGIN
    while address < HEAP_END:
        tag,segment,offset=struct.unpack_from("<3H",raw,address-HEAP_BEGIN)
        next_address=(segment<<16)|offset
        end=next_address or HEAP_END
        assert address+6 <= end <= HEAP_END, (hex(address),tag,hex(end))
        entry={"address":address,"tag":tag,"handle":tag&255,
               "locked":bool(tag&0x8000),"pending_free":bool(tag&0x4000),
               "next":next_address,"payload_bytes":end-address-6,"free":tag==0}
        if entry["free"]:
            start=address+6
            work=start if (start&0x7fff)+WORK_STORAGE<=0x8000 else (start+0x7fff)&~0x7fff
            lease_end=(work+WORK_STORAGE if work-start>=SYN_STORAGE else
                       ((work>>15)+1)*0x8000+SYN_STORAGE)
            required=max(WORK_STORAGE+SYN_STORAGE,lease_end-start)
            entry.update(current_lease_bytes_needed=required,
                         remaining_node_header_bytes=6,
                         current_lease_fits_without_compaction=required+6<=entry["payload_bytes"])
        result.append(entry)
        if next_address==0: break
        address=next_address
    free=[n for n in result if n["free"]]
    return {"arena_begin":HEAP_BEGIN,"arena_end":HEAP_END,"nodes":result,
            "free_payload_bytes":sum(n["payload_bytes"] for n in free),
            "largest_free_payload_bytes":max((n["payload_bytes"] for n in free),default=0),
            "current_lease_has_direct_fit":any(n["current_lease_fits_without_compaction"] for n in free),
            "actual_allocation_attempted":False}


class LocalBridge:
    """Same existing route synchronizer, attached only to our owned QEMU."""
    def __init__(self,emulator): self.emulator=emulator
    def get_json(self,path):
        if path=="/api/key-status": return self.emulator.key_status()
        if path in ("/api/state","/api/diagnostics"): return self.emulator.snapshot("lcd",0,0)
        if path=="/api/frame": return self.emulator.completed_frame()
        raise ValueError(path)
    def set_matrix(self,index):
        low,high=(0,0) if index is None else matrix_masks(index)
        self.emulator.set_key(0,0,low,high)
    def pulse_matrix(self,index): self.emulator.pulse_matrix(index)


def validate_transport_samples(samples):
    """Check settled original player states; not a PCM or timing verdict."""
    result = {}
    for action, count, state, enabled in (
            ('play', 6, 1, True), ('pause', 3, 2, False),
            ('resume', 6, 1, True), ('stop', 3, 0, False)):
        points = [samples[f'06-{action}-{n}'] for n in range(1, count + 1)]
        for point in points:
            assert point['player']['state_087c'] == state, action + ' player state'
            assert point['device_audio']['enabled'] is enabled, action + ' DAC state'
            hle = point['rom_mp3_hle']
            assert not any(hle[field] for field in (
                'failures', 'input_space_failures', 'pcm_copy_failures',
                'final_frame_failures')), action + ' codec failure'
        frames = [point['rom_mp3_hle']['frames'] for point in points]
        if enabled:
            assert all(b > a for a, b in zip(frames, frames[1:])), action + ' decoder stalled'
        else:
            assert len(set(frames)) == 1, action + ' decoder still advancing'
        result[action] = dict(player_state=state, dac_enabled=enabled,
                              decoded_frames=frames, settled_samples=count)
    return result


def validate_seek_history(before, after, max_startup_frames):
    """Classify only evidenced reset-time warmup, retaining raw failures.

    The caller must separately prove position movement and resumed PCM/decode.
    The bound is fixture-specific, not a universal MPEG/ROM tolerance.
    """
    recovery = after['history_recovery']
    # Factory reload initializes several nested wrappers (currently three
    # reset calls). The per-action no-output bound below applies across ALL
    # those resets, so repeated reset cannot replenish a warmup allowance.
    assert after['calls'][0] > before['calls'][0], 'no decoder reset at seek'
    delta = after['failures'] - before.get('failures', 0)
    assert 0 <= delta <= max_startup_frames, 'seek warmup total exceeded bound'
    assert not recovery['after_output'], 'history missing after output began'
    assert not recovery['no_progress'], 'history warmup made no progress'
    assert recovery['max_startup_frames'] <= max_startup_frames, 'warmup exceeded bound'
    for field in ('input_space_failures','pcm_copy_failures','final_frame_failures'):
        assert after[field] == 0, field
    reasons = after['no_pcm_reasons']
    assert reasons['invalid_sideinfo'] == reasons['unknown'] == 0, 'unclassified no-PCM'
    assert (after['failures'] == after['codec_results']['no_pcm'] ==
            reasons['missing_history'] == recovery['startup_frames']), 'not all failures are startup history'
    for key, value in after['codec_results'].items():
        if key not in ('ok','no_pcm'):
            assert value == 0, 'codec error: ' + key
    assert after['frames'] > before['frames'], 'no decode recovery'
    return dict(raw_failures=after['failures'], startup_history_frames=recovery['startup_frames'],
                max_startup_frames=recovery['max_startup_frames'], permitted_bound=max_startup_frames)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("qemu","firmware","soc-rom","nand-checkpoint","package","output"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--observe-native-codec",action="store_true",
                   help="observe real allocations/PCM after selecting a file with experimental factory ABI")
    p.add_argument('--expected-nand-sha256', default=TONE_NAND_SHA,
                   help='explicit identity for an independently verified fixture; default is original tone NAND; LCD route guard remains')
    p.add_argument("--rom-mp3-hle-base",type=lambda value:int(value,0),default=0,
                   help="explicit marked 01/02 MP3 HLE service base; not legacy ROM/UI HLE")
    p.add_argument("--icount-shift",type=lambda value:"auto" if value=="auto" else int(value),
                   choices=(*range(11),"auto"),default=None,
                   help="optional QEMU instruction clock; auto adapts to host speed, not real CPU cycles")
    p.add_argument("--host-timeout-scale",type=float,default=1,
                   help="scale ONLY host boot/key/readiness timeouts (1..20); guest clock is unchanged")
    p.add_argument("--instruction-clock",action="store_true",
                   help="experimental PLL/CLKCON partial cycle model; requires --icount-shift 0")
    p.add_argument("--startup-card-reference",type=Path,
                   help="optional exact gray5 startup-card reference; dismiss once using physical Enter")
    p.add_argument("--key-release",choices=("auto","candidate","host-pulse"),default="auto",
                   help="physical-key release policy; explicit candidate enables same-input clock comparisons")
    p.add_argument('--key-pulse-ms', type=int, choices=range(20,501), default=150,
                   help='fixed physical hold duration for host-pulse; never wait for a guest candidate')
    p.add_argument("--observe-dtu-refill",action="store_true",
                   help="opt-in read-only completion/IRQ/refill timestamps, no hardware changes")
    p.add_argument("--minimal-control-observers",action="store_true",
                   help="experimental reduced historical observers; strict faults and key ACK retained")
    p.add_argument('--trace-player-redraw', action='store_true',
                   help='enable existing resource observers just before closing the file picker; not timing evidence')
    p.add_argument('--wake-before-player', action='store_true',
                   help='native M63 screen-off/M61 wake/F4 return before selecting audio')
    p.add_argument('--observe-volume-contact-bounds', action='store_true',
                   help='Bracket initial volume contacts with guest-time reads (perturbs timing)')
    p.add_argument('--trace-volume-contacts', action='store_true',
                   help='Record atomic matrix changes inside core; read only after each initial volume attempt')
    p.add_argument('--initial-volume-settle-ms', type=int, choices=range(0, 2001), default=300,
                   help='Idle settle after each initial volume attempt; does not change contact duration')
    p.add_argument('--initial-volume-up', type=int, choices=range(8), default=0,
                   help='raise native player volume by physical Up contacts before codec observation')
    p.add_argument('--probe-key-durations', action='store_true',
                   help='before player route, compare 40/80/150 ms M26 contacts on owned desktop')
    p.add_argument('--speed-window-seconds', type=int, choices=range(0,61), default=0,
                   help='unpaused desktop/player speed windows with LCD polling; no debugger')
    p.add_argument('--profile-unknown-cycles', action='store_true',
                   help='count unknown-cycle opcode families during windows; diagnostic overhead, not a performance comparison')
    p.add_argument('--profile-host-cpu', action='store_true',
                   help='sample owned CPU user IPs during player windows only (Linux x86_64; not a speed benchmark)')
    p.add_argument('--observe-host-cpu-time', action='store_true',
                   help='read owned Linux CPU thread accounting at speed-window endpoints only')
    p.add_argument('--profile-audio-reopen', action='store_true',
                   help='bounded read-only PC samples while DAC is off after playback; not a speed test')
    p.add_argument('--profile-audio-reopen-stack', action='store_true',
                   help='pause once per closed episode for a coherent waiter stack; requires reopen profile')
    p.add_argument('--profile-audio-reopen-seconds', type=int, choices=range(1,121), default=12,
                   help='bounded reopen observation window; extend for long tracks, maximum 120 seconds')
    p.add_argument('--profile-player', action='store_true',
                   help='after speed windows, collect 20 read-only CPU stack samples; not timing evidence')
    p.add_argument('--speed-audio-poll', action='store_true',
                   help='also fetch the complete DAC packet every 50 ms in the player speed window')
    p.add_argument('--compare-audio-poll', action='store_true',
                   help='same-process player windows without/with/with/without audio polling; no recorder')
    p.add_argument('--profile-samples', type=int, choices=range(1,101), default=20,
                   help='bounded number of debugger samples, outside timing windows')
    p.add_argument('--realtime', action='store_true',
                   help='enable QEMU host pacing; requires the instruction clock')
    p.add_argument("--observe-dtu-config",action="store_true",
                   help="read the bounded ED configuration trace; no breakpoints or guest writes")
    p.add_argument("--record-device-audio",action="store_true",
                   help="capture actual DAC ring after file selection; split on gaps")
    p.add_argument('--audio-start-at-file-switch', action='store_true',
                   help='start existing DAC capture immediately before confirming the target file')
    p.add_argument("--audio-seconds",type=int,choices=range(1,301),default=20,
                   help="bounded actual-device capture time; default 20 wall seconds")
    p.add_argument("--codec-observations",type=int,choices=range(1,61),default=12,
                   help="number of five-second observations of the SAME owned process")
    p.add_argument("--observe-play-controls",action="store_true",
                   help="after loading, observe physical D/F/D/G keys; requires native codec mode")
    p.add_argument('--play-controls-volume-up', type=int, choices=range(8), default=0,
                   help='physical volume Up contacts before transport checks; requires --observe-play-controls')
    p.add_argument("--observe-volume-controls",action="store_true",
                   help="after loading, sweep seven contacts each direction and record native volume/PCM")
    p.add_argument('--volume-sweep-order', choices=('down-up','up-down'), default='down-up',
                   help='physical volume sweep order; up-down tests real descent from the highest level')
    p.add_argument("--inspect-player-files",action="store_true",
                   help="after playback reopen the real file picker with F1 and capture it; no file selection")
    p.add_argument('--inspect-audio-modes', action='store_true',
                   help='physical F3/settings -> audio modes -> next option; isolated read-only NAND')
    p.add_argument('--audio-mode-volume-up', type=int, choices=range(8), default=0,
                   help='physical Up contacts before mode comparison, no direct volume writes')
    p.add_argument('--sweep-audio-modes', action='store_true',
                   help='visit all 14 grid entries using physical keys and verify original parameters')
    p.add_argument("--switch-mono-reference",type=Path,
                   help="after file inspection select verified MONO441.MP3; path to the observed full gray5 reference")
    p.add_argument('--switch-long22-reference', type=Path,
                   help='select the pinned LONG22.MP3 reference instead of MONO441')
    p.add_argument('--file-switch-up-count', type=int, choices=range(65), default=0,
                   help='explicit physical Up steps after file-switch Down route')
    p.add_argument('--file-switch-row-y', type=int, choices=range(108), default=105,
                   help='actual target row position; exact reference pixels remain required')
    p.add_argument('--file-switch-volume-up', type=int, choices=range(8), default=0,
                   help='physical Up contacts before file-switch inspection')
    p.add_argument('--file-switch-eq', action='store_true',
                   help='select heavy-treble in the original menu before switching files')
    p.add_argument('--return-stereo-from-list', action='store_true',
                   help='after LONG22 playback, physically select the first playlist item')
    p.add_argument("--stop-before-file-picker",action="store_true",
                   help="physical G/Stop before reopening picker, as a switching diagnostic control")
    p.add_argument("--play-mono-from-list",action="store_true",
                   help="after adding MONO441 use F2, Down, Enter to select it for playback")
    p.add_argument("--watch-playlist-index",action="store_true",
                   help="host hardware watches of player index/path during real playlist selection; not timing")
    p.add_argument("--tone-down-count",type=int,choices=range(1,65),default=28,
                   help="physical root-list Down presses; selected tone still requires exact LCD row match")
    p.add_argument("--tone-row-y",type=int,choices=range(108),default=105,
                   help="top pixel of the selected 13-pixel tone row; supports changed list scrolling")
    p.add_argument("--tone-up-count",type=int,choices=range(65),default=0,
                   help="physical Up presses after Down navigation; exact tone LCD guard remains mandatory")
    p.add_argument('--selected-file-reference', type=Path,
                   help='explicit visually inspected full gray5 file-list reference (selected row y=105)')
    p.add_argument('--selected-file-reference-sha256',
                   help='pinned SHA256 of the explicitly inspected file-list reference')
    p.add_argument("--observe-player-back",action="store_true",
                   help="observe physical Back84 after playback; do not assume delivery means exit")
    p.add_argument('--rom-mp3-arena-image',type=lambda s:int(s,0),default=0)
    p.add_argument("--observe-player-minimize",action="store_true",
                   help="observe original F4/008E minimize; not a forced session release")
    p.add_argument("--observe-exit-heap-writes",action="store_true",
                   help="watch two live heap headers during F4; read-only, not timing evidence")
    p.add_argument('--reopen-after-minimize',action='store_true',
                   help='reopen and play the same NAND file in the SAME process, then minimize again')
    p.add_argument('--minimize-with-eq',action='store_true',
                   help='select treble EQ through original UI before the reopen/release check')
    p.add_argument('--observe-seek-reload-writes', action='store_true',
                   help='read-only hardware watches on original seek stream/frame; not timing evidence')
    p.add_argument('--observe-seek-controls',action='store_true',
                   help='use original H/S forward/back controls instead of D/F/D/G transport observations')
    p.add_argument('--inspect-player-help', action='store_true',
                   help='capture the original M15/008D help route after playback; not repeat verification')
    p.add_argument('--observe-ab-repeat', action='store_true',
                   help='use three original Space contacts to set A/B and cancel; observe position, not listening quality')
    p.add_argument('--observe-player-blank', action='store_true',
                   help='use original B twice for white-screen mode and recovery while decoding')
    p.add_argument("--observe-state-writes",action="store_true",
                   help="host hardware watches of actual player state and owner READY during controls")
    p.add_argument("--observe-end-writes",action="store_true",
                   help="also watch original internal-SRAM end/exhaustion bits; requires state watches")
    p.add_argument("--observe-input-writes",action="store_true",
                   help="watch input words before selection and capture first AAAA write; native codec only")
    p.add_argument("--observe-file-scan-writes",action="store_true",
                   help="resolve the original file-scan frame and observe its first counter decrease")
    p.add_argument("--observe-audio-files",action="store_true",
                   help="read sparse original file/callback boundaries without a host debugger")
    args=p.parse_args()
    if args.observe_host_cpu_time and not args.speed_window_seconds:
        p.error('--observe-host-cpu-time requires speed windows')
    if args.profile_host_cpu and (not 1 <= args.speed_window_seconds <= 30 or
                                 args.profile_unknown_cycles):
        p.error('--profile-host-cpu requires a 1..30 second window without opcode profiling')
    if args.trace_volume_contacts and (not args.initial_volume_up or
            args.observe_volume_contact_bounds or args.key_release != 'host-pulse'):
        p.error('--trace-volume-contacts requires initial volume host pulses and no boundary polling')
    if args.observe_player_blank and (not args.observe_native_codec or any((
            args.inspect_player_help,args.observe_ab_repeat,args.observe_play_controls,
            args.observe_volume_controls,args.inspect_player_files,args.inspect_audio_modes,
            args.observe_player_back,args.observe_player_minimize,args.speed_window_seconds))):
        p.error('--observe-player-blank requires native codec without other UI routes or speed windows')
    if args.observe_ab_repeat and (not args.observe_native_codec or any((
            args.inspect_player_help, args.observe_play_controls, args.observe_volume_controls,
            args.inspect_player_files, args.inspect_audio_modes, args.observe_player_back,
            args.observe_player_minimize, args.speed_window_seconds))):
        p.error('--observe-ab-repeat requires native codec without other UI routes or speed windows')
    if args.inspect_player_help and (not args.observe_native_codec or any((
            args.observe_play_controls, args.observe_volume_controls,
            args.inspect_player_files, args.inspect_audio_modes,
            args.observe_player_back, args.observe_player_minimize,
            args.speed_window_seconds))):
        p.error('--inspect-player-help requires native codec without other UI routes or speed windows')
    if args.play_controls_volume_up and not (args.observe_play_controls or args.observe_ab_repeat or args.observe_player_blank):
        p.error('--play-controls-volume-up requires --observe-play-controls or --observe-ab-repeat')
    if args.compare_audio_poll and (not args.speed_window_seconds or
            not args.observe_native_codec or args.record_device_audio):
        p.error('--compare-audio-poll requires speed windows, native codec, and no separate recorder')
    if args.profile_unknown_cycles and not (args.speed_window_seconds and args.instruction_clock):
        p.error('--profile-unknown-cycles requires speed windows and instruction clock')
    if args.profile_audio_reopen and not args.observe_native_codec:
        p.error('--profile-audio-reopen requires --observe-native-codec')
    if args.profile_audio_reopen_stack and not args.profile_audio_reopen:
        p.error('--profile-audio-reopen-stack requires --profile-audio-reopen')
    if args.realtime and not args.instruction_clock:
        p.error('--realtime requires --instruction-clock')
    if args.observe_seek_reload_writes and (not args.observe_seek_controls or any((
            args.observe_state_writes, args.observe_input_writes,
            args.observe_file_scan_writes, args.observe_exit_heap_writes,
            args.speed_window_seconds, args.record_device_audio))):
        p.error('--observe-seek-reload-writes requires seek controls without other watches, audio recording or speed windows')
    if args.speed_window_seconds and (not args.instruction_clock or any((
            args.observe_state_writes, args.observe_end_writes, args.observe_input_writes,
            args.observe_file_scan_writes, args.observe_exit_heap_writes))):
        p.error('speed windows require instruction clock and no debugger observers')
    if args.instruction_clock and args.icount_shift != 0:
        p.error("--instruction-clock requires --icount-shift 0")
    if not 1 <= args.host_timeout_scale <= 20:
        p.error("--host-timeout-scale must be in [1,20]")
    if args.observe_play_controls and not args.observe_native_codec:
        p.error("--observe-play-controls requires --observe-native-codec")
    if args.volume_sweep_order != 'down-up' and not args.observe_volume_controls:
        p.error('--volume-sweep-order requires --observe-volume-controls')
    if args.observe_volume_controls and (not args.observe_native_codec or args.observe_play_controls):
        p.error("--observe-volume-controls requires native codec and no play-controls sequence")
    if args.inspect_audio_modes and (not args.observe_native_codec or any((
            args.observe_play_controls, args.observe_volume_controls, args.inspect_player_files,
            args.observe_player_back, args.observe_player_minimize, args.speed_window_seconds))):
        p.error('--inspect-audio-modes requires native codec and no other control sequence')
    if args.audio_mode_volume_up and not args.inspect_audio_modes:
        p.error('--audio-mode-volume-up requires --inspect-audio-modes')
    if args.sweep_audio_modes and not args.inspect_audio_modes:
        p.error('--sweep-audio-modes requires --inspect-audio-modes')
    if bool(args.selected_file_reference) != bool(args.selected_file_reference_sha256):
        p.error('--selected-file-reference and its SHA256 must be supplied together')
    if args.selected_file_reference:
        explicit_reference = args.selected_file_reference.read_bytes()
        if (len(explicit_reference) != 240*120 or any(v > 31 for v in explicit_reference)
                or hashlib.sha256(explicit_reference).hexdigest() != args.selected_file_reference_sha256):
            p.error('selected-file reference must be valid gray5 with the pinned SHA256')
    if args.inspect_player_files and (not args.observe_native_codec or args.observe_player_back or args.observe_player_minimize):
        p.error("--inspect-player-files requires native codec and cannot follow player exit")
    if args.switch_mono_reference and not args.inspect_player_files:
        p.error("--switch-mono-reference requires --inspect-player-files")
    if (args.switch_long22_reference or args.file_switch_volume_up) and not args.inspect_player_files:
        p.error('file switch options require --inspect-player-files')
    if args.switch_long22_reference and args.switch_mono_reference:
        p.error('choose only one file-switch reference')
    if args.audio_start_at_file_switch and not (args.record_device_audio and
            (args.switch_long22_reference or args.switch_mono_reference)):
        p.error('file-switch audio capture requires recording and a target reference')
    if (args.file_switch_up_count or args.file_switch_row_y != 105) and not (
            args.switch_long22_reference or args.switch_mono_reference):
        p.error('file-switch positioning requires a pinned target reference')
    if (args.file_switch_eq or args.return_stereo_from_list) and not (
            args.switch_long22_reference and args.play_mono_from_list):
        p.error('EQ/return switch requires LONG22 and explicit playlist playback')
    if args.stop_before_file_picker and not args.inspect_player_files:
        p.error("--stop-before-file-picker requires --inspect-player-files")
    if args.play_mono_from_list and not (args.switch_mono_reference or args.switch_long22_reference):
        p.error("--play-mono-from-list requires --switch-mono-reference")
    if args.trace_player_redraw and (not args.switch_mono_reference or
            not args.minimal_control_observers or args.speed_window_seconds):
        p.error('--trace-player-redraw requires mono selection, minimal observers and no speed window')
    if args.watch_playlist_index and (not args.play_mono_from_list or args.speed_window_seconds or
            any((args.observe_state_writes,args.observe_input_writes,args.observe_exit_heap_writes,args.observe_file_scan_writes))):
        p.error("--watch-playlist-index requires list playback and no other watch/speed window")
    mono_row=None
    switch_path = b'0:\\MONO441.MP3'
    switch_down_count = 28
    if args.switch_long22_reference:
        long_frame = args.switch_long22_reference.read_bytes()
        if hashlib.sha256(long_frame).hexdigest() != '7468d581c323c9c8482e02899a7de990bbd4e64b12ca567fd6bb28c976b23fc0':
            p.error('LONG22 reference is not the visually checked file-list frame')
        mono_row = long_frame[105*240:118*240]
        switch_path = b'0:\\LONG22.MP3'
        switch_down_count = 29
    if args.switch_mono_reference:
        mono_frame=args.switch_mono_reference.read_bytes()
        if len(mono_frame)!=240*120:
            p.error("mono reference must be a complete gray5 frame")
        mono_row=mono_frame[105*240:118*240]
        if hashlib.sha256(mono_row).hexdigest()!='869d339ad696299a5305d489e2cd3c3963d7a98e5eebecb17f1236e83cc189c3':
            p.error("mono reference is not the observed MONO441.MP3 5015-byte row")
    if args.observe_player_back and not args.observe_native_codec:
        p.error("--observe-player-back requires --observe-native-codec")
    if args.observe_player_minimize and (not args.observe_native_codec or args.observe_player_back):
        p.error("--observe-player-minimize requires native codec and cannot combine with Back")
    if args.observe_exit_heap_writes and (not args.observe_player_minimize or
            args.observe_state_writes or args.observe_input_writes or args.observe_file_scan_writes):
        p.error("--observe-exit-heap-writes requires minimize and no other write watches")
    if args.reopen_after_minimize and (not args.observe_player_minimize or not args.rom_mp3_hle_base or
            args.observe_exit_heap_writes or args.observe_state_writes or args.observe_input_writes or
            args.observe_file_scan_writes):
        p.error('--reopen-after-minimize requires minimize and HLE, without hardware watches')
    if args.minimize_with_eq and not args.reopen_after_minimize:
        p.error('--minimize-with-eq requires --reopen-after-minimize')
    if args.observe_seek_controls and (not args.observe_play_controls or args.observe_volume_controls):
        p.error('--observe-seek-controls requires play controls without volume sweep')
    if args.observe_state_writes and not (args.observe_play_controls or args.observe_volume_controls):
        p.error("--observe-state-writes requires play or volume controls")
    if args.observe_end_writes and args.observe_volume_controls:
        p.error("volume target and end flag watches cannot be combined")
    if args.observe_end_writes and not args.observe_state_writes:
        p.error("--observe-end-writes requires --observe-state-writes")
    if args.observe_input_writes and (not args.observe_native_codec or args.observe_state_writes):
        p.error("--observe-input-writes requires native codec and cannot combine with state watches")
    if args.observe_file_scan_writes and (not args.observe_native_codec or
            args.observe_play_controls or args.observe_input_writes):
        p.error("--observe-file-scan-writes requires native codec and no other write/control watches")
    if not re.fullmatch(r'[0-9a-fA-F]{64}', args.expected_nand_sha256):
        p.error('--expected-nand-sha256 must contain 64 hexadecimal digits')
    args.output.mkdir(parents=True,exist_ok=False)
    identities={}
    for name in ("qemu","firmware","soc_rom","nand_checkpoint","package"):
        path=getattr(args,name);size,digest=artifact_identity(path)
        identities[name]={"path":str(path.resolve()),"bytes":size,"sha256":digest}
    assert identities["firmware"]["sha256"]==PRG_SHA
    assert identities["nand_checkpoint"]["sha256"]==args.expected_nand_sha256.lower(), 'NAND identity differs from explicit fixture pin'
    report={"passed":False,"artifacts":identities,"route":[],"heap_samples":{},
            "host_guest_memory_writes":0,"nand_save_enabled":False,
            "missing_entry_bypassed":False,"factory_player_connected":False,
            "observe_native_codec":args.observe_native_codec,"native_codec_samples":{},
            "observe_play_controls":args.observe_play_controls,"control_observations":[],
            "playback_verified":False}
    report["rom_mp3_hle_base"]=args.rom_mp3_hle_base
    report["icount_shift"]=args.icount_shift
    report["instruction_clock"]=args.instruction_clock
    report['realtime_pacing']=args.realtime
    report["host_timeout_scale"]=args.host_timeout_scale
    # Fixed instruction time can run much slower than host time. A 150 ms
    # HOST pulse then disappears before one original scanner iteration.
    # In that mode use replay_step's existing candidate-gated release: keep
    # the physical level until the guest observes it, then release normally.
    # Do not use a single-scan device pulse or inject the logical event.
    candidate_release=(args.key_release=="candidate" or
        (args.key_release=="auto" and args.icount_shift is not None))
    key_pulse_duration=0 if candidate_release else args.key_pulse_ms / 1000
    report["key_press_policy"]=("physical level until original candidate, then release"
        if key_pulse_duration==0 else f"physical level for {key_pulse_duration} host seconds")
    startup_card=None
    if args.startup_card_reference is not None:
        startup_card=args.startup_card_reference.read_bytes()
        assert len(startup_card)==240*120 and all(v<=31 for v in startup_card),"invalid startup gray5 reference"
        report["startup_card_reference"]={"path":str(args.startup_card_reference.resolve()),
            "sha256":hashlib.sha256(startup_card).hexdigest(),
            "policy":"one physical Enter only after three exact full-frame matches; no timer/PC edits"}
    report["codec_observations"]=args.codec_observations
    report["dtu_refill_trace_enabled"]=args.observe_dtu_refill
    report["control_observers_minimal"]=args.minimal_control_observers
    report["memory_write_scope"]="zero debugger injections; enabled HLE writes its owned service outputs"
    journal=RunJournal(args.output/"process",kind="mp3-player-heap",artifacts=identities)
    emulator=watch=audio_capture=None
    active_host_samplers = []
    def capture(label,check_watch=True):
        if watch is not None and check_watch: watch.check()
        emulator.qmp.execute("stop")
        try:
            state=emulator.snapshot("lcd",0,0);save_snapshot(args.output,label,state)
            ranges=(("heap","memory",HEAP_BEGIN,HEAP_END-HEAP_BEGIN),
                    ("arena-entry","code",0x308c1c,0x10),
                    ("input-ring","data",0x1000,0x600),
                    ("source-buffers","data",0x50d948,0x2000),
                    ("stream-globals","data",0x512840,0x40),
                    ("decoder","data",0x333e,0xa8),("audio","data",0x4a52,0x6a),
                    ("audio-dualport","data",0xf000,32),
                    ("audio-vectors","code",0xc0,8),
                    ("heap-bitmap","memory",0x5127ea,32),
                    ("heap-end","memory",0x5129a0,4))
            if args.observe_dtu_config or args.observe_file_scan_writes or args.observe_audio_files:
                ranges += (("audio-contexts","data",0x48c4,0x18e),
                           ("internal-stack","data",0x0b00,0x500))
            if args.observe_audio_files:
                ranges += (("file-loop-code","code",0x321614,0x88),
                           ("file-driver-globals","data",0x5129a0,0x150))
            scan_frame=None
            for suffix,source,start,size in ranges:
                raw=base64.b64decode(emulator.snapshot(source,start,size)["frame"])
                (args.output/f"{label}.{suffix}.bin").write_bytes(raw)
                if suffix=='arena-entry' and args.rom_mp3_arena_image:
                    image=args.soc_rom.read_bytes()
                    expected=image[args.rom_mp3_arena_image:args.rom_mp3_arena_image+size]
                    assert raw==expected,'arena release image is not active on the code bus'
                if suffix=="internal-stack" and args.observe_file_scan_writes:
                    scan_frame=find_file_scan_frame(raw)
                if suffix=="heap":
                    report["heap_samples"][label]=heap_nodes(raw)
                    if args.observe_native_codec:
                        # Recognize the new owned payload by its actual heap
                        # node, size, signature and self handle; never inject
                        # or assume the diagnostic caller's owner address.
                        import build_np560_mp3_factory as binding
                        import build_np560_mp3_session as session
                        owners=[]
                        for node in report["heap_samples"][label]["nodes"]:
                            if node["free"] or node["payload_bytes"]!=binding.SIZE: continue
                            start=node["address"]+6-HEAP_BEGIN
                            words=struct.unpack_from(f"<{binding.SIZE//2}H",raw,start)
                            if (words[binding.SIGNATURE//2]!=binding.SIGNATURE_VALUE or
                                    words[binding.SELF_HANDLE//2]!=node["handle"]): continue
                            owners.append({"node":node,"words":words,
                                "session_initialized":words[session.MAGIC//2]==session.MAGIC_VALUE,
                                "ready":words[session.READY//2],"phase":words[session.PHASE//2],
                                "status":words[session.STATUS//2],"detail":words[session.DETAIL//2],
                                "lease_handle":words[0],"busy":words[session.BUSY//2]})
                        report["native_codec_samples"][label]={"owners":owners}
            if args.observe_native_codec:
                if args.observe_volume_controls or args.inspect_audio_modes or args.initial_volume_up:
                    volume = emulator.snapshot("data", 0x4a64, 4, diagnostics=False)
                    report["native_codec_samples"][label]["volume_bytes"] = base64.b64decode(volume["frame"]).hex()
                pcm=base64.b64decode(emulator.snapshot("data",0x1784,4608)["frame"])
                (args.output/f"{label}.pcm-buffers.bin").write_bytes(pcm)
                values=struct.unpack("<2304h",pcm)
                report["native_codec_samples"][label].update(
                    pcm_nonzero_values=sum(v!=0 for v in values),pcm_sha256=hashlib.sha256(pcm).hexdigest())
                packet=emulator.audio()
                device_pcm=base64.b64decode(packet.pop("pcm"))
                (args.output/f"{label}.device-pcm.bin").write_bytes(device_pcm)
                device_values=struct.unpack(f"<{len(device_pcm)//2}h",device_pcm)
                packet.update(nonzero_values=sum(v!=0 for v in device_values),
                              pcm_sha256=hashlib.sha256(device_pcm).hexdigest())
                report["native_codec_samples"][label]["device_audio"]=packet
                report["native_codec_samples"][label]["transport"]={
                    prop:emulator.qmp.execute("qom-get",{"path":"/machine","property":prop})
                    for prop in ("dtu-state","timer0-state","timer1-state","timer2-state")}
                if args.instruction_clock:
                    clock=emulator.qmp.execute("qom-get",{"path":"/machine",
                        "property":"instruction-clock-state"})
                    report["native_codec_samples"][label]["instruction_clock"]=clock
                    assert "FAULT:0" in clock, clock
                if args.observe_dtu_refill:
                    report["native_codec_samples"][label]["dtu_refill"]=json.loads(
                        emulator.qmp.execute("qom-get",{"path":"/machine","property":"dtu-refill-state"}))
                if args.observe_dtu_config:
                    report["native_codec_samples"][label]["dtu_config"]=json.loads(
                        emulator.qmp.execute("qom-get",{"path":"/machine","property":"dtu-config-trace"}))
                if args.observe_audio_files:
                    audio_files=json.loads(emulator.qmp.execute("qom-get",
                        {"path":"/machine","property":"audio-file-trace"}))
                    report["native_codec_samples"][label]["audio_files"]=audio_files
                    (args.output/f"{label}.audio-files.json").write_text(json.dumps(audio_files,indent=2)+"\n")
                # Original 0D:500C..5050 loads this far pointer and checks
                # byte fields +087A (MP3 mode 5) and +087C (Play/Pause gate).
                # Read physical memory, independent of the current DS. The
                # byte bus addresses the high byte first within each word.
                pointer_raw=base64.b64decode(emulator.snapshot("memory",0x507e06,4)["frame"])
                (args.output/f"{label}.player-root.bin").write_bytes(pointer_raw)
                segment,offset=struct.unpack("<2H",pointer_raw)
                address=(segment<<16)|offset
                player={"address":address,"key_status":emulator.key_status()}
                # The root survives an arena reset and can point into freed
                # memory (e.g. 0x44 fill is not player state 68).
                allocation=next((n for n in report["heap_samples"][label]["nodes"]
                    if not n["free"] and n["address"]+6==address and
                    n["payload_bytes"]>=0x08a0),None)
                player["allocation_live"]=allocation is not None
                if allocation is not None:
                    fields=base64.b64decode(emulator.snapshot("memory",address+0x0860,0x40)["frame"])
                    (args.output/f"{label}.player-fields.bin").write_bytes(fields)
                    player.update(mode_087a=fields[0x1a^1],selection_087b=fields[0x1b^1],
                                  state_087c=fields[0x1c^1])
                    if args.observe_seek_controls or args.observe_ab_repeat:
                        position = base64.b64decode(emulator.snapshot('memory',address+0x0802,8)['frame'])
                        total_hi,total_lo,current_hi,current_lo = struct.unpack('<4H',position)
                        player.update(duration_ms_0802=(total_hi<<16)|total_lo,
                                      position_ms_0806=(current_hi<<16)|current_lo)
                report["native_codec_samples"][label]["player"]=player
                if args.rom_mp3_hle_base:
                    hle=json.loads(
                        emulator.qmp.execute("qom-get",{"path":"/machine","property":"rom-mp3-hle-state"}))
                    report["native_codec_samples"][label]["rom_mp3_hle"]=hle
                    print(f"  HLE frames={hle['frames']} granules={hle['granules']} "
                          f"input-space calls={hle.get('input_space_calls',0)} failures={hle['failures']}",flush=True)
                print(f"  {state['registers'].splitlines()[0]} DAC={packet.get('enabled')} "
                      f"mode={player.get('mode_087a')} state={player.get('state_087c')}",flush=True)
            measured=report["heap_samples"][label]
            print(f"{label}: free={measured['free_payload_bytes']} largest={measured['largest_free_payload_bytes']} direct-fit={measured['current_lease_has_direct_fit']}",flush=True)
            if args.observe_file_scan_writes and scan_frame and watch is None and label.startswith("05-codec-"):
                arm_file_scan(scan_frame,label)
            return state
        finally: emulator.qmp.execute("cont")
    def speed_window(label, audio_poll_override=None):
        if not args.speed_window_seconds:
            return
        # A looping short file can be in the native close/reopen interval at
        # a window boundary. Wait for actual playback, never force DAC state.
        deadline=time.monotonic()+5
        while True:
            emulator.qmp.execute('stop')
            audio_before=emulator.audio() if label == 'player' else None
            if not audio_before or (audio_before['enabled'] and audio_before['request_clock']['running']):
                break
            emulator.qmp.execute('cont')
            if time.monotonic() >= deadline:
                raise AssertionError('playback did not become active before speed window')
            time.sleep(.05)
        def clock_sample():
            clock=emulator.qmp.execute('qom-get', {'path':'/machine','property':'instruction-clock-state'})
            assert 'FAULT:0' in clock, clock
            # Reuse the paused endpoint read: no additional sampling in the
            # measured interval. A cycle-model correction can change guest
            # seconds without making host instruction execution faster.
            return {field: int(re.search(r'\b'+field+r':(\d+)\b', clock)[1])
                    for field in ('NS', 'INSTRUCTIONS', 'CYCLES', 'UNKNOWN_COST',
                                  'UNKNOWN_SRAM', 'UNKNOWN_OPCODE')}
        clock_before=clock_sample()
        profile_property={'path': '/machine', 'property': 'instruction-clock-profile'}
        if args.profile_unknown_cycles:
            profile_before=json.loads(emulator.qmp.execute('qom-get', profile_property))
            emulator.qmp.execute('qom-set', {'path': '/machine',
                'property': 'instruction-clock-profile-enabled', 'value': True})
        if audio_before:
            assert audio_before['enabled'] and audio_before['request_clock']['running'], 'speed window is not active playback'
        host_sampler = None
        if args.profile_host_cpu and label == 'player':
            cpus = emulator.qmp.execute('query-cpus-fast')
            assert len(cpus) == 1
            host_tid = cpus[0]['thread-id']
            assert Path(f'/proc/{emulator.process.pid}/task/{host_tid}').is_dir()
            host_sampler = UserIPSampler(host_tid)
            active_host_samplers.append(host_sampler)
            host_sampler.start()
        host_time_before = None
        if args.observe_host_cpu_time:
            cpus = emulator.qmp.execute('query-cpus-fast')
            assert len(cpus) == 1
            time_tid = cpus[0]['thread-id']
            host_time_before = read_thread_time(emulator.process.pid, time_tid)
        started=time.monotonic()
        emulator.qmp.execute('cont')
        polls=0
        audio_polls=0
        audio_poll_seconds=0.0
        audio_pcm_chars=0
        lcd_poll_seconds=0.0
        next_lcd=started
        poll_audio=args.speed_audio_poll and label == 'player'
        if audio_poll_override is not None:
            poll_audio=audio_poll_override
        while time.monotonic()-started < args.speed_window_seconds:
            if time.monotonic() >= next_lcd:
                request_started=time.monotonic()
                emulator.snapshot('lcd', 0, 0, diagnostics=False)
                lcd_poll_seconds+=time.monotonic()-request_started
                polls+=1
                next_lcd=time.monotonic()+.2
            if poll_audio:
                request_started=time.monotonic()
                packet=emulator.audio()
                audio_poll_seconds+=time.monotonic()-request_started
                audio_pcm_chars+=len(packet['pcm'])
                audio_polls+=1
            time.sleep(.05 if poll_audio else .2)
        emulator.qmp.execute('stop')
        elapsed=time.monotonic()-started
        host_time_after = (read_thread_time(emulator.process.pid, time_tid)
                           if host_time_before is not None else None)
        host_profile = None
        if host_sampler is not None:
            host_profile = host_sampler.stop()
            host_sampler.close()
            active_host_samplers.remove(host_sampler)
            host_profile.update(pid=emulator.process.pid, tid=host_tid,
                maps=Path(f'/proc/{emulator.process.pid}/maps').read_text(),
                note='Software CPU-clock user IPs; sampling overhead present, not an uninstrumented speed result')
            assert host_profile['samples']
            assert all(s['pid'] == emulator.process.pid and s['tid'] == host_tid and
                       s['misc'] & 7 == 2 for s in host_profile['samples'])
        clock_after=clock_sample()
        profile_delta=None
        if args.profile_unknown_cycles:
            profile_after=json.loads(emulator.qmp.execute('qom-get', profile_property))
            emulator.qmp.execute('qom-set', {'path': '/machine',
                'property': 'instruction-clock-profile-enabled', 'value': profile_before['enabled']})
            before_ops=profile_before['opcodes']; after_ops=profile_after['opcodes']
            profile_delta={op: after_ops.get(op,0)-before_ops.get(op,0)
                           for op in set(before_ops)|set(after_ops)}
            assert all(count >= 0 for count in profile_delta.values()), profile_delta
        clock_delta={field: clock_after[field]-clock_before[field] for field in clock_before}
        assert all(value >= 0 for value in clock_delta.values()), (clock_before, clock_after)
        assert clock_delta['UNKNOWN_COST'] == clock_delta['UNKNOWN_SRAM'] + clock_delta['UNKNOWN_OPCODE'], clock_delta
        if profile_delta is not None:
            assert sum(profile_delta.values()) == clock_delta['UNKNOWN_OPCODE'], profile_delta
        cpu=emulator.qmp.execute('qom-get', {'path':'/machine','property':'cpu-state'})
        assert all(f'{field}=none' in cpu for field in ('ROM_MISSING','UNSUPPORTED','INVALID_CONTROL'))
        result=dict(label=label, host_seconds=elapsed, guest_seconds=clock_delta['NS']/1e9,
                    realtime_ratio=clock_delta['NS']/1e9/elapsed, lcd_polls=polls,
                    clock_before=clock_before, clock_after=clock_after,
                    guest_instructions=clock_delta['INSTRUCTIONS'],
                    guest_cycles=clock_delta['CYCLES'],
                    unknown_cost_instructions=clock_delta['UNKNOWN_COST'],
                    unknown_sram_instructions=clock_delta['UNKNOWN_SRAM'],
                    unknown_opcode_instructions=clock_delta['UNKNOWN_OPCODE'],
                    instructions_per_host_second=clock_delta['INSTRUCTIONS']/elapsed,
                    cycles_per_instruction=(clock_delta['CYCLES']/clock_delta['INSTRUCTIONS']
                                            if clock_delta['INSTRUCTIONS'] else None),
                    audio_polls=audio_polls, audio_poll_enabled=poll_audio,
                    audio_poll_seconds=audio_poll_seconds,
                    audio_pcm_base64_chars=audio_pcm_chars,
                    lcd_poll_seconds=lcd_poll_seconds)
        report.setdefault('speed_windows', []).append(result)
        if host_time_before is not None:
            result['host_cpu_time'] = thread_time_delta(host_time_before, host_time_after,
                                                       elapsed, clock_delta['INSTRUCTIONS'])
        if host_profile is not None:
            result['host_cpu_profile'] = host_profile
        if profile_delta is not None:
            result['unknown_opcode_profile']={op: count for op,count in
                sorted(profile_delta.items(), key=lambda item: (-item[1], item[0])) if count}
            result['profile_note']='instrumented opcode-family counts; not an uninstrumented performance window'
        if audio_before:
            audio_after=emulator.audio()
            if audio_capture is not None:
                audio_capture.checkpoint(audio_after)
            before, after = audio_before['request_clock'], audio_after['request_clock']
            result['audio_request_clock_before'] = dict(before)
            result['audio_request_clock_after'] = dict(after)
            # Bound the unpaused region in the actual DAC ring. A recording
            # may also include paused setup/diagnostic captures outside it.
            result['audio_generation_before'] = audio_before['generation']
            result['audio_generation_after'] = audio_after['generation']
            result['audio_first_frame'] = audio_before['next_frame']
            result['audio_next_frame'] = audio_after['next_frame']
            result['endpoint_audio_active'] = bool(audio_after['enabled'] and after['running'])
            # A false endpoint is not proof of a whole-window stop. The
            # duty-ratio and clock/control checks below still reject idle
            # windows and retain gaps as audio_continuous=false.
            assert before['hz'] == after['hz'] and before['pll'] == after['pll'], (
                'audio request clock changed during window', before, after)
            ticks=after['ticks']-before['ticks']
            expected_ticks=result['guest_seconds']*after['hz']
            result['audio_request_ticks']=ticks
            result['audio_request_hz']=after['hz']
            result['audio_request_duty_ratio']=ticks/expected_ticks
            result['audio_control_events']=audio_after['control_event_next']-audio_before['control_event_next']
            # The pinned short tone loops through the original stop/open/
            # reconfigure path, as observed before this optimization. Do not
            # mislabel it as continuous audio, or accept an idle-ended test.
            result['audio_continuous']=abs(ticks-expected_ticks) < 2+after['hz']*.01
            assert .90 < result['audio_request_duty_ratio'] < 1.01, result
            assert result['audio_continuous'] or result['audio_control_events'] > 0, result
            result['audio_playback_window']=True
        print('unpaused speed: '+json.dumps({k: v for k, v in result.items()
              if k != 'host_cpu_profile'}), flush=True)
        emulator.qmp.execute('cont')

    def arm_file_scan(frame,label):
        nonlocal watch
        # Called by capture while the owned guest is still QMP-stopped.
        report["file_scan_write_observer"]={**frame,"resolved_sample":label,
            "host_guest_memory_writes":0,"scope":"writer evidence, not timing"}
        watch=FileScanWatch(args.qemu,emulator.process.pid,frame["frame"],args.output)
        watch.ready()
        print(f"file scan hardware watch armed at {frame['frame']-2:04x}",flush=True)
    try:
        expected,_=expected_from_package(args.package)
        emulator=Emulator(qemu=args.qemu,firmware=args.firmware,soc_rom=args.soc_rom,
            rom_mp3_hle_base=args.rom_mp3_hle_base,
            rom_mp3_arena_image=args.rom_mp3_arena_image,
            icount_shift=args.icount_shift,
            icount_align=args.realtime,
            nand_checkpoint=args.nand_checkpoint,soc_rom_skeleton=True,
            boot_mode="firmware-vma03",start_paused=True,journal=journal)
        if args.instruction_clock:
            emulator.qmp.execute("qom-set",{"path":"/machine",
                "property":"instruction-clock","value":True})
        if args.observe_dtu_refill:
            emulator.qmp.execute("qom-set",{"path":"/machine","property":"dtu-refill-trace","value":True})
        if args.minimal_control_observers:
            emulator.qmp.execute("qom-set",{"path":"/machine",
                "property":"control-observers-minimal","value":True})
        if args.trace_volume_contacts:
            emulator.qmp.execute('qom-set', {'path': '/machine',
                'property': 'key-contact-trace-enabled', 'value': True})
            report['volume_contact_traces'] = []
        bridge=LocalBridge(emulator);emulator.qmp.execute("cont")
        print(f"owned PID={emulator.process.pid}; waiting for original desktop",flush=True)
        boot_started=time.monotonic()
        deadline=boot_started+150*args.host_timeout_scale;stable=0;next_progress=boot_started+15
        card_stable=0;card_dismissed=False
        while time.monotonic()<deadline:
            state=emulator.snapshot("lcd",0,0)
            if args.instruction_clock:
                report["boot_instruction_clock"]=emulator.qmp.execute("qom-get",
                    {"path":"/machine","property":"instruction-clock-state"})
                if "FAULT:0" not in report["boot_instruction_clock"]:
                    save_snapshot(args.output,"boot-clock-fault",state)
                    raise AssertionError(report["boot_instruction_clock"])
            assessment=assess(state,expected[1])
            stable=stable+1 if assessment["passed"] else 0
            if stable>=3: break
            if startup_card is not None and not card_dismissed:
                card_stable=card_stable+1 if (base64.b64decode(state["frame"])==startup_card and
                    all(assessment["diagnostic_checks"].values())) else 0
                if card_stable>=3 and emulator.key_status().get("matrix_rearmed",False):
                    save_snapshot(args.output,"00-startup-card",state)
                    print("exact startup card confirmed; physical Enter",flush=True)
                    report["startup_card_dismissal"]=replay_step(bridge,RouteStep("dismiss-startup-card",53,0x86),
                        press_timeout=10*args.host_timeout_scale,release_timeout=10*args.host_timeout_scale,
                        poll_interval=.05,settle=.8,pulse_duration=key_pulse_duration)
                    card_dismissed=True
            if time.monotonic()>=next_progress:
                irq=next((line.split(" REQUESTS:")[0] for line in state["registers"].splitlines()
                          if line.startswith("IRQ64=")),"")
                save_snapshot(args.output,"boot-latest",state)
                print(f"boot {time.monotonic()-boot_started:.1f}s {state['registers'].splitlines()[0]} {irq} "
                      f"toolbar mismatches={assessment['toolbar']['mismatch_pixels']}",flush=True)
                next_progress=time.monotonic()+15
            time.sleep(1)
        assert stable>=3,"desktop did not complete"
        capture("00-desktop")
        if args.wake_before_player:
            from probe_np560_clock_progress import power_clock_snapshot
            report['wake_before_player'] = {'before': power_clock_snapshot(emulator)}
            replay_step(bridge, RouteStep('screen-off',63,0x8f),
                press_timeout=30, release_timeout=30, poll_interval=.05,
                settle=1, pulse_duration=key_pulse_duration)
            deadline = time.monotonic() + 30 * args.host_timeout_scale
            while time.monotonic() < deadline:
                state = emulator.snapshot('lcd',0,0,diagnostics=False)
                if 'DISPLAY=off SLEEP=on' in state['lcd_state']:
                    break
                time.sleep(.1)
            else:
                raise TimeoutError('native screen-off did not finish')
            state = capture('00-screen-off')
            assert 'DISPLAY=off SLEEP=on' in state['lcd_state'], 'screen did not turn off'
            report['wake_before_player']['off'] = power_clock_snapshot(emulator)
            # This path polls GPIO rather than the normal key-event queue.
            # Hold the physical switch only until the original LCD wakes.
            emulator.set_key(0,0,matrix_low=0,matrix_high=1 << (61-32))
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    state = emulator.snapshot('lcd',0,0)
                    if 'DISPLAY=on SLEEP=off' in state['lcd_state']:
                        break
                    time.sleep(.05)
                else:
                    raise TimeoutError('native M61 wake did not enable LCD')
            finally:
                emulator.set_key(0,0,matrix_low=0,matrix_high=0)
            time.sleep(1)
            capture('00-woken')
            report['wake_before_player']['woken'] = power_clock_snapshot(emulator)
            replay_step(bridge,RouteStep('wake-return',4,0x8e),
                press_timeout=30,release_timeout=30,poll_interval=.05,
                settle=1,pulse_duration=key_pulse_duration)
            state = capture('00-wake-desktop')
            assert assess(state,expected[1])['passed'], 'wake did not return to desktop'
        if args.probe_key_durations:
            from probe_np560_key_duration import observe
            report['key_duration_probe'] = observe(bridge)
        speed_window('desktop')
        route=[("start",55,0xb0),("entertainment",53,0x86),("mp3",53,0x86),
               ("open-file",60,0xe2),("parent",53,0x86)]
        route += [(f"down-{i+1}",37,0x83) for i in range(args.tone_down_count)]
        route += [(f"up-{i+1}",61,0x82) for i in range(args.tone_up_count)]
        if args.selected_file_reference:
            reference = args.selected_file_reference.read_bytes()
            assert len(reference) == 240*120 and all(v <= 31 for v in reference)
            assert hashlib.sha256(reference).hexdigest() == args.selected_file_reference_sha256
            report['selected_file_reference'] = dict(path=str(args.selected_file_reference),
                sha256=args.selected_file_reference_sha256)
        else:
            assert not args.selected_file_reference_sha256, 'reference hash needs a reference file'
            reference_state=json.loads((Path(__file__).resolve().parents[1]/
                "tmp/np560-mp3-player-20260906-v1/with-tone/frames/09-root-bottom.json").read_text())
            # Only this historical reference predates gray5-darkness encoding.
            assert "ENCODING=" not in reference_state["lcd_state"] and "INV=on" in reference_state["lcd_state"]
            reference=bytes(31-v for v in base64.b64decode(reference_state["frame"]))
            report["legacy_tone_reference_conversion"]="31 - old gray5 light-level; guest unchanged"
        for label,index,event in route:
            print(f"route {label}",flush=True)
            report["route"].append(replay_step(bridge,RouteStep(label,index,event),
                press_timeout=10*args.host_timeout_scale,release_timeout=10*args.host_timeout_scale,poll_interval=.05,settle=.8,
                pulse_duration=key_pulse_duration))
            if label=="mp3":
                # This checkpoint initially shows the factory's transient
                # damaged-playlist notice. The menu ACK is not readiness.
                # Wait for the real F1/F2/F3/F4 strip, visually verified in
                # player-heap-v1/failure.png, without dismissing/injecting it.
                reference_player=json.loads((Path(__file__).resolve().parents[1]/
                    "tmp/np560-mp3-player-heap-20260907-v1/failure.json").read_text())
                target=base64.b64decode(reference_player["frame"])[:14*240]
                report["player_ready_strip_sha256"]=hashlib.sha256(target).hexdigest()
                assert report["player_ready_strip_sha256"]=="015e2d1685de842b69be403decc43797b9eaaa366182e5c1c970d0d684117e8a"
                deadline=time.monotonic()+30*args.host_timeout_scale;ready=0;rearmed=False
                while time.monotonic()<deadline:
                    frame=base64.b64decode(emulator.completed_frame()["frame"])
                    ready=ready+1 if frame[:14*240]==target else 0
                    rearmed=bool(emulator.key_status().get("matrix_rearmed",False))
                    if ready>=4 and rearmed: break
                    time.sleep(.25)
                assert ready>=4 and rearmed,"original player did not become ready"
                capture("01-player")
            if label=="parent": capture("02-root")
        state=capture("03-selected-tone")
        assert "ENCODING=gray5-darkness" in state["lcd_state"]
        frame=base64.b64decode(state["frame"])
        # Guard the selected filename row against accidentally opening a
        # different file. Compare actual LCD, not an inferred ACK or OCR.
        report['tone_selection']={'down_count':args.tone_down_count,'up_count':args.tone_up_count,'row_y':args.tone_row_y,
            'exact_reference_row_matched':False}
        assert frame[args.tone_row_y*240:(args.tone_row_y+13)*240]==reference[105*240:118*240],"selected tone row differs"
        report['tone_selection']['exact_reference_row_matched']=True
        if args.observe_input_writes:
            report["input_write_observer"]={"addresses":[0x1000,0x1452],"host_guest_memory_writes":0}
            emulator.qmp.execute("stop")
            try:
                watch=InputRingWatch(args.qemu,emulator.process.pid,args.output)
                watch.ready()
            finally: emulator.qmp.execute("cont")
            print("input ring hardware watches armed before selecting tone",flush=True)
        if args.record_device_audio and not args.audio_start_at_file_switch:
            audio_capture=DeviceAudioCapture(emulator,args.audio_seconds)
        try:
            replay_step(bridge,RouteStep("select-tone",53,0x86),press_timeout=15*args.host_timeout_scale,
                release_timeout=15*args.host_timeout_scale,poll_interval=.05,settle=1,pulse_duration=key_pulse_duration)
        except RuntimeError as error: report["entry_observation"]=str(error)
        if args.initial_volume_up:
            report['initial_volume_route'] = []
            for n in range(args.initial_volume_up):
                try:
                    report['initial_volume_route'].append(replay_step(
                        bridge,RouteStep(f'initial-volume-{n+1}',61,0x82),
                        press_timeout=45,release_timeout=45,poll_interval=.05,
                        settle=args.initial_volume_settle_ms / 1000,pulse_duration=key_pulse_duration,
                        observe_contact_bounds=args.observe_volume_contact_bounds))
                finally:
                    if args.trace_volume_contacts:
                        # replay_step releases even on failure. Never add a
                        # status read while this physical pulse is held.
                        try:
                            trace = json.loads(emulator.qmp.execute('qom-get', {
                                'path': '/machine', 'property': 'key-contact-trace'}))
                        except Exception as trace_error:
                            trace = {'error': str(trace_error)}
                        report['volume_contact_traces'].append(
                            dict(attempt=n+1, trace=trace))
        state=capture("04-mp3-init")
        if args.observe_native_codec:
            # This is a bounded observation of the same live process, not a
            # timeout-triggered restart. Passing means native owner + real
            # output observed, NOT full initialization or audible playback.
            for i in range(args.codec_observations):
                if any(field+"=none" not in state["registers"] for field in
                       ("ROM_MISSING","UNSUPPORTED","INVALID_CONTROL")): break
                sample=report["native_codec_samples"]["04-mp3-init" if i==0 else f"05-codec-{i}"]
                if any(o["session_initialized"] and o["ready"]==1 and o["lease_handle"] for o in sample["owners"]) and sample["pcm_nonzero_values"]:
                    report["native_owner_and_pcm_observed"]=True
                    report.setdefault("first_native_owner_and_pcm_sample",i)
                time.sleep(5);state=capture(f"05-codec-{i+1}")
            assert "ROM_MISSING=none" in state["registers"],state["registers"].splitlines()[0]
            assert report.get("native_owner_and_pcm_observed"),"no initialized native owner and PCM observed within window"
            if args.compare_audio_poll:
                for poll_audio in (False, True, True, False):
                    speed_window('player', audio_poll_override=poll_audio)
            else:
                speed_window('player')
            if args.profile_audio_reopen:
                # This runs outside speed windows. Bracket each CPU read with
                # actual DAC events; a sample crossing re-enable is labelled,
                # not silently assigned to the closed interval.
                episodes=[]
                episode=None
                was_active=False
                deadline=time.monotonic()+args.profile_audio_reopen_seconds
                while time.monotonic()<deadline and len(episodes)<3:
                    before=emulator.audio()
                    if before['enabled']:
                        was_active=True
                        if episode is not None:
                            episode['on_packet']=before
                            episodes.append(episode)
                            episode=None
                    elif was_active:
                        if episode is None:
                            episode=dict(off_packet=before,samples=[])
                        cpu_sample=emulator.qmp.execute('qom-get',{'path':'/machine','property':'cpu-state'})
                        # Reuse the explicit paused-stack diagnostic for one
                        # post-stop worker snapshot as well. A PC sampled while
                        # running is only a trigger; recheck the closed device
                        # and the instruction after stopping before reading RAM.
                        if (args.profile_audio_reopen_stack and
                                'work_stack' not in episode and
                                any(e.get('pc') == 0x08330a and
                                    e.get('frame', -1) >= episode['off_packet']['next_frame']
                                    for e in before.get('control_events', [])) and
                                not any(pc in cpu_sample for pc in
                                        ('PC=08:47fa', 'PC=08:47fe'))):
                            emulator.qmp.execute('stop')
                            try:
                                work_cpu=emulator.qmp.execute('qom-get',{
                                    'path':'/machine','property':'cpu-state'})
                                work_audio=emulator.audio()
                                if (not work_audio['enabled'] and
                                        work_audio['generation'] == before['generation'] and
                                        not any(pc in work_cpu for pc in
                                                ('PC=08:47fa', 'PC=08:47fe'))):
                                    sp=int(re.search(r'\bR15\s*=([0-9a-f]+)',work_cpu,re.I)[1],16)
                                    if sp % 2 == 0 and 0xb00 <= sp < 0x1000:
                                        stack=emulator.snapshot('data',sp,min(256,0x1000-sp))
                                        episode['work_stack']=dict(sp=sp,
                                            cpu=work_cpu.splitlines()[:6],
                                            trigger_cpu=cpu_sample.splitlines()[0],
                                            frame=work_audio['next_frame'],
                                            generation=work_audio['generation'],
                                            data=stack['frame'],paused=True,
                                            host_guest_memory_writes=0)
                            finally:
                                emulator.qmp.execute('cont')
                        if (args.profile_audio_reopen_stack and 'stack' not in episode
                                and 'PC=08:47fe' in cpu_sample):
                            emulator.qmp.execute('stop')
                            try:
                                paused_cpu=emulator.qmp.execute('qom-get',{
                                    'path':'/machine','property':'cpu-state'})
                                paused_audio=emulator.audio()
                                if (not paused_audio['enabled'] and
                                        any(pc in paused_cpu for pc in ('PC=08:47fa', 'PC=08:47fe'))):
                                    sp=int(re.search(r'\bR15\s*=([0-9a-f]+)',paused_cpu,re.I)[1],16)
                                    assert sp % 2 == 0 and sp + 96 <= 0x10000
                                    stack=emulator.snapshot('data',sp,96)
                                    flags=emulator.snapshot('data',0xf010,8)
                                    episode['stack']=dict(sp=sp,cpu=paused_cpu.splitlines()[:6],
                                        trigger_cpu=cpu_sample.splitlines()[0],
                                        frame=paused_audio['next_frame'],generation=paused_audio['generation'],
                                        data=stack['frame'],flags_f010=flags['frame'],
                                        paused=True,host_guest_memory_writes=0)
                            finally:
                                emulator.qmp.execute('cont')
                        after=emulator.audio()
                        episode['samples'].append(dict(
                            before_frame=before['next_frame'],after_frame=after['next_frame'],
                            generation=before['generation'],after_generation=after['generation'],
                            enabled_after=after['enabled'],
                            state=cpu_sample.splitlines()[:4]))
                    time.sleep(.005)
                if episode is not None:
                    episode['incomplete']=True
                    episodes.append(episode)
                # Do not retain redundant base64 PCM in a PC diagnostic.
                for item in episodes:
                    for key in ('off_packet','on_packet'):
                        if key in item: item[key].pop('pcm',None)
                report['audio_reopen_profile']=dict(episodes=episodes,
                    observation_limit_seconds=args.profile_audio_reopen_seconds,
                    host_guest_memory_writes=0, debugger_used=False,
                    paused_stack_sampling=args.profile_audio_reopen_stack,
                    post_stop_work_stacks=sum('work_stack' in e for e in episodes),
                    caveat='QMP sampling perturbs host load; PC reads are not instruction traces or speed evidence')
                assert episodes,'no DAC close/reopen observed in bounded profile'
                if args.profile_audio_reopen_stack:
                    assert len(episodes)==3 and all('stack' in e and not e.get('incomplete')
                        for e in episodes),'three complete coherent waiter stacks were not captured'
            if args.profile_player:
                report['player_profile']=f'{args.profile_samples} debugger samples AFTER timing windows; not timing evidence'
                for sample in range(args.profile_samples):
                    trace=subprocess.run(['gdb','-q','-nx','-batch','-p',str(emulator.process.pid),
                        '-ex','set pagination off','-ex','thread apply all bt 8','-ex','detach'],
                        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=15)
                    (args.output/f'player-profile-{sample:02}.txt').write_text(trace.stdout)
                    assert trace.returncode==0,trace.stdout
                    time.sleep(.25)
            if args.observe_play_controls or args.observe_volume_controls:
                if args.play_controls_volume_up:
                    report['play_controls_volume_route'] = []
                    for n in range(args.play_controls_volume_up):
                        report['play_controls_volume_route'].append(replay_step(
                            bridge, RouteStep(f'transport-volume-{n+1}',61,0x82),
                            press_timeout=45,release_timeout=45,poll_interval=.05,
                            settle=.3,pulse_duration=key_pulse_duration))
                if args.observe_state_writes:
                    import build_np560_mp3_session as session
                    sample=report["native_codec_samples"][f"05-codec-{args.codec_observations}"]
                    assert len(sample["owners"])==1
                    addresses={"player_state":sample["player"]["address"]+0x087c,
                               "codec_ready":sample["owners"][0]["node"]["address"]+6+session.READY}
                    report["state_write_observer"]={"addresses":addresses,
                        "volume_current_target_internal_sram":args.observe_volume_controls,
                        "end_flags_internal_sram":args.observe_end_writes,
                        "host_guest_memory_writes":0,"scope":"write callers during physical controls, not timing"}
                    emulator.qmp.execute("stop")
                    try:
                        watch=PlayerStateWatch(args.qemu,emulator.process.pid,addresses,args.output,
                                               observe_end=args.observe_end_writes,
                                               observe_volume=args.observe_volume_controls)
                        watch.ready()
                    finally: emulator.qmp.execute("cont")
                    print("player state/READY hardware watches armed",flush=True)
                # These are letters from the original player's visible
                # controls. The original dispatcher converts them to 0092
                # (state-dependent Play/Pause) or 0091 (Stop); never inject
                # those logical commands or overwrite the state gate.
                controls = [("play",1,0x64,6),("pause",9,0x66,3),
                            ("resume",1,0x64,6),("stop",17,0x67,3)]
                if args.observe_seek_controls:
                    controls = [('forward',25,0x68,2),('rewind',18,0x73,2)]
                    report['seek_controls_observed'] = True
                    if args.observe_seek_reload_writes:
                        from observe_np560_seek_reload import SeekReloadWatch
                        report['seek_write_observer'] = {
                            'host_guest_memory_writes': 0,
                            'scope': 'original stream/frame writes; debugger stops, not timing'}
                        emulator.qmp.execute('stop')
                        try:
                            watch = SeekReloadWatch(args.qemu, emulator.process.pid, args.output)
                            watch.ready()
                        finally:
                            emulator.qmp.execute('cont')
                        print('seek reload hardware watches armed', flush=True)
                if args.observe_volume_controls:
                    # Original 0D:4D76/4E96 consumes Up82/Down83 and calls
                    # 08:3324. No direct writes to volume or PCM are allowed.
                    directions = {'down': (37,0x83), 'up': (61,0x82)}
                    controls = [(f"volume-{direction}-{n}", *directions[direction], 1)
                                for direction in args.volume_sweep_order.split('-')
                                for n in range(1,8)]
                    report["observe_volume_controls"] = True
                    report["volume_sweep_order"] = args.volume_sweep_order
                for action,index,event,samples in controls:
                    label=f"06-{action}"
                    capture(label+"-before")
                    print(f"physical control {action}: matrix {index}",flush=True)
                    observation={"action":action,"matrix_index":index,"event":event}
                    report["control_observations"].append(observation)
                    try:
                        observation["delivery"]=replay_step(bridge,RouteStep(label,index,event),
                            press_timeout=45,release_timeout=45,poll_interval=.1,
                            settle=1,pulse_duration=key_pulse_duration)
                    except (RuntimeError,TimeoutError) as error:
                        observation["error"]=str(error)
                        capture(label+"-delivery-failure")
                        raise
                    state=capture(label+"-delivered")
                    for i in range(samples):
                        assert all(field+"=none" in state["registers"] for field in
                                   ("ROM_MISSING","UNSUPPORTED","INVALID_CONTROL"))
                        # LONG22 is 20 seconds. Two 5-second forward windows
                        # can reach EOF before rewind and invalidate its gate.
                        # Seek diagnostics need short settled windows; other
                        # transport tests retain their 5-second observations.
                        time.sleep(1 if args.observe_seek_controls else 5)
                        state=capture(f"{label}-{i+1}")
                if args.observe_play_controls and not args.observe_volume_controls and not args.observe_seek_controls:
                    report['transport_validation'] = validate_transport_samples(
                        report['native_codec_samples'])
                if args.observe_seek_controls:
                    report['seek_observation_interval_seconds'] = 1
                    report['seek_playback_resumed'] = {}
                    report['seek_position_changed'] = {}
                    report['seek_codec_failures'] = {}
                    for action in ('forward', 'rewind'):
                        points = [report['native_codec_samples'][f'06-{action}-{i}'] for i in (1, 2)]
                        report['seek_codec_failures'][action] = {
                            field: points[-1]['rom_mp3_hle'][field] for field in
                            ('failures','input_space_failures','pcm_copy_failures','final_frame_failures')}
                        report['seek_playback_resumed'][action] = (
                            all(point['device_audio']['enabled'] for point in points) and
                            points[1]['rom_mp3_hle']['frames'] > points[0]['rom_mp3_hle']['frames'])
                        before = report['native_codec_samples'][f'06-{action}-before']['player']['position_ms_0806']
                        after = report['native_codec_samples'][f'06-{action}-delivered']['player']['position_ms_0806']
                        report['seek_position_changed'][action] = dict(before_ms=before,after_ms=after,
                            direction_matches=(after > before if action == 'forward' else after < before))
                    assert all(report['seek_playback_resumed'].values()), 'seek did not resume DAC/decode; inspect original release/commit path'
                    assert all(value['direction_matches'] for value in report['seek_position_changed'].values()), 'seek playback continued but position did not change in requested direction'
                    # Pinned no-Info LONG22: MPEG2 mono 48 kb/s, 156/157-byte
                    # frames, 4-byte header + 9-byte sideinfo, at least 143
                    # history bytes/frame. ceil(255 / 143) = 2. Other fixtures
                    # retain zero tolerance until independently characterized.
                    bound = 2 if args.expected_nand_sha256.lower() == 'f0b40254f19510be15b85e02c9f212627137bcf16d136ad69ad506fe2e4f55c8' else 0
                    report['seek_history_validation'] = {}
                    for action in ('forward','rewind'):
                        report['seek_history_validation'][action] = validate_seek_history(
                            report['native_codec_samples'][f'06-{action}-before']['rom_mp3_hle'],
                            report['native_codec_samples'][f'06-{action}-2']['rom_mp3_hle'], bound)
                if watch is not None and not args.observe_seek_reload_writes:
                    assert "STATE_WRITE name=" in watch.text(),"no observed player/READY changes"
            if args.observe_player_back or args.observe_player_minimize:
                if args.minimize_with_eq:
                    report['minimize_eq_route'] = []
                    steps = [('volume-'+str(i),61,0x82) for i in range(7)]
                    steps += [('settings',44,0xea),('down1',37,0x83),
                              ('down2',37,0x83),('modes',53,0x86),
                              ('treble',37,0x83),('confirm',53,0x86),('back',4,0x8e)]
                    for name,index,event in steps:
                        report['minimize_eq_route'].append(replay_step(
                            bridge,RouteStep('minimize-eq-'+name,index,event),
                            press_timeout=45,release_timeout=45,poll_interval=.1,
                            settle=.3,pulse_duration=key_pulse_duration))
                    capture('07-eq-start')
                    time.sleep(5)
                    capture('07-eq-end')
                    eq = report['native_codec_samples']['07-eq-end']['rom_mp3_hle']
                    assert eq['version'] == 8 and eq['audio_mode']['enabled'], eq
                    assert not (eq['failures'] or eq['pcm_copy_failures'] or eq['audio_mode']['failures'])
                action,index,event=("minimize",4,0x8e) if args.observe_player_minimize else ("back",28,0x84)
                label="07-"+action
                capture(label+"-before")
                if args.observe_exit_heap_writes:
                    sample=report['native_codec_samples'][label+'-before']
                    assert sample['player']['allocation_live'] and len(sample['owners'])==1
                    addresses={'player_heap_header':sample['player']['address']-6,
                               'codec_heap_header':sample['owners'][0]['node']['address']}
                    report['state_write_observer']={'addresses':addresses,
                        'host_guest_memory_writes':0,'scope':'actual heap invalidation callers, not timing'}
                    emulator.qmp.execute('stop')
                    try:
                        watch=PlayerStateWatch(args.qemu,emulator.process.pid,addresses,args.output)
                        watch.ready()
                    finally: emulator.qmp.execute('cont')
                print(f"physical player {action}: matrix {index}", flush=True)
                report["player_"+action+"_delivery"] = replay_step(
                    bridge, RouteStep("player-"+action,index,event),
                    press_timeout=45,release_timeout=45,poll_interval=.1,
                    settle=1,pulse_duration=key_pulse_duration)
                state=capture(label+"-delivered")
                for i in range(3):
                    assert all(field+"=none" in state["registers"] for field in
                               ("ROM_MISSING","UNSUPPORTED","INVALID_CONTROL"))
                    time.sleep(5);state=capture(f"{label}-{i+1}")
                if args.reopen_after_minimize:
                    first=report['native_codec_samples'][label+'-3']
                    assert first['rom_mp3_hle']['sessions']==0,'first exit retained HLE session'
                    assert not first['owners'],'first exit retained codec owner'
                    steps=[('reopen-player',53,0x86),('open-file',60,0xe2),('parent',53,0x86)]
                    steps += [(f'down-{i+1}',37,0x83) for i in range(args.tone_down_count)]
                    steps += [(f'up-{i+1}',61,0x82) for i in range(args.tone_up_count)]
                    steps += [('select-tone',53,0x86)]
                    report['reopen_route']=[]
                    for name,index,event in steps:
                        print('reopen route '+name,flush=True)
                        report['reopen_route'].append(replay_step(bridge,RouteStep('reopen-'+name,index,event),
                            press_timeout=45,release_timeout=45,poll_interval=.1,
                            settle=.3,pulse_duration=key_pulse_duration))
                        if name in ('reopen-player','parent','select-tone'):
                            capture('08-'+name)
                    for i in range(3):
                        time.sleep(5);state=capture(f'08-play-{i+1}')
                    second=report['native_codec_samples']['08-play-3']
                    assert second['rom_mp3_hle']['sessions']==1 and second['owners']
                    assert second['rom_mp3_hle']['frames']>first['rom_mp3_hle']['frames']
                    if args.minimize_with_eq:
                        report['eq_enabled_after_reopen'] = second['rom_mp3_hle']['audio_mode']['enabled']
                        assert not second['rom_mp3_hle']['pcm_copy_failures']
                        assert not second['rom_mp3_hle']['audio_mode']['failures']
                    report['second_minimize_delivery']=replay_step(bridge,RouteStep('second-minimize',4,0x8e),
                        press_timeout=45,release_timeout=45,poll_interval=.1,
                        settle=1,pulse_duration=key_pulse_duration)
                    for i in range(3):
                        time.sleep(5);state=capture(f'09-exit-{i+1}')
                    last=report['native_codec_samples']['09-exit-3']
                    assert last['rom_mp3_hle']['sessions']==0 and not last['owners']
                    assert last['rom_mp3_hle']['failures']==0 and not last['device_audio']['enabled']
                    report['same_process_reopen_release_verified']=True
        else:
            assert "ROM_MISSING=01:4804" in state["registers"],state["registers"].splitlines()[0]
        if args.inspect_audio_modes:
            report['audio_mode_route'] = []
            for contact in range(args.audio_mode_volume_up):
                report['audio_mode_route'].append(replay_step(bridge,
                    RouteStep('mode-volume-up-'+str(contact+1),61,0x82),
                    press_timeout=45,release_timeout=45,poll_interval=.05,
                    settle=.5,pulse_duration=key_pulse_duration))
            capture('10-normal-start')
            time.sleep(5)
            capture('10-normal-end')
            for name, index, event in (('settings',44,0xea),('settings-down-1',37,0x83),
                    ('settings-down-2',37,0x83),('audio-menu',53,0x86),
                    ('audio-next',37,0x83),('audio-select',53,0x86)):
                report['audio_mode_route'].append(replay_step(bridge,RouteStep(name,index,event),
                    press_timeout=45,release_timeout=45,poll_interval=.05,
                    settle=.5,pulse_duration=key_pulse_duration))
                capture('10-'+name)
            time.sleep(5)
            capture('10-audio-selected-running')
            # Still in settings, with audio-mode item selected. Re-enter the
            # three-column grid, Up from index 3 to 0, confirm normal mode.
            for name, index, event in (('audio-reenter',53,0x86),
                    ('audio-normal',61,0x82),('normal-restored-start',53,0x86)):
                report['audio_mode_route'].append(replay_step(bridge,RouteStep(name,index,event),
                    press_timeout=45,release_timeout=45,poll_interval=.05,
                    settle=.5,pulse_duration=key_pulse_duration))
                capture('10-'+name)
            time.sleep(5)
            capture('10-normal-restored-end')
            if args.sweep_audio_modes:
                from analyze_np560_audio_modes import extract
                expected = extract(args.firmware.read_bytes())['menu_rows']
                report['audio_mode_sweep'] = []
                # Snake through the three-column grid without assuming that
                # Right wraps at the row edge or into the missing last cell.
                steps = [(0,53,0x86),(1,29,0x81),(2,29,0x81),(5,37,0x83),
                         (4,45,0x80),(3,45,0x80),(6,37,0x83),(7,29,0x81),
                         (8,29,0x81),(11,37,0x83),(10,45,0x80),(9,45,0x80),
                         (12,37,0x83),(13,29,0x81)]
                for selection, index, event in steps:
                    label = '11-audio-mode-'+str(selection)
                    delivery = replay_step(bridge,RouteStep(label,index,event),
                        press_timeout=45,release_timeout=45,poll_interval=.05,
                        settle=1,pulse_duration=key_pulse_duration)
                    capture(label)
                    sample = report['native_codec_samples'][label]
                    hle = sample['rom_mp3_hle']
                    mode = hle['audio_mode']
                    item = dict(selection=selection,delivery=delivery,
                                actual_selection=sample['player']['selection_087b'],
                                mode=mode,frames=hle['frames'])
                    report['audio_mode_sweep'].append(item)
                    assert sample['player']['mode_087a'] == 10, item
                    assert item['actual_selection'] == selection, item
                    assert mode['coefficients'] == expected[selection]['coefficient_words'], item
                    assert mode['enabled'] == expected[selection]['enabled'], item
                    assert not (mode['failures'] or hle['failures'] or hle['pcm_copy_failures']), item
        if args.inspect_player_files:
            for i in range(args.file_switch_volume_up):
                replay_step(bridge,RouteStep('file-volume-up-'+str(i+1),61,0x82),
                    press_timeout=45,release_timeout=45,poll_interval=.05,
                    settle=.5,pulse_duration=key_pulse_duration)
            capture('09-file-switch-source')
            if args.file_switch_eq:
                for name, index, event in (('settings',44,0xea),('down1',37,0x83),
                        ('down2',37,0x83),('modes',53,0x86),('treble',37,0x83),
                        ('confirm',53,0x86),('back',4,0x8e)):
                    replay_step(bridge,RouteStep('switch-eq-'+name,index,event),
                        press_timeout=45,release_timeout=45,poll_interval=.05,
                        settle=.5,pulse_duration=key_pulse_duration)
                    capture('09-switch-eq-'+name)
                sample = report['native_codec_samples']['09-switch-eq-back']
                assert sample['player']['mode_087a'] == 5, 'EQ route did not return to player'
                assert sample['rom_mp3_hle']['audio_mode']['enabled'], 'EQ not enabled'
            if args.stop_before_file_picker:
                report['stop_before_file_picker']={'delivery':replay_step(
                    bridge,RouteStep('stop-before-picker',17,0x67),
                    press_timeout=45,release_timeout=45,poll_interval=.1,
                    settle=1,pulse_duration=key_pulse_duration)}
                for i in range(2):
                    time.sleep(2)
                    state=capture(f'09-stop-before-picker-{i+1}')
                sample=report['native_codec_samples']['09-stop-before-picker-2']
                before=report['native_codec_samples']['09-stop-before-picker-1']
                report['stop_before_file_picker']['dac_disabled']=not sample['device_audio']['enabled']
                assert report['stop_before_file_picker']['dac_disabled'],'physical Stop did not disable DAC'
                stable=all(before['rom_mp3_hle'][key]==sample['rom_mp3_hle'][key]
                           for key in ('frames','granules'))
                report['stop_before_file_picker']['decode_counters_stable']=stable
                assert stable and not before['device_audio']['enabled'],'Stop did not remain inactive across observations'
            report['file_picker_inspection'] = {'selection_performed': False}
            report['file_picker_inspection']['delivery'] = replay_step(
                bridge,RouteStep('inspect-file-picker',60,0xe2),
                press_timeout=45,release_timeout=45,poll_interval=.1,
                settle=1,pulse_duration=key_pulse_duration)
            state=capture('10-file-picker-reopened')
            time.sleep(1)
            state=capture('10-file-picker-settled')
            if mono_row is not None:
                report['mono_switch']={'route':[],'selected_row_verified':False,
                                       'audio_correctness_verified':False}
                steps=[('mono-parent',53,0x86)]
                report['mono_switch']['target_path'] = switch_path.decode('ascii')
                steps += [(f'mono-down-{i+1}',37,0x83) for i in range(switch_down_count)]
                steps += [(f'target-up-{i+1}',61,0x82) for i in range(args.file_switch_up_count)]
                report['mono_switch']['target_row_y'] = args.file_switch_row_y
                for name,index,event in steps:
                    print('switch route '+name,flush=True)
                    report['mono_switch']['route'].append(replay_step(
                        bridge,RouteStep(name,index,event),press_timeout=45,
                        release_timeout=45,poll_interval=.1,settle=.3,
                        pulse_duration=key_pulse_duration))
                state=capture('11-selected-mono')
                row_y = args.file_switch_row_y
                assert base64.b64decode(state['frame'])[row_y*240:(row_y+13)*240]==mono_row,'selected mono row differs'
                report['mono_switch']['selected_row_verified']=True
                if args.trace_player_redraw:
                    emulator.qmp.execute('stop')
                    try:
                        emulator.qmp.execute('qom-set', {'path':'/machine',
                            'property':'resource-trace-all','value':True})
                        emulator.qmp.execute('qom-set', {'path':'/machine',
                            'property':'control-observers-minimal','value':False})
                    finally:
                        emulator.qmp.execute('cont')
                    report['redraw_observation']={'enabled_before':'select-mono',
                        'timing_evidence':False,'host_guest_memory_writes':0}
                    # Full observers can run slower than real time. Hold the
                    # diagnostic contact until the original scanner accepts
                    # it; a 150 ms host pulse can disappear between scans.
                    key_pulse_duration = None
                    report['redraw_observation']['key_release'] = 'candidate'
                if args.audio_start_at_file_switch:
                    assert audio_capture is None
                    audio_capture = DeviceAudioCapture(emulator, args.audio_seconds)
                    report['mono_switch']['device_capture_start'] = 'before target confirmation'
                report['mono_switch']['delivery']=replay_step(
                    bridge,RouteStep('select-mono',53,0x86),press_timeout=45,
                    release_timeout=45,poll_interval=.1,settle=1,
                    pulse_duration=key_pulse_duration)
                for i in range(3):
                    time.sleep(2)
                    state=capture(f'12-mono-{i+1}')
                    assert all(field+'=none' in state['registers'] for field in
                               ('ROM_MISSING','UNSUPPORTED','INVALID_CONTROL'))
                # F1 may append a track rather than make it current. Keep
                # channel evidence, but do not falsely require immediate
                # mono playback until the actual playlist selection occurs.
                channel_state=struct.unpack('<H',base64.b64decode(
                    emulator.snapshot('data',0xf006,2)['frame']))[0]
                report['mono_switch']['final_channel_state']=channel_state
                report['mono_switch']['mono_channel_state_verified']=not bool(channel_state&0x0800)
                report['mono_switch']['immediate_playback_required']=False
                report['mono_switch']['playlist_delivery']=replay_step(
                    bridge,RouteStep('inspect-mono-playlist',52,0xe1),
                    press_timeout=45,release_timeout=45,poll_interval=.1,
                    settle=1,pulse_duration=key_pulse_duration)
                state=capture('13-playlist-after-add')
                if args.play_mono_from_list:
                    if args.watch_playlist_index:
                        player_address=report['native_codec_samples']['13-playlist-after-add']['player']['address']
                        addresses={'playlist_active_index':player_address+0x868,
                                   'playlist_active_path':player_address+0x980}
                        report['state_write_observer']={'addresses':addresses,
                            'host_guest_memory_writes':0,'scope':'playlist index/path writers; not timing'}
                        emulator.qmp.execute('stop')
                        try:
                            for label,addr,size in (('playlist-getter',0x33384e,0x22),
                                    ('playlist-confirm',0x0ea522,0x110),('playlist-path-index',0x326868,0x6c)):
                                code=base64.b64decode(emulator.snapshot('code',addr,size)['frame'])
                                (args.output/(label+'.code.bin')).write_bytes(code)
                            watch=PlayerStateWatch(args.qemu,emulator.process.pid,addresses,args.output)
                            watch.ready()
                        finally: emulator.qmp.execute('cont')
                    report['mono_switch']['play_route']=[]
                    for name,index,event in (('playlist-next',37,0x83),('playlist-play',53,0x86)):
                        report['mono_switch']['play_route'].append(replay_step(
                            bridge,RouteStep(name,index,event),press_timeout=45,
                            release_timeout=45,poll_interval=.1,settle=1,
                            pulse_duration=key_pulse_duration))
                        state=capture('14-'+name)
                    for i in range(3):
                        time.sleep(2)
                        state=capture(f'15-mono-playing-{i+1}')
                        assert all(field+'=none' in state['registers'] for field in
                                   ('ROM_MISSING','UNSUPPORTED','INVALID_CONTROL'))
                    sample=report['native_codec_samples']['15-mono-playing-3']
                    player_address=sample['player']['address']
                    raw=base64.b64decode(emulator.snapshot('data',player_address+0x097c,256)['frame'])
                    (args.output/'15-active-path.bin').write_bytes(raw)
                    logical=bytearray(raw);logical[::2]=raw[1::2];logical[1::2]=raw[::2]
                    active=bytes(logical[1:]).split(b'\0',1)[0]
                    report['mono_switch']['active_path']=active.decode('ascii',errors='replace')
                    report['mono_switch']['final_path_is_mono']=active.upper()==switch_path
                    # The 0.63-second mono fixture can finish before this
                    # periodic snapshot and advance to another playlist item.
                    # A final path alone cannot prove or disprove selection.
                    channel_state=struct.unpack('<H',base64.b64decode(
                        emulator.snapshot('data',0xf006,2)['frame']))[0]
                    report['mono_switch']['selected_channel_state']=channel_state
                    report['mono_switch']['final_channel_is_mono']=not bool(channel_state&0x0800)
                    if args.return_stereo_from_list:
                        for name,index,event in (('list',52,0xe1),('previous',61,0x82),
                                                 ('play',53,0x86)):
                            replay_step(bridge,RouteStep('return-stereo-'+name,index,event),
                                press_timeout=45,release_timeout=45,poll_interval=.05,
                                settle=.2,pulse_duration=key_pulse_duration)
                            capture('16-return-stereo-'+name)
                        time.sleep(.5)
                        capture('16-return-stereo-running')
                        sample=report['native_codec_samples']['16-return-stereo-running']
                        raw=base64.b64decode(emulator.snapshot('data',
                            sample['player']['address']+0x097c,256)['frame'])
                        logical=bytearray(raw);logical[::2]=raw[1::2];logical[1::2]=raw[::2]
                        active=bytes(logical[1:]).split(b'\0',1)[0]
                        report['stereo_return']={'active_path':active.decode('ascii',errors='replace')}
                        assert active.upper()==b'0:\\TONE440.MP3', report['stereo_return']
                        assert sample['device_audio']['request_clock']['hz'] == 44084
                        hle=sample['rom_mp3_hle']
                        assert not (hle['failures'] or hle['pcm_copy_failures'] or hle['audio_mode']['failures'])
                        if args.file_switch_eq:
                            assert hle['audio_mode']['enabled'], 'EQ lost across file switch'
        if args.observe_ab_repeat or args.observe_player_blank:
            report['ab_volume_route'] = []
            for index in range(args.play_controls_volume_up):
                report['ab_volume_route'].append(replay_step(bridge,
                    RouteStep(f'ab-volume-up-{index+1}',61,0x82),
                    press_timeout=45,release_timeout=45,poll_interval=.1,
                    settle=.3,pulse_duration=key_pulse_duration))
        if args.observe_player_blank:
            before=capture('30-before-blank')
            report['blank_deliveries']=[]
            for name in ('31-blank','32-restored'):
                report['blank_deliveries'].append(replay_step(bridge,RouteStep(name,30,0x62),
                    press_timeout=45,release_timeout=45,poll_interval=.1,
                    settle=.5,pulse_duration=key_pulse_duration))
                capture(name+'-start')
                time.sleep(2)
                state=capture(name+'-end')
                first=report['native_codec_samples'][name+'-start']
                last=report['native_codec_samples'][name+'-end']
                assert last['device_audio']['enabled'], 'B action disabled DAC'
                assert last['rom_mp3_hle']['frames'] > first['rom_mp3_hle']['frames'], 'B action stopped decoding'
            blank=(args.output/'31-blank-end.gray5').read_bytes()
            restored=(args.output/'32-restored-end.gray5').read_bytes()
            original=(args.output/'30-before-blank.gray5').read_bytes()
            report['blank_display_observation']=dict(blank_levels=sorted(set(blank)),
                restored_header_equal=restored[:240*16]==original[:240*16],
                device_pcm_verified=False)
            assert len(set(blank))==1, 'original B did not produce a uniform screen'
            assert restored[:240*16]==original[:240*16], 'original B did not restore player header'
        if args.observe_ab_repeat:
            repeat = report['ab_repeat_observation'] = {
                'scope': 'original matrix route and playback position; not browser listening or all-format acceptance',
                'deliveries': [], 'positions_ms': [], 'wraps': 0,
            }
            def repeat_key(name):
                repeat['deliveries'].append(replay_step(bridge,RouteStep(name,54,0x20),
                    press_timeout=45,release_timeout=45,poll_interval=.1,
                    settle=.2,pulse_duration=key_pulse_duration))
                capture(name)
                return report['native_codec_samples'][name]
            a = repeat_key('24-repeat-A')
            time.sleep(2)
            b = repeat_key('25-repeat-B')
            repeat['a_observed_ms'] = a['player']['position_ms_0806']
            # B activates an immediate rewind: this is the position AFTER
            # pressing B, not the stored loop-end boundary.
            repeat['b_observed_ms'] = b['player']['position_ms_0806']
            previous = repeat['b_observed_ms']
            for index in range(10):
                time.sleep(.75)
                label=f'26-repeat-{index}'
                state=capture(label)
                sample=report['native_codec_samples'][label]
                position=sample['player']['position_ms_0806']
                assert sample['device_audio']['enabled'], 'DAC inactive during repeat'
                repeat['positions_ms'].append(position)
                if position < previous - 500:
                    repeat['wraps'] += 1
                previous=position
            canceled=repeat_key('27-repeat-cancel')
            time.sleep(4)
            state=capture('28-repeat-canceled-progress')
            after=report['native_codec_samples']['28-repeat-canceled-progress']
            repeat['cancel_position_ms']=canceled['player']['position_ms_0806']
            repeat['after_cancel_position_ms']=after['player']['position_ms_0806']
            assert repeat['wraps'] >= 2, 'A-B did not produce two observed position wraps'
            assert repeat['after_cancel_position_ms'] > max(repeat['positions_ms']) + 1000, 'third Space did not continue beyond observed loop range'
            assert repeat['after_cancel_position_ms'] > repeat['cancel_position_ms'] + 3000, 'playback did not advance through cancellation window'
            assert after['device_audio']['enabled'], 'DAC inactive after repeat cancellation'
            assert after['rom_mp3_hle']['frames'] > canceled['rom_mp3_hle']['frames'], 'decoder stopped after cancellation'
        if args.inspect_player_help:
            capture('20-before-player-help')
            report['player_help_inspection'] = {
                'repeat_verified': False,
                'delivery': replay_step(bridge, RouteStep('player-help',15,0x8d),
                    press_timeout=45,release_timeout=45,poll_interval=.1,
                    settle=1,pulse_duration=key_pulse_duration),
            }
            state=capture('21-player-help')
            time.sleep(1)
            state=capture('22-player-help-settled')
            report['player_help_inspection']['scroll_delivery'] = []
            for page in range(1, 7):
                report['player_help_inspection']['scroll_delivery'].append(
                    replay_step(bridge, RouteStep(f'help-down-{page}',37,0x83),
                        press_timeout=45,release_timeout=45,poll_interval=.1,
                        settle=.5,pulse_duration=key_pulse_duration))
                state=capture(f'23-player-help-down-{page}')
        assert "UNSUPPORTED=none" in state["registers"] and "INVALID_CONTROL=none" in state["registers"]
        report["passed"]=True
    except (Exception,KeyboardInterrupt) as error:
        report["error"]=f"{type(error).__name__}: {error}"
        # replay_step already captures bounded before/timeout key counters.
        # Preserve them BEFORE a later failure screenshot advances the guest.
        # A string-only error loses the first divergence on missed short taps.
        if hasattr(error, "input_evidence"):
            report["input_failure_evidence"] = error.input_evidence
        print(report["error"],flush=True)
        if emulator is not None:
            try: capture("failure",check_watch=False)
            except Exception as secondary: report["capture_error"]=str(secondary)
    finally:
        for sampler in active_host_samplers:
            sampler.close()
        if watch is not None:
            watch.close()
            if args.observe_seek_reload_writes:
                report['seek_write_observer'].update(log=str(watch.path),
                    gdb_exit_code=watch.process.returncode,
                    reached_limit='SEEK_WRITE_LIMIT reached' in watch.text(),
                    local_watch_armed='SEEK_LOCAL_ARMED fp=' in watch.text())
            elif args.observe_file_scan_writes:
                report["file_scan_write_observer"].update(log=str(watch.path),gdb_exit_code=watch.process.returncode,
                    reached_limit="SCAN_WRITE_LIMIT reached" in watch.text(),
                    first_decrease_captured="FIRST_SCAN_DECREASE_DUMP_COMPLETE" in watch.text())
            elif args.observe_input_writes:
                report["input_write_observer"].update(log=str(watch.path),gdb_exit_code=watch.process.returncode,
                    reached_limit="INPUT_WRITE_LIMIT reached" in watch.text(),
                    first_aaaa_captured="FIRST_AAAA_WRITE captured" in watch.text(),
                    first_aaaa_dump_complete="FIRST_AAAA_DUMP_COMPLETE" in watch.text())
            else:
                report["state_write_observer"].update(log=str(watch.path),gdb_exit_code=watch.process.returncode,
                    reached_limit="STATE_WRITE_LIMIT reached" in watch.text())
        if audio_capture is not None: audio_capture.stop.set()
        if emulator is not None:
            emulator.close();report["exit_code"]=emulator.process.returncode
        if audio_capture is not None:
            report["device_audio_capture"]=audio_capture.finish(args.output)
        (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] and report["exit_code"]==0 else 1


if __name__=="__main__": raise SystemExit(main())
