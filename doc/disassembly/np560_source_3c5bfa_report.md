# NP560.PRG DMCU auxiliary-image report

- Source: `C:\Users\ASUS\Documents\ChatGPT\np560\NP560+V3.80版系统升级程序\NP560.PRG`
- Selected file range: `0x1C0000..0x1D0000`
- Size: 65,536 bytes / 32,768 words
- SHA-256: `c2d9b27c2d1f23cac83659309f8a55a3a4914d7ca00837eec2c2d1036a2e95e5`
- 16-bit word byte order: `little`
- Mapping: source word 0 = `3C:0000`
- Entry seeds: `3C:5BFA`

## Results

- Reachable instructions: 607
- Call instructions: 13
- Unknown/reserved frontiers: 0
- Overlapping decode targets: 0

## Unresolved targets

- `33:07B0`: 10 reference(s)
- `33:5B70`: 2 reference(s)
- `33:5ABA`: 1 reference(s)

## Function boundary

- The preceding source function ends with `UNLINK; RETS` at
  `3C:5BF6..3C:5BF8`.
- The candidate begins independently at `3C:5BFA` with `LINK #0x04`, saves
  `R1..R7`, and has one closed epilogue at `3C:61EE..3C:61FE`.
- The following source function begins at `3C:6200` with `LINK #0x0F`.
- Therefore the exact copy range is `3C:5BFA..3C:61FF`, or `0x0606` bytes.

## Xref and ABI audit

- Four structural PRG calls target resident `1F:5BFA`: `2D:6D40`,
  `39:D92C`, `3B:EBCA`, and `3B:F052`.  Every call has the identical sequence
  `PUSH R1; PUSH R0; SCALL 1F:5BFA; ADD SP,#4`, proving one two-word far
  pointer argument and caller cleanup of four bytes.
- No PRG call targets the source address `3C:5BFA`; it is linked storage for
  the missing resident entry, not an independently live source function.
- The observed live caller `1C:D92C` is the same-PC resident copy of
  `39:D92C`, inside the already closed `1C:D462 <- 39:D462` file-browser
  layout body.  The runtime missing-ROM record therefore agrees exactly with
  the static xref and ABI.
- Same-segment `AJMP` targets use only the 16-bit PC and all remain inside the
  copied range, so moving source segment `3C` to resident segment `1F` does
  not require instruction rewriting.

## Dependency closure

- Ten calls target the ordinary PRG function at `33:07B0`.
- Two calls target the already recovered same-PC overlay
  `33:5B70 <- 50:5B70`.
- The remaining call targets `33:5ABA`.  Flat `33:5ABA` is an incompatible
  internal branch target in the source `33:52AA` worker: `33:5AB2` contains
  `AJMP ULE,33:5ABA`.  The worker has an exact resident copy at
  `16:52AA <- 33:52AA`, and calls target the resident entry rather than the
  source entry, but that does not prove every possible execution of source
  bank 33 has retired before a runtime overlay install.  Permanently replacing
  `33:5ABA` would therefore have an unresolved lifetime collision.
- The exact linked implementation is the complete call-free leaf
  `50:5ABA..50:5AC6`; twelve PRG sites call logical `33:5ABA` and none call
  the source.  It is embedded unchanged at the collision-free resident slot
  `06:1CF0..06:1CFD`.  The slot follows the exact `50:5906` leaf ending at
  `06:1CEF`, precedes the clear-buffer routine at `06:1D00`, and does not
  overlap the menu-dependency installer, which ends at `06:1CBF`.
- Only the source-proven call in this copied function is retargeted:
  `3C:5C16: SCALL 33:5ABA` becomes
  `1F:5C16: SCALL 06:1CF0`.  All other words of the `1F:5BFA` resident body
  remain the shipped `3C:5BFA` words, and flat `33:5ABA` remains untouched.
- No HLE return, state patch, or guessed result is used.
