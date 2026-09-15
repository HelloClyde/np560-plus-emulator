; Reachable DMCU code from NP560-runtime-source-patched-v655.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x303C86
; source word byte order: little
; source file word 0 maps to 50:3C86
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
50:3C86  2E00       LINK #0x00
50:3C88  58F0       MOV [--R15], R0
50:3C8A  58F1       MOV [--R15], R1
50:3C8C  68F1 2734  MOV REG[0xF1], #0x2734
50:3C90  68F0 0051  MOV REG[0xF0], #0x0051
50:3C94  58F1       MOV [--R15], R1
50:3C96  58F0       MOV [--R15], R0
50:3C98  BD14 6E10  SCALL 14:6E10
50:3C9C  50F4       ADD R15, #0x4
50:3C9E  381F       MOV R1, [R15++]
50:3CA0  380F       MOV R0, [R15++]
50:3CA2  2F00       UNLINK
50:3CA4  C620       RETS
