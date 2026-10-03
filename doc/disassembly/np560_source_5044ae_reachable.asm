; Reachable DMCU code from NP560-runtime-source-patched-v655.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x3044AE
; source word byte order: little
; source file word 0 maps to 50:44AE
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
50:44AE  2E00       LINK #0x00
50:44B0  58F0       MOV [--R15], R0
50:44B2  58F1       MOV [--R15], R1
50:44B4  4810       MOV R1, #0x0
50:44B6  4800       MOV R0, #0x0
50:44B8  58F1       MOV [--R15], R1
50:44BA  58F0       MOV [--R15], R0
50:44BC  BD0D 2F30  SCALL 0D:2F30
50:44C0  50F4       ADD R15, #0x4
50:44C2  381F       MOV R1, [R15++]
50:44C4  380F       MOV R0, [R15++]
50:44C6  2F00       UNLINK
50:44C8  C620       RETS
