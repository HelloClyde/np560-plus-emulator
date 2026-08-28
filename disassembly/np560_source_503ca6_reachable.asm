; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x303CA6
; source word byte order: little
; source file word 0 maps to 50:3CA6
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
50:3CA6  2E00       LINK #0x00
50:3CA8  58F0       MOV [--R15], R0
50:3CAA  58F1       MOV [--R15], R1
50:3CAC  4810       MOV R1, #0x0
50:3CAE  4800       MOV R0, #0x0
50:3CB0  58F1       MOV [--R15], R1
50:3CB2  58F0       MOV [--R15], R0
50:3CB4  480B       MOV R0, #0xB
50:3CB6  58F0       MOV [--R15], R0
50:3CB8  BD1B 23B8  SCALL 1B:23B8
50:3CBC  50F6       ADD R15, #0x6
50:3CBE  381F       MOV R1, [R15++]
50:3CC0  380F       MOV R0, [R15++]
50:3CC2  2F00       UNLINK
50:3CC4  C620       RETS
