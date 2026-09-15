# NP560.PRG DMCU auxiliary-image report

- Source: `C:\Users\ASUS\Documents\ChatGPT\np560\NP560+V3.80版系统升级程序\NP560.PRG`
- Selected file range: `0x300000..0x310000`
- Size: 65,536 bytes / 32,768 words
- SHA-256: `28f84ed40d49fb4c871624aa28966e3f326246dac21b533e7b3be018ca6a8e1b`
- 16-bit word byte order: `little`
- Mapping: source word 0 = `50:0000`
- Entry seeds: `50:5ABA`

## Results

- Reachable instructions: 5
- Call instructions: 0
- Unknown/reserved frontiers: 0
- Overlapping decode targets: 0

## Unresolved targets

- None

## Boundary, xref, and ABI audit

- `50:5ABA` begins with `LINK #0`, switches `DS0` to `00A1`, zero-extends the
  byte at `A1:3886` into `R0`, and ends with balanced `UNLINK; RETS` at
  `50:5AC4..50:5AC6`.
- It takes no stack arguments and makes no child calls.
- Twelve structural PRG calls target logical `33:5ABA`; no call targets
  source `50:5ABA`.  Flat `33:5ABA` is an internal branch target in a larger
  segment-33 worker, not this five-instruction leaf.
- Specifically, the source `33:52AA` worker branches from `33:5AB2` to
  `33:5ABA`.  Although its exact resident copy exists at
  `16:52AA <- 33:52AA` and direct call scans find no call to source entry
  `33:52AA`, that is insufficient to prove the source bank can never execute
  the internal branch after overlay installation.  A same-PC install is
  therefore unsafe.
- The exact `0x000E` source bytes are instead embedded unchanged at resident
  `06:1CF0..06:1CFD`.  This verified gap is bounded by the exact `50:5906`
  resident leaf ending at `06:1CEF` and the clear-buffer routine beginning at
  `06:1D00`; the preceding menu-dependency installer ends at `06:1CBF`.
- Only the copied caller is patched: source `3C:5C16` contains
  `SCALL 33:5ABA`, while resident `1F:5C16` calls `06:1CF0`.  No runtime write
  touches `33:5ABA`, and the other eleven logical callers are not guessed or
  globally redirected.  This closes the active dependency of
  `1F:5BFA <- 3C:5BFA` without a host-side service or guessed return value.
