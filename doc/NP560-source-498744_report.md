# NP560.PRG DMCU auxiliary-image report

- Source: `C:\Users\ASUS\Documents\ChatGPT\np560\NP560+V3.80版系统升级程序\NP560.PRG`
- Selected file range: `0x290000..0x2A0000`
- Size: 65,536 bytes / 32,768 words
- SHA-256: `238da7f47f497f8ca9b3422879a910ff32f1a829005caebd68de7a7942ee7a14`
- 16-bit word byte order: `little`
- Mapping: source word 0 = `49:0000`
- Entry seeds: `49:8744`

## Results

- Reachable instructions: 192
- Call instructions: 11
- Unknown/reserved frontiers: 0
- Overlapping decode targets: 0

## Unresolved targets

- `32:DB08`: 10 reference(s)
- `32:B922`: 1 reference(s)

## Boundary and ABI interpretation

- `49:8744` begins with `LINK #0`, saves `R0..R3`, and consumes the six
  16-bit stack slots at `FP+6..FP+10`.  The three structural callers each
  remove exactly `0x0C` argument bytes after `SCALL 2C:8744`.
- All decoded branches stay inside `49:8744..8930`.  The function restores
  `R0..R3`, executes `UNLINK`, and returns at `49:8930`; `49:8932` begins the
  next `LINK #0x23` function.  The exact copy range is therefore `0x01EE`
  bytes (`49:8744..8931`).
- The body performs only coordinate/line drawing.  It does not read or write
  the file-browser object or its logical `+0x12` byte.

## Dependency closure

- One call to `32:B922` uses the already restored
  `APPLICATION_MAIN_ACTION_RENDER_CLEAR_OVERLAY_*` body.
- Ten calls to `32:DB08` use the already restored
  `APPLICATION_RESOURCE_OPEN_OVERLAY_*` body.  Despite the historical name,
  this is the exact five-argument drawing primitive used by this function.
- There are no other direct calls, unknown frontiers, or overlapping decode
  targets.  No additional dependency overlay or call retarget is required.

## Why the flat target is invalid

The exact renderer calls `2C:8744` at `3A:8A20`, `3E:D12E`, and `3E:D17A`.
Flat `2C:8744` is the middle of an unrelated large controller: it has no
`LINK`, inherits another function's `R11` frame, reaches `2C:87F8 → 1C:D462`,
and finally returns from `2C:9B94` past the renderer's own epilogues.  That
misexecution produced the observed `obj+0x12=0` diagnostic; it was not evidence
that a constructor should be forced to write the field.

The apparent overlap with the larger `2C:7E18..9B94` body is an original ROM
lifecycle, not two functions that must execute from segment 2C simultaneously.
Thirteen shipped call sites target the missing resident entry `0F:7E18`, while
there are no calls to `2C:7E18`.  The latter is its complete `+0x1D` source
image: a `LINK #0x16` function with 2,266 reachable instructions, 26 calls, no
unknown opcode, and a balanced return at `2C:9B94`.

The reconstructed resident ROM therefore first publishes the whole controller
at `0F:7E18..9B96`.  The late guest installer can then copy this complete
layout body to the original writable `2C:8744` target without destroying the
controller; QEMU exposes that narrow destination as coherent data/code RAM.
The controller's computed dispatcher reads fifteen near targets from
`0F:7E92..7EB0` through the Harvard data bus, so QEMU also exposes that exact
`0x1E`-byte reconstructed-ROM subrange as a read-only data alias.  The
controller's six not-yet-closed external dependency targets remain explicit
follow-up work; restoring the body does not claim that its entire call closure
is already complete.
All three renderer callers retain their original target.  This restores the
vendor layering and changes no object field, return value, NAND content, or
host-side device behavior.  The interim v739 relocation attempt was never used
for dynamic evidence and is superseded by this source-to-resident recovery.
