# NP560+ QEMU/DMCU emulator

This tree adds a QEMU TCG system target for the 16-bit King Billion DMCU used
by the Noah NP560+. The default is strict hardware mode: missing resident-ROM
code is not replaced unless `rom-hle=on` is explicitly requested.

## Implemented

- `qemu-system-dmcu` and the `-M np560` machine.
- Harvard code/data buses, an 8-bit code segment plus a byte-addressed 16-bit
  PC, 9-bit `DS0`/`DS1` translation, the direct 64 KiB internal data window,
  and unbanked frame/stack accesses.
- Sixteen 16-bit registers, byte aliases, SFRs, flags, stack frames, ALU,
  multiply/divide, branches/calls, shifts (including the cross-register shift
  buffer), bit operations, `REP`, and the currently observed `REPB` forms.
- The 4 MiB external program/NOR source image at `20:0000`-`5F:FFFF`, on a
  code bus distinct from writable external data RAM. The directly evidenced
  power-on data window exposes NOR at `20:0000`-`4F:FFFF`; data segment 50 and
  above is RAM. Recovered overlay slots are shared explicitly between the
  buses so the guest loader can install utility trampolines, the 60-byte
  compiler copy helper at `32:F786`, and the recovered runtime/application
  overlays used by the V3.80 cold-start path.
- Optional real SoC ROM loading at `00:0000`, up to 2 MiB, with
  `soc-rom=FILE`. The older single-bank option `mask-rom=FILE` maps a 64 KiB
  dump at `03:0000`.
- Optional updater code images:
  - USB loader at `00:1000`;
  - NAND burner at `50:6000`;
  - update-driver block at `52:0000`.
- A hardware ST7529 LCD model at physical addresses `0xF00001` (command) and
  `0xF00003` (data). It implements the address window, data scan direction,
  3-byte/3-pixel 5-bit grayscale RAM transfers, display/sleep, inversion, and
  the NP560 module's inferred cross-bank COM wiring.
- A reconstructed Samsung `EC:DC` large-page NAND device: 2048 data bytes plus
  64 OOB bytes per page, 64 pages per erase block, and 4096 blocks (512 MiB).
  This matches the NP560+ capacity and the burner's `0x95` extended-ID geometry
  branch. Guest code
  can read IDs, read/program pages, and erase blocks; programming obeys NAND's
  one-to-zero rule. `nand-image=FILE` loads the package's logical page stream
  and synthesizes erased OOB bytes. Complete data+OOB checkpoints can be
  restored and explicitly saved, including automatically on Web-frontend exit.
- The evidenced keyboard hardware path: GPIO state at `F010`, the `F160/F164`
  matrix registers, exact reader `06:B126`, scanner `2E:5F28`, and application
  mapper `28:F4A4`. In strict mode the Web frontend changes only physical key
  state. The older `F340` make-code latch remains as a compatibility
  diagnostic, but the Web frontend supplies a nonzero code only when ROM HLE
  is explicitly enabled; native-system tests assert that it is unused.
- A Web/QMP frontend that reads the ST7529's internal GRAM as a 240x120,
  5-bit-gray image and reports NAND activity. Raw physical-memory viewing
  remains a diagnostic option.

