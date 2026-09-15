# NP560.PRG DMCU auxiliary-image report

- Source: `C:\Users\ASUS\Documents\ChatGPT\np560\NP560+V3.80版系统升级程序\NP560.PRG`
- Selected file range: `0x2B0000..0x2C0000`
- Size: 65,536 bytes / 32,768 words
- SHA-256: `8f43ee1a0297378f965c532eeac727b4af0df75987e19322085a66dec53047c7`
- 16-bit word byte order: `little`
- Mapping: source word 0 = `4B:0000`
- Entry seeds: `4B:2B6E`

## Results

- Reachable instructions: 170
- Call instructions: 2
- Unknown/reserved frontiers: 0
- Overlapping decode targets: 0

## Unresolved targets

- `32:EC6E`: 1 reference(s)
- `33:66E2`: 1 reference(s)

## Boundary and ABI interpretation

- `4B:2B6E` begins with `LINK #3`, saves `R0/R1/R2/R3/R6/R7`, and consumes one
  far-pointer argument from `FP+6/FP+8`.
- All decoded branches remain inside `4B:2B6E..2CF6`; the function restores the
  saved registers, executes `UNLINK`, and returns with `RETS` at `4B:2CF6`.
  The exact copy range is therefore `0x018A` bytes (`4B:2B6E..2CF7`).
- The helper derives rectangle/coordinate words from the pointed object, passes
  four words to `32:EC6E`, then calls `33:66E2` to commit the result. It does not
  read or write the browser object's logical `+0x12` valid-item byte.

## Dependency closure

- `32:EC6E ← 4F:EC6E` is already restored by
  `STORAGE_RANGE_DISPATCH_OVERLAY_*`. It is a framed four-word adapter whose
  only child is the already restored `27:507C ← 44:507C` body.
- `33:66E2 ← 50:66E2` is already restored by
  `APPLICATION_UI_COMMIT_OVERLAY_*`. It is a `LINK #0` wrapper around the
  already restored `31:4BAC ← 4E:4BAC` startup/UI commit body.
- No call retarget or additional closure overlay is required after copying this
  exact function to `2E:2B6E`.

## Why v736 was wrong and v737 is exact

The complete renderer source calls `2E:2B6E` at `3E:D3FE`. Flat `2E:2B6E` is
only an internal suffix of the unrelated `2E:1752` input function: it has no
`LINK` and relies on that input caller's `R11` locals. The input function is
relocated to `11:1752`, so its 18 *internal* self-calls correctly become
`11:2B6E`; the external renderer call must not follow that relocation.

v737 keeps the renderer's original `SCALL 2E:2B6E` and installs this complete
source body at that linked target. It changes no return value, object field,
NAND data, or host-side device behavior.
