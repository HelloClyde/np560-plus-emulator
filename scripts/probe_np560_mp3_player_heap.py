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
from test_np560_mp3_allocation import HEAP_BEGIN, HEAP_END, PRG_SHA
from verify_np560_toolbar_frames import expected_from_package
from web.np560_web import Emulator, RunJournal, artifact_identity

TONE_NAND_SHA = "639e470754517a6b763b0f762d788aed6b78c479aef061692834df3b22a10a19"


class DeviceAudioCapture:
    """Read the actual DAC presentation ring for a bounded time; never fill gaps."""
    def __init__(self, emulator, seconds=20):
        self.seconds=seconds
        self.stop=threading.Event();self.parts=[];self.error=None;self.delivery=[]
        self.thread=threading.Thread(target=self.run,args=(emulator,),daemon=True)
        self.thread.start()

    def run(self, emulator):
        deadline=time.monotonic()+self.seconds
        try:
            while not self.stop.is_set() and time.monotonic()<deadline:
                packet=emulator.audio()
                if "request_delivery" in packet:
                    # Same packet/read cadence as the real PCM capture; no
                    # extra query, clock advance, dequeue or guest write.
                    self.delivery.append({k:packet[k] for k in (
                        "generation","next_frame","enabled","request_clock","request_delivery",
                        "control_event_next","control_events") if k in packet})
                assert packet["sample_rate"]==48000 and packet["channels"]==2
                first,last=packet["first_frame"],packet["next_frame"]
                raw=base64.b64decode(packet["pcm"])
                assert len(raw)==(last-first)*4
                if last>first:
                    part=self.parts[-1] if self.parts else None
                    if part is None or part["generation"]!=packet["generation"] or first>part["next_frame"]:
                        part={"generation":packet["generation"],"first_frame":first,
                              "next_frame":first,"data":bytearray()}
                        self.parts.append(part)
                    assert last>=part["next_frame"],"device audio timeline moved backwards"
                    part["data"].extend(raw[(part["next_frame"]-first)*4:])
                    part["next_frame"]=last
                self.stop.wait(.05)
        except Exception as error:
            if not self.stop.is_set(): self.error=str(error)

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
    def __init__(self,qemu,pid,addresses,output,observe_end=False):
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


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("qemu","firmware","soc-rom","nand-checkpoint","package","output"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--observe-native-codec",action="store_true",
                   help="observe real allocations/PCM after selecting a file with experimental factory ABI")
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
    p.add_argument('--speed-window-seconds', type=int, choices=range(0,61), default=0,
                   help='unpaused desktop/player speed windows with LCD polling; no debugger')
    p.add_argument('--profile-player', action='store_true',
                   help='after speed windows, collect 20 read-only CPU stack samples; not timing evidence')
    p.add_argument('--speed-audio-poll', action='store_true',
                   help='also fetch the complete DAC packet every 50 ms in the player speed window')
    p.add_argument('--profile-samples', type=int, choices=range(1,101), default=20,
                   help='bounded number of debugger samples, outside timing windows')
    p.add_argument('--realtime', action='store_true',
                   help='enable QEMU host pacing; requires the instruction clock')
    p.add_argument("--observe-dtu-config",action="store_true",
                   help="read the bounded ED configuration trace; no breakpoints or guest writes")
    p.add_argument("--record-device-audio",action="store_true",
                   help="capture actual DAC ring after file selection; split on gaps")
    p.add_argument("--audio-seconds",type=int,choices=range(1,301),default=20,
                   help="bounded actual-device capture time; default 20 wall seconds")
    p.add_argument("--codec-observations",type=int,choices=range(1,61),default=12,
                   help="number of five-second observations of the SAME owned process")
    p.add_argument("--observe-play-controls",action="store_true",
                   help="after loading, observe physical D/F/D/G keys; requires native codec mode")
    p.add_argument("--observe-player-back",action="store_true",
                   help="observe physical Back84 after playback; do not assume delivery means exit")
    p.add_argument('--rom-mp3-arena-image',type=lambda s:int(s,0),default=0)
    p.add_argument("--observe-player-minimize",action="store_true",
                   help="observe original F4/008E minimize; not a forced session release")
    p.add_argument("--observe-exit-heap-writes",action="store_true",
                   help="watch two live heap headers during F4; read-only, not timing evidence")
    p.add_argument('--reopen-after-minimize',action='store_true',
                   help='reopen and play the same NAND file in the SAME process, then minimize again')
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
    if args.realtime and not args.instruction_clock:
        p.error('--realtime requires --instruction-clock')
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
    if args.observe_state_writes and not args.observe_play_controls:
        p.error("--observe-state-writes requires --observe-play-controls")
    if args.observe_end_writes and not args.observe_state_writes:
        p.error("--observe-end-writes requires --observe-state-writes")
    if args.observe_input_writes and (not args.observe_native_codec or args.observe_state_writes):
        p.error("--observe-input-writes requires native codec and cannot combine with state watches")
    if args.observe_file_scan_writes and (not args.observe_native_codec or
            args.observe_play_controls or args.observe_input_writes):
        p.error("--observe-file-scan-writes requires native codec and no other write/control watches")
    args.output.mkdir(parents=True,exist_ok=False)
    identities={}
    for name in ("qemu","firmware","soc_rom","nand_checkpoint","package"):
        path=getattr(args,name);size,digest=artifact_identity(path)
        identities[name]={"path":str(path.resolve()),"bytes":size,"sha256":digest}
    assert identities["firmware"]["sha256"]==PRG_SHA
    assert identities["nand_checkpoint"]["sha256"]==TONE_NAND_SHA
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
                    player.update(mode_087a=fields[0x1a^1],state_087c=fields[0x1c^1])
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
    def speed_window(label):
        if not args.speed_window_seconds:
            return
        emulator.qmp.execute('stop')
        def clock_ns():
            clock=emulator.qmp.execute('qom-get', {'path':'/machine','property':'instruction-clock-state'})
            assert 'FAULT:0' in clock, clock
            return int(re.search(r'\bNS:(\d+)', clock)[1])
        start_ns=clock_ns()
        audio_before=emulator.audio() if label == 'player' else None
        if audio_before:
            assert audio_before['enabled'] and audio_before['request_clock']['running'], 'speed window is not active playback'
        started=time.monotonic()
        emulator.qmp.execute('cont')
        polls=0
        audio_polls=0
        next_lcd=started
        poll_audio=args.speed_audio_poll and label == 'player'
        while time.monotonic()-started < args.speed_window_seconds:
            if time.monotonic() >= next_lcd:
                emulator.snapshot('lcd', 0, 0, diagnostics=False)
                polls+=1
                next_lcd=time.monotonic()+.2
            if poll_audio:
                emulator.audio()
                audio_polls+=1
            time.sleep(.05 if poll_audio else .2)
        emulator.qmp.execute('stop')
        elapsed=time.monotonic()-started
        end_ns=clock_ns()
        cpu=emulator.qmp.execute('qom-get', {'path':'/machine','property':'cpu-state'})
        assert all(f'{field}=none' in cpu for field in ('ROM_MISSING','UNSUPPORTED','INVALID_CONTROL'))
        result=dict(label=label, host_seconds=elapsed, guest_seconds=(end_ns-start_ns)/1e9,
                    realtime_ratio=(end_ns-start_ns)/1e9/elapsed, lcd_polls=polls,
                    audio_polls=audio_polls)
        report.setdefault('speed_windows', []).append(result)
        if audio_before:
            audio_after=emulator.audio()
            before, after = audio_before['request_clock'], audio_after['request_clock']
            assert audio_after['enabled'] and after['running'], 'playback ended during the speed window'
            assert before['hz'] == after['hz'] and before['pll'] == after['pll']
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
        print('unpaused speed: '+json.dumps(result), flush=True)
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
        speed_window('desktop')
        route=[("start",55,0xb0),("entertainment",53,0x86),("mp3",53,0x86),
               ("open-file",60,0xe2),("parent",53,0x86)]
        route += [(f"down-{i+1}",37,0x83) for i in range(28)]
        reference_state=json.loads((Path(__file__).resolve().parents[1]/
            "tmp/np560-mp3-player-20260906-v1/with-tone/frames/09-root-bottom.json").read_text())
        # The pinned Sept-6 export predates gray5-darkness encoding. Its
        # legacy inverted light-level pixels have exactly opposite polarity.
        # Convert only this old reference; never alter guest/LCD snapshots.
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
        assert frame[105*240:118*240]==reference[105*240:118*240],"selected tone row differs"
        if args.observe_input_writes:
            report["input_write_observer"]={"addresses":[0x1000,0x1452],"host_guest_memory_writes":0}
            emulator.qmp.execute("stop")
            try:
                watch=InputRingWatch(args.qemu,emulator.process.pid,args.output)
                watch.ready()
            finally: emulator.qmp.execute("cont")
            print("input ring hardware watches armed before selecting tone",flush=True)
        if args.record_device_audio:
            audio_capture=DeviceAudioCapture(emulator,args.audio_seconds)
        try:
            replay_step(bridge,RouteStep("select-tone",53,0x86),press_timeout=15*args.host_timeout_scale,
                release_timeout=15*args.host_timeout_scale,poll_interval=.05,settle=1,pulse_duration=key_pulse_duration)
        except RuntimeError as error: report["entry_observation"]=str(error)
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
            speed_window('player')
            if args.profile_player:
                report['player_profile']=f'{args.profile_samples} debugger samples AFTER timing windows; not timing evidence'
                for sample in range(args.profile_samples):
                    trace=subprocess.run(['gdb','-q','-nx','-batch','-p',str(emulator.process.pid),
                        '-ex','set pagination off','-ex','thread apply all bt 8','-ex','detach'],
                        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=15)
                    (args.output/f'player-profile-{sample:02}.txt').write_text(trace.stdout)
                    assert trace.returncode==0,trace.stdout
                    time.sleep(.25)
            if args.observe_play_controls:
                if args.observe_state_writes:
                    import build_np560_mp3_session as session
                    sample=report["native_codec_samples"][f"05-codec-{args.codec_observations}"]
                    assert len(sample["owners"])==1
                    addresses={"player_state":sample["player"]["address"]+0x087c,
                               "codec_ready":sample["owners"][0]["node"]["address"]+6+session.READY}
                    report["state_write_observer"]={"addresses":addresses,
                        "end_flags_internal_sram":args.observe_end_writes,
                        "host_guest_memory_writes":0,"scope":"write callers during physical controls, not timing"}
                    emulator.qmp.execute("stop")
                    try:
                        watch=PlayerStateWatch(args.qemu,emulator.process.pid,addresses,args.output,
                                               observe_end=args.observe_end_writes)
                        watch.ready()
                    finally: emulator.qmp.execute("cont")
                    print("player state/READY hardware watches armed",flush=True)
                # These are letters from the original player's visible
                # controls. The original dispatcher converts them to 0092
                # (state-dependent Play/Pause) or 0091 (Stop); never inject
                # those logical commands or overwrite the state gate.
                for action,index,event,samples in (
                        ("play",1,0x64,6),("pause",9,0x66,3),
                        ("resume",1,0x64,6),("stop",17,0x67,3)):
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
                        time.sleep(5);state=capture(f"{label}-{i+1}")
                if watch is not None: assert "STATE_WRITE name=" in watch.text(),"no observed player/READY changes"
            if args.observe_player_back or args.observe_player_minimize:
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
                    steps += [(f'down-{i+1}',37,0x83) for i in range(28)]
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
        assert "UNSUPPORTED=none" in state["registers"] and "INVALID_CONTROL=none" in state["registers"]
        report["passed"]=True
    except (Exception,KeyboardInterrupt) as error:
        report["error"]=f"{type(error).__name__}: {error}"
        print(report["error"],flush=True)
        if emulator is not None:
            try: capture("failure",check_watch=False)
            except Exception as secondary: report["capture_error"]=str(secondary)
    finally:
        if watch is not None:
            watch.close()
            if args.observe_file_scan_writes:
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