The instruction decoder is based on the DMCU appendix in patent
[CN1916884A](https://patents.google.com/patent/CN1916884A/zh). This is an
independent clean-room implementation, not vendor source code.

## What is in `NP560+.upd`

`disassembly/np560_upd.py` verifies the package checksum and identifies four
payload slots:

| Slot | Size | Meaning |
|---:|---:|---|
| 0 | `0x17C88` | burner program loaded at `50:6000` |
| 1 | `0x12EE4` | update/LCD/storage driver loaded at `52:0000` |
| 2 | `0x400000` | word-swapped copy of `NP560.PRG` |
| 3 | `0x29ED3B4` | `MASKROM NP560 VER3.65` NAND/resource image |

The slot-3 header declares 85,866 logical 512-byte pages, exactly the package
size rounded up to a page boundary. It is therefore a page stream without raw
NAND spare/OOB bytes; the burner pads the final page before programming it.

The package also ships a separate `USB_Loader_Noah.bin`. These are the
rewritable external Flash/NAND materials and upgrade helpers. This product is
not a Linux/U-Boot platform, and the package's `MASKROM` label refers to the
NAND image, not to the SoC's factory mask ROM.

The main program and updater helpers call resident routines in code segments
02 and 03. Those bytes are internal to the SoC and are not present in the
upgrade package. Since no physical unit is available, this project uses a
clean-room functional reconstruction instead of claiming to reproduce the
unknown factory bytes. Caller disassembly and unmodified vendor code establish
each entry's observable ABI; the replacement then executes as ordinary DMCU
guest instructions and drives modeled peripherals through MMIO. QEMU never
intercepts `SCALL` to manufacture a ROM return value.

`disassembly/build_np560_reconstructed_rom.py` currently reconstructs these
entries and loader actions:

| Entry | Reconstructed behavior | Evidence/status |
|---|---|---|
| `02:BB1E` | read NAND ID | burner derives `EC:DC`, geometry byte `0x95` |
| `02:BBF6` | read page/OOB | recovered seven-word stack ABI |
| `02:BCC6` | program page/OOB | same ABI; caller reads, edits, then calls it |
| `02:BDD6` | erase block | one block argument; zero means success |
| `03:0030` | application cold-start bridge | builds the outer frame expected by `33:4F50` |
| `03:0080` | resident continuation | focused images use the older diagnostic poll loop; the system image uses an explicitly inferred guest loop that re-enters complete shipped system main `20:026A`, which prepares exact continuation `2D:7DD2` |
| `03:1000` | clear byte buffer | reconstructed `length + far pointer` ABI |
| `03:1100` | low 32 bits of 32x32 multiply | reconstructed four-word operand ABI |
| `08:43A6` | forward far-memory copy | nine five-word calls; fixed and overlapping copies prove direction |
| `14:65CE/68B0/6AD8` | ST7529 power/init/clear | complete same-PC bodies at `31:*`; ends with display-on command `AF` |
| `14:6AEC/6E10/6F30` | ST7529 region/bitmap/delay | complete same-PC bodies at `31:*`, with zero calls to the source addresses |
| `18:6D56` | forward far-memory copy | sixteen five-word calls; overlapping zero expansion proves direction |
| `25:6042` | overlay wrapper installed in program RAM | all callers establish the clear-buffer ABI |
| `33:07B0` | overlay wrapper installed in program RAM | 935 callers; compiler multiply helper ABI |
| `03:026A` | first initializer continuation | enters `2E:4560` in the strict probe |
| `07:7FE4` | second initializer continuation | installs runtime overlays in the strict probe |
| `2C:9A7C` | overlay from `49:9A7C` | complete 490-byte no-argument function |
| `2E:5316` | overlay from `4B:5316` | complete 388-byte four-argument function |
| `33:6030` | overlay from `50:6030` | complete 12-byte no-argument wrapper |
| `06:1CE0` | relocated exact body from `50:5906` | complete 16-byte bit-control function; preserves live flat code at colliding `33:5906` |
| `33:5B70` | overlay from `50:5B70` | complete 14-byte application-state reader; 36 calls target the overlay and none call the source |
| `1F:B496` | exact resident body from `3C:B496` | complete 1,488-byte one-argument application-event dispatcher reached by event `0x84` |
| `25:5858`, `30:A3C2`, `25:E324` | application-storage overlays from `42:5858`, `4D:A3C2`, `42:E324` | complete same-PC functions reached by the flashed V3.80 checkpoint |
| `33:524C` plus 17 dependencies | closed resource/storage runtime graph from PRG banks `42`-`50` | exact guest modules; fixes the deterministic 49-lifecycle stack corruption caused by executing the unrelated flat target |
| `1C:7FFE`, `1E:7E4E` | exact resident bodies from `39:7FFE`, `3B:7E4E` | complete `0x7CA`- and `0x670`-byte resource/storage modules, including the internal `39:8110 -> 39:873C` jump |

The cold-start bridge also invokes NP560.PRG's otherwise-unreferenced fixed
callback at `20:0030`. It clears the BSS/data windows, initializes low-level
SFR state, and returns normally. In particular it clears data addresses
`50:0000`-`53:FFFF`, even though the application also executes code in those
logical segments. This is direct evidence that PRG/NOR code and external data
RAM cannot be one pre-populated writable backing store.

A second startup entry at `20:026A` is now executed by the strict diagnostic
path. Its naked call to flat `2C:9A7C` is ABI-incompatible, but
`49:9A7C..49:9C65` is a complete same-PC no-argument function. The same
signature method recovers `4B:5316 -> 2E:5316`, the `50:6030 -> 33:6030`
wrapper, and its exact `50:5906` bit-control dependency. Flat `33:5906` is also
live fall-through code, so the loader relocates that short body to resident
`06:1CE0` and patches the two proven guest call sites instead of permanently
overwriting the collision. A later transition similarly proves
`50:5B70 -> 33:5B70`. The exact evidence and the
boundary between proof and inference are recorded in
`disassembly/NP560_resident_boot_contract.md`.

The reset target itself has the same kind of ABI constraint: `20:0004` jumps
to `33:4F50`, inside the event-`0x008E` activation path of the ordinary handler
at `33:4510`. The reconstructed `03:0030` therefore builds a compatible outer
frame and prepares `context+0x38` / `context+0x30` in registers before returning.
Separately, the shipped NAND burner proves the vendor compiler's startup
pattern: 21 calls copy initialized objects from code-image addresses into data
RAM. The application contains the same 60-byte helper template at `4F:F786`,
while 270 descriptors in two chains call its overlay destination `32:F786`.
The chains contain 9 and 261 copies and return through `03:026A` and
`07:7FE4`. The dual-chain probe executes every descriptor and validates 2,955
final initialized bytes before runtime code can modify them. It installs the
recovered full-function overlays, enters unmodified `20:026A`, and reaches the next
  former strict boundary `08:427E` from `2C:9AF6`. A complete relocation-proven
  source module has since been recovered for `08:427E`, and the segment-03 jump
  table now supplies the exact `03:4124` trampoline/body.  The nine first-chain
  descriptors' three internal-ROM source windows are now restored from their
  bounded `+0x1D` linked PRG copies at `21:FFF8`, `24:57C8`, and `24:A622`.
  Only the isolated `--initializer-probe` keeps recognizable sentinels for ABI
  testing; the overlay/system path uses exact storage bytes. QEMU does not hide
  this path with ROM-service emulation.

The current system image reconstructs the inferred `01:0200` late loader,
installs the application/LCD/storage overlays as guest DMCU code, and enters the
exact `3B:F734` resident dispatcher. With the complete post-upgrade NAND
checkpoint it reaches `31:D9AA` and the exact `06:B126` matrix reader with
`ROM_MISSING=none`, `UNSUPPORTED=none`, and ROM HLE disabled. The hardware
ST7529 receives non-uniform frames and its RAM is no longer all zero. The data
bus alias `33:707C -> 50:707C` also restores the evidenced `33:D000` font base;
without it, executable words were misread as a `6A0B:FFEE` resource pointer.
The update image also supplies a complete same-PC body for resident `1F:B496`
at `3C:B496`; all nine callers agree on its one-word ABI. Exact guest execution
of that dispatcher now handles application event `0x84` and redraws the screen.
This establishes an end-to-end native CPU/NAND/LCD/keyboard execution path; it
does not prove the original `01:0200` ordering, the inferred application-state
guard, the resident's post-application selection policy, or the unknown factory
initializer bytes.

The application resource loop at `25:CC94` calls `33:524C` once per lifecycle.
The flat bytes at that destination are the tail of an unrelated framed function:
they appeared to return successfully 49 times, then wrapped the stack and entered
missing `14:2262`. The updater contains an exact `50:524C` same-PC wrapper and a
closed graph of 17 dependencies. The clean-room loader now installs all 18 exact
modules, while QEMU exposes only those proven destinations as executable
code/data aliases. The strict system test pins `33:524C` byte-for-byte against
the PRG source before accepting native idle. A 64-lifecycle single-process run
now crosses the old failure point with `SP=FFFE`, `ROM_HLE=off`, and no missing
ROM.

The exact top-level application continuation `2D:7DD2` unwinds through the
real `20:0320` epilogue after a foreground lifecycle. It begins with
`ADD SP,#8`, so it is not an ordinary stand-alone entry: it consumes the
compiler transfer frame and two parent-prepared words. Because the following
factory-ROM policy is unavailable, the clean-room system image installs a
four-word guest DMCU continuation at `03:0080`: call the complete shipped
system main `20:026A`, then jump back to `03:0080`. That parent establishes
the proven frame, performs its initialization and `01:0200` loader call, and
only then enters `2D:7DD2`. The strict trace now observes a real `SCHEDRET` at
`20:0326 -> 03:0084` on the second Enter lifecycle. Its register snapshot is
`R0=0000, R1=0080, R2=0085`: the shipped epilogue clears R0 but leaves the
application exit event in R2. Separate scheduler-owned runs reproduce
`R2=0082` and `R2=0083` at the same exact return boundary. This recovers the
factory selector's input-register ABI, although not yet its target-selection
policy. Meanwhile,
`FIRST_LOW_SP=none` and `FIRST_LOW_FP=none` remain hard gates. The exact
`33:529E` compiler epilogue has one legitimate top-of-stack transition:
its final `POP R0` at `33:52A4` advances `SP=FFFE` to `0000` for one
instruction, after which `UNLINK` restores the high stack from `FP=FFF8`.
QEMU reports this separately as `BENIGN_SP_WRAP` so it cannot conceal a real
low-stack transition. Repeating the cold-start
`20:0004 -> 33:4F50` activation path was disproved by a lifecycle trace: it
eventually overwrote the synthetic outer return frame. The replacement is an
inferred "re-enter the same complete system main" policy, not recovered
mask-ROM bytes and not a host-side ROM service. The physical-matrix regression
covers every one of the 64 row/column positions in one persistent QEMU system
session. All positions pass through exact scanner `2E:5F28` and mapper
`28:F4A4`; this includes events `0x82`, `0x83`, `0x84`, and `0x85`, with
`0x84` consumed by exact resident `1F:B496` inside its current lifecycle.

The full 4 MiB PRG contains exactly one literal call to `2D:7DD2`, at
`20:031C`, immediately followed by the `20:0320` startup epilogue; it contains
no literal call or jump to resident `03:0080`. This is signature-checked by
`analyse_np560_boot_contract.py` and proves the factory selector is not hidden
elsewhere in the upgradeable program image.

The repeated-lifecycle regression also naturally reached `02:C588`. All four
static callers pass one of `0x23`, `0x24`, `0x30`, or `0x65`, reclaim the one
argument themselves, and never consume a return value. The `0x23/0x24` pair
brackets two three-byte emissions through adjacent entry `02:C5DC`, while
`0x30/0x65` occurs only on the chip-ID-`0xEC` NAND self-test branch. The
reconstructed image therefore supplies the CPU-visible normal return as one
guest `RETS`. A probable external diagnostic-byte side effect remains
unmodeled until an SFR or pin can be evidenced; no UART address is fabricated.

`02:B9E2`, `02:BAC4`, and `02:BAC8` are temporary no-op select/setup entries;
their exact GPIO side effects are not yet known. Every other word in the
generated image is the reserved opcode `0x0F00`. With
`soc-rom-skeleton=on`, execution therefore stops and records the first new
unknown dependency rather than silently stubbing it. Without any reconstructed
or dumped ROM, strict main-program boot still stops at `03:0030`; the extracted
slot-1 driver initializes the LCD and stops at `02:BAC4`.

The earlier `0x526A1E` experiment reaches the native event handler but is not a
valid application context: static analysis now identifies it as one 16-bit
field inside a table of `0x94`-byte records. Treating its program bytes as a UI
object consequently reaches `17:9244` through garbage fields. That entry is
still a real unresolved dependency used by six multibyte text/glyph call sites,
but it is not yet evidence for the cold-start path. `--probe-font-lookup` adds
an explicitly recorded, exploration-only `RETS` there; it is not part of the
default reconstructed behavior.

Extract any package slot without loading the other large payloads:

```powershell
python ..\disassembly\np560_upd.py `
  '..\NP560+V3.80版系统升级程序\NP560+.upd' `
  --extract-dir $env:TEMP\np560-upd --extract-slot 1
```

The program image is converted to CPU byte order during extraction; auxiliary
word-code images retain the updater's big-endian word order expected by the
QEMU loader.

## Verified hardware path

The extracted slot-1 driver boots at `52:0000` in strict mode and runs the
original ST7529 initialization sequence. The current regression observes:

```text
ST7529=on SLEEP=off INV=on CMD=5c
WINDOW=C0-79,L20-139 DATA=57921 FRAMES=2
ROM_MISSING=02:bac4 FETCHES=1
```

No ROM HLE is active on this path. It proves that the actual updater code is
driving the modeled LCD controller and that the 240x120 visible window is
columns 0-79 (three pixels per column group), lines 20-139.

V3.80 programs `DATSDR=00,00,02` and `COMSCN=001`.  The exact recovered
`18:6454` font blitter independently stores successive glyph rows one packed
framebuffer line lower in memory (`-0x3c` words), establishing a bottom-up
240x120 framebuffer contract.  The modeled NP560 glass therefore crosses the
two ST7529 COM banks so that the firmware setting presents GRAM lines 139..20
as visible rows 0..119.  `test-np560-st7529.ps1` pins all four bank/window
boundaries: GRAM 139/80/79/20 appear at visible rows 0/59/60/119.  This avoids
the former half-correct result where lower text was upright but upper text was
vertically mirrored.

## Build and run

From PowerShell:

```powershell
.\build-np560.ps1
.\run-np560.ps1
```

The WSL build is placed at
`E:\qemu-dmcu-build\qemu-system-dmcu`.

Run with a real flat SoC-ROM dump:

```powershell
.\run-np560.ps1 -SocRom C:\path\to\soc-rom.bin
```

Build and use the current clean-room system ROM with the complete NAND
checkpoint produced by the V3.80 burner run:

```powershell
python ..\disassembly\build_np560_reconstructed_rom.py `
  --initializer-overlay-probe --probe-rom-08-427e-return `
  --probe-rom-01-0200-return --probe-system-main `
  --probe-resident-app-state-guard `
  --output ..\tmp\np560-system-v380-rom.bin

.\run-np560.ps1 `
  -SocRom ..\tmp\np560-system-v380-rom.bin -SocRomSkeleton `
  -NandCheckpoint ..\tmp\np560-v380-flashed-ecc.nand
```

The loaded NAND is kept in emulator memory so an input image is never modified
implicitly. To preserve guest program/erase operations, request an explicit
output checkpoint. It contains all 512 MiB data, 16 MiB OOB, geometry metadata,
and independent checksums. The save button and normal Web shutdown both update
the requested output:

```powershell
.\run-np560-web.ps1 `
  -SocRom ..\tmp\np560-system-v380-rom.bin -SocRomSkeleton `
  -NandCheckpoint ..\tmp\np560-v380-flashed-ecc.nand `
  -NandSaveOnExit E:\np560-data\np560-live.nand
```

A complete checkpoint is 553,648,192 bytes. Atomic replacement temporarily
needs enough free space for a second copy, so choose a volume with at least
about 1.1 GiB free.

For the obsolete invalid-context probe (retained only for reproducing the
`17:9244` trace):

```powershell
python ..\disassembly\build_np560_reconstructed_rom.py `
  --startup-context 0x526A1E --probe-font-lookup `
  --output ..\tmp\np560-reconstructed-rom-probe.bin

.\run-np560-web.ps1 `
  -SocRom ..\tmp\np560-reconstructed-rom-probe.bin -SocRomSkeleton
```

The obsolete invalid-context probe has no meaningful UI behavior because
`0x526A1E` is table data rather than an object base. Its legacy `F340` input is
available only with explicit `-RomHle`; strict Web mode leaves `F340` at zero.

Run the supplied auxiliary programs:

```powershell
.\run-np560.ps1 -BootMode usb `
  -UsbLoader '..\NP560+V3.80版系统升级程序\USB_Loader_Noah.bin'

.\run-np560.ps1 -BootMode burn `
  -BurnCode '..\NP560+V3.80版系统升级程序\BURN_NAND_FLASH_CODE.bin'

.\run-np560.ps1 -BootMode driver `
  -DriverCode "$env:TEMP\np560-upd\NP560_UPDATE_DRIVER.bin"
```

Add `-Trace` for `in_asm,unimp` output in
`E:\qemu-dmcu-build\np560-trace.log`.

## Web frontend

Build the current native system image and start the Web frontend from the full
post-upgrade NAND checkpoint:

```powershell
python ..\disassembly\build_np560_reconstructed_rom.py `
  --initializer-overlay-probe --probe-rom-08-427e-return `
  --probe-rom-01-0200-return --probe-system-main `
  --probe-resident-app-state-guard `
  --output ..\tmp\np560-system-v380-rom.bin

.\run-np560-web.ps1 `
  -SocRom ..\tmp\np560-system-v380-rom.bin -SocRomSkeleton `
  -NandCheckpoint ..\tmp\np560-v380-flashed-ecc.nand
```

The resulting QMP/Web state is `DISPLAY=on`, `SLEEP=off`, with a 28,800-byte
240x120 gray5 frame. ROM HLE and UI HLE remain off. `-NandImage` still accepts
the logical package stream for focused tests; `-NandCheckpoint` restores the
full 512 MiB data plus OOB state and the two options are mutually exclusive.

```powershell
.\run-np560-web.ps1
```

Open `http://127.0.0.1:8765`. The default display source is the ST7529
hardware controller. The debug panel can switch to physical-memory mode;
the explicit ROM-HLE diagnostic framebuffer is at `0xEF0000`, 1 bpp,
30 bytes per row. When `-NandSaveOnExit` is present, the debug panel also
enables **保存 NAND**; without an explicit output the NAND remains intentionally
read-only across emulator restarts.

For reverse-engineering, `/api/state?source=data&base=ADDRESS&size=SIZE` reads
the raw `np560.data` RAM backend. This differs from `source=memory`: physical
memory intentionally includes higher-priority PRG/NOR and executable-overlay
aliases, while `source=data` exposes the guest's writable state underneath
those aliases. Both endpoints are diagnostic and read-only.

The NP560 panel is not only a 240x120 dot matrix.  Factory initialization
writes ST7529 `DISCTRL` parameters `04,24,00`, so the controller runs at
148-line duty while `LASET 14,8B` reserves lines 20..139 for the raster.
Exact resident routine `14:6E10` writes two additional 240-bit planes to
lines 19 and 140 from the 60-byte guest buffer at data address `51:2734`.
Those planes drive the custom-glass status marks and battery above the raster.
QOM property `lcd-annunciators` and Web field `lcd_annunciators` expose this
electrode state read-only; the browser renders the fixed glass artwork from
those bits and never reads ADC or power controls directly.  The full raw
controller-line diagnostic remains available as `source=lcd-gram` (240x160).

To watch only changes in the original guest annunciator buffer:

```powershell
python .\monitor_np560_lcd_segments.py `
  --url http://127.0.0.1:8778 --interval 0.25
```

The monitor labels the two firmware planes by their proven controller line
numbers (`plane19` and `plane140`) and prints newly enabled/disabled electrode
indices without changing hardware inputs or injecting keys.

Every state response also reports `soc_rom_configured`, `soc_rom_size`, and
`soc_rom_sha256`. These bind a screen or memory dump to the executable image
selected on QEMU's machine object; comparing only resident menu data is not
sufficient because the v108 and v109 experiments share those resources while
their executable call at `1C:CFD6` differs.  The v109 and v110 experiments also
share the direct-menu resources, while v110 restores the exact 1172-byte
`23:A38C <- 40:A38C` application-context selector.  v110 and v113 share that
code and differ only in the 28 recovered first-initializer source bytes.  The Web debug panel shows
the ROM filename, byte size, and SHA-256 prefix (with the complete digest in its
title), so an old frontend can no longer be mistaken for the current experiment.

Long native runs can be watched without enabling the high-volume QEMU
instruction log.  The monitor below polls the Web/QMP state, emits one compact
heartbeat every five seconds, and pauses QEMU at the first unsupported/invalid
control state, missing-ROM fetch, odd instruction PC, IRQ FP-save overwrite, or
native `MENUOK` milestone.  After the LCD has shown at least 16 non-uniform
pixels, it also stops if the frame remains uniform for fifteen seconds.  The
longer default tolerates the firmware's multi-second blank transition frames
while still catching a persistent blank-after-visible failure close to the
responsible guest state.  A late attachment is armed from QEMU's retained
non-empty LCD-flush counter, so it can still catch a display which was already
blank when monitoring began.  The monitor also samples every `SYSMAIN` entry
and stops when SP descends for two consecutive lifecycles (16 bytes/cycle
minimum by default), which catches a leaking return chain before it reaches the
IRQ FP-save slot.
The output directory receives `events.jsonl`, the
complete register state, a JSON snapshot, the raw 240x120 gray5 frame, and a
rendered LCD PNG:

For the usual Web experiment on port 8775, the short entry point pins the ROM
SHA-256 reported at attachment time, resumes QEMU, and creates a timestamped
capture directory automatically:

```powershell
.\watch-np560-web.ps1
```

It names the exact `0x04D6` writer, next PC, old/new word, logical/physical
address, bus path (`BUS:1` translated data bus or `BUS:2` internal SRAM), SP,
and FP in both the console incident and `events.jsonl`.  Use `-NoResume` when an
already-paused instance must remain paused, or `-ExpectedSocRomSha256 DIGEST`
to reject an unintended Web instance before monitoring begins.

```powershell
python .\monitor_np560_web.py `
  --url http://127.0.0.1:8775 `
  --poll-interval 0.1 --heartbeat 5 --timeout 2400 `
  --expect-soc-rom-sha256 ROM_SHA256 `
  --output-dir ..\tmp\np560-monitor-run
```

Use `--stop-on incident`, `--stop-on menu`, or `--stop-on never` to narrow the
trigger. `--once --no-pause` captures an already-paused instance without
changing it, and `--resume` continues an instance before monitoring.
`--stack-descent-cycles` and `--stack-descent-min-bytes` tune the early warning;
`--no-stack-descent-check` disables only that stateful check.
`--blank-after-visible-seconds` and `--blank-min-visible-pixels` tune the LCD
watch; `--no-blank-after-visible-check` disables it.  This is an observer only:
it never alters guest RAM, NAND, registers, or reconstructed
ROM contents.

The current direct-menu experiment is built with the exact recovered page-zero
table, the guest-side manager/resource probe, and the exact upstream selector
used by the observed native `1B:CE3C -> 23:A38C -> 18:21F4` launch chain.  The
v109 artifact remains available as the pre-selector historical baseline and
v110 as the selector-plus-sentinel baseline.  v113 changes exactly the three
recovered first-initializer source windows (28 bytes total):

```powershell
python ..\disassembly\build_np560_reconstructed_rom.py `
  --initializer-overlay-probe --probe-rom-08-427e-return `
  --probe-rom-01-0200-return --probe-system-main `
  --probe-storage-global-templates --probe-direct-generic-menu `
  --output ..\tmp\np560-system-v380-direct-menu-v113.bin `
  --manifest ..\tmp\np560-system-v380-direct-menu-v113.json

python .\verify_np560_direct_menu_web.py `
  --url http://127.0.0.1:8775 `
  --soc-rom ..\tmp\np560-system-v380-direct-menu-v113.bin
```

The v113 SHA-256 is
`29bd2c1e5badd346c00c44d80e196efa84468839b68b90cae6d392a5970fda3d`.

The separate v112 image removes the direct-menu probe and therefore exercises
the ordinary shipped application chain instead of jumping to `2C:C9E8`.  v111
is retained as the otherwise-identical sentinel-source baseline:

```powershell
python ..\disassembly\build_np560_reconstructed_rom.py `
  --initializer-overlay-probe --probe-rom-08-427e-return `
  --probe-rom-01-0200-return --probe-system-main `
  --probe-storage-global-templates `
  --output ..\tmp\np560-system-v380-natural-v112.bin `
  --manifest ..\tmp\np560-system-v380-natural-v112.json

python .\verify_np560_natural_menu_web.py `
  --url http://127.0.0.1:8775 `
  --soc-rom ..\tmp\np560-system-v380-natural-v112.bin
```

Its SHA-256 is
`b7bbe361a253297724f9dd01a6707dfb6eb6b8559ab88bd1f032d8fa179abdfd`.
This is a dynamic-test candidate, not yet a claimed working-menu result.  The
QEMU binary must first be rebuilt from the current source so executable/data
aliases include the restored `23:A38C` window.  An older binary ignores the
guest's overlay copy for instruction fetch and executes the unrelated flat PRG
target instead; the resulting repeated or garbled glyph screen is therefore
not evidence against the recovered font data.

The natural verifier cannot be satisfied by the direct-menu probe.  It
requires the bounded application trace to show exact parent entry and balanced
return for `1B:D48E -> 23:A38C -> 23:A81E`, followed by resident launch manager,
registry lookup, generic-menu construction, all five recovered root labels,
distinct non-empty native glyph bitmaps, and the bottom-up ST7529 row mapping.

The verifier is read-only and operates on an already-running Web instance. It
requires the running instance to report the exact SHA-256 of the artifact passed
with `--soc-rom`, the exact `1C:CFD6 -> 07:4500` storage-pair call,
the `06:6840` resource callback marker, linked position `1C:9748`, the copied
root-page prefix, five constructed menu items, a native-font blit increase, a
non-uniform LCD frame, and the global bottom-up ST7529 row mapping.  A
non-zero framebuffer alone is deliberately not accepted: the recovered menu
stream sends complete GBK character words to guest renderer `32:7B42`, and
the verifier requires the exact five page-zero labels `娱乐`, `时间`, `计算`,
`翻译`, and `资料` in that bounded guest-call trace.  Thus random glyphs or a
repeat of the earlier initialization message cannot pass as a working menu.
It also correlates those ten GBK character words with the original
`17:9244 -> 18:657A` font-copy path, requiring a non-empty, distinct bitmap
hash for every character; a single replacement glyph repeated ten times is
therefore rejected as well.

HLE is off by default. It is retained only for CPU/ABI diagnostics:

```powershell
.\run-np560-web.ps1 -RomHle -HleUi
```

In that mode, select **physical memory diagnostic** in the page to view the
HLE bitmap. HLE does not stand in for the ST7529 in strict mode.

## Tests

```powershell
.\test-np560.ps1
.\test-np560-aux.ps1
.\test-np560-rom.ps1
.\test-np560-st7529.ps1
.\test-np560-driver.ps1
.\test-np560-lcd.ps1
.\test-np560-keyboard.ps1
.\test-np560-nand.ps1
.\test-np560-nand-rw.ps1
.\test-np560-ecc.ps1
.\test-np560-ecc-correction.ps1
.\test-np560-memory-split.ps1
.\test-np560-initializer-probe.ps1
.\test-np560-runtime-overlays.ps1
.\test-np560-web.ps1
python -m unittest discover -s ..\disassembly -p "test_*.py" -v
python ..\disassembly\analyse_np560_boot_contract.py
```

`test-np560-st7529.ps1` uses a minimal strict-mode firmware to verify command
and data MMIO. `test-np560-driver.ps1` extracts and executes the original
slot-1 driver, checks the hardware GRAM through the same Web/QMP path, and
asserts its exact first missing resident-ROM call.
`test-np560-lcd.ps1` tests only the explicitly enabled ROM-HLE graphics ABI.
`test-np560-keyboard.ps1` now delegates to the strict system boot and requires a
fully burned V3.80 checkpoint. It drives the real `F160/F164` matrix path,
`06:B126` key reader, and application scheduler; it does not use the obsolete
`03:0080`/`F340` exploration latch.
The lightweight Web regression additionally checks all letter, digit,
punctuation, navigation, and F1--F4 browser positions directly against the
three original 64-word event tables in `NP560.PRG`, and verifies that strict
Web input publishes only physical matrix/GPIO state with `key-code=0`.
`test-np560-nand.ps1` runs the unmodified vendor burner command 1 through the
reconstructed guest ROM and verifies its 528-byte DMA result against package
page `0x3F` plus erased OOB. `test-np560-nand-rw.ps1` is a pure guest-code
program/read/erase/read round trip and checks both returned bytes and device
counters. It then runs a second guest writer, saves a full checkpoint, starts
a third read-only guest, and verifies that both page data and OOB survive
across QEMU processes while the reader reports zero program/erase operations.
`test-np560-ecc.ps1` exhaustively verifies all 4,096 single-bit syndromes of the
paired-parity `F20A/F20C/F20E` hardware model. The vendor correction regression
then proves clean data is accepted, a single-bit error is restored, and a
double-bit error is rejected through the original burner routine.
`test-np560-memory-split.ps1` writes zero to data address `50:6000`
and then executes the untouched PRG/NOR instruction at code address `50:6000`,
proving the Harvard backings are no longer accidentally unified.
`test-np560-initializer-probe.ps1` deliberately supplies explicit sentinel
bytes at the three internal-ROM source ranges, runs the unmodified nine-descriptor
initializer at `24:7FE4`, verifies all nine `53:` RAM destinations, and requires
execution to stop at the still-unknown resident continuation `03:026A`. The
sentinels are diagnostic data and remain isolated from system images.  The
runtime-overlay path instead checks the exact `+0x1D` PRG storage copies; its
only non-zero first-chain storage word is `0x0280` at linked `21:FFFE`.

`test-np560-runtime-overlays.ps1` separately stops after both initializer
chains to validate all 9+261 descriptors, verifies the EMCR values, and checks
all 223 currently recovered runtime modules, including the exact resource/
storage graph. Older diagnostic variants can still stop at deliberately omitted
ROM entries; that stop is no longer the boundary of the complete system image.

`test-np560-system-boot.ps1 -NandCheckpoint FILE` is the end-to-end regression.
It requires the exact resident dispatcher, at least one physical NAND read, a
non-uniform hardware LCD frame, no missing ROM/unsupported instruction, and an
exact guest keyboard scan/press/release cycle. Supplying the four mapped events
proves both the inferred next-lifecycle continuation and the resident
in-application dispatch path:

```powershell
.\test-np560-system-boot.ps1 `
  -NandCheckpoint ..\tmp\np560-v380-flashed-ecc.nand `
  -RawEvent 0x100,0x101,0x102,0x104

.\test-np560-system-boot.ps1 `
  -NandCheckpoint ..\tmp\np560-v380-flashed-ecc.nand `
  -AllMatrixEvents

.\test-np560-system-lifecycle.ps1 `
  -NandCheckpoint ..\tmp\np560-v380-flashed-ecc.nand -Count 64

.\test-np560-system-web.ps1
```

`-AllMatrixEvents` now exercises all 64 physical positions in one QEMU process,
proving that keyboard state, application lifecycles, and resident stack frames
remain stable together. `-RowIsolatedMatrix` retains the older one-process-per-
row mode for focused hardware diagnosis.

The strict Web regression additionally requires `F340_READS=0`,
`KEY_CODE=00000000`, a non-uniform 28,800-byte ST7529 frame, and a second
`APPLICATION_TRACE=TOP` lifecycle after Enter is released. It now also pins
the second lifecycle's exact return as
`SCHEDRET ... /r0000:0080:0085/`; the three saved values are R0/R1/R2.

The current reconstructed-ROM unit suite contains 122 tests. The strict hardware gates also
include the 64-lifecycle stress run, all 64 physical key positions, the ST7529
bottom-up COM mapping, NAND data/OOB checkpoint persistence, and both ECC tests.

## Current boundary

There is currently no strict missing-code boundary on the exercised V3.80
checkpoint boot: it reaches the native resident/application path with
`ROM_MISSING=none` and `UNSUPPORTED=none`. The boundary is now behavioral
fidelity. The original bytes and exact ordering of resident `01:0200` and the
early application-state transition remain inferred rather than dumped from
hardware.  The first initializer's source values are no longer in that unknown
set: all three windows are recovered from bounded linked PRG storage islands.
The returned application's selection event is now proven to survive in R2;
the remaining unknown is how the factory manager maps that event and its
persistent state to the next application.
The exercised `0x84` transition itself now uses exact recovered `1F:B496` code;
the remaining inference is the surrounding resident loader/guard policy.
The original post-application scheduler/selection policy is likewise unknown;
the current system image deliberately loops the complete shipped `20:026A`
system main in guest code. A single-process repeated-exit stress run now passes
64 complete lifecycles, produces 1,554 LCD frames and 66 NAND reads, and keeps
both low-stack/low-frame diagnostics clear. This proves the cold activation
path must not be replayed, but does not reveal the factory manager's
application-selection decisions. The LCD path is active, non-uniform, uses the restored font pointer,
and its two native boot messages now agree with both the guest drawing
coordinates and bottom-up framebuffer contract. A complete Noah main screen
still has not been validated against a real device. The boot sample performs the
evidenced page-`0x3F` NAND read, but has not yet proved every filesystem/resource
operation or NAND write path used by normal applications.

The `F20A/F20C/F20E` paired-parity operation and the vendor single-bit
correction contract are now modeled and regression-tested. What remains unknown
is the factory filesystem's complete OOB layout, bad-block and wear policy, and
all application-level write/recovery paths, together with timers/interrupts,
audio, USB controller behavior, and remaining DMA/SFR paths.
With no physical unit, exact factory ROM bytes, timing, and electrical register
layout and the original LCD-init call order cannot be proven; the attainable target is a behaviorally compatible
clean-room reconstruction with explicit evidence and strict failures at every
unsupported boundary. The LCD, NAND, and keyboard paths follow that
hardware-model architecture rather than synthetic host ROM services.
