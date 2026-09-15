#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Opt-in MP3 HLE gate, strict unknown holes, ABI, and device reset checks."""

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
import re
import struct
import subprocess
import tempfile
import time

from build_np560_mp3_resident import load_bundle
from web.np560_web import Emulator


def check(qemu, bundle, output, name, *, enabled=True, unknown=False,
          offset=0x100, bank=0xa3, invalid_workspace=False,
          release=False, device_reset=False, icount=None, minimal=False):
    _, image, manifest = load_bundle(bundle)
    base = manifest["rom_mp3_hle"]["base"]
    target = base + (len(manifest["rom_mp3_hle"]["targets"])*16 if unknown else 0)
    assert not unknown or image[target:target+2] == b"\0\x0f"
    words = [0x6800, 2, 0x68ff, 0x6000, 0x6810, bank, 0x6811, 0x34,
             0x68f1, 0xaabb, 0x68f2, 0xcccc, 0x68f3, offset, 0x68f4, 0xddee,
             0xbd00 | target >> 16, target & 65535]
    if release:
        words += [0xbd00 | (base+48) >> 16, (base+48) & 65535]
    final = 0x200000+len(words)*2
    words += [0xd0ff]
    missing = unknown or not enabled
    result = dict(name=name, passed=False, enabled=enabled, expected_missing=missing,
                  debugger_guest_memory_writes=0, nand_used=False,
                  control_observers_minimal=minimal)
    with tempfile.TemporaryDirectory(prefix="np560-hle-gate-") as directory:
        firmware = Path(directory)/"caller.prg"
        firmware.write_bytes(struct.pack(f"<{len(words)}H", *words))
        emu = Emulator(qemu=qemu, firmware=firmware, soc_rom=bundle/"resident.bin",
            soc_rom_skeleton=True, rom_mp3_hle_base=base if enabled else 0,
            boot_mode="firmware", start_paused=True, icount_shift=icount)
        result["owned_pid"] = emu.process.pid
        try:
            if minimal:
                emu.qmp.execute("qom-set", {"path":"/machine",
                    "property":"control-observers-minimal", "value":True})
            emu.qmp.execute("cont")
            deadline = time.monotonic()+15
            while time.monotonic() < deadline:
                state = emu.qmp.execute("qom-get", {"path":"/machine", "property":"cpu-state"})
                if ("ROM_MISSING=none" not in state or
                    f"PC={final>>16:02x}:{final&65535:04x}" in state):
                    break
                time.sleep(.1)
            emu.qmp.execute("stop")
            result["state_prefix"] = state[:350]
            (output/f"{name}.cpu.txt").write_text(state)
            stats = json.loads(emu.qmp.execute("qom-get", {"path":"/machine", "property":"rom-mp3-hle-state"}))
            result["hle"] = stats
            assert "ROM_HLE=off" in state and "HLE_UI=off" in state
            if missing:
                assert f"ROM_MISSING={target>>16:02x}:{target&65535:04x}" in state
                assert not enabled or stats["sessions"] == 0
            else:
                assert f"PC={final>>16:02x}:{final&65535:04x}" in state
                assert all(token+"=none" in state for token in ("ROM_MISSING", "UNSUPPORTED", "INVALID_CONTROL"))
                registers = {int(k):int(v,16) for k,v in re.findall(
                    r"\bR(\d+)\s*=([0-9a-f]{4})\b", "\n".join(state.splitlines()[:5]), re.I)}
                expected = {0:0, 1:0xaabb, 2:2 if invalid_workspace or offset>0x1d00 or offset%2 else 0,
                            3:offset, 4:0xddee, 15:0x6000}
                assert all(registers[k]==v for k,v in expected.items()), registers
                assert f"DS0={bank:03x} DS1=034" in state
                assert stats["sessions"] == int(not release and expected[2]==0)
                if device_reset:
                    emu.qmp.execute("system_reset")
                    reset = json.loads(emu.qmp.execute("qom-get", {"path":"/machine", "property":"rom-mp3-hle-state"}))
                    assert reset["sessions"]==0 and reset["device_resets"]>stats["device_resets"], reset
                    result["after_device_reset"] = reset
            result["passed"] = True
        finally:
            emu.close()
            result["exit_code"] = emu.process.returncode
            (output/f"{name}.qemu.log").write_bytes(emu.log_path.read_bytes())
            (output/f"{name}.json").write_text(json.dumps(result,indent=2)+"\n")
    print(name, result["passed"], flush=True)
    return result


def rejected_config(qemu, bundle, output):
    _, image, manifest = load_bundle(bundle)
    gate = manifest["rom_mp3_hle"]["base"]
    outcomes = []
    with tempfile.TemporaryDirectory(prefix="np560-hle-config-") as directory:
        program = Path(directory)/"caller.prg"
        program.write_bytes(struct.pack("<H", 0xd0ff))
        altered = bytearray(image)
        altered[gate+8] ^= 1
        rom = Path(directory)/"wrong-version.bin"
        rom.write_bytes(altered)
        mixed = bytearray(image)
        mixed[gate+16+8] ^= 1
        mixed_rom = Path(directory)/"mixed-version.bin"
        mixed_rom.write_bytes(mixed)
        wrong_service = bytearray(image)
        last = gate+(len(manifest["rom_mp3_hle"]["targets"])-1)*16
        wrong_service[last+10] ^= 1
        service_rom = Path(directory)/"wrong-service.bin"
        service_rom.write_bytes(wrong_service)
        for name, path, base, message in (
            ("wrong-version", rom, gate, "no versioned service marker"),
            ("mixed-version", mixed_rom, gate, "no versioned service marker"),
            ("wrong-last-service", service_rom, gate, "no versioned service marker"),
            ("outside-01-02", bundle/"resident.bin", 0x30000, "must fit ROM 01/02")):
            command = [str(qemu), "-M", f"np560,soc-rom={path},soc-rom-skeleton=on,rom-mp3-hle-base={base}",
                       "-bios", str(program), "-nographic", "-monitor", "none"]
            proc = subprocess.run(command, capture_output=True, text=True, timeout=15)
            (output/f"{name}.qemu.log").write_text(proc.stdout+proc.stderr)
            assert proc.returncode != 0 and message in proc.stderr, proc.stderr
            outcomes.append(dict(name=name, exit_code=proc.returncode, rejected=True))
    return outcomes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("qemu", "resident-bundle", "output"):
        p.add_argument("--"+name, type=Path, required=True)
    p.add_argument("--minimal-control-observers",action="store_true")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(passed=False, cases=[], qemu_sha256=hashlib.sha256(args.qemu.read_bytes()).hexdigest())
    try:
        for name, opts in (
            ("abi-reset", dict(device_reset=True)),
            ("abi-release-icount", dict(release=True, icount=5)),
            ("invalid-offset", dict(offset=0x1e00)),
            ("unaligned-offset", dict(offset=0x101)),
            ("rom-workspace", dict(bank=0x40, invalid_workspace=True)),
            ("mmio-workspace", dict(bank=1, offset=0x1d00, invalid_workspace=True)),
            ("disabled-gate", dict(enabled=False)),
            ("unknown-hole", dict(unknown=True))):
            report["cases"].append(check(args.qemu,args.resident_bundle,args.output,name,
                minimal=args.minimal_control_observers,**opts))
        report["rejected"] = rejected_config(args.qemu,args.resident_bundle,args.output)
        report["passed"] = True
    except (AssertionError, RuntimeError, subprocess.TimeoutExpired) as error:
        report["failure"] = str(error)[:2500]
        print(report["failure"], flush=True)
    finally:
        (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
