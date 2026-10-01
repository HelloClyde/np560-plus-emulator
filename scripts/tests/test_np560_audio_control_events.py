#!/usr/bin/env python3
"""Bounded audio/HLE lifecycle evidence: guest writes, wrap, read-only, reset.

No NAND or user Web; this tests observation, not audible playback.
"""

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import argparse
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import time

from build_np560_mp3_resident import load_bundle
from web.np560_web import Emulator


def check(qemu, bundle, output, hle):
    _, _, manifest = load_bundle(bundle)
    gate = manifest["rom_mp3_hle"]["base"]
    words = [0x6800, 2, 0x68ff, 0x6000, 0x6810, 0xa3, 0x68f3, 0x100]
    expected = []
    for i in range(70):
        pc = 0x200000 + len(words)*2
        if hle:
            words += [0xbd00 | gate >> 16, gate & 65535]
        else:
            # A valid PLL but DAC remains off: no data requests or tone.
            reg, value = (0xea, 0x84ff) if i % 2 == 0 else (0x72, 0x8008)
            words += [0x6800 | reg, value]
            expected.append((pc, reg, value))
    if hle:
        words += [0xbd00 | (gate+48) >> 16, (gate+48) & 65535]
    else:
        for value in (1, 0):
            expected.append((0x200000 + len(words)*2, 0x70, value))
            words += [0x6870, value]
    final = 0x200000 + len(words)*2
    words += [0xd0ff]
    with tempfile.TemporaryDirectory(prefix="np560-audio-events-") as directory:
        firmware = Path(directory)/"caller.prg"
        firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
        emu = Emulator(qemu=qemu, firmware=firmware,
            soc_rom=bundle/"resident.bin" if hle else None,
            soc_rom_skeleton=hle, rom_mp3_hle_base=gate if hle else 0,
            boot_mode="firmware", start_paused=True, icount_shift=5)
        result = dict(passed=False, name="hle" if hle else "dac",
                      host_guest_memory_writes=0, nand_used=False)
        try:
            emu.qmp.execute("cont")
            deadline = time.monotonic()+15
            while time.monotonic()<deadline:
                state = emu.qmp.execute("qom-get", {"path":"/machine", "property":"cpu-state"})
                if f"PC={final>>16:02x}:{final&65535:04x}" in state:
                    break
                time.sleep(.01)
            assert f"PC={final>>16:02x}:{final&65535:04x}" in state, state[:1000]
            assert all(k+"=none" in state for k in ("ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL"))
            emu.qmp.execute("stop")

            def snapshot():
                return json.loads(emu.qmp.execute("qom-get", {
                    "path":"/machine", "property":"rom-mp3-hle-state"})) if hle else emu.audio()

            before = snapshot()
            assert before == snapshot(), "reading a snapshot mutated device evidence"
            events = before["lifecycle_events" if hle else "control_events"]
            count = before["lifecycle_next" if hle else "control_event_next"]
            assert count == (71 if hle else 72) and len(events) == 64
            assert [e["sequence"] for e in events] == list(range(count-64,count))
            assert all(a["virtual_ns"] <= b["virtual_ns"] for a,b in zip(events,events[1:]))
            if hle:
                assert before["sessions"] == before["failures"] == 0
                assert before["calls"] == [70,0,0,1]
                for event in events:
                    assert event["workspace"] == (0xa3<<15)+0x100
                    assert event["service"] == (3 if event["sequence"] == 70 else 0)
                    assert event["present"] and not event["pending"]
                    assert event["frames"] == event["granules"] == 0
                    assert event["session_frames"] == event["session_granules"] == 0
            else:
                for event in events:
                    pc,reg,value = expected[event["sequence"]]
                    assert (event["pc"],event["reg"],event["value"]) == (pc,reg,value), event
                    assert event["old_value"] == (1-value if reg == 0x70 else value)
                    assert event["last_request_ns"] == [0, 0]
                    assert not event["enabled"] and not event["running"]
                    assert event["ticks"] == 0 and event["writes"] == [0,0]
                assert before["writes"] == [2,0,35]
            emu.qmp.execute("system_reset")
            reset = snapshot()
            assert reset["lifecycle_next" if hle else "control_event_next"] == 0
            assert reset["lifecycle_events" if hle else "control_events"] == []
            result.update(passed=True, next_sequence=count, events=events,
                          reset_empty=True, paused_reads_identical=True)
        finally:
            emu.close()
            result["exit_code"] = emu.process.returncode
            (output/(result["name"]+".json")).write_text(json.dumps(result,indent=2)+"\n")
    assert result["exit_code"] == 0
    print(result["name"],"passed",flush=True)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("qemu","resident-bundle","output"):
        p.add_argument("--"+name,type=Path,required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    report = dict(passed=False, qemu_sha256=hashlib.sha256(args.qemu.read_bytes()).hexdigest(),cases=[])
    try:
        for hle in (False,True):
            report["cases"].append(check(args.qemu,args.resident_bundle,args.output,hle))
        report["passed"] = True
    finally:
        (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
